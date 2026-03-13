"""
전략 자동 추천 & 그리드 서치 엔진
- In-sample / Out-of-sample 70/30 분리 백테스트 (과최적화 억제)
- 단타 최적화 파라미터 포함 54개 전략×파라미터 조합 병렬 백테스트
- 5개 지표 가중 조합 스코어 (수익률·샤프·소르티노·승률·MDD)
- 실시간 지표 기반 시장 상태 분석
- 5분 캐시
"""
import asyncio
import time
import itertools
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from core.backtest import download_history, run_backtest_on_df
from core.defaults import SCALPING_DEFAULTS, get_strategy_params
from core.strategies import get_signal

# ─── 파라미터 그리드 (단타 최적화 포함) ──────────────────────────
PARAM_GRID: list[tuple[str, dict]] = []
SCALPING_HINT_DEFAULTS = {
    strategy: get_strategy_params(strategy)
    for strategy in SCALPING_DEFAULTS["strategy_params"]
}

for _period, _oversold, _overbought in itertools.product([7, 9, 10, 14], [25, 30], [65, 70]):
    PARAM_GRID.append(("rsi", {"period": _period, "oversold": _oversold, "overbought": _overbought}))

_macd_combos = [(5, 13, 5), (8, 21, 7), (8, 21, 9), (12, 26, 7), (12, 26, 9)]
for _fast, _slow, _sig in _macd_combos:
    PARAM_GRID.append(("macd", {"fast": _fast, "slow": _slow, "signal": _sig}))

for _period, _std in itertools.product([10, 15, 20], [1.5, 2.0, 2.5]):
    PARAM_GRID.append(("bollinger", {"period": _period, "std_dev": _std}))

for _short, _long in itertools.product([3, 5, 7], [10, 15, 20]):
    if _short < _long:
        PARAM_GRID.append(("ma_cross", {"short_period": _short, "long_period": _long}))

# ─── 스캘핑 전용 파라미터 (서브-분봉 최적화) ─────────────────────
# RSI 초단기: period=5 (기존 그리드에 없는 조합만 추가)
for _oversold, _overbought in itertools.product([25, 30], [65, 70]):
    PARAM_GRID.append(("rsi", {"period": 5, "oversold": _oversold, "overbought": _overbought}))

# Bollinger 초단기: period=7 (빠른 밴드 수축/이탈 포착)
for _std in [1.5, 2.0]:
    PARAM_GRID.append(("bollinger", {"period": 7, "std_dev": _std}))

# VWAP 이탈 스캘핑: deviation 0.1~0.5%, period 10~20봉
for _dev, _period in itertools.product([0.001, 0.002, 0.003, 0.005], [10, 15, 20]):
    PARAM_GRID.append(("vwap", {"deviation": _dev, "period": _period}))

# ─── 캐시 ──────────────────────────────────────────────────────
_cache: dict = {}
_CACHE_TTL = 300


def _cache_key(
    market,
    interval,
    days,
    split_ratio,
    top_n,
    order_ratio,
    stop_loss,
    take_profit,
    trailing_stop,
    trailing_stop_pct,
):
    return (
        f"{market}:{interval}:{days}:{split_ratio}:{top_n}:"
        f"{order_ratio}:{stop_loss}:{take_profit}:{trailing_stop}:{trailing_stop_pct}"
    )


def _get_cached(key):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None


def _set_cached(key, data):
    _cache[key] = {"ts": time.time(), "data": data}


# ─── 스코어링 (5개 지표 가중 조합) ──────────────────────────────
def score_result(summary: dict) -> float:
    """수익률·샤프·소르티노·승률·MDD 가중 조합 점수."""
    trades = summary.get("total_trades", 0)
    if trades < 2:
        return -999.0
    ret = summary.get("total_return_pct", 0)
    sharpe = summary.get("sharpe_ratio", 0)
    sortino = summary.get("sortino_ratio", 0)
    win_rate = summary.get("win_rate_pct", 0)
    mdd = summary.get("mdd_pct", 0)
    mdd_penalty = mdd * 0.1  # MDD -10% → -1.0점
    return (
        ret * 0.30
        + sharpe * 0.25
        + sortino * 0.15
        + (win_rate / 5) * 0.15
        + mdd_penalty * 0.15
    )


# ─── 과최적화 감지 ────────────────────────────────────────────
def detect_overfit(
    train_summary: dict,
    test_summary: dict,
    degradation_threshold: float = 0.5,
) -> dict:
    """OOS 성과가 in-sample 대비 50% 이상 저하 → overfit 경고."""
    train_score = score_result(train_summary)
    test_score = score_result(test_summary)

    if train_score <= 0:
        return {
            "overfit": False,
            "train_score": round(train_score, 4),
            "test_score": round(test_score, 4),
            "degradation_pct": 0.0,
            "reason": "학습 구간 점수 음수 — 과최적화 판단 불가",
        }

    degradation = (train_score - test_score) / abs(train_score)
    overfit = degradation >= degradation_threshold
    return {
        "overfit": overfit,
        "train_score": round(train_score, 4),
        "test_score": round(test_score, 4),
        "degradation_pct": round(degradation * 100, 1),
        "reason": (
            f"OOS 점수({test_score:.2f})가 학습 점수({train_score:.2f}) 대비 "
            f"{degradation * 100:.1f}% 저하 — {'과최적화 의심' if overfit else '정상 범위'}"
        ),
    }


def _extract_metrics(summary: dict) -> dict:
    return {
        "total_return_pct": summary.get("total_return_pct", 0),
        "sharpe_ratio": summary.get("sharpe_ratio", 0),
        "sortino_ratio": summary.get("sortino_ratio", 0),
        "win_rate_pct": summary.get("win_rate_pct", 0),
        "profit_factor": summary.get("profit_factor", 0),
        "expectancy_krw": summary.get("expectancy_krw", 0),
        "total_trades": summary.get("total_trades", 0),
        "mdd_pct": summary.get("mdd_pct", 0),
    }


def _selection_score(rec: dict, market_hint: str) -> float:
    """스캘핑 추천용 정렬 점수. 현재 시장 적합도와 거래 빈도를 함께 반영한다."""
    train = rec["metrics"]["train"]
    oos = rec["metrics"]["oos"]
    live_action = rec.get("live_signal", {}).get("action", "hold")
    warmup_bonus = 4.0 if rec.get("warmup_position") else 0.0
    trades = oos.get("total_trades", 0)
    total_return = oos.get("total_return_pct", 0)
    win_rate = oos.get("win_rate_pct", 0)
    live_bonus = 3.0 if live_action == "buy" else (-0.5 if live_action == "sell" else 0.0)

    if trades <= 0:
        train_trades = train.get("total_trades", 0)
        train_return = train.get("total_return_pct", 0)
        market_bonus = 2.0 if rec["strategy"] == market_hint else 0.0
        train_trade_bonus = min(train_trades, 10) * 0.15
        return market_bonus + train_trade_bonus + train_return + rec["score"] + live_bonus + warmup_bonus

    market_bonus = 2.0 if rec["strategy"] == market_hint else 0.0
    profit_bonus = 1.5 if total_return > 0 else 0.0
    trade_bonus = min(trades, 10) * 0.2
    win_bonus = win_rate / 100

    return rec["oos_score"] + market_bonus + profit_bonus + trade_bonus + win_bonus + live_bonus + warmup_bonus


def _select_top_recommendations(scored: list[dict], market_info: dict, top_n: int) -> list[dict]:
    """거래 가능한 조합을 우선 추천하고, 없을 때만 제한적으로 fallback 한다."""
    market_hint = market_info.get("best_strategy_hint", "")
    tradable = [rec for rec in scored if rec["metrics"]["oos"].get("total_trades", 0) > 0]
    if tradable:
        pool = tradable
    else:
        warm_positions = [rec for rec in scored if rec.get("warmup_position")]
        if warm_positions:
            pool = warm_positions
        else:
            live_buy = [rec for rec in scored if rec.get("live_signal", {}).get("action") == "buy"]
            if live_buy:
                pool = live_buy
            else:
                hinted = [rec for rec in scored if rec["strategy"] == market_hint]
                pool = hinted if hinted else scored

    ranked = []
    for rec in pool:
        ranked_rec = dict(rec)
        ranked_rec["selection_score"] = round(_selection_score(rec, market_hint), 4)
        ranked.append(ranked_rec)

    ranked.sort(
        key=lambda rec: (
            rec["selection_score"],
            rec["metrics"]["oos"].get("total_trades", 0),
            rec["metrics"]["oos"].get("total_return_pct", 0),
            rec["score"],
        ),
        reverse=True,
    )
    return ranked[:top_n]


def _build_market_hint_fallback(scored: list[dict], market_info: dict) -> dict | None:
    """OOS 거래가 모두 0건일 때 현재 시장 상태에 맞는 스캘핑 프리셋을 반환한다."""
    strategy = market_info.get("best_strategy_hint")
    params = get_strategy_params(strategy) if strategy in SCALPING_HINT_DEFAULTS else None
    if not strategy or not params:
        return None

    for rec in scored:
        if rec["strategy"] == strategy and rec["params"] == params:
            fallback = dict(rec)
            fallback["selection_score"] = round(max(rec.get("selection_score", 0), 0.0), 4)
            fallback["fallback"] = True
            return fallback

    return {
        "strategy": strategy,
        "params": params,
        "score": 0.0,
        "oos_score": 0.0,
        "selection_score": 0.0,
        "fallback": True,
        "warmup_position": False,
        "overfit_info": {
            "overfit": False,
            "train_score": 0.0,
            "test_score": 0.0,
            "degradation_pct": 0.0,
            "reason": "시장 상태 기반 fallback",
        },
        "metrics": {
            "train": _extract_metrics({}),
            "oos": _extract_metrics({}),
        },
    }


def _has_warmup_position(
    market: str,
    interval: str,
    strategy: str,
    params: dict,
    order_ratio: float,
    stop_loss: float,
    take_profit: float,
    trailing_stop: bool,
    trailing_stop_pct: float,
    df_live: pd.DataFrame,
) -> bool:
    from core.bot import BotConfig, BotState, _warmup_paper_state

    config = BotConfig(
        market=market,
        interval=interval,
        strategy=strategy,
        params=params,
        mode="paper",
        budget=SCALPING_DEFAULTS["budget"],
        order_ratio=order_ratio,
        stop_loss=stop_loss,
        take_profit=take_profit,
        trailing_stop=trailing_stop,
        trailing_stop_pct=trailing_stop_pct,
    )
    state = BotState()
    state.paper_krw = config.budget
    return _warmup_paper_state(config, state, df_live)


# ─── 시장 상태 분석 ────────────────────────────────────────────
def analyze_market_condition(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 30:
        return {"condition": "unknown", "reason": "데이터 부족", "best_strategy_hint": "rsi"}

    try:
        close = df["close"].values.astype(float)
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.mean(gain[-14:]) if len(gain) >= 14 else np.mean(gain)
        avg_loss = np.mean(loss[-14:]) if len(loss) >= 14 else np.mean(loss)
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 50

        ma20 = np.mean(close[-20:]) if len(close) >= 20 else np.mean(close)
        if len(close) >= 25:
            ma20_prev = np.mean(close[-25:-5])
            slope = (ma20 - ma20_prev) / ma20_prev * 100
        else:
            slope = 0.0

        if len(close) >= 20:
            std = np.std(close[-20:])
            bb_mid = np.mean(close[-20:])
            bb_width_pct = (4 * std) / bb_mid * 100
        else:
            bb_width_pct = 2.0

        if len(close) >= 26:
            ema12 = _ema(close, 12)
            ema26 = _ema(close, 26)
            macd_val = ema12 - ema26
        else:
            macd_val = 0.0

        if bb_width_pct > 4.0:
            condition, hint = "volatile", "bollinger"
            reason = f"BB폭 {bb_width_pct:.1f}% - 고변동성, 볼린저밴드 전략 권장"
        elif abs(slope) > 0.5 and ((slope > 0 and macd_val > 0) or (slope < 0 and macd_val < 0)):
            condition = "trending_up" if slope > 0 else "trending_down"
            hint = "ma_cross" if abs(slope) > 1.0 else "macd"
            direction = "상승" if slope > 0 else "하락"
            reason = (
                f"MA20 기울기 {slope:+.2f}%, MACD {'양' if macd_val > 0 else '음'} - "
                f"{direction} 추세, {'MA크로스' if hint == 'ma_cross' else 'MACD'} 전략 권장"
            )
        else:
            condition, hint = "ranging", "rsi"
            reason = f"RSI {rsi:.1f}, BB폭 {bb_width_pct:.1f}% - 횡보 구간, RSI 전략 권장"

        return {
            "condition": condition,
            "rsi": round(rsi, 1),
            "bb_width_pct": round(bb_width_pct, 2),
            "ma20_slope": round(slope, 3),
            "reason": reason,
            "best_strategy_hint": hint,
        }
    except Exception as e:
        return {"condition": "unknown", "reason": f"분석 오류: {str(e)}", "best_strategy_hint": "rsi"}


def _ema(values: np.ndarray, period: int) -> float:
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


# ─── 그리드 서치 메인 함수 ────────────────────────────────────
async def run_grid_search(
    market: str = SCALPING_DEFAULTS["market"],
    interval: str = SCALPING_DEFAULTS["interval"],
    days: int = SCALPING_DEFAULTS["recommendation_lookback_days"],
    top_n: int = 3,
    order_ratio: float = SCALPING_DEFAULTS["order_ratio"],
    stop_loss: float = SCALPING_DEFAULTS["stop_loss"],
    take_profit: float = SCALPING_DEFAULTS["take_profit"],
    trailing_stop: bool = SCALPING_DEFAULTS["trailing_stop"],
    trailing_stop_pct: float = SCALPING_DEFAULTS["trailing_stop_pct"],
    split_ratio: float = 0.7,  # 앞 70% in-sample, 뒤 30% OOS
) -> dict:
    if days < 3:
        return {"error": "days는 최소 3 이상이어야 합니다 (OOS 구간 확보)"}

    key = _cache_key(
        market,
        interval,
        days,
        split_ratio,
        top_n,
        order_ratio,
        stop_loss,
        take_profit,
        trailing_stop,
        trailing_stop_pct,
    )
    cached = _get_cached(key)
    if cached:
        result = dict(cached)
        result["cached"] = True
        return result

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=8)

    df = await loop.run_in_executor(executor, lambda: download_history(market, interval, days))
    if df is None or df.empty or len(df) < 100:
        return {"error": "데이터 다운로드 실패 또는 데이터 부족"}

    # In-sample / OOS 분리
    split_idx = int(len(df) * split_ratio)
    df_train = df.iloc[:split_idx]
    df_test = df.iloc[split_idx:]
    if len(df_train) < 100 or len(df_test) < 30:
        return {
            "error": f"데이터 부족: 학습 {len(df_train)}봉, 검증 {len(df_test)}봉 (최소: 100 / 30)"
        }

    df_live = df.tail(200)
    market_info = analyze_market_condition(df_live)

    def run_one(strategy, params):
        try:
            train_res = run_backtest_on_df(
                df_train, strategy, params,
                order_ratio=order_ratio,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=trailing_stop,
                trailing_stop_pct=trailing_stop_pct,
            )
            test_res = run_backtest_on_df(
                df_test, strategy, params,
                order_ratio=order_ratio,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=trailing_stop,
                trailing_stop_pct=trailing_stop_pct,
            )
            return train_res, test_res
        except Exception as e:
            return {"error": str(e)}, {"error": str(e)}

    tasks = [
        loop.run_in_executor(executor, run_one, strategy, params)
        for strategy, params in PARAM_GRID
    ]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    scored = []
    for (strategy, params), result in zip(PARAM_GRID, results_raw):
        if isinstance(result, Exception):
            continue
        train_res, test_res = result
        if "error" in train_res or "error" in test_res:
            continue

        train_summary = train_res.get("summary", {})
        test_summary = test_res.get("summary", {})
        train_score = score_result(train_summary)
        if train_score <= -999:
            continue

        test_score = score_result(test_summary)
        overfit_info = detect_overfit(train_summary, test_summary)
        live_signal = get_signal(strategy, df_live, params)
        warmup_position = _has_warmup_position(
            market,
            interval,
            strategy,
            params,
            order_ratio,
            stop_loss,
            take_profit,
            trailing_stop,
            trailing_stop_pct,
            df_live,
        )

        # OOS 거래가 1건 미만이면 점수 패널티
        oos_score = test_score if test_summary.get("total_trades", 0) >= 1 else -100.0

        scored.append({
            "strategy": strategy,
            "params": params,
            "score": round(train_score, 4),
            "oos_score": round(oos_score, 4),
            "overfit_info": overfit_info,
            "live_signal": {
                "action": live_signal.action,
                "reason": live_signal.reason,
            },
            "warmup_position": warmup_position,
            "metrics": {
                "train": _extract_metrics(train_summary),
                "oos": _extract_metrics(test_summary),
            },
        })

    top = _select_top_recommendations(scored, market_info, top_n)
    if (
        top
        and top[0]["metrics"]["oos"].get("total_trades", 0) == 0
        and not top[0].get("warmup_position")
        and top[0].get("live_signal", {}).get("action") != "buy"
    ):
        fallback = _build_market_hint_fallback(scored, market_info)
        if fallback:
            top = [fallback] + [
                rec for rec in top
                if not (rec["strategy"] == fallback["strategy"] and rec["params"] == fallback["params"])
            ]
            top = top[:top_n]

    strategy_names = {"rsi": "RSI", "macd": "MACD", "bollinger": "볼린저 밴드", "ma_cross": "MA 크로스"}
    for rec in top:
        name = strategy_names.get(rec["strategy"], rec["strategy"])
        m_train = rec["metrics"]["train"]
        m_oos = rec["metrics"]["oos"]
        if rec.get("fallback"):
            rec["reason"] = f"{name} 전략 (시장 상태 fallback) | {market_info.get('reason', '현재 시장 상태 기준')}"
            continue
        market_hint = " (시장 상태 일치)" if rec["strategy"] == market_info.get("best_strategy_hint") else ""
        live_note = ""
        if rec.get("live_signal", {}).get("action") == "buy":
            live_note = " | 현재 buy 신호"
        elif rec.get("warmup_position"):
            live_note = " | 시작 시 포지션 복원 가능"
        overfit_warn = " ⚠️ 과최적화 의심" if rec["overfit_info"].get("overfit") else ""
        rec["reason"] = (
            f"{name} 전략{market_hint}{overfit_warn} | "
            f"학습 수익률 {m_train['total_return_pct']:+.1f}% / OOS {m_oos['total_return_pct']:+.1f}% | "
            f"샤프(OOS) {m_oos['sharpe_ratio']:.2f} | "
            f"승률(OOS) {m_oos['win_rate_pct']:.0f}% ({m_oos['total_trades']}건)"
            f"{live_note}"
        )

    executor.shutdown(wait=False)

    data = {
        "recommendations": top,
        "market_condition": market_info,
        "total_combinations_tested": len(scored),
        "split_info": {
            "train_candles": len(df_train),
            "oos_candles": len(df_test),
            "split_ratio": split_ratio,
        },
        "cached": False,
    }
    _set_cached(key, data)
    return data
