"""Tests for momentum v1 _evaluate_momentum()."""
import pytest
from unittest.mock import patch
from backend.app.services.screening.engine import ScreeningEngine
from backend.app.services.scoring.types import CriterionResult


@pytest.fixture
def engine():
    with patch('backend.app.services.screening.engine.get_sentiment_analyzer'), \
         patch('backend.app.services.screening.engine.get_catalyst_service'):
        return ScreeningEngine()


class TestMomentumBaseScoring:
    def test_perfect_returns(self, engine):
        result = engine._evaluate_momentum({
            'return_1m': 0.20,   # >0.15 → 30
            'return_3m': 0.35,   # >0.30 → 30
            'return_1y': 0.55,   # >0.50 → 40
        })
        assert result.points_earned == 100.0
        assert result.score_pct == 100.0

    def test_zero_returns(self, engine):
        result = engine._evaluate_momentum({
            'return_1m': 0.01,
            'return_3m': 0.05,
            'return_1y': 0.05,
        })
        assert result.points_earned == 0.0
        assert result.score_pct == 0.0


class TestMomentumDrawdownPenalties:
    def test_1m_severe_penalty(self, engine):
        """1M < -10% → -15 penalty."""
        result = engine._evaluate_momentum({
            'return_1m': -0.12,  # base=0, penalty=15
            'return_3m': 0.01,
            'return_1y': 0.01,
        })
        assert result.points_earned == 0.0  # clamped at 0

    def test_1m_moderate_penalty(self, engine):
        """1M < -5% → -10 penalty."""
        result = engine._evaluate_momentum({
            'return_1m': -0.07,  # base=0, penalty=10
            'return_3m': 0.25,   # base=20
            'return_1y': 0.35,   # base=25
        })
        # base = 0+20+25 = 45, penalty = 10, earned = 35
        assert result.points_earned == 35.0

    def test_3m_severe_penalty(self, engine):
        """3M < -20% → -15 penalty."""
        result = engine._evaluate_momentum({
            'return_1m': 0.01,
            'return_3m': -0.25,
            'return_1y': 0.01,
        })
        assert result.points_earned == 0.0

    def test_1y_severe_penalty(self, engine):
        """1Y < -30% → -20 penalty."""
        result = engine._evaluate_momentum({
            'return_1m': 0.06,   # +10
            'return_3m': 0.12,   # +10
            'return_1y': -0.35,  # base=0, penalty=20
        })
        # base = 10+10+0 = 20, penalty = 20, earned = 0
        assert result.points_earned == 0.0

    def test_combined_penalties_clamp_at_zero(self, engine):
        """Multiple penalties should clamp at 0, not go negative."""
        result = engine._evaluate_momentum({
            'return_1m': -0.15,   # penalty=15
            'return_3m': -0.25,   # penalty=15
            'return_1y': -0.35,   # penalty=20
        })
        # base=0, penalties=50, earned = max(0, 0-50) = 0
        assert result.points_earned == 0.0
        assert result.score_pct == 0.0


class TestMomentumCoverage:
    def test_missing_1y_is_unknown(self, engine):
        result = engine._evaluate_momentum({
            'return_1m': 0.10,
            'return_3m': 0.20,
            # return_1y missing
        })
        assert result.criteria['return_1y_available'] == CriterionResult.UNKNOWN
        assert result.criteria['return_1m_available'] == CriterionResult.PASS
        # points_known_max should be 60 (30+30), not 100
        assert result.points_known_max == 60.0

    def test_all_missing_returns_none_score(self, engine):
        result = engine._evaluate_momentum({})
        assert result.score_pct is None
        assert result.score_points is None
        assert result.coverage.known_count == 0

    def test_total_max_is_100(self, engine):
        result = engine._evaluate_momentum({'return_1m': 0.10})
        assert result.points_total_max == 100.0
