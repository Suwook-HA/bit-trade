import pandas as pd

from core.bot import _get_signal_df, _validate_order_ratio


def test_get_signal_df_uses_only_closed_candles(sample_df):
    signal_df = _get_signal_df(sample_df)

    assert len(signal_df) == len(sample_df) - 1
    assert signal_df.index[-1] == sample_df.index[-2]
    pd.testing.assert_series_equal(signal_df.iloc[-1], sample_df.iloc[-2], check_names=False)


def test_validate_order_ratio_blocks_orders_above_risk_limit():
    message = _validate_order_ratio(0.5)

    assert message is not None
    assert "max_position_weight" in message


def test_validate_order_ratio_allows_safe_order_size():
    assert _validate_order_ratio(0.3) is None
