# Tier 2 Catalysts — Implementation Plan (Final, Post-Fixup)

_Last updated: 2026-02-04_

Implements Credit Stress, Volatility Structure, and Event Density to make Trade Readiness 100% real. Removes the "Partial Score" warning from the UI.

---

## Semantics & Contracts

**All component scores use risk-off polarity: 0 = calm/good, 100 = stressed/bad.**

| Component | 0 means | 100 means | Inversion in readiness? |
|-----------|---------|-----------|------------------------|
| MRI | Risk-On | Risk-Off | No |
| Liquidity | Expanding | Contracting | No |
| Credit Stress | Calm spreads | Stressed spreads | No |
| Vol Structure | Calm vol | Stressed vol | No |
| Event Density | Light week | Heavy week | No |

**No inversion** — all scores feed directly into weighted sum.

**Driver contributions** use delta-from-neutral: `contribution = (score - 50) * weight`.

**Driver direction** is standardized to `risk_on | risk_off | neutral` (neutral band: score within ±1 of 50). A separate `regime` field carries component-specific labels.

---

## Files Created

| File | Purpose |
|------|---------|
| `data_providers/interfaces/credit.py` | CreditDataProvider Protocol |
| `data_providers/interfaces/volatility.py` | VolatilityDataProvider Protocol |
| `data_providers/interfaces/event_density.py` | EventDensityDataProvider Protocol |
| `data_providers/credit_provider.py` | FRED-based credit spreads (HY OAS, IG OAS, HY OAS change 4w) |
| `data_providers/volatility_provider.py` | yfinance-based vol structure (VIX, VIX3M/VXV, VVIX) |
| `data_providers/event_density_provider.py` | Uses existing NewsFeedService calendars |

All paths relative to `backend/app/services/`.

## Files Modified

| File | Changes |
|------|---------|
| `command_center/catalyst_config.py` | Added CREDIT_STRESS, VOL_STRUCTURE, EVENT_DENSITY config blocks |
| `command_center/catalyst_service.py` | Added 6 methods, updated constructor, rewired readiness, fixed drivers, added regime field |
| `api/endpoints/macro_intelligence.py` | Replaced 3 placeholder endpoints with real implementations |
| `data_providers/fred/fred_service.py` | Added BAMLH0A0HYM2, BAMLC0A0CM series + staleness thresholds |
| `data_providers/interfaces/__init__.py` | Exported new protocols |
| `data_providers/__init__.py` | Exported new providers + singletons |
| `data_providers/liquidity_provider.py` | Uses LIQUIDITY_FRED_SERIES (not global FRED_SERIES) to avoid credit pollution |
| `frontend/.../TradeReadinessGauge.jsx` | Handles `neutral` direction (gray →) |

---

## Credit Stress

**Metrics:** `hy_oas` (45%), `ig_oas` (25%), `hy_oas_change_4w` (30%)

- Replaced `hy_ig_spread` with `hy_oas_change_4w` to avoid double-counting HY
- Uses `get_series_with_changes()` for 4-week change data
- All directions = False (higher spreads / widening = risk-off)
- Baselines: HY 3.50%, IG 1.20%, change_4w 0.0%
- Stdevs: HY 1.20%, IG 0.35%, change_4w 0.40%
- Regimes: `low_stress` (<35), `elevated` (35-65), `high_stress` (>65)
- FRED series: BAMLH0A0HYM2, BAMLC0A0CM
- Staleness: 72h (weekend-safe)

## Volatility Structure

**Metrics:** `vix` (40%), `term_slope` (35%), `vvix` (25%)

- Directions: vix=False, term_slope=True (contango=bullish → reduces risk-off score), vvix=False
- Baselines: VIX 17.0, term_slope +1.5, VVIX 85.0
- Stdevs: VIX 6.0, term_slope 2.5, VVIX 15.0
- Regimes: `calm` (<35), `elevated` (35-65), `stressed` (>65)
- Data source: yfinance (^VIX, ^VIX3M with ^VXV fallback, ^VVIX optional)
- Staleness: 72h (weekend-safe)
- VVIX is optional — reduces completeness if missing, doesn't fail

## Event Density

**Max-points normalization (NOT z-score):**

- `EVENT_DENSITY_MAX_POINTS`: 25.0
- Event point weights: high=3, medium=2, low=1
- Earnings cap: 5 points max from earnings events
- Score formula: `clamp(0, 100, 100 * total_points / EVENT_DENSITY_MAX_POINTS)`
- Regimes: `light` (<35), `moderate` (35-65), `heavy` (>65)
- Data source: NewsFeedService (economic + earnings calendars, 7-day window)

---

## Trade Readiness Weights

| Component | Weight |
|-----------|--------|
| MRI | 40% |
| Liquidity | 20% |
| Credit Stress | 15% |
| Vol Structure | 15% |
| Event Density | 10% |

---

## Driver Contract

Each driver object contains:

```
{
  "name": str,           # component name
  "value": float,        # component score (0-100)
  "contribution": float, # (score - 50) * weight
  "direction": str,      # "risk_on" | "risk_off" | "neutral"
  "regime": str          # component-specific regime label
}
```

Direction is derived from score: `risk_off` if >51, `risk_on` if <49, `neutral` otherwise.

---

## Liquidity Provider Isolation

The global `FRED_SERIES` dict in `fred_service.py` includes both liquidity and credit series. `liquidity_provider.py` defines `LIQUIDITY_FRED_SERIES` as a filtered subset containing only the 6 liquidity-relevant series (WALCL, RRPONTSYD, WTREGEN, NFCI, DGS10, T10YIE), preventing credit series from being fetched unnecessarily.

---

## Post-Implementation Fixup (completed)

Per `Tier2FixupPlan.md`, the following issues were resolved:

1. **Liquidity provider FRED isolation** — `LIQUIDITY_FRED_SERIES` constant
2. **Driver direction normalization** — `risk_on|risk_off|neutral` with separate `regime` field
3. **`_format_drivers_human_readable()`** — reads `regime` instead of `direction`
4. **Tests updated** — removed partial-state assertions, added Tier 2 coverage (cases A-F)
5. **Dev requirements** — `backend/requirements-dev.txt` (pytest, pytest-asyncio, freezegun)
6. **This document** — updated to match implemented reality
