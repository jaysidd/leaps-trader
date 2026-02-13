"""Tests for shared scoring types."""
import pytest
from backend.app.services.scoring.types import (
    CriterionResult,
    CoverageInfo,
    GateConfig,
    StageResult,
    GATE_CONFIGS,
    compute_coverage_adjusted_score,
    build_coverage_from_criteria,
)


class TestCriterionResult:
    def test_values(self):
        assert CriterionResult.PASS == "PASS"
        assert CriterionResult.FAIL == "FAIL"
        assert CriterionResult.UNKNOWN == "UNKNOWN"

    def test_json_serializable(self):
        """CriterionResult is a str enum so it serializes to JSON strings."""
        import json
        data = {"criterion": CriterionResult.PASS}
        serialized = json.dumps(data)
        assert '"PASS"' in serialized


class TestCoverageInfo:
    def test_basic(self):
        c = CoverageInfo(known_count=4, pass_count=3, total_count=5)
        assert c.fail_count == 1
        assert c.unknown_count == 1

    def test_all_known_all_pass(self):
        c = CoverageInfo(known_count=5, pass_count=5, total_count=5)
        assert c.fail_count == 0
        assert c.unknown_count == 0

    def test_to_dict(self):
        c = CoverageInfo(known_count=4, pass_count=3, total_count=5)
        d = c.to_dict()
        assert d == {"known_count": 4, "pass_count": 3, "total_count": 5}


class TestComputeCoverageAdjustedScore:
    def test_full_coverage_full_points(self):
        """All known, all earned: should be 100."""
        pct, points, pct_raw = compute_coverage_adjusted_score(100, 100, 100)
        assert pct == 100.0
        assert points == 100.0
        assert pct_raw == 100.0

    def test_full_coverage_zero_points(self):
        """All known, none earned: should be 0."""
        pct, points, pct_raw = compute_coverage_adjusted_score(0, 100, 100)
        assert pct == 0.0
        assert points == 0.0
        assert pct_raw == 0.0

    def test_zero_known_max_returns_none(self):
        """No known metrics: should return None."""
        pct, points, pct_raw = compute_coverage_adjusted_score(0, 0, 100)
        assert pct is None
        assert points is None
        assert pct_raw is None

    def test_half_coverage_applies_penalty(self):
        """Half coverage should apply the 0.85 + 0.15*0.5 = 0.925 multiplier."""
        # 50 earned out of 50 known, 100 total
        pct, points, pct_raw = compute_coverage_adjusted_score(50, 50, 100)
        assert pct_raw == 100.0
        # pct = 100 * (0.85 + 0.15 * 0.5) = 100 * 0.925 = 92.5
        assert pct == pytest.approx(92.5)
        assert points == pytest.approx(92.5)

    def test_technical_scale_90(self):
        """Technical has total_max=90. Full points should give pct=100, points=90."""
        pct, points, pct_raw = compute_coverage_adjusted_score(90, 90, 90)
        assert pct == 100.0
        assert points == 90.0

    def test_clamped_to_100(self):
        """Score should never exceed 100."""
        pct, points, pct_raw = compute_coverage_adjusted_score(110, 100, 100)
        assert pct == 100.0

    def test_clamped_to_0(self):
        """Score should never go below 0."""
        pct, points, pct_raw = compute_coverage_adjusted_score(-10, 100, 100)
        assert pct == 0.0


class TestBuildCoverageFromCriteria:
    def test_mixed_criteria(self):
        criteria = {
            "a": CriterionResult.PASS,
            "b": CriterionResult.FAIL,
            "c": CriterionResult.UNKNOWN,
            "d": CriterionResult.PASS,
        }
        c = build_coverage_from_criteria(criteria)
        assert c.known_count == 3   # PASS + FAIL
        assert c.pass_count == 2    # PASS only
        assert c.total_count == 4

    def test_all_unknown(self):
        criteria = {
            "a": CriterionResult.UNKNOWN,
            "b": CriterionResult.UNKNOWN,
        }
        c = build_coverage_from_criteria(criteria)
        assert c.known_count == 0
        assert c.pass_count == 0
        assert c.total_count == 2


class TestStageResultPassesGate:
    def test_fundamental_gate_passes(self):
        """3 pass, 4 known out of 5: should pass."""
        sr = StageResult(
            stage_id="fundamental",
            criteria={
                "a": CriterionResult.PASS,
                "b": CriterionResult.PASS,
                "c": CriterionResult.PASS,
                "d": CriterionResult.FAIL,
                "e": CriterionResult.UNKNOWN,
            },
            coverage=CoverageInfo(known_count=4, pass_count=3, total_count=5),
        )
        assert sr.passes_gate(GATE_CONFIGS["fundamental"]) is True

    def test_fundamental_gate_fails_insufficient_pass(self):
        """2 pass, 4 known: not enough passes."""
        sr = StageResult(
            stage_id="fundamental",
            criteria={},
            coverage=CoverageInfo(known_count=4, pass_count=2, total_count=5),
        )
        assert sr.passes_gate(GATE_CONFIGS["fundamental"]) is False

    def test_fundamental_gate_fails_insufficient_known(self):
        """3 pass, 3 known: not enough known."""
        sr = StageResult(
            stage_id="fundamental",
            criteria={},
            coverage=CoverageInfo(known_count=3, pass_count=3, total_count=5),
        )
        assert sr.passes_gate(GATE_CONFIGS["fundamental"]) is False

    def test_technical_gate_passes(self):
        """3 pass, 6 known out of 7: should pass."""
        sr = StageResult(
            stage_id="technical",
            criteria={},
            coverage=CoverageInfo(known_count=6, pass_count=3, total_count=7),
        )
        assert sr.passes_gate(GATE_CONFIGS["technical"]) is True

    def test_options_gate_passes(self):
        """2 pass, 3 known out of 4: should pass."""
        sr = StageResult(
            stage_id="options",
            criteria={},
            coverage=CoverageInfo(known_count=3, pass_count=2, total_count=4),
        )
        assert sr.passes_gate(GATE_CONFIGS["options"]) is True


class TestGateConfigs:
    def test_fundamental_config(self):
        cfg = GATE_CONFIGS["fundamental"]
        assert cfg.min_pass == 3
        assert cfg.min_known == 4
        assert cfg.total == 5

    def test_technical_config(self):
        cfg = GATE_CONFIGS["technical"]
        assert cfg.min_pass == 3
        assert cfg.min_known == 6
        assert cfg.total == 7

    def test_options_config(self):
        cfg = GATE_CONFIGS["options"]
        assert cfg.min_pass == 2
        assert cfg.min_known == 3
        assert cfg.total == 4
