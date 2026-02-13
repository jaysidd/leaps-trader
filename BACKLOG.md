# LEAPS Trader — Backlog

> Prioritized list of improvements, tech debt, and known issues.
> When a new agent asks "what should I work on?" — start here.
>
> **Update rules:** When you fix a bug listed here, move it to "Recently Completed".
> When you discover a new bug, add it with priority and affected files.
> See CLAUDE.md for full documentation update rules.

---

## P0: Critical

| # | Issue | Files | Impact |
|---|-------|-------|--------|
| 1 | Robinhood session pickle persistence | `services/brokers/robinhood_service.py` | Session data stored insecurely on disk. Security risk if machine is compromised. |
| 2 | `user_alerts.alert_scope` column missing in DB | `models/user_alert.py` | Log warning on startup. Not blocking but schema is out of sync. Run migration or add column. |

---

## P1: High (Should Fix Soon)

| # | Issue | Files | Impact |
|---|-------|-------|--------|
| 3 | Synchronous Anthropic client blocks event loop | `services/ai/claude_service.py` | Needs `AsyncAnthropic` migration. Event loop stalls during AI calls, affects all concurrent requests. |
| 4 | Earnings risk scoring silently fails | `signal_engine.py`, `claude_service.py` | Event loop mismatch in worker thread. Earnings catalyst data missing from signals. |
| 5 | `asyncio.create_task()` from worker thread for Telegram | `auto_trader.py`, `position_monitor.py` | Not thread-safe. Telegram notifications may silently fail. |
| 6 | Multi-snapshot shape mismatch | `alpaca_service.py` | spread/volume always None in bulk option snapshot path. Affects option liquidity checks. |
| 7 | No CI/CD pipeline | — | No automated testing on commit/PR. Regressions go undetected until manual discovery. |
| 8 | No frontend tests at all | `frontend/src/` | 50+ components, 8 stores, 18 API clients with zero unit tests. |
| 9 | `MacroOverlayTest.jsx` temp page still in routes | `frontend/src/App.jsx` | Test/debug page accessible in production. Should be removed. |
| 10 | DB connection exhaustion under load | Multiple endpoint files | Some endpoints still use manual `SessionLocal()` instead of `Depends(get_db)`. Audit all endpoint files. |

---

## P2: Medium (Quality Improvements)

| # | Issue | Files | Impact |
|---|-------|-------|--------|
| 11 | No error boundaries in React | `frontend/src/` | Top-level ErrorBoundary exists but per-page boundaries are missing. Unhandled errors crash entire app. |
| 12 | No TypeScript | `frontend/src/` | All frontend is JSX. TypeScript migration would catch type errors at build time. |
| 13 | Empty `frontend/src/store/` directory | Legacy empty directory | Confusing for agents. Stores live in `/stores/`. Delete this directory. |
| 14 | Hard-coded paths in older tests | `backend/tests/services/` | Tests use absolute paths, non-portable across machines. |
| 15 | Trading pipeline test coverage gaps | `backend/tests/trading/` | 79 tests exist but auto_trader.py and order_executor.py have zero test coverage. |
| 16 | Saved scans endpoint audit | `backend/app/api/endpoints/` | Saved scans was fixed to use `Depends(get_db)` — verify all other endpoint files follow same pattern. |

---

## P3: Low (Nice to Have)

| # | Issue | Description |
|---|-------|-------------|
| 17 | Hosting/security hardening | Pre-deployment checklist exists in archived plans. Needs implementation before any public hosting. |
| 18 | Backtest strategy visualization | No visual debugging during backtests. Only final results shown. |
| 19 | WebSocket expansion | Infrastructure exists (`ws_endpoints.py`). Could expand for real-time portfolio updates, bot status, etc. |
| 20 | Settings validation | `settings.py` endpoint has TODO for actual validation per service. Currently accepts anything. |
| 21 | Catalyst Phase 2-3 | Earnings risk score + options positioning catalysts. TODO in `catalyst_service.py`. |

---

## Recently Completed (for context)

- **Screening threshold rebalance** (2026-02-12): Fixed screening pipeline over-tightening that produced 0 results from 1119 stocks. Key changes: removed default $50B market cap ceiling (presets now control caps), relaxed fundamental KNOWN to 4/5, relaxed technical gate to 3/7 PASS + 5/7 KNOWN, relaxed options gate to 2/4 PASS + 3/4 KNOWN, restored LEAPS-realistic options thresholds (IV <70%, OI >100, spread <15%, premium <20%), lowered composite minimum to 20. Pipeline now produces 25-50 results per scan. Files: types.py, fundamental.py, screener.py, options.py, engine.py.
- **Screening pipeline quality overhaul** (2026-02-12): Fixed critical filter misalignment causing 207 stocks to pass screening with 0 actionable trades. Root causes: IV threshold at 70% (should be 40% for LEAPS buying), options gate only needing 2/4 PASS, no composite score minimum, signal engine penalties too harsh (-40 possible), AI validator too conservative (75 threshold). 8 fixes across 5 files: options.py, types.py, engine.py, signal_engine.py, signal_validator.py. Expected result: ~25-40 screened stocks with much higher downstream conversion rate.
- **5-agent code review**: 113 findings across 3 tiers — all implemented (Tier 1: Alpaca timeout/retry, asyncio.to_thread. Tier 2: input validation, DB session leak, composite indexes, backoff polling. Tier 3: trailing stop, roll alert dedup, circuit breaker reset, 7→2 query consolidation, backtest semaphore, rate limiting, request timeout)
- **Multi-strategy queue system**: 8 phases + 2 code reviews. 4-layer intelligence pipeline: Screening → Strategy Selection → Signal Engine → AI Validation
- **Trading bot**: 13-phase implementation. Full pipeline: Signal Engine → Risk Gateway → Position Sizer → Order Executor → Position Monitor → Trade Journal
- **Backtesting engine**: 5 Backtrader strategies with async execution and Semaphore(3) concurrency limiting
- **Trading pipeline tests**: 5 test files, 79 tests (risk_gateway, position_sizer, position_monitor, circuit_breaker, pnl_calculations)
- **E2E tests**: 3 Playwright specs, 27 tests (smoke, signal-to-trade, bot-management)
- **Saved scans fix**: Per-preset auto-save from Scan All Presets + DB connection leak fix (Depends(get_db))
- **Position monitor timezone fix**: Fixed aware/naive datetime subtraction bug on line 421
- **Auto-scan fix**: (1) Settings key mismatch — frontend `automation.auto_scan_*` vs backend `auto_scan_*` caused saves to silently fail. (2) Job now runs fresh screening engine per-preset and saves results, instead of only reading stale saved results.
- **Robust scanning overhaul**: (1) Dynamic FMP screener universe (267→1128 stocks). (2) Removed all [:25]/[:50] result caps. (3) Continuous interval scanning (30min default) with market-hours guard. (4) Relaxed defaults: revenue 20→10%, earnings 15→5%, technical gate min_known 6→5. (5) Settings UI for scan mode + interval.
- **Auto-scan defaults fix**: auto_scan_enabled was `false` by default with no UI toggle, so auto-scan never ran on Railway. Fixed via one-time seed migration + Autopilot UI controls. Added Redis log sink + /api/v1/logs endpoint + Logs page + Sentry SDK integration.

---

## Deferred Items (From Code Reviews)

| Ref | Item | Status |
|-----|------|--------|
| #39 | Comprehensive test coverage for trading pipeline | Partially addressed — 5 test files exist, auto_trader + order_executor still uncovered |
| — | Synchronous Anthropic → AsyncAnthropic | Not started — requires client swap + testing |
| — | Earnings risk scoring event loop mismatch | Not started — needs investigation |
| — | Telegram create_task thread safety | Not started — needs asyncio-safe alternative |
