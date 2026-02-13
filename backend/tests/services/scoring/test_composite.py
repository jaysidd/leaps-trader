"""Tests for composite score v1 _calculate_composite_score_v1()."""
import pytest
from unittest.mock import patch
from backend.app.services.screening.engine import ScreeningEngine
from backend.app.services.scoring.types import StageResult, CoverageInfo


@pytest.fixture
def engine():
    with patch('backend.app.services.screening.engine.get_sentiment_analyzer'), \
         patch('backend.app.services.screening.engine.get_catalyst_service'):
        return ScreeningEngine()


def _stage(stage_id, score_pct, score_points, total_max):
    return StageResult(
        stage_id=stage_id,
        criteria={},
        coverage=CoverageInfo(0, 0, 0),
        score_pct=score_pct,
        score_points=score_points,
        points_total_max=total_max,
    )


def _unknown_stage(stage_id, total_max):
    return StageResult(
        stage_id=stage_id,
        criteria={},
        coverage=CoverageInfo(0, 0, 0),
        points_total_max=total_max,
    )


class TestCompositeRescaling:
    def test_perfect_scores_no_sentiment(self, engine):
        """Perfect scores should rescale to exactly 100."""
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _stage("technical", 100, 90, 90),   # max points = 90
            _stage("options", 100, 100, 100),
            _stage("momentum", 100, 100, 100),
        )
        # raw = 0.40*100 + 0.30*90 + 0.20*100 + 0.10*100 = 97
        # final = 97 * (100/97) = 100.0
        assert result['score'] == 100.0

    def test_perfect_scores_with_sentiment(self, engine):
        """Perfect scores with sentiment should rescale to exactly 100."""
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _stage("technical", 100, 90, 90),
            _stage("options", 100, 100, 100),
            _stage("momentum", 100, 100, 100),
            sentiment_score=100.0,
        )
        # raw = 0.35*100 + 0.25*90 + 0.15*100 + 0.10*100 + 0.15*100 = 97.5
        # final = 97.5 * (100/97.5) = 100.0
        assert result['score'] == 100.0

    def test_zero_scores_no_sentiment(self, engine):
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 0, 0, 100),
            _stage("technical", 0, 0, 90),
            _stage("options", 0, 0, 100),
            _stage("momentum", 0, 0, 100),
        )
        assert result['score'] == 0.0

    def test_example_from_spec(self, engine):
        """F=75, T=60 (of 90), O=80, M=50 → raw=69, scaled=71.13."""
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 75, 75, 100),
            _stage("technical", None, 60, 90),   # 60 points of 90
            _stage("options", 80, 80, 100),
            _stage("momentum", 50, 50, 100),
        )
        # raw = 0.40*75 + 0.30*60 + 0.20*80 + 0.10*50 = 30+18+16+5 = 69
        # final = 69 * (100/97) ≈ 71.13
        assert result['score'] == pytest.approx(71.13, abs=0.01)


class TestCompositeUnknownNeutral:
    def test_unknown_component_uses_scale_aware_neutral(self, engine):
        """UNKNOWN technical uses neutral = 0.5 * 90 = 45, not 50."""
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _unknown_stage("technical", 90),       # UNKNOWN → 45 points
            _stage("options", 100, 100, 100),
            _stage("momentum", 100, 100, 100),
        )
        # raw = 0.40*100 + 0.30*45 + 0.20*100 + 0.10*100 = 40+13.5+20+10 = 83.5
        # final = 83.5 * (100/97) ≈ 86.08
        assert result['score'] == pytest.approx(86.08, abs=0.01)
        assert result['component_availability']['technical_available'] is False
        assert result['component_availability']['fundamental_available'] is True

    def test_all_unknown_gives_neutral_score(self, engine):
        """All UNKNOWN → all neutral (F=50,T=45,O=50,M=50)."""
        result = engine._calculate_composite_score_v1(
            _unknown_stage("fundamental", 100),
            _unknown_stage("technical", 90),
            _unknown_stage("options", 100),
            _unknown_stage("momentum", 100),
        )
        # raw = 0.40*50 + 0.30*45 + 0.20*50 + 0.10*50 = 20+13.5+10+5 = 48.5
        # final = 48.5 * (100/97) ≈ 50.0
        assert result['score'] == pytest.approx(50.0, abs=0.01)

    def test_availability_flags(self, engine):
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _unknown_stage("technical", 90),
            _stage("options", 100, 100, 100),
            _unknown_stage("momentum", 100),
        )
        assert result['component_availability']['fundamental_available'] is True
        assert result['component_availability']['technical_available'] is False
        assert result['component_availability']['options_available'] is True
        assert result['component_availability']['momentum_available'] is False


class TestCompositeSentimentMissing:
    def test_sentiment_mode_true_score_none_uses_sentiment_weights(self, engine):
        """D1: sentiment_mode=True but score=None → with-sent weights, S=50."""
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _stage("technical", 100, 90, 90),
            _stage("options", 100, 100, 100),
            _stage("momentum", 100, 100, 100),
            sentiment_score=None,
            sentiment_mode=True,
        )
        # raw = 0.35*100 + 0.25*90 + 0.15*100 + 0.10*100 + 0.15*50
        # = 35 + 22.5 + 15 + 10 + 7.5 = 90
        # final = 90 * (100/97.5) ≈ 92.31
        assert result['score'] == pytest.approx(92.31, abs=0.01)
        assert result['component_availability']['sentiment_available'] is False

    def test_sentiment_score_provided(self, engine):
        result = engine._calculate_composite_score_v1(
            _stage("fundamental", 100, 100, 100),
            _stage("technical", 100, 90, 90),
            _stage("options", 100, 100, 100),
            _stage("momentum", 100, 100, 100),
            sentiment_score=80.0,
        )
        # raw = 0.35*100 + 0.25*90 + 0.15*100 + 0.10*100 + 0.15*80
        # = 35 + 22.5 + 15 + 10 + 12 = 94.5
        # final = 94.5 * (100/97.5) ≈ 96.92
        assert result['score'] == pytest.approx(96.92, abs=0.01)
        assert result['component_availability']['sentiment_available'] is True
