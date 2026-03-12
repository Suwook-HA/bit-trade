import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    action: str  # 'buy' | 'sell' | 'hold'
    reason: str
    price: float
    indicator_values: dict


def compute_rsi_signal(df: pd.DataFrame, period: int = 14, oversold: float = 30, overbought: float = 70) -> Signal:
    if len(df) < period + 1:
        return Signal("hold", "Not enough data", df["close"].iloc[-1], {})

    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=period)
    rsi = df["rsi"].iloc[-1]
    price = df["close"].iloc[-1]

    if pd.isna(rsi):
        return Signal("hold", "RSI not computed", price, {})

    if rsi <= oversold:
        return Signal("buy", f"RSI {rsi:.1f} <= {oversold} (oversold)", price, {"rsi": round(rsi, 2)})
    elif rsi >= overbought:
        return Signal("sell", f"RSI {rsi:.1f} >= {overbought} (overbought)", price, {"rsi": round(rsi, 2)})
    return Signal("hold", f"RSI {rsi:.1f}", price, {"rsi": round(rsi, 2)})


def compute_macd_signal(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Signal:
    if len(df) < slow + signal:
        return Signal("hold", "Not enough data", df["close"].iloc[-1], {})

    df = df.copy()
    macd_df = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.empty:
        return Signal("hold", "MACD not computed", df["close"].iloc[-1], {})

    col_macd = f"MACD_{fast}_{slow}_{signal}"
    col_signal = f"MACDs_{fast}_{slow}_{signal}"

    macd_val = macd_df[col_macd].iloc[-1]
    sig_val = macd_df[col_signal].iloc[-1]
    prev_macd = macd_df[col_macd].iloc[-2]
    prev_sig = macd_df[col_signal].iloc[-2]
    price = df["close"].iloc[-1]

    if pd.isna(macd_val) or pd.isna(sig_val):
        return Signal("hold", "MACD not computed", price, {})

    indicators = {"macd": round(macd_val, 2), "signal": round(sig_val, 2)}

    # Golden cross: MACD crosses above signal
    if prev_macd <= prev_sig and macd_val > sig_val:
        return Signal("buy", "MACD golden cross", price, indicators)
    # Dead cross: MACD crosses below signal
    elif prev_macd >= prev_sig and macd_val < sig_val:
        return Signal("sell", "MACD dead cross", price, indicators)
    return Signal("hold", f"MACD {macd_val:.2f} / Signal {sig_val:.2f}", price, indicators)


def _bbands(close: pd.Series, length: int = 20, std_dev: float = 2.0):
    """numba 없이 pandas rolling으로 볼린저밴드 계산"""
    mid = close.rolling(length).mean()
    std = close.rolling(length).std(ddof=0)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def compute_bollinger_signal(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0
) -> Signal:
    if len(df) < period:
        return Signal("hold", "Not enough data", df["close"].iloc[-1], {})

    df = df.copy()
    upper, mid, lower = _bbands(df["close"], length=period, std_dev=std_dev)

    upper_val = upper.iloc[-1]
    lower_val = lower.iloc[-1]
    mid_val   = mid.iloc[-1]
    price = df["close"].iloc[-1]

    upper = upper_val
    lower = lower_val
    mid   = mid_val

    if pd.isna(upper) or pd.isna(lower):
        return Signal("hold", "BB not computed", price, {})

    indicators = {
        "upper": round(upper, 0),
        "lower": round(lower, 0),
        "mid": round(mid, 0),
    }

    if price <= lower:
        return Signal("buy", f"Price touched lower BB {lower:.0f}", price, indicators)
    elif price >= upper:
        return Signal("sell", f"Price touched upper BB {upper:.0f}", price, indicators)
    return Signal("hold", f"Price within BB ({lower:.0f} ~ {upper:.0f})", price, indicators)


def compute_ma_cross_signal(
    df: pd.DataFrame,
    short_period: int = 5,
    long_period: int = 20
) -> Signal:
    if len(df) < long_period + 1:
        return Signal("hold", "Not enough data", df["close"].iloc[-1], {})

    df = df.copy()
    df["ma_short"] = ta.sma(df["close"], length=short_period)
    df["ma_long"] = ta.sma(df["close"], length=long_period)

    short_cur = df["ma_short"].iloc[-1]
    long_cur = df["ma_long"].iloc[-1]
    short_prev = df["ma_short"].iloc[-2]
    long_prev = df["ma_long"].iloc[-2]
    price = df["close"].iloc[-1]

    if pd.isna(short_cur) or pd.isna(long_cur):
        return Signal("hold", "MA not computed", price, {})

    indicators = {
        f"ma{short_period}": round(short_cur, 0),
        f"ma{long_period}": round(long_cur, 0),
    }

    # Golden cross
    if short_prev <= long_prev and short_cur > long_cur:
        return Signal("buy", f"MA{short_period} golden cross MA{long_period}", price, indicators)
    # Dead cross
    elif short_prev >= long_prev and short_cur < long_cur:
        return Signal("sell", f"MA{short_period} dead cross MA{long_period}", price, indicators)
    return Signal("hold", f"MA{short_period}={short_cur:.0f}, MA{long_period}={long_cur:.0f}", price, indicators)


STRATEGY_MAP = {
    "rsi": compute_rsi_signal,
    "macd": compute_macd_signal,
    "bollinger": compute_bollinger_signal,
    "ma_cross": compute_ma_cross_signal,
}


def get_signal(strategy: str, df: pd.DataFrame, params: dict, volume_filter: bool = True) -> Signal:
    func = STRATEGY_MAP.get(strategy)
    if func is None:
        return Signal("hold", "Unknown strategy", df["close"].iloc[-1] if not df.empty else 0, {})

    signal = func(df, **params)

    # 거래량 필터: 신호 발생 시 거래량이 평균의 40% 미만이면 노이즈로 간주
    if volume_filter and signal.action != "hold" and "volume" in df.columns and len(df) >= 20:
        vol_cur = float(df["volume"].iloc[-1])
        vol_avg = float(df["volume"].rolling(20).mean().iloc[-1])
        if not pd.isna(vol_avg) and vol_avg > 0 and vol_cur < vol_avg * 0.4:
            return Signal(
                "hold",
                f"Low volume filtered ({vol_cur:.0f} < {vol_avg * 0.4:.0f})",
                signal.price,
                signal.indicator_values,
            )

    return signal


def compute_indicators_for_chart(df: pd.DataFrame) -> dict:
    """프론트엔드 차트에 표시할 지표 계산"""
    if df.empty:
        return {}

    result = {}

    # MA
    for period in [5, 20, 60]:
        ma = ta.sma(df["close"], length=period)
        if ma is not None:
            result[f"ma{period}"] = [
                {"time": int(ts.timestamp()), "value": float(v)}
                for ts, v in zip(df.index, ma)
                if not pd.isna(v)
            ]

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = _bbands(df["close"], length=20, std_dev=2.0)
    result["bb_upper"] = [
        {"time": int(ts.timestamp()), "value": float(v)}
        for ts, v in zip(df.index, bb_upper)
        if not pd.isna(v)
    ]
    result["bb_lower"] = [
        {"time": int(ts.timestamp()), "value": float(v)}
        for ts, v in zip(df.index, bb_lower)
        if not pd.isna(v)
    ]
    result["bb_mid"] = [
        {"time": int(ts.timestamp()), "value": float(v)}
        for ts, v in zip(df.index, bb_mid)
        if not pd.isna(v)
    ]

    # RSI
    rsi = ta.rsi(df["close"], length=14)
    if rsi is not None:
        result["rsi"] = [
            {"time": int(ts.timestamp()), "value": float(v)}
            for ts, v in zip(df.index, rsi)
            if not pd.isna(v)
        ]

    # MACD
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        result["macd"] = [
            {"time": int(ts.timestamp()), "value": float(v)}
            for ts, v in zip(df.index, macd_df["MACD_12_26_9"])
            if not pd.isna(v)
        ]
        result["macd_signal"] = [
            {"time": int(ts.timestamp()), "value": float(v)}
            for ts, v in zip(df.index, macd_df["MACDs_12_26_9"])
            if not pd.isna(v)
        ]
        result["macd_hist"] = [
            {"time": int(ts.timestamp()), "value": float(v)}
            for ts, v in zip(df.index, macd_df["MACDh_12_26_9"])
            if not pd.isna(v)
        ]

    return result
