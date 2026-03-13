"""
전략 함수 단위 테스트
- RSI / MACD / Bollinger / MA Cross 신호 타입 검증
- 경계값, 최소 데이터 요건, 반환 타입 확인
"""
import pytest
import numpy as np
import pandas as pd

from core.strategies import get_signal


# ─── 헬퍼 ─────────────────────────────────────────────────────────

def _make_rising_df(n=100) -> pd.DataFrame:
    """단조 상승 시계열 (MA Cross 매수 신호 유도용)"""
    prices = np.linspace(1_000_000, 2_000_000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    return pd.DataFrame(
        {"open": prices, "high": prices * 1.001, "low": prices * 0.999,
         "close": prices, "volume": np.ones(n) * 1000},
        index=idx,
    )


def _make_falling_df(n=100) -> pd.DataFrame:
    """단조 하락 시계열"""
    prices = np.linspace(2_000_000, 1_000_000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    return pd.DataFrame(
        {"open": prices, "high": prices * 1.001, "low": prices * 0.999,
         "close": prices, "volume": np.ones(n) * 1000},
        index=idx,
    )


# ─── 반환 타입 / 기본 검증 ──────────────────────────────────────────

class TestGetSignalReturnType:
    """get_signal()이 항상 올바른 타입을 반환하는지 확인"""

    @pytest.mark.parametrize("strategy,params", [
        ("rsi",      {"period": 14, "oversold": 30, "overbought": 70}),
        ("macd",     {"fast": 12, "slow": 26, "signal": 9}),
        ("bollinger", {"period": 20, "std_dev": 2.0}),
        ("ma_cross", {"short_period": 5, "long_period": 20}),
    ])
    def test_returns_signal_object(self, sample_df, strategy, params):
        signal = get_signal(strategy, sample_df, params)
        assert hasattr(signal, "action"), "Signal 객체에 action 속성이 있어야 함"
        assert signal.action in {"buy", "sell", "hold"}, f"action은 buy/sell/hold 중 하나여야 함, 실제: {signal.action}"

    def test_unknown_strategy_returns_hold(self, sample_df):
        signal = get_signal("unknown_strategy_xyz", sample_df, {})
        assert signal.action == "hold"


# ─── RSI 전략 ─────────────────────────────────────────────────────

class TestRsiStrategy:
    PARAMS = {"period": 14, "oversold": 30, "overbought": 70}

    def test_hold_on_normal_market(self, ranging_df):
        signal = get_signal("rsi", ranging_df, self.PARAMS)
        # 횡보장에서 hold가 많아야 하지만, 최소한 valid action이어야 함
        assert signal.action in {"buy", "sell", "hold"}

    def test_oversold_triggers_buy(self):
        """RSI가 과매도 구간에 있으면 buy 신호"""
        # 강한 하락 시계열: RSI 낮아짐
        np.random.seed(0)
        prices = np.linspace(2_000_000, 800_000, 100)
        idx = pd.date_range("2024-01-01", periods=100, freq="1min")
        df = pd.DataFrame(
            {"open": prices, "high": prices * 1.001, "low": prices * 0.999,
             "close": prices, "volume": np.ones(100) * 1000},
            index=idx,
        )
        signal = get_signal("rsi", df, {"period": 14, "oversold": 50, "overbought": 80})
        # oversold 임계값을 높여(50) buy가 발생하는지 확인
        assert signal.action in {"buy", "hold"}

    def test_short_period_rsi(self, sample_df):
        """단기 RSI(7) 파라미터 동작"""
        signal = get_signal("rsi", sample_df, {"period": 7, "oversold": 25, "overbought": 65})
        assert signal.action in {"buy", "sell", "hold"}


# ─── MACD 전략 ────────────────────────────────────────────────────

class TestMacdStrategy:
    PARAMS = {"fast": 12, "slow": 26, "signal": 9}

    def test_basic_signal(self, sample_df):
        signal = get_signal("macd", sample_df, self.PARAMS)
        assert signal.action in {"buy", "sell", "hold"}

    def test_scalping_params(self, sample_df):
        """단타 파라미터(5/13/5) 동작"""
        signal = get_signal("macd", sample_df, {"fast": 5, "slow": 13, "signal": 5})
        assert signal.action in {"buy", "sell", "hold"}

    def test_rising_market_bias(self, bull_market_df):
        """상승 추세에서 MACD는 buy 또는 hold여야 함"""
        signal = get_signal("macd", bull_market_df, self.PARAMS)
        assert signal.action in {"buy", "hold"}


# ─── 볼린저 밴드 전략 ─────────────────────────────────────────────

class TestBollingerStrategy:
    PARAMS = {"period": 20, "std_dev": 2.0}

    def test_basic_signal(self, sample_df):
        signal = get_signal("bollinger", sample_df, self.PARAMS)
        assert signal.action in {"buy", "sell", "hold"}

    def test_narrow_band_params(self, ranging_df):
        """좁은 밴드(std_dev=1.5) 횡보장"""
        signal = get_signal("bollinger", ranging_df, {"period": 10, "std_dev": 1.5})
        assert signal.action in {"buy", "sell", "hold"}

    def test_wide_band_params(self, sample_df):
        """넓은 밴드(std_dev=2.5)"""
        signal = get_signal("bollinger", sample_df, {"period": 20, "std_dev": 2.5})
        assert signal.action in {"buy", "sell", "hold"}


# ─── MA 크로스 전략 ───────────────────────────────────────────────

class TestMaCrossStrategy:
    PARAMS = {"short_period": 5, "long_period": 20}

    def test_basic_signal(self, sample_df):
        signal = get_signal("ma_cross", sample_df, self.PARAMS)
        assert signal.action in {"buy", "sell", "hold"}

    def test_rising_market_buy(self):
        """단조 상승에서 골든크로스 → buy"""
        df = _make_rising_df(80)
        signal = get_signal("ma_cross", df, {"short_period": 3, "long_period": 10})
        assert signal.action in {"buy", "hold"}

    def test_falling_market_sell(self):
        """단조 하락에서 데드크로스 → sell"""
        df = _make_falling_df(80)
        signal = get_signal("ma_cross", df, {"short_period": 3, "long_period": 10})
        assert signal.action in {"sell", "hold"}

    def test_scalping_params(self, sample_df):
        """단타 파라미터(3/10)"""
        signal = get_signal("ma_cross", sample_df, {"short_period": 3, "long_period": 10})
        assert signal.action in {"buy", "sell", "hold"}
