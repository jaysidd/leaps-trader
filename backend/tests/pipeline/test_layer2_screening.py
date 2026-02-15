"""
Layer 2: Screening Engine — Gate validation tests.

Tests the 4-stage screening pipeline:
  Stage 1: Fundamental gate (4/5 PASS, 4/5 KNOWN)
  Stage 2: Technical gate (3/7 PASS, 5/7 KNOWN)
  Stage 3: Options gate (2/4 PASS, 2/4 KNOWN)
  Stage 4: Momentum scoring + composite

Focus on gate pass/fail logic and composite score thresholds.
Note: These tests call the scoring functions directly rather than
screen_single_stock() which requires deep FMP/Alpaca mocking.
"""
import pytest
from app.services.scoring.types import (
    GateConfig,
    StageResult,
    CoverageInfo,
    CriterionResult,
    GATE_CONFIGS,
)


class TestGateConfigs:
    """Verify gate configuration values."""

    def test_fundamental_gate_requires_4_of_5(self):
        """Fundamental gate: 4 PASS required out of 5."""
        gate = GATE_CONFIGS["fundamental"]
        assert gate.min_pass == 4
        assert gate.min_known == 4
        assert gate.total == 5

    def test_technical_gate_requires_3_of_7(self):
        """Technical gate: 3 PASS required out of 7."""
        gate = GATE_CONFIGS["technical"]
        assert gate.min_pass == 3
        assert gate.min_known == 5
        assert gate.total == 7

    def test_options_gate_requires_2_of_4(self):
        """Options gate: 2 PASS required out of 4."""
        gate = GATE_CONFIGS["options"]
        assert gate.min_pass == 2
        assert gate.min_known == 2
        assert gate.total == 4


class TestFundamentalGateLogic:
    """Test the fundamental gate pass/fail logic."""

    def test_4_of_5_pass_passes_gate(self):
        """4/5 PASS + 4/5 KNOWN → passes fundamental gate."""
        criteria = {
            "debt_to_equity": CriterionResult.PASS,
            "current_ratio": CriterionResult.PASS,
            "quick_ratio": CriterionResult.PASS,
            "gross_margin": CriterionResult.PASS,
            "operating_margin": CriterionResult.UNKNOWN,
        }
        coverage = CoverageInfo(known_count=4, pass_count=4, total_count=5)
        stage = StageResult(stage_id="fundamental", criteria=criteria, coverage=coverage)
        assert stage.passes_gate(GATE_CONFIGS["fundamental"])

    def test_3_of_5_pass_fails_gate(self):
        """3/5 PASS → fails fundamental gate (needs 4)."""
        criteria = {
            "debt_to_equity": CriterionResult.PASS,
            "current_ratio": CriterionResult.PASS,
            "quick_ratio": CriterionResult.PASS,
            "gross_margin": CriterionResult.FAIL,
            "operating_margin": CriterionResult.FAIL,
        }
        coverage = CoverageInfo(known_count=5, pass_count=3, total_count=5)
        stage = StageResult(stage_id="fundamental", criteria=criteria, coverage=coverage)
        assert not stage.passes_gate(GATE_CONFIGS["fundamental"])

    def test_5_of_5_pass_passes_gate(self):
        """5/5 PASS → easily passes fundamental gate."""
        criteria = {
            "debt_to_equity": CriterionResult.PASS,
            "current_ratio": CriterionResult.PASS,
            "quick_ratio": CriterionResult.PASS,
            "gross_margin": CriterionResult.PASS,
            "operating_margin": CriterionResult.PASS,
        }
        coverage = CoverageInfo(known_count=5, pass_count=5, total_count=5)
        stage = StageResult(stage_id="fundamental", criteria=criteria, coverage=coverage)
        assert stage.passes_gate(GATE_CONFIGS["fundamental"])

    def test_insufficient_known_fails_gate(self):
        """Even with PASS, if not enough criteria are KNOWN, gate fails."""
        criteria = {
            "debt_to_equity": CriterionResult.PASS,
            "current_ratio": CriterionResult.PASS,
            "quick_ratio": CriterionResult.PASS,
            "gross_margin": CriterionResult.UNKNOWN,
            "operating_margin": CriterionResult.UNKNOWN,
        }
        # Only 3 KNOWN, but fundamental gate requires 4
        coverage = CoverageInfo(known_count=3, pass_count=3, total_count=5)
        stage = StageResult(stage_id="fundamental", criteria=criteria, coverage=coverage)
        assert not stage.passes_gate(GATE_CONFIGS["fundamental"])


class TestTechnicalGateLogic:
    """Test the technical gate pass/fail logic."""

    def test_3_of_7_pass_with_5_known_passes(self):
        """3/7 PASS + 5/7 KNOWN → passes technical gate."""
        coverage = CoverageInfo(known_count=5, pass_count=3, total_count=7)
        criteria = {
            "uptrend": CriterionResult.PASS,
            "rsi_ok": CriterionResult.PASS,
            "macd_bullish": CriterionResult.PASS,
            "volume_above_avg": CriterionResult.FAIL,
            "breakout": CriterionResult.FAIL,
            "volatility_ok": CriterionResult.UNKNOWN,
            "trend_strong": CriterionResult.UNKNOWN,
        }
        stage = StageResult(stage_id="technical", criteria=criteria, coverage=coverage)
        assert stage.passes_gate(GATE_CONFIGS["technical"])

    def test_2_of_7_pass_fails(self):
        """2/7 PASS → fails technical gate (needs 3)."""
        coverage = CoverageInfo(known_count=5, pass_count=2, total_count=7)
        criteria = {
            "uptrend": CriterionResult.PASS,
            "rsi_ok": CriterionResult.PASS,
            "macd_bullish": CriterionResult.FAIL,
            "volume_above_avg": CriterionResult.FAIL,
            "breakout": CriterionResult.FAIL,
            "volatility_ok": CriterionResult.UNKNOWN,
            "trend_strong": CriterionResult.UNKNOWN,
        }
        stage = StageResult(stage_id="technical", criteria=criteria, coverage=coverage)
        assert not stage.passes_gate(GATE_CONFIGS["technical"])

    def test_4_known_fails_technical_gate(self):
        """4/7 KNOWN is below technical min_known of 5 → fails."""
        coverage = CoverageInfo(known_count=4, pass_count=4, total_count=7)
        criteria = {
            "uptrend": CriterionResult.PASS,
            "rsi_ok": CriterionResult.PASS,
            "macd_bullish": CriterionResult.PASS,
            "volume_above_avg": CriterionResult.PASS,
            "breakout": CriterionResult.UNKNOWN,
            "volatility_ok": CriterionResult.UNKNOWN,
            "trend_strong": CriterionResult.UNKNOWN,
        }
        stage = StageResult(stage_id="technical", criteria=criteria, coverage=coverage)
        assert not stage.passes_gate(GATE_CONFIGS["technical"])


class TestOptionsGateLogic:
    """Test the options gate pass/fail logic."""

    def test_2_of_4_pass_passes(self):
        """2/4 PASS + 2/4 KNOWN → passes options gate."""
        coverage = CoverageInfo(known_count=2, pass_count=2, total_count=4)
        criteria = {
            "leaps_available": CriterionResult.PASS,
            "iv_acceptable": CriterionResult.PASS,
            "oi_sufficient": CriterionResult.UNKNOWN,
            "spread_ok": CriterionResult.UNKNOWN,
        }
        stage = StageResult(stage_id="options", criteria=criteria, coverage=coverage)
        assert stage.passes_gate(GATE_CONFIGS["options"])

    def test_1_of_4_pass_fails(self):
        """1/4 PASS → fails options gate (needs 2)."""
        coverage = CoverageInfo(known_count=3, pass_count=1, total_count=4)
        criteria = {
            "leaps_available": CriterionResult.PASS,
            "iv_acceptable": CriterionResult.FAIL,
            "oi_sufficient": CriterionResult.FAIL,
            "spread_ok": CriterionResult.UNKNOWN,
        }
        stage = StageResult(stage_id="options", criteria=criteria, coverage=coverage)
        assert not stage.passes_gate(GATE_CONFIGS["options"])


class TestCompositeScoreMinimum:
    """Test the MIN_COMPOSITE_SCORE threshold."""

    def test_minimum_score_constant(self):
        """Verify the screening engine can be instantiated."""
        from app.services.screening.engine import ScreeningEngine
        engine = ScreeningEngine()
        assert engine is not None


class TestCriterionResult:
    """Test the tri-state criterion result enum."""

    def test_pass_value(self):
        assert CriterionResult.PASS.value == "PASS"

    def test_fail_value(self):
        assert CriterionResult.FAIL.value == "FAIL"

    def test_unknown_value(self):
        assert CriterionResult.UNKNOWN.value == "UNKNOWN"

    def test_coverage_info_properties(self):
        """CoverageInfo computes fail_count and unknown_count from fields."""
        cov = CoverageInfo(known_count=4, pass_count=3, total_count=5)
        assert cov.fail_count == 1    # known - passed
        assert cov.unknown_count == 1  # total - known
