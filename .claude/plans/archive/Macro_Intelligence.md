# High-Impact Catalysts V1.0 — Detailed Design Spec (for Coding Agent)

## Navigation (Required)
Top Navigation:
**Command Center | Screener | Signals | Portfolio | Macro Intelligence**

### UX Rule
- **Command Center** shows *summaries + alerts* only (no deep analytics).
- **Macro Intelligence** is the drill-down page for catalysts + regime internals.
- **Ticker Detail** shows a compact “Catalyst Overlay” with links to Macro Intelligence.

---

## Objective
Add a **Catalyst Intelligence Layer** to improve trading decisions (especially LEAPS / swing), by combining high-ROI catalysts into:
1) **Environment/Regime context**
2) **Ticker-specific event risk**
3) **Signal confidence modifiers**
4) **Actionable alerts with dedupe + cooldown**

The system must be explainable:
- Every catalyst score returns **drivers**, **confidence**, and **last updated**.

---

## Scope: High-Impact Catalysts (Ranked by ROI)

### Tier 1 (Implement First)
1. **Liquidity & Financial Conditions**
2. **Earnings Season & Guidance Risk**
3. **Options Positioning**

### Tier 2
4. **Credit Markets (Equities follow credit)**
5. **Volatility Structure (beyond VIX)**
6. **Macro Calendar Density (event stacking)**

### Tier 3 (optional after stabilization)
7. **Insider + Institutional Flows**
8. **Narrative Crowding / Consensus Fatigue**
9. **Cross-Asset Confirmation**
10. **Regime Compatibility (strategy fit)**

---

## System Architecture

### New Services
- `CatalystService`
  - computes catalyst signals from data snapshots
  - returns a unified `CatalystSummary` (macro + ticker)
- `CatalystDataIngestor`
  - fetches scheduled data (daily/weekly) and market data (hourly)
- `CatalystAlertAdapter`
  - exposes catalyst-trigger conditions to the existing alert framework (UserAlert + AlertService)

### Existing Services to Integrate With
- `MacroSignalService` (MRI/regime already exists)
- Existing `AlertService` (must remain the single notifier authority)
- Existing Market data provider layer (use interfaces; do not hardcode vendors)

---

## Data Model Additions (DB)

### 1) `CatalystSnapshot` (macro-level time-series)
Stores computed catalyst outputs for audit + charts.

Fields:
- `id`
- `timestamp`
- `liquidity_score` (0–100)
- `credit_stress_score` (0–100)
- `vol_structure_score` (0–100)
- `event_density_score` (0–100)
- `options_positioning_score` (0–100) (index-level)
- `cross_asset_confirmation_score` (0–100)
- `confidence_by_component` (JSON)
- `drivers` (JSON) — top drivers per component
- `data_stale` (bool)
- `last_api_success` (datetime)

Indexes:
- `(timestamp desc)`

### 2) `TickerCatalystSnapshot` (ticker-level time-series)
Stores per-ticker event/catalyst overlays.

Fields:
- `id`
- `symbol` (indexed)
- `timestamp`
- `earnings_risk_score` (0–100)
- `options_positioning_score` (0–100) (ticker-level)
- `insider_flow_score` (0–100) (optional)
- `crowding_score` (0–100) (optional)
- `macro_bias_score` (0–100) (output of macro+sector mapping)
- `confidence_by_component` (JSON)
- `drivers` (JSON)
- `next_known_events` (JSON) — earnings date, guidance flag, macro events relevance
- `data_stale` (bool)

Indexes:
- `(symbol, timestamp desc)`

### 3) `EventCalendar` (macro + earnings)
A unified calendar table to support “Event Density” and per-ticker earnings risk.

Fields:
- `id`
- `event_type` (CPI, FOMC, Jobs, TreasuryAuction, Earnings, etc.)
- `symbol` (nullable for macro events)
- `event_datetime`
- `importance` (low/med/high)
- `estimated_vol_impact` (optional)
- `source` (string)

Indexes:
- `(event_datetime)`
- `(symbol, event_datetime)`

---

## Data Inputs (What to Fetch)

### A) Liquidity & Financial Conditions (macro)
Inputs (daily/weekly):
- Central bank balance sheet trend proxy (QE/QT direction)
- Reverse repo proxy (RRP)
- Treasury General Account proxy (TGA)
- Financial Conditions Index proxy (FCI)
- Real yields proxy (10Y nominal – inflation expectations) or simplified proxy (10Y yield trend)

**Note:** Use an abstraction layer: `LiquidityDataProvider` returning normalized values.  
Do not vendor-lock.

### B) Earnings & Guidance Risk (ticker)
Inputs (daily):
- Earnings datetime (confirmed)
- Expected earnings window (pre/post market)
- Recent earnings result direction (optional)
- Guidance direction (up/flat/down) if available

Provider interface: `EarningsCalendarProvider`.

### C) Options Positioning (macro + ticker)
Inputs (daily/intraday depending on availability):
- Put/Call ratio (index + ticker)
- Open interest by strike (calls/puts)
- Implied volatility percentile/rank
- Gamma exposure proxy (GEX) if available
- “OI walls” (top strikes by OI)

Provider interface: `OptionsPositioningProvider`.

### D) Credit Markets (macro)
Inputs (daily):
- High yield spread proxy
- Investment grade spread proxy
- Credit stress proxy (optional)

Provider interface: `CreditDataProvider`.

### E) Volatility Structure (macro)
Inputs (daily/intraday):
- VIX (spot)
- VIX 3M (or equivalent) to compute term structure slope
- VVIX (optional)
- Skew proxy (optional)

Provider interface: `VolatilityDataProvider`.

### F) Macro Calendar Density (macro)
Inputs (calendar):
- CPI, PPI, FOMC, Jobs, major Treasury auctions
- Add “importance” + “known volatility” flags

Provider interface: `MacroEventCalendarProvider`.

### G) Insider / Institutional Flows (optional)
Inputs (daily/weekly):
- Insider buys/sells (clustered buys)
- ETF flows by sector
- 13F changes (quarterly)

Provider interface: `FlowsProvider`.

### H) Narrative Crowding (optional)
Inputs (daily):
- Analyst rating skew
- Estimate revisions trend
- Polymarket saturation (market odds stuck >X% for Y days)

Provider interface: `CrowdingProvider`.

### I) Cross-Asset Confirmation (macro)
Inputs (intraday/daily):
- SPY/QQQ
- DXY (dollar)
- TLT (long bonds)
- Oil/commodities proxy (optional)
- Gold proxy (optional)

Provider interface: `CrossAssetProvider`.

---

## Core Calculations (Exact Outputs + Rules)

### 1) Liquidity Regime Score (0–100)
Goal: Determine whether liquidity is **expanding (risk-on)** or **contracting (risk-off)**.

Inputs normalized to z-scores or percentiles:
- `QT_QE_trend`
- `RRP_change`
- `TGA_change`
- `FCI_change`
- `RealYield_change`

Compute:
- `liquidity_score = clamp(0..100, 50 + Σ(w_i * signal_i))`

Rules:
- Strongly contracting liquidity → score < 35
- Strongly expanding liquidity → score > 65
- Provide: `drivers = top 3 inputs by absolute contribution`
- Provide: `confidence` based on completeness of inputs + stability (low volatility in inputs increases confidence)

### 2) Earnings Risk Score (Ticker, 0–100)
Goal: Flag event risk and adjust signal confidence.

Compute:
- Days to earnings: `dte = (earnings_datetime - now).days`
- Risk curve:
  - `dte <= 0`: 20 (event passed)
  - `1–2 days`: 90
  - `3–5 days`: 75
  - `6–10 days`: 55
  - `>10 days`: 30
- If guidance has been negative recently → add +10–20
- If implied vol elevated vs percentile → add +10–20

Output:
- `earnings_risk_score`
- `next_known_events` includes earnings datetime + session + any guidance flag
- `drivers` includes dte, IV percentile, guidance flag
- `confidence` depends on completeness (missing earnings date = low confidence)

### 3) Options Positioning Score (Macro + Ticker, 0–100)
Goal: Identify “pain zones” and volatility regime.

Compute subcomponents:
- Put/Call percentile (higher = fear)
- IV rank/percentile
- OI wall concentration (how concentrated top strikes are)
- GEX proxy if available:
  - Positive gamma → smoother trends
  - Negative gamma → chop/reversals

Combine:
- `options_positioning_score = weighted sum → 0..100`

Interpretation:
- 0–33: supportive positioning (risk-on / stable)
- 34–66: mixed
- 67–100: fragile (risk-off / high reversal risk)

Ticker-specific outputs:
- `oi_walls = top call/put strikes`
- `max_pain` (optional)
- `drivers` include: put/call, IV rank, top OI strikes

### 4) Credit Stress Score (0–100)
Goal: Early warning for risk-off.

Compute from spreads:
- Rising HY/IG spreads → higher stress score

Output:
- `credit_stress_score`
- `drivers` include HY spread change, IG spread change
- `confidence` depends on data completeness

### 5) Volatility Structure Score (0–100)
Goal: Detect volatility regime (compression vs expansion).

Key measures:
- Term structure slope: `VIX3M - VIX`
  - Contango (positive) = calmer
  - Backwardation (negative) = stress
- Optional: VVIX high = instability

Output:
- `vol_structure_score` (higher = risk-off/stress)
- `drivers`: slope + VIX level + VVIX if available

### 6) Event Density Score (0–100)
Goal: Identify “stacked macro risk weeks” and adjust alert sensitivity.

Compute for next 7 calendar days:
- Count events weighted by importance:
  - High = 3 points
  - Med = 2 points
  - Low = 1 point

`event_density_points = sum(points)`
Normalize to 0–100 using configurable max points.

Outputs:
- `event_density_score`
- `next_events = list top upcoming events`
- Rule: When density > 70, tighten risk controls:
  - raise signal thresholds
  - reduce recommended sizing
  - suppress low-confidence alerts

### 7) Cross-Asset Confirmation Score (0–100)
Goal: Confirm regime by checking correlated assets.

Create binary confirmations:
- Equities up + bonds stable + dollar stable → risk-on confirmation
- Equities up + dollar surging + bonds falling → fragile
- Equities flat + credit stress rising → warning

Score:
- `cross_asset_confirmation_score = sum(confirmations) scaled`

Output:
- Provide which assets disagreed as `drivers`

### 8) Regime Compatibility (Rule Engine)
Goal: Ensure strategy type fits the current environment.

Inputs:
- `MRI` (existing)
- Liquidity score
- Credit stress
- Vol structure

Rule examples:
- LEAPS bullish signals get reduced confidence if:
  - MRI indicates risk-off OR
  - liquidity_score < 40 OR
  - credit_stress_score > 70

Output:
- `regime_fit` (good / mixed / poor)
- `trade_readiness_modifier` (-30% .. +10%)

---

## Unified Output: Trade Readiness (Recommended)
Create a single macro-level rollup:

`trade_readiness_score (0–100)` computed from:
- MRI (existing) (40%)
- Liquidity (20%)
- Credit (15%)
- Vol structure (15%)
- Event density (10%, inverted)

Also compute:
- `readiness_label` (green/yellow/red)
- `confidence` (min of key confidences)
- `drivers` (top 3)

This score powers:
- Command Center top-right summary strip
- Alert thresholds scaling
- Ticker “macro overlay” confidence adjustment

---

## Integration With Existing Alerts (Mandatory)

### Alert Types to Add (reusing UserAlert + AlertService)
- `CATALYST_LIQUIDITY_REGIME_CHANGE`
- `CATALYST_CREDIT_STRESS_SPIKE`
- `CATALYST_VOL_REGIME_CHANGE`
- `CATALYST_EVENT_DENSITY_HIGH`
- `TICKER_EARNINGS_WITHIN_DAYS`
- `TICKER_OPTIONS_FRAGILE_POSITIONING`

### Alert Params (JSON examples)
- Liquidity regime change:
  ```json
  {"threshold_low": 40, "threshold_high": 60, "persistence_checks": 2}

  ### Noise Controls
	- persistence: require 2 consecutive runs before triggering
	- cooldown per alert type
	- dedupe hash includes (type + symbol + window + direction)

⸻

### Scheduler Cadence (Suggested)
	- Liquidity/Credit/Vol: daily + refresh intraday if data supports
	- Options positioning: daily (or intraday if available)
	- Event density: recompute every 6 hours
	- Earnings calendar: daily
	- Ticker overlays: recompute on-demand + cached daily

⸻

### API Endpoints (FastAPI)

All under: /command-center/macro-intelligence/*

Macro-level
	- GET /catalysts/summary
Returns: readiness score + component scores + confidence + drivers + staleness
	- GET /catalysts/liquidity
	- GET /catalysts/credit
	- GET /catalysts/volatility
	- GET /catalysts/event-density
	- GET /catalysts/cross-asset
	- GET /catalysts/history?hours=168

Ticker-level
	- GET /ticker/{symbol}/catalysts
Returns earnings risk, options positioning, macro bias modifier, next events, drivers
	- GET /ticker/{symbol}/events
	- GET /ticker/{symbol}/options-positioning

⸻

### UI Requirements

Command Center (summary only)

## Right panel should show
	- Trade Readiness Score (or MRI + readiness modifier)
	- Mini “Catalyst Status” list (icons + up/down)
	- “View Macro Intelligence →” link

No deep tables here.

### Macro Intelligence Page (new)

## Sections (top-down)
	1.	Trade Readiness (primary)
	2.	Liquidity & Financial Conditions
	3.	Options Positioning (Index-level + heat zones)
	4.	Credit Stress
	5.	Volatility Structure
	6.	Event Density Timeline
	7.	Cross-Asset Confirmation
	8.	(Optional) Crowding/Flows tabs

### Ticker Detail Overlay

## A compact “Catalyst Overlay” card
	- Earnings risk (days + score)
	- Options fragility score + OI wall hints
	- Macro readiness modifier (+/-)
	- Link to Macro Intelligence

⸻

Explainability (Non-Negotiable)

## Every catalyst output must include
	- score
	- confidence_score
	- drivers (top 3)
	- last_updated
	- data_stale

⸻

### Testing Requirements (Minimum)
	1.	Deterministic unit tests

	- same inputs → same scores
	- boundary conditions (score clamping)

# Scenario tests

	- High event density week → readiness drops + alert sensitivity increases
	- Liquidity contracting + credit stress rising → readiness “red”
	- Earnings in 2 days → ticker earnings risk > 85

# Staleness behavior

	- stale data suppresses new catalyst alerts

⸻

Configuration (Must Be Externalized)

## Provide config for
	- weights of readiness score
	- threshold levels for regime labels
	- alert persistence and cooldowns
	- event importance weights
	- minimum data completeness for confidence scoring


# Data Provider Interface Spec (Companion) — Macro Intelligence v1

## Purpose
Define **exact provider interfaces** and **payload contracts** for all data inputs used by the Catalyst + Macro Intelligence layer.

### Design Goals
- Providers are **vendor-agnostic** (no hardcoded Polygon/Tradier/etc.)
- All providers return **normalized, typed payloads**
- Responses include **timestamps** and **data quality metadata**
- Missing fields must be explicit (`null`) — never silently omitted
- Every provider supports:
  - live/current fetch
  - optional historical window fetch (when feasible)

---

## Common Types

### `DataQuality`
```json
{
  "source": "string",
  "as_of": "ISO-8601 datetime",
  "is_stale": false,
  "stale_reason": null,
  "completeness": 1.0,
  "confidence_score": 0.0
}


# Rules
	- completeness ∈ [0,1]
	- confidence_score ∈ [0,100]
	- is_stale=true implies confidence_score <= 40 unless explicitly justified

### TimeRange
	- start: ISO-8601 datetime
	- end: ISO-8601 datetime
	- interval: one of: 1m | 5m | 15m | 1h | 1d

### SeriesPoint
{
> "t": "ISO-8601 datetime",
> "v": 123.45
}

## Provider Contract Rules (Mandatory)
	1.	Providers must be async
	2.	Provider methods must raise typed exceptions (not raw strings) for:
	- auth failures
	- rate limits
	- timeouts
	- upstream format changes
	3.	Providers must return DataQuality with:
	- source
	- as_of
	- completeness
	- confidence_score
	4.	Providers must support mocking for tests

⸻

1. LiquidityDataProvider

### Overview

Returns macro liquidity/conditions metrics used to compute the Liquidity Regime score.

### Interface

# class LiquidityDataProvider(Protocol)
```
async def get_current(self) -> dict: ...
async def get_history(self, start: str, end: str, interval: str = "1d") -> dict: ...

```
get_current() Response

{
> "quality": { "source": "fred|vendor|internal", "as_of": "2026-02-02T14:30:00Z", "is_stale": false, "stale_reason": null, "completeness": 0.9, "confidence_score": 78 },
> "metrics": {
```
"fed_balance_sheet": { "value": 7.53e12, "unit": "usd", "change_1w": -0.3, "change_4w": -1.1 },
"rrp": { "value": 0.61e12, "unit": "usd", "change_1w": -8.2, "change_4w": -21.5 },
"tga": { "value": 0.73e12, "unit": "usd", "change_1w": 4.0, "change_4w": 10.6 },
"fci": { "value": -0.21, "unit": "index", "change_1w": -0.05, "change_4w": -0.10 },
"real_yield_10y": { "value": 1.85, "unit": "pct", "change_1w": 0.06, "change_4w": 0.12 }
```
  }
}

# Notes
	- change_* are percent change for monetary series (fed_balance_sheet/rrp/tga)
	- change_* are absolute change for indices/percent series (fci/real_yield_10y)

get_history() Response

{
> "quality": { "...": "..." },
> "series": {
```
"fed_balance_sheet": [ { "t": "...", "v": 7.54e12 }, { "t": "...", "v": 7.53e12 } ],
"rrp": [ { "t": "...", "v": 0.62e12 }, { "t": "...", "v": 0.61e12 } ],
"tga": [ { "t": "...", "v": 0.70e12 }, { "t": "...", "v": 0.73e12 } ],
"fci": [ { "t": "...", "v": -0.18 }, { "t": "...", "v": -0.21 } ],
"real_yield_10y": [ { "t": "...", "v": 1.79 }, { "t": "...", "v": 1.85 } ]
```
  }
}

2. OptionsPositioningProvider

### Overview

Returns options positioning metrics for both index-level and ticker-level analysis.

### Interface
class OptionsPositioningProvider(Protocol):
```
async def get_index_positioning(self, symbol: str, as_of: str | None = None) -> dict: ...
async def get_ticker_positioning(self, symbol: str, as_of: str | None = None) -> dict: ...
async def get_oi_walls(self, symbol: str, expiry: str | None = None, top_n: int = 5) -> dict: ...

```
get_index_positioning(symbol)

symbol examples: SPY, QQQ, IWM

# Response

{
> "quality": { "...": "..." },
> "symbol": "SPY",
> "as_of": "2026-02-02T15:00:00Z",
> "metrics": {
```
"put_call_ratio": { "value": 0.92, "percentile_1y": 61 },
"iv_rank": { "value": 34.0, "unit": "pct" },
"iv_percentile": { "value": 41.0, "unit": "pct" },
"gex": { "value": 1.8e9, "unit": "usd_gamma", "available": true },
"skew": { "value": -1.2, "unit": "pct", "available": false }
```
  }
}

get_ticker_positioning(symbol)
Response:
{
> "quality": { "...": "..." },
> "symbol": "AAPL",
> "as_of": "2026-02-02T15:00:00Z",
> "metrics": {
```
"put_call_ratio": { "value": 0.78, "percentile_1y": 35 },
"iv_rank": { "value": 22.0, "unit": "pct" },
"iv_percentile": { "value": 28.0, "unit": "pct" },
"oi_concentration": { "value": 0.42, "unit": "ratio", "explain": "Top 5 strikes contain 42% of OI" }
```
  }
}

get_oi_walls(symbol, expiry, top_n)

# Response
{
> "quality": { "...": "..." },
> "symbol": "AAPL",
> "expiry": "2026-03-20",
> "as_of": "2026-02-02T15:00:00Z",
> "walls": {
```
"calls": [
  { "strike": 200, "open_interest": 185000, "notional": 3.7e9 },
  { "strike": 210, "open_interest": 142000, "notional": 2.9e9 }
],
"puts": [
  { "strike": 180, "open_interest": 161000, "notional": 3.2e9 },
  { "strike": 175, "open_interest": 121000, "notional": 2.4e9 }
]
```
  }
}


3. EarningsCalendarProvider

### Overview

Returns earnings dates and optional guidance metadata.

### Interface
class EarningsCalendarProvider(Protocol):
```
async def get_next_earnings(self, symbol: str) -> dict: ...
async def get_earnings_calendar(self, start: str, end: str, symbols: list[str] | None = None) -> dict: ...

```
get_next_earnings(symbol)

# Response
{
> "quality": { "...": "..." },
> "symbol": "AMD",
> "earnings": {
```
"event_datetime": "2026-02-10T21:00:00Z",
"session": "after_market",
"confirmed": true,
"estimate_available": true,
"guidance_trend": "up|flat|down|null",
"last_report_date": "2025-11-05"
```
  }
}

get_earnings_calendar(start, end, symbols)

# Response
{
> "quality": { "...": "..." },
> "range": { "start": "...", "end": "..." },
> "items": [
```
{
  "symbol": "MSFT",
  "event_datetime": "2026-02-06T21:00:00Z",
  "session": "after_market",
  "confirmed": true
}
```
  ]
}

4. CreditDataProvider

### Overview

Returns credit spread proxies to compute Credit Stress score.

### Interface
class CreditDataProvider(Protocol):
```
async def get_current_spreads(self) -> dict: ...
async def get_spread_history(self, start: str, end: str, interval: str = "1d") -> dict: ...

```
get_current_spreads()

# Response
{
> "quality": { "...": "..." },
> "as_of": "2026-02-02T14:00:00Z",
> "spreads": {
```
"high_yield_oas": { "value": 3.45, "unit": "pct", "change_1w": 0.12, "change_4w": 0.28 },
"investment_grade_oas": { "value": 1.18, "unit": "pct", "change_1w": 0.03, "change_4w": 0.07 }
```
  }
}

get_spread_history(start, end)

# Response
{
> "quality": { "...": "..." },
> "series": {
```
"high_yield_oas": [ { "t": "...", "v": 3.21 }, { "t": "...", "v": 3.45 } ],
"investment_grade_oas": [ { "t": "...", "v": 1.11 }, { "t": "...", "v": 1.18 } ]
```
  }
}

5. VolatilityDataProvider

### Overview

Returns volatility term structure inputs for Volatility Structure score.

### Interface
class VolatilityDataProvider(Protocol):
```
async def get_current(self) -> dict: ...
async def get_history(self, start: str, end: str, interval: str = "1d") -> dict: ...

```
get_current()

# Response
{
> "quality": { "...": "..." },
> "as_of": "2026-02-02T15:00:00Z",
> "metrics": {
```
"vix": { "value": 16.3, "unit": "index" },
"vix3m": { "value": 18.1, "unit": "index", "available": true },
"vvix": { "value": 95.0, "unit": "index", "available": false }
```
  }
}

get_history(start, end)

# Response
{
> "quality": { "...": "..." },
> "series": {
```
"vix": [ { "t": "...", "v": 14.8 }, { "t": "...", "v": 16.3 } ],
"vix3m": [ { "t": "...", "v": 17.2 }, { "t": "...", "v": 18.1 } ]
```
  }
}

6. MacroEventCalendarProvider

### Overview

Returns macro events (CPI/FOMC/Jobs/Auctions) used for Event Density and event timeline.

### Interface
class MacroEventCalendarProvider(Protocol):
```
async def get_events(self, start: str, end: str) -> dict: ...
async def get_upcoming(self, days: int = 14) -> dict: ...

```
get_events(start, end)

# Response
{
> "quality": { "...": "..." },
> "range": { "start": "...", "end": "..." },
> "events": [
```
{
  "event_type": "CPI",
  "event_datetime": "2026-02-12T13:30:00Z",
  "importance": "high",
  "region": "US",
  "notes": "YoY, MoM headline/core"
},
{
  "event_type": "FOMC",
  "event_datetime": "2026-03-18T18:00:00Z",
  "importance": "high",
  "region": "US",
  "notes": "Rate decision + SEP"
}
```
  ]
}

get_upcoming(days)

Same payload, filtered to next N days.

⸻

7. CrossAssetProvider

### Overview

Returns prices and volatility inputs across assets for Cross-Asset Confirmation and divergence checks.

### Interface
class CrossAssetProvider(Protocol):
```
async def get_quotes(self, symbols: list[str]) -> dict: ...
async def get_returns(self, symbol: str, windows: list[str] = ["1h","4h","1d","5d"]) -> dict: ...
async def get_atr_percent(self, symbol: str, period: int = 14, interval: str = "1d") -> dict: ...

```
get_quotes(symbols)

# Response
{
> "quality": { "...": "..." },
> "as_of": "2026-02-02T15:10:00Z",
> "quotes": [
```
{ "symbol": "SPY", "price": 695.41, "change_pct_1d": 0.54 },
{ "symbol": "TLT", "price": 94.22, "change_pct_1d": -0.31 },
{ "symbol": "DXY", "price": 103.45, "change_pct_1d": 0.18 }
```
  ]
}

get_returns(symbol, windows)

# Response
{
> "quality": { "...": "..." },
> "symbol": "SPY",
> "as_of": "2026-02-02T15:10:00Z",
> "returns": {
```
"1h": 0.12,
"4h": 0.35,
"1d": 0.54,
"5d": 1.88
```
  }
}

get_atr_percent(symbol, period, interval)

# Response
{
> "quality": { "...": "..." },
> "symbol": "SPY",
> "as_of": "2026-02-02T00:00:00Z",
> "atr": {
```
"period": 14,
"interval": "1d",
"atr_value": 6.42,
"atr_percent": 0.92
```
  }
}

## Error Handling (Standardized)

# Providers must raise
	- ProviderAuthError
	- ProviderRateLimitError(retry_after_seconds: int | None)
	- ProviderTimeoutError
	- ProviderUpstreamFormatError
	- ProviderUnavailableError

⸻

## Staleness Rules (Global)

If quality.is_stale == true OR quality.as_of older than a configured max age:
	- downstream scores must set data_stale=true
	- alerts must be suppressed for affected components
	- UI must display last updated time

⸻

Testing Guidance (Provider Mocks)

Each provider must include a Fake*Provider implementation with deterministic fixtures matching the payload schemas above.

# Minimum fixtures
	- normal environment
	- risk-off environment
	- missing fields environment (completeness < 1.0)

⸻

## Implementation Notes
	- Use Pydantic models mirroring these schemas.
	- Keep provider adapters in /data_providers/{provider_name}/.
	- Keep interfaces in /data_providers/interfaces/.
	- Never import concrete vendor SDKs outside adapter modules.


⸻

### Delivery Checklist
	- DB models + indexes
	- Providers interfaces implemented (no vendor lock)
	- CatalystService computations with explainability
	- FastAPI endpoints
	- Macro Intelligence UI page
	- Ticker catalyst overlay
	- Alert types integrated into existing AlertService
	- Scheduler jobs
	- Tests + sample fixtures