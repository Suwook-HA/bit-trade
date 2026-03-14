import asyncio
import json
import os
import websockets
import pyupbit
import pandas as pd
from collections import defaultdict, deque
from dotenv import load_dotenv
from typing import Optional, Callable, Dict

load_dotenv()

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")

# ─── Interval 설정 ────────────────────────────────────────────────
INTERVAL_MAP = {
    "5s":  ("second", 5),
    "10s": ("second", 10),
    "15s": ("second", 15),
    "30s": ("second", 30),
    "1m":  ("minute", 1),
    "3m":  ("minute", 3),
    "5m":  ("minute", 5),
    "15m": ("minute", 15),
    "1h":  ("minute", 60),
    "4h":  ("minute", 240),
    "1d":  ("day", None),
}

# 서브-분봉(스캘핑) 인터벌 — REST API 미지원, TickAggregator 사용
SCALPING_INTERVALS: frozenset = frozenset({"5s", "10s", "15s", "30s"})

INTERVAL_SECONDS_MAP: Dict[str, int] = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


# ─── 기본 클라이언트 ──────────────────────────────────────────────
def get_upbit_client() -> Optional[pyupbit.Upbit]:
    if UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY:
        return pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)
    return None


def get_candles(market: str, interval: str, count: int = 200) -> list:
    if interval in SCALPING_INTERVALS:
        agg = get_tick_aggregator(INTERVAL_SECONDS_MAP[interval])
        df = agg.get_history_df(market)
        if df.empty:
            return []
        return [
            {
                "time": int(ts.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for ts, row in df.tail(count).iterrows()
        ]

    interval_type, interval_val = INTERVAL_MAP.get(interval, ("minute", 1))
    if interval_type == "minute":
        df = pyupbit.get_ohlcv(market, interval=f"minute{interval_val}", count=count)
    else:
        df = pyupbit.get_ohlcv(market, interval="day", count=count)

    if df is None or df.empty:
        return []
    return [
        {
            "time": int(ts.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]


def get_candles_df(market: str, interval: str, count: int = 200) -> pd.DataFrame:
    if interval in SCALPING_INTERVALS:
        return get_tick_aggregator(INTERVAL_SECONDS_MAP[interval]).get_history_df(market)

    interval_type, interval_val = INTERVAL_MAP.get(interval, ("minute", 1))
    if interval_type == "minute":
        df = pyupbit.get_ohlcv(market, interval=f"minute{interval_val}", count=count)
    else:
        df = pyupbit.get_ohlcv(market, interval="day", count=count)
    return df if df is not None else pd.DataFrame()


def get_ticker(market: str) -> dict:
    ticker = pyupbit.get_current_price(market)
    if ticker is None:
        return {}
    orderbook_raw = pyupbit.get_orderbook(market)
    result = {"market": market, "price": ticker}
    # pyupbit.get_orderbook() returns a list, not dict
    orderbook = orderbook_raw[0] if isinstance(orderbook_raw, list) and orderbook_raw else orderbook_raw
    if orderbook and isinstance(orderbook, dict) and "orderbook_units" in orderbook:
        result["ask_price"] = orderbook["orderbook_units"][0]["ask_price"]
        result["bid_price"] = orderbook["orderbook_units"][0]["bid_price"]
    return result


def get_orderbook_imbalance(market: str, depth: int = 5) -> dict:
    """상위 N 호가의 매수/매도 잔량 불균형 지수를 반환한다.

    imbalance in [-1, 1]:
      +1 = 완전 매수 우위 (bid-heavy), -1 = 완전 매도 우위 (ask-heavy)
    spread_pct: 최우선 매도-매수 스프레드 (%)
    """
    orderbook_raw = pyupbit.get_orderbook(market)
    # pyupbit.get_orderbook() returns a list, not dict
    orderbook = orderbook_raw[0] if isinstance(orderbook_raw, list) and orderbook_raw else orderbook_raw
    if not orderbook or not isinstance(orderbook, dict) or "orderbook_units" not in orderbook:
        return {"imbalance": 0.0, "bid_vol": 0.0, "ask_vol": 0.0, "spread_pct": 0.0}

    units = orderbook["orderbook_units"][:depth]
    bid_vol = sum(u["bid_size"] for u in units)
    ask_vol = sum(u["ask_size"] for u in units)
    total = bid_vol + ask_vol
    imbalance = (bid_vol - ask_vol) / total if total > 0 else 0.0

    spread_pct = 0.0
    if units:
        best_ask = units[0]["ask_price"]
        best_bid = units[0]["bid_price"]
        mid = (best_ask + best_bid) / 2
        if mid > 0:
            spread_pct = (best_ask - best_bid) / mid * 100

    return {
        "imbalance": round(imbalance, 4),
        "bid_vol": round(bid_vol, 4),
        "ask_vol": round(ask_vol, 4),
        "spread_pct": round(spread_pct, 4),
    }


def get_balance(currency: str = "KRW") -> float:
    upbit = get_upbit_client()
    if upbit is None:
        return 0.0
    balance = upbit.get_balance(currency)
    return float(balance) if balance else 0.0


def place_order(side: str, market: str, price: float = None, volume: float = None) -> dict:
    upbit = get_upbit_client()
    if upbit is None:
        return {"error": "No API key configured"}
    try:
        if side == "buy":
            result = upbit.buy_market_order(market, volume) if price is None else upbit.buy_limit_order(market, price, volume)
        else:
            result = upbit.sell_market_order(market, volume) if price is None else upbit.sell_limit_order(market, price, volume)
        return result if result else {}
    except Exception as e:
        return {"error": str(e)}


# ─── TickAggregator ───────────────────────────────────────────────
def _new_candle(period_start: float, price: float, volume: float) -> dict:
    return {
        "period_start": period_start,
        "open": price, "high": price, "low": price, "close": price,
        "volume": volume, "trade_count": 1,
    }


class TickAggregator:
    """WebSocket tick을 서브-분봉 OHLCV 캔들로 집계한다.

    per-market:
      - _open_candles: 현재 진행 중인 캔들
      - _history: 완성된 캔들 링 버퍼 (maxlen=500)
      - _queues: 완성 캔들 이벤트 큐 (봇 이벤트 주도 루프가 await)
    """

    def __init__(self, interval_seconds: int):
        self._interval = interval_seconds
        self._open_candles: Dict[str, dict] = {}
        self._queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

    async def on_tick(self, market: str, price: float, volume: float, timestamp_s: float):
        """tick 1건 처리. WebSocket 핸들러에서 호출."""
        period_start = int(timestamp_s // self._interval) * self._interval
        cur = self._open_candles.get(market)

        if cur is None:
            self._open_candles[market] = _new_candle(period_start, price, volume)
            return

        if cur["period_start"] != period_start:
            # 기간 전환 — 완성 캔들 방출
            completed = dict(cur)
            self._history[market].append(completed)
            await self._queues[market].put(completed)
            self._open_candles[market] = _new_candle(period_start, price, volume)
        else:
            cur["high"] = max(cur["high"], price)
            cur["low"] = min(cur["low"], price)
            cur["close"] = price
            cur["volume"] += volume
            cur["trade_count"] += 1

    async def get_next_candle(self, market: str) -> dict:
        """다음 완성 캔들이 올 때까지 블로킹. 봇 이벤트 루프에서 사용."""
        return await self._queues[market].get()

    def get_history_df(self, market: str) -> pd.DataFrame:
        """완성된 캔들 이력을 DataFrame으로 반환 (신호 계산용)."""
        history = list(self._history[market])
        if not history:
            return pd.DataFrame()
        df = pd.DataFrame(history)
        df.index = pd.to_datetime(df["period_start"], unit="s", utc=True).dt.tz_localize(None)
        return df[["open", "high", "low", "close", "volume"]].copy()

    def seed_from_df(self, market: str, df: pd.DataFrame):
        """봇 시작 시 1m 캔들로 이력을 초기화 (warm-up)."""
        if df.empty:
            return
        for ts, row in df.iterrows():
            self._history[market].append({
                "period_start": int(ts.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "trade_count": 1,
            })


# ─── TickAggregator 싱글턴 팩토리 ───────────────────────────────
_tick_aggregators: Dict[int, TickAggregator] = {}


def get_tick_aggregator(interval_seconds: int) -> TickAggregator:
    if interval_seconds not in _tick_aggregators:
        _tick_aggregators[interval_seconds] = TickAggregator(interval_seconds)
    return _tick_aggregators[interval_seconds]


def dispatch_tick_to_aggregators(market: str, price: float, volume: float, timestamp_s: float):
    """활성 TickAggregator 전체에 tick을 비동기로 전달. WebSocket 핸들러 내부에서 호출."""
    for agg in _tick_aggregators.values():
        asyncio.create_task(agg.on_tick(market, price, volume, timestamp_s))


# ─── Upbit WebSocket 클라이언트 ──────────────────────────────────
class UpbitWebSocketClient:
    """Upbit 실시간 WebSocket — ticker + orderbook 구독, tick 집계 자동 전달"""

    UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"

    def __init__(
        self,
        markets: list,
        on_ticker: Callable = None,
        on_orderbook: Callable = None,
    ):
        self.markets = markets
        self.on_ticker = on_ticker
        self.on_orderbook = on_orderbook
        self._running = False
        self._task = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run(self):
        while self._running:
            try:
                async with websockets.connect(
                    self.UPBIT_WS_URL,
                    ping_interval=60,
                    ping_timeout=10,
                ) as ws:
                    types = [{"type": "ticker", "codes": self.markets}]
                    if self.on_orderbook:
                        types.append({
                            "type": "orderbook",
                            "codes": self.markets,
                            "isOnlyRealtime": True,
                        })
                    subscribe_msg = json.dumps([{"ticket": "trading-app"}] + types)
                    await ws.send(subscribe_msg)

                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(raw)
                        msg_type = data.get("type")

                        if msg_type == "ticker":
                            market = data["code"]
                            price = data["trade_price"]
                            trade_vol = data.get("trade_volume", 0.0)   # 건당 체결량
                            timestamp_s = data.get("timestamp", 0) / 1000.0

                            # 활성 TickAggregator에 tick 전달
                            if _tick_aggregators:
                                dispatch_tick_to_aggregators(market, price, trade_vol, timestamp_s)

                            if self.on_ticker:
                                await self.on_ticker({
                                    "market": market,
                                    "price": price,
                                    "change": data["signed_change_rate"],
                                    "volume": data["acc_trade_volume_24h"],
                                    "trade_volume": trade_vol,
                                    "timestamp": data["timestamp"],
                                })

                        elif msg_type == "orderbook" and self.on_orderbook:
                            await self.on_orderbook(data)

            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
                if self._running:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    await asyncio.sleep(5)
