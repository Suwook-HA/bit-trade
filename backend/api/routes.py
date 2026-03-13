from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional

from core.upbit_client import get_candles, get_candles_df, get_ticker
from core.strategies import compute_indicators_for_chart
from core.bot import start_bot, stop_bot, get_bot_status
from core.backtest import run_backtest
from core.auth import verify_api_key
from db.database import get_db

router = APIRouter(prefix="/api")


# ─── Candles ────────────────────────────────────────────────────

@router.get("/candles/{market}")
async def candles(market: str, interval: str = "1m", count: int = 200):
    data = get_candles(market, interval, min(count, 500))
    return {"market": market, "interval": interval, "candles": data}


@router.get("/indicators/{market}")
async def indicators(market: str, interval: str = "1m", count: int = 200):
    df = get_candles_df(market, interval, min(count, 500))
    result = compute_indicators_for_chart(df)
    return result


# ─── Ticker ─────────────────────────────────────────────────────

@router.get("/ticker/{market}")
async def ticker(market: str):
    return get_ticker(market)


# ─── Bot ─────────────────────────────────────────────────────────

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
    execution_interval_seconds: int = 0
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0002
    trailing_stop: bool = False
    trailing_stop_pct: float = 0.02
    auto_strategy: bool = False


@router.post("/bot/start", dependencies=[Depends(verify_api_key)])
async def bot_start(req: BotStartRequest):
    config = req.model_dump()
    if req.auto_strategy:
        from core.recommender import run_grid_search
        rec = await run_grid_search(
            market=req.market,
            interval=req.interval,
            days=7,
            top_n=1,
            order_ratio=req.order_ratio,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        if rec and not rec.get("error") and rec.get("recommendations"):
            best = rec["recommendations"][0]
            config["strategy"] = best["strategy"]
            config["params"] = best["params"]
    return await start_bot(config)


@router.post("/bot/stop", dependencies=[Depends(verify_api_key)])
async def bot_stop(
    market: Optional[str] = Query(None, description="마켓 코드 (예: KRW-BTC). 생략 시 전체 중지")
):
    return await stop_bot(market=market)


@router.get("/bot/status")
async def bot_status(
    market: Optional[str] = Query(None, description="마켓 코드. 생략 시 전체 상태 반환")
):
    return get_bot_status(market=market)


# ─── Backtest ────────────────────────────────────────────────────

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
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0002
    trailing_stop: bool = False
    trailing_stop_pct: float = 0.02


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
        fee_rate=req.fee_rate,
        slippage_rate=req.slippage_rate,
        trailing_stop=req.trailing_stop,
        trailing_stop_pct=req.trailing_stop_pct,
    ))
    return result


# ─── Strategy Recommend ──────────────────────────────────────────

class RecommendRequest(BaseModel):
    market: str = "KRW-BTC"
    interval: str = "1m"
    days: int = 7
    split_ratio: float = 0.7


@router.post("/strategy/recommend")
async def strategy_recommend(req: RecommendRequest):
    from core.recommender import run_grid_search
    return await run_grid_search(
        market=req.market,
        interval=req.interval,
        days=req.days,
        split_ratio=req.split_ratio,
    )


# ─── Portfolio ───────────────────────────────────────────────────

@router.get("/portfolio")
async def portfolio(
    market: Optional[str] = Query(None, description="마켓 코드. 생략 시 KRW-BTC"),
    mode: Optional[str] = Query(None, description="paper | live"),
):
    target_market = market or "KRW-BTC"
    target_mode = mode or "paper"
    db = await get_db()
    try:
        # positions 테이블 우선 조회 (멀티마켓 지원)
        cursor = await db.execute(
            "SELECT krw_balance, asset_balance, entry_price, position, updated_at "
            "FROM positions WHERE mode=? AND market=? LIMIT 1",
            (target_mode, target_market),
        )
        pos_row = await cursor.fetchone()

        if pos_row:
            paper = {
                "krw": pos_row[0],
                "asset": pos_row[1],
                "btc": pos_row[1],   # 하위 호환 alias
                "entry_price": pos_row[2],
                "position": pos_row[3],
                "updated_at": pos_row[4],
                "market": target_market,
            }
        else:
            # paper_portfolio 폴백 (BTC 전용 레거시)
            cursor2 = await db.execute(
                "SELECT krw_balance, btc_balance, updated_at FROM paper_portfolio ORDER BY id DESC LIMIT 1"
            )
            row = await cursor2.fetchone()
            paper = (
                {"krw": row[0], "btc": row[1], "asset": row[1], "updated_at": row[2]}
                if row else {}
            )

        # 최근 거래 내역
        cursor3 = await db.execute(
            "SELECT side, price, volume, pnl, created_at, strategy, mode FROM trades "
            "ORDER BY created_at DESC LIMIT 50"
        )
        rows = await cursor3.fetchall()
        trades = [
            {"side": r[0], "price": r[1], "volume": r[2], "pnl": r[3],
             "created_at": r[4], "strategy": r[5], "mode": r[6]}
            for r in rows
        ]

        # P&L 집계
        cursor4 = await db.execute(
            "SELECT pnl FROM trades WHERE side='sell' AND pnl IS NOT NULL"
        )
        pnl_rows = await cursor4.fetchall()
        pnl_values = [r[0] for r in pnl_rows if r[0] is not None]
        total_pnl = sum(pnl_values)
        win_count = sum(1 for p in pnl_values if p > 0)
        loss_count = sum(1 for p in pnl_values if p < 0)
        best_trade = max(pnl_values) if pnl_values else 0
        worst_trade = min(pnl_values) if pnl_values else 0
        pnl_summary = {
            "total_pnl": round(total_pnl),
            "trade_count": len(pnl_values),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate_pct": round(win_count / len(pnl_values) * 100, 1) if pnl_values else 0,
            "best_trade": round(best_trade),
            "worst_trade": round(worst_trade),
        }

        return {"paper_portfolio": paper, "recent_trades": trades, "pnl_summary": pnl_summary}
    finally:
        await db.close()


@router.get("/portfolio/all")
async def portfolio_all(
    mode: Optional[str] = Query(None, description="paper | live"),
):
    """모든 마켓 포지션 목록 반환"""
    target_mode = mode or "paper"
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT market, krw_balance, asset_balance, entry_price, position, peak_price, updated_at "
            "FROM positions WHERE mode=? ORDER BY market",
            (target_mode,),
        )
        rows = await cursor.fetchall()
        positions = [
            {
                "market": r[0],
                "krw": r[1],
                "asset": r[2],
                "btc": r[2],   # 하위 호환
                "entry_price": r[3],
                "position": r[4],
                "peak_price": r[5],
                "updated_at": r[6],
            }
            for r in rows
        ]
        total_krw = sum(p["krw"] for p in positions)
        return {
            "mode": target_mode,
            "positions": positions,
            "total_positions": len(positions),
            "total_krw_balance": round(total_krw),
        }
    finally:
        await db.close()


# ─── Risk Engine ─────────────────────────────────────────────────

@router.get("/risk/status")
async def risk_status(
    mode: Optional[str] = Query(None, description="paper | live. 생략 시 전체"),
):
    from core.risk_engine import get_risk_engine
    engine = get_risk_engine()
    if mode:
        return engine.get_status(mode)
    return engine.get_all_status()


@router.post("/risk/reset-circuit-breaker", dependencies=[Depends(verify_api_key)])
async def risk_reset_circuit_breaker(mode: str = Query("paper")):
    from core.risk_engine import get_risk_engine
    get_risk_engine().reset_circuit_breaker(mode)
    return {"ok": True, "message": f"Circuit breaker reset for mode={mode}"}


# ─── Audit Log ───────────────────────────────────────────────────

@router.get("/audit-log")
async def audit_log(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="bot_start | bot_stop | risk_blocked | circuit_breaker 등"),
    market: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
):
    """구조화 감사 로그 조회"""
    import json
    db = await get_db()
    try:
        conditions = []
        filter_params: list = []
        if event_type:
            conditions.append("event_type = ?")
            filter_params.append(event_type)
        if market:
            conditions.append("market = ?")
            filter_params.append(market)
        if mode:
            conditions.append("mode = ?")
            filter_params.append(mode)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cursor = await db.execute(
            f"SELECT id, event_type, market, mode, message, details, created_at "
            f"FROM audit_log {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            filter_params + [limit, offset],
        )
        rows = await cursor.fetchall()
        logs = [
            {
                "id": r[0],
                "event_type": r[1],
                "market": r[2],
                "mode": r[3],
                "message": r[4],
                "details": json.loads(r[5]) if r[5] else None,
                "created_at": r[6],
            }
            for r in rows
        ]

        cursor2 = await db.execute(
            f"SELECT COUNT(*) FROM audit_log {where}", filter_params
        )
        total = (await cursor2.fetchone())[0]

        return {"logs": logs, "total": total, "limit": limit, "offset": offset}
    finally:
        await db.close()


# ─── Orders ──────────────────────────────────────────────────────

@router.get("/orders")
async def orders(
    market: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="pending | filled | cancelled | failed"),
    mode: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """주문 목록 조회"""
    db = await get_db()
    try:
        conditions = []
        filter_params: list = []
        if market:
            conditions.append("market = ?")
            filter_params.append(market)
        if status:
            conditions.append("status = ?")
            filter_params.append(status)
        if mode:
            conditions.append("mode = ?")
            filter_params.append(mode)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cursor = await db.execute(
            f"SELECT id, market, mode, side, status, price, volume, "
            f"filled_price, filled_volume, strategy, exchange_order_id, "
            f"error_message, created_at, updated_at "
            f"FROM orders {where} ORDER BY created_at DESC LIMIT ?",
            filter_params + [limit],
        )
        rows = await cursor.fetchall()
        result = [
            {
                "id": r[0], "market": r[1], "mode": r[2], "side": r[3],
                "status": r[4], "price": r[5], "volume": r[6],
                "filled_price": r[7], "filled_volume": r[8],
                "strategy": r[9], "exchange_order_id": r[10],
                "error_message": r[11], "created_at": r[12], "updated_at": r[13],
            }
            for r in rows
        ]
        return {"orders": result, "total": len(result)}
    finally:
        await db.close()
