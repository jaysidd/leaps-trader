### macro_bias_score = weighted sum of
	- Macro Risk Index (global)
	- Liquidity score
	- Sector/Ticker macro exposure weights
Map score to label:
- 0–33 → Bearish
- 34–66 → Neutral
- 67–100 → Bullish


## ### 2. Macro Confidence Indicator

**Display**
- Confidence percentage (e.g., “Confidence: 58%”)
- Color-coded using global confidence rules

**Rules**
- If any upstream macro component is stale:
  - Show warning icon
  - Tooltip: “Some macro data is stale”


## ### 3. Key Macro Drivers (Top 3)

**Display**
A short bullet list, e.g.:

- Liquidity: Mixed (↓ RRP, ↑ TGA)
- Fed Policy: Neutral
- Event Risk: Earnings in 3 days

**Rules**
- Max 3 drivers
- Human-readable, not numeric
- Derived from existing drivers arrays (no new computation)


## ### 4. Trade Compatibility Indicator

**Display**
- Label: `Trade Compatibility`
- Values:
  - Favorable
  - Mixed
  - Unfavorable

**Logic**
Based on:
- Trade Readiness score
- Ticker earnings risk
- Options positioning fragility (if available)

### Example
- Favorable: readiness > 60 AND earnings_risk < 50
- Mixed: readiness 40–60 OR earnings_risk elevated
- Unfavorable: readiness < 40 OR earnings imminent (≤2 days)


## ### 5. Earnings Risk Callout (If Applicable)

**Condition**
- Show only if earnings within next 10 days

**Display**
- “⚠ Earnings in 3 days (After Market)”
- Include confidence if unconfirmed

This must reuse existing earnings provider data.


# ## Expand / Detail View (Optional but Recommended)

## ### Expanded Overlay Shows
- Macro Bias score breakdown
- Liquidity regime snapshot
- MRI snapshot
- Link: **“View full Macro Intelligence →”**

This should be a soft expansion (accordion or modal), not a page jump.


# ## API Requirements (Read-only)

## ### New Endpoint

GET /ticker/{symbol}/macro-overlay
## ### Response Contract
```json
{
> "symbol": "AAPL",
> "macro_bias": "neutral",
> "macro_bias_score": 52,
> "confidence_score": 58,
> "data_stale": false,

> "trade_compatibility": "mixed",

> "drivers": [
```
"Liquidity conditions mixed",
"Fed policy neutral",
"Earnings in 3 days"
```
  ],

> "earnings": {
```
"event_datetime": "2026-02-05T21:00:00Z",
"session": "after_market",
"confirmed": true
```
  },

> "links": {
```
"macro_intelligence": "/macro-intelligence"
```
  }
}

#### UI Behavior Rules
	- Overlay must render in <100ms (cached data only)
	- No blocking calls on stock detail load
	- Gracefully degrade if macro data is stale or partial
	- Never block trading signals due to macro overlay

⸻

Explicit Non-Goals (Do NOT implement)
	- No per-ticker prediction markets
	- No ticker-specific macro alerts
	- No premium data dependencies
	- No override of user trade decisions

Overlay is context, not a gatekeeper.

⸻

#### Final UX Principle

Macro informs the trade.
It never replaces the trader.

If macro is unclear, show uncertainty — do not hide the signal.

---Few more updates 
A default mapping table (config or DB-seeded)
	- Used by:
	- /ticker/{symbol}/macro-overlay
	- Any future per-ticker macro scoring

### Example (what the agent should codify)
sector_macro_weights:
  Technology:
```
liquidity: 0.30
fed_policy: 0.25
earnings: 0.20
options_positioning: 0.15
event_risk: 0.10

```
### Financials
```
liquidity: 0.35
fed_policy: 0.30
earnings: 0.15
options_positioning: 0.10
event_risk: 0.10



```
⸻

#### 2️⃣ Suppressing Signals based on Macro Overlay

⚠️ This should NOT be hard-coded by the agent (at least not yet).

This is a trading philosophy decision, not just an engineering one.

Why you should be careful

### If you hard-suppress signals
	- You risk missing:
	- Early reversals
	- High-conviction setups in bad regimes
	- You reduce flexibility for different strategies:
	- **LEAPS** vs swing vs intraday
	- You lock in assumptions before seeing real usage

What you should do instead (recommended)

implement soft influence, not hard suppression.

Agent responsibilities (safe)
	- Compute and expose:
	- trade_compatibility: Favorable / Mixed / Unfavorable
	- macro_confidence
	- Add flags, not gates:
	- macro_headwind: true/false
	- Pass everything through to UI + signals

Your responsibility (later, configurable)
	- Decide when (or if) to suppress:
	- Via user settings
	- Via strategy-specific rules
	- Via experimentation

### Example rule (future, not hard-coded now)

“Suppress swing entries when Trade Readiness < 35 AND earnings < 2 days.”