import asyncio
import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

from core.upbit_client import get_candles_df, get_ticker, place_order, get_balance
from core.strategies import get_signal
from db.database import get_db


@dataclass
class BotConfig:
    market: str = "KRW-BTC"
    interval: str = "1m"
    strategy: str = "rsi"
    params: dict = field(default_factory=lambda: {"period": 14, "oversold": 30, "overbought": 70})
    mode: str = "paper"          # 'paper' | 'live'
    budget: float = 1000000      # KRW
    order_ratio: float = 0.5     # 예산의 몇 % 투자
    stop_loss: float = 0.03      # 손절 3%
    take_profit: float = 0.05    # 익절 5%
    auto_rebalance: bool = False
    rebalance_interval_candles: int = 30
    rebalance_threshold: float = 0.20


@dataclass
class BotState:
    running: bool = False
    position: str = "none"      # 'none' | 'long'
    entry_price: float = 0.0
    entry_volume: float = 0.0
    paper_krw: float = 10000000
    paper_btc: float = 0.0
    total_trades: int = 0
    total_pnl: float = 0.0
    last_signal: str = "hold"
    last_signal_reason: str = ""
    last_check: str = ""
    rebalance_count: int = 0
    last_rebalanced: str = ""
    candle_counter: int = 0


# 전역 봇 상태
_bot_config: Optional[BotConfig] = None
_bot_state: BotState = BotState()
_bot_task: Optional[asyncio.Task] = None
_log_callbacks: list = []


def get_bot_status() -> dict:
    state = _bot_state
    config = _bot_config
    pnl_pct = 0.0

    if state.position == "long" and state.entry_price > 0:
        current_ticker = get_ticker(config.market if config else "KRW-BTC")
        current_price = current_ticker.get("price", state.entry_price)
        pnl_pct = (current_price - state.entry_price) / state.entry_price * 100

    return {
        "running": state.running,
        "position": state.position,
        "entry_price": state.entry_price,
        "entry_volume": state.entry_volume,
        "paper_krw": state.paper_krw,
        "paper_btc": state.paper_btc,
        "total_trades": state.total_trades,
        "total_pnl": state.total_pnl,
        "current_pnl_pct": round(pnl_pct, 2),
        "last_signal": state.last_signal,
        "last_signal_reason": state.last_signal_reason,
        "last_check": state.last_check,
        "rebalancing_enabled": config.auto_rebalance if config else False,
        "last_rebalanced": state.last_rebalanced,
        "rebalance_count": state.rebalance_count,
        "config": asdict(config) if config else None,
    }


async def _record_trade(mode: str, market: str, side: str, price: float, volume: float, strategy: str, pnl: float = 0):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO trades (mode, market, side, price, volume, strategy, pnl) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mode, market, side, price, volume, strategy, pnl)
        )
        await db.commit()
    finally:
        await db.close()


async def _paper_buy(config: BotConfig, price: float) -> bool:
    state = _bot_state
    invest_krw = state.paper_krw * config.order_ratio
    if invest_krw < 5000:
        return False

    volume = invest_krw / price
    state.paper_krw -= invest_krw
    state.paper_btc += volume
    state.entry_price = price
    state.entry_volume = volume
    state.position = "long"
    state.total_trades += 1

    await _record_trade("paper", config.market, "buy", price, volume, config.strategy)
    return True


async def _paper_sell(config: BotConfig, price: float) -> bool:
    state = _bot_state
    if state.paper_btc <= 0:
        return False

    volume = state.paper_btc
    krw_return = volume * price
    pnl = krw_return - (state.entry_volume * state.entry_price)

    state.paper_krw += krw_return
    state.paper_btc = 0
    state.total_pnl += pnl
    state.position = "none"

    await _record_trade("paper", config.market, "sell", price, volume, config.strategy, pnl)
    return True


async def _live_buy(config: BotConfig, price: float) -> bool:
    state = _bot_state
    krw_balance = get_balance("KRW")
    invest_krw = min(krw_balance * config.order_ratio, config.budget * config.order_ratio)

    if invest_krw < 5000:
        return False

    result = place_order("buy", config.market, volume=invest_krw)
    if "error" in result:
        return False

    volume = invest_krw / price
    state.entry_price = price
    state.entry_volume = volume
    state.position = "long"
    state.total_trades += 1

    await _record_trade("live", config.market, "buy", price, volume, config.strategy)
    return True


async def _live_sell(config: BotConfig, price: float) -> bool:
    state = _bot_state
    btc_balance = get_balance("BTC")
    if btc_balance < 0.0001:
        return False

    result = place_order("sell", config.market, volume=btc_balance)
    if "error" in result:
        return False

    pnl = btc_balance * price - state.entry_volume * state.entry_price
    state.total_pnl += pnl
    state.position = "none"
    state.paper_btc = 0

    await _record_trade("live", config.market, "sell", price, btc_balance, config.strategy, pnl)
    return True


async def _rebalance_check(config: BotConfig):
    """주기적 그리드 서치로 최적 전략 재평가 및 자동 전환"""
    state = _bot_state

    # 포지션 보유 중이면 전략 전환 금지
    if state.position == "long":
        return

    try:
        from core.recommender import PARAM_GRID, score_result
        from core.backtest import download_history, run_backtest_on_df
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=6)

        df = await loop.run_in_executor(
            executor, lambda: download_history(config.market, config.interval, days=3)
        )
        if df is None or df.empty or len(df) < 60:
            executor.shutdown(wait=False)
            return

        def score_combo(strategy, params):
            try:
                result = run_backtest_on_df(
                    df, strategy, params,
                    order_ratio=config.order_ratio,
                    stop_loss=config.stop_loss,
                    take_profit=config.take_profit,
                )
                return score_result(result.get("summary", {}))
            except Exception:
                return -999.0

        tasks = [
            loop.run_in_executor(executor, score_combo, s, p)
            for s, p in PARAM_GRID
        ]
        scores = await asyncio.gather(*tasks, return_exceptions=True)

        valid_scores = [
            (i, s) for i, s in enumerate(scores)
            if not isinstance(s, Exception) and s > -999
        ]
        if not valid_scores:
            executor.shutdown(wait=False)
            return

        best_idx, best_score = max(valid_scores, key=lambda x: x[1])
        best_strategy, best_params = PARAM_GRID[best_idx]

        # 현재 전략 스코어
        current_score = await loop.run_in_executor(
            executor, score_combo, config.strategy, config.params
        )

        executor.shutdown(wait=False)

        # 현재 전략보다 threshold 이상 높은 경우 전환
        should_switch = False
        if current_score <= 0 and best_score > 0:
            should_switch = True
        elif current_score > 0 and best_score > current_score * (1 + config.rebalance_threshold):
            should_switch = True

        if should_switch and (best_strategy != config.strategy or best_params != config.params):
            config.strategy = best_strategy
            config.params = best_params
            state.last_rebalanced = datetime.now().strftime("%H:%M:%S")
            state.rebalance_count += 1

    except Exception:
        pass  # 재조정 실패가 메인 루프에 영향 없도록


async def _bot_loop(config: BotConfig):
    state = _bot_state
    state.running = True

    # Initialize paper portfolio from DB
    if config.mode == "paper":
        db = await get_db()
        try:
            cursor = await db.execute("SELECT krw_balance, btc_balance FROM paper_portfolio ORDER BY id DESC LIMIT 1")
            row = await cursor.fetchone()
            if row:
                state.paper_krw = row[0]
                state.paper_btc = row[1]
        finally:
            await db.close()

    interval_seconds = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600
    }.get(config.interval, 60)

    while state.running:
        try:
            df = get_candles_df(config.market, config.interval, count=100)
            if df.empty:
                await asyncio.sleep(interval_seconds)
                continue

            signal = get_signal(config.strategy, df, config.params)
            state.last_signal = signal.action
            state.last_signal_reason = signal.reason
            state.last_check = datetime.now().strftime("%H:%M:%S")

            price = signal.price

            # Check stop-loss / take-profit first
            if state.position == "long" and state.entry_price > 0:
                change = (price - state.entry_price) / state.entry_price
                if change <= -config.stop_loss:
                    signal_action = "sell"
                    state.last_signal_reason = f"Stop-loss triggered ({change*100:.1f}%)"
                elif change >= config.take_profit:
                    signal_action = "sell"
                    state.last_signal_reason = f"Take-profit triggered ({change*100:.1f}%)"
                else:
                    signal_action = signal.action
            else:
                signal_action = signal.action

            if signal_action == "buy" and state.position == "none":
                if config.mode == "paper":
                    await _paper_buy(config, price)
                else:
                    await _live_buy(config, price)

            elif signal_action == "sell" and state.position == "long":
                if config.mode == "paper":
                    await _paper_sell(config, price)
                else:
                    await _live_sell(config, price)

            # Save paper portfolio state
            if config.mode == "paper":
                db = await get_db()
                try:
                    await db.execute(
                        "UPDATE paper_portfolio SET krw_balance=?, btc_balance=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                        (state.paper_krw, state.paper_btc)
                    )
                    await db.commit()
                finally:
                    await db.close()

            # 자동 재조정 체크
            if config.auto_rebalance:
                state.candle_counter += 1
                if state.candle_counter >= config.rebalance_interval_candles:
                    state.candle_counter = 0
                    asyncio.create_task(_rebalance_check(config))

        except asyncio.CancelledError:
            break
        except Exception as e:
            state.last_signal_reason = f"Error: {str(e)}"

        await asyncio.sleep(interval_seconds)

    state.running = False


async def start_bot(config_dict: dict) -> dict:
    global _bot_config, _bot_task, _bot_state

    if _bot_state.running:
        return {"error": "Bot is already running"}

    _bot_config = BotConfig(**{
        k: v for k, v in config_dict.items()
        if k in BotConfig.__dataclass_fields__
    })
    _bot_state = BotState()

    _bot_task = asyncio.create_task(_bot_loop(_bot_config))
    return {"status": "started", "config": asdict(_bot_config)}


async def stop_bot() -> dict:
    global _bot_task, _bot_state

    if not _bot_state.running:
        return {"error": "Bot is not running"}

    _bot_state.running = False
    if _bot_task:
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        _bot_task = None

    return {"status": "stopped"}
