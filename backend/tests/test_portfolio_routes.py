from api.routes import _build_seeded_trade


def test_build_seeded_trade_for_open_position():
    trade = _build_seeded_trade(
        {
            "position": "long",
            "entry_price": 101_500_000,
            "asset": 0.0025,
            "updated_at": "2026-03-13 14:00:00",
        },
        market="KRW-BTC",
        mode="paper",
    )

    assert trade is not None
    assert trade["side"] == "buy"
    assert trade["price"] == 101_500_000
    assert trade["volume"] == 0.0025
    assert trade["status"] == "seeded"
    assert trade["synthetic"] is True
    assert trade["market"] == "KRW-BTC"
    assert trade["mode"] == "paper"


def test_build_seeded_trade_skips_flat_position():
    trade = _build_seeded_trade(
        {
            "position": "none",
            "entry_price": 0,
            "asset": 0,
        },
        market="KRW-BTC",
        mode="paper",
    )

    assert trade is None
