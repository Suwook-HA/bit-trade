import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

fake_strategies = types.ModuleType("core.strategies")
fake_strategies.get_signal = lambda *args, **kwargs: None
sys.modules.setdefault("core.strategies", fake_strategies)

from core.bot import BotConfig, BotState, _execute_signal


class DummyRisk:
    def __init__(self):
        self.kwargs = None

    def check_order_allowed(self, **kwargs):
        self.kwargs = kwargs
        return True, ""


def test_live_buy_uses_live_balances_for_risk_check(monkeypatch):
    risk = DummyRisk()
    config = BotConfig(mode="live", market="KRW-BTC", budget=1_000_000, order_ratio=0.5)
    state = BotState(position="none")
    called = {}

    def fake_get_balance(currency: str) -> float:
        balances = {"KRW": 200_000, "BTC": 0.1}
        return balances[currency]

    async def fake_live_buy(cfg, st, price):
        called["price"] = price
        return True

    monkeypatch.setattr("core.bot.get_balance", fake_get_balance)
    monkeypatch.setattr("core.bot._live_buy", fake_live_buy)

    asyncio.run(_execute_signal(config, state, risk, "buy", price=100_000_000))

    assert called["price"] == 100_000_000
    assert risk.kwargs["invest_krw"] == 100_000
    assert risk.kwargs["total_portfolio_krw"] == 10_200_000
