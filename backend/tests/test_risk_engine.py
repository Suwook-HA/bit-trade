"""
리스크 엔진 시나리오 테스트
- 일일 손실 한도 초과
- 연속 손실 제한
- Circuit Breaker 발동/해제
- 최대 동시 포지션 제한
- 자산 비중 제한
"""
import pytest
from core.risk_engine import RiskEngine, RiskConfig


@pytest.fixture
def engine() -> RiskEngine:
    """테스트 격리를 위한 독립 RiskEngine 인스턴스"""
    return RiskEngine()


@pytest.fixture
def strict_engine() -> RiskEngine:
    """엄격한 설정 RiskEngine (테스트용 낮은 임계값)"""
    config = RiskConfig(
        max_daily_loss_pct=0.02,          # 2% 손실 허용
        max_consecutive_losses=3,          # 연속 3회 손실 차단
        max_simultaneous_positions=2,      # 최대 2개 포지션
        max_position_weight=0.30,          # 최대 30% 비중
        circuit_breaker_enabled=True,
        circuit_breaker_threshold=0.05,    # 5% 손실 시 circuit breaker
    )
    e = RiskEngine(config)
    return e


# ─── 초기화 ─────────────────────────────────────────────────────────

class TestInitializeSession:

    def test_session_initialized(self, engine):
        engine.initialize_session("paper", 10_000_000)
        status = engine.get_status("paper")
        assert status["initial_value"] == 10_000_000
        assert status["daily_pnl"] == 0.0
        assert not status["circuit_breaker_triggered"]

    def test_multiple_modes_independent(self, engine):
        engine.initialize_session("paper", 5_000_000)
        engine.initialize_session("live", 20_000_000)
        assert engine.get_status("paper")["initial_value"] == 5_000_000
        assert engine.get_status("live")["initial_value"] == 20_000_000


# ─── 주문 허용 기본 ──────────────────────────────────────────────────

class TestCheckOrderAllowed:

    def test_buy_allowed_normal(self, engine):
        engine.initialize_session("paper", 10_000_000)
        allowed, reason = engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=10_000_000,
            active_position_count=0,
        )
        assert allowed, f"정상 주문이 차단됨: {reason}"

    def test_sell_always_allowed(self, engine):
        """매도 주문은 항상 허용 (포지션 청산)"""
        engine.initialize_session("paper", 10_000_000)
        allowed, _ = engine.check_order_allowed(
            mode="paper", side="sell", market="KRW-BTC",
            invest_krw=0, total_portfolio_krw=10_000_000,
            active_position_count=5,  # 최대치 초과여도
        )
        assert allowed

    def test_uninitialized_mode_denied(self, engine):
        """초기화되지 않은 mode는 거부"""
        allowed, reason = engine.check_order_allowed(
            mode="unknown_mode", side="buy", market="KRW-BTC",
            invest_krw=100_000, total_portfolio_krw=1_000_000,
            active_position_count=0,
        )
        assert not allowed
        assert "초기화" in reason or "세션" in reason.lower() or "not" in reason.lower()


# ─── 일일 손실 한도 ──────────────────────────────────────────────────

    def test_default_config_allows_half_budget_order(self, engine):
        engine.initialize_session("paper", 1_000_000)
        allowed, reason = engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=1_000_000,
            active_position_count=0,
        )
        assert allowed, f"湲곕낯 二쇰Ц 鍮꾩쑉(50%)???李⑤떒?섎㈃ ?덈맖: {reason}"


class TestDailyLossLimit:

    def test_daily_loss_exceeded_blocks_buy(self, strict_engine):
        strict_engine.initialize_session("paper", 10_000_000)
        # 2% 손실 한도, 10,000,000 × 0.02 = 200,000원 손실
        strict_engine.on_trade_result("paper", -250_000)  # 한도 초과
        allowed, reason = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=9_750_000,
            active_position_count=0,
        )
        assert not allowed
        assert "손실" in reason or "loss" in reason.lower()

    def test_daily_loss_within_limit_allows_buy(self, strict_engine):
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -100_000)  # 한도 이내
        allowed, _ = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=9_900_000,
            active_position_count=0,
        )
        assert allowed

    def test_profit_does_not_reset_daily_loss(self, strict_engine):
        """이익이 나도 당일 누적 손실은 그대로"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -300_000)  # 한도 초과 손실
        strict_engine.on_trade_result("paper", +500_000)  # 이익 발생
        status = strict_engine.get_status("paper")
        assert status["daily_pnl"] < 0  # 손실이 이익으로 상쇄되어도 누적 손실은 음수


# ─── 연속 손실 제한 ──────────────────────────────────────────────────

class TestConsecutiveLossLimit:

    def test_consecutive_losses_blocks_buy(self, strict_engine):
        """연속 3회 손실 후 매수 차단"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -10_000)
        strict_engine.on_trade_result("paper", -10_000)
        strict_engine.on_trade_result("paper", -10_000)

        allowed, reason = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=9_970_000,
            active_position_count=0,
        )
        assert not allowed
        assert "연속" in reason or "consecutive" in reason.lower()

    def test_profit_resets_consecutive_loss_count(self, strict_engine):
        """이익 거래가 연속 손실 카운터를 초기화"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -10_000)
        strict_engine.on_trade_result("paper", -10_000)
        strict_engine.on_trade_result("paper", +50_000)  # 이익 → 카운터 초기화
        strict_engine.on_trade_result("paper", -10_000)

        allowed, _ = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=500_000, total_portfolio_krw=10_020_000,
            active_position_count=0,
        )
        assert allowed


# ─── Circuit Breaker ─────────────────────────────────────────────────

class TestCircuitBreaker:

    def test_circuit_breaker_triggers_on_threshold(self, strict_engine):
        """5% 손실(=500,000원) 시 circuit breaker 발동"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -600_000)  # 6% 손실
        status = strict_engine.get_status("paper")
        assert status["circuit_breaker_triggered"]

    def test_circuit_breaker_blocks_all_buys(self, strict_engine):
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -600_000)

        allowed, reason = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=100_000, total_portfolio_krw=9_400_000,
            active_position_count=0,
        )
        assert not allowed
        assert "circuit" in reason.lower() or "차단" in reason

    def test_circuit_breaker_allows_sell(self, strict_engine):
        """Circuit breaker 발동 중에도 매도는 허용"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -600_000)

        allowed, _ = strict_engine.check_order_allowed(
            mode="paper", side="sell", market="KRW-BTC",
            invest_krw=0, total_portfolio_krw=9_400_000,
            active_position_count=1,
        )
        assert allowed

    def test_reset_circuit_breaker(self, strict_engine):
        """Circuit breaker 수동 해제"""
        strict_engine.initialize_session("paper", 10_000_000)
        strict_engine.on_trade_result("paper", -600_000)
        assert strict_engine.get_status("paper")["circuit_breaker_triggered"]

        strict_engine.reset_circuit_breaker("paper")
        assert not strict_engine.get_status("paper")["circuit_breaker_triggered"]

    def test_circuit_breaker_disabled(self):
        """circuit_breaker_enabled=False 시 발동 안 함"""
        config = RiskConfig(
            circuit_breaker_enabled=False,
            circuit_breaker_threshold=0.01,  # 1%로 낮춰도
        )
        engine = RiskEngine(config)
        engine.initialize_session("paper", 10_000_000)
        engine.on_trade_result("paper", -5_000_000)  # 50% 손실
        assert not engine.get_status("paper")["circuit_breaker_triggered"]


# ─── 최대 동시 포지션 ────────────────────────────────────────────────

class TestMaxSimultaneousPositions:

    def test_max_positions_blocks_buy(self, strict_engine):
        """최대 2개 포지션 초과 시 매수 차단"""
        strict_engine.initialize_session("paper", 10_000_000)
        allowed, reason = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-SOL",
            invest_krw=500_000, total_portfolio_krw=10_000_000,
            active_position_count=2,  # 이미 최대
        )
        assert not allowed
        assert "포지션" in reason or "position" in reason.lower()

    def test_exactly_at_max_blocks(self, strict_engine):
        strict_engine.initialize_session("paper", 10_000_000)
        allowed, _ = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-ETH",
            invest_krw=500_000, total_portfolio_krw=10_000_000,
            active_position_count=2,
        )
        assert not allowed


# ─── 자산 비중 제한 ──────────────────────────────────────────────────

class TestPositionWeight:

    def test_overweight_position_blocked(self, strict_engine):
        """30% 비중 초과 주문 차단"""
        strict_engine.initialize_session("paper", 10_000_000)
        allowed, reason = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=4_000_000,   # 40% 비중
            total_portfolio_krw=10_000_000,
            active_position_count=0,
        )
        assert not allowed
        assert "비중" in reason or "weight" in reason.lower()

    def test_within_weight_allowed(self, strict_engine):
        strict_engine.initialize_session("paper", 10_000_000)
        allowed, _ = strict_engine.check_order_allowed(
            mode="paper", side="buy", market="KRW-BTC",
            invest_krw=2_500_000,   # 25% 비중
            total_portfolio_krw=10_000_000,
            active_position_count=0,
        )
        assert allowed


# ─── get_all_status ──────────────────────────────────────────────────

class TestGetAllStatus:

    def test_get_all_status_empty(self, engine):
        result = engine.get_all_status()
        assert isinstance(result, dict)

    def test_get_all_status_multiple_modes(self, engine):
        engine.initialize_session("paper", 5_000_000)
        engine.initialize_session("live", 20_000_000)
        result = engine.get_all_status()
        assert "paper" in result
        assert "live" in result
