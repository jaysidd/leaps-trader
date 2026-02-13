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
- `services/automation/preset_selector.py` — Market-adaptive preset selection using MRI, regime, Fear & Greed, trade readiness

**Infrastructure:**
- `services/settings_service.py` — App-wide settings (Redis + DB)
- `services/telegram_bot.py` — Telegram alerts + remote commands
- `services/alerts/alert_service.py` — Price/technical alert checking
- `services/cache.py` — Redis caching utilities

### Database Models (27)

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

### 2026-02-13 — Auto-Scan Fix + Logs Viewer + Sentry Integration
- **Fixed**: Auto-scan not firing on Railway — `automation.auto_scan_enabled` defaulted to `false` with no UI toggle. Added one-time migration in `seed_defaults()` to force-update existing DB values via sentinel key `_internal.auto_scan_defaults_v2`.
- **New service**: `services/log_sink.py` — Loguru custom sink pushing structured JSON logs to Redis list `app:logs` (5000 entry ring buffer via LPUSH+LTRIM).
- **New API**: `api/endpoints/logs.py` — GET /api/v1/logs with level/search/module filtering and configurable limit.
- **New page**: `frontend/src/pages/Logs.jsx` — Real-time log viewer with auto-refresh (5s), level filters, free-text search, module filter, color-coded monospace entries, follow-tail mode.
- **Modified**: `autopilot.py` — /status endpoint now returns `auto_scan_enabled` and `auto_scan_presets` fields.
- **Modified**: `Autopilot.jsx` — Added Auto-Scan master toggle (green) and multi-select preset pills fetched from GET /screener/presets.
- **Modified**: `main.py` — Registered Redis log sink, logs router, and optional Sentry SDK init (via SENTRY_DSN env var).
- **Modified**: `config.py` — Added `SENTRY_DSN` setting.
- **Modified**: `requirements.txt` — Added `sentry-sdk[fastapi]>=2.0.0`.
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
