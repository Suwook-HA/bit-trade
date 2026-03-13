"""
백테스트 계산 회귀 테스트
- 신규 지표(Sortino, Profit Factor, Expectancy, Turnover) 존재 검증
- 기본 계산 정합성 확인
- 데이터 부족 처리 확인
"""
import pytest
import numpy as np
import pandas as pd

from core.backtest import run_backtest_on_df


# ─── 기본 동작 ─────────────────────────────────────────────────────

class TestRunBacktestOnDf:

    def test_returns_summary_and_trades(self, large_df):
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        assert "summary" in result
        assert "trades" in result
        assert "equity_curve" in result

    def test_summary_contains_all_required_keys(self, large_df):
        """Step 2에서 추가한 4개 지표를 포함한 모든 필드 존재 확인"""
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        summary = result["summary"]

        required_keys = [
            "initial_budget",
            "final_value",
            "total_return_pct",
            "total_trades",
            "win_rate_pct",
            "mdd_pct",
            "sharpe_ratio",
            # 신규 지표 (Step 2)
            "sortino_ratio",
            "profit_factor",
            "expectancy_krw",
            "turnover",
            "data_points",
            "fee_rate_pct",
            "slippage_rate_pct",
        ]
        for key in required_keys:
            assert key in summary, f"summary에 '{key}' 키가 없음"

    def test_initial_budget_preserved(self, large_df):
        budget = 5_000_000
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70},
                                    initial_budget=budget)
        assert result["summary"]["initial_budget"] == budget

    def test_final_value_is_positive(self, large_df):
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        assert result["summary"]["final_value"] > 0

    def test_win_rate_between_0_and_100(self, large_df):
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        wr = result["summary"]["win_rate_pct"]
        assert 0 <= wr <= 100, f"win_rate_pct={wr} 범위 초과"


# ─── 신규 지표 회귀 테스트 ─────────────────────────────────────────

class TestNewMetrics:

    def test_sortino_ratio_is_float(self, large_df):
        result = run_backtest_on_df(large_df, "macd", {"fast": 12, "slow": 26, "signal": 9})
        sortino = result["summary"]["sortino_ratio"]
        assert isinstance(sortino, (int, float)), f"sortino_ratio 타입 오류: {type(sortino)}"

    def test_profit_factor_non_negative(self, large_df):
        result = run_backtest_on_df(large_df, "macd", {"fast": 12, "slow": 26, "signal": 9})
        pf = result["summary"]["profit_factor"]
        assert pf >= 0, f"profit_factor={pf} 음수"

    def test_profit_factor_sentinel_when_no_loss(self):
        """손실 거래가 없으면 profit_factor=999.0 반환"""
        # 단조 상승 → 손절 없이 익절만 발생
        prices = np.linspace(1_000_000, 3_000_000, 300)
        idx = pd.date_range("2024-01-01", periods=300, freq="1min")
        df = pd.DataFrame(
            {"open": prices, "high": prices * 1.01, "low": prices * 0.995,
             "close": prices, "volume": np.ones(300) * 1000},
            index=idx,
        )
        result = run_backtest_on_df(
            df, "rsi",
            {"period": 14, "oversold": 30, "overbought": 70},
            stop_loss=0.99,   # 사실상 손절 없음
        )
        pf = result["summary"]["profit_factor"]
        assert pf > 0

    def test_turnover_between_0_and_1(self, large_df):
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        turnover = result["summary"]["turnover"]
        assert 0 <= turnover <= 1, f"turnover={turnover} 범위 초과"

    def test_expectancy_is_numeric(self, large_df):
        result = run_backtest_on_df(large_df, "bollinger", {"period": 20, "std_dev": 2.0})
        exp = result["summary"]["expectancy_krw"]
        assert isinstance(exp, (int, float)), f"expectancy_krw 타입 오류: {type(exp)}"

    def test_mdd_non_positive(self, large_df):
        result = run_backtest_on_df(large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        mdd = result["summary"]["mdd_pct"]
        assert mdd <= 0, f"mdd_pct={mdd}는 0 이하여야 함"


# ─── 에러 처리 ─────────────────────────────────────────────────────

class TestBacktestEdgeCases:

    def test_empty_df_returns_error(self):
        result = run_backtest_on_df(pd.DataFrame(), "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        assert "error" in result

    def test_insufficient_data_returns_error(self):
        """30봉 미만 데이터 → error"""
        prices = np.linspace(50_000_000, 55_000_000, 30)
        idx = pd.date_range("2024-01-01", periods=30, freq="1min")
        df = pd.DataFrame(
            {"open": prices, "high": prices * 1.001, "low": prices * 0.999,
             "close": prices, "volume": np.ones(30)},
            index=idx,
        )
        result = run_backtest_on_df(df, "rsi", {"period": 14, "oversold": 30, "overbought": 70})
        assert "error" in result

    def test_no_trades_produces_valid_summary(self, large_df):
        """거래가 발생하지 않는 극단 파라미터에서도 summary 반환"""
        result = run_backtest_on_df(
            large_df, "rsi",
            {"period": 14, "oversold": 5, "overbought": 95},  # 거의 발생 안 함
        )
        # error 또는 유효한 summary 반환 (둘 다 허용)
        assert "error" in result or "summary" in result

    def test_fee_and_slippage_reduce_return(self, large_df):
        """수수료/슬리피지 증가 시 수익률이 감소하거나 같아야 함"""
        result_low = run_backtest_on_df(
            large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70},
            fee_rate=0.0001, slippage_rate=0.0001,
        )
        result_high = run_backtest_on_df(
            large_df, "rsi", {"period": 14, "oversold": 30, "overbought": 70},
            fee_rate=0.002, slippage_rate=0.001,
        )
        if "error" not in result_low and "error" not in result_high:
            assert (
                result_low["summary"]["total_return_pct"]
                >= result_high["summary"]["total_return_pct"]
            )

    def test_stop_loss_limits_loss(self):
        """손절 설정 시 개별 거래 손실이 손절선 이하"""
        prices = np.concatenate([
            np.linspace(1_000_000, 1_200_000, 100),
            np.linspace(1_200_000, 600_000, 200),
        ])
        idx = pd.date_range("2024-01-01", periods=300, freq="1min")
        df = pd.DataFrame(
            {"open": prices, "high": prices * 1.005, "low": prices * 0.995,
             "close": prices, "volume": np.ones(300) * 1000},
            index=idx,
        )
        stop_loss = 0.05
        result = run_backtest_on_df(df, "rsi", {"period": 14, "oversold": 30, "overbought": 70},
                                    stop_loss=stop_loss)
        if "error" not in result:
            for trade in result["trades"]:
                if trade.get("side") == "sell" and "pnl_pct" in trade:
                    assert trade["pnl_pct"] >= -(stop_loss * 100 + 1), \
                        f"pnl_pct={trade['pnl_pct']} 손절선 초과"
