# LEAPS Trader — Architecture Reference

> Single source of truth for the application architecture. Read this file to understand the full system.
>
> **Update rules:** When you add/remove/rename a page, router, service, model, store, or scheduler job — update the relevant table here and add a Changelog entry at the bottom.
> See CLAUDE.md for full documentation update rules.

## Application Overview

LEAPS Trader is a **stock screening and options trading automation platform** originally designed for finding LEAPS (Long-term Equity Anticipation Securities) with 5x return potential. It has evolved into a full trading suite with automated signal generation, AI-powered trade validation, real-time portfolio management, backtesting, and macro intelligence.

**Stack:** FastAPI (Python 3.11) + React 19 / Vite / Zustand / Tailwind + PostgreSQL + Redis
**Single-user app** — no authentication system. Paper + live trading via Alpaca.

---

## System Map

### Frontend Pages (14 unique pages, 15 routes)

| Route | Page Component | Purpose |
|-------|---------------|---------|
| `/`, `/command-center` | CommandCenter | Dashboard: MRI gauge, catalysts, news, sentiment, market pulse |
| `/screener` | Screener | Stock screening with presets, custom criteria, manual symbols |
| `/saved-scans` | SavedScans | Browse/manage persisted screening results by category |
| `/signals` | SignalQueue | Trading signals queue, AI analysis, manual trade execution |
| `/portfolio` | Portfolio | Current positions, holdings, P&L tracking |
| `/macro-intelligence` | MacroIntelligence | FRED data, event calendar, liquidity/volatility analysis |
| `/heatmap` | HeatMap | Sector correlations and market overview heatmaps |
| `/trade-journal` | TradeJournal | Trade history, daily performance stats, analytics |
| `/bot-performance` | BotPerformance | Trading bot metrics, performance charts, error tracking |
| `/backtesting` | Backtesting | Strategy backtesting with equity curves and trade logs |
| `/autopilot` | Autopilot | Monitoring dashboard: market gauges, pipeline status, position calculator, activity feed |
| `/logs` | Logs | Real-time application logs viewer (Redis ring buffer, level/search/module filtering) |
| `/health` | Health | System health dashboard: dependency checks, scheduler jobs, auto-scan & bot status |
| `/settings` | Settings | App config, bot rules, API credentials, automation schedules |

### Backend API Routers (23 groups)

| Prefix | Router File | Purpose |
|--------|------------|---------|
| `/api/v1/screener` | screener.py | Stock screening engine, presets, streaming scan-all |
| `/api/v1/stocks` | stocks.py | Stock details, price data, fundamentals |
| `/api/v1/signals` | signals.py | Signal queue CRUD, stats, bulk operations |
| `/api/v1/trading` | trading.py | Manual/webhook trade submissions |
| `/api/v1/trading/bot` | bot.py | Bot config, control, approve/reject, journal, performance (20 endpoints) |
| `/api/v1/backtesting` | backtesting.py | Run backtests, get results, list/delete history |
| `/api/v1/scan-processing` | scan_processing.py | Strategy selector pipeline, AI review, queue reviewed |
| `/api/v1/ai` | ai_analysis.py | Claude AI signal analysis and pre-trade validation |
| `/api/v1/sentiment` | sentiment.py | Sentiment analysis, news processing |
| `/api/v1/strategy` | strategy.py | Strategy recommendations, position sizing |
| `/api/v1/settings` | settings.py | App configuration persistence |
| `/api/v1/command-center` | command_center.py | Market data, MRI snapshots, daily metrics |
| `/api/v1/command-center/macro` | macro.py | Macro data aggregation |
| `/api/v1/command-center/macro-intelligence` | macro_intelligence.py | Catalysts, event calendars, trade readiness |
| `/api/v1/portfolio` | portfolio.py | Portfolio positions from brokers |
| `/api/v1/heatmap` | heatmap.py | Sector correlations and heatmap data |
| `/api/v1/saved-scans` | saved_scans.py | Save/load/delete screening results |
| `/api/v1/alerts` | user_alerts.py | Price/technical alerts |
| `/api/v1/webhooks` | webhooks.py | External webhook ingestion |
| `/api/v1/autopilot` | autopilot.py | Autopilot status, activity log, market state, position calculator (4 endpoints) |
| `/api/v1/logs` | logs.py | Application log viewer from Redis ring buffer (level/search/module filtering) |
| `/api/v1/health` | health.py | System health dashboard, dependency checks, scheduler job status (5 endpoints) |
| `/ws` | ws_endpoints.py | Real-time price streaming WebSocket |

### Backend Services

**Screening & Signals:**
- `services/screening/engine.py` — 4-stage screening pipeline (fundamental → technical → options → momentum)
- `services/signals/signal_engine.py` — Signal generation from queue (5 strategies, 2 timeframes)
- `services/signals/strategy_selector.py` — Rules engine: timeframe qualification + confidence scoring
- `services/signals/signal_validator.py` — Claude AI pre-trade validation (Layer 4)

**Trading Bot Pipeline (7 files):**
- `services/trading/auto_trader.py` — Singleton orchestrator (process_new_signals, execute_manual_signal, preview_signal)
- `services/trading/risk_gateway.py` — 16-point risk validation (fail-fast, skip_bot_status_check for manual)
- `services/trading/position_sizer.py` — 3 modes: fixed dollar, % portfolio, risk-based
- `services/trading/order_executor.py` — Alpaca order placement (bracket, notional, option)
- `services/trading/position_monitor.py` — SL/TP/trailing/EOD/expiry checks every 1 min
- `services/trading/trade_journal.py` — Daily stats aggregation + analytics
- `services/trading/alpaca_trading_service.py` — Alpaca client wrapper with caching + timeout

**Backtesting:**
- `services/backtesting/engine.py` — Backtrader orchestrator (fetch data → build feed → run cerebro → extract results)
- `services/backtesting/strategies.py` — 5 bt.Strategy classes: ORBBreakout, VWAPPullback, RangeBreakout, TrendFollowing, MeanReversion

**Data Providers:**
- `services/data_fetcher/alpaca_service.py` — Prices, options chains, snapshots, account data
- `services/data_fetcher/fmp_service.py` — Fundamentals, technical indicators, bulk metrics
- `services/data_fetcher/finviz.py` — Stock universe screening
- `services/data_fetcher/tastytrade.py` — Enhanced Greeks/IV data (optional)
- `services/data_fetcher/sentiment.py` — News + social sentiment analysis
- `services/data_fetcher/price_stream_service.py` — Real-time price WebSocket
- `services/data_providers/fred/fred_service.py` — FRED macro indicators (rates, DXY, VIX)
- `services/data_providers/volatility_provider.py`, `liquidity_provider.py`, `credit_provider.py`, `event_density_provider.py`

**AI & Analysis:**
- `services/ai/claude_service.py` — Claude API client with cost tracking + cache
- `services/ai/auto_analysis.py` — Auto-analyze high-confidence signals
- `services/analysis/technical.py`, `fundamental.py`, `options.py`, `sentiment.py`, `catalyst.py`

**Command Center:**
- `services/command_center/macro_signal.py` — MRI (Market Regime Index) calculation
- `services/command_center/catalyst_service.py` — Catalyst scores (liquidity, trade readiness)
- `services/command_center/market_data.py`, `news_service.py`, `news_feed.py`, `polymarket.py`, `copilot.py`

**Automation:**
- `data/presets_catalog.py` — LEAPS_PRESETS dict (29 presets + iv_crush alias), `_PRESET_DISPLAY_NAMES`, `resolve_preset()`, `get_catalog_hash()`. Single source of truth for all screening presets.
- `services/automation/preset_selector.py` — Market-adaptive preset selection using weighted composite scoring (regime 35%, MRI 30%, F&G 20%, readiness 15%)

**Infrastructure:**
- `services/settings_service.py` — App-wide settings (Redis + DB)
- `services/telegram_bot.py` — Telegram alerts + remote commands
- `services/alerts/alert_service.py` — Price/technical alert checking
- `services/cache.py` — Redis caching utilities

### Database Models (28)

| Model | Table | Key Fields | Purpose |
|-------|-------|-----------|---------|
| Stock | stocks | symbol, name, sector, market_cap | Stock master data |
| PriceHistory | price_history | symbol, date, ohlcv | Historical price cache |
| Fundamental | fundamentals | symbol, pe, eps, revenue_growth | Fundamental data cache |
| TechnicalIndicator | technical_indicators | symbol, sma, rsi, macd | Technical calc cache |
| ScreeningResult | screening_results | symbol, score, criteria | Screener run results |
| SavedScanResult | saved_scan_results | scan_type, symbol, stock_data (JSON) | Persisted scan results |
| SavedScanMetadata | saved_scan_metadata | scan_type, display_name, stock_count | Scan category metadata |
| Option | options | symbol, strike, expiry, greeks | Option contract data |
| SignalQueue | signal_queue | symbol, timeframe, strategy, status | Queue entry point |
| TradingSignal | trading_signals | symbol, strategy, confidence, entry/stop/target | Generated signals |
| BotConfiguration | bot_configurations | 33 columns: risk rules, sizing, exit thresholds | Bot settings |
| BotState | bot_states | 20 columns: status, daily P&L, circuit breaker | Bot runtime state |
| ExecutedTrade | executed_trades | 34 columns: entry, exit, P&L, Greeks | Trade history |
| DailyBotPerformance | daily_bot_performance | date, win_rate, total_pnl, trade_count | Daily stats |
| BacktestResult | backtest_results | config, metrics, equity_curve, trade_log (JSON) | Backtest runs |
| UserAlert | user_alerts | symbol, type, threshold, triggered | User alerts |
| WebhookAlert | webhook_alerts | source, payload, processed | Webhook log |
| MRISnapshot | mri_snapshots | regime, score, components | Market regime snapshots |
| CatalystSnapshot | catalyst_snapshots | scores (liquidity, readiness) | Catalyst snapshots |
| TickerCatalystSnapshot | ticker_catalyst_snapshots | symbol, catalyst scores | Per-ticker catalysts |
| EventCalendar | event_calendars | event_type, date, description | Economic/earnings events |
| PolymarketSnapshot | polymarket_snapshots | market data time-series | Prediction market data |
| SectorMacroMapping | sector_macro_mappings | sector, macro indicator weights | Sector-macro weights |
| Watchlist | watchlists | name, symbols | User watchlists |
| BrokerConnection | broker_connections | broker, credentials (encrypted) | Broker creds |
| Settings | settings | key, value | App settings K/V store |
| AutopilotLog | autopilot_logs | event_type, market_conditions, pipeline data | Autopilot activity log for scan events, market state, pipeline tracking |
| ReplayAuditLog | replay_audit_logs | replay_session_id, stage, decision (JSON) | Captures every pipeline decision during historical replay for post-analysis |

### Zustand Stores (8)

| Store | File | State Managed |
|-------|------|---------------|
| screenerStore | screenerStore.js | Scan state, results, progress, SSE streaming |
| signalsStore | signalsStore.js | Signals list, unread count, polling (30s) |
| botStore | botStore.js | Bot status, config, trades, exponential backoff polling |
| backtestStore | backtestStore.js | Backtest results, config, async polling |
| portfolioStore | portfolioStore.js | Portfolio positions, holdings, P&L |
| priceStreamStore | priceStreamStore.js | Real-time price subscriptions via WebSocket |
| savedScansStore | savedScansStore.js | Saved scan categories, metadata, CRUD |
| themeStore | themeStore.js | Dark/light mode + localStorage persistence |

### Frontend API Clients (18 files in `frontend/src/api/`)

axios.js (base), screener.js, stocks.js, signals.js, trading.js, bot.js, backtesting.js, savedScans.js, scanProcessing.js, ai.js, sentiment.js, strategy.js, settings.js, commandCenter.js, macroIntelligence.js, portfolio.js, alerts.js, userAlerts.js

---

## Data Flow Diagrams

### Screening Pipeline
```
Finviz/FMP Universe → Fundamental Filter (40%) → Technical Filter (30%) → Options Filter (20%) → Momentum Score (10%) → Composite Scored List
```

### 4-Layer Intelligence Pipeline
```
Layer 1: SCREENING → Finviz/FMP universe → 4-stage filter → 25-50 scored stocks
Layer 2: STRATEGY SELECTION → Fresh FMP indicators → rules-based strategy assignment
Layer 3: SIGNAL ENGINE → 5 strategies (ORB, VWAP, Range, Trend, MeanReversion) → TradingSignal
Layer 4: AI VALIDATION → Claude reviews signal → confidence scoring → auto-execute / manual review / reject
```

### Signal-to-Trade Pipeline
```
SignalQueue → SignalEngine (5min scheduler) → StrategySelector → SignalValidator (Claude AI)
    ↓
AutoTrader routes by execution_mode:
  signal_only → UI display only
  semi_auto   → PENDING_APPROVAL → user approve/reject
  full_auto   → RiskGateway (16 checks) → PositionSizer (3 modes) → OrderExecutor (Alpaca)
    ↓
PositionMonitor (1min) → check SL/TP/trailing/EOD/expiry → TradeJournal
```

### Manual Trade Flow
```
User clicks "Trade" on signal → SendToBotModal → Preview (risk + sizing) → Confirm → Execute through full pipeline
(No bot RUNNING required — skip_bot_status_check=True)
```

### Backtesting Flow
```
Config (symbol, strategy, dates, capital) → POST /run → DB record → asyncio.to_thread(Backtrader)
    → Semaphore(3) limits concurrency → Frontend polls GET /results/{id} every 2s
    → Results: metrics (Sharpe, return%, drawdown, win rate) + equity curve + trade log
```

---

## Integration Map

| Provider | What It Provides | Notes |
|----------|-----------------|-------|
| **Alpaca** | Trading (paper+live), prices, options chains, account | Primary broker. Monkey-patched timeout. |
| **FMP** | Fundamentals, technical indicators, bulk metrics | `/stable/` field names differ from v3. Redis cached. |
| **Finviz** | Stock universe for screening | Optional Finviz Elite for enhanced data |
| **Claude AI** | Signal validation, market regime analysis, copilot | AsyncAnthropic migration pending |
| **Telegram** | Trade alerts, scan summaries, roll alerts | Allowed user IDs configured |
| **FRED** | Macro data (yields, credit spreads, liquidity) | Via aiohttp, session closed on shutdown |
| **TastyTrade** | Enhanced Greeks/IV data | Optional, OAuth2 with refresh tokens |
| **Robinhood** | Portfolio data | Optional, pickle-based session (security risk) |

---

## Background Jobs (10 APScheduler jobs)

| Job ID | Interval | Function | Purpose |
|--------|----------|----------|---------|
| alert_checker | 5 min | check_alerts_job | Check price/technical alerts → trigger notifications |
| signal_checker | 5 min | check_signals_job | Process signal queue → signal engine → AI validation → auto-trader |
| position_monitor | 1 min | monitor_positions_job | Check SL/TP/trailing/EOD/expiry for open positions |
| mri_calculator | 15 min | calculate_mri_job | Calculate Market Regime Index snapshot |
| market_snapshot_capture | 30 min | capture_market_snapshots_job | Polymarket + market data time-series |
| catalyst_calculator | 60 min | calculate_catalysts_job | Catalyst scores (smart-skip if unchanged) |
| bot_daily_reset | cron 9:30 ET M-F | bot_daily_reset_job | Reset daily counters at market open |
| bot_health_check | 5 min | bot_health_check_job | Verify bot state consistency |
| auto_scan | interval 30min (or cron 8:30 CT) | auto_scan_job | Run configured scan presets with dynamic FMP universe → save + queue to signal processing. **Smart mode**: market-adaptive preset selection via preset_selector + top-N candidate filter |
| health_alert | 10 min | health_alert_job | Check system health, send Telegram alerts on status degradation (healthy→degraded/critical) |

---

## Middleware & Infrastructure

- **Rate Limiting**: In-memory per-IP sliding window (120 req/min) in `main.py`
- **Request Timeout**: 120s middleware, skips WebSocket and long-running paths (`/backtesting/run`, `/screener/run`, `/ai/`)
- **Global Exception Handler**: Catches unhandled errors, returns generic 500 (no stack traces exposed)
- **CORS**: Configured for localhost ports + leapstraders.com
- **Shutdown Cleanup**: Closes 6 aiohttp sessions on app shutdown (FMP, market_data, news, news_feed, polymarket, FRED)
- **Polling**: botStore + signalsStore use exponential backoff (setTimeout-based, doubles on error, capped)

---

## Trading Bot Deep Dive

### Execution Modes
- **signal_only** (default): Signals appear on UI only, no execution
- **semi_auto**: Signals queued as PENDING_APPROVAL for one-click approve/reject
- **full_auto**: Automatic risk → size → execute pipeline
- **Manual**: User clicks "Trade" on any signal → preview → confirm (no bot RUNNING required)

### Bot State Machine
```
STOPPED → RUNNING → PAUSED → HALTED
Circuit Breaker: NONE → WARNING → PAUSED → HALTED (escalation only, never downgrades)
```

### Risk Gateway (16 checks, fail-fast)
1. Bot status check (skipped for manual trades)
2. Circuit breaker level
3. Market hours (weekday + 9:30-16:00 ET)
4. Daily trade limit
5. Daily loss limit
6. Concurrent positions limit
7. Buying power check
8. Portfolio allocation per-trade cap
9. Total invested cap
10. Signal confidence threshold
11. AI analysis check
12. Strategy filter
13. Duplicate position check
14. Option bid-ask spread check
15. Option open interest check
16. Option premium limit

### Position Sizer (3 modes)
- **Fixed Dollar**: Exact dollar amount per trade
- **% Portfolio**: Percentage of total equity
- **Risk-Based**: Dollar risk amount / stop distance = shares

### Trade Lifecycle States
```
PENDING_ENTRY → OPEN → PENDING_EXIT → CLOSED (or CANCELLED / ERROR)
Exit reasons: take_profit, stop_loss, trailing_stop, time_exit, signal_invalidated, circuit_breaker, manual, kill_switch
```

---

## Multi-Strategy Queue System

**4-Layer Pipeline**: Screening → Strategy Selection → Signal Engine → AI Pre-Trade Validation

**5 Strategies**: ORB Breakout, VWAP Pullback, Range Breakout, Trend Following, Mean Reversion
**Timeframes**: 1H and Daily (4H was removed)
**AI Validation Thresholds**: confidence >= 75 auto-execute, 40-74 manual review, <40 reject
**Scheduled Scans**: APScheduler CronTrigger, configurable presets/time in Settings AutomationTab

---

## Testing Infrastructure

| Layer | Tool | Files | Coverage |
|-------|------|-------|----------|
| Backend unit tests | pytest + freezegun | 11 files in `tests/services/` | Scoring, command center |
| Trading pipeline tests | pytest | 5 files in `tests/trading/` (79 tests) | risk_gateway, position_sizer, position_monitor, circuit_breaker, pnl_calculations |
| E2E tests | Playwright | 3 specs in `tests/e2e/flows/` (27 tests) | Smoke (all pages), signal-to-trade, bot-management |
| Frontend unit tests | — | None | **Zero coverage** |
| CI/CD | — | None | **Not configured** |

See `docs/TEST_STRATEGY.md` for the comprehensive test plan.

---

## Data Provider Gotchas

- **FMP** `/stable/` field names differ from v3 — always check actual API response shape
- **FMP** sync wrappers use dedicated background event loop (`_run_sync` + `asyncio.run_coroutine_threadsafe`)
- **FMP** cache falsiness: use `if cached is not None:` not `if cached:`
- **Alpaca** `ContractType` enum: use `.value` not `str()` — `str(ContractType.CALL)` = `"contracttype.call"` not `"call"`
- **Alpaca** option snapshots require `OptionHistoricalDataClient`, NOT `StockHistoricalDataClient`
- **Alpaca** TradingClient has NO built-in timeout — monkey-patched via `_session.request`
- **Alpaca** `_trading_client` cached to prevent connection leaks (was creating new client per call)
- **LEAPS** DTE threshold: 250 days (not 365) — real-world LEAPS expirations can be 9-10 months out
- **Screening** engine fetches 2y price history (not 1y) for sufficient data + 1yr return calculation
- **Backtrader** subclass params: MUST include ALL base params (dict replaces, not merges)
- **Redis**: Flush FMP cache after field mapping changes: `r.keys('fmp:*')` then `r.delete(*keys)`
- **has_sufficient_data** threshold: 200 trading days (matching SMA200 requirement)

---

## Completed Major Work

- **13-phase trading bot**: Full pipeline from signal generation through position monitoring and trade journaling
- **Multi-strategy queue system**: 8 phases of implementation + 2 rounds of deep code review (all findings fixed)
- **5-agent code review**: 113 findings across 3 tiers (Critical/High/Medium) — all implemented
- **Macro Intelligence**: MRI gauge, Tier 1+2 catalyst providers (liquidity, volatility, credit, event density)
- **Backtesting engine**: 5 Backtrader strategies with async execution and concurrency limiting
- **Test infrastructure**: 79 backend trading pipeline tests + 27 Playwright E2E tests
- **Saved scans auto-save**: Per-preset saving from Scan All Presets + DB connection leak fix (Depends(get_db))

---

## Changelog

> Every agent MUST add an entry here when they change system structure. Format: `YYYY-MM-DD: what changed`.

- 2026-02-12: Documentation consolidation — 34 scattered files → 3 authoritative docs (ARCHITECTURE.md, BACKLOG.md, CLAUDE.md). 24 files archived, 2 deleted, 2 memory files retired.
- 2026-02-12: Fixed saved scans bug — Scan All Presets now saves per-preset (was saving as single "All Presets" bucket). Converted saved_scans.py endpoints to Depends(get_db).
- 2026-02-12: Added 79 trading pipeline tests (risk_gateway, position_sizer, position_monitor, circuit_breaker, pnl_calculations) + 27 Playwright E2E tests.
- 2026-02-12: Fixed position_monitor.py timezone bug — aware/naive datetime subtraction on line 421.
- 2026-02-12: Fixed auto_scan_job — (1) settings key mismatch: frontend sent `automation.auto_scan_*` but DB stored `auto_scan_*`, (2) job now runs fresh screening engine per-preset instead of only reading stale saved results. Added code annotation comments to 4 structural hotspot files.
- 2026-02-12: Robust scanning overhaul — (1) Dynamic stock universe via FMP company-screener API (267→1128 stocks), with fallback to hardcoded lists. (2) Removed all artificial result caps ([:25], [:50]) across 5 locations in screener.py and main.py. (3) Continuous interval-based scanning (default 30min, configurable 15/30/60min) with market-hours guard, replacing daily-only cron. New settings: `automation.auto_scan_mode`, `automation.auto_scan_interval_minutes`. (4) Relaxed screening defaults: revenue growth 20%→10%, earnings growth 15%→5%, technical gate min_known 6→5. (5) Settings.jsx AutomationTab updated with scan mode selector and interval picker.
- 2026-02-12: **Screening pipeline quality overhaul** — Tightened all filters to reduce noise (207→~25-40 stocks expected). 8 changes across 4 files: (1) Gate configs tightened: fundamental 3/5→4/5, technical 3/7→4/7, options 2/4→3/4 PASS (types.py). (2) Options IV threshold 70%→40% for LEAPS buying (options.py). (3) Liquidity minimum 100→500 OI (options.py). (4) Spread threshold 10%→5%, premium 15%→12% (options.py). (5) Added composite score minimum of 65 in screening engine (engine.py). (6) Signal engine gate penalty cap at -15 total (signal_engine.py). (7) AI validator auto-execute threshold 75→65 with less conservative prompting (signal_validator.py). (8) Flushed 3360 Redis FMP cache keys.
- 2026-02-12: **Screening threshold rebalance** — Removed default $50B market cap ceiling (presets now control caps), relaxed technical gate to 3/7, relaxed options gate to 2/4, restored options IV/OI/spread/premium to LEAPS-realistic values (IV <70%, OI >100, spread <15%, premium <20%), lowered composite minimum to 20. Pipeline now produces 25-50 results (was 0 after over-tightening).

### 2026-02-12 — Autopilot Conductor Layer
- **New service**: `services/automation/preset_selector.py` — Market-adaptive preset selection using MRI, regime, F&G, trade readiness
- **New model**: `models/autopilot_log.py` — Activity log for scan events, market conditions, pipeline tracking
- **New API**: `api/endpoints/autopilot.py` — 4 endpoints: /status, /activity, /market-state, /calculate-position
- **New page**: `frontend/src/pages/Autopilot.jsx` — Monitoring dashboard with market gauges, pipeline status, position calculator, activity feed
- **Modified**: `auto_scan_job` in main.py — Smart mode branch for market-adaptive preset selection + top-N candidate filter
- **Modified**: `BotConfiguration` — 3 new columns: autopilot_max_capital, autopilot_max_candidates, autopilot_max_trades_per_day
- **Modified**: `settings_service.py` — New setting: automation.smart_scan_enabled
- **Modified**: `App.jsx` — New /autopilot route + nav link
- **Modified**: `Settings.jsx` — Smart scan toggle in AutomationTab

### 2026-02-13 — Auto-Scan Fix + Logs Viewer
- **Fixed**: Auto-scan not firing on Railway — `automation.auto_scan_enabled` defaulted to `false` with no UI toggle. Added one-time migration in `seed_defaults()` to force-update existing DB values via sentinel key `_internal.auto_scan_defaults_v2`.
- **New service**: `services/log_sink.py` — Loguru custom sink pushing structured JSON logs to Redis list `app:logs` (5000 entry ring buffer via LPUSH+LTRIM).
- **New API**: `api/endpoints/logs.py` — GET /api/v1/logs with level/search/module filtering and configurable limit.
- **New page**: `frontend/src/pages/Logs.jsx` — Real-time log viewer with auto-refresh (5s), level filters, free-text search, module filter, color-coded monospace entries, follow-tail mode.
- **Modified**: `autopilot.py` — /status endpoint now returns `auto_scan_enabled` and `auto_scan_presets` fields.
- **Modified**: `Autopilot.jsx` — Added Auto-Scan master toggle (green) and multi-select preset pills fetched from GET /screener/presets.
- **Modified**: `main.py` — Registered Redis log sink and logs router.
- **Modified**: `App.jsx` — Added `/logs` route.
- **Modified**: `Sidebar.jsx` — Added Logs to Tools nav section.

### 2026-02-13 — System Health Monitoring Dashboard
- **New service**: `services/health_monitor.py` — Centralized health tracking via Redis: scheduler job timing/status, dependency checks (DB/Redis/Alpaca/Scheduler), dashboard aggregation, overdue detection, Telegram alert logic with cooldown.
- **New API**: `api/endpoints/health.py` — 5 endpoints: /dashboard, /dependencies, /jobs, /jobs/{id}, POST /check.
- **New page**: `frontend/src/pages/Health.jsx` — Health dashboard with overall status banner, 4 dependency cards, scheduler jobs table (color-coded), auto-scan + trading bot panels, Telegram status, 15s auto-refresh.
- **New job**: `health_alert_job` (10 min) — Checks system health, sends Telegram alerts on status transitions (healthy→degraded, degraded→critical) with 30min cooldown.
- **Modified**: `main.py` — Enhanced `/health` endpoint with real dependency checks (returns 503 only when critical), instrumented all 9 scheduler jobs with timing/status tracking, registered health router, added health_alert_job.
- **Modified**: `telegram_bot.py` — Added `broadcast_to_allowed_users(message)` for system alerts.
- **Fixed**: `auto_trader._send_telegram` (line 746) — Was importing from non-existent `app.services.notifications.telegram_service`. Now uses `get_telegram_bot()` + `asyncio.run_coroutine_threadsafe`.
- **Fixed**: `position_monitor._send_roll_alert` — Same broken import fix as auto_trader.
- **Modified**: `App.jsx` — Added `/health` route.
- **Modified**: `Sidebar.jsx` — Added Health to Tools nav section.

### 2026-02-13 — Screening Pipeline Fix (0 Results)
- **Root cause**: Auto-scan consistently returned 0 stocks for `conservative` and `blue_chip_leaps` presets due to 3 compounding issues:
  1. Options gate `min_known=3` impossible to meet when Alpaca snapshots are unavailable (off-hours/rate limits) — only IV+OI from contract data (often 0/unpopulated), spread+premium require bid/ask.
  2. Sector filter excluded Financial Services and Consumer Defensive — blocking V, MA, JPM, WMT, COST, PG, KO from conservative/blue-chip scans.
  3. IV=0.0 and OI=0 from uninitialized Alpaca data treated as real measurements instead of UNKNOWN.
- **Fixed**: `scoring/types.py` — Options gate `min_known` 3→2.
- **Fixed**: `screening/engine.py` — Options gate soft-pass: if LEAPS contracts exist but 0 criteria are KNOWN (no snapshot data), allow through with `options_soft_pass=True` flag for downstream re-evaluation.
- **Fixed**: `analysis/options.py` — IV=0.0 now treated as UNKNOWN (not a real measurement). OI=0 with no bid/ask data treated as UNKNOWN (contract data often doesn't populate OI).
- **Fixed**: `analysis/fundamental.py` — Added "Financial Services" and "Consumer Defensive" to GROWTH_SECTORS.
- **Fixed**: `screener.py` — Added `skip_sector_filter: True` to `conservative` and `blue_chip_leaps` presets.
- **Added**: `main.py` — Diagnostic failure-breakdown logging in auto_scan_job (aggregates `failed_at` counts per preset).

### 2026-02-13 — Fix Alpaca SDK on Railway
- **Root cause**: `alpaca.data` module failed to import on Railway due to missing `pytz` dependency (pandas 3.0 dropped pytz, but alpaca-py still requires it). Additionally, `TradingClient.__init__()` crashed with invalid `retry_attempts` parameter (removed in alpaca-py 0.43.x). Railway's Nixpacks build cache also served stale pip installs.
- **Fixed**: `requirements.txt` — Pinned `alpaca-py==0.43.2` (busted stale cache), added `pytz>=2024.1`.
- **Fixed**: `alpaca_trading_service.py` — Removed invalid `retry_attempts`, `retry_wait_seconds`, `retry_exception_codes` from TradingClient init. Added `_try_init()` lazy-init pattern + `reinitialize()` for live credential updates.
- **Fixed**: `alpaca_service.py` — Added `_try_init()` lazy-init, `reinitialize()`, improved import error logging (logs actual exception instead of generic "not installed").
- **Fixed**: `settings_service.py` — Auto-reinitializes Alpaca data + trading singletons when API keys updated via Settings UI (no restart required).
- **Fixed**: `price_stream_service.py` — Improved import error logging.

### 2026-02-13 — PresetSelector Weighted Scoring Overhaul
- **Root cause**: Old priority-chain classification in `preset_selector.py` let a single `readiness_label="yellow"` (trade readiness score 34-66, very common) veto bullish regime + low MRI, permanently locking scanner into `cautious` → only conservative + blue_chip_leaps. Bullish signals (regime, MRI) could never reach `moderate_bull` or `aggressive_bull` checks.
- **Rewritten**: `preset_selector.py` — Replaced priority-chain with weighted composite scoring system. All 4 signals (regime 35%, MRI 30%, F&G 20%, readiness 15%) contribute proportionally to a -100/+100 composite score. Score thresholds: ≥50 aggressive_bull, ≥20 moderate_bull, ≥0 neutral, ≥-20 cautious, ≥-50 defensive. Only hard override: extreme panic (MRI>80 + F&G<10) → skip. Missing signals excluded from weighting (remaining signals re-normalized). Added `_compute_composite_score()` method.
- **Fixed**: `market_data.py` — CNN Fear & Greed API non-200 responses (status 418 = bot detection) now fall through to VIX-based fallback calculation instead of returning None. F&G signal now almost always available.
- **Fixed**: `autopilot.py` — `/market-state` endpoint updated for new `_classify_condition(score, snapshot)` signature. Response now includes `composite_score` and `signal_scores` breakdown.
- **Modified**: `main.py` — Auto-scan Smart mode logging now shows composite score and full reasoning string.
- **Result**: With MRI=34.5, regime=bullish, F&G=70 (VIX fallback), readiness=yellow → composite +21.7 → `moderate_bull` (was `cautious`). Scanner now selects ["moderate", "blue_chip_leaps", "swing_breakout"] instead of just ["conservative", "blue_chip_leaps"].
- **Fixed**: `main.py` — Added `scan_failed` autopilot event logging in exception handler + startup cleanup for orphaned `scan_started` events (from deploys that killed mid-scan).

### 2026-02-13 — StrategySelector HIGH Confidence Fix
- **Root cause**: 0 out of 486 scanned stocks reached HIGH confidence for auto-trading, despite 22 qualifying for 1d timeframe. Two issues: (1) "missing SMA data" from FMP rate limits (403 errors during heavy scanning) was classified as a serious edge case, blocking HIGH. (2) Single-timeframe HIGH threshold was 68 (too conservative for stocks that already passed 4-stage screening).
- **Fixed**: `strategy_selector.py` — Removed "missing sma" from serious edge cases (missing data ≠ risk signal). Lowered single-timeframe HIGH score threshold from 68 to 65.
- **Expected result**: Stocks with composite_score ≥ 65 and no real risk signals (overbought/oversold/weak trend) can now auto-queue for the trading pipeline.

### 2026-02-13 — E2E Pipeline Tests + Quality Gate Fixes
- **Root cause**: Stock SN scored 85% confidence from Signal Engine but only 3/10 from AI Batch Analyzer. The 7-layer pipeline was sequentially lenient — each layer let marginal stocks through. Five weak thresholds identified: (1) gate penalty cap -15 rescued 25 free confidence points, (2) MIN_COMPOSITE_SCORE=20 too low, (3) AI validator prompt said "be practical" (explicitly lenient), (4) auto-execute threshold 65 too low, (5) MIN_CONFIDENCE=60 too low.
- **Fixed (5 threshold changes)**:
  - `signal_engine.py` — Gate penalty cap -15 → -25; MIN_CONFIDENCE 60 → 62
  - `engine.py` — MIN_COMPOSITE_SCORE 20 → 30
  - `signal_validator.py` — CONFIDENCE_THRESHOLD 65 → 70; prompt rewritten to evaluate objectively (removed "be practical")
- **New**: `backend/tests/pipeline/` — 109 tests across 10 files (conftest.py, helpers.py, mock_stocks.py, mock_market.py, test_layer1-7, test_quality_gates.py, test_full_pipeline.py). Tests cover all 7 pipeline layers with controlled mock data, zero external API calls, runs in ~1s.
- **Result**: SN-like edge stocks now fail at signal engine (confidence ~35 vs MIN_CONFIDENCE 62) and strategy selector (score 32 < min_score 55). Strong stocks still pass all layers unchanged.

### 2026-02-13 — Remove Sentry + Pipeline Diagnostic Tooling
- **Removed**: Sentry SDK — never activated (no DSN configured). Removed from `requirements.txt`, `main.py` (init block), `config.py` (SENTRY_DSN setting). Uninstalled from venv.
- **Fixed**: `user_alerts` table — 6 columns defined in SQLAlchemy model but missing from PostgreSQL (alert_scope, alert_params, severity, cooldown_minutes, dedupe_key, last_dedupe_at). `create_all()` doesn't ALTER existing tables. Fixed via `scripts/fix_user_alerts_columns.py`.
- **New script**: `scripts/diagnose_pipeline.py` — Tests all 7 pipeline layers with real data, prints color-coded results. Supports `--layer N` for single-layer testing, `--execute` for paper trade placement, `--api-guide` for curl command reference. Identifies exactly where signals get stuck or silently filtered.
- **New script**: `scripts/fix_user_alerts_columns.py` — Migration script adding 6 missing columns to user_alerts table.

### 2026-02-13 — Historical Replay Harness
- **New package**: `scripts/replay/` — Replay past trading days through the real signal pipeline using Alpaca Historical API. Pre-fetches bars, advances a simulated clock bar-by-bar, runs the REAL signal engine + risk gateway code at each tick.
- **New module**: `scripts/replay/replay_services.py` — Three classes: `ReplayClock` (simulated time), `ReplayDataService` (patches AlpacaService with cached historical bars), `ReplayTradingService` (virtual account + simulated fills). `DatetimeProxy` intercepts `datetime.now()` in signal_engine/risk_gateway modules.
- **New script**: `scripts/replay/replay_trading_day.py` — Main replay script. Usage: `python3 scripts/replay/replay_trading_day.py 2026-02-10 --symbols SSRM,NVDA --interval 30`. Supports `--equity`, `--no-cleanup`, `--timeframes`, `--start-time`/`--end-time`. Tags DB records with `source=replay` and cleans up on exit.
- **Architecture**: Monkey-patches 7 methods on existing service singletons (alpaca_service: get_bars, get_snapshot, get_historical_prices, get_options_chain, get_opening_range; alpaca_trading_service: get_account, get_clock, get_all_positions, get_position, get_orders, place_market_order, place_limit_order) + patches datetime.now() in signal_engine and risk_gateway modules. No production code modified.

### 2026-02-13 — Replay Harness: Full E2E Pipeline (Screening + AI + Risk + Sizing)
- **Enhanced**: `scripts/replay/replay_trading_day.py` — Wired all 7 pipeline layers into the replay loop: PresetSelector → Screening → Signal Engine → AI Validation → Risk Gateway → Position Sizer → Execute → Position Monitor (SL/TP). New CLI flags: `--skip-screening` (bypass screening gate), `--no-ai` (skip Claude AI validation), `--no-risk-check` (skip 16-point Risk Gateway). Virtual `BotConfiguration` and `BotState` objects provide realistic trading limits for replay. Position sizing uses FIXED_DOLLAR mode with 5% or $500 cap. AI Validator falls back gracefully when Claude is unavailable (`manual_review` mode — still executes in replay). Verified: 2 signals, 2 trades, 2 wins, $22.90 P/L on SSRM replay 2026-02-10 with full pipeline.
- **Enhanced**: `scripts/replay/replay_services.py` — `replay_get_options_chain` now returns synthetic LEAPS DataFrame (instead of `None`) to trigger screening engine's soft-pass path. Synthetic option: ATM strike, 300-day DTE, zero market data → triggers `leaps_available=True, known_count=0` → soft-pass.
- **Audit stages expanded**: `ai_validation` and `risk_check` stages now logged alongside existing `preset_selection`, `screening`, `signal_generation`, `trade_execution`, `position_exit`, `summary`. Full pipeline decision chain is captured in `replay_audit_logs` table.

### 2026-02-13 — Replay Harness: PresetSelector Integration + Audit Logging
- **Enhanced**: `scripts/replay/replay_services.py` — Added `ReplayMarketIntelligence` class (~300 lines) that computes historical market intelligence directly from SPY daily bar cache. Computes regime (RSI+SMA200+VIX proxy from realized volatility), Fear & Greed (VIX-to-score formula), and Trade Readiness (MRI 40% + regime proxy 60%). Loads MRI from DB `mri_snapshots` table. Patches 4 service caches: `MacroSignalService._cached_mri`, `MarketRegimeDetector._cache`, `MarketDataService.get_fear_greed_index`, `CatalystService.calculate_trade_readiness`.
- **Enhanced**: `scripts/replay/replay_trading_day.py` — Integrated PresetSelector into replay loop. Market intelligence is computed at startup, PresetSelector runs with patched data, prints condition/presets/composite score/signal breakdown. Extreme fear conditions (`skip`) trigger early exit.
- **New model**: `app/models/replay_audit_log.py` — `ReplayAuditLog` captures every pipeline decision during replay (stage, symbol, decision JSON, pass/fail, score, reasoning). Stages: preset_selection, screening, signal_generation, risk_check, trade_execution, position_exit, summary. Indexed on replay_session_id + replay_date + stage.
- **Gotcha fixed**: `^VIX` is not a valid Alpaca symbol — `MarketRegimeDetector.get_market_data()` fails silently. Solved by computing VIX proxy from SPY 20-day realized volatility (annualized std of daily returns).
- **Gotcha fixed**: Regime detector cache expects top-level keys (`detector._cache.get("regime")`), not nested under `{"rules": ...}`. PresetSelector reads these directly.
- **Verified**: Market intelligence now varies correctly across replay dates (e.g., Feb 4: MRI=57.7, F&G=96 vs Feb 10: MRI=48.6, F&G=91). 416 tests pass.

### 2026-02-13 — Cross-Direction Signal Conflict Detection
- **Root cause**: Historical replay revealed NVDA whipsaw loss — 3 SHORT signals (range_breakout, orb_breakout, vwap_pullback) preceded a conflicting LONG signal (trend_following) that was executed, then hit stop-loss from the short signal's SL level.
- **Fixed**: `signal_engine.py` — Added step 8b: cross-direction conflict check. Before emitting a signal, checks for active opposing-direction signals for the same symbol (any timeframe, within 2 hours). Blocks BUY when active SELL signals exist, and vice versa.
- **Fixed**: `risk_gateway.py` — Added check #15: `_check_opposing_position()`. Blocks execution of a signal when an open position in the opposing direction already exists for the same symbol. Added to the fail-fast check list after duplicate position check.
- **Tests**: 2 new tests in `test_risk_gateway.py` (opposing position rejected + allowed when no conflict). 416 total tests pass.
- **Replay results**: 4-day backtest (Feb 6-12) with SSRM+NVDA+AAPL: 35 signals, 17 trades, 76% win rate, +$46.55 cumulative P/L. Previously NVDA whipsaw caused a loss; now correctly blocked.

### 2026-02-13 — Fix Robinhood 2FA Verification Flow
- **Root cause**: robin_stocks' `_validate_sherrif_id()` calls Python's `input()` for SMS/email verification codes, blocking the FastAPI event loop forever. The `mfa_code` parameter only works for TOTP (authenticator apps), not Robinhood's newer `verification_workflow` (SMS/email/push) flow.
- **Fixed**: `robinhood_service.py` — Added `VerificationRequired` exception class and `_patched_validate_sherrif_id()` that intercepts the SMS/email challenge and raises instead of calling `input()`. New `verify_and_login()` method submits the code directly to Robinhood's `/challenge/{id}/respond/` API and retries login. The monkey-patch is installed/restored around each `rh.login()` call.
- **Fixed**: `portfolio.py` — New `/connections/{id}/verify` endpoint for SMS/email verification flow. Updated `_connect_robinhood()` to handle `requires_verification` response and store encrypted password for verification completion. Updated `submit_mfa()` to work with both TOTP and verification workflows.
- **Fixed**: `Portfolio.jsx` — `ConnectBrokerModal` now properly routes to `submitMFA` store action (which auto-routes to verify endpoint) when MFA code is entered, instead of re-calling the initial connect endpoint. Shows correct verification method label (SMS/email).
- **Fixed**: `portfolioStore.js` — `submitMFA` action auto-detects SMS/email vs TOTP flow and calls the appropriate API endpoint. Added `verificationData` state for tracking challenge details.
- **Fixed**: `portfolio.js` (API) — Added `submitVerification()` method for the new `/verify` endpoint.

### 2026-02-14 — PresetSelector Showstopper Fix + Comprehensive Tests
- **New module**: `app/data/presets_catalog.py` — Extracted LEAPS_PRESETS dict (~29 presets + iv_crush alias) and `_PRESET_DISPLAY_NAMES` from `screener.py` into standalone data module. Eliminates circular import risk. Includes `resolve_preset()` fail-fast helper and `get_catalog_hash()` for version breadcrumbs.
- **Fixed (B1)**: `preset_selector.py` — `"value_deep"` preset name in MARKET_CONDITIONS typo → `"deep_value"`. Neutral condition was silently falling back to "moderate" instead of scanning deep-value stocks.
- **Fixed (B2)**: `preset_selector.py` — Regime cache TTL mismatch: selector checked 10 minutes but `MarketRegimeDetector` uses 5 minutes → aligned to 5 minutes.
- **Fixed (B3)**: `preset_selector.py` — `if confidence` is falsy for 0 → changed to `if confidence is not None`. Zero confidence should mean zero signal, not default multiplier 0.7.
- **Fixed (B4)**: `preset_selector.py` — Docstring falsely claimed "no API calls" → fixed to reflect that stale/missing cache triggers Alpaca fetches.
- **Fixed (B5)**: `main.py`, `replay_trading_day.py` — Silent fallback to "moderate" preset in automation paths eliminated. Now uses `resolve_preset()` which either raises (strict mode) or logs error and skips. UI endpoints keep fallback but now log warnings.
- **Added**: `preset_selector.py` — `SELECTOR_VERSION = "1.1.0"` + `catalog_hash` in `select_presets()` return dict for audit/replay debugging.
- **Added**: `preset_selector.py` — `_validate_preset_catalog()` startup validation, called once from `get_preset_selector()`. In strict mode (`PRESET_CATALOG_STRICT=true`), raises ValueError on missing presets.
- **Modified**: `screener.py` — Removed LEAPS_PRESETS and _PRESET_DISPLAY_NAMES definitions, imports from `presets_catalog`. UI fallback now logs warning.
- **Modified**: `main.py` — Imports LEAPS_PRESETS + resolve_preset from `presets_catalog`. Auto-scan uses `resolve_preset(preset, "auto_scan", strict=False)`.
- **Modified**: `replay_trading_day.py` — Imports from `presets_catalog`. Uses `resolve_preset(preset, "replay", strict=False)` with warning on unknown preset.
- **New tests**: `tests/pipeline/test_preset_selector_comprehensive.py` — 86 tests (85 pass, 1 skip for hysteresis) across 13 test classes: boundary classification, confidence scaling, weight renormalization, readiness label fallback, panic override, preset mapping contracts, cache behavior, failure resilience, stability, scoring math, reasoning output, edge cases, classification integration.
- **New doc**: `docs/PRESET_SELECTOR_TESTS.md` — Reusable test case document with 69 spec'd test cases, hand-verified math tables for all mock snapshots, bug documentation, and future migration recommendations.
- **Modified**: `tests/pipeline/mock_market.py` — 8 new snapshot fixtures: NEAR_PANIC_MRI_ONLY, NEAR_PANIC_FG_ONLY, LABEL_FALLBACK_GREEN/YELLOW/RED, MAX_BULLISH/BEARISH_MARKET, BOUNDARY_AGGRESSIVE.
- **Test count**: 194 pipeline tests (was 109), 211 total pipeline+scoring tests. Full regression: 492 passed, 1 skipped (9 pre-existing failures in test_engine_integration.py unrelated to this change).
