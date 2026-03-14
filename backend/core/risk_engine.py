"""
리스크 관리 엔진 — 전략 시그널과 주문 허용 여부 판단을 분리한다.

RiskEngine은 모드(paper/live)별로 독립 상태를 유지하며,
봇 루프에서 매수 시그널 발생 시 check_order_allowed()를 호출해 허용 여부를 결정한다.
매도 주문은 항상 허용된다 (포지션 청산 우선).
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    max_daily_loss_pct: float = 0.05          # 일일 손실 한도 (포트폴리오 대비 %)
    max_position_weight: float = 1.00          # 종목별 최대 비중
    max_consecutive_losses: int = 5            # 연속 손실 허용 횟수
    max_simultaneous_positions: int = 4        # 최대 동시 포지션 수
    circuit_breaker_enabled: bool = True       # circuit breaker 활성화
    circuit_breaker_threshold: float = 0.10   # circuit breaker 발동 손실 기준


@dataclass
class RiskState:
    initial_value: float = 0.0
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    circuit_breaker_triggered: bool = False
    session_date: str = ""


class RiskEngine:
    def __init__(self, config: Optional[RiskConfig] = None):
        self._config = config or RiskConfig()
        self._states: Dict[str, RiskState] = {}

    @property
    def config(self) -> RiskConfig:
        return self._config

    # ─── 세션 초기화 ────────────────────────────────────────────────
    def initialize_session(self, mode: str, total_portfolio_value: float) -> None:
        """봇 시작 시 호출. 모드별 상태를 초기화한다."""
        today = date.today().isoformat()
        state = self._states.get(mode)
        if state and state.session_date == today:
            # 당일 이미 초기화된 경우 portfolio 값만 갱신
            state.initial_value = total_portfolio_value
        else:
            self._states[mode] = RiskState(
                initial_value=total_portfolio_value,
                session_date=today,
            )
        logger.info("RiskEngine session initialized: mode=%s value=%.0f", mode, total_portfolio_value)

    # ─── 주문 허용 여부 판단 ────────────────────────────────────────
    def check_order_allowed(
        self,
        mode: str,
        side: str,
        market: str,
        invest_krw: float,
        total_portfolio_krw: float,
        active_position_count: int,
    ) -> Tuple[bool, str]:
        """매수/매도 주문 허용 여부를 반환한다.

        Returns:
            (True, "") → 허용
            (False, reason) → 거부
        """
        # 매도는 항상 허용 (청산 우선)
        if side == "sell":
            return True, ""

        state = self._states.get(mode)
        if state is None:
            return False, f"리스크 엔진 세션 미초기화 (mode={mode}). start_bot()을 먼저 호출하세요."

        cfg = self._config

        # 1. Circuit breaker
        if cfg.circuit_breaker_enabled and state.circuit_breaker_triggered:
            return False, "Circuit breaker 발동 — 당일 매수 차단. /api/risk/reset-circuit-breaker로 해제하세요."

        # 2. 일일 손실 한도
        if state.initial_value > 0:
            daily_loss_pct = abs(min(state.daily_pnl, 0)) / state.initial_value
            if daily_loss_pct >= cfg.max_daily_loss_pct:
                return False, (
                    f"일일 손실 한도 초과: {daily_loss_pct*100:.1f}% ≥ {cfg.max_daily_loss_pct*100:.0f}%"
                )

        # 3. 연속 손실 한도
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return False, (
                f"연속 손실 한도 초과: {state.consecutive_losses}회 ≥ {cfg.max_consecutive_losses}회"
            )

        # 4. 최대 동시 포지션 수
        if active_position_count >= cfg.max_simultaneous_positions:
            return False, (
                f"최대 동시 포지션 초과: {active_position_count} ≥ {cfg.max_simultaneous_positions}개"
            )

        # 5. 종목 비중 한도
        if total_portfolio_krw > 0:
            weight = invest_krw / total_portfolio_krw
            if weight > cfg.max_position_weight:
                return False, (
                    f"종목 비중 초과: {weight*100:.1f}% > {cfg.max_position_weight*100:.0f}%"
                )

        return True, ""

    # ─── 거래 결과 업데이트 ─────────────────────────────────────────
    def on_trade_result(self, mode: str, pnl: float) -> None:
        """매도 체결 후 호출. 손익에 따라 상태를 갱신한다."""
        state = self._states.get(mode)
        if state is None:
            return

        state.daily_pnl += pnl

        if pnl < 0:
            state.consecutive_losses += 1
        else:
            state.consecutive_losses = 0

        # Circuit breaker 체크
        cfg = self._config
        if cfg.circuit_breaker_enabled and state.initial_value > 0:
            total_loss_pct = abs(min(state.daily_pnl, 0)) / state.initial_value
            if total_loss_pct >= cfg.circuit_breaker_threshold and not state.circuit_breaker_triggered:
                state.circuit_breaker_triggered = True
                logger.warning(
                    "Circuit breaker triggered: mode=%s daily_loss=%.1f%%",
                    mode, total_loss_pct * 100,
                )

    # ─── Circuit breaker 해제 ───────────────────────────────────────
    def reset_circuit_breaker(self, mode: str) -> None:
        """Circuit breaker 수동 해제 (운영자 확인 후 호출)."""
        state = self._states.get(mode)
        if state:
            state.circuit_breaker_triggered = False
            logger.info("Circuit breaker reset: mode=%s", mode)

    # ─── 상태 조회 ──────────────────────────────────────────────────
    def get_status(self, mode: str) -> dict:
        state = self._states.get(mode)
        if state is None:
            return {"mode": mode, "initialized": False}
        cfg = self._config
        return {
            "mode": mode,
            "initialized": True,
            "initial_value": state.initial_value,
            "daily_pnl": round(state.daily_pnl, 0),
            "consecutive_losses": state.consecutive_losses,
            "circuit_breaker_triggered": state.circuit_breaker_triggered,
            "session_date": state.session_date,
            "config": {
                "max_daily_loss_pct": cfg.max_daily_loss_pct,
                "max_position_weight": cfg.max_position_weight,
                "max_consecutive_losses": cfg.max_consecutive_losses,
                "max_simultaneous_positions": cfg.max_simultaneous_positions,
                "circuit_breaker_enabled": cfg.circuit_breaker_enabled,
                "circuit_breaker_threshold": cfg.circuit_breaker_threshold,
            },
        }

    def get_state(self, mode: str) -> "Optional[RiskState]":
        """Raw RiskState 반환 (bot.py consecutive_losses 동기화용)."""
        return self._states.get(mode)

    def get_all_status(self) -> dict:
        return {mode: self.get_status(mode) for mode in self._states}


# ─── 스캘핑 전용 RiskConfig 프리셋 ──────────────────────────────
SCALPING_RISK_CONFIG = RiskConfig(
    max_daily_loss_pct=0.02,           # 일일 손실 한도 2%
    max_position_weight=0.50,
    max_consecutive_losses=3,          # 연속 3회 손절 시 중단
    max_simultaneous_positions=2,
    circuit_breaker_enabled=True,
    circuit_breaker_threshold=0.03,    # 3% 손실 시 circuit breaker 발동
)


# ─── 싱글턴 ───────────────────────────────────────────────────────
_risk_engine: Optional[RiskEngine] = None


def get_risk_engine() -> RiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
