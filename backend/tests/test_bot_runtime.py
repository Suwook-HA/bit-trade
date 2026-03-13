import asyncio

import pandas as pd

from core.bot import BotConfig, BotState, _bot_loop, _get_signal_df, _validate_order_ratio, _warmup_paper_state
from core.strategies import Signal


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


def test_warmup_paper_state_seeds_open_position(sample_df, monkeypatch):
    config = BotConfig(
        strategy="macd",
        params={"fast": 5, "slow": 13, "signal": 5},
        budget=1_000_000,
        order_ratio=0.3,
        stop_loss=0.5,
        take_profit=0.5,
        trailing_stop=False,
    )
    state = BotState()
    state.paper_krw = config.budget
    calls = {"count": 0}

    def fake_get_signal(strategy, df, params):
        calls["count"] += 1
        action = "buy" if calls["count"] == 2 else "hold"
        return Signal(action, action, float(df["close"].iloc[-1]), {})

    monkeypatch.setattr("core.bot.get_signal", fake_get_signal)

    seeded = _warmup_paper_state(config, state, sample_df)

    assert seeded is True
    assert state.position == "long"
    assert state.paper_asset > 0
    assert state.paper_krw < config.budget
    assert "Warm-up seeded open" in state.last_signal_reason


def test_warmup_paper_state_resets_flat_state_after_sell(sample_df, monkeypatch):
    config = BotConfig(
        strategy="macd",
        params={"fast": 5, "slow": 13, "signal": 5},
        budget=1_000_000,
        order_ratio=0.3,
        stop_loss=0.5,
        take_profit=0.5,
        trailing_stop=False,
    )
    state = BotState()
    state.paper_krw = config.budget
    calls = {"count": 0}

    def fake_get_signal(strategy, df, params):
        calls["count"] += 1
        if calls["count"] == 2:
            action = "buy"
        elif calls["count"] == 4:
            action = "sell"
        else:
            action = "hold"
        return Signal(action, action, float(df["close"].iloc[-1]), {})

    monkeypatch.setattr("core.bot.get_signal", fake_get_signal)

    seeded = _warmup_paper_state(config, state, sample_df)

    assert seeded is False
    assert state.position == "none"
    assert state.paper_asset == 0
    assert state.paper_krw == config.budget


def test_bot_loop_preserves_seeded_paper_balances(monkeypatch):
    config = BotConfig(mode="paper", budget=1_000_000)
    state = BotState(
        position="long",
        entry_price=100_000_000,
        entry_volume=0.003,
        paper_krw=700_000,
        paper_asset=0.003,
    )

    monkeypatch.setattr("core.bot.get_risk_engine", lambda: object())

    def fake_get_candles_df(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr("core.bot.get_candles_df", fake_get_candles_df)

    asyncio.run(_bot_loop(config, state))

    assert state.paper_krw == 700_000
    assert state.paper_asset == 0.003
