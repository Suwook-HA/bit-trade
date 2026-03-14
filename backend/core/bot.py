import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass, field, asdict

from core.upbit_client import (
    get_candles_df, get_ticker, place_order, get_balance,
    get_tick_aggregator, SCALPING_INTERVALS, INTERVAL_SECONDS_MAP,
)
from core.strategies import get_signal
from core.risk_engine import get_risk_engine, SCALPING_RISK_CONFIG, RiskEngine
from db.database import get_db, get_persistent_db, upsert_position, write_audit_log

logger = logging.getLogger(__name__)

SUPPORTED_MARKETS = {"KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP"}
WARMUP_CANDLE_COUNT = 180
WARMUP_MIN_WINDOW = 35


@dataclass
class BotConfig:
    market: str = SCALPING_DEFAULTS["market"]
    interval: str = SCALPING_DEFAULTS["interval"]
    strategy: str = SCALPING_DEFAULTS["strategy"]
    params: dict = field(default_factory=lambda: get_strategy_params(SCALPING_DEFAULTS["strategy"]))
    mode: str = SCALPING_DEFAULTS["mode"]          # 'paper' | 'live'
    budget: float = SCALPING_DEFAULTS["budget"]      # KRW
    order_ratio: float = SCALPING_DEFAULTS["order_ratio"]     # 예산의 몇 % 투자
    stop_loss: float = SCALPING_DEFAULTS["stop_loss"]      # 손절 3%
    take_profit: float = SCALPING_DEFAULTS["take_profit"]    # 익절 5%
    auto_rebalance: bool = SCALPING_DEFAULTS["auto_rebalance"]
    rebalance_interval_candles: int = SCALPING_DEFAULTS["rebalance_interval_candles"]
    rebalance_threshold: float = 0.20
    execution_interval_seconds: int = SCALPING_DEFAULTS["execution_interval_seconds"]  # 0 = 캔들 타임프레임과 동일
    fee_rate: float = SCALPING_DEFAULTS["fee_rate"]             # 업비트 수수료 0.05%
    slippage_rate: float = SCALPING_DEFAULTS["slippage_rate"]        # 슬리피지 0.02%
    trailing_stop: bool = SCALPING_DEFAULTS["trailing_stop"]
    trailing_stop_pct: float = SCALPING_DEFAULTS["trailing_stop_pct"]


@dataclass
class BotState:
    running: bool = False
    position: str = "none"       # 'none' | 'long'
    entry_price: float = 0.0
    entry_volume: float = 0.0
    paper_krw: float = SCALPING_DEFAULTS["budget"]
    paper_asset: float = 0.0     # BTC/ETH/SOL/XRP 등 asset 잔고 (마켓 무관)
    total_trades: int = 0
    total_pnl: float = 0.0
    last_signal: str = "hold"
    last_signal_reason: str = ""
    last_check: str = ""
    rebalance_count: int = 0
    last_rebalanced: str = ""
    candle_counter: int = 0
    peak_price: float = 0.0
    last_price: float = 0.0     # 최근 가격 캐시 (get_bot_status 논블로킹용)
    consecutive_losses: int = 0  # RiskEngine 연동용


# ── 멀티마켓 전역 Dict ───────────────────────────────────────────
_bot_configs: Dict[str, BotConfig] = {}   # key: market
_bot_states:  Dict[str, BotState]  = {}
_bot_tasks:   Dict[str, asyncio.Task] = {}
_bot_risk_engines: Dict[str, RiskEngine] = {}  # 봇별 독립 RiskEngine


def _validate_order_ratio(order_ratio: float) -> Optional[str]:
    if not 0 < order_ratio <= 1:
        return "order_ratio must be between 0 and 1"

    max_weight = get_risk_engine().config.max_position_weight
    if order_ratio > max_weight:
        return (
            f"order_ratio {order_ratio:.2f} exceeds risk max_position_weight "
            f"{max_weight:.2f}; lower the order ratio to {max_weight:.2f} or less"
        )

    return None


def _get_signal_df(df):
    """Use only closed candles when computing live signals."""
    if df is None or df.empty:
        return df
    if len(df) < 2:
        return df.iloc[0:0].copy()
    return df.iloc[:-1].copy()


def _get_risk_context(config: BotConfig, state: BotState, price: float) -> tuple[float, float]:
    if config.mode == "live":
        currency = config.market.split("-")[1]
        krw_balance = get_balance("KRW")
        asset_balance = get_balance(currency)
        total_portfolio = krw_balance + asset_balance * price
        invest_krw = min(krw_balance * config.order_ratio, config.budget * config.order_ratio)
        return total_portfolio, invest_krw

    total_portfolio = state.paper_krw + state.paper_asset * price
    invest_krw = min(state.paper_krw * config.order_ratio, config.budget * config.order_ratio)
    return total_portfolio, invest_krw


def _count_active_positions(mode: str) -> int:
    return sum(
        1
        for market, state in _bot_states.items()
        if state.position == "long" and _bot_configs.get(market) and _bot_configs[market].mode == mode
    )


def _warmup_paper_state(config: BotConfig, state: BotState, df) -> bool:
    """
    시작 직전 최근 캔들로 현재 열려 있어야 하는 포지션만 복원한다.
    과거 실현손익은 반영하지 않고, 마지막 열린 포지션만 seed 한다.
    """
    signal_df = _get_signal_df(df)
    if signal_df is None or len(signal_df) <= WARMUP_MIN_WINDOW:
        return False

    sim_krw = config.budget
    sim_asset = 0.0
    position = "none"
    entry_price = 0.0
    entry_volume = 0.0
    peak_price = 0.0

    for idx in range(WARMUP_MIN_WINDOW, len(signal_df)):
        window_df = signal_df.iloc[:idx + 1]
        signal = get_signal(config.strategy, window_df, config.params)
        price = float(signal.price)
        signal_action = signal.action

        if position == "long" and price > peak_price:
            peak_price = price

        if position == "long" and entry_price > 0:
            change = (price - entry_price) / entry_price
            if change <= -config.stop_loss:
                signal_action = "sell"
            elif change >= config.take_profit:
                signal_action = "sell"
            elif config.trailing_stop and peak_price > 0:
                drop = (price - peak_price) / peak_price
                if drop <= -config.trailing_stop_pct:
                    signal_action = "sell"

        if signal_action == "buy" and position == "none":
            invest_krw = min(sim_krw * config.order_ratio, config.budget * config.order_ratio)
            if invest_krw < 5000:
                continue

            buy_price = price * (1 + config.slippage_rate)
            fee = invest_krw * config.fee_rate
            entry_volume = (invest_krw - fee) / buy_price
            sim_krw -= invest_krw
            sim_asset = entry_volume
            entry_price = buy_price
            peak_price = buy_price
            position = "long"

        elif signal_action == "sell" and position == "long":
            # 과거 실현손익은 버리고, flat 상태만 복원한다.
            sim_krw = config.budget
            sim_asset = 0.0
            entry_price = 0.0
            entry_volume = 0.0
            peak_price = 0.0
            position = "none"

    if position != "long":
        return False

    state.paper_krw = sim_krw
    state.paper_asset = sim_asset
    state.position = position
    state.entry_price = entry_price
    state.entry_volume = entry_volume
    state.peak_price = peak_price
    state.last_signal = "hold"
    state.last_signal_reason = (
        f"Warm-up seeded open {config.strategy} position from recent closed candles"
    )
    return True


def get_bot_status(market: Optional[str] = None) -> dict:
    """
    market=None → 모든 마켓 상태 dict 반환
    market 지정  → 해당 마켓 단일 상태 반환
    """
    if market:
        targets = [market] if market in _bot_states else []
    else:
        targets = list(_bot_states.keys())

    def _state_dict(m: str) -> dict:
        state = _bot_states[m]
        config = _bot_configs.get(m)
        pnl_pct = 0.0
        if state.position == "long" and state.entry_price > 0:
            current_price = state.last_price if state.last_price > 0 else state.entry_price
            pnl_pct = (current_price - state.entry_price) / state.entry_price * 100
        return {
            "running": state.running,
            "market": m,
            "position": state.position,
            "entry_price": state.entry_price,
            "entry_volume": state.entry_volume,
            "paper_krw": state.paper_krw,
            "paper_asset": state.paper_asset,
            "paper_btc": state.paper_asset,  # 하위 호환 alias
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
            "risk": _bot_risk_engines.get(m, get_risk_engine()).get_status(config.mode if config else "paper"),
        }

    if market:
        return _state_dict(market) if targets else {"error": f"Bot for {market} not found"}

    # 단일 봇만 있으면 기존 포맷(단일 dict) 반환 (하위 호환)
    if len(targets) == 1:
        return _state_dict(targets[0])

    return {m: _state_dict(m) for m in targets}


async def _record_trade(
    mode: str, market: str, side: str, price: float, volume: float,
    strategy: str, pnl: float = 0, status: str = "filled"
):
    """trades + orders 테이블에 기록."""
    db = await get_persistent_db()
    await db.execute(
        "INSERT INTO trades (mode, market, side, price, volume, strategy, pnl) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mode, market, side, price, volume, strategy, pnl)
    )
    await db.execute(
        """INSERT INTO orders
           (market, mode, side, status, price, volume, filled_price, filled_volume, strategy)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (market, mode, side, status, price, volume, price, volume, strategy)
    )
    await db.commit()


async def _paper_buy(config: BotConfig, state: BotState, price: float) -> bool:
    invest_krw = min(state.paper_krw * config.order_ratio, config.budget * config.order_ratio)
    if invest_krw < 5000:
        return False

    buy_price = price * (1 + config.slippage_rate)
    fee = invest_krw * config.fee_rate
    volume = (invest_krw - fee) / buy_price

    state.paper_krw -= invest_krw
    state.paper_asset += volume
    state.entry_price = buy_price
    state.entry_volume = volume
    state.peak_price = buy_price
    state.position = "long"
    state.total_trades += 1

    logger.info(
        "Paper BUY [%s]: price=%.0f, volume=%.6f, invest=%.0f KRW",
        config.market, buy_price, volume, invest_krw
    )
    await _record_trade("paper", config.market, "buy", buy_price, volume, config.strategy)
    return True


async def _paper_sell(config: BotConfig, state: BotState, price: float) -> Optional[float]:
    """매도 후 pnl 반환. 실패 시 None."""
    if state.paper_asset <= 0:
        return None

    volume = state.paper_asset
    sell_price = price * (1 - config.slippage_rate)
    krw_return = volume * sell_price
    fee = krw_return * config.fee_rate
    krw_return -= fee
    pnl = krw_return - (state.entry_volume * state.entry_price)

    state.paper_krw += krw_return
    state.paper_asset = 0.0
    state.peak_price = 0.0
    state.total_pnl += pnl
    state.position = "none"

    pnl_pct = pnl / (state.entry_volume * state.entry_price) * 100 if state.entry_volume * state.entry_price > 0 else 0
    logger.info(
        "Paper SELL [%s]: price=%.0f, pnl=%.0f KRW (%.2f%%)",
        config.market, sell_price, pnl, pnl_pct
    )
    await _record_trade("paper", config.market, "sell", sell_price, volume, config.strategy, pnl)
    return pnl


async def _live_buy(config: BotConfig, state: BotState, price: float) -> bool:
    krw_balance = get_balance("KRW")
    invest_krw = min(krw_balance * config.order_ratio, config.budget * config.order_ratio)
    if invest_krw < 5000:
        return False

    result = place_order("buy", config.market, volume=invest_krw)
    if "error" in result:
        logger.error("Live BUY failed [%s]: %s", config.market, result["error"])
        return False

    buy_price = price * (1 + config.slippage_rate)
    fee = invest_krw * config.fee_rate
    volume = (invest_krw - fee) / buy_price

    state.entry_price = buy_price
    state.entry_volume = volume
    state.peak_price = buy_price
    state.position = "long"
    state.total_trades += 1

    logger.info("Live BUY [%s]: price=%.0f, volume=%.6f", config.market, buy_price, volume)
    await _record_trade("live", config.market, "buy", buy_price, volume, config.strategy)
    return True


async def _live_sell(config: BotConfig, state: BotState, price: float) -> Optional[float]:
    """Live 매도. 성공 시 pnl 반환, 실패 시 None."""
    currency = config.market.split("-")[1]  # "KRW-ETH" → "ETH"
    asset_balance = get_balance(currency)
    if asset_balance < 0.0001:
        return None

    result = place_order("sell", config.market, volume=asset_balance)
    if "error" in result:
        logger.error("Live SELL failed [%s]: %s", config.market, result["error"])
        return None

    sell_price = price * (1 - config.slippage_rate)
    krw_return = asset_balance * sell_price
    fee = krw_return * config.fee_rate
    krw_return -= fee
    pnl = krw_return - (state.entry_volume * state.entry_price)

    state.total_pnl += pnl
    state.position = "none"

    logger.info("Live SELL [%s]: price=%.0f, pnl=%.0f KRW", config.market, sell_price, pnl)
    await _record_trade("live", config.market, "sell", sell_price, asset_balance, config.strategy, pnl)
    return pnl


async def _rebalance_check(config: BotConfig, state: BotState):
    """주기적 그리드 서치로 최적 전략 재평가 및 자동 전환."""
    if state.position == "long":
        return

    try:
        from core.recommender import PARAM_GRID, score_result
        from core.backtest import download_history, run_backtest_on_df
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_running_loop()

        with ThreadPoolExecutor(max_workers=6) as executor:
            df = await loop.run_in_executor(
                executor, lambda: download_history(config.market, config.interval, days=3)
            )
            if df is None or df.empty or len(df) < 60:
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
                return

            best_idx, best_score = max(valid_scores, key=lambda x: x[1])
            best_strategy, best_params = PARAM_GRID[best_idx]
            current_score = await loop.run_in_executor(
                executor, score_combo, config.strategy, config.params
            )

        should_switch = False
        if current_score <= 0 and best_score > 0:
            should_switch = True
        elif current_score > 0 and best_score > current_score * (1 + config.rebalance_threshold):
            should_switch = True

        if should_switch and (best_strategy != config.strategy or best_params != config.params):
            old_strategy = config.strategy
            config.strategy = best_strategy
            config.params = best_params
            state.last_rebalanced = datetime.now().strftime("%H:%M:%S")
            state.rebalance_count += 1
            logger.info(
                "Rebalance [%s]: %s → %s", config.market, old_strategy, best_strategy
            )
            db = await get_persistent_db()
            await write_audit_log(
                db, "strategy_switch",
                f"{old_strategy} → {best_strategy}",
                market=config.market, mode=config.mode,
                details={"old": old_strategy, "new": best_strategy, "params": best_params}
            )

    except Exception as e:
        logger.warning("Rebalance check failed [%s]: %s", config.market, e)



# ─── 공통 헬퍼: 신호 액션 결정 (stop/take-profit/trailing 적용) ──
def _compute_signal_action(config: BotConfig, state: BotState, signal, price: float) -> str:
    if state.position == "long" and state.entry_price > 0:
        change = (price - state.entry_price) / state.entry_price
        if change <= -config.stop_loss:
            state.last_signal_reason = f"Stop-loss triggered ({change*100:.2f}%)"
            return "sell"
        if change >= config.take_profit:
            state.last_signal_reason = f"Take-profit triggered ({change*100:.2f}%)"
            return "sell"
        if config.trailing_stop and state.peak_price > 0:
            drop = (price - state.peak_price) / state.peak_price
            if drop <= -config.trailing_stop_pct:
                state.last_signal_reason = f"Trailing stop ({drop*100:.2f}% from peak)"
                return "sell"
    return signal.action


# ─── 공통 헬퍼: 신호 실행 (매수/매도/리스크 차단/포지션 저장) ────
async def _execute_signal(
    config: BotConfig, state: BotState, risk: RiskEngine,
    signal_action: str, price: float,
    volume_filter: bool = True,
) -> None:
    if signal_action == "buy" and state.position == "none":
        if config.mode == "paper":
            available_krw = state.paper_krw
            asset_value = state.paper_asset * price
            invest_krw = available_krw * config.order_ratio
        else:
            available_krw = get_balance("KRW")
            asset_currency = config.market.split("-")[1]
            asset_value = get_balance(asset_currency) * price
            invest_krw = min(available_krw * config.order_ratio, config.budget * config.order_ratio)

        total_portfolio = available_krw + asset_value
        active_pos = sum(1 for s in _bot_states.values() if s.position == "long")
        allowed, reason = risk.check_order_allowed(
            mode=config.mode, side="buy", market=config.market,
            invest_krw=invest_krw, total_portfolio_krw=total_portfolio,
            active_position_count=active_pos,
        )
        if not allowed:
            db = await get_persistent_db()
            await write_audit_log(db, "risk_blocked", reason, market=config.market, mode=config.mode)
            state.last_signal_reason = f"Risk blocked: {reason}"
            logger.info("Buy blocked [%s]: %s", config.market, reason)
        else:
            if config.mode == "paper":
                await _paper_buy(config, state, price)
            else:
                await _live_buy(config, state, price)

    elif signal_action == "sell" and state.position == "long":
        pnl = await _paper_sell(config, state, price) if config.mode == "paper" \
              else await _live_sell(config, state, price)
        if pnl is not None:
            risk.on_trade_result(config.mode, pnl)
            risk_state = risk.get_state(config.mode)
            if risk_state:
                state.consecutive_losses = risk_state.consecutive_losses
            risk_status = risk.get_status(config.mode)
            if risk_status.get("circuit_breaker_triggered"):
                db = await get_persistent_db()
                await write_audit_log(
                    db, "circuit_breaker", "Circuit breaker triggered, stopping bot",
                    market=config.market, mode=config.mode,
                    details={"pnl": pnl, "daily_pnl": risk_status["daily_pnl"]},
                )
                logger.warning("Circuit breaker triggered [%s]", config.market)
                state.running = False

    if config.mode == "paper":
        db = await get_persistent_db()
        await upsert_position(
            db, "paper", config.market,
            krw_balance=state.paper_krw, asset_balance=state.paper_asset,
            entry_price=state.entry_price, position=state.position,
            peak_price=state.peak_price,
        )
        await db.commit()


# ─── 이벤트 주도 스캘핑 루프 (서브-분봉 전용) ──────────────────
async def _bot_loop_scalping(config: BotConfig, state: BotState):
    """5s/10s/15s/30s 인터벌 전용. TickAggregator 완성 캔들 도착 시 신호 평가."""
    interval_s = INTERVAL_SECONDS_MAP.get(config.interval, 30)
    aggregator = get_tick_aggregator(interval_s)

    # 1m REST 캔들로 warm-up (동기 HTTP 호출 → run_in_executor로 이벤트 루프 블로킹 방지)
    loop = asyncio.get_running_loop()
    seed_df = await loop.run_in_executor(
        None, lambda: get_candles_df(config.market, "1m", count=100)
    )
    if not seed_df.empty:
        aggregator.seed_from_df(config.market, seed_df)
        logger.info("Scalping warm-up [%s]: seeded %d candles", config.market, len(seed_df))

    risk = _bot_risk_engines.get(config.market, get_risk_engine())

    while state.running:
        try:
            candle = await asyncio.wait_for(
                aggregator.get_next_candle(config.market),
                timeout=interval_s * 5,
            )

            df = aggregator.get_history_df(config.market)
            if len(df) < 10:
                continue

            price = float(candle["close"])
            state.last_price = price
            if state.position == "long" and price > state.peak_price:
                state.peak_price = price

            signal = get_signal(config.strategy, df, config.params, volume_filter=False)
            state.last_signal = signal.action
            state.last_signal_reason = signal.reason
            state.last_check = datetime.now().strftime("%H:%M:%S")

            signal_action = _compute_signal_action(config, state, signal, price)
            await _execute_signal(config, state, risk, signal_action, price, volume_filter=False)

            if not state.running:
                break

            if config.auto_rebalance:
                state.candle_counter += 1
                if state.candle_counter >= config.rebalance_interval_candles:
                    state.candle_counter = 0
                    asyncio.create_task(_rebalance_check(config, state))

        except asyncio.TimeoutError:
            logger.warning("Scalping timeout [%s]: no ticks for %ds", config.market, interval_s * 5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Scalping bot error [%s]: %s", config.market, e, exc_info=True)
            state.last_signal_reason = f"Error: {str(e)}"

    state.running = False
    logger.info("Scalping bot stopped [%s]", config.market)


# ─── 기존 폴링 루프 (1m 이상) ───────────────────────────────────
async def _bot_loop(config: BotConfig, state: BotState):
    state.running = True

    if config.mode == "paper":
        state.paper_krw = config.budget
        state.paper_asset = 0.0

    if config.interval in SCALPING_INTERVALS:
        await _bot_loop_scalping(config, state)
        return

    candle_seconds = INTERVAL_SECONDS_MAP.get(config.interval, 60)
    interval_seconds = (
        config.execution_interval_seconds
        if config.execution_interval_seconds > 0
        else candle_seconds
    )

    logger.info(
        "Bot started: market=%s interval=%s strategy=%s mode=%s",
        config.market, config.interval, config.strategy, config.mode,
    )

    risk = _bot_risk_engines.get(config.market, get_risk_engine())

    while state.running:
        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                None, lambda: get_candles_df(config.market, config.interval, count=100)
            )
            signal_df = _get_signal_df(df)
            if signal_df is None or signal_df.empty:
                await asyncio.sleep(interval_seconds)
                continue

            signal = get_signal(config.strategy, signal_df, config.params)
            state.last_signal = signal.action
            state.last_signal_reason = signal.reason
            state.last_check = datetime.now().strftime("%H:%M:%S")

            price = signal.price
            state.last_price = price

            if state.position == "long" and price > state.peak_price:
                state.peak_price = price

            signal_action = _compute_signal_action(config, state, signal, price)
            await _execute_signal(config, state, risk, signal_action, price)

            if not state.running:
                break

            if config.auto_rebalance:
                state.candle_counter += 1
                if state.candle_counter >= config.rebalance_interval_candles:
                    state.candle_counter = 0
                    asyncio.create_task(_rebalance_check(config, state))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Bot loop error [%s]: %s", config.market, e, exc_info=True)
            state.last_signal_reason = f"Error: {str(e)}"

        await asyncio.sleep(interval_seconds)

    state.running = False
    logger.info("Bot stopped [%s]", config.market)


async def start_bot(config_dict: dict) -> dict:
    market = config_dict.get("market", SCALPING_DEFAULTS["market"])

    if market not in SUPPORTED_MARKETS:
        return {"error": f"Unsupported market: {market}. Supported: {sorted(SUPPORTED_MARKETS)}"}

    if market in _bot_states and _bot_states[market].running:
        return {"error": f"Bot for {market} is already running"}

    merged_config = {
        "market": SCALPING_DEFAULTS["market"],
        "interval": SCALPING_DEFAULTS["interval"],
        "strategy": SCALPING_DEFAULTS["strategy"],
        "params": get_strategy_params(SCALPING_DEFAULTS["strategy"]),
        "mode": SCALPING_DEFAULTS["mode"],
        "budget": SCALPING_DEFAULTS["budget"],
        "order_ratio": SCALPING_DEFAULTS["order_ratio"],
        "stop_loss": SCALPING_DEFAULTS["stop_loss"],
        "take_profit": SCALPING_DEFAULTS["take_profit"],
        "auto_rebalance": SCALPING_DEFAULTS["auto_rebalance"],
        "rebalance_interval_candles": SCALPING_DEFAULTS["rebalance_interval_candles"],
        "execution_interval_seconds": SCALPING_DEFAULTS["execution_interval_seconds"],
        "fee_rate": SCALPING_DEFAULTS["fee_rate"],
        "slippage_rate": SCALPING_DEFAULTS["slippage_rate"],
        "trailing_stop": SCALPING_DEFAULTS["trailing_stop"],
        "trailing_stop_pct": SCALPING_DEFAULTS["trailing_stop_pct"],
        **config_dict,
    }
    if not merged_config.get("params"):
        merged_config["params"] = get_strategy_params(merged_config["strategy"])
    config = BotConfig(**{
        k: v for k, v in merged_config.items()
        if k in BotConfig.__dataclass_fields__
    })

    validation_error = _validate_order_ratio(config.order_ratio)
    if validation_error:
        return {"error": validation_error}

    state = BotState()
    if config.mode == "paper":
        state.paper_krw = config.budget
        warmup_df = get_candles_df(config.market, config.interval, count=WARMUP_CANDLE_COUNT)
        seeded = _warmup_paper_state(config, state, warmup_df)
    else:
        seeded = False

    # RiskEngine 세션 초기화 — 스캘핑 인터벌이면 타이트한 프리셋 사용
    if config.interval in SCALPING_INTERVALS:
        _bot_risk_engines[market] = RiskEngine(SCALPING_RISK_CONFIG)

        # 스캘핑 봇 전용 Upbit 스트림 예약 (브라우저 연결 없어도 tick 수신)
        from api.ws_handler import subscribe_for_bot
        await subscribe_for_bot(market)
    else:
        _bot_risk_engines[market] = get_risk_engine()

    _bot_risk_engines[market].initialize_session(config.mode, config.budget)

    _bot_configs[market] = config
    _bot_states[market] = state
    _bot_tasks[market] = asyncio.create_task(_bot_loop(config, state))

    # 감사 로그
    db = await get_persistent_db()
    if seeded:
        await write_audit_log(
            db, "warmup_position_seeded",
            f"Seeded {config.strategy} position from recent candles",
            market=market, mode=config.mode,
            details={
                "entry_price": round(state.entry_price, 0),
                "entry_volume": state.entry_volume,
                "paper_krw": round(state.paper_krw, 0),
            }
        )
    await write_audit_log(
        db, "bot_start",
        f"Bot started: {config.strategy} / {config.mode}",
        market=market, mode=config.mode,
        details=asdict(config)
    )

    logger.info("Bot started for market=%s mode=%s", market, config.mode)
    return {"status": "started", "market": market, "config": asdict(config)}


async def stop_bot(market: Optional[str] = None) -> dict:
    """market=None → 모든 봇 중지, market 지정 → 해당 마켓만 중지."""
    targets = [market] if market else list(_bot_states.keys())
    stopped = []

    for m in targets:
        state = _bot_states.get(m)
        if not state or not state.running:
            continue

        state.running = False
        task = _bot_tasks.get(m)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _bot_tasks.pop(m, None)

        stopped.append(m)

        # 스캘핑 봇이었으면 Upbit 스트림 예약 해제
        config = _bot_configs.get(m)
        if config and config.interval in SCALPING_INTERVALS:
            from api.ws_handler import unsubscribe_for_bot
            await unsubscribe_for_bot(m)

        # 감사 로그
        db = await get_persistent_db()
        await write_audit_log(
            db, "bot_stop", f"Bot stopped for {m}",
            market=m, mode=config.mode if config else None
        )

    if not stopped:
        return {"error": "No running bot found"}
    return {"status": "stopped", "markets": stopped}
