# Tier 2 Catalysts — Revised Implementation Plan (Rev1 Feedback Applied)

Implements Credit Stress, Volatility Structure, and Event Density to make Trade Readiness 100% real. Removes the "Partial Score" warning from the UI.

---

## Open Questions — Resolved

1. **Rename Trade Readiness?** No. Current naming + polarity (0=Risk-On, 100=Risk-Off) is consistent and the UI renders it correctly.
2. **Exclude earnings from Event Density?** No. Keep earnings with 5-point cap. Earnings season is a macro-level concern. Cap prevents overcounting.
3. **Credit Stress: level or change?** Option A — keep `hy_oas` + `ig_oas` levels, replace `hy_ig_spread` with `hy_oas_change_4w` to avoid HY double-counting and add early-warning capability. FRED service already has `get_series_with_changes()` infrastructure.

---

## Phase 0: Semantics & Contracts

**All component scores use risk-off polarity: 0 = calm/good, 100 = stressed/bad.**

| Component | 0 means | 100 means | Inversion in readiness? |
|-----------|---------|-----------|------------------------|
| MRI | Risk-On | Risk-Off | No |
| Liquidity | Expanding | Contracting | No |
| Credit Stress | Calm spreads | Stressed spreads | No |
| Vol Structure | Calm vol | Stressed vol | No |
| Event Density | Light week | Heavy week | **No** (remove existing inversion at line 404-406) |

**Key change:** Remove the event density inversion (`100 - component_score`) from `calculate_trade_readiness()` line 404-406. All scores feed directly into weighted sum.

**Driver contributions** use delta-from-neutral: `contribution = (score - 50) * weight` instead of `score * weight`. This makes "Top Drivers" reflect what's actually pushing risk today.

---

## Phase 1: Config (catalyst_config.py)

Add config blocks for all 3 catalysts following the liquidity pattern.

**Credit Stress:**
- Metrics: `hy_oas` (45%), `ig_oas` (25%), `hy_oas_change_4w` (30%)
- All directions = False (higher spreads / widening = risk-off)
- Baselines: HY 3.50%, IG 1.20%, change_4w 0.0%
- Stdevs: HY 1.20%, IG 0.35%, change_4w 0.40%
- Thresholds: low_stress <35, high_stress >65

**Volatility Structure:**
- Metrics: `vix` (40%), `term_slope` (35%), `vvix` (25%)
- Directions: vix=False, term_slope=True (contango=bullish→reduces risk-off score), vvix=False
- Baselines: VIX 17.0, term_slope +1.5, VVIX 85.0
- Stdevs: VIX 6.0, term_slope 2.5, VVIX 15.0
- Thresholds: calm <35, stressed >65

**Event Density (max-points normalization, NOT z-score):**
- `EVENT_DENSITY_MAX_POINTS`: 25.0 (calibrated so a "heavy" week scores ~100)
- Event point weights: high=3, medium=2, low=1
- Earnings cap: 5 points max from earnings events
- Score formula: `clamp(0, 100, 100 * total_points / EVENT_DENSITY_MAX_POINTS)`
- Thresholds: light <35, heavy >65

---

## Phase 2: Data Providers (3 new files + FRED series additions)

### 2a. Credit Provider (`data_providers/credit_provider.py`)

- Add FRED series: `BAMLH0A0HYM2` (HY OAS), `BAMLC0A0CM` (IG OAS) to `FRED_SERIES` dict in fred_service.py
- Add staleness thresholds: 72h for both (daily series, weekend-safe)
- Uses `get_series_with_changes()` for `hy_oas_change_4w`
- Returns: `{ quality: DataQuality, metrics: { high_yield_oas: MetricValue, investment_grade_oas: MetricValue, hy_oas_change_4w: MetricValue } }`
- Singleton: `get_credit_provider()`

### 2b. Volatility Provider (`data_providers/volatility_provider.py`)

- yfinance tickers: `^VIX`, `^VIX3M` (fallback `^VXV`), `^VVIX`
- `yf.Ticker(symbol).history(period="5d")` via ThreadPoolExecutor (matches market_data.py pattern)
- Derives `term_slope = vix3m - vix`
- VVIX is optional — reduce completeness if missing, don't fail
- Staleness: **72h** (weekend-safe)
- Returns: `{ quality: DataQuality, metrics: { vix: MetricValue, term_slope: MetricValue, vvix: MetricValue } }`
- Singleton: `get_volatility_provider()`

### 2c. Event Density Provider (`data_providers/event_density_provider.py`)

- Uses existing `NewsFeedService.get_economic_calendar(days_ahead=7)` + `get_earnings_calendar(days_ahead=7)`
- Sums weighted event points: high=3, medium=2, low=1
- Caps earnings contribution at 5 points
- Returns top 10 events sorted by datetime with: name, datetime, impact, category, source
- Returns: `{ quality: DataQuality, metrics: { total_points: float, high_impact_count: int, events: List[dict] } }`
- Singleton: `get_event_density_provider()`

---

## Phase 3: Score Computation (catalyst_service.py)

Add 6 methods following the `_compute_liquidity_score` / `get_liquidity` pattern:

1. **`_compute_credit_stress_score(metrics)`** — z-score normalization against baselines/stdevs, regimes: low_stress/elevated/high_stress
2. **`get_credit_stress(db=None)`** — cache key "credit_stress", TTL 90s
3. **`_compute_vol_structure_score(metrics)`** — z-score normalization, term_slope direction=True (inverted signal), regimes: calm/elevated/stressed
4. **`get_vol_structure(db=None)`** — cache key "vol_structure", TTL 90s
5. **`_compute_event_density_score(metrics)`** — **max-points normalization** (NOT z-score): `clamp(0, 100, 100 * total_points / MAX_POINTS)`, regimes: light/moderate/heavy
6. **`get_event_density(db=None)`** — cache key "event_density", TTL 90s, includes events list in response

Update constructor to accept `credit_provider`, `volatility_provider`, `event_density_provider`.

---

## Phase 4: Trade Readiness Integration (catalyst_service.py)

### 4a. Replace placeholder block (lines 389-397)

```python
# Replace placeholder loop with real calls:
for component_name, getter in [
    ("credit_stress", self.get_credit_stress),
    ("vol_structure", self.get_vol_structure),
    ("event_density", self.get_event_density),
]:
    try:
        result = await getter(db)
        score = result.get("score", defaults[component_name])
        components[component_name] = {
            "score": score,
            "regime": result.get("regime"),
            "available": True,
        }
        confidences[component_name] = result.get("confidence_score", 0)
        if result.get("data_stale"):
            stale_components.append(component_name)
        drivers.append({
            "name": component_name,
            "value": score,
            "contribution": (score - 50) * weights[component_name],  # delta-from-neutral
            "direction": result.get("regime", "transition"),
        })
    except Exception as e:
        logger.error(f"CatalystService: Error getting {component_name}: {e}")
        components[component_name] = {"score": defaults[component_name], "available": False, "error": str(e)}
        confidences[component_name] = 0
```

### 4b. Remove event density inversion (line 404-406)

Delete:
```python
if component_name == "event_density":
    component_score = 100 - component_score
```

Event density now follows same polarity as all other scores (0=light/100=heavy = 0=good/100=bad).

### 4c. Update existing MRI + Liquidity driver contributions

Change from `score * weight` to `(score - 50) * weight` for driver contribution (lines 349, 379).

### 4d. Update readiness output

- Set `readiness_is_partial: False`
- Remove `partial_reason`
- Include all 5 component confidences: `overall_confidence = min(confidences_of_available_components)`
- Add `unavailable_components: [...]` list for any runtime failures (structural completeness is True, runtime availability may vary)

### 4e. Update `save_snapshot`

Populate `credit_stress_score`, `vol_structure_score`, `event_density_score` columns (already nullable in model). Set `readiness_is_partial=False`.

### 4f. Update `_format_drivers_human_readable`

Add credit/vol/event density to driver summary strings:
- Credit: "Credit: Calm" / "Credit: Stressed (↑ HY Spreads)"
- Vol: "Volatility: Low" / "Volatility: Elevated (↑ VIX, Backwardation)"
- Event: "Events: Light Week" / "Events: Heavy Week (3 high-impact)"

Replace placeholder comment at line 1005-1006.

---

## Phase 5: API Endpoints (macro_intelligence.py)

Replace 3 placeholder endpoints (lines 558-594):

```python
GET /catalysts/credit       → service.get_credit_stress(db)
GET /catalysts/volatility   → service.get_vol_structure(db)
GET /catalysts/event-density → service.get_event_density(db)  # includes events list
```

---

## Phase 6: Module Registration

- `interfaces/__init__.py` — add CreditDataProvider, VolatilityDataProvider, EventDensityDataProvider protocols
- `data_providers/__init__.py` — add provider impls + singletons
- Add 3 interface protocol files: `interfaces/credit.py`, `interfaces/volatility.py`, `interfaces/event_density.py`

---

## Files Summary

| File | Action | Changes |
|------|--------|---------|
| `data_providers/credit_provider.py` | **NEW** | FRED-based credit spreads |
| `data_providers/volatility_provider.py` | **NEW** | yfinance VIX/VIX3M/VVIX |
| `data_providers/event_density_provider.py` | **NEW** | NewsFeedService calendars |
| `data_providers/interfaces/credit.py` | **NEW** | CreditDataProvider protocol |
| `data_providers/interfaces/volatility.py` | **NEW** | VolatilityDataProvider protocol |
| `data_providers/interfaces/event_density.py` | **NEW** | EventDensityDataProvider protocol |
| `data_providers/fred/fred_service.py` | Modify | Add BAMLH0A0HYM2, BAMLC0A0CM series + staleness thresholds |
| `data_providers/interfaces/__init__.py` | Modify | Export new protocols |
| `data_providers/__init__.py` | Modify | Export new providers + singletons |
| `command_center/catalyst_config.py` | Modify | Add credit/vol/event density configs |
| `command_center/catalyst_service.py` | Modify | Add 6 methods, update constructor, rewire readiness, fix drivers, remove inversion |
| `api/endpoints/macro_intelligence.py` | Modify | Replace 3 placeholder endpoints |

All paths relative to `backend/app/services/` except API endpoint.

---

## Post-Implementation Fixup (per Tier2FixupPlan.md)

See `.claude/plans/Tier2FixupPlan.md` for full details. Implementing tasks 1-6 below.
