from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from core.upbit_client import get_candles, get_candles_df, get_ticker
from core.strategies import compute_indicators_for_chart
from core.bot import start_bot, stop_bot, get_bot_status
from core.backtest import run_backtest
from db.database import get_db

router = APIRouter(prefix="/api")


# --- Candles ---

@router.get("/candles/{market}")
async def candles(market: str, interval: str = "1m", count: int = 200):
    data = get_candles(market, interval, min(count, 500))
    return {"market": market, "interval": interval, "candles": data}


@router.get("/indicators/{market}")
async def indicators(market: str, interval: str = "1m", count: int = 200):
    df = get_candles_df(market, interval, min(count, 500))
    result = compute_indicators_for_chart(df)
    return result


# --- Ticker ---

@router.get("/ticker/{market}")
async def ticker(market: str):
    return get_ticker(market)


# --- Bot ---

class BotStartRequest(BaseModel):
    market: str = "KRW-BTC"
    interval: str = "1m"
    strategy: str = "rsi"
    params: dict = {}
    mode: str = "paper"
    budget: float = 1000000
    order_ratio: float = 0.5
    stop_loss: float = 0.03
    take_profit: float = 0.05
    auto_rebalance: bool = False
    rebalance_interval_candles: int = 30


@router.post("/bot/start")
async def bot_start(req: BotStartRequest):
    return await start_bot(req.model_dump())


@router.post("/bot/stop")
async def bot_stop():
    return await stop_bot()


@router.get("/bot/status")
async def bot_status():
    return get_bot_status()


# --- Backtest ---

class BacktestRequest(BaseModel):
    market: str = "KRW-BTC"
    interval: str = "1m"
    strategy: str = "rsi"
    params: dict = {}
    days: int = 7
    initial_budget: float = 10000000
    order_ratio: float = 0.5
    stop_loss: float = 0.03
    take_profit: float = 0.05


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: run_backtest(
        market=req.market,
        interval=req.interval,
        strategy=req.strategy,
        params=req.params,
        days=req.days,
        initial_budget=req.initial_budget,
        order_ratio=req.order_ratio,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    ))
    return result


# --- Strategy Recommend ---

class RecommendRequest(BaseModel):
    market: str = "KRW-BTC"
    interval: str = "1m"
    days: int = 7


@router.post("/strategy/recommend")
async def strategy_recommend(req: RecommendRequest):
    from core.recommender import run_grid_search
    return await run_grid_search(
        market=req.market,
        interval=req.interval,
        days=req.days,
    )


# --- Portfolio ---

@router.get("/portfolio")
async def portfolio():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT krw_balance, btc_balance, updated_at FROM paper_portfolio ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        paper = {"krw": row[0], "btc": row[1], "updated_at": row[2]} if row else {}

        cursor2 = await db.execute(
            "SELECT side, price, volume, pnl, created_at, strategy, mode FROM trades ORDER BY created_at DESC LIMIT 50"
        )
        rows = await cursor2.fetchall()
        trades = [
            {"side": r[0], "price": r[1], "volume": r[2], "pnl": r[3],
             "created_at": r[4], "strategy": r[5], "mode": r[6]}
            for r in rows
        ]
        return {"paper_portfolio": paper, "recent_trades": trades}
    finally:
        await db.close()
