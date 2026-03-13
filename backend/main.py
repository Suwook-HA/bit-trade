import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db, close_persistent_db
from api.routes import router
from api.ws_handler import handle_ticker_ws, handle_candle_ws, start_upbit_stream

# 로깅 설정 (앱 시작 시 최초 1회)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting BTC Trading App...")
    await init_db()
    asyncio.create_task(start_upbit_stream(["KRW-BTC", "KRW-ETH"]))
    yield
    # 셧다운 시 영속 DB 커넥션 정리
    await close_persistent_db()
    logger.info("BTC Trading App stopped")


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
