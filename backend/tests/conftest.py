"""
pytest 픽스처 모음
- sample_df: 200봉 랜덤 OHLCV (재현 가능)
- bull_market_df: 상승 추세 OHLCV
- ranging_df: 횡보 OHLCV
"""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


def _make_ohlcv(prices: np.ndarray, base_volume: float = 1.0) -> pd.DataFrame:
    """가격 배열로 OHLCV DataFrame 생성"""
    n = len(prices)
    noise = np.abs(np.random.randn(n) * prices * 0.002)  # ±0.2% 노이즈
    opens = prices
    closes = prices + np.random.randn(n) * prices * 0.001
    highs = np.maximum(opens, closes) + noise
    lows = np.minimum(opens, closes) - noise
    volumes = base_volume * (1 + np.abs(np.random.randn(n) * 0.3))

    index = pd.date_range(
        start=datetime(2024, 1, 1),
        periods=n,
        freq="1min",
    )
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=index,
    )


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """200봉 재현 가능 랜덤 OHLCV"""
    np.random.seed(42)
    prices = 50_000_000 + np.cumsum(np.random.randn(200) * 100_000)
    prices = np.abs(prices)  # 음수 방지
    return _make_ohlcv(prices)


@pytest.fixture
def bull_market_df() -> pd.DataFrame:
    """상승 추세 200봉 OHLCV"""
    np.random.seed(7)
    trend = np.linspace(40_000_000, 60_000_000, 200)
    noise = np.random.randn(200) * 200_000
    prices = trend + noise
    return _make_ohlcv(prices)


@pytest.fixture
def ranging_df() -> pd.DataFrame:
    """횡보 200봉 OHLCV"""
    np.random.seed(13)
    base = 50_000_000
    prices = base + np.random.randn(200) * 300_000
    return _make_ohlcv(prices)


@pytest.fixture
def large_df() -> pd.DataFrame:
    """1000봉 OHLCV (백테스트 충분 데이터)"""
    np.random.seed(99)
    prices = 50_000_000 + np.cumsum(np.random.randn(1000) * 80_000)
    prices = np.abs(prices)
    return _make_ohlcv(prices)
