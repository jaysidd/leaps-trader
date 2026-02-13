# V2_AGENT_PATCH_NOTES.md
## Applies on top of: “Macro Intelligence Implementation Plan (V2)”
## Priority: HIGH — Overrides V2 where conflicts exist

This document contains **final decisions and corrections** that MUST be applied on top of the V2 plan.
If there is any conflict between V2 and this file, **this file wins**.

---

## 1. Liquidity Data Sources & Calculations (MANDATORY)

### Use the following FRED series IDs explicitly:
- Fed Balance Sheet: `WALCL`
- Reverse Repo (ON RRP): `RRPONTSYD`
- Treasury General Account: `WTREGEN`
- Financial Conditions Index: `NFCI`
- 10Y Nominal Yield: `DGS10`
- 10Y Breakeven Inflation: `T10YIE`

### Real Yield Formula (EXPLICIT)
```text
real_yield_10y = DGS10 - T10YIE

	- Do NOT fetch a separate “real yield” series.
	- Treat real yield as a derived metric.
	- Note: several FRED series are weekly/daily — do not expect intraday changes.

⸻

### Scheduler Cadence Optimization (IMPORTANT)

#### Change from naïve hourly storage to smart cadence
	- Liquidity snapshot job:
	- Run every 6 hours, OR
	- Hourly but do not store a new row if inputs are unchanged
	- Do NOT force hourly DB writes for slow-moving series.

#### Rationale
	- Avoids DB bloat
	- Avoids misleading “movement” in charts
	- Respects upstream rate limits

⸻

### Trade Readiness Score (PARTIAL STATE HANDLING)

#### Until Tier 2+ catalysts exist
	- Either:
	- Compute trade_readiness_score dynamically (not stored), OR
	- Store it with:

> "readiness_is_partial": true
UI Requirement
	- If readiness_is_partial=true, UI must display:
“Partial score — additional catalysts pending”

Do NOT present partial readiness history as final.

⸻

### Provider Structure Naming (CONSISTENCY RULE)

#### Canonical structure
backend/app/services/data_providers/
├── interfaces/
├── fred/
├── yahoo/
├── options/

	- Legacy modules like data_fetcher/yahoo_finance.py MUST be wrapped by a provider adapter.
	- Do NOT mix provider logic directly into services.

⸻

### Earnings Calendar Robustness (MANDATORY)

#### Earnings payload MUST include
	- confirmed: bool
	- event_datetime: datetime | null

#### Rules
	- If earnings date is missing or unconfirmed:
	- Do NOT throw
	- Set earnings_risk_score = 30
	- Set confidence_score low
	- Earnings logic must degrade gracefully.

⸻

### Options Positioning Scope (PHASE 3 CLARIFICATION)

#### Phase 3 v1 implementation
	- Use Yahoo options chain only
	- Compute:
	- IV percentile/rank (approx)
	- Put/Call proxy
	- OI walls (top strikes)
	- Gamma / GEX:
	- Optional
	- Default available=false
	- Must NOT block release

#### Explicitly defer
	- Tastytrade auth complexity
	- Premium options providers

Provider interface must allow future upgrade without refactor.

⸻

### Database Indexes (REQUIRED)

#### Add these indexes explicitly

###### CatalystSnapshot
	- (timestamp DESC)

###### TickerCatalystSnapshot
	- (symbol, timestamp DESC)

###### EventCalendar
	- (event_datetime)
	- (symbol, event_datetime)

⸻

### Data Staleness Rules (BEHAVIORAL REQUIREMENT)

#### If any provider reports stale data
	- Keep last known score
	- Set data_stale = true
	- Suppress new catalyst alerts
	- UI must show:
“Last updated X minutes ago”

No alerts should fire from stale data.

⸻

### Implementation Priority Reminder

#### Follow this order
	1.	Liquidity (FRED-based)
	2.	Earnings Risk
	3.	Options Positioning

Do NOT implement Tier 2/3 catalysts until Tier 1 signals + alerts are stable.

⸻

##### Final Guiding Rule

#### This system prioritizes
	- Stability over speed
	- Explainability over cleverness
	- Confidence over frequency

If a signal is uncertain, downgrade confidence — do not guess.

# # Unit Test Acceptance Criteria — Macro Intelligence (Tier 1 + Alert Integration)

## ## Scope
These tests validate Tier 1 catalysts and integration rules:
- Liquidity (FRED + derived real yields)
- Earnings Risk
- Options Positioning (Yahoo-only v1)
- Trade Readiness partial handling
- Data staleness behavior
- Alert evaluation via existing AlertService (no direct notifications in signal services)

All tests must be deterministic using mocked providers and fixed timestamps.


## ## General Test Rules (Global)
1. All provider calls must be mocked (no live network).
2. Freeze time in tests (e.g., `2026-02-02T12:00:00Z`) to ensure deterministic DTE and window math.
3. Scores must always be clamped to `[0, 100]`.
4. Every computed output must include:
   - `score`
   - `confidence_score`
   - `drivers` (list, length 0–3)
   - `data_stale` flag
   - `as_of` timestamp
5. Missing data must never raise unhandled exceptions; it must reduce confidence and/or set stale.


# # A) LiquidityDataProvider Adapter Tests (FRED)

## ## A1. Correct FRED series are requested
**Given** a mocked FRED client  
**When** `LiquidityDataProvider.get_current()` is called  
**Then** it must request:
- **WALCL**
- **RRPONTSYD**
- **WTREGEN**
- NFCI
- DGS10
- T10YIE

**Pass/Fail**
- PASS if all series IDs are requested at least once.
- FAIL if any is missing or a wrong ID is used.

## ## A2. Real yield calculation is correct
**Given** DGS10 = 4.20 and T10YIE = 2.10  
**When** liquidity current metrics are returned  
**Then** `real_yield_10y.value` must equal `2.10` (4.20 - 2.10)

**Pass/Fail**
- PASS if computed value equals expected within float tolerance (±0.0001).
- FAIL otherwise.

## ## A3. Missing series handling
**Given** one of the required series returns null/missing  
**When** `get_current()` runs  
**Then**
- it must not throw
- `quality.completeness < 1.0`
- `quality.confidence_score` reduced vs baseline
- missing metric is present with `value=null` or omitted with explicit record in `stale_reason` (choose one approach consistently)


# # B) Liquidity Scoring Tests (CatalystService)

## ## B1. Score clamps to 0–100
**Given** extreme inputs that would push score below 0 or above 100  
**When** `compute_liquidity_score()` runs  
**Then** score must be clamped in `[0,100]`

## ## B2. Drivers list contains top contributors
**Given** known inputs with deterministic contributions  
**When** `compute_liquidity_score()` runs  
**Then**
- `drivers` must include the top 1–3 signals by absolute contribution
- driver entries must include `name`, `value`, `contribution`

## ## B3. Confidence score decreases with missing inputs
**Given** completeness = 1.0 vs completeness = 0.6  
**When** scoring runs  
**Then** the 0.6 case must produce strictly lower `confidence_score`

## ## B4. Staleness flags propagate
**Given** provider returns `quality.is_stale=true`  
**When** scoring runs  
**Then**
- output must set `data_stale=true`
- `confidence_score <= 40` (or configured stale cap)
- scoring still returns a last-known score if available, otherwise returns score with low confidence


# # C) EarningsCalendarProvider & Earnings Risk Tests

## ## C1. Days-to-earnings curve correctness
Freeze `now = 2026-02-02T12:00:00Z`

#### Test cases (event_datetime relative to now)
- in 1 day → score >= 85
- in 3 days → score between 65–85
- in 7 days → score between 45–65
- in 14+ days → score <= 35
- in past → score <= 25

**Pass/Fail**
- PASS if computed score lands in expected range.
- FAIL if outside.

## ## C2. Missing earnings date degrades gracefully
**Given** earnings provider returns `event_datetime=null`  
**When** ticker earnings risk is computed  
**Then**
- no exceptions
- `earnings_risk_score == 30` (per patch notes)
- `confidence_score` is low (<= 40)
- drivers include `missing_earnings_date=true`

## ## C3. Unconfirmed earnings date reduces confidence
**Given** `confirmed=false` but event_datetime exists  
**Then**
- `confidence_score` must be reduced (strictly less than confirmed case)
- score may remain same, but confidence must differ


# # D) OptionsPositioningProvider (Yahoo-only v1) Tests

## ## D1. OI walls extraction returns sorted top strikes
**Given** mocked options chain with OI by strike  
**When** `get_oi_walls(symbol, top_n=3)`  
**Then**
- returns exactly 3 strikes for calls and puts (if available)
- sorted by `open_interest` descending
- includes `strike`, `open_interest`, and `notional` if computed

## ## D2. Put/Call proxy is computed and stable
**Given** total call OI and total put OI  
**When** ticker positioning is computed  
**Then** `put_call_ratio.value == put_OI / call_OI` (handle call_OI=0)

#### Edge case
- call_OI = 0 → ratio should be null or max-capped; must not divide by zero

## ## D3. GEX is optional and must not block
**Given** provider lacks GEX  
**When** positioning is computed  
**Then**
- `gex.available == false`
- options score still computed without error


# # E) Event Density (If enabled in Tier 1 bonus) Tests

## ## E1. Weighted event density points
**Given** events in next 7 days:
- 2 high (3 pts each)
- 1 medium (2 pts)
- 2 low (1 pt each)

Total points = 2*3 + 1*2 + 2*1 = 10

**When** event density is computed  
**Then**
- computed points == 10
- normalized score maps correctly to configured max points

## ## E2. High density triggers readiness dampening
**Given** `event_density_score > 70`  
**When** readiness modifiers are computed  
**Then**
- `trade_readiness_score` decreases vs same inputs with low density
- or modifier applies (explicitly test whichever your implementation chooses)


# # F) Trade Readiness Partial State Tests

## ## F1. readiness_is_partial is set when Tier 2/3 missing
**Given** only liquidity + earnings exist (options optional)  
**When** `get_trade_readiness()` is called  
**Then**
- `readiness_is_partial == true` OR readiness computed dynamically without storing
- UI payload contains a human-readable `partial_reason` or equivalent flag

## ## F2. Readiness must not be stored as final history when partial
**Given** readiness_is_partial=true  
**When** snapshot persistence runs  
**Then**
- either readiness is not persisted in DB, or persisted with the partial flag
- tests should assert DB record respects the chosen policy


# # G) Staleness Behavior Tests (Critical)

## ## G1. Stale provider suppresses alerts
**Given** liquidity provider returns stale data  
**And** a macro/catalyst alert exists that would trigger under normal data  
**When** `AlertService.check_all_alerts()` runs  
**Then**
- no new AlertNotification is created
- `times_triggered` does not increment

## ## G2. Stale score still returned but marked
**Given** stale provider data  
**When** `/macro-intelligence/catalysts/summary` payload is generated  
**Then**
- includes last known score (if available)
- `data_stale=true`
- includes `last_api_success` and `as_of`


# # H) Alert Framework Integration Tests (Existing AlertService)

## ## H1. Macro/catalyst alerts route through AlertService only
**Given** CatalystService computed outputs  
**When** alerts are evaluated  
**Then**
- only AlertService creates AlertNotification entries
- no direct Telegram calls are made from CatalystService (use spy/mock to assert)

## ## H2. Dedupe + cooldown behavior
**Given** an alert condition is true across multiple checks  
**When** `check_all_alerts()` runs twice within cooldown window  
**Then**
- only 1 notification created
- second run does not create a duplicate
- dedupe key must match (type + symbol/scope + direction + window)

## ## H3. Persistence rule (2 consecutive checks)
**Given** divergence or regime-change alert requires persistence=2  
**When**
- first evaluation sees condition true
- second evaluation sees condition true
**Then**
- notification is created only on second evaluation

**And when**
- first true, second false
**Then**
- no notification created


# # I) API Payload Contract Tests (FastAPI)

## ## I1. /catalysts/summary schema
**When** endpoint returns payload  
**Then** it must include:
- readiness score + label (or partial flag)
- component scores present for implemented catalysts
- drivers (0–3)
- confidence_score
- data_stale
- as_of

## ## I2. /ticker/{symbol}/catalysts schema
Must include:
- earnings_risk_score + drivers + confidence
- options_positioning_score (if enabled) + drivers + confidence
- next_known_events (earnings at minimum)
- data_stale indicators per component (or overall)


## ## Minimum Coverage Requirements
- Liquidity scoring: 90%+ branch coverage
- Earnings risk: 90%+ branch coverage
- Alert dedupe/persistence: 100% of critical paths
- Staleness suppression: 100% of critical paths


## ## Definition of Done
All tests pass locally using mocks with no external calls.
A CI run completes under 2 minutes for unit tests (target).
No flaky tests (no dependence on real time or network).