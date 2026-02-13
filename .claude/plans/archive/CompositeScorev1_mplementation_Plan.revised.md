Composite Score v1 — Implementation Plan
Implements the architecture defined in .claude/plans/CompositeScoreArchitecture_v1.md: tri-state criteria, coverage-adjusted sub-scores, momentum drawdown penalties, and composite rescaling.

Phase 1: Shared Types (no behavior change)
New file: backend/app/services/scoring/types.py (+ __init__.py)

Define:

CriterionResult(str, Enum): PASS / FAIL / UNKNOWN
CoverageInfo dataclass: known_count, pass_count, total_count
GateConfig dataclass: min_pass, min_known, total
StageResult dataclass:
stage_id
criteria: Dict[str, CriterionResult]
coverage: CoverageInfo
score_pct (nullable, 0-100) — coverage-adjusted percent form (for UI/debug)
score_points (nullable, 0-points_total_max) — points form used in composite math
score_pct_raw (nullable, 0-100) — before coverage adjustment
points_earned, points_known_max, points_total_max
gate_passed (bool or None), reason (optional str)
compute_coverage_adjusted_score(earned, known_max, total_max) — shared formula:
pct_raw = 100 * (earned / known_max)
coverage = known_max / total_max
pct = clamp(0, 100, pct_raw * (0.85 + 0.15 * coverage))
points = (pct / 100) * total_max
GATE_CONFIGS dict: fundamental(3/4/5), technical(3/6/7), options(2/3/4)
Phase 2: Fundamental Refactor
Modify: backend/app/services/analysis/fundamental.py

Add new evaluate() method alongside existing methods (backward compat):

Mandatory pre-gates (tri-state, not counted toward 3-of-5):

market_cap_ok (must be KNOWN + PASS)
price_ok (must be KNOWN + PASS)
Tri-state criteria (5 criteria, excluding mandatory market_cap/price pre-gates):

revenue_growth_ok → UNKNOWN if revenue_growth is None (currently defaults to False)
earnings_growth_ok → UNKNOWN if earnings is None AND margins is None (currently has fallback to False)
debt_ok → UNKNOWN if debt_to_equity is None (currently defaults to True)
liquidity_ok → UNKNOWN if current_ratio is None (currently defaults to True)
sector_ok → UNKNOWN if sector is None (currently defaults to False)
Coverage-adjusted scoring — 5 point buckets (revenue 30, earnings 30, margins 20, balance sheet 10, ROE 10 = 100 total). If a metric's data is None, that bucket is excluded from points_known_max.

Return StageResult with gate evaluation via GATE_CONFIGS["fundamental"].

Existing meets_fundamental_criteria() and calculate_fundamental_score() remain as-is.

Phase 3: Technical Refactor
Modify: backend/app/services/analysis/technical.py

Add has_sufficient_data(df, min_days=252) -> bool
Modify: backend/app/services/screening/engine.py

Add _evaluate_technical() returning StageResult
Changes:

Data sufficiency: If < 252 trading days → all criteria UNKNOWN, score=None, gate fails with reason insufficient_price_history

Tri-state criteria (7 criteria):

uptrend → UNKNOWN if price/sma_50/sma_200 is None/NaN
rsi_ok → UNKNOWN if rsi is None/NaN
macd_bullish → UNKNOWN if macd/signal is None/NaN
volume_above_avg → UNKNOWN if volume or avg_volume is None
breakout → PASS/FAIL only (detection returns bool)
volatility_ok → UNKNOWN if atr or price is None
trend_strong → UNKNOWN if adx is None
Adjusted point values (per v1 spec):

Trend alignment: 25 (unchanged)
RSI: 15 (was 20)
MACD: 15 (was 20)
Volume: 20 (unchanged)
Breakout: 15 bonus
Non-breakout perfect = 75 (was 85), total max = 90
Coverage-adjusted scoring with points_total_max = 90.

Store both score_pct (0-100) and score_points (0-90) derived from the shared helper.
Existing _check_technical_criteria() and _calculate_technical_score() kept with deprecation comment.

Phase 4: Options Refactor
Modify: backend/app/services/analysis/options.py

Add evaluate() method and _compute_mid_price() helper:

Pricing definitions (v1 spec):

mid = (bid + ask) / 2 if both > 0, else last if available, else None
spread_pct = (ask - bid) / mid — UNKNOWN if can't compute
premium_pct = mid / current_price — UNKNOWN if can't compute
Tri-state criteria (4 criteria):

iv_ok → UNKNOWN if IV is None (currently defaults to 1.0)
liquidity_ok → UNKNOWN if OI is None
spread_ok → UNKNOWN if spread_pct can't be computed
premium_ok → UNKNOWN if premium_pct can't be computed
Coverage-adjusted scoring — 4 buckets (IV 30, liquidity 25, spread 20, premium 25 = 100 total). IV rank adjustment applied after base, clamp 0-100.

Return StageResult with gate evaluation via GATE_CONFIGS["options"].

Existing calculate_options_score(), meets_options_criteria(), get_leaps_summary_enhanced() remain as-is.

Phase 5: Momentum Drawdown Penalties
Modify: backend/app/services/screening/engine.py

Add _evaluate_momentum() returning StageResult:

Base scoring — same thresholds (1M: 30, 3M: 30, 1Y: 40 = 100)

Drawdown penalties (applied after base, then clamp 0-100):

Period	Condition	Penalty
1M	< -10%	-15
1M	< -5%	-10
3M	< -20%	-15
3M	< -10%	-10
1Y	< -30%	-20
1Y	< -15%	-10
Coverage tracking — if a return period is unavailable (insufficient price data), that bucket is UNKNOWN. No gate (momentum is always post-gate).

Existing _calculate_momentum_score() kept with deprecation comment.

Phase 6: Composite Scoring + Engine Wiring (the cutover)
Modify: backend/app/services/screening/engine.py

6a. New _calculate_composite_score_v1()
Accepts 4 StageResult objects + optional sentiment_score: float
UNKNOWN components → substitute neutral = 50% of that component's max points:
neutral_points = 0.5 * points_total_max (so Technical neutral is 45, not 50)
flag {component}_available = false
Rescale: score = clamp(0, 100, raw * (100 / RAW_MAX))
RAW_MAX_NO_SENT = 97.0
RAW_MAX_WITH_SENT = 97.5
Returns {"score": float, "component_availability": Dict[str, bool]}
6b. Refactor screen_single_stock()
Replace internal calls:

fund_analysis.meets_fundamental_criteria() + calculate_fundamental_score() → fund_analysis.evaluate()
_check_technical_criteria() + _calculate_technical_score() → _evaluate_technical()
opt_analysis.get_leaps_summary_enhanced() (scoring part) → opt_analysis.evaluate()
_calculate_momentum_score() → _evaluate_momentum()
_calculate_composite_score() → _calculate_composite_score_v1()
Gate checks use stage_result.passes_gate(GATE_CONFIGS[stage]).

Result dict preserves ALL existing keys (backward compat) plus new v1 keys:


result['criteria'] = {stage: {criterion: "PASS"/"FAIL"/"UNKNOWN", ...}, ...}
result['coverage'] = {stage: {known_count, pass_count, total_count}, ...}
result['component_availability'] = {fundamental_available: bool, ...}
6c. Refactor calculate_stock_scores() (no-gate mode)
Same pattern: each analysis produces a StageResult (with gate_passed=None), composite uses same rescaling. Missing data → score=None → neutral=50% (scale-aware) at composite level.

6d. Update screen_with_sentiment()
Lines 616-622 currently call _calculate_composite_score() with floats from the result dict. Update to reconstruct StageResult objects or call _calculate_composite_score_v1() with a wrapper that builds minimal StageResults from the stored sub-scores.

Phase 7: API Schema (optional, additive)
New file: backend/app/schemas/screening.py

Define ScreeningResultV1 Pydantic model with all existing + new fields (all optional except symbol and score)
Modify: backend/app/api/endpoints/screener.py

Update ScreenResponse to use results: List[ScreeningResultV1] (purely additive — all new fields are Optional)
Phase 8: Database Model (optional, additive)
Modify: backend/app/models/screening_result.py

Add nullable columns: fundamental_score, technical_score, options_score, momentum_score (DECIMAL(6,2))
Add nullable JSON columns: criteria_v1, coverage_v1
Create Alembic migration (nullable columns = zero-downtime)
Phase 9: Tests
Directory: backend/tests/services/scoring/

Test File	Covers
test_scoring_types.py	CriterionResult, CoverageInfo, compute_coverage_adjusted_score, StageResult.passes_gate
test_fundamental.py	evaluate() tri-state, coverage adjustment, gate with coverage threshold
test_technical.py	RSI/MACD new max points, non-breakout cap 75, data sufficiency
test_options.py	mid_price fallback, tri-state criteria, coverage adjustment
test_momentum.py	Drawdown penalties, coverage with missing periods
test_composite.py	Rescaling (97/97.5), UNKNOWN→neutral=50% (Technical neutral=45), perfect=100
test_engine_integration.py	End-to-end screen_single_stock with mocked data, result shape validation
Implementation Order

Phase 1 (types)  →  Phase 2-5 (each sub-score, parallel-safe, no behavior change)
                  →  Phase 6 (cutover: engine wiring)
                  →  Phase 7-8 (API + DB, optional/additive)
                  →  Phase 9 (tests throughout)
Phases 2-5 are independent and can be implemented in any order. Phase 6 depends on all of 2-5. Phases 7-8 depend on 6 but are optional for v1 functionality.

Files Modified Summary
File	Changes
backend/app/services/scoring/types.py	NEW — shared types
backend/app/services/analysis/fundamental.py	Add evaluate()
backend/app/services/analysis/technical.py	Add has_sufficient_data()
backend/app/services/analysis/options.py	Add evaluate(), _compute_mid_price()
backend/app/services/screening/engine.py	Add _evaluate_technical(), _evaluate_momentum(), _calculate_composite_score_v1(). Refactor screen_single_stock(), calculate_stock_scores(), screen_with_sentiment()
backend/app/schemas/screening.py	NEW — Pydantic response models
backend/app/models/screening_result.py	Add sub-score + criteria columns
backend/app/api/endpoints/screener.py	Update response model
Verification
Unit tests — Run pytest backend/tests/services/scoring/ for all scoring logic
Integration test — screen_single_stock("AAPL") returns result with both old keys (fundamental_score, passed_all, etc.) and new keys (criteria, coverage, component_availability)
No-gate mode — calculate_stock_scores("AAPL") returns all sub-scores and rescaled composite
Sentiment path — screen_with_sentiment("AAPL") produces correct rescaled composite with sentiment weight
Missing data — Screen a stock with incomplete data (e.g., no options chain) → UNKNOWN criteria, neutral=50% substitution (Technical neutral=45), options_available=false
Frontend — Existing screener UI renders results without errors (all old fields preserved)