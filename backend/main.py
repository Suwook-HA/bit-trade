import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from api.routes import router
from api.ws_handler import handle_ticker_ws, handle_candle_ws, start_upbit_stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Start Upbit real-time stream
    asyncio.create_task(start_upbit_stream(["KRW-BTC", "KRW-ETH"]))
    yield


app = FastAPI(title="Bitcoin Trading App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.websocket("/ws/ticker")
async def ws_ticker(websocket: WebSocket):
    await handle_ticker_ws(websocket)


@app.websocket("/ws/candle")
async def ws_candle(websocket: WebSocket):
    await handle_candle_ws(websocket)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Bitcoin Trading API"}
