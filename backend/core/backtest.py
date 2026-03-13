import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

import pyupbit
from core.strategies import get_signal


def download_history(market: str, interval: str, days: int = 30) -> pd.DataFrame:
    """Upbit에서 과거 데이터 다운로드 (배치 방식)"""
    interval_map = {
        "1m": ("minute1", 1),
        "3m": ("minute3", 3),
        "5m": ("minute5", 5),
        "15m": ("minute15", 15),
        "1h": ("minute60", 60),
        "1d": ("day", 1440),
    }

    upbit_interval, mins = interval_map.get(interval, ("minute1", 1))
    candles_needed = int(days * 24 * 60 / mins)

    all_df = []
    to_date = None
    batch_size = 200

    batches_needed = (candles_needed + batch_size - 1) // batch_size

    for _ in range(min(batches_needed, 50)):  # max 50 batches = 10000 candles
        try:
            if upbit_interval == "day":
                df = pyupbit.get_ohlcv(market, interval="day", count=batch_size, to=to_date)
            else:
                df = pyupbit.get_ohlcv(market, interval=upbit_interval, count=batch_size, to=to_date)

            if df is None or df.empty:
                break

            all_df.append(df)
            to_date = df.index[0].strftime("%Y-%m-%d %H:%M:%S")

        except Exception:
            break

    if not all_df:
        return pd.DataFrame()

    combined = pd.concat(all_df).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined


def run_backtest_on_df(
    df: pd.DataFrame,
    strategy: str,
    params: dict,
    initial_budget: float = 10000000,
    order_ratio: float = 0.5,
    stop_loss: float = 0.03,
    take_profit: float = 0.05,
    fee_rate: float = 0.0005,        # 업비트 수수료 0.05%
    slippage_rate: float = 0.0002,   # 슬리피지 0.02%
    trailing_stop: bool = False,
    trailing_stop_pct: float = 0.02,
    volume_filter: bool = True,
) -> dict:
    """사전 다운로드된 DataFrame으로 백테스트 실행 (그리드 서치용)"""
    if df.empty or len(df) < 50:
        return {"error": "Not enough historical data"}

    krw = initial_budget
    btc = 0.0
    position = "none"
    entry_price = 0.0
    peak_price = 0.0
    trades = []
    equity_curve = []
    window = 60

    for i in range(window, len(df)):
        window_df = df.iloc[:i + 1]
        price = float(df["close"].iloc[i])
        ts = int(df.index[i].timestamp())

        try:
            signal = get_signal(strategy, window_df, params, volume_filter=volume_filter)
        except Exception:
            continue

        action = signal.action

        # 포지션 보유 중 최고가 갱신
        if position == "long":
            if price > peak_price:
                peak_price = price

        if position == "long" and entry_price > 0:
            change = (price - entry_price) / entry_price
            if change <= -stop_loss:
                action = "sell"
            elif change >= take_profit:
                action = "sell"
            # 추적손절
            elif trailing_stop and peak_price > 0:
                drop = (price - peak_price) / peak_price
                if drop <= -trailing_stop_pct:
                    action = "sell"

        if action == "buy" and position == "none":
            invest = krw * order_ratio
            if invest >= 5000:
                # 슬리피지 반영 매수 체결가
                buy_price = price * (1 + slippage_rate)
                fee = invest * fee_rate
                btc = (invest - fee) / buy_price
                krw -= invest
                entry_price = buy_price
                peak_price = buy_price
                position = "long"
                trades.append({"time": ts, "side": "buy", "price": round(buy_price, 0), "volume": btc})

        elif action == "sell" and position == "long":
            # 슬리피지 반영 매도 체결가
            sell_price = price * (1 - slippage_rate)
            krw_return = btc * sell_price
            fee = krw_return * fee_rate
            krw_return -= fee
            pnl = krw_return - (btc * entry_price)
            krw += krw_return
            trades.append({
                "time": ts, "side": "sell", "price": round(sell_price, 0), "volume": btc,
                "pnl": round(pnl, 0),
                "pnl_pct": round((sell_price - entry_price) / entry_price * 100, 2),
            })
            btc = 0.0
            position = "none"
            entry_price = 0.0
            peak_price = 0.0

        total_value = krw + btc * price
        equity_curve.append({"time": ts, "value": round(total_value, 0)})

    final_price = float(df["close"].iloc[-1])
    final_value = krw + btc * final_price

    total_return = (final_value - initial_budget) / initial_budget * 100
    sell_trades = [t for t in trades if t["side"] == "sell"]
    winning = [t for t in sell_trades if t.get("pnl", 0) > 0]
    win_rate = len(winning) / len(sell_trades) * 100 if sell_trades else 0

    equity_values = np.array([e["value"] for e in equity_curve])
    if len(equity_values) > 0:
        running_max = np.maximum.accumulate(equity_values)
        drawdowns = (equity_values - running_max) / running_max
        mdd = float(drawdowns.min() * 100)
    else:
        mdd = 0

    # ── Annualization factor ─────────────────────────────────────
    if len(df) > 1:
        avg_seconds = (df.index[-1] - df.index[0]).total_seconds() / (len(df) - 1)
        candles_per_year = 365 * 24 * 3600 / max(avg_seconds, 1)
    else:
        candles_per_year = 252 * 24 * 60  # fallback: 1분봉

    # ── Sharpe Ratio ─────────────────────────────────────────────
    if len(equity_values) > 1:
        returns = np.diff(equity_values) / equity_values[:-1]
        if returns.std() > 0:
            sharpe = float(returns.mean() / returns.std() * np.sqrt(candles_per_year))
        else:
            sharpe = 0.0
    else:
        returns = np.array([])
        sharpe = 0.0

    # ── Sortino Ratio ────────────────────────────────────────────
    if len(returns) > 0:
        downside = returns[returns < 0]
        if len(downside) > 0 and downside.std() > 0:
            sortino = float(returns.mean() / downside.std() * np.sqrt(candles_per_year))
        else:
            sortino = 0.0
    else:
        sortino = 0.0

    # ── Profit Factor ────────────────────────────────────────────
    pnl_values = [t.get("pnl", 0) for t in sell_trades]
    gross_profit = sum(p for p in pnl_values if p > 0)
    gross_loss = abs(sum(p for p in pnl_values if p < 0))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else 999.0

    # ── Expectancy (평균 거래 PnL) ───────────────────────────────
    expectancy = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

    # ── Turnover (거래 빈도) ─────────────────────────────────────
    turnover = len(sell_trades) / len(df) if len(df) > 0 else 0.0

    return {
        "summary": {
            "initial_budget": initial_budget,
            "final_value": round(final_value, 0),
            "total_return_pct": round(total_return, 2),
            "total_trades": len(sell_trades),
            "win_rate_pct": round(win_rate, 2),
            "mdd_pct": round(mdd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "profit_factor": profit_factor,
            "expectancy_krw": round(expectancy, 0),
            "turnover": round(turnover, 4),
            "data_points": len(df),
            "fee_rate_pct": round(fee_rate * 100, 3),
            "slippage_rate_pct": round(slippage_rate * 100, 3),
        },
        "trades": trades[-100:],
        "equity_curve": equity_curve[::max(1, len(equity_curve) // 500)],
    }


def run_backtest(
    market: str,
    interval: str,
    strategy: str,
    params: dict,
    days: int = 30,
    initial_budget: float = 10000000,
    order_ratio: float = 0.5,
    stop_loss: float = 0.03,
    take_profit: float = 0.05,
    fee_rate: float = 0.0005,
    slippage_rate: float = 0.0002,
    trailing_stop: bool = False,
    trailing_stop_pct: float = 0.02,
) -> dict:
    df = download_history(market, interval, days)
    if df.empty or len(df) < 50:
        return {"error": "Not enough historical data"}
    return run_backtest_on_df(
        df, strategy, params, initial_budget, order_ratio,
        stop_loss, take_profit, fee_rate, slippage_rate,
        trailing_stop, trailing_stop_pct,
    )
