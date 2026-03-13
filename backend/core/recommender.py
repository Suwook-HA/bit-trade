"""
전략 자동 추천 & 그리드 서치 엔진
- 단타 최적화 파라미터 포함 54개 전략×파라미터 조합 병렬 백테스트
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

# ─── 파라미터 그리드 (단타 최적화 포함) ──────────────────────────
PARAM_GRID: list[tuple[str, dict]] = []

# RSI: 단기(7,9) + 표준(10,14) 조합
for _period, _oversold, _overbought in itertools.product([7, 9, 10, 14], [25, 30], [65, 70]):
    PARAM_GRID.append(("rsi", {"period": _period, "oversold": _oversold, "overbought": _overbought}))

# MACD: 단기(5/13/5) + 표준(8/21, 12/26)
_macd_combos = [
    (5, 13, 5),   # 단타 최적화
    (8, 21, 7),
    (8, 21, 9),
    (12, 26, 7),
    (12, 26, 9),
]
for _fast, _slow, _sig in _macd_combos:
    PARAM_GRID.append(("macd", {"fast": _fast, "slow": _slow, "signal": _sig}))

# 볼린저밴드: 단기(10) + 표준(15, 20)
for _period, _std in itertools.product([10, 15, 20], [1.5, 2.0, 2.5]):
    PARAM_GRID.append(("bollinger", {"period": _period, "std_dev": _std}))

# MA 크로스: 단기(3/10, 5/15) + 표준
for _short, _long in itertools.product([3, 5, 7], [10, 15, 20]):
    if _short < _long:
        PARAM_GRID.append(("ma_cross", {"short_period": _short, "long_period": _long}))

# ─── 캐시 ──────────────────────────────────────────────────────
_cache: dict = {}
_CACHE_TTL = 300  # 5분

def _cache_key(market, interval, days):
    return f"{market}:{interval}:{days}"

def _get_cached(key):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None

def _set_cached(key, data):
    _cache[key] = {"ts": time.time(), "data": data}


# ─── 스코어링 ──────────────────────────────────────────────────
def score_result(summary: dict) -> float:
    trades = summary.get("total_trades", 0)
    if trades < 2:
        return -999.0
    ret = summary.get("total_return_pct", 0)
    sharpe = summary.get("sharpe_ratio", 0)
    win_rate = summary.get("win_rate_pct", 0)
    return ret * 0.4 + sharpe * 0.4 + (win_rate / 5) * 0.2


# ─── 시장 상태 분석 ────────────────────────────────────────────
def analyze_market_condition(df: pd.DataFrame) -> dict:
    """최근 캔들 데이터로 시장 상태 판별"""
    if df is None or len(df) < 30:
        return {"condition": "unknown", "reason": "데이터 부족", "best_strategy_hint": "rsi"}

    try:
        close = df["close"].values.astype(float)

        # RSI(14)
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.mean(gain[-14:]) if len(gain) >= 14 else np.mean(gain)
        avg_loss = np.mean(loss[-14:]) if len(loss) >= 14 else np.mean(loss)
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 50

        # MA20, MA20 기울기
        ma20 = np.mean(close[-20:]) if len(close) >= 20 else np.mean(close)
        if len(close) >= 25:
            ma20_prev = np.mean(close[-25:-5])
            slope = (ma20 - ma20_prev) / ma20_prev * 100
        else:
            slope = 0.0

        # 볼린저 밴드 폭
        if len(close) >= 20:
            std = np.std(close[-20:])
            bb_mid = np.mean(close[-20:])
            bb_upper = bb_mid + 2 * std
            bb_lower = bb_mid - 2 * std
            bb_width_pct = (bb_upper - bb_lower) / bb_mid * 100
        else:
            bb_width_pct = 2.0

        # MACD 방향
        if len(close) >= 26:
            ema12 = _ema(close, 12)
            ema26 = _ema(close, 26)
            macd_val = ema12 - ema26
        else:
            macd_val = 0.0

        # 시장 상태 분류
        if bb_width_pct > 4.0:
            condition = "volatile"
            hint = "bollinger"
            reason = f"BB폭 {bb_width_pct:.1f}% - 고변동성, 볼린저밴드 전략 권장"
        elif abs(slope) > 0.5 and ((slope > 0 and macd_val > 0) or (slope < 0 and macd_val < 0)):
            condition = "trending_up" if slope > 0 else "trending_down"
            hint = "ma_cross" if abs(slope) > 1.0 else "macd"
            direction = "상승" if slope > 0 else "하락"
            reason = f"MA20 기울기 {slope:+.2f}%, MACD {'양' if macd_val > 0 else '음'} - {direction} 추세, {'MA크로스' if hint == 'ma_cross' else 'MACD'} 전략 권장"
        else:
            condition = "ranging"
            hint = "rsi"
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
    market: str = "KRW-BTC",
    interval: str = "1m",
    days: int = 7,
    top_n: int = 3,
    order_ratio: float = 0.5,
    stop_loss: float = 0.03,
    take_profit: float = 0.05,
) -> dict:
    key = _cache_key(market, interval, days)
    cached = _get_cached(key)
    if cached:
        result = dict(cached)
        result["cached"] = True
        return result

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=8)

    # 1. 데이터 1회 다운로드
    df = await loop.run_in_executor(executor, lambda: download_history(market, interval, days))
    if df is None or df.empty or len(df) < 100:
        return {"error": "데이터 다운로드 실패 또는 데이터 부족"}

    # 2. 시장 상태 분석 (최근 200봉)
    df_live = df.tail(200)
    market_info = analyze_market_condition(df_live)

    # 3. 35개 조합 병렬 백테스트
    def run_one(strategy, params):
        try:
            return run_backtest_on_df(
                df, strategy, params,
                order_ratio=order_ratio,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as e:
            return {"error": str(e)}

    tasks = [
        loop.run_in_executor(executor, run_one, strategy, params)
        for strategy, params in PARAM_GRID
    ]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)

    # 4. 스코어링
    scored = []
    for (strategy, params), result in zip(PARAM_GRID, results_raw):
        if isinstance(result, Exception) or "error" in result:
            continue
        summary = result.get("summary", {})
        s = score_result(summary)
        if s <= -999:
            continue
        scored.append({
            "strategy": strategy,
            "params": params,
            "score": round(s, 4),
            "metrics": {
                "total_return_pct": summary.get("total_return_pct", 0),
                "sharpe_ratio": summary.get("sharpe_ratio", 0),
                "win_rate_pct": summary.get("win_rate_pct", 0),
                "total_trades": summary.get("total_trades", 0),
                "mdd_pct": summary.get("mdd_pct", 0),
            },
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    # 5. 추천 이유 생성
    strategy_names = {
        "rsi": "RSI", "macd": "MACD",
        "bollinger": "볼린저 밴드", "ma_cross": "MA 크로스",
    }
    for i, rec in enumerate(top):
        name = strategy_names.get(rec["strategy"], rec["strategy"])
        m = rec["metrics"]
        market_hint = " (시장 상태 일치)" if rec["strategy"] == market_info.get("best_strategy_hint") else ""
        rec["reason"] = (
            f"{name} 전략{market_hint} - "
            f"수익률 {m['total_return_pct']:+.1f}%, 샤프 {m['sharpe_ratio']:.2f}, "
            f"승률 {m['win_rate_pct']:.0f}% ({m['total_trades']}건)"
        )

    executor.shutdown(wait=False)

    data = {
        "recommendations": top,
        "market_condition": market_info,
        "total_combinations_tested": len(scored),
        "cached": False,
    }
    _set_cached(key, data)
    return data
