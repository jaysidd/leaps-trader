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

## Deployment Workflow

- **Branches**: `main` = staging, `prod` = production
- **Flow**: PR → merge to `main` → Staging auto-deploys → test on staging → PR `main`→`prod` → merge → Production auto-deploys
- **Staging domains**: Backend: `leaps-trader-backend-staging.up.railway.app` | Frontend: `leaps-trader-frontend-staging.up.railway.app`
- **Production domains**: Backend: `leaps-trader-backend-production.up.railway.app` | Frontend: `leaps-trader-frontend-production.up.railway.app`
- Each environment has isolated PostgreSQL, Redis, and env vars (FRONTEND_URL, VITE_API_BASE_URL point to respective domains)
- **Never push directly to `prod`** — always merge via PR from `main`

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
- Composite score minimum: 30 (engine.py) — raised from 20 to filter marginal stocks that barely pass gates
- Market cap max: No default upper limit — presets control their own caps. Only small-cap/aggressive presets have explicit caps.
- Options spread threshold: 15% (options.py) — bid-ask spread max for acceptable LEAPS fills
- Options premium threshold: 20% (options.py) — max premium as % of stock price for LEAPS entry
- Signal engine gate penalty cap: -25 total (was -15, originally -40 uncapped) — tighter than before but still prevents total score destruction
- Signal engine MIN_CONFIDENCE: 62 (raised from 60) — combined with gate penalty cap change, filters more marginal signals
- AI validator auto-execute threshold: 70 (raised from 65) — only genuinely strong setups auto-execute; 40-69 goes to manual review
- AI validator prompt: evaluates objectively (removed old "be practical" lenient phrasing) — flags weak setups even if they passed screening
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
- LEAPS_PRESETS lives in `app/data/presets_catalog.py` (extracted from screener.py to avoid circular imports). Use `from app.data.presets_catalog import LEAPS_PRESETS, resolve_preset` everywhere. Never import LEAPS_PRESETS from screener.py.
- `resolve_preset(name, source, strict)` is the single gatekeeper for preset resolution outside UI endpoints. Strict mode (default: `PRESET_CATALOG_STRICT=true` env var) raises `ValueError` on unknown presets. Use `strict=False` when graceful skip is OK (auto_scan). UI endpoints still use `LEAPS_PRESETS.get()` with fallback but now log warnings.
- PresetSelector startup validation: `_validate_preset_catalog()` runs once on first `get_preset_selector()` call. In strict mode, raises `ValueError` if any preset name in `MARKET_CONDITIONS` is missing from `LEAPS_PRESETS`. Set `PRESET_CATALOG_STRICT=false` when running tests that don't need the full catalog.
- PresetSelector `confidence=0` gotcha (B3 fix): Use `if confidence is not None` not `if confidence` — zero confidence should mean zero signal contribution, not default to 0.7.
- Pipeline E2E tests: 222 tests in `backend/tests/pipeline/` covering all 7 layers + comprehensive PresetSelector tests with mock data — run with `python3 -m pytest tests/pipeline/ -v` (~1s, zero API calls)
- Replay E2E tests: 6 tests in `backend/tests/replay/` — fixture-based, no API calls. Synthetic SPY DataFrames (bull/neutral/bear/panic/mild_bull + parameterized mid-band) feed through ReplayMarketIntelligence → PresetSelector. Run with `python3 -m pytest tests/replay/ -v -m replay`. Tests 01-05 use corner fixtures; Test 06 uses discovery approach (tries 7 candidate parameterizations, asserts ≥1 hits moderate_bull, validates score↔condition consistency for all). Assertions use condition buckets (not exact scores) to avoid flakiness.
- Replay confidence scale fix: `_compute_regime_from_bars()` in replay_services.py normalizes confidence from 1-10 → 0-100 via `confidence = min(int(confidence * 12.5), 100)`. Without this, regime signal (35% weight) is nearly zeroed out. The LIVE `MarketRegimeDetector.analyze_regime_rules()` has the SAME bug (P1 in BACKLOG.md) — not yet fixed.
- Replay fixture VIX proxy gotcha: Daily noise % in synthetic fixtures gets amplified by the 20-day trailing std window. Original bear fixture used 1.6% daily noise → VIX proxy 52 (2008-level), F&G=0. Tuned to 1.0% → VIX ~32, F&G ~29. When designing fixtures, always verify the actual VIX proxy output, not just the noise parameter.
- Replay missing MRI: Without DB, MRI=None for all replay scenarios (except when injected). This redistributes MRI's 30% weight to other signals — regime jumps from 35% → 50%. Also disables panic override (requires both MRI>80 AND F&G<10). Production may behave differently when MRI data is available.
- Replay mid-band testing: The cautious band (-20 to 0) is extremely narrow to hit from bar-derived signals alone (without MRI injection). Without MRI, the 30% weight redistributes to regime/F&G/readiness, making regime dominant (~50%). Gentle downtrends stay in neutral (not enough VIX push) or jump to defensive (VIX threshold triggers bearish regime). Use discovery approach: try multiple parameterizations and assert ≥1 hits the target band, rather than pinning a single fragile fixture.
- Signal engine cross-direction conflict check (step 8b): Blocks BUY signals when active SELL signals exist for the same symbol (any timeframe, within 2h), and vice versa. Prevents whipsaw losses from conflicting multi-timeframe signals.
- Risk gateway opposing position check (#15): Blocks execution if an open position in the opposing direction already exists. Defense-in-depth alongside signal engine conflict check.
- Historical replay harness: `scripts/replay/replay_trading_day.py` — replays past trading days through all 7 pipeline layers. Usage: `python3 scripts/replay/replay_trading_day.py 2026-02-10 --symbols SSRM,NVDA --interval 15`. Flags: `--skip-screening` (bypass screening), `--no-ai` (skip Claude validation), `--no-risk-check` (skip Risk Gateway). AI Validator falls back to `manual_review` if Claude unavailable.
- Replay synthetic options chain: `replay_get_options_chain` returns DataFrame with single LEAPS call (ATM strike, 300 DTE, zero market data) to trigger screening soft-pass. Returning `None` causes hard-fail with `no_options_data`.
- Replay virtual trading: Virtual BotConfiguration (max_per_stock_trade=$500, max_daily_loss=2%, max_concurrent=5) and BotState track trades/P&L/circuit breaker during replay. Position sizing uses FIXED_DOLLAR mode.
- Replay market intelligence: `ReplayMarketIntelligence` computes regime/F&G/readiness from SPY daily bar cache (not live services). `^VIX` is NOT a valid Alpaca symbol — VIX is approximated from SPY 20-day realized volatility. Patches 4 caches: MRI, regime detector, F&G, readiness.
- Regime detector cache format: `MarketRegimeDetector._cache` stores keys at TOP LEVEL (`detector._cache.get("regime")`), NOT nested under `{"rules": ...}`. PresetSelector reads these directly.
- Replay audit log: `ReplayAuditLog` model (replay_audit_logs table) captures every pipeline decision during replay. Stages: preset_selection, screening, signal_generation, risk_check, trade_execution, position_exit, summary. Each entry has session UUID, decision JSON blob, pass/fail, score, reasoning.
- robin_stocks 2FA: `_validate_sherrif_id()` calls `input()` for SMS/email codes — blocks forever in web server. Our `robinhood_service.py` monkey-patches it with `_patched_validate_sherrif_id()` that raises `VerificationRequired` instead. The verify flow uses Robinhood's `/challenge/{id}/respond/` API directly.
- Robinhood verification has TWO flows: (1) TOTP `mfa_code` passed to `rh.login()` — works natively, (2) SMS/email `verification_workflow` — requires monkey-patching + our `/verify` endpoint. The `ConnectBrokerModal` → `submitMFA` store action auto-detects which flow to use.
- Redis socket timeouts: `cache.py` sets `socket_connect_timeout=5` and `socket_timeout=5` on both URL-based and host-based Redis clients. Without these, the app hangs indefinitely when Redis is unreachable (Railway deploys, Redis restarts). Always keep these timeouts.
- Redis log sink circuit breaker: `log_sink.py` skips all Redis log writes for 60s after any write failure (`_circuit_open_until` monotonic timestamp). Prevents log storms and cascading failures when Redis is temporarily down.
- Railway healthcheck: Uses `healthcheckPath = "/"` not `/health`. The `/health` endpoint checks Redis-stored job statuses which can timeout during Redis issues, causing Railway to restart the container in a loop. Root `/` returns a simple FastAPI response.
- Railway deploy triggers: Staging auto-deploys from `main` branch, Production auto-deploys from `prod` branch. Never push directly to `prod`.

## Reference Documents

- **[ARCHITECTURE.md](../ARCHITECTURE.md)** — Complete system map, data flows, all services/models/stores
- **[BACKLOG.md](../BACKLOG.md)** — Prioritized improvements, known issues, deferred items
- **[docs/TEST_STRATEGY.md](../docs/TEST_STRATEGY.md)** — Comprehensive test plan (1,400 lines)
- **[project-management/ROADMAP.md](../project-management/ROADMAP.md)** — Future feature ideas
