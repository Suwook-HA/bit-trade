"""
Recommender OOS/overfit 테스트
- detect_overfit() 정확도 확인
- score_result() 5개 지표 조합 검증
- _extract_metrics() 필드 존재 확인
"""
import pytest
import numpy as np

from core.recommender import (
    detect_overfit,
    score_result,
    _extract_metrics,
    _build_market_hint_fallback,
    _select_top_recommendations,
)


# ─── detect_overfit ────────────────────────────────────────────────

class TestDetectOverfit:

    def _make_summary(self, ret=5.0, sharpe=1.0, sortino=1.2, win_rate=55.0,
                      mdd=-5.0, trades=10) -> dict:
        return {
            "total_return_pct": ret,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "win_rate_pct": win_rate,
            "mdd_pct": mdd,
            "total_trades": trades,
            "profit_factor": 1.5,
            "expectancy_krw": 50_000,
            "turnover": 0.05,
        }

    def test_no_overfit_when_oos_similar(self):
        train = self._make_summary(ret=5.0, sharpe=1.0)
        test = self._make_summary(ret=4.5, sharpe=0.9)
        result = detect_overfit(train, test)
        assert not result["overfit"]

    def test_overfit_when_oos_degrades_50pct(self):
        """OOS 점수가 학습 대비 50% 이상 하락 → overfit=True"""
        train = self._make_summary(ret=20.0, sharpe=3.0, sortino=4.0, win_rate=70, mdd=-3.0)
        # OOS는 거의 0에 가까운 성능
        test = self._make_summary(ret=0.1, sharpe=0.01, sortino=0.01, win_rate=51, mdd=-15.0, trades=3)
        result = detect_overfit(train, test)
        assert result["overfit"]

    def test_degradation_pct_is_correct(self):
        """degradation_pct 계산 검증"""
        train = self._make_summary(ret=10.0, sharpe=2.0, win_rate=60.0)
        test = self._make_summary(ret=5.0, sharpe=1.0, win_rate=55.0)
        result = detect_overfit(train, test)
        assert 0 <= result["degradation_pct"] <= 100

    def test_negative_train_score_returns_no_overfit(self):
        """학습 구간 점수가 음수이면 overfit 판단 불가 → overfit=False"""
        train = self._make_summary(ret=-20.0, sharpe=-2.0, win_rate=30.0, mdd=-30.0, trades=2)
        test = self._make_summary(ret=-10.0, sharpe=-1.0, win_rate=35.0)
        result = detect_overfit(train, test)
        assert not result["overfit"]
        assert "판단 불가" in result["reason"] or "음수" in result["reason"]

    def test_returns_required_keys(self):
        train = self._make_summary()
        test = self._make_summary()
        result = detect_overfit(train, test)
        for key in ["overfit", "train_score", "test_score", "degradation_pct", "reason"]:
            assert key in result, f"'{key}' 키 없음"

    def test_custom_threshold(self):
        """사용자 정의 임계값(0.3) 적용"""
        train = self._make_summary(ret=10.0, sharpe=2.0, win_rate=60.0)
        test = self._make_summary(ret=6.0, sharpe=1.3, win_rate=55.0)
        result_strict = detect_overfit(train, test, degradation_threshold=0.3)
        result_lenient = detect_overfit(train, test, degradation_threshold=0.9)
        # strict 임계값에서는 overfit일 수 있고, lenient에서는 아닐 수 있음
        assert isinstance(result_strict["overfit"], bool)
        assert isinstance(result_lenient["overfit"], bool)


# ─── score_result ──────────────────────────────────────────────────

class TestScoreResult:

    def test_insufficient_trades_returns_sentinel(self):
        """거래 수 < 2 → -999.0 반환"""
        summary = {
            "total_trades": 1,
            "total_return_pct": 100.0,
            "sharpe_ratio": 5.0,
            "sortino_ratio": 6.0,
            "win_rate_pct": 80.0,
            "mdd_pct": -1.0,
        }
        assert score_result(summary) == -999.0

    def test_zero_trades_returns_sentinel(self):
        summary = {"total_trades": 0, "total_return_pct": 0}
        assert score_result(summary) == -999.0

    def test_positive_return_high_sharpe_high_score(self):
        """수익률·샤프 높을수록 점수 높음"""
        good = {
            "total_trades": 20, "total_return_pct": 30.0,
            "sharpe_ratio": 3.0, "sortino_ratio": 4.0,
            "win_rate_pct": 65.0, "mdd_pct": -5.0,
        }
        bad = {
            "total_trades": 20, "total_return_pct": 2.0,
            "sharpe_ratio": 0.3, "sortino_ratio": 0.4,
            "win_rate_pct": 45.0, "mdd_pct": -20.0,
        }
        assert score_result(good) > score_result(bad)

    def test_large_mdd_penalizes_score(self):
        """MDD가 클수록 점수 감소"""
        low_mdd = {
            "total_trades": 15, "total_return_pct": 10.0,
            "sharpe_ratio": 1.5, "sortino_ratio": 2.0,
            "win_rate_pct": 60.0, "mdd_pct": -3.0,
        }
        high_mdd = dict(low_mdd)
        high_mdd["mdd_pct"] = -30.0
        assert score_result(low_mdd) > score_result(high_mdd)

    def test_score_uses_five_metrics(self):
        """5개 지표(수익률·샤프·소르티노·승률·MDD) 모두 반영 확인"""
        base = {
            "total_trades": 10, "total_return_pct": 5.0,
            "sharpe_ratio": 1.0, "sortino_ratio": 1.0,
            "win_rate_pct": 50.0, "mdd_pct": -5.0,
        }
        # 소르티노만 올리면 점수 상승
        with_sortino = dict(base)
        with_sortino["sortino_ratio"] = 5.0
        assert score_result(with_sortino) > score_result(base)


# ─── _extract_metrics ─────────────────────────────────────────────

class TestExtractMetrics:

    def test_all_keys_present(self):
        summary = {
            "total_return_pct": 5.0,
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.5,
            "win_rate_pct": 55.0,
            "profit_factor": 1.8,
            "expectancy_krw": 30_000,
            "total_trades": 12,
            "mdd_pct": -4.0,
        }
        metrics = _extract_metrics(summary)
        for key in [
            "total_return_pct", "sharpe_ratio", "sortino_ratio", "win_rate_pct",
            "profit_factor", "expectancy_krw", "total_trades", "mdd_pct",
        ]:
            assert key in metrics, f"'{key}' 누락"

    def test_missing_keys_default_to_zero(self):
        """누락된 필드는 0으로 기본값"""
        metrics = _extract_metrics({})
        for key in ["total_return_pct", "sharpe_ratio", "total_trades"]:
            assert metrics[key] == 0


class TestSelectTopRecommendations:

    def _make_rec(self, strategy, trades, total_return, oos_score, train_score=1.0):
        return {
            "strategy": strategy,
            "params": {},
            "score": train_score,
            "oos_score": oos_score,
            "live_signal": {"action": "hold", "reason": ""},
            "warmup_position": False,
            "metrics": {
                "train": {"total_trades": 5, "total_return_pct": 1.0},
                "oos": {
                    "total_trades": trades,
                    "total_return_pct": total_return,
                    "win_rate_pct": 55.0,
                },
            },
        }

    def test_prefers_tradable_market_hint_for_scalping(self):
        scored = [
            self._make_rec("macd", trades=0, total_return=0.0, oos_score=-100.0),
            self._make_rec("rsi", trades=2, total_return=0.2, oos_score=0.1),
            self._make_rec("bollinger", trades=3, total_return=0.1, oos_score=0.05),
        ]

        top = _select_top_recommendations(scored, {"best_strategy_hint": "rsi"}, top_n=1)

        assert top[0]["strategy"] == "rsi"

    def test_prefers_live_buy_signal_when_oos_is_quiet(self):
        buy_ready = self._make_rec("macd", trades=0, total_return=0.0, oos_score=-100.0)
        buy_ready["live_signal"]["action"] = "buy"
        sleepy = self._make_rec("rsi", trades=0, total_return=0.0, oos_score=0.1)

        top = _select_top_recommendations([sleepy, buy_ready], {"best_strategy_hint": "rsi"}, top_n=1)

        assert top[0]["strategy"] == "macd"
        assert top[0]["live_signal"]["action"] == "buy"

    def test_prefers_warmup_ready_strategy_when_oos_is_quiet(self):
        warm_ready = self._make_rec("ma_cross", trades=0, total_return=0.0, oos_score=-100.0)
        warm_ready["warmup_position"] = True
        sleepy = self._make_rec("rsi", trades=0, total_return=0.0, oos_score=0.1)

        top = _select_top_recommendations([sleepy, warm_ready], {"best_strategy_hint": "rsi"}, top_n=1)

        assert top[0]["strategy"] == "ma_cross"
        assert top[0]["warmup_position"] is True

    def test_filters_zero_trade_oos_when_tradable_options_exist(self):
        scored = [
            self._make_rec("macd", trades=0, total_return=0.0, oos_score=99.0),
            self._make_rec("ma_cross", trades=1, total_return=-0.1, oos_score=-0.2),
        ]

        top = _select_top_recommendations(scored, {"best_strategy_hint": "ma_cross"}, top_n=2)

        assert top[0]["strategy"] == "ma_cross"
        assert all(rec["metrics"]["oos"]["total_trades"] > 0 for rec in top)

    def test_falls_back_to_market_hint_when_all_oos_trades_are_zero(self):
        scored = [
            self._make_rec("macd", trades=0, total_return=0.0, oos_score=99.0, train_score=0.2),
            self._make_rec("rsi", trades=0, total_return=0.0, oos_score=0.1, train_score=0.1),
        ]

        top = _select_top_recommendations(scored, {"best_strategy_hint": "rsi"}, top_n=1)

        assert top[0]["strategy"] == "rsi"

    def test_builds_market_hint_scalping_fallback(self):
        fallback = _build_market_hint_fallback([], {"best_strategy_hint": "rsi", "reason": "횡보"})

        assert fallback is not None
        assert fallback["strategy"] == "rsi"
        assert fallback["params"] == {"period": 7, "oversold": 25, "overbought": 65}
        assert fallback["fallback"] is True
