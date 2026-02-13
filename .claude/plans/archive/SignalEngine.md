# Signal Engine Overhaul: Soft Gates, TOD-RVOL, Liquidity, Options, IV

Already done (prior turn): notification bridge (Telegram + AlertNotification when signals fire), initial threshold reduction.

---

## Step 1: Cap Size Classification Helper

**File:** `backend/app/services/signals/signal_engine.py`

Add `_classify_cap_size(market_cap)` and mid-cap tier to `PARAMS`:

```python
def _classify_cap_size(self, market_cap: float) -> str:
    if market_cap >= 10_000_000_000:  return "large_cap"
    if market_cap >= 2_000_000_000:   return "mid_cap"
    return "small_cap"
```

Add `"mid_cap"` tier to `PARAMS` dict (interpolated between large and small).

In `process_queue_item()`: if `item.cap_size` is None, fetch market_cap from `yahoo_service.get_stock_info(symbol)` and classify. Cache the result on the queue item.

---

## Step 2: Time-of-Day RVOL

**File:** `backend/app/services/data_fetcher/alpaca_service.py`

**Bar limits per timeframe** (to get ≥10 trading days of history for ≥5 matching TOD bars):

| Timeframe | Bars/day | 10 days | Limit (with buffer) |
|-----------|----------|---------|---------------------|
| 5m | ~78 | 780 | 900 |
| 15m | ~26 | 260 | 300 |
| 4h | ~2 | 20 | 120 (fetch more for range lookback) |

```python
TOD_BAR_LIMITS = {"5m": 900, "15m": 300, "4h": 120}
```

Add `get_time_of_day_rvol(df, timeframe)`:
- Use the **same bar history** already fetched (single API call)
- Determine the **evaluation bar** — the bar all gates/strategies/confidence read from:
  - For 5m/15m: use **last closed bar** (iloc[-2] if latest bar is partial, avoids partial-bar volume bias)
  - For 4h: use **latest bar** (iloc[-1]) even if partial — see Step 5 stale-check note
  - Handle early session: if market just opened and no closed bar exists yet, return `None`
- Convert bar timestamps to ET via `zoneinfo.ZoneInfo("America/New_York")`
- Extract evaluation bar's ET time window (e.g. 11:05-11:10 for 5m)
- Filter df to bars matching same hour:minute on **prior days** (exclude today)
- Require **≥5 matching bars** or return `None` (fallback to classic RVOL)
- Use **median** volume (outlier-resistant): `tod_median_volume = filtered_df['volume'].median()`
- Return `(eval_bar_index, eval_bar_volume / tod_median_volume, tod_median_volume)`

Add `get_bars_with_enhanced_indicators(symbol, timeframe)`:
- Calls `get_bars()` with timeframe-specific limit from `TOD_BAR_LIMITS` (caller does **not** pass limit — function selects it internally)
- Calls `calculate_indicators()` (unchanged)
- Calls `get_time_of_day_rvol(df, timeframe)` on same df
- Stores TOD metrics **on the evaluation bar row** (not blindly on last row):
  - `rvol_tod`, `tod_avg_dollar_volume = close * tod_median_volume`
- If TOD median unavailable (< 5 samples or early session), falls back:
  - `tod_avg_dollar_volume = close * volume_ma20` (uses the 20-period MA already computed by `calculate_indicators()`)
  - `rvol_tod` left as `NaN` → downstream reads `effective_rvol = rvol` (classic)
- Returns `(df, eval_bar_index)` so callers read all indicators from the same row

**No extra API call** — one `get_bars()` with larger limit covers it.

**Evaluation bar contract**: gates, confidence, and strategies all read from `df.iloc[eval_bar_index]`. This ensures rvol_tod, ATR%, RVOL, EMAs, RSI are all from the same bar.

`effective_rvol = rvol_tod if not NaN else rvol` — used consistently in gate scoring, volume-confirmation tiers, and confidence formula.

---

## Step 3: Liquidity Floors

**File:** `backend/app/services/signals/signal_engine.py`

Add `LIQUIDITY_FLOORS` constant:

```python
LIQUIDITY_FLOORS = {
    "large_cap":  {"5m": 500_000,  "15m": 1_200_000, "4h": 15_000_000},
    "mid_cap":    {"5m": 250_000,  "15m": 600_000,   "4h": 8_000_000},
    "small_cap":  {"5m": 100_000,  "15m": 250_000,   "4h": 3_000_000},
}
```

In `_score_quality_gates()`, check `tod_avg_dollar_volume` against floor. Below floor = structural hard-fail (not enough real liquidity regardless of RVOL).

---

## Step 4: ATR%/RVOL Pivot Thresholds (by cap + timeframe)

**File:** `backend/app/services/signals/signal_engine.py`

Update `PARAMS` to include `mid_cap` and tuned pivots:

| TF | Cap | ATR% pivot | RVOL(tod) pivot |
|----|-----|-----------|-----------------|
| 5m | large | 0.15 | 0.80 |
| 5m | mid | 0.18 | 0.90 |
| 5m | small | 0.22 | 1.00 |
| 15m | large | 0.25 | 0.70 |
| 15m | mid | 0.30 | 0.80 |
| 15m | small | 0.35 | 0.90 |
| 4h | large | 0.50 | 0.60 |
| 4h | mid | 0.60 | 0.65 |
| 4h | small | 0.75 | 0.70 |

These are **not hard-fails** — they set where penalty scoring begins.

---

## Step 5: Soft/Scored Quality Gates

**File:** `backend/app/services/signals/signal_engine.py`

Replace `_check_quality_gates()` with `_score_quality_gates()`:

```python
def _score_quality_gates(self, df, params, symbol, cap_size, timeframe) -> Tuple[bool, Dict[str, float]]:
```

**Structural hard-fails** (return `(False, {})`):
- Missing/NaN required fields (close, volume, atr_percent)
- `volume <= 0` or `atr_percent <= 0`
- Fewer than **30 bars** (need EMA21 + buffer; max indicator window is 21)
- **Timeframe-aware stale check** (reads from evaluation bar):
  - 5m: stale if >10min old
  - 15m: stale if >30min old
  - 4h: **no stale check** — 4h bars only close ~2x/day (10:30, 14:30 ET), so "last closed bar" is often hours old and that's expected. The 4h evaluation bar uses the current partial bar instead (accepted tradeoff: partial volume for 4h).
  - Skip stale check in first 5-10min after open (no closed bars yet for 5m/15m)
- `tod_avg_dollar_volume` below liquidity floor (uses fallback `close * volume_ma20` when TOD median unavailable — see Step 2)

**Soft-score ATR%** (penalties feed confidence):
- `>= pivot`: 0 penalty; `>= pivot * 1.5`: +5 bonus
- `50%-100%` of pivot: linear -15 to 0
- `< 50%` of pivot: -20
- `> max_atr_percent`: -10 (choppy)

**Soft-score RVOL** (uses `effective_rvol = rvol_tod ?? rvol`):
- `>= pivot`: 0; `>= pivot * 1.5`: +5; `>= pivot * 2.0`: +10
- `50%-100%` of pivot: linear -15 to 0
- `< 50%`: -20

**4h partial-bar RVOL adjustment**: The 4h eval bar is partial, so raw volume looks "low" early in the window. Compute **volume pace** for 4h: `paced_volume = volume / elapsed_fraction` where `elapsed_fraction = minutes_since_bar_open / 240`. Then `rvol_tod = paced_volume / tod_median_volume`. This normalizes a half-filled 4h bar to its expected full-bar pace, avoiding systematic RVOL penalties early in the window. If `elapsed_fraction < 0.1` (< 24 min into bar), return RVOL score = 0 (neutral — too early to judge pace). Apply the same pace adjustment to `tod_avg_dollar_volume` for 4h liquidity floor checks.

Returns `(True, {"atr_score": float, "rvol_score": float})`.

---

## Step 6: IV Quality Score (LEAPS-friendly)

**File:** `backend/app/services/signals/signal_engine.py`

Add `_fetch_iv_rank(symbol)` — **single fetch, shared by IV scoring + earnings risk**:
- Fetch IV rank from TastyTrade: `tastytrade_service.get_iv_rank(symbol)`
- If unavailable, return `None`
- Called once per symbol in `process_queue_item()` and passed to both `_score_iv_quality()` and `_score_earnings_risk()`

Add `_score_iv_quality(iv_rank, cap_size)`:
- Takes `iv_rank` as parameter (already fetched — no duplicate call)
- If `iv_rank is None`, return 0 (neutral — don't block)

**Large/Mid cap IV scoring** (iv_rank 0-100):
| IV Rank | Score |
|---------|-------|
| ≤ 20 | +5 (cheap vol tailwind) |
| 21-50 | 0 |
| 51-70 | -5 |
| 71-85 | -12 |
| > 85 | -20 |

**Small cap IV scoring** (tolerate higher baseline):
| IV Rank | Score |
|---------|-------|
| ≤ 25 | +5 |
| 26-60 | 0 |
| 61-80 | -5 |
| 81-90 | -12 |
| > 90 | -20 |

---

## Step 7: Earnings Risk Overlay

**File:** `backend/app/services/signals/signal_engine.py`

Add `_score_earnings_risk(symbol, iv_rank)`:
- Takes `iv_rank` as parameter (already fetched in `_fetch_iv_rank()` — no duplicate call)
- Fetch earnings date from `catalyst.get_earnings_date(symbol)`
- If `days_to_earnings ≤ 14`:
  - If `iv_rank is not None and iv_rank >= 70`: return -10 (inflated IV into earnings)
  - Else: return -5 (gap risk)
- Otherwise: return 0

---

## Step 8: Options Execution Overlay

**File:** `backend/app/services/signals/signal_engine.py`

Add `_check_options_eligibility(symbol, direction, cap_size)`:
- Fetch options chain via `yahoo_service.get_options_chain(symbol, include_leaps=True)`
- Find nearest monthly expiration in **150-210 DTE** window (or closest ≥140)
- Use **strike proximity** as delta proxy (~0.30-0.50 delta at 150-210 DTE):
  - Calls (bullish): **100-110%** of spot (ATM to slightly OTM)
  - Puts (bearish): **90-100%** of spot (slightly OTM to ATM)
- Check at least one contract in that band meets:

| Criteria | Large | Mid | Small |
|----------|-------|-----|-------|
| OI floor | ≥ 500 | ≥ 300 | ≥ 150 |
| Spread cap (spread/mid) | ≤ 12% | ≤ 12% | ≤ 18% |

- Also require underlying ADDV (use **daily** volume from `yahoo_service.get_stock_info()` or cached daily stats — NOT intraday bar volume): Large ≥ $150M, Mid ≥ $75M, Small ≥ $30M
- **Defensive guardrails**:
  - If `mid_price == 0` (missing bid or ask): treat contract as illiquid, skip it
  - If `bid` or `ask` is `None`/`NaN`: skip contract
  - If `spread / mid > 1.0` (spread exceeds mid — data anomaly): skip contract
  - If no contracts pass all checks in the band, return `{"options_eligible": False, "reason": "no qualifying contracts in strike band"}`
- Returns `{"options_eligible": bool, "best_strike": float, "dte": int, "oi": int}` or `{"options_eligible": False, "reason": str}`

**This does NOT block signal generation.** Signals fire as equity-eligible; options eligibility is metadata attached to the signal. The `TradingSignal` record will include `options_eligible` and `options_details` in its data.

---

## Step 9: Updated Confidence Formula

**File:** `backend/app/services/signals/signal_engine.py`

Update `_calculate_confidence(df, direction, params, gate_scores=None, iv_score=0, earnings_score=0)`:

| Component | Points | Range |
|-----------|--------|-------|
| Base | 50 | fixed |
| Trend alignment | EMA8/EMA21 + price position | 0 to +20 |
| Momentum (RSI) | RSI thresholds | 0 to +15 |
| Volume confirmation | volume_spike + effective_rvol tiers | 0 to +20 |
| ATR quality | ATR well above min | 0 to +5 |
| **Gate: ATR** | from `gate_scores` | -20 to +5 |
| **Gate: RVOL** | from `gate_scores` | -20 to +10 |
| **IV quality** | from `_score_iv_quality()` | -20 to +5 |
| **Earnings risk** | from `_score_earnings_risk()` | -10 to 0 |

Clamped 0-100. Theoretical max 125 → 100. Practical floor ~10.

**Volume confirmation** component must use `effective_rvol` (rvol_tod ?? rvol) consistently.

---

## Step 10: MIN_CONFIDENCE Filter

**File:** `backend/app/services/signals/signal_engine.py`

```python
MIN_CONFIDENCE = 60  # Start here for mixed caps + all-day scanning
```

In `process_queue_item()`, after strategy returns a signal:
```python
if signal and signal.get('confidence', 0) < MIN_CONFIDENCE:
    logger.debug(f"{symbol} signal rejected: confidence {confidence} < {MIN_CONFIDENCE}")
    signal = None
```

Tuning: `<5/day → 58 → 55` | `>30/day → 62 → 65`

---

## Step 11: Thread Everything Through process_queue_item()

**File:** `backend/app/services/signals/signal_engine.py`

Updated flow in `process_queue_item()`:

```python
def process_queue_item(self, item, db):
    # 1. Classify cap size (fetch market_cap if item.cap_size is None)
    cap_size = item.cap_size or self._resolve_cap_size(item.symbol, db)

    # 2. Get bars with enhanced indicators (TOD-RVOL included)
    #    No limit arg — function selects TOD_BAR_LIMITS[timeframe] internally
    df, eval_idx = alpaca_service.get_bars_with_enhanced_indicators(symbol, timeframe)

    # 3. Score quality gates (structural fail or soft penalties)
    #    Reads from df.iloc[eval_idx] — same bar as TOD-RVOL, ATR%, etc.
    passes, gate_scores = self._score_quality_gates(df, params, symbol, cap_size, timeframe, eval_idx)
    if not passes: return None

    # 4. Fetch iv_rank ONCE, pass to both scorers (avoids duplicate TastyTrade call)
    iv_rank = self._fetch_iv_rank(symbol)
    iv_score = self._score_iv_quality(iv_rank, cap_size)
    earnings_score = self._score_earnings_risk(symbol, iv_rank)

    # 5. Check strategies (pass gate_scores, iv_score, earnings_score, eval_idx)
    signal = self._check_orb_breakout(symbol, df, params, cap_size, timeframe, gate_scores, iv_score, earnings_score, eval_idx)
    if not signal: signal = self._check_vwap_pullback(..., eval_idx)
    if not signal: signal = self._check_range_breakout(..., eval_idx)

    # 6. MIN_CONFIDENCE filter
    if signal and signal['confidence'] < MIN_CONFIDENCE:
        signal = None

    # 7. Check options eligibility (metadata, not a blocker)
    if signal:
        options_info = self._check_options_eligibility(symbol, signal['direction'], cap_size)
        signal['options_eligible'] = options_info.get('options_eligible', False)
        signal['options_details'] = options_info

    # 8. Create record + notify
    if signal:
        trading_signal = self._create_signal_record(signal, item, db)
        ...
```

---

## Step 12: Market Hours Guard

**File:** `backend/app/main.py`

In `check_signals_job()`, add at top:

```python
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
now_et = datetime.now(ET)

if now_et.weekday() >= 5:  return          # weekends
market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
if now_et < market_open or now_et > market_close:  return
```

**Holiday handling**: Add a lightweight `_is_market_open()` check using Alpaca's clock API (`alpaca_service.get_clock()`) at the start of each cycle. If `clock.is_open == False`, skip the entire cycle. This catches holidays, early closes, and any other non-trading day without maintaining a holiday calendar. One API call per 5-min cycle is negligible and saves all downstream calls on holidays.

---

## Step 13: Monitoring / Diagnostic Logging

**File:** `backend/app/services/signals/signal_engine.py`

In `process_all_queue_items()`, log per-cycle stats:

```
📡 Signal engine cycle: 39 items | structural_fail: 2 | heavy_atr_penalty: 8 | heavy_rvol_penalty: 5 |
   equity_eligible: 24 | options_eligible: 14 | signals: 3 | rejected_low_conf: 7
```

Track per cycle:
- Structural failure rate (target <5%)
- Heavy ATR penalty rate (target ~10-25%)
- Heavy RVOL penalty rate (target ~10-25%)
- **`rvol_tod_available` count/%** — quickest indicator that TOD history fetch and time-matching logic are working correctly (target: >80% during midday, lower in first 30min)
- % equity-eligible vs options-eligible
- Signals/day (target 5-30)
- Distribution of iv_rank for generated signals
- % signals flagged "earnings soon"

Updated log line:
```
📡 Signal engine cycle: 39 items | due: 25 | cadence_skip: 14 | same_bar_skip: 3 |
   structural_fail: 2 | tod_rvol_avail: 20/22 (91%) | heavy_atr_penalty: 5 | heavy_rvol_penalty: 3 |
   equity_eligible: 15 | options_eligible: 9 | signals: 2 | rejected_low_conf: 4
   api_calls: alpaca=25 tastytrade=22 yahoo=2 catalyst=22
```

API call counters prove cadence + same-bar savings. Increment per-cycle counters at each call site: Alpaca `get_bars()`, TastyTrade `get_iv_rank()`, Yahoo `get_options_chain()` / `get_stock_info()`, Catalyst `get_earnings_date()`. Use a simple dict passed through the cycle or a cycle-scoped counter on the engine instance.

---

## Step 14: Timeframe Scheduling Guard

**Files:** `backend/app/services/signals/signal_engine.py`, `backend/app/models/signal_queue.py`

Single scheduler job stays at 5 minutes. `process_all_queue_items()` skips items that aren't due yet, **before** any Alpaca/Yahoo/TastyTrade calls.

### Cadence gating (per-item, timestamp-based)

`minute % interval == 0` breaks when the scheduler isn't cron-aligned (APScheduler interval trigger starts from boot time, e.g. :07/:12/:17). Use per-item timestamps instead:

```python
SCAN_CADENCES_SECONDS = {"5m": 300, "15m": 900, "4h": 1800}  # seconds between scans

def _is_item_due(self, item: SignalQueue, now: datetime) -> bool:
    interval = self.SCAN_CADENCES_SECONDS.get(item.timeframe, 300)
    if item.last_checked_at is None:
        return True  # never checked → always due
    elapsed = (now - item.last_checked_at).total_seconds()
    return elapsed >= interval
```

In `process_all_queue_items()`, filter before any API calls:

```python
now = datetime.utcnow()
items_due = [i for i in active_items if self._is_item_due(i, now)]
cadence_skipped = len(active_items) - len(items_due)
```

`last_checked_at` already exists on `SignalQueue` and is updated in `process_queue_item()`, so this works with no schema change. Works regardless of scheduler alignment.

**Call savings**:
- 15m items: ~66% fewer cycles (every 15m vs 5m)
- 4h items: ~83% fewer cycles (every 30m vs 5m)

### "New eval bar?" short-circuit

Even when an item is due, it may still be evaluating the same bar (data delays, no new bar yet). After fetching `(df, eval_idx)` but **before** gates/strategies/IV/options:

1. Add `last_eval_bar_key` column to `SignalQueue` model:

```python
# In signal_queue.py
last_eval_bar_key = Column(String(100), nullable=True)  # "2026-02-03T10:30:00Z" or "2026-02-03T10:30:00Z|185.23|4521300" for 4h
```

2. In `process_queue_item()`, after getting `(df, eval_idx)`:

**Critical**: update `last_checked_at` **immediately after the Alpaca fetch**, before the same-bar check. If we only update it after full processing, same-bar skips would leave `last_checked_at` stale, causing `_is_item_due()` to return `True` every cycle and re-fetching bars unnecessarily.

```python
# Update last_checked_at RIGHT AFTER Alpaca fetch (before same-bar check)
item.times_checked += 1
item.last_checked_at = datetime.utcnow()

eval_bar = df.iloc[eval_idx]
eval_bar_ts = df.index[eval_idx] if isinstance(df.index, pd.DatetimeIndex) else eval_bar.get('timestamp')

# Normalize to UTC string for consistent storage/comparison
# Alpaca timestamps are UTC-aware; if naive (shouldn't happen), treat as UTC
eval_ts_utc = eval_bar_ts.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if eval_bar_ts.tzinfo else eval_bar_ts.strftime('%Y-%m-%dT%H:%M:%SZ')

if timeframe == "4h":
    # 4h uses partial bar → timestamp stays constant for hours.
    # Use fingerprint: ts + close + volume to detect meaningful changes.
    eval_key = f"{eval_ts_utc}|{eval_bar['close']:.2f}|{int(eval_bar['volume'])}"
else:
    # 5m/15m use last closed bar → new timestamp = new bar
    eval_key = eval_ts_utc

if item.last_eval_bar_key == eval_key:
    logger.debug(f"{symbol} same eval bar {eval_key} — skipping")
    db.commit()  # persist last_checked_at update
    return None

item.last_eval_bar_key = eval_key
```

**Why fingerprint for 4h?** The 4h eval bar uses the current partial bar (Step 2/5). Its timestamp stays constant for the full 4-hour window. With timestamp-only comparison, you'd evaluate once at bar open and skip every 30-min cycle after — defeating the purpose of 30-min cadence. The fingerprint `(ts, close, volume)` changes as the partial bar fills, ensuring re-evaluation when price/volume move meaningfully.

**5m/15m don't need fingerprints** — they use the last *closed* bar, so a new timestamp always means new data.

This prevents wasting compute on gates/strategies/IV/options/earnings when the underlying data hasn't changed. The Alpaca `get_bars()` call still happens (needed to check for new bar), but all downstream calls (TastyTrade IV, Yahoo options chain, catalyst earnings) are skipped.

**Migration**: `alembic revision --autogenerate -m "add last_eval_bar_key to signal_queues"` + `alembic upgrade head`

Also add `last_eval_bar_key` to `to_dict()` for API visibility.

---

## Files Modified (4 files)

| File | Changes |
|------|---------|
| `backend/app/services/data_fetcher/alpaca_service.py` | `get_time_of_day_rvol()` (median, ≥5 samples, evaluation bar, fallback to volume_ma20) + `get_bars_with_enhanced_indicators()` (auto-selects `TOD_BAR_LIMITS[timeframe]`, returns `(df, eval_idx)`, adds `rvol_tod` + `tod_avg_dollar_volume` on eval bar) |
| `backend/app/services/signals/signal_engine.py` | Add mid_cap to PARAMS, `_classify_cap_size()`, `_fetch_iv_rank()` (single fetch shared by IV + earnings), `_score_quality_gates()` (soft + liquidity floors, 4h skips stale check), `_score_iv_quality(iv_rank, cap_size)`, `_score_earnings_risk(symbol, iv_rank)`, `_check_options_eligibility()` (strike proximity proxy + defensive guardrails, not a blocker), updated `_calculate_confidence()` (+IV +earnings +gate scores), `MIN_CONFIDENCE=60` filter, enhanced diagnostic logging with `rvol_tod_available` metric, thread everything through `process_queue_item()` with `eval_idx`, `SCAN_CADENCES_SECONDS` + `_is_item_due()` per-item cadence gating (timestamp-based, scheduler-alignment-safe), "new eval bar?" short-circuit with fingerprint for 4h partial bars |
| `backend/app/models/signal_queue.py` | Add `last_eval_bar_key` column (String(100), nullable) + update `to_dict()` |
| `backend/app/main.py` | Market hours guard in `check_signals_job()` + Alpaca clock API check for holidays |

---

## Verification

1. **Market hours guard**: Server outside hours → no signal processing. During hours → processing logged
2. **TOD-RVOL**: Logs show `rvol_tod` values; midday values higher than classic `rvol` for same bars
3. **Liquidity floors**: Small-cap with tiny dollar volume → structural fail logged
4. **Soft gates**: Previously-blocked stocks now get scored; some produce signals with penalties
5. **IV scoring**: High-IV stocks show negative iv_score in logs; low-IV stocks get bonus
6. **Earnings overlay**: Stocks within 14 days of earnings show penalty
7. **Options eligibility**: Signals include `options_eligible: true/false` with strike/DTE details
8. **Signal generation**: First signals appear during market hours. Bell icon + Telegram fire
9. **Tuning (1-2 days)**: Check signals/day. Adjust MIN_CONFIDENCE if outside 5-30 range
10. **Diagnostic dashboard**: Per-cycle log line shows structural/penalty/eligibility breakdown
11. **Cadence gating**: 15m items show ~900s between checks regardless of scheduler boot time; 4h items show ~1800s. Log shows `cadence_skip: N` with correct counts per cycle.
12. **New eval bar short-circuit**: Repeated runs on same bar show "same eval bar — skipping" in debug logs, no downstream IV/options/earnings calls. Verify `last_checked_at` still updates on same-bar skips (prevents re-fetching bars every cycle).
13. **API call counters**: Per-cycle log shows `alpaca: N | tastytrade: N | yahoo: N` — verify cadence + same-bar skip are delivering expected savings vs baseline.