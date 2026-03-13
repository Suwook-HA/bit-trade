from api.routes import BotStartRequest, RecommendRequest
from core.defaults import SCALPING_DEFAULTS, get_strategy_params


def test_bot_start_defaults_match_scalping_profile():
    req = BotStartRequest()

    assert req.market == SCALPING_DEFAULTS["market"]
    assert req.interval == SCALPING_DEFAULTS["interval"]
    assert req.strategy == SCALPING_DEFAULTS["strategy"]
    assert req.params == get_strategy_params(SCALPING_DEFAULTS["strategy"])
    assert req.order_ratio == SCALPING_DEFAULTS["order_ratio"]
    assert req.stop_loss == SCALPING_DEFAULTS["stop_loss"]
    assert req.take_profit == SCALPING_DEFAULTS["take_profit"]
    assert req.trailing_stop is SCALPING_DEFAULTS["trailing_stop"]
    assert req.trailing_stop_pct == SCALPING_DEFAULTS["trailing_stop_pct"]


def test_recommend_defaults_match_scalping_profile():
    req = RecommendRequest()

    assert req.market == SCALPING_DEFAULTS["market"]
    assert req.interval == SCALPING_DEFAULTS["interval"]
    assert req.days == SCALPING_DEFAULTS["recommendation_lookback_days"]
    assert req.order_ratio == SCALPING_DEFAULTS["order_ratio"]
    assert req.stop_loss == SCALPING_DEFAULTS["stop_loss"]
    assert req.take_profit == SCALPING_DEFAULTS["take_profit"]
    assert req.trailing_stop is SCALPING_DEFAULTS["trailing_stop"]
    assert req.trailing_stop_pct == SCALPING_DEFAULTS["trailing_stop_pct"]
