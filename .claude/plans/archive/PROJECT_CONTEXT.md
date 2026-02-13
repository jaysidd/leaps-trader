# Project Context — Multi-Strategy Queue System

## Current Focus
**Status**: All 8 phases implemented + 2 rounds of deep code review completed. All CRITICAL, HIGH, and MEDIUM findings fixed.

## What Was Built: 4-Layer Intelligence Pipeline

```
Layer 1: SCREENING (existing) → Finviz/FMP universe → 4-stage filter → 25-30 scored stocks
Layer 2: STRATEGY SELECTION (new) → Fresh FMP indicators → rules-based timeframe assignment
Layer 3: SIGNAL ENGINE (enhanced) → 1h + Daily params, Trend Following + Mean Reversion
Layer 4: AI PRE-TRADE VALIDATION (new) → Claude reviews signals before bot execution
```

## Phases Completed

### Phase 1: Timeframe Infrastructure
- Removed 4H, formalized 1H and Daily timeframes
- Added `SCAN_CADENCES_SECONDS`, `LIQUIDITY_FLOORS`, `PARAMS` for 1h and 1d
- Same-bar short-circuit logic for 1h (timestamp-based) and 1d (date-based)
- Frontend timeframe dropdowns updated

### Phase 2: FMP Technical Indicators
- `get_technical_indicator()`, `get_strategy_metrics()`, `get_bulk_strategy_metrics()`
- Redis caching with 1h TTL
- Async semaphore (5 concurrent) for bulk fetches

### Phase 3: StrategySelector Service
- Rules engine with configurable thresholds per timeframe
- Confidence calculation: HIGH (auto-queue), MEDIUM (review), LOW (skip)
- Edge case detection (overbought, low volume, wide spread, etc.)

### Phase 4: ScanProcessor API
- POST /scan-processing/process — Run StrategySelector on saved scan
- POST /scan-processing/ai-review — Claude batch review of MEDIUM stocks
- POST /scan-processing/queue-reviewed — Queue approved stocks

### Phase 5: AI Pre-Trade Validation
- SignalValidator fetches FRESH Alpaca data, re-checks setup validity
- Claude AI review with confidence scoring (>=75 auto-execute, 40-74 manual review, <40 reject)
- Persists validation_status, validation_reasoning, validated_at on TradingSignal

### Phase 6: Scheduled Scan Automation
- APScheduler CronTrigger job for auto-scan
- Configurable presets, schedule time, auto-process toggle
- Telegram summary notification

### Phase 7: Frontend Changes
- SavedScans: Auto-Process button + results panel + AI Review modal
- SignalQueue: confidence_level + strategy_reasoning display
- Settings: AutomationTab with scan config

### Phase 8: Backtesting Updates
- TrendFollowingStrategy + MeanReversionStrategy added to Backtrader
- Backtesting.jsx updated with new strategy options + timeframe mappings

---

## Deep Code Review: Round 1 Findings (All Fixed)

### CRITICAL (6) — All Fixed
| # | Issue | File | Fix |
|---|-------|------|-----|
| C1 | auto_scan_job called non-existent method | main.py | Rewrote to use screening engine directly |
| C2 | get_bulk_strategy_metrics wrong async pattern | fmp_service.py | Changed to proper async with _run_sync pattern |
| C3 | FMP tech indicator key mismatch | fmp_service.py | Aligned with actual FMP API response keys |
| C4 | Dead TF code: no SMA20/ADX indicators | signal_engine.py | Added SMA20, ADX, pullback zone indicators |
| C5 | Backtrader params inheritance broken | strategies.py | All subclasses now include full base params |
| C6 | Backtrader key names misaligned | strategies.py | sma_short/min_adx/pullback_pct aligned with signal engine |

### HIGH (14) — All Fixed
| # | Issue | File | Fix |
|---|-------|------|-----|
| H1 | analyze_batch doesn't exist on ClaudeService | scan_processing.py | Replaced with direct call_claude() |
| H2 | AnalysisResult attribute error | scan_processing.py | Use response_text + parser.extract_json() |
| H3 | Missing PARAMS for 1h timeframe | signal_engine.py | Added 3 cap-size dicts for 1h |
| H4 | Missing PARAMS for 1d timeframe | signal_engine.py | Added 3 cap-size dicts for 1d |
| H5 | datetime.utcnow() deprecated + tz mismatch | signal_validator.py | datetime.now(timezone.utc) + tz normalization |
| H6 | FMP bulk fetch unbounded concurrency | fmp_service.py | Semaphore(5) + to_thread for rate limiter |
| H7 | 1d bar fetch: no Alpaca endpoint for daily | signal_engine.py | Falls back to daily snapshot data |
| H8 | Missing SCAN_CADENCES for 1h/1d | signal_engine.py | Added 1800s (1h) and 14400s (1d) |
| H9 | VALID_CAP_SIZES missing mid_cap | signals.py | Added "mid_cap" to set |
| H10 | auto_scan_job missing scheduler job | main.py | Added CronTrigger job |
| H11 | TF params: stop_atr_mult=0.5 (too tight) | strategies.py | Changed to 1.5 (matches signal engine) |
| H12 | TF params: pullback_pct=2.0 (divergent) | strategies.py | Changed to 0.5 (matches signal engine) |
| H13 | MR strategy: no sma20 indicator for target | strategies.py | Added self.sma20 = bt.ind.SMA(..., period=20) |
| H14 | Settings AutomationTab keys not prefixed | Settings.jsx | Prefixed all with "automation." |

### MEDIUM (20+) — All Fixed
- BB std deviation: ddof=0 (population, matches Backtrader/TradingView)
- New strategy fields (sma20/50/200, adx, bb_upper/mid/lower) in institutional_data
- Public call_claude() wrapper on ClaudeService
- FMP cache falsiness: `if cached is not None:` instead of `if cached:`
- Sell-side chasing check added to signal_validator
- Signal age timezone comparison fixed

---

## Deep Code Review: Round 2 Findings (All Fixed)

### HIGH (5) — All Fixed
| # | Issue | File | Fix |
|---|-------|------|-----|
| R2-H1 | ORM mutation: mutating sr.stock_data in-place | scan_processing.py | `sd = dict(sr.stock_data or {})` — copy first |
| R2-H2 | DECIMAL(0) falsy: `if sr.score` fails for 0 | scan_processing.py | `if sr.score is not None` |
| R2-H3 | AI response type inconsistent | scan_processing.py | Wrapped in `{"raw_response": ..., "parse_error": True}` |
| R2-H4 | Partial commits in batch validation | signal_validator.py | `db.flush()` instead of `db.commit()` |
| R2-H5 | TF else block fires on all non-uptrend | strategies.py | Independent `if downtrend` check |

### MEDIUM (8) — All Fixed
- Edge case string mismatch in strategy_selector ("no sma data" vs "missing sma")
- MR entry logic rewritten to use crossover/reclaim pattern
- TF entry logic rewritten to use crossover pattern matching signal engine

---

## Deferred Items (Pre-existing, Not From This Work)
- Synchronous Anthropic client blocks event loop (needs AsyncAnthropic migration)
- Earnings risk scoring silently fails (event loop mismatch in worker thread)
- asyncio.create_task() from worker thread for Telegram (not thread-safe)
- Multi-snapshot shape mismatch (spread/volume always None in bulk path)
- Zero tests for trading pipeline (#39)

---

## Files Created
- `backend/app/services/signals/strategy_selector.py`
- `backend/app/services/signals/signal_validator.py`
- `backend/app/api/endpoints/scan_processing.py`
- `frontend/src/api/scanProcessing.js`

## Files Modified (This Session's Bug Fixes)
- `backend/app/services/backtesting/strategies.py` — params inheritance, key alignment, entry logic
- `backend/app/api/endpoints/scan_processing.py` — ORM mutation, DECIMAL, AI response, call_claude
- `backend/app/services/signals/signal_validator.py` — timezone, flush, sell-side chasing
- `backend/app/api/endpoints/signals.py` — VALID_CAP_SIZES
- `frontend/src/pages/Settings.jsx` — AutomationTab key prefixes
- `backend/app/services/data_fetcher/fmp_service.py` — semaphore, rate limiter, cache
- `backend/app/services/signals/signal_engine.py` — institutional_data, BB ddof
- `backend/app/services/ai/claude_service.py` — public call_claude() wrapper
- `backend/app/services/signals/strategy_selector.py` — edge case string fix

## Next Steps
- Restart backend + frontend to test all changes
- Run full pipeline test: scan → auto-process → signal generation → validation
- Optional: Address deferred architectural items
- Optional: Run Round 3 code review for final verification
