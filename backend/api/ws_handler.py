import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from core.upbit_client import UpbitWebSocketClient, get_ticker

# 연결된 클라이언트 목록
_ticker_clients: set[WebSocket] = set()
_candle_clients: set[WebSocket] = set()

_upbit_ws: UpbitWebSocketClient = None


async def _broadcast(clients: set[WebSocket], data: dict):
    disconnected = set()
    for ws in clients.copy():
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.add(ws)
    clients -= disconnected


async def on_ticker_update(data: dict):
    await _broadcast(_ticker_clients, {"type": "ticker", **data})


async def start_upbit_stream(markets: list[str] = ["KRW-BTC"]):
    global _upbit_ws
    if _upbit_ws is not None:
        return

    _upbit_ws = UpbitWebSocketClient(markets, on_ticker=on_ticker_update)
    await _upbit_ws.start()


async def handle_ticker_ws(websocket: WebSocket):
    await websocket.accept()
    _ticker_clients.add(websocket)

    # Send initial ticker immediately
    try:
        ticker = get_ticker("KRW-BTC")
        if ticker:
            await websocket.send_json({"type": "ticker", **ticker})
    except Exception:
        pass

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        _ticker_clients.discard(websocket)
    except Exception:
        _ticker_clients.discard(websocket)


async def handle_candle_ws(websocket: WebSocket):
    """캔들 업데이트용 WebSocket - 현재가 변경시 클라이언트에 알림"""
    await websocket.accept()
    _candle_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _candle_clients.discard(websocket)
    except Exception:
        _candle_clients.discard(websocket)
