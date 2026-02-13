"""
Shared types for the v1 composite scoring system.

Units convention (D5):
- Growth rates, margins, ROE, returns: decimals (0.20 = 20%)
- Debt-to-equity: percentage points (150 = 150%) — per upstream data
- Options IV: decimal (0.70 = 70%)
- IV Rank: 0-100 scale
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


class CriterionResult(str, Enum):
    """Tri-state criterion evaluation."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class CoverageInfo:
    """Coverage statistics for a screening stage."""
    known_count: int      # criteria that evaluated to PASS or FAIL
    pass_count: int       # criteria that evaluated to PASS
    total_count: int      # total criteria in this stage

    @property
    def fail_count(self) -> int:
        return self.known_count - self.pass_count

    @property
    def unknown_count(self) -> int:
        return self.total_count - self.known_count

    def to_dict(self) -> Dict[str, int]:
        return {
            "known_count": self.known_count,
            "pass_count": self.pass_count,
            "total_count": self.total_count,
        }


@dataclass
class GateConfig:
    """Gate requirements for a stage."""
    min_pass: int         # minimum PASS criteria to pass gate
    min_known: int        # minimum KNOWN (non-UNKNOWN) criteria to pass gate
    total: int            # total criteria count


@dataclass
class StageResult:
    """
    Result from evaluating a screening stage.

    score_pct:    0-100 coverage-adjusted percent (for UI / debug)
    score_points: 0-points_total_max (for composite math)
    score_pct_raw: 0-100 before coverage adjustment
    """
    stage_id: str
    criteria: Dict[str, CriterionResult]
    coverage: CoverageInfo
    score_pct: Optional[float] = None
    score_points: Optional[float] = None
    score_pct_raw: Optional[float] = None
    points_earned: float = 0.0
    points_known_max: float = 0.0
    points_total_max: float = 0.0
    reason: Optional[str] = None

    def passes_gate(self, config: GateConfig) -> bool:
        """
        Single source of truth for gate evaluation (D4).
        Returns True only if both coverage and pass thresholds are met.
        """
        return (
            self.coverage.pass_count >= config.min_pass
            and self.coverage.known_count >= config.min_known
        )

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id,
            "criteria": {k: v.value for k, v in self.criteria.items()},
            "coverage": self.coverage.to_dict(),
            "score_pct": self.score_pct,
            "score_points": self.score_points,
            "score_pct_raw": self.score_pct_raw,
            "reason": self.reason,
        }


# Gate configurations — tightened to reduce noise and improve signal quality.
# Previously: fundamental 3/5, technical 3/7, options 2/4 — far too permissive.
GATE_CONFIGS = {
    "fundamental": GateConfig(min_pass=4, min_known=4, total=5),
    "technical":   GateConfig(min_pass=3, min_known=5, total=7),
    "options":     GateConfig(min_pass=2, min_known=3, total=4),
}


def compute_coverage_adjusted_score(
    points_earned: float,
    points_known_max: float,
    points_total_max: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Coverage-adjusted sub-score formula from v1 spec.

    Returns (score_pct, score_points, score_pct_raw):
      - score_pct:     0-100, coverage-adjusted percent
      - score_points:  0-points_total_max, for composite math
      - score_pct_raw: 0-100, before coverage adjustment

    Returns (None, None, None) if points_known_max == 0 (full UNKNOWN).
    """
    if points_known_max == 0:
        return None, None, None

    pct_raw = 100.0 * (points_earned / points_known_max)
    coverage = points_known_max / points_total_max
    pct = max(0.0, min(100.0, pct_raw * (0.85 + 0.15 * coverage)))
    points = (pct / 100.0) * points_total_max

    return pct, points, pct_raw


def build_coverage_from_criteria(criteria: Dict[str, CriterionResult]) -> CoverageInfo:
    """Build CoverageInfo from a criteria dict."""
    known = sum(1 for v in criteria.values() if v != CriterionResult.UNKNOWN)
    passed = sum(1 for v in criteria.values() if v == CriterionResult.PASS)
    return CoverageInfo(
        known_count=known,
        pass_count=passed,
        total_count=len(criteria),
    )
