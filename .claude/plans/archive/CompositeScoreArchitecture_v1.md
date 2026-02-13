# Composite Score Architecture — v1 Scoring Contract

This document defines the *implementation contract* for computing a `0–100` composite score from sub-scores, including hard gates, missing-data policy, and normalization rules.

## Decisions Locked for v1

1) **Technical score is defined on a `0–90` scale** (breakout is a +15 bonus; non-breakout “perfect” caps at 75).
2) **Missing data uses tri-state**: `PASS | FAIL | UNKNOWN`, plus **coverage thresholds** for gates.
3) **Momentum adds drawdown penalties**, then clamps to `0–100` (no negative composite scale).

## Weighting Schemes

### Default (no sentiment)

| Component | Weight |
|---|---:|
| Fundamental | 0.40 |
| Technical | 0.30 |
| Options | 0.20 |
| Momentum | 0.10 |

### With sentiment (Phase 2)

| Component | Weight |
|---|---:|
| Fundamental | 0.35 |
| Technical | 0.25 |
| Options | 0.15 |
| Momentum | 0.10 |
| Sentiment | 0.15 |

## Units & Conventions

- Growth rates, margins, ROE, and returns are expressed as **decimals**:
  - `0.20` means **20%**.
- Debt-to-equity (`D/E`) is expressed as **percentage points** (per upstream data):
  - `150` means **150%**.
- Options implied volatility (`IV`) is expressed as a **decimal**:
  - `0.70` means **70%**.
- IV Rank is `0–100` (already a percentage-like scale).
- “Clamp” means `min(max(x, lo), hi)`.

## Output Contract (per symbol)

At minimum:

- `passed_all: bool`
- `failed_at: str | null` (stage id)
- `passed_stages: string[]`
- `fundamental_score: float | null` (0–100 if known)
- `technical_score: float | null` (0–90 if known)
- `options_score: float | null` (0–100 if known)
- `momentum_score: float | null` (0–100 if known)
- `score: float` (final composite `0–100` if `passed_all=true`; otherwise `0` or omitted per UX)
- `criteria`: per-stage maps of `{criterion: PASS|FAIL|UNKNOWN}`
- `coverage`: per-stage `{known_count, pass_count, total_count}`

Recommended stage ids:

- `fundamentals_gate`
- `technical_gate`
- `options_gate`
- `scoring`
- plus data-fail ids like `data_fetch`, `price_data`, `options_data` as needed

## Missing Data Policy

### Tri-state evaluation
Every criterion/metric evaluates to one of:

- `PASS`: data known and condition satisfied
- `FAIL`: data known and condition not satisfied
- `UNKNOWN`: missing/unreliable/uncomputable data

### Gate counting
- Only `PASS` counts toward “need ≥K of N”.
- `UNKNOWN` does **not** count as pass.
- Each gate also requires a minimum known count (prevents passing on ignorance).

### Score calculation with missing data
For any sub-score with point buckets:

1) `points_earned`: sum of points awarded from known metrics
2) `points_known_max`: sum of max points for metrics that are not `UNKNOWN`
3) If `points_known_max == 0`: the sub-score is `UNKNOWN` (`null`)
4) Else:
   - `subscore_raw = 100 * (points_earned / points_known_max)`
   - `coverage = points_known_max / points_total_max`
   - `subscore = clamp(0, 100, subscore_raw * (0.85 + 0.15 * coverage))`

If a component score is `UNKNOWN` at composite time:
- Use `neutral=50` for composite math and set `{component}_available=false` for transparency.

## Pipeline (Hard Gates + Scoring)

### Stage 1 — Fundamental Gate (hard)

#### Mandatory (must be KNOWN + PASS)
- Market cap in `$500M–$50B`
- Price in `$5–$500`

If either is `FAIL` or `UNKNOWN` → `failed_at="fundamentals_gate"`.

#### Additional criteria (need ≥3 PASS of 5, and ≥4 KNOWN of 5)
- Revenue growth `> 0.20`
- Earnings growth `> 0.15`
- Debt-to-equity `< 150`
- Current ratio `> 1.2`
- Sector is in growth list

If not met → `failed_at="fundamentals_gate"`.

#### Fundamental Score (0–100)

| Metric | Max | Tiers |
|---|---:|---|
| Revenue Growth | 30 | `>0.50:30`, `>0.30:20`, `>0.20:10` |
| Earnings Growth | 30 | `>0.50:30`, `>0.30:20`, `>0.15:10` |
| Profit Margins | 20 | `>0.20:20`, `>0.10:10` |
| Balance Sheet | 10 | `D/E <50 AND CR >2.0:10`, `D/E <100 AND CR >1.5:5` |
| ROE | 10 | `>0.20:10`, `>0.15:5` |

### Stage 2 — Technical Gate (hard)

#### Data sufficiency
Require enough price history to compute SMA200 and 1Y returns reliably:
- Minimum bars: **≥252 trading days**

If insufficient → `failed_at="technical_gate"` with reason `insufficient_price_history`.

#### Gate criteria (need ≥3 PASS of 7, and ≥6 KNOWN of 7)
- Uptrend: `Price > SMA50 > SMA200`
- RSI OK: `40 ≤ RSI14 ≤ 70`
- MACD bullish: `MACD > Signal`
- Volume above avg: `Volume > 1.2× avg_volume_50`
- Breakout (60D): let `resistance = max(high over last 60 bars excluding last 5)` and `recent_high = max(high over last 5 bars)`; breakout if `recent_high > resistance × 1.01`
- Volatility OK: `ATR14 / Price > 0.03`
- Trend strong: `ADX14 > 25`

If not met → `failed_at="technical_gate"`.

#### Technical Score (0–90)

Non-breakout “perfect” = 75. Breakout bonus = +15.

| Component | Max | Scoring |
|---|---:|---|
| Trend Alignment | 25 | `Price > SMA20 > SMA50 > SMA200: +25`, `Price > SMA50 > SMA200: +15` |
| RSI Positioning | 15 | `50–65: +15`, `40–50 or 65–70: +8` |
| MACD Momentum | 15 | `MACD > Signal & Hist > 0: +15`, `MACD > Signal: +8` |
| Volume Strength | 20 | `Vol > 1.5× avg: +20`, `Vol > 1.2× avg: +10` |
| Breakout Bonus | 15 | breakout true: `+15` |

### Stage 3 — Options Gate (hard)

#### LEAPS universe
- Calls only
- DTE window: `365–730` days
- Selection: “closest-to-ATM call” by `min(|strike - current_price|)` (must be consistent)

If no chain / no LEAPS → `failed_at="options_gate"`.

#### Pricing definitions
- `mid = (bid + ask) / 2` if `bid>0` and `ask>0`, else `mid = last` if available.
- `spread_pct = (ask - bid) / mid` if `mid>0` and `bid>0` and `ask>0`, else `UNKNOWN`.
- `premium_pct = mid / current_price` if `mid>0` and `current_price>0`, else `UNKNOWN`.

#### Gate criteria (need ≥2 PASS of 4, and ≥3 KNOWN of 4)
- IV `< 0.70`
- Open interest `> 100`
- Spread `spread_pct < 0.10`
- Premium `premium_pct < 0.15`

If not met → `failed_at="options_gate"`.

#### Options Score (0–100) + IV-rank adjustment

Base score:

| Component | Max | Scoring |
|---|---:|---|
| IV (lower is better) | 30 | `IV <0.30:30`, `<0.50:20`, `<0.70:10` |
| Liquidity | 25 | `OI>500 & Vol>100:25`, `OI>200 & Vol>50:15`, `OI>100:10` |
| Spread Tightness | 20 | `spread_pct <0.05:20`, `<0.10:10` |
| Premium Efficiency | 25 | `premium_pct <0.05:25`, `<0.10:15`, `<0.15:10` |

IV Rank adjustment (TastyTrade enhanced data), clamp final to `0..100`:

- `IV Rank <20: +15`
- `IV Rank 20–40: +10`
- `IV Rank 70–85: -10`
- `IV Rank >85: -20`

### Stage 4 — Momentum (no gate)

Returns use trading-day counts:
- 1M: 21d
- 3M: 63d
- 1Y: 252d

Base points:

| Period | Max | Tiers |
|---|---:|---|
| 1M | 30 | `>0.15:30`, `>0.10:20`, `>0.05:10` |
| 3M | 30 | `>0.30:30`, `>0.20:20`, `>0.10:10` |
| 1Y | 40 | `>0.50:40`, `>0.30:25`, `>0.10:10` |

Drawdown penalties (apply after base, then clamp `0..100`):

| Period | Penalties |
|---|---|
| 1M | `< -0.10: -15`, `< -0.05: -10` |
| 3M | `< -0.20: -15`, `< -0.10: -10` |
| 1Y | `< -0.30: -20`, `< -0.15: -10` |

## Composite Score (Stage 5)

### Raw weighted sum

**Default (no sentiment)**

`raw = 0.40*F + 0.30*T + 0.20*O + 0.10*M`

Where:
- `F, O, M ∈ [0,100]`
- `T ∈ [0,90]`

**With sentiment**

`raw = 0.35*F + 0.25*T + 0.15*O + 0.10*M + 0.15*S`

Where `S ∈ [0,100]` (or `S=50` if sentiment unavailable).

### Scale back to 0–100
Because `T` tops out at 90, the raw maximum is below 100.

Define:
- `RAW_MAX_NO_SENT = 0.40*100 + 0.30*90 + 0.20*100 + 0.10*100 = 97`
- `RAW_MAX_WITH_SENT = 0.35*100 + 0.25*90 + 0.15*100 + 0.10*100 + 0.15*100 = 97.5`

Final:
- If no sentiment: `score = clamp(0, 100, raw * (100 / 97))`
- With sentiment: `score = clamp(0, 100, raw * (100 / 97.5))`

This scaling is a constant factor per scheme (it preserves rankings; it only maps the scheme’s true max back onto a 0–100 UI scale).

## Example
Scores:
- `F=75`, `T=60` (of 90), `O=80`, `M=50`

Raw (no sentiment):
- `raw = 75*0.40 + 60*0.30 + 80*0.20 + 50*0.10 = 30 + 18 + 16 + 5 = 69`

Scaled:
- `score = 69 * (100/97) ≈ 71.13`
