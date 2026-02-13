## Documentation Update Rules (MANDATORY)

These rules are **not optional**. Every agent MUST follow them before ending a session.

### When You Change Code, Update the Docs

**ARCHITECTURE.md** (project root) — Update when you:
- Add, remove, or rename a page, API router, service, model, store, or scheduler job
- Change a data flow or pipeline (screening, signal-to-trade, backtesting)
- Add a new integration or data provider
- Change middleware, infrastructure, or background job behavior
- Discover a new gotcha or fix an existing one in the "Data Provider Gotchas" section
- Add the change to the "Changelog" section at the bottom with today's date

**BACKLOG.md** (project root) — Update when you:
- Fix a bug listed there → move it to "Recently Completed"
- Discover a new bug or tech debt → add it with priority (P0-P3) and affected files
- Complete a backlog item → move it to "Recently Completed" with a one-line summary
- Defer something → add it to "Deferred Items" with reason

**This file (CLAUDE.md)** — Update when you:
- Change project rules (ports, commands, working directories)
- Discover a new data provider gotcha that future agents must know
- Change key entry points or pipeline structure

### At Session End

When the user says "save context", "sync", or "wrap up", OR when the session is ending naturally:
1. Review what you changed this session
2. Update ARCHITECTURE.md if system structure changed (add changelog entry)
3. Update BACKLOG.md if bugs were fixed or discovered
4. Do NOT skip this step — the next agent depends on accurate docs

---

## Project Rules

- **Always restart** backend (port 8000) and frontend (port 5176) after making changes
- Ports 5173/5174 belong to other apps — do NOT use them
- Use `python3` not `python` (macOS)
- Activate venv: `source venv/bin/activate` before running Python scripts
- Backend working dir: `/Users/junaidsiddiqi/leaps-trader/backend`
- Frontend working dir: `/Users/junaidsiddiqi/leaps-trader/frontend`

## Tech Stack

FastAPI + SQLAlchemy + APScheduler + PostgreSQL + Redis | React 19 + Vite + Zustand + Tailwind | Alpaca + FMP + Finviz + Claude AI + Telegram + FRED

## Key Entry Points

- `backend/app/main.py` — FastAPI app, 20 routers, 9 scheduler jobs, middleware
- `backend/app/services/screening/engine.py` — 4-stage screening pipeline
- `backend/app/services/signals/signal_engine.py` — Signal generation (5 strategies)
- `backend/app/services/trading/auto_trader.py` — Trading bot orchestrator
- `frontend/src/App.jsx` — React routes (11 pages)
- `frontend/src/stores/` — 8 Zustand stores

## Key Pipelines

**Screening**: FMP dynamic universe (1000+ stocks, fallback to hardcoded 267) → 4-stage filter (fundamental 4/5, technical 3/7, options 2/4, momentum) → composite score ≥20 cutoff → SavedScans (~25-50 stocks)
**Signal-to-Trade**: SignalQueue → SignalEngine (5min) → StrategySelector → AI Validator → AutoTrader → RiskGateway (16 checks) → PositionSizer → OrderExecutor → PositionMonitor (1min) → TradeJournal
**Backtesting**: Config → POST /run → Backtrader (max 3 concurrent via Semaphore) → poll results

## Execution Modes

- `signal_only` (default): signals appear on UI only
- `semi_auto`: queued as PENDING_APPROVAL for user approve/reject
- `full_auto`: automatic risk → size → execute pipeline
- **Manual**: Trade button on any signal → SendToBotModal → preview → confirm (no bot RUNNING required)

## Data Provider Gotchas

- FMP `/stable/` field names differ from v3 — always check actual response
- FMP sync wrappers use dedicated background event loop (`_run_sync` + `asyncio.run_coroutine_threadsafe`)
- FMP cache: use `if cached is not None:` not `if cached:` (zero/empty are valid)
- Alpaca `ContractType` enum: use `.value` not `str()` — `str(ContractType.CALL)` = `"contracttype.call"`
- Alpaca option snapshots require `OptionHistoricalDataClient`, NOT `StockHistoricalDataClient`
- Alpaca TradingClient has NO built-in timeout — monkey-patched via `_session.request`
- LEAPS DTE threshold: 250 days (not 365) — real-world expirations can be 9-10 months out
- Backtrader subclass params: MUST include ALL base params (dict replaces, not merges)
- Flush Redis FMP cache after field mapping changes: `r.keys('fmp:*')` then `r.delete(*keys)`
- Screening gate thresholds (types.py): fundamental 4/5 PASS + 4/5 KNOWN, technical 3/7 + 5/7, options 2/4 + 2/4
- Options gate soft-pass: if LEAPS exist but 0 criteria are KNOWN (no Alpaca snapshot data), allow through — downstream signal engine re-evaluates
- Alpaca option snapshots often return empty off-hours / rate limited — IV=0.0 and OI=0 treated as UNKNOWN, not PASS/FAIL
- Options IV gate threshold: 70% — LEAPS with IV above 70% are overpaying for time value
- Options liquidity minimum: 100 OI — minimum open interest for acceptable LEAPS liquidity
- Composite score minimum: 20 (engine.py) — low bar since 4-stage gates already filter heavily
- Market cap max: No default upper limit — presets control their own caps. Only small-cap/aggressive presets have explicit caps.
- Options spread threshold: 15% (options.py) — bid-ask spread max for acceptable LEAPS fills
- Options premium threshold: 20% (options.py) — max premium as % of stock price for LEAPS entry
- Signal engine gate penalty cap: -15 total (was -40 uncapped) — prevents vol/ATR from crushing valid setups
- AI validator auto-execute threshold: 65 (not 75) — stocks here passed 3 quality layers already
- DB endpoints: use `Depends(get_db)` not manual `SessionLocal()` to prevent connection leaks
- FMP screener universe cached 4h in Redis (`fmp:screener_universe:*`) — flush after changing screener params
- Auto-scan runs in interval mode (default 30min) with market-hours guard — requires server restart to change mode
- Railway pip cache: Changing requirements.txt content busts the cache. If all lines show "cached 0ms" in build logs, a dep change wasn't detected.
- alpaca-py + pandas 3.0: pandas 3.0 dropped pytz as dependency, but alpaca-py data module still requires it — must explicitly add `pytz` to requirements.txt
- alpaca-py 0.43.x: TradingClient no longer accepts `retry_attempts`, `retry_wait_seconds`, `retry_exception_codes` — removed in newer versions
- Alpaca service singletons: Both `alpaca_service` and `alpaca_trading_service` have `reinitialize()` for live credential updates and lazy `_try_init()` on `is_available` check
- PresetSelector uses WEIGHTED composite scoring (-100 to +100): regime 35%, MRI 30%, F&G 20%, readiness 15%. Score thresholds: ≥50 aggressive_bull, ≥20 moderate_bull, ≥0 neutral, ≥-20 cautious, ≥-50 defensive. No single signal can veto the classification (except extreme panic MRI>80 + F&G<10).
- CNN Fear & Greed API returns 418 (bot detection) — `get_fear_greed_index()` falls through to VIX-based fallback via `_get_fear_greed_fallback()`. F&G should almost always be available now.
- PresetSelector `_classify_condition()` takes TWO args `(score, snapshot)` — any external callers (autopilot.py) must call `_compute_composite_score()` first

## Reference Documents

- **[ARCHITECTURE.md](../ARCHITECTURE.md)** — Complete system map, data flows, all services/models/stores
- **[BACKLOG.md](../BACKLOG.md)** — Prioritized improvements, known issues, deferred items
- **[docs/TEST_STRATEGY.md](../docs/TEST_STRATEGY.md)** — Comprehensive test plan (1,400 lines)
- **[project-management/ROADMAP.md](../project-management/ROADMAP.md)** — Future feature ideas
