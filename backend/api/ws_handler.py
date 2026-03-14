"""
WebSocket 핸들러 — 마켓별 구독 분리

- ticker 채널: 클라이언트가 ?market=KRW-BTC로 연결 → 해당 마켓 이벤트만 수신
- candle 채널: 마켓별 분리, 실제 최신 캔들 payload 제공 (단순 알림 X)
- Upbit 스트림: 실제 구독 중인 마켓만 등록, 동적 추가/제거 지원
- 비정상 종료 후 재연결 시 자동 복구
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect
from core.upbit_client import UpbitWebSocketClient, get_ticker, get_candles_df

logger = logging.getLogger(__name__)

# ─── 연결 레지스트리 ───────────────────────────────────────────────
# { market: Set[WebSocket] }
_ticker_clients: Dict[str, Set[WebSocket]] = defaultdict(set)
_candle_clients: Dict[str, Set[WebSocket]] = defaultdict(set)

_upbit_ws: UpbitWebSocketClient | None = None
_subscribed_markets: Set[str] = set()
_bot_markets: Set[str] = set()   # 스캘핑 봇이 점유 중인 마켓 (브라우저 없어도 스트림 유지)
_ws_lock = asyncio.Lock()


async def _broadcast_to_market(clients_map: Dict[str, Set[WebSocket]], market: str, data: dict):
    """특정 마켓 구독 클라이언트에게만 브로드캐스트."""
    clients = clients_map.get(market)
    if not clients:
        return
    disconnected = set()
    for ws in clients.copy():
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.add(ws)
    clients -= disconnected


async def on_ticker_update(data: dict):
    market = data.get("market", "KRW-BTC")
    await _broadcast_to_market(_ticker_clients, market, {"type": "ticker", **data})

    # candle 구독 클라이언트에게 해당 마켓의 최신 캔들 payload 전송
    if _candle_clients.get(market):
        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: get_candles_df(market, "1m", count=2))
            if not df.empty:
                latest = df.iloc[-1]
                candle_payload = {
                    "type": "candle",
                    "market": market,
                    "open": float(latest["open"]),
                    "high": float(latest["high"]),
                    "low": float(latest["low"]),
                    "close": float(latest["close"]),
                    "volume": float(latest["volume"]),
                    "timestamp": int(df.index[-1].timestamp()),
                }
                await _broadcast_to_market(_candle_clients, market, candle_payload)
        except Exception as e:
            logger.debug("Candle broadcast error: %s", e)


async def _ensure_market_subscribed(market: str):
    """해당 마켓이 Upbit 스트림에 아직 없으면 추가한다."""
    global _upbit_ws, _subscribed_markets

    async with _ws_lock:
        if market in _subscribed_markets:
            return

        _subscribed_markets.add(market)
        markets_list = list(_subscribed_markets)

        if _upbit_ws is not None:
            await _upbit_ws.stop()
            _upbit_ws = None

        _upbit_ws = UpbitWebSocketClient(markets_list, on_ticker=on_ticker_update)
        asyncio.create_task(_upbit_ws.start())
        logger.info("Upbit stream restarted with markets: %s", markets_list)


async def _release_market_if_unused(market: str):
    """해당 마켓 구독자가 0명이 되면 Upbit 스트림에서 제거한다."""
    global _upbit_ws, _subscribed_markets

    has_ticker = bool(_ticker_clients.get(market))
    has_candle = bool(_candle_clients.get(market))
    has_bot = market in _bot_markets  # 스캘핑 봇이 점유 중이면 유지
    if has_ticker or has_candle or has_bot:
        return

    async with _ws_lock:
        _subscribed_markets.discard(market)
        if not _subscribed_markets:
            if _upbit_ws is not None:
                await _upbit_ws.stop()
                _upbit_ws = None
            return

        markets_list = list(_subscribed_markets)
        if _upbit_ws is not None:
            await _upbit_ws.stop()
        _upbit_ws = UpbitWebSocketClient(markets_list, on_ticker=on_ticker_update)
        asyncio.create_task(_upbit_ws.start())
        logger.info("Upbit stream restarted after removing %s: %s", market, markets_list)


# ─── 봇 전용 구독 관리 ────────────────────────────────────────────
async def subscribe_for_bot(market: str):
    """스캘핑 봇 시작 시 호출 — 브라우저 없이도 해당 마켓 Upbit 스트림을 유지한다."""
    _bot_markets.add(market)
    await _ensure_market_subscribed(market)
    logger.info("Bot subscribed to market stream: %s", market)


async def unsubscribe_for_bot(market: str):
    """스캘핑 봇 종료 시 호출 — 브라우저 구독자도 없으면 스트림을 해제한다."""
    _bot_markets.discard(market)
    await _release_market_if_unused(market)
    logger.info("Bot unsubscribed from market stream: %s", market)


# ─── 공개 초기화 (main.py lifespan에서 호출) ──────────────────────
async def start_upbit_stream(markets: list[str] = None):
    """초기 마켓 목록으로 Upbit 스트림을 시작한다 (이후 동적 추가 가능)."""
    global _upbit_ws, _subscribed_markets
    if markets:
        for m in markets:
            _subscribed_markets.add(m)
    if _upbit_ws is not None:
        return
    if _subscribed_markets:
        _upbit_ws = UpbitWebSocketClient(list(_subscribed_markets), on_ticker=on_ticker_update)
        asyncio.create_task(_upbit_ws.start())
        logger.info("Upbit stream started: %s", list(_subscribed_markets))


# ─── Ticker WebSocket 핸들러 ──────────────────────────────────────
async def handle_ticker_ws(websocket: WebSocket):
    await websocket.accept()
    market = websocket.query_params.get("market", "KRW-BTC")
    _ticker_clients[market].add(websocket)

    await _ensure_market_subscribed(market)

    # 초기 현재가 즉시 전송
    try:
        ticker = get_ticker(market)
        if ticker:
            await websocket.send_json({"type": "ticker", **ticker})
    except Exception:
        pass

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _ticker_clients[market].discard(websocket)
        await _release_market_if_unused(market)


# ─── Candle WebSocket 핸들러 ─────────────────────────────────────
async def handle_candle_ws(websocket: WebSocket):
    """캔들 구독 WebSocket — 실제 최신 캔들 payload를 스트림으로 제공한다."""
    await websocket.accept()
    market = websocket.query_params.get("market", "KRW-BTC")
    interval = websocket.query_params.get("interval", "1m")
    _candle_clients[market].add(websocket)

    await _ensure_market_subscribed(market)

    # 초기 최신 캔들 즉시 전송
    try:
        df = get_candles_df(market, interval, count=2)
        if not df.empty:
            latest = df.iloc[-1]
            await websocket.send_json({
                "type": "candle",
                "market": market,
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "close": float(latest["close"]),
                "volume": float(latest["volume"]),
                "timestamp": int(df.index[-1].timestamp()),
            })
    except Exception:
        pass

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _candle_clients[market].discard(websocket)
        await _release_market_if_unused(market)
