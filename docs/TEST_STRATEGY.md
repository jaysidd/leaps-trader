# LEAPS Trader — Production-Grade Test Strategy

> Tailored for the actual codebase: FastAPI + React 19 + Zustand + Alpaca/FMP + Backtrader
> Last updated: 2026-02-12

---

## Table of Contents

1. [Architecture Under Test](#1-architecture-under-test)
2. [Test Pyramid & Tooling](#2-test-pyramid--tooling)
3. [Positive Scenarios (Happy Path)](#3-positive-scenarios-happy-path)
4. [Negative Scenarios (Failure & Error Handling)](#4-negative-scenarios-failure--error-handling)
5. [Visual Regression Testing](#5-visual-regression-testing)
6. [Edge Cases & Market Conditions](#6-edge-cases--market-conditions)
7. [Data Integrity & Financial Accuracy](#7-data-integrity--financial-accuracy)
8. [Performance & Load Testing](#8-performance--load-testing)
9. [Automation Architecture](#9-automation-architecture)
10. [Observability & Monitoring](#10-observability--monitoring)
11. [Test Case Matrix](#11-test-case-matrix)
12. [Risk-Based Prioritization](#12-risk-based-prioritization)
13. [CI/CD Pipeline Architecture](#13-cicd-pipeline-architecture)
14. [Mock Broker API Design](#14-mock-broker-api-design)
15. [Failure Simulation Plan](#15-failure-simulation-plan)

---

## 1. Architecture Under Test

### What Exists (Scope IN)

| Layer | Technology | Key Components |
|-------|-----------|----------------|
| **Frontend** | React 19 + Vite + Zustand + Tailwind | 11 pages, 50+ components, 8 stores, 18 API clients |
| **Backend API** | FastAPI + SQLAlchemy + APScheduler | 21 router groups, 27 models, 40+ services |
| **Trading Bot** | AutoTrader singleton + 6-stage pipeline | Risk Gateway (16 checks), Position Sizer (3 modes), Order Executor, Position Monitor |
| **Signal Engine** | 5 strategies (ORB, VWAP, Range, TF, MR) | Strategy Selector, Signal Validator (Claude AI), scheduled processing |
| **Screening** | 4-stage pipeline + 50 filters | Finviz + FMP data sources, scoring engine |
| **Backtesting** | Backtrader (blocking, thread pool) | 5 strategy classes, max 3 concurrent, equity curve + trade log |
| **Broker** | Alpaca (paper + live) | Orders, positions, account, options chains |
| **Data** | FMP + Alpaca + Finviz + TastyTrade | Fundamentals, prices, options, sentiment, technicals |
| **AI** | Claude (Anthropic) | Signal validation, market regime, copilot chat |
| **Infra** | PostgreSQL + Redis + WebSocket | Rate limiting, request timeout, session cleanup |
| **Notifications** | Telegram | Trade alerts, scan summaries, roll alerts |

### What Does NOT Exist (Scope OUT — Removed from Template)

| Template Item | Why Removed |
|---------------|------------|
| IBKR integration | Not implemented — Alpaca only |
| Modify order before execution | No order modification endpoint exists |
| PDT violations | Not enforced in app (Alpaca handles it) |
| Margin call risk | No margin trading support |
| Expired option contract placement | Options are read-only (chains + Greeks); no option order execution via app |
| Incorrect strike selection | No option order flow in app |
| Partial fill rejection | No partial fill handling implemented |
| Greeks recalculation (Delta, Theta, Vega) | Read-only from TastyTrade — app doesn't compute Greeks |
| Option Greeks accuracy tests | Consumed from provider, not calculated |
| Watchlist add/remove | No watchlist feature in current UI |
| 100/500 concurrent users | Single-user app (no auth system) |
| Canary testing | No multi-environment deployment |
| Contract tests | Single team, no microservices |

---

## 2. Test Pyramid & Tooling

```
                    ┌─────────────┐
                    │   E2E (PW)  │  ~30 tests — Critical user flows
                    ├─────────────┤
                 ┌──┤ Integration │  ~60 tests — API + DB + services
                 │  ├─────────────┤
              ┌──┤  │    Unit     │  ~150 tests — Pure logic, formatters, scoring
              │  │  └─────────────┘
              │  │
```

| Layer | Tool | Target | Count |
|-------|------|--------|-------|
| **Unit (Frontend)** | Vitest + @testing-library/react | Formatters, utils, store logic, component rendering | ~50 |
| **Unit (Backend)** | pytest + pytest-asyncio | Scoring, risk checks, position sizing, signal logic | ~80 |
| **Integration (Backend)** | pytest + httpx (TestClient) + test DB | API endpoints, DB operations, scheduler jobs | ~60 |
| **E2E (Frontend)** | Playwright (TypeScript) | Full page flows against running backend | ~30 |
| **Visual Regression** | Playwright screenshots + pixelmatch | Key UI states, dark/light mode, charts | ~20 |
| **Performance** | k6 (load), Playwright (timing) | API latency, page load, WebSocket throughput | ~10 |

### New Dependencies Required

**Frontend** (`package.json devDependencies`):
```json
{
  "@playwright/test": "^1.50.0",
  "msw": "^2.0.0"
}
```

**Backend** (`requirements-test.txt`):
```
pytest==8.3.0
pytest-asyncio==0.24.0
pytest-cov==6.0.0
httpx==0.28.0
freezegun==1.4.0
factory-boy==3.3.0
respx==0.22.0
```

---

## 3. Positive Scenarios (Happy Path)

### 3.1 Signal-to-Trade Pipeline (HIGHEST PRIORITY)

#### TC-HP-01: Manual Signal → Bot Execution
```
Preconditions:
  - Bot config exists with valid Alpaca paper keys
  - At least 1 signal in ACTIVE status
  - Alpaca paper account has buying power > $1000

Steps:
  1. Navigate to /signals
  2. Click "Trade" button on an ACTIVE signal
  3. SendToBotModal opens → verify preview phase shows:
     - Symbol, strategy, direction
     - Position size calculation
     - Risk/reward preview
     - Stop loss / take profit levels
  4. Click "Execute" button
  5. Confirm execution

Expected Result:
  - Order placed via Alpaca API (paper mode)
  - ExecutedTrade record created in DB
  - Signal status updated to EXECUTED
  - Toast notification: "Order placed for {symbol}"
  - Position appears in /portfolio or bot active trades

Data Validation:
  - executed_trade.entry_price matches Alpaca fill price (±0.5%)
  - executed_trade.quantity matches position_sizer output
  - executed_trade.stop_loss_price set per bot config
  - executed_trade.take_profit_price set per bot config
  - executed_trade.signal_id references the source signal

Backend Confirmation:
  - GET /api/v1/trading/bot/active-trades returns new trade
  - Alpaca GET /v2/orders shows matching order

UI State:
  - Modal closes after execution
  - Signal row shows "Executed" badge
  - Active trades count increments in BotStatusBar
```

#### TC-HP-02: Screening → Auto-Process → Signal Generation
```
Preconditions:
  - FMP + Alpaca API keys configured
  - Market data available for test symbols
  - At least 1 screening preset saved

Steps:
  1. Navigate to /saved-scans
  2. Click "Auto-Process" on a saved scan
  3. Wait for strategy selection to complete
  4. Verify results panel shows:
     - HIGH confidence stocks (auto-queued)
     - MEDIUM confidence stocks (review needed)
     - LOW confidence stocks (skipped)
  5. Navigate to /signals → Signal Queue tab

Expected Result:
  - HIGH confidence stocks appear in signal queue
  - Each queued item has strategy + timeframe assigned
  - Signal engine processes queue on next scheduler tick

Data Validation:
  - signal_queue records created with correct cap_size, timeframe, strategy
  - strategy_selector confidence matches displayed confidence
  - stock_data JSON populated with FMP metrics
```

#### TC-HP-03: Place Market Buy via Quick Trade
```
Preconditions:
  - Alpaca paper account connected
  - Buying power > order value

Steps:
  1. Call POST /api/v1/trading/quick-buy/AAPL?qty=1
  2. Verify 200 response with order ID
  3. Poll GET /api/v1/trading/orders/{id} until filled

Expected Result:
  - Order status transitions: new → accepted → filled
  - Position created for AAPL
  - Account buying power decremented

Data Validation:
  - order.filled_avg_price within 0.5% of last trade price
  - order.filled_qty == 1
  - position.qty == 1
```

#### TC-HP-04: Close Full Position
```
Preconditions:
  - Open position exists for symbol

Steps:
  1. Call POST /api/v1/trading/positions/AAPL/close
  2. Verify order placed and filled

Expected Result:
  - Position fully liquidated
  - PnL calculated correctly
  - Position disappears from GET /positions

Data Validation:
  - realized_pnl = (exit_price - entry_price) × qty
```

#### TC-HP-05: Close Partial Position
```
Preconditions:
  - Open position with qty >= 2

Steps:
  1. Call POST /api/v1/trading/positions/AAPL/close { qty: 1 }
  2. Verify partial fill

Expected Result:
  - Position qty decremented by 1
  - Remaining position still shown

Data Validation:
  - position.qty == original_qty - 1
  - order.filled_qty == 1
```

#### TC-HP-06: Cancel Open Order
```
Preconditions:
  - Limit order placed (not yet filled)

Steps:
  1. Call DELETE /api/v1/trading/orders/{id}
  2. Verify cancellation

Expected Result:
  - Order status → cancelled
  - Buying power restored
  - Order removed from open orders list
```

#### TC-HP-07: Run Backtest and View Results
```
Preconditions:
  - PostgreSQL running, Alpaca API available for historical data

Steps:
  1. Navigate to /backtesting
  2. Configure: AAPL, ORB strategy, 1h timeframe, large_cap, last 30 days
  3. Click "Run Backtest"
  4. Wait for completion (poll status)

Expected Result:
  - Metrics displayed: Sharpe ratio, total return %, max drawdown, win rate, profit factor
  - Equity curve chart renders (lightweight-charts)
  - Trade log table populated
  - Backtest appears in history section

Data Validation:
  - backtest_result.status == "completed"
  - metrics JSON contains all required fields
  - equity_curve array is non-empty and monotonically timestamped
  - trade_log entries sum to total_return metric (±rounding)
```

#### TC-HP-08: Bot Start → Signal Processing → Auto-Execution
```
Preconditions:
  - Bot config: execution_mode = "full_auto"
  - Signal queue populated
  - Bot status: STOPPED

Steps:
  1. POST /api/v1/trading/bot/start
  2. Wait for next signal processing tick (5 min or trigger manually)
  3. Observe auto-execution pipeline

Expected Result:
  - Bot status → RUNNING
  - Signals processed through: Risk Gateway → Position Sizer → Order Executor
  - ExecutedTrade records created
  - Position Monitor begins tracking

Data Validation:
  - bot_state.status == "RUNNING"
  - bot_state.is_running == True
  - executed_trades have signal_id references
```

#### TC-HP-09: Semi-Auto Signal → Approve → Execute
```
Preconditions:
  - Bot config: execution_mode = "semi_auto"
  - Signal generated

Steps:
  1. Signal appears as PENDING_APPROVAL
  2. GET /api/v1/trading/bot/pending-approvals
  3. POST /api/v1/trading/bot/approve/{trade_id}

Expected Result:
  - Trade executes through full pipeline
  - Status: PENDING_APPROVAL → OPEN
  - Position created on Alpaca
```

#### TC-HP-10: View Analytics Dashboard (Command Center)
```
Steps:
  1. Navigate to / (CommandCenter)
  2. Verify all widgets render:
     - Market Pulse, Fear & Greed Gauge, MRI Gauge
     - News Ticker, Catalyst Feed
     - Morning Brief, Trade Readiness Gauge
     - Macro Overlay, Polymarket Widget

Expected Result:
  - No loading spinners stuck indefinitely
  - All gauges show valid numeric ranges
  - News ticker scrolls
  - No console errors
```

#### TC-HP-11: Paper vs Live Trading Mode Switch
```
Steps:
  1. GET /api/v1/trading/mode → verify current mode
  2. PUT /api/v1/trading/mode { paper_mode: true }
  3. Verify all subsequent trades go to paper account

Expected Result:
  - Mode persists across requests
  - Account info reflects paper account
```

#### TC-HP-12: Dark Mode Toggle
```
Steps:
  1. Click dark mode toggle
  2. Verify all pages render correctly in dark mode
  3. Refresh page → verify persistence (localStorage)

Expected Result:
  - All text readable (contrast ratios)
  - Charts render with dark background
  - No white flash on page transitions
```

---

## 4. Negative Scenarios (Failure & Error Handling)

### 4.1 Trading Failures

#### TC-NEG-01: Insufficient Buying Power
```
Steps:
  1. Set up paper account with <$10 buying power
  2. Attempt to buy $1000 worth of stock

Expected:
  - Risk Gateway rejects (check #6: buying power)
  - UI shows error: "Insufficient buying power"
  - No order placed on Alpaca
  - No ExecutedTrade record created
  - No duplicate orders on retry
```

#### TC-NEG-02: Invalid Symbol
```
Steps:
  1. POST /api/v1/trading/quick-buy/ZZZZZ?qty=1
  2. POST /api/v1/signals/queue/add { symbol: "!!!INVALID" }

Expected:
  - API returns 400/422 with descriptive error
  - Input validation regex catches invalid symbols
  - No partial state changes in DB
```

#### TC-NEG-03: Broker API Timeout
```
Steps:
  1. Mock Alpaca API to respond after 15s (beyond timeout)
  2. Attempt order placement

Expected:
  - TradingClient timeout fires (monkey-patched)
  - Retry logic attempts (up to configured retries)
  - After max retries: error logged, user notified
  - No ghost orders (verify via Alpaca GET /orders)
  - consecutive_errors incremented on bot_state
```

#### TC-NEG-04: API Rate Limit Exceeded
```
Steps:
  1. Send 130 requests within 60 seconds from same IP

Expected:
  - First 120 succeed (200)
  - Requests 121-130 return 429 Too Many Requests
  - Rate limit resets after sliding window
  - No data corruption during rate limiting
```

#### TC-NEG-05: WebSocket Disconnect During Active Monitoring
```
Steps:
  1. Connect to /ws for price stream
  2. Kill WebSocket connection server-side
  3. Observe reconnection behavior

Expected:
  - priceStreamStore.isConnected → false
  - Auto-reconnect attempts with backoff
  - Position monitor continues (uses REST fallback)
  - No phantom position updates from stale data
```

#### TC-NEG-06: Order Rejected by Broker
```
Steps:
  1. Mock Alpaca to return order rejection (e.g., market closed)

Expected:
  - ExecutedTrade NOT created (or marked FAILED)
  - Error message includes rejection reason
  - Risk Gateway logs rejection
  - Bot consecutive_errors incremented
  - If max_consecutive_errors reached → bot auto-pauses
```

#### TC-NEG-07: Corrupted/Missing Market Data
```
Steps:
  1. Mock FMP to return null/empty for a symbol's technicals
  2. Run signal engine on that symbol

Expected:
  - Signal engine skips symbol with log warning
  - No NaN/None propagation into signal calculations
  - Other symbols in queue process normally
  - No unhandled exceptions
```

#### TC-NEG-08: Database Connection Failure
```
Steps:
  1. Kill PostgreSQL mid-request

Expected:
  - SQLAlchemy pool_pre_ping detects stale connection
  - Retry on next request
  - No session leaks (context manager pattern)
  - Global exception handler returns 500 (no stack trace)
```

#### TC-NEG-09: Concurrent Backtest Limit
```
Steps:
  1. Submit 4 backtests simultaneously

Expected:
  - First 3 execute concurrently
  - 4th waits (Semaphore(3) with 5-min timeout)
  - If timeout exceeded → returns 503 "Server busy"
  - No thread pool exhaustion
```

#### TC-NEG-10: Duplicate Signal Queue Submission
```
Steps:
  1. Add AAPL to signal queue
  2. Add AAPL again with same timeframe/strategy

Expected:
  - Duplicate detection prevents second entry
  - User notified "Already in queue"
  - Single queue entry exists in DB
```

#### TC-NEG-11: Bot Start When Already Running
```
Steps:
  1. POST /api/v1/trading/bot/start (bot already RUNNING)

Expected:
  - Returns error: "Bot is already running"
  - No state corruption
  - No duplicate scheduler jobs
```

#### TC-NEG-12: Signal Validation — AI Rejection
```
Steps:
  1. Create signal that would fail AI validation (confidence < 40)

Expected:
  - Signal marked validation_status = "REJECTED"
  - validation_reasoning populated with Claude's explanation
  - Signal NOT auto-executed
  - Signal visible in UI with rejection badge
```

#### TC-NEG-13: Request Timeout (120s)
```
Steps:
  1. Mock a slow endpoint (not in skip list)
  2. Wait > 120 seconds

Expected:
  - Middleware kills request at 120s
  - Returns 504 Gateway Timeout
  - Long-running paths (/backtesting/run, /screener/run, /ai/*) are exempt
```

---

## 5. Visual Regression Testing

### Strategy

| Tool | Purpose |
|------|---------|
| Playwright `page.screenshot()` | Capture full-page and component-level screenshots |
| `pixelmatch` / `@playwright/test toHaveScreenshot()` | Pixel-level diff against baselines |

### Snapshot Capture Points

| ID | Page/State | What to Capture |
|----|-----------|-----------------|
| VR-01 | CommandCenter — loaded | All widgets rendered, gauges populated |
| VR-02 | CommandCenter — dark mode | Same widgets in dark theme |
| VR-03 | Screener — results table | Populated screening results with scores |
| VR-04 | Signals — queue + active signals | Signal cards with status badges |
| VR-05 | SendToBotModal — preview phase | Position size, risk/reward, SL/TP |
| VR-06 | SendToBotModal — post-execution | Success state |
| VR-07 | Backtesting — metrics + equity curve | Chart + metric cards |
| VR-08 | Backtesting — trade log table | Populated trade log |
| VR-09 | Portfolio — positions table | Holdings with P&L colors |
| VR-10 | TradeJournal — trades history | Executed trades with status |
| VR-11 | BotPerformance — metrics | Performance cards + chart |
| VR-12 | Settings — bot config form | All fields rendered |
| VR-13 | Settings — automation tab | Scheduled scan config |
| VR-14 | MacroIntelligence — full page | FRED data + MRI + catalysts |
| VR-15 | HeatMap — sector heatmap | Color-coded sectors |
| VR-16 | Error state — API failure | Error banners on pages |
| VR-17 | Responsive — 768px width | Navigation collapse, table scroll |
| VR-18 | Responsive — 1920px width | Full layout |
| VR-19 | BotStatusBar — running state | Green indicator, active trade count |
| VR-20 | BotStatusBar — paused/error state | Yellow/red indicator |

### Color Consistency Checks

| Element | Expected |
|---------|----------|
| BUY signals | Green (`text-green-600`) |
| SELL signals | Red (`text-red-600`) |
| Positive P&L | Green |
| Negative P&L | Red |
| Neutral/zero | Gray (`text-gray-600`) |
| Score >= 70 | Green |
| Score 50-69 | Yellow |
| Score < 50 | Red |
| HIGH confidence | Green badge |
| MEDIUM confidence | Yellow badge |
| LOW confidence | Red badge |

### Baseline Policy

- Baselines committed to git (`tests/e2e/__screenshots__/`)
- Updated on intentional UI changes only (requires PR review)
- Pixel diff threshold: **0.1%** (trading UIs must be pixel-accurate for financial data)
- Separate baselines per viewport: 1280×720 (default), 768×1024 (tablet), 1920×1080 (desktop)

---

## 6. Edge Cases & Market Conditions

### 6.1 Market Hours Behavior

#### TC-EDGE-01: Market Open vs Closed
```
Tests:
  - Signal engine behavior during market hours (generates signals)
  - Signal engine behavior outside market hours (skips or queues)
  - Position monitor outside hours (no SL/TP checks for equities)
  - EOD close trigger (eod_close_minutes_before market close)
  - Bot daily reset at 9:30 AM ET
  - Scanner behavior outside hours (uses cached data)

Validation:
  - marketHours.js utility returns correct isOpen state
  - Scheduler jobs respect market calendar
```

#### TC-EDGE-02: Pre-Market / After-Hours Data
```
Tests:
  - Alpaca extended hours data availability
  - Signal engine: does it use extended hours bars?
  - Position monitor: extended hours price for SL/TP?

Expected:
  - App should use regular session data only (unless explicitly configured)
  - Extended hours prices should NOT trigger stop losses
```

#### TC-EDGE-03: EOD Auto-Close
```
Tests:
  - Equity positions close at configured minutes before close
  - LEAPS/option positions are SKIPPED (already implemented)
  - Bot config eod_close_minutes_before respected (default: 5)

Validation:
  - Only equity ExecutedTrades with exit_reason="EOD_CLOSE"
  - Option positions untouched
```

### 6.2 Concurrency & Idempotency

#### TC-EDGE-04: Duplicate Click Submission
```
Steps:
  1. Click "Execute" button rapidly 3 times in SendToBotModal

Expected:
  - Only 1 order placed
  - Button disabled after first click
  - No duplicate ExecutedTrade records
```

#### TC-EDGE-05: Concurrent Signal Processing
```
Steps:
  1. Two signal engine scheduler ticks fire simultaneously

Expected:
  - Singleton AutoTrader prevents duplicate processing
  - Same signal not processed twice
  - No race condition on DB commits
```

#### TC-EDGE-06: Multi-Tab Usage
```
Steps:
  1. Open app in 2 browser tabs
  2. Execute trade in tab 1
  3. Observe tab 2

Expected:
  - Tab 2 polling updates reflect new trade
  - No conflicting state between tabs
  - WebSocket connections both active
```

#### TC-EDGE-07: Network Drop Mid-Order
```
Steps:
  1. Initiate order placement
  2. Disconnect network after request sent, before response received

Expected:
  - Frontend shows timeout error
  - Backend order may or may not have been placed
  - User can check /orders to verify
  - No phantom positions in local state
```

### 6.3 Data Edge Cases

#### TC-EDGE-08: Symbol with No Historical Data
```
Steps:
  1. Add newly IPO'd stock to signal queue
  2. Signal engine processes it

Expected:
  - has_sufficient_data check fails (needs 200 trading days)
  - Symbol skipped with reason logged
  - Not counted as error
```

#### TC-EDGE-09: FMP API Returns Stale Data
```
Steps:
  1. FMP cache TTL expires
  2. FMP API is slow/unavailable

Expected:
  - Redis cache miss → API call with retry
  - If API fails, signal engine skips symbol
  - Stale cache (if `cached is not None` check) used as fallback
```

#### TC-EDGE-10: Zero-Price / Halted Stock
```
Steps:
  1. Stock in queue is halted (Alpaca returns no quote)

Expected:
  - Signal engine detects missing price data
  - Skips signal generation
  - Risk gateway would reject (no entry_price)
```

#### TC-EDGE-11: Bulk Queue Limit
```
Steps:
  1. POST /api/v1/signals/queue/bulk-add with 101 symbols

Expected:
  - API returns 400: "Maximum 100 symbols per bulk add"
  - No partial inserts
```

#### TC-EDGE-12: Trailing Stop Without Entry Price
```
Steps:
  1. ExecutedTrade exists with entry_price = None

Expected:
  - Position monitor skips trailing stop check
  - Initializes high_water_mark from current_price
  - Logged as warning, not error
```

---

## 7. Data Integrity & Financial Accuracy

### 7.1 PnL Calculations

#### TC-FIN-01: Realized PnL (Long)
```
Formula: realized_pnl = (exit_price - entry_price) × quantity
Tolerance: ±$0.01 (penny-level)
Rounding: HALF_EVEN (banker's rounding)

Test cases:
  - Profit: entry=100.00, exit=105.50, qty=10 → PnL = $55.00
  - Loss: entry=100.00, exit=95.25, qty=10 → PnL = -$47.50
  - Break-even: entry=100.00, exit=100.00, qty=10 → PnL = $0.00
  - Fractional shares: entry=150.12, exit=155.67, qty=0.5 → PnL = $2.78
```

#### TC-FIN-02: Unrealized PnL
```
Formula: unrealized_pnl = (current_price - entry_price) × quantity
Updated: Every position monitor tick (1 min)
Tolerance: ±$0.01

Validation:
  - Matches Alpaca position unrealized_pl (±slippage window)
  - Negative values displayed in red, positive in green
```

#### TC-FIN-03: Max Drawdown Percentage
```
Formula: max_drawdown_pct = (peak_equity - trough_equity) / peak_equity × 100
Previous bug: Was storing dollar amount, now fixed to percentage

Test cases:
  - start_equity=10000, peak=12000, trough=9000 → drawdown = 25%
  - start_equity=50000, peak=50000, trough=45000 → drawdown = 10%
```

#### TC-FIN-04: Position Sizing (3 Modes)
```
Mode 1 - Fixed Dollar:
  - config.position_size_dollars = 5000
  - qty = floor(5000 / current_price)

Mode 2 - Percentage of Portfolio:
  - config.position_size_pct = 5 (%)
  - position_value = portfolio_value × 0.05
  - qty = floor(position_value / current_price)

Mode 3 - Risk-Based:
  - config.risk_per_trade_pct = 1 (%)
  - risk_dollars = portfolio_value × 0.01
  - risk_per_share = entry_price - stop_loss_price
  - qty = floor(risk_dollars / risk_per_share)

Validation:
  - qty always >= 1 (or reject if can't afford 1 share)
  - qty × current_price <= buying_power
  - Decimal precision: qty is integer for stocks
```

### 7.2 Screening & Scoring Accuracy

#### TC-FIN-05: Composite Score Calculation
```
Existing tests: backend/tests/test_composite.py
Extend with:
  - Boundary values (score = 0, score = 100)
  - DECIMAL(0) falsy check (score = 0 should NOT be None)
  - Sector-specific weight overrides
```

#### TC-FIN-06: ATR / RVOL Calculations
```
ATR: 14-period Average True Range
  - True Range = max(high-low, |high-prev_close|, |low-prev_close|)
  - ATR = SMA(TR, 14)
  - Tolerance: ±0.01

RVOL: Relative Volume
  - RVOL = current_volume / avg_volume(20d)
  - Tolerance: ±0.01
```

#### TC-FIN-07: Risk-to-Reward Ratio
```
Formula: r_r = (target_price - entry_price) / (entry_price - stop_loss_price)

Test cases:
  - entry=100, target=110, stop=95 → R:R = 2.0
  - entry=100, target=103, stop=98 → R:R = 1.5
  - entry=100, target=100, stop=95 → R:R = 0.0 (should reject)
  - entry=100, target=90, stop=95 → R:R = negative (should reject)
```

### 7.3 Backtest Result Accuracy

#### TC-FIN-08: Backtest Metrics Validation
```
Sharpe Ratio:
  - sharpe = mean(returns) / std(returns) × sqrt(252)
  - Tolerance: ±0.01

Win Rate:
  - win_rate = winning_trades / total_trades × 100
  - Must match trade_log count

Profit Factor:
  - profit_factor = sum(winning_pnl) / abs(sum(losing_pnl))
  - Tolerance: ±0.01

Equity Curve:
  - First point = initial_capital
  - Last point = initial_capital + total_pnl
  - Monotonically timestamped
  - No gaps
```

### 7.4 Decimal Precision Standards

| Data Type | Precision | Example |
|-----------|-----------|---------|
| Stock price | 2 decimal places | $150.25 |
| PnL | 2 decimal places | -$47.50 |
| Percentage | 2 decimal places | 12.50% |
| Score | 1 decimal place | 78.5 |
| Quantity (stocks) | Integer | 10 |
| Quantity (fractional) | Up to 6 decimals | 0.123456 |
| ATR | 2 decimal places | 3.45 |
| RVOL | 2 decimal places | 1.85 |
| Sharpe | 2 decimal places | 1.23 |

---

## 8. Performance & Load Testing

### 8.1 API Latency Targets

| Endpoint Category | P50 Target | P95 Target | P99 Target |
|-------------------|-----------|-----------|-----------|
| Trading (place order) | <200ms | <500ms | <1s |
| Signal queue (CRUD) | <100ms | <300ms | <500ms |
| Screening (run scan) | <30s | <60s | <90s |
| Backtesting (run) | <60s | <120s | <300s |
| Command Center (load) | <500ms | <1s | <2s |
| Portfolio (positions) | <200ms | <500ms | <1s |
| Settings (read/write) | <100ms | <200ms | <500ms |

### 8.2 Frontend Performance

| Metric | Target |
|--------|--------|
| Initial page load (LCP) | <2s |
| Route navigation | <500ms |
| Chart render (equity curve) | <1s |
| Table render (100 rows) | <500ms |
| Dark mode toggle | <100ms |

### 8.3 Load Test Scenarios (k6)

| Scenario | Load | Duration | Key Metric |
|----------|------|----------|------------|
| Signal queue burst | 50 add-to-queue/sec | 60s | Error rate < 1%, all 200s |
| Screening concurrent | 5 concurrent scans | 5 min | All complete, no timeouts |
| Backtest saturation | 6 concurrent (3 active + 3 queued) | 10 min | Semaphore holds, no crashes |
| Position monitor under load | 50 active positions | 1 hour | No missed SL/TP checks |
| WebSocket price stream | 100 symbols | 10 min | No message drops, reconnect < 5s |
| Rate limit validation | 150 req/min | 2 min | 120 succeed, 30 return 429 |

### 8.4 Resource Limits

| Resource | Threshold | Alert |
|----------|-----------|-------|
| Backend memory | <512MB | Warning at 400MB |
| Redis memory | <256MB | Warning at 200MB |
| PostgreSQL connections | <20 pool (10 base + 20 overflow) | Warning at 15 |
| CPU per backtest | <1 core | Warning at 80% |
| aiohttp sessions | 5 max | Verified at shutdown |

---

## 9. Automation Architecture

### 9.1 Test Structure

```
leaps-trader/
├── tests/
│   ├── e2e/                          # Playwright E2E tests
│   │   ├── playwright.config.ts
│   │   ├── fixtures/
│   │   │   ├── auth.ts               # Setup (no auth, just base URL)
│   │   │   ├── mock-data.ts          # Seed data for tests
│   │   │   └── test-helpers.ts       # Common assertions
│   │   ├── pages/                    # Page Object Models
│   │   │   ├── command-center.page.ts
│   │   │   ├── screener.page.ts
│   │   │   ├── signals.page.ts
│   │   │   ├── backtesting.page.ts
│   │   │   ├── portfolio.page.ts
│   │   │   ├── settings.page.ts
│   │   │   ├── trade-journal.page.ts
│   │   │   └── bot-performance.page.ts
│   │   ├── flows/                    # E2E test specs
│   │   │   ├── signal-to-trade.spec.ts
│   │   │   ├── screening-pipeline.spec.ts
│   │   │   ├── backtesting.spec.ts
│   │   │   ├── bot-management.spec.ts
│   │   │   ├── portfolio-view.spec.ts
│   │   │   └── settings-config.spec.ts
│   │   ├── visual/                   # Screenshot tests
│   │   │   ├── dashboard.visual.ts
│   │   │   ├── dark-mode.visual.ts
│   │   │   └── responsive.visual.ts
│   │   └── __screenshots__/          # Baseline images
│   │
│   ├── frontend/                     # Vitest unit tests
│   │   ├── utils/
│   │   │   ├── formatters.test.ts
│   │   │   └── marketHours.test.ts
│   │   ├── stores/
│   │   │   ├── botStore.test.ts
│   │   │   ├── signalsStore.test.ts
│   │   │   └── backtestStore.test.ts
│   │   └── components/
│   │       ├── SendToBotModal.test.tsx
│   │       ├── BotStatusBar.test.tsx
│   │       └── ResultsTable.test.tsx
│   │
│   └── backend/                      # pytest (existing + new)
│       ├── conftest.py               # DB fixtures, mock factories
│       ├── unit/
│       │   ├── test_risk_gateway.py
│       │   ├── test_position_sizer.py
│       │   ├── test_position_monitor.py
│       │   ├── test_signal_engine.py
│       │   ├── test_strategy_selector.py
│       │   └── test_formatters.py
│       ├── integration/
│       │   ├── test_bot_endpoints.py
│       │   ├── test_signal_endpoints.py
│       │   ├── test_trading_endpoints.py
│       │   ├── test_backtesting_endpoints.py
│       │   └── test_screening_endpoints.py
│       └── services/                 # Existing tests (11 files)
│           ├── test_composite.py
│           ├── test_options.py
│           └── ...
```

### 9.2 Mock Broker Environment

```python
# tests/mocks/mock_alpaca.py

class MockAlpacaTradingClient:
    """
    Deterministic mock for Alpaca TradingClient.
    Supports: orders, positions, account, options chains.
    """

    def __init__(self, paper=True):
        self.orders = {}
        self.positions = {}
        self.account = MockAccount(
            buying_power=100_000.0,
            portfolio_value=100_000.0,
            equity=100_000.0
        )

    def submit_order(self, order_data):
        """Simulate order placement with configurable fill behavior."""
        order = MockOrder(
            id=uuid4(),
            symbol=order_data.symbol,
            qty=order_data.qty,
            side=order_data.side,
            status="filled",  # Instant fill for tests
            filled_avg_price=self._get_mock_price(order_data.symbol),
            filled_qty=order_data.qty,
        )
        self.orders[order.id] = order
        self._update_positions(order)
        return order

    def get_all_positions(self):
        return list(self.positions.values())

    def close_position(self, symbol, **kwargs):
        if symbol in self.positions:
            del self.positions[symbol]
            return MockOrder(status="filled")
        raise APIError("Position not found")

# Configurable failure modes:
class MockAlpacaWithFailures(MockAlpacaTradingClient):
    def __init__(self, fail_on=None, timeout_on=None, reject_on=None):
        super().__init__()
        self.fail_on = fail_on or []        # Symbols that throw errors
        self.timeout_on = timeout_on or []   # Symbols that timeout
        self.reject_on = reject_on or []     # Symbols that get rejected
```

### 9.3 Test Data Strategy

| Data Category | Strategy | Source |
|--------------|----------|--------|
| Stock prices | Frozen fixtures (JSON) | Captured from Alpaca paper |
| Screening results | Factory-generated | factory-boy + realistic ranges |
| Bot configuration | Preset configs (3 profiles) | Conservative, moderate, aggressive |
| Signals | Seeded per strategy type | 1 per strategy × 2 timeframes |
| Backtest results | Pre-computed fixtures | Known-good results for validation |
| FMP fundamentals | Redis-cached snapshots | Captured and frozen |
| User settings | Default + custom profiles | Settings model defaults |

### 9.4 Paper Trading Sandbox Validation

```
Test Environment:
  - Alpaca paper account (dedicated test keys)
  - PostgreSQL test database (leaps_trader_test)
  - Redis test instance (DB index 1)
  - Frontend pointed at test backend

Validation Flow:
  1. Reset paper account positions
  2. Seed test data (signals, queue, bot config)
  3. Run E2E flow: signal → execute → monitor → close
  4. Verify final account state matches expected P&L
  5. Tear down test data
```

---

## 10. Observability & Monitoring

### 10.1 What to Log

| Category | Log Level | Content |
|----------|-----------|---------|
| Order placement | INFO | symbol, qty, side, order_type, signal_id |
| Order fill | INFO | order_id, filled_price, filled_qty, latency_ms |
| Order rejection | ERROR | order_id, rejection_reason, full_response |
| Risk gateway pass | DEBUG | trade_id, all 16 check results |
| Risk gateway reject | WARNING | trade_id, failed_check, reason |
| Position monitor action | INFO | trade_id, action (SL/TP/trailing/EOD), trigger_price |
| Signal generated | INFO | symbol, strategy, timeframe, direction, strength |
| AI validation result | INFO | signal_id, confidence, status, reasoning_summary |
| Bot state change | INFO | old_status → new_status, trigger (user/auto/error) |
| Backtest complete | INFO | id, strategy, symbol, duration_ms, total_return |
| API error | ERROR | endpoint, status_code, error_message, request_id |
| Rate limit hit | WARNING | IP, request_count, window |
| DB session leak | ERROR | session_id, endpoint, duration |
| Scheduler job failure | ERROR | job_id, exception, traceback |

### 10.2 Alert Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| Order failure spike | >3 failures in 5 minutes | CRITICAL |
| Bot consecutive errors | consecutive_errors >= 3 | HIGH |
| Bot auto-pause triggered | max_consecutive_errors reached | CRITICAL |
| Max drawdown exceeded | drawdown_pct > configured max | CRITICAL |
| Daily loss limit hit | daily_pnl < -configured limit | CRITICAL |
| API error rate | >5% of requests in 5 min window | HIGH |
| Response latency | P95 > 2s for 5 minutes | HIGH |
| WebSocket disconnect | No reconnect in 30s | MEDIUM |
| Backtest timeout | Running > 5 minutes | MEDIUM |
| Screening timeout | Running > 2 minutes | MEDIUM |
| Redis connection lost | Connection refused | HIGH |
| PostgreSQL pool exhausted | Active connections > 25 | CRITICAL |
| Memory usage | >80% of limit | HIGH |

### 10.3 Monitoring Dashboard Metrics

| Metric | Type | Source |
|--------|------|--------|
| Orders placed (today) | Counter | executed_trades table |
| Orders failed (today) | Counter | Error logs |
| Active positions | Gauge | Alpaca API |
| Daily PnL | Gauge | daily_bot_performance |
| Signal queue depth | Gauge | signal_queue table |
| Backtest running count | Gauge | Semaphore counter |
| API request rate | Rate | Rate limiter middleware |
| WebSocket connections | Gauge | Connection manager |
| Bot uptime | Timer | bot_state.started_at |
| Scheduler job latency | Histogram | APScheduler events |

---

## 11. Test Case Matrix

### Priority: P0 (Must Pass Before Any Deploy)

| ID | Category | Test | Backend | Frontend | E2E |
|----|----------|------|---------|----------|-----|
| P0-01 | Trading | Manual signal execution (full pipeline) | ✅ | ✅ | ✅ |
| P0-02 | Trading | Risk gateway rejects insufficient buying power | ✅ | | |
| P0-03 | Trading | Position sizing produces correct qty | ✅ | | |
| P0-04 | Trading | Stop loss triggers at correct price | ✅ | | |
| P0-05 | Trading | No duplicate orders on rapid clicks | | | ✅ |
| P0-06 | Financial | PnL calculation accuracy (±$0.01) | ✅ | | |
| P0-07 | Financial | Max drawdown percentage correct | ✅ | | |
| P0-08 | Bot | Bot start/stop/pause state transitions | ✅ | | ✅ |
| P0-09 | Bot | Consecutive errors → auto-pause | ✅ | | |
| P0-10 | Bot | EOD close skips LEAPS/options | ✅ | | |

### Priority: P1 (Must Pass Before Release)

| ID | Category | Test | Backend | Frontend | E2E |
|----|----------|------|---------|----------|-----|
| P1-01 | Signals | Signal engine generates valid signals | ✅ | | |
| P1-02 | Signals | Strategy selector categorizes correctly | ✅ | | |
| P1-03 | Signals | AI validation flows (accept/review/reject) | ✅ | | |
| P1-04 | Screening | Full screening pipeline runs | ✅ | | ✅ |
| P1-05 | Backtest | All 5 strategies produce valid results | ✅ | | |
| P1-06 | Backtest | Concurrent limit (3) enforced | ✅ | | |
| P1-07 | Portfolio | Positions display matches Alpaca | | | ✅ |
| P1-08 | UI | All pages load without errors | | | ✅ |
| P1-09 | UI | Dark mode renders correctly | | | ✅ |
| P1-10 | API | Rate limiting works (120 req/min) | ✅ | | |

### Priority: P2 (Should Pass)

| ID | Category | Test | Backend | Frontend | E2E |
|----|----------|------|---------|----------|-----|
| P2-01 | UI | Visual regression (20 snapshots) | | | ✅ |
| P2-02 | Perf | API latency within targets | ✅ | | |
| P2-03 | Perf | Page load < 2s | | | ✅ |
| P2-04 | Data | Formatter edge cases (null, NaN, 0) | | ✅ | |
| P2-05 | Data | Market hours utility accuracy | | ✅ | |
| P2-06 | Infra | WebSocket reconnection | | | ✅ |
| P2-07 | Infra | Request timeout (120s) | ✅ | | |
| P2-08 | Infra | Session cleanup on shutdown | ✅ | | |
| P2-09 | Bot | Semi-auto approval flow | ✅ | | ✅ |
| P2-10 | Bot | Trade journal daily aggregation | ✅ | | |

---

## 12. Risk-Based Prioritization

### Risk × Impact Matrix

```
                   HIGH IMPACT                    LOW IMPACT
              ┌─────────────────────┬─────────────────────┐
 HIGH RISK    │ P0: Trading pipeline│ P2: Formatting      │
              │ P0: PnL accuracy    │ P2: Visual regress  │
              │ P0: Risk gateway    │ P2: Dark mode       │
              │ P0: Position sizing │                     │
              ├─────────────────────┼─────────────────────┤
 LOW RISK     │ P1: Screening       │ P2: Performance     │
              │ P1: Backtesting     │ P2: Responsive      │
              │ P1: Signal engine   │ P2: Tooltips        │
              └─────────────────────┴─────────────────────┘
```

### Implementation Order

```
Phase 1 (Week 1): P0 — Trading Pipeline Safety
  - Risk gateway unit tests
  - Position sizer unit tests
  - PnL calculation tests
  - Position monitor (SL/TP/trailing) tests
  - Bot state machine tests
  → Prevents: Capital loss, wrong position sizes, missed stops

Phase 2 (Week 2): P0 E2E + P1 Backend
  - Playwright setup + signal-to-trade flow
  - Signal engine tests
  - Strategy selector tests
  - Backtest strategy tests
  → Prevents: Broken user flows, bad signals

Phase 3 (Week 3): P1 E2E + P2 Backend
  - All pages load test
  - Screening flow E2E
  - Rate limiting / timeout tests
  - Frontend unit tests (formatters, stores)
  → Prevents: UI regressions, infrastructure failures

Phase 4 (Week 4): P2 + Visual + Performance
  - Visual regression baselines
  - Performance benchmarks
  - WebSocket tests
  - Complete coverage gaps
  → Prevents: UX regressions, slow pages
```

---

## 13. CI/CD Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Git Push / PR                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Stage 1: Lint + Type Check (parallel, ~30s)            │
│  ├── ESLint (frontend)                                  │
│  ├── ruff (backend)                                     │
│  └── Type check (pyright or mypy — optional)            │
│                                                         │
│  Stage 2: Unit Tests (parallel, ~2min)                  │
│  ├── pytest backend/tests/unit/ --cov                   │
│  └── vitest run --coverage                              │
│                                                         │
│  Stage 3: Integration Tests (~3min)                     │
│  ├── Start PostgreSQL (test DB)                         │
│  ├── Start Redis (test instance)                        │
│  ├── pytest backend/tests/integration/                  │
│  └── Stop services                                      │
│                                                         │
│  Stage 4: E2E Tests (~5min)                             │
│  ├── Start backend (test mode)                          │
│  ├── Start frontend (test mode)                         │
│  ├── npx playwright test                                │
│  ├── Upload screenshots on failure                      │
│  └── Stop services                                      │
│                                                         │
│  Stage 5: Visual Regression (on PR only, ~2min)         │
│  ├── Compare against main branch baselines              │
│  └── Post diff images to PR comments                    │
│                                                         │
│  Gate: All stages green → merge allowed                 │
│                                                         │
│  Stage 6: Post-Merge (main branch only)                 │
│  ├── Build frontend (npm run build)                     │
│  ├── Run smoke test against staging                     │
│  └── Update visual baselines if changed                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Environment Variables for CI

```yaml
# GitHub Actions / CI secrets
ALPACA_API_KEY_TEST: paper trading key (dedicated test account)
ALPACA_SECRET_KEY_TEST: paper trading secret
FMP_API_KEY_TEST: FMP key (or mock)
DATABASE_URL_TEST: postgresql://test:test@localhost:5432/leaps_test
REDIS_URL_TEST: redis://localhost:6379/1
ANTHROPIC_API_KEY_TEST: Claude key (or mock for unit tests)
```

---

## 14. Mock Broker API Design

### Architecture

```
Tests can use 3 levels of mocking:

Level 1: Unit Test Mocks (fastest)
  - MockAlpacaTradingClient class
  - Returns deterministic data
  - No network calls
  - Used in: risk_gateway, position_sizer, order_executor tests

Level 2: respx HTTP Mocks (medium)
  - Intercepts actual HTTP calls
  - Returns realistic JSON responses
  - Tests retry logic, timeout handling
  - Used in: integration tests, alpaca_service tests

Level 3: Paper Trading (slowest, most realistic)
  - Real Alpaca paper account
  - Real order placement + fills
  - Used in: E2E smoke tests (nightly, not per-commit)
```

### Mock Response Fixtures

```
tests/fixtures/
├── alpaca/
│   ├── account.json              # Paper account snapshot
│   ├── order_filled.json         # Successful market order
│   ├── order_rejected.json       # Insufficient buying power
│   ├── positions.json            # 5 mock positions
│   ├── bars_1h.json              # 1-hour OHLCV bars
│   └── options_chain.json        # Option contracts
├── fmp/
│   ├── profile.json              # Company profile
│   ├── financials.json           # Income statement
│   ├── technicals_rsi.json       # RSI indicator
│   ├── technicals_sma.json       # SMA indicator
│   └── quote.json                # Real-time quote
└── signals/
    ├── orb_signal.json           # ORB breakout signal
    ├── vwap_signal.json          # VWAP pullback signal
    ├── trend_signal.json         # Trend following signal
    ├── mean_rev_signal.json      # Mean reversion signal
    └── range_signal.json         # Range breakout signal
```

---

## 15. Failure Simulation Plan

### Controlled Failure Injection

| Failure | Simulation Method | What to Verify |
|---------|-------------------|----------------|
| Alpaca API down | respx mock returns 503 | Retry → error → log → no ghost order |
| Alpaca timeout | respx mock with 15s delay | Timeout fires → retry → error |
| FMP API stale | Return data with old timestamp | Cache fallback used, signal skipped |
| PostgreSQL crash | Stop DB container mid-test | pool_pre_ping reconnects, 500 returned |
| Redis unavailable | Stop Redis mid-test | App degrades (no cache), API still works |
| WebSocket server crash | Close WS connection | Client reconnects with backoff |
| Scheduler job failure | Raise exception in job | Job retries on next interval, error logged |
| Memory pressure | Allocate large arrays in test | No OOM, graceful degradation |
| Concurrent writes | 10 parallel signal inserts | No duplicates, all succeed or conflict resolved |
| Bot crash mid-trade | Kill AutoTrader during execution | Position monitor picks up orphaned trades |
| Network partition | Block outbound traffic | Timeout → retry → error → no partial state |

### Chaos Testing Schedule

```
Nightly (automated):
  - Random API failure injection during E2E suite
  - Verify all failures are handled gracefully
  - No unhandled exceptions in logs
  - No orphaned DB records

Weekly (manual review):
  - Paper account reconciliation (app state vs Alpaca state)
  - Redis cache integrity check
  - PostgreSQL connection pool health
  - Memory leak detection (compare start/end memory)
```

---

## Appendix: Items Added (Not in Original Template)

These items are specific to LEAPS Trader and were NOT in the original template:

1. **Signal Engine pipeline tests** — 5 strategies × 2 timeframes
2. **Strategy Selector confidence scoring** — HIGH/MEDIUM/LOW thresholds
3. **AI Validation flow** — Claude confidence gating (75/40 thresholds)
4. **Backtrader strategy param inheritance** — Subclass params must include all base params
5. **Backtrader concurrency semaphore** — Max 3 concurrent, 5-min timeout
6. **Bot execution modes** — signal_only vs semi_auto vs full_auto routing
7. **Trailing stop edge cases** — Missing entry_price, high_water initialization
8. **Roll alert deduplication** — [ROLL_ALERT_SENT] tag prevents repeated sends
9. **consecutive_errors reset** — Resets on success, not just on manual clear
10. **EOD close LEAPS skip** — Options excluded from auto-close
11. **max_drawdown_pct percentage fix** — Stores %, not dollar amount
12. **Batch delete Promise.all** — Signal queue bulk operations
13. **FMP cache falsy check** — `cached is not None` vs truthy
14. **Scheduled scan automation** — CronTrigger job validation
15. **Scan processing ORM mutation** — dict copy before mutation
16. **DECIMAL(0) handling** — Score of 0 is valid, not None
17. **Exponential backoff polling** — Store polling with setTimeout doubling
18. **Paper vs Live mode toggle** — Mode persistence and enforcement
19. **Telegram notification delivery** — Trade alerts, scan summaries
20. **Session cleanup on shutdown** — 5+ aiohttp sessions closed
