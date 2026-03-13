"""
리스크 관리 엔진 — 전략 신호와 독립적으로 주문 허용 여부를 결정.

FR-03 구현:
- 일일 최대 손실 한도
- 자산별 최대 비중
- 연속 손실 제한
- 최대 동시 포지션 수
- 계정 단위 circuit breaker
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """리스크 파라미터 설정"""
    max_daily_loss_pct: float = 0.05       # 일일 최대 손실 5%
    max_position_weight: float = 0.40      # 단일 자산 최대 비중 40%
    max_consecutive_losses: int = 5        # 연속 손실 허용 횟수
    max_simultaneous_positions: int = 4    # 최대 동시 포지션 수
    circuit_breaker_enabled: bool = True   # circuit breaker 활성화
    circuit_breaker_threshold: float = 0.10  # 발동 손실률 10%


@dataclass
class RiskState:
    """일별/세션별 리스크 추적 상태"""
    daily_pnl: float = 0.0
    daily_pnl_date: str = ""              # "YYYY-MM-DD"
    consecutive_losses: int = 0
    circuit_breaker_triggered: bool = False
    initial_portfolio_value: float = 0.0  # 세션 시작 포트폴리오 가치


class RiskEngine:
    """
    전략 신호와 독립적으로 주문 허용 여부를 판단하는 리스크 엔진.
    mode("paper" | "live") 단위로 상태를 관리한다.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self._states: Dict[str, RiskState] = {}

    def get_state(self, mode: str) -> RiskState:
        if mode not in self._states:
            self._states[mode] = RiskState()
        return self._states[mode]

    def initialize_session(self, mode: str, total_portfolio_value: float) -> None:
        """봇 시작 시 세션 초기화. circuit breaker 기준값 설정."""
        state = self.get_state(mode)
        state.initial_portfolio_value = total_portfolio_value
        state.circuit_breaker_triggered = False
        today = str(date.today())
        if state.daily_pnl_date != today:
            state.daily_pnl = 0.0
            state.daily_pnl_date = today
        logger.info(
            "RiskEngine session initialized: mode=%s, portfolio=%.0f", mode, total_portfolio_value
        )

    def check_order_allowed(
        self,
        mode: str,
        side: str,               # 'buy' | 'sell'
        market: str,
        invest_krw: float,
        total_portfolio_krw: float,
        active_position_count: int,
    ) -> Tuple[bool, str]:
        """
        주문 허용 여부 판단.
        sell 주문은 항상 허용 (포지션 청산은 리스크 규칙 우선).
        반환: (allowed: bool, reason: str)
        """
        # sell은 항상 허용
        if side == "sell":
            return True, "OK"

        state = self.get_state(mode)
        cfg = self.config

        # 1. circuit breaker 체크
        if cfg.circuit_breaker_enabled and state.circuit_breaker_triggered:
            return False, "Circuit breaker triggered — bot halted until manual reset"

        # 2. 일일 최대 손실 체크
        if total_portfolio_krw > 0 and state.daily_pnl < 0:
            daily_loss_pct = -state.daily_pnl / max(total_portfolio_krw, 1)
            if daily_loss_pct >= cfg.max_daily_loss_pct:
                return False, (
                    f"Daily loss limit reached: "
                    f"{daily_loss_pct * 100:.1f}% >= {cfg.max_daily_loss_pct * 100:.1f}%"
                )

        # 3. 단일 자산 최대 비중 체크
        if total_portfolio_krw > 0 and invest_krw > 0:
            weight = invest_krw / total_portfolio_krw
            if weight > cfg.max_position_weight:
                return False, (
                    f"Position weight too large: "
                    f"{weight * 100:.1f}% > {cfg.max_position_weight * 100:.1f}%"
                )

        # 4. 연속 손실 제한 체크
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return False, (
                f"Consecutive losses limit: "
                f"{state.consecutive_losses} >= {cfg.max_consecutive_losses}"
            )

        # 5. 최대 동시 포지션 체크
        if active_position_count >= cfg.max_simultaneous_positions:
            return False, (
                f"Max simultaneous positions reached: "
                f"{active_position_count} >= {cfg.max_simultaneous_positions}"
            )

        return True, "OK"

    def on_trade_result(self, mode: str, pnl: float) -> None:
        """
        거래 완료 후 리스크 상태 업데이트.
        pnl > 0: 이익, pnl < 0: 손실
        """
        state = self.get_state(mode)
        cfg = self.config

        # 일별 PnL (날짜 바뀌면 초기화)
        today = str(date.today())
        if state.daily_pnl_date != today:
            state.daily_pnl = 0.0
            state.daily_pnl_date = today
        state.daily_pnl += pnl

        # 연속 손실 카운터
        if pnl < 0:
            state.consecutive_losses += 1
            logger.debug("Consecutive losses: %d", state.consecutive_losses)
        else:
            state.consecutive_losses = 0

        # circuit breaker 평가
        if cfg.circuit_breaker_enabled and state.initial_portfolio_value > 0:
            total_loss_pct = -state.daily_pnl / state.initial_portfolio_value
            if total_loss_pct >= cfg.circuit_breaker_threshold:
                if not state.circuit_breaker_triggered:
                    state.circuit_breaker_triggered = True
                    logger.warning(
                        "⚠️ Circuit breaker triggered! Daily loss: %.1f%%",
                        total_loss_pct * 100,
                    )

    def reset_circuit_breaker(self, mode: str) -> None:
        """수동 circuit breaker 해제."""
        state = self.get_state(mode)
        state.circuit_breaker_triggered = False
        logger.info("Circuit breaker reset for mode=%s", mode)

    def get_status(self, mode: str) -> dict:
        """현재 리스크 상태 조회."""
        state = self.get_state(mode)
        cfg = self.config
        return {
            "daily_pnl": round(state.daily_pnl, 0),
            "consecutive_losses": state.consecutive_losses,
            "circuit_breaker_triggered": state.circuit_breaker_triggered,
            "config": {
                "max_daily_loss_pct": cfg.max_daily_loss_pct,
                "max_position_weight": cfg.max_position_weight,
                "max_consecutive_losses": cfg.max_consecutive_losses,
                "max_simultaneous_positions": cfg.max_simultaneous_positions,
                "circuit_breaker_enabled": cfg.circuit_breaker_enabled,
                "circuit_breaker_threshold": cfg.circuit_breaker_threshold,
            },
        }

    def get_all_status(self) -> dict:
        """모든 mode의 리스크 상태 반환."""
        return {mode: self.get_status(mode) for mode in self._states}


# ── 전역 싱글턴 ──────────────────────────────────────────────────
_risk_engine: RiskEngine = RiskEngine()


def get_risk_engine() -> RiskEngine:
    return _risk_engine
