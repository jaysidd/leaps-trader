# LEAPS Trader — Session Summary

> **Last updated**: 2026-02-14
> **Purpose**: Comprehensive snapshot for resuming work in a new CLI session.

---

## 1. Project Status

**LEAPS Trader** is a full-stack automated options trading system focused on LEAPS (Long-Term Equity Anticipation Securities). It screens stocks, generates signals, validates with AI, manages risk, and executes trades.

### Stack
- **Backend**: FastAPI + SQLAlchemy + APScheduler + PostgreSQL + Redis (port 8000)
- **Frontend**: React 19 + Vite + Zustand + Tailwind (port 5176)
- **Integrations**: Alpaca (trading/data), FMP (fundamentals), Finviz (screening), Claude AI (validation), Telegram (alerts), FRED (macro), Robinhood (portfolio)

### System Health
- **Backend**: 20 API routers, 9 scheduler jobs, deployed on Railway
- **Frontend**: 11 pages, 8 Zustand stores, 50+ components
- **Test suite**: 228 pipeline+replay tests (227 pass, 1 skip), ~1.1s, zero API calls
- **Production**: Auto-scan running every 30 min during market hours

---

## 2. What We Built (Recent Sessions, 2026-02-12 to 2026-02-14)

### PresetSelector Overhaul (the main focus)
The PresetSelector is the brain that reads market conditions and picks which screening presets to run. It was fundamentally broken:

1. **Old system**: Priority-chain where any single signal (e.g., `readiness_label="yellow"`) could veto everything else. Scanner was permanently locked into `cautious` (only conservative + blue_chip presets).

2. **New system**: Weighted composite scoring. Four signals contribute proportionally:
   - Market Regime: 35% (bullish/neutral/bearish from SPY technicals)
   - MRI (Macro Risk Index): 30% (from macro service)
   - Fear & Greed: 20% (CNN API with VIX-based fallback)
   - Trade Readiness: 15% (FRED + regime proxy)

   Score maps to condition: >=50 aggressive_bull, >=20 moderate_bull, >=0 neutral, >=-20 cautious, >=-50 defensive, <-50 skip

3. **5 showstopper bugs fixed**: Typo in preset name, TTL mismatch, `confidence=0` treated as falsy, stale docstring, silent fallback in automation paths.

4. **Preset catalog extracted**: `LEAPS_PRESETS` moved from `screener.py` to standalone `app/data/presets_catalog.py` with `resolve_preset()` fail-fast helper, `get_catalog_hash()` for versioning, and startup validation.

### Replay Harness
Built a historical replay system that replays past trading days through all 7 pipeline layers:
- `ReplayClock`: Simulated time advancement
- `ReplayMarketIntelligence`: Computes regime/F&G/readiness from SPY daily bars
- `ReplayDataService`: Patches Alpaca singletons with cached historical data
- `ReplayTradingService`: Virtual account with simulated fills
- `ReplayAuditLog`: Captures every pipeline decision with JSON blobs

### Test Infrastructure
- **222 pipeline tests** across 7 layers (conftest.py, helpers, mock_stocks, mock_market, 7 layer test files, quality gates, full pipeline)
- **6 replay E2E tests** (corner fixtures + mid-band discovery)
- **All tests**: zero API calls, ~1.1s total runtime

---

## 3. Current Work: PresetSelector Replay Testing (COMPLETE)

### What was decided
The PresetSelector testing phase is **done**. We validated through two complementary approaches:

**Unit tests (222 in pipeline/):** Pin exact math, boundary conditions, failure resilience, panic override, weight renormalization, cache behavior — all 6 market conditions tested with precise snapshot fixtures.

**Replay E2E tests (6 in replay/):** Prove the full plumbing works (bars -> signals -> patched caches -> PresetSelector) with real-ish bar-derived data:

| Test | Fixture | Score | Condition | What it validates |
|------|---------|-------|-----------|-------------------|
| E2E-01 | Neutral (sideways) | +17.8 | neutral | Never defensive/skip on sideways |
| E2E-02 | Bull (uptrend) | +78.2 | aggressive_bull | Strong bull -> aggressive presets |
| E2E-03 | Bear (downtrend) | -47.4 | defensive | Never aggressive on bear day |
| E2E-04 | Panic (crash+MRI) | -79.9 | skip | Panic override (MRI>80 + F&G<10) |
| E2E-05 | Bull (x2 runs) | +78.2 | aggressive_bull | Determinism + no state leakage |
| E2E-06 | 7 candidates | varies | varies | Mid-band discovery (moderate_bull hit) |

### Why we stopped here
- 4 of 6 conditions covered by replay (aggressive_bull, neutral, defensive, skip)
- moderate_bull and cautious covered by E2E-06 discovery approach + 113 unit tests
- Mixed signals (conflicting regime + F&G) can't be naturally produced from single SPY bar fixtures
- Diminishing returns from further fixture tuning

---

## 4. Architecture Decisions Made

### Scoring System
- **Weighted composite** instead of priority-chain: No single signal can dominate (except panic override)
- **Weight redistribution**: When a signal is missing (e.g., MRI=None), its weight distributes proportionally to available signals
- **Panic override**: Only hard override — requires BOTH MRI>80 AND F&G<10

### Preset Catalog
- **Extracted to standalone module**: `app/data/presets_catalog.py` — eliminates circular import risk
- **`resolve_preset()`**: Single gatekeeper for all non-UI preset resolution. Strict mode raises on unknown presets.
- **Startup validation**: `_validate_preset_catalog()` runs once on first `get_preset_selector()` call

### Replay Testing Strategy
- **Corner fixtures**: Bull, neutral, bear, panic — test extreme behaviors
- **Mid-band discovery**: Try multiple parameterizations, assert >=1 hits target band — robust to formula tweaks
- **Condition buckets, not exact scores**: Assertions check `condition in (...)` not `score == 41.7`

### Test Philosophy
- **Unit tests**: Pin exact math, catch regressions, test all edge cases
- **Replay E2E tests**: Validate plumbing (data flow through real services), not math

---

## 5. Next Steps & Priorities

### Immediate (P1)
1. **Fix live confidence scale bug** (BACKLOG P1 #11)
   - File: `backend/app/services/ai/market_regime.py`
   - `analyze_regime_rules()` returns confidence 1-10 but PresetSelector expects 0-100
   - Same fix as replay path: `confidence = min(int(confidence * 12.5), 100)`
   - This is the **highest-priority known bug** — regime signal (35% weight) is nearly zeroed out in production

2. **Synchronous Anthropic client** (BACKLOG P1 #3)
   - `services/ai/claude_service.py` blocks the event loop during AI calls
   - Needs `AsyncAnthropic` migration

3. **CI/CD pipeline** (BACKLOG P1 #7)
   - 228 tests exist but no automation on commit/PR

### Medium Term (P2)
4. **Typed StrategyProfile objects** (BACKLOG P2 #22) — replace string preset names with dataclasses
5. **Frontend tests** (BACKLOG P1 #8) — 50+ components with zero tests
6. **Trading pipeline test coverage** — auto_trader.py and order_executor.py have zero tests

### Deferred
- TypeScript migration (P2)
- WebSocket expansion (P3)
- Backtest visualization (P3)

---

## 6. Gotchas & Critical Context

### PresetSelector
- `confidence=0` is falsy in Python — always use `if confidence is not None`
- `_classify_condition()` takes TWO args `(score, snapshot)` — callers must call `_compute_composite_score()` first
- Missing signals redistribute weight — removing MRI makes regime jump from 35% to ~50%

### Replay Fixtures
- **Daily noise % != VIX proxy**: 1.6% noise produced VIX proxy 52 (2008-level). Always verify actual VIX output.
- **Without MRI**: Panic override is disabled (needs both MRI>80 AND F&G<10). Cautious band (-20 to 0) is nearly unreachable.
- **Deterministic**: All fixtures use seeded RNG (`np.random.default_rng(seed)`)

### Alpaca
- `ContractType` enum: use `.value` not `str()` — `str(ContractType.CALL)` = `"contracttype.call"`
- Option snapshots require `OptionHistoricalDataClient`, NOT `StockHistoricalDataClient`
- `TradingClient` has NO built-in timeout — monkey-patched via `_session.request`
- Off-hours snapshots return empty data — IV=0.0 and OI=0 treated as UNKNOWN, not real values

### Data Providers
- FMP `/stable/` field names differ from v3 — always check actual response
- CNN Fear & Greed API returns 418 (bot detection) — falls through to VIX-based fallback
- FMP cache uses Redis with 4h TTL — flush after changing screener params: `r.keys('fmp:*')` then `r.delete(*keys)`

### Infrastructure
- Backend port 8000, Frontend port 5176 (NOT 5173/5174 — those are other apps)
- Use `python3` not `python` (macOS)
- Activate venv: `source venv/bin/activate`
- DB endpoints: always `Depends(get_db)`, never manual `SessionLocal()`

---

## 7. Key Files Quick Reference

| Purpose | File |
|---------|------|
| FastAPI app + scheduler | `backend/app/main.py` |
| PresetSelector (scoring) | `backend/app/services/automation/preset_selector.py` |
| Preset catalog (data) | `backend/app/data/presets_catalog.py` |
| Screening engine | `backend/app/services/screening/engine.py` |
| Signal engine | `backend/app/services/signals/signal_engine.py` |
| Auto trader | `backend/app/services/trading/auto_trader.py` |
| Market regime detector | `backend/app/services/ai/market_regime.py` |
| Replay harness | `backend/scripts/replay/replay_trading_day.py` |
| Replay services | `backend/scripts/replay/replay_services.py` |
| Pipeline tests (222) | `backend/tests/pipeline/` |
| Replay tests (6) | `backend/tests/replay/` |
| Architecture reference | `ARCHITECTURE.md` |
| Backlog / issues | `BACKLOG.md` |
| Agent rules / gotchas | `.claude/CLAUDE.md` |

---

## 8. Test Commands

```bash
# All pipeline + replay tests (228 total)
cd backend && source venv/bin/activate
python3 -m pytest tests/pipeline/ tests/replay/ -v

# Just replay E2E tests
python3 -m pytest tests/replay/ -v -m replay

# Just pipeline unit tests
python3 -m pytest tests/pipeline/ -v

# Single test with full output
python3 -m pytest tests/replay/test_replay_preset_selector_e2e.py::test_mid_band_discovery -v -s

# Pipeline diagnostic (real data, color-coded)
python3 scripts/diagnose_pipeline.py --layer 1  # PresetSelector only
python3 scripts/diagnose_pipeline.py             # All 7 layers

# Historical replay
python3 scripts/replay/replay_trading_day.py 2026-02-10 --symbols SSRM,NVDA --interval 15
```

---

## 9. Session Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-13 | Replace priority-chain with weighted composite scoring | Single-signal veto locked scanner to `cautious` permanently |
| 2026-02-13 | Extract LEAPS_PRESETS to standalone module | Circular import risk + need for `resolve_preset()` gatekeeper |
| 2026-02-14 | Fix 5 PresetSelector showstopper bugs | B1-B5 all discovered during comprehensive test creation |
| 2026-02-14 | Use condition buckets not exact scores in replay tests | Exact scores are fragile — formula tweaks break tests |
| 2026-02-14 | Discovery approach for mid-band testing | Cautious band too narrow to pin; try multiple combos instead |
| 2026-02-14 | Defer live confidence scale fix | Replay path fixed; live fix is P1 #11 but needs separate session |
| 2026-02-14 | Stop PresetSelector testing, move on | 228 tests across unit+E2E, all 6 conditions covered, diminishing returns |
