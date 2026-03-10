import asyncio
import json
import os
import websockets
import pyupbit
import pandas as pd
from dotenv import load_dotenv
from typing import Optional, Callable

load_dotenv()

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")

INTERVAL_MAP = {
    "1m": ("minute", 1),
    "3m": ("minute", 3),
    "5m": ("minute", 5),
    "15m": ("minute", 15),
    "1h": ("minute", 60),
    "4h": ("minute", 240),
    "1d": ("day", None),
}


def get_upbit_client() -> Optional[pyupbit.Upbit]:
    if UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY:
        return pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)
    return None


def get_candles(market: str, interval: str, count: int = 200) -> list[dict]:
    interval_type, interval_val = INTERVAL_MAP.get(interval, ("minute", 1))

    if interval_type == "minute":
        df = pyupbit.get_ohlcv(market, interval=f"minute{interval_val}", count=count)
    else:
        df = pyupbit.get_ohlcv(market, interval="day", count=count)

    if df is None or df.empty:
        return []

    candles = []
    for ts, row in df.iterrows():
        candles.append({
            "time": int(ts.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return candles


def get_candles_df(market: str, interval: str, count: int = 200) -> pd.DataFrame:
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
    orderbook = pyupbit.get_orderbook(market)
    result = {"market": market, "price": ticker}
    if orderbook and len(orderbook) > 0:
        ob = orderbook[0]
        result["ask_price"] = ob["orderbook_units"][0]["ask_price"]
        result["bid_price"] = ob["orderbook_units"][0]["bid_price"]
    return result


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
            if price is None:
                result = upbit.buy_market_order(market, volume)
            else:
                result = upbit.buy_limit_order(market, price, volume)
        else:
            if price is None:
                result = upbit.sell_market_order(market, volume)
            else:
                result = upbit.sell_limit_order(market, price, volume)
        return result if result else {}
    except Exception as e:
        return {"error": str(e)}


class UpbitWebSocketClient:
    """Upbit 실시간 WebSocket 클라이언트"""

    UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"

    def __init__(self, markets: list[str], on_ticker: Callable = None, on_candle: Callable = None):
        self.markets = markets
        self.on_ticker = on_ticker
        self.on_candle = on_candle
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
                    ping_timeout=10
                ) as ws:
                    subscribe_msg = json.dumps([
                        {"ticket": "trading-app"},
                        {"type": "ticker", "codes": self.markets},
                    ])
                    await ws.send(subscribe_msg)

                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(raw)

                        if data.get("type") == "ticker" and self.on_ticker:
                            await self.on_ticker({
                                "market": data["code"],
                                "price": data["trade_price"],
                                "change": data["signed_change_rate"],
                                "volume": data["acc_trade_volume_24h"],
                                "timestamp": data["timestamp"],
                            })
            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
                if self._running:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    await asyncio.sleep(5)
