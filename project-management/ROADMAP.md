# LEAPS Trader - Strategic Roadmap & Feature Ideas

## Current State Assessment

The project has solid foundations:
- 4-stage screening funnel (Fundamentals → Technical → Options → Scoring)
- Yahoo Finance + Finviz integration with rate limiting & caching
- React frontend with adjustable criteria
- TastyTrade integration for enhanced Greeks

## Key Gaps vs. Competitors (TrendSpider, TastyTrade, Thinkorswim)

| Feature | Competitors | Current State |
|---------|-------------|---------------|
| Automated Chart Analysis | Auto trendlines, pattern recognition | Manual indicators only |
| Dynamic Alerts | Alerts tied to moving trendlines | Webhook alerts (basic) |
| Backtesting | 50+ years historical testing | Not implemented |
| Visual Strategy Builder | No-code drag-and-drop | JSON criteria only |
| Live Streaming | Real-time price updates | SSE endpoint (implemented) |
| Options Visualizations | Greeks curves, P/L diagrams | ✅ P/L Chart, Return Calculator |
| Multi-Timeframe Analysis | Simultaneous 5m/1h/1d views | Single timeframe |
| Interactive Charts | TradingView-style charts | ✅ TradingView integration |
| Strategy Recommendations | AI-powered suggestions | ✅ Delta/DTE optimization |
| Position Sizing | Risk-based sizing | ✅ Kelly Criterion |
| Market Hours Awareness | Auto-pause outside hours | ✅ Smart refresh |

---

## Strategic Differentiator

**Niche: "The free, open-source tool built specifically for finding LEAPS with 5x potential"**

Don't try to be TrendSpider. Be the BEST at LEAPS screening.

---

## High-Priority Features

### P0: LEAPS-Specific Value (Your Differentiator)

#### 1. 5x Return Calculator
Show exactly what stock price is needed for 5x option return at each strike.

```python
# Example implementation
def calculate_5x_price(current_price, strike, premium, target_multiplier=5.0):
    """Calculate stock price needed for 5x return on LEAPS call"""
    target_profit = premium * target_multiplier
    required_stock_price = strike + premium + target_profit
    percent_move_needed = ((required_stock_price - current_price) / current_price) * 100
    return {
        "required_stock_price": required_stock_price,
        "percent_move_needed": percent_move_needed,
        "break_even": strike + premium
    }
```

#### 2. Strike Selection Wizard
Given target return, suggest optimal strike + expiration.

```python
# Criteria for optimal LEAPS strike
- Delta: 0.60-0.80 (deep ITM for leverage without excessive risk)
- Premium: <15% of stock price (reasonable cost)
- Open Interest: >100 (liquidity)
- DTE: Sweet spot 400-500 days (time value decay slower)
```

#### 3. Time Decay Visualizer
LEAPS decay slower initially - show this visually.

```python
# Theta decay is non-linear
# LEAPS at 400 DTE lose ~$0.01/day
# Same option at 30 DTE loses ~$0.10/day
# Visualize this curve for user education
```

#### 4. IV Crush Predictor
Flag upcoming earnings/events that could affect IV.

```python
# Integrate earnings calendar
# Alert: "NVDA earnings in 45 days - IV likely to spike then crush"
# Suggest: "Consider entering after earnings if IV drops"
```

---

### P0: Options P/L Visualization

Add visual profit/loss diagrams like TastyTrade's curve analysis.

**Frontend Component:**
```jsx
// frontend/src/components/charts/PLDiagram.jsx
// Show P/L at expiration across price range
// X-axis: Stock price at expiration
// Y-axis: Profit/Loss
// Mark: Break-even, max profit zone, current price
```

**Libraries to consider:**
- Recharts (already React-friendly)
- Lightweight Charts by TradingView (free)

---

### P1: Basic Backtesting Engine (Critical for Credibility)

Users can't trust a screener without historical validation.

**Implementation:**
```python
# backend/app/services/strategy/backtest_engine.py

class BacktestEngine:
    def run_backtest(self, strategy_criteria, start_date, end_date, entry_frequency="weekly"):
        """
        1. For each entry date, run screening with criteria
        2. "Buy" LEAPS on stocks that pass
        3. Track what happened to those LEAPS
        4. Calculate: win rate, avg return, max drawdown, Sharpe
        """

    def calculate_metrics(self, trades):
        return {
            "total_trades": len(trades),
            "win_rate": wins / total,
            "avg_return": mean(returns),
            "max_drawdown": calculate_max_drawdown(equity_curve),
            "sharpe_ratio": calculate_sharpe(returns),
            "best_trade": max(returns),
            "worst_trade": min(returns)
        }
```

**Data needed:**
- Historical options prices (harder to get - consider CBOE or OptionMetrics)
- Or simulate with Black-Scholes from historical stock prices

---

### P1: Dynamic Alerts

Alerts that evolve with the market (TrendSpider's killer feature).

**Alert Types:**
```python
# backend/app/services/alerts/alert_manager.py

ALERT_TYPES = {
    "price_cross_sma": "Stock crossed above/below moving average",
    "iv_rank_threshold": "IV Rank dropped below threshold",
    "leaps_available": "New LEAPS expiration now available",
    "screening_match": "Stock now passes all screening criteria",
    "breakout": "Stock broke above resistance level",
    "earnings_approaching": "Earnings within X days for watchlist stock"
}
```

**Delivery:**
- WebSocket for real-time in-app
- Telegram bot (you already have integration)
- Email (add SendGrid/SES)

---

### P2: Pattern Recognition

Detect chart patterns ideal for LEAPS entries.

```python
# backend/app/services/analysis/patterns.py

def detect_patterns(df):
    patterns = []

    # Cup and Handle (accumulation - good for LEAPS)
    if detect_cup_and_handle(df):
        patterns.append({"type": "cup_and_handle", "confidence": 0.8})

    # Bull Flag (continuation)
    if detect_bull_flag(df):
        patterns.append({"type": "bull_flag", "confidence": 0.75})

    # Double Bottom (reversal)
    if detect_double_bottom(df):
        patterns.append({"type": "double_bottom", "confidence": 0.7})

    return patterns

# Use TA-Lib for pattern detection or implement custom
```

---

### P2: Signal Language DSL (Pine Script Alternative)

Simple domain-specific language for screening conditions.

```
# Example LEAPS Signal Language
WHEN RSI crosses above 30
AND Price above SMA(200)
AND IV_Rank below 40
AND LEAPS_DTE between 365 and 500
THEN SIGNAL "LEAPS Entry"
```

**Parser implementation:**
```python
# backend/app/services/signals/parser.py

def parse_signal(signal_text):
    """Parse signal language into executable conditions"""
    conditions = []
    for line in signal_text.split('\n'):
        if line.startswith('WHEN') or line.startswith('AND'):
            conditions.append(parse_condition(line))
    return conditions
```

---

## Scanner Presets (Thinkorswim-Style)

Create LEAPS-specific scan templates:

```python
PRESETS = {
    "iv_crush_opportunity": {
        "description": "Low IV rank + earnings 60+ days away + uptrend",
        "criteria": {
            "iv_rank_max": 30,
            "days_to_earnings_min": 60,
            "price_above_sma200": True,
            "rsi_min": 40
        }
    },
    "cheap_leaps": {
        "description": "Very low IV + premium <10% of stock + high liquidity",
        "criteria": {
            "iv_rank_max": 20,
            "premium_percent_max": 10,
            "open_interest_min": 500
        }
    },
    "momentum_leaps": {
        "description": "Strong fundamentals + RSI recovering + MACD bullish",
        "criteria": {
            "revenue_growth_min": 25,
            "rsi_min": 35,
            "rsi_max": 60,
            "macd_bullish": True
        }
    },
    "turnaround_plays": {
        "description": "Oversold RSI + above SMA200 + high short interest",
        "criteria": {
            "rsi_max": 35,
            "price_above_sma200": True,
            "short_interest_min": 10
        }
    },
    "sector_rotation": {
        "description": "Strongest relative strength vs SPY + sector leading",
        "criteria": {
            "relative_strength_min": 1.1,
            "sector_rank_max": 3
        }
    }
}
```

---

## Architecture Additions

### New Backend Modules

```
backend/app/services/
├── strategy/
│   ├── backtest_engine.py      # Historical simulation
│   ├── position_sizer.py       # Kelly criterion, risk-based sizing
│   ├── pnl_calculator.py       # Options P/L at various prices
│   └── probability_engine.py   # Monte Carlo, Black-Scholes
├── alerts/
│   ├── alert_manager.py        # Dynamic alert conditions
│   ├── alert_triggers.py       # Check conditions against live data
│   └── delivery.py             # WebSocket, Telegram, Email
├── patterns/
│   ├── chart_patterns.py       # Cup/handle, flags, etc.
│   └── support_resistance.py   # Auto-detect levels
└── signals/
    ├── parser.py               # DSL parser
    └── executor.py             # Run parsed signals
```

### New Frontend Components

```
frontend/src/components/
├── charts/
│   ├── PLDiagram.jsx           # Risk/reward at expiration
│   ├── ProbabilityCone.jsx     # Price probability distribution
│   ├── GreeksGauges.jsx        # Visual delta/theta/vega
│   ├── IVRankChart.jsx         # Historical IV rank
│   ├── ThetaDecayCurve.jsx     # Time decay visualization
│   └── BacktestResults.jsx     # Strategy performance
├── wizards/
│   ├── StrikeSelector.jsx      # Optimal strike wizard
│   └── ReturnCalculator.jsx    # 5x return calculator
└── alerts/
    ├── AlertBuilder.jsx        # Create dynamic alerts
    └── AlertList.jsx           # Manage active alerts
```

---

## Implementation Priority

| Priority | Feature | Effort | Impact | Dependencies |
|----------|---------|--------|--------|--------------|
| **P0** | 5x Return Calculator | Low | High | None |
| **P0** | Strike Selection Wizard | Low | High | None |
| **P0** | Options P/L Chart | Medium | High | Recharts |
| **P1** | Basic Backtesting | High | Very High | Historical data source |
| **P1** | Dynamic Alerts | Medium | High | WebSocket, Redis pub/sub |
| **P1** | IV Crush Predictor | Low | Medium | Earnings calendar API |
| **P2** | Pattern Recognition | Medium | Medium | TA-Lib or custom |
| **P2** | Signal Language DSL | High | Medium | Parser implementation |
| **P2** | Scanner Presets | Low | Medium | None |
| **P3** | Multi-timeframe charts | Medium | Medium | Chart library |
| **P3** | Mobile app | Very High | Medium | React Native |

---

## Quick Wins (Can implement today)

1. **5x Return Calculator** - Pure math, add to StockDetail modal
2. **Scanner Presets** - Just predefined criteria objects
3. **IV Crush Warning** - Check earnings date vs DTE
4. **Greeks Gauges** - Visual representation of existing data
5. **Break-even Timeline** - Calculate and display in detail view

---

## Data Sources to Consider

| Data | Source | Cost |
|------|--------|------|
| Historical Options | CBOE, OptionMetrics | $$$$ |
| Historical Options | Polygon.io | $29/mo |
| Earnings Calendar | Yahoo Finance | Free |
| Short Interest | FINRA, Ortex | Free/Paid |
| Insider Trading | SEC EDGAR | Free |
| Reddit Sentiment | PushShift, Reddit API | Free |

---

## Success Metrics

Track these to know if the tool is working:

1. **Screening Accuracy** - % of screened stocks that actually 2x+ within LEAPS timeframe
2. **User Engagement** - Daily active screenings
3. **Alert Usefulness** - % of alerts acted upon
4. **Backtest Correlation** - Do backtested returns match real returns?

---

---

## ✅ Implemented Features

### Settings Management System (Hybrid Approach)

A comprehensive settings management system that allows configuration through a web UI while keeping sensitive credentials secure.

**Architecture:**
- **Sensitive secrets (API keys)** → Stored securely in `.env` file
- **Application settings** → Database with admin UI
- **API key status** → Database tracks which services are configured (not the actual keys)

**Backend Components:**

```
backend/app/
├── models/
│   └── settings.py           # AppSettings & ApiKeyStatus models
├── services/
│   └── settings_service.py   # Settings management service
└── api/endpoints/
    └── settings.py           # REST API endpoints
```

**Database Models:**
```python
# AppSettings - stores non-sensitive configuration
class AppSettings(Base):
    key = Column(String(100), unique=True)      # e.g., "screening.market_cap_min"
    value = Column(Text)                         # The setting value
    value_type = Column(String(20))             # string, integer, float, boolean, json
    category = Column(String(50))               # screening, rate_limit, cache, feature, ui
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)

# ApiKeyStatus - tracks which API keys are configured
class ApiKeyStatus(Base):
    service_name = Column(String(50), unique=True)  # yahoo, finviz, tastytrade, etc.
    is_configured = Column(Boolean)
    is_valid = Column(Boolean)
    last_validated = Column(DateTime)
    error_message = Column(Text)
```

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/settings` | Get all settings grouped by category |
| GET | `/api/v1/settings/summary` | Get settings with API key status |
| GET | `/api/v1/settings/category/{category}` | Get settings for a category |
| GET | `/api/v1/settings/key/{key}` | Get a single setting |
| PUT | `/api/v1/settings/key/{key}` | Update a single setting |
| PUT | `/api/v1/settings` | Batch update multiple settings |
| GET | `/api/v1/settings/api-keys` | Get API key status (not actual keys) |
| PUT | `/api/v1/settings/api-keys` | Update an API key |
| POST | `/api/v1/settings/api-keys/{service}/validate` | Validate an API key |
| POST | `/api/v1/settings/seed` | Reset to default settings |

**Frontend Components:**

```
frontend/src/
├── api/
│   └── settings.js           # API client for settings
├── pages/
│   └── Settings.jsx          # Settings page with tabs
└── App.jsx                   # Router with navigation
```

**Settings Page Tabs:**
1. **API Keys** - Configure and validate API keys for services
2. **Screening Defaults** - Market cap, growth, RSI, IV, DTE thresholds
3. **Performance** - Rate limits and cache TTL settings
4. **Features** - Feature toggles and UI preferences

**Supported Services:**
- Yahoo Finance (always configured - free tier)
- Finviz Elite (optional - enhanced screening)
- TastyTrade (optional - real-time Greeks & IV)
- Anthropic/Claude (optional - AI analysis)
- Telegram Bot (optional - alerts & commands)
- Alpha Vantage (optional - additional data)

**Security Features:**
- API keys are NEVER exposed through the settings API
- Only configuration status (is_configured, is_valid) is returned
- Actual keys remain in server-side `.env` file
- Validation endpoints test keys without exposing them

**Default Settings Categories:**
| Category | Examples |
|----------|----------|
| screening | market_cap_min, revenue_growth_min, rsi_min, iv_rank_max |
| rate_limit | default_rpm, yahoo_rpm, finviz_rpm |
| cache | prices_ttl, fundamentals_ttl, options_ttl |
| feature | enable_ai_analysis, enable_telegram_alerts |
| ui | default_theme, results_per_page |

---

### Command Center Dashboard

A comprehensive trading command center that consolidates market intelligence, news, prediction markets, and AI assistance into a single view.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ COMMAND CENTER                                   [Mode: LEAPS ▼] [🤖 AI]   │
├───────────────────────────────────────────────────────────────┬─────────────┤
│ 🤖 AI Morning Brief                                           │             │
│ Market optimistic. SPY +0.8%. Low VIX favors LEAPS buyers... │  Fear/Greed │
├────────────────┬──────────────────┬───────────────────────────┤   Gauge     │
│ Market Pulse   │ Sector Heatmap   │ Catalyst Feed             │             │
│ SPY +0.8%      │ Tech +1.4%       │ 🏛️ Fed speaks 2pm        ├─────────────┤
│ QQQ +1.2%      │ Energy -0.8%     │ 📊 CPI tomorrow           │ Polymarket  │
│ VIX 18.5       │ ...              │ 💼 AAPL earnings          │ Fed: 78%    │
└────────────────┴──────────────────┴───────────────────────────┴─────────────┘
```

**Backend Services:**
```
backend/app/services/command_center/
├── __init__.py
├── market_data.py      # Indices, VIX, Fear & Greed, Sectors
├── polymarket.py       # Prediction market odds & changes
├── news_feed.py        # Finnhub news, economic/earnings calendar
└── copilot.py          # AI morning brief, explanations, chat
```

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/command-center/dashboard` | Full dashboard data (single request) |
| GET | `/api/v1/command-center/market/summary` | Market indices, VIX, sectors |
| GET | `/api/v1/command-center/market/fear-greed` | CNN Fear & Greed Index |
| GET | `/api/v1/command-center/polymarket/dashboard` | Prediction market widget data |
| GET | `/api/v1/command-center/polymarket/changes` | Significant odds changes |
| GET | `/api/v1/command-center/news/catalyst-feed` | Combined news/events feed |
| GET | `/api/v1/command-center/copilot/morning-brief` | AI-generated morning brief |
| POST | `/api/v1/command-center/copilot/chat` | Interactive AI chat |
| POST | `/api/v1/command-center/copilot/explain` | Metric explanations |

**Frontend Components:**
```
frontend/src/components/command-center/
├── index.js
├── MarketPulse.jsx        # SPY, QQQ, DIA, IWM with changes
├── FearGreedGauge.jsx     # Visual gauge with history
├── PolymarketWidget.jsx   # Prediction odds + movers
├── CatalystFeed.jsx       # News, earnings, economic events
├── MorningBrief.jsx       # Collapsible AI summary
├── SectorHeatmap.jsx      # Visual sector performance
└── CopilotChat.jsx        # Interactive AI assistant
```

**Data Sources (All FREE):**
| Source | Data | API |
|--------|------|-----|
| Yahoo Finance | Indices, sectors | yfinance |
| CNN | Fear & Greed Index | Public endpoint |
| Polymarket | Prediction markets | REST API (no auth) |
| Finnhub | News, calendars | Free tier (60/min) |
| Alpha Vantage | Sentiment | Free tier (25/day) |
| Claude AI | Analysis, chat | ANTHROPIC_API_KEY |

**Trading Mode Selector:**
- LEAPS Mode: 365+ DTE, delta 0.60-0.80
- Swing Mode: 30-60 DTE, delta 0.40-0.55
- Custom Mode: User-defined parameters

**Key Features:**
1. **AI Morning Brief** - Daily market summary with actionable insights
2. **Fear & Greed Gauge** - Visual sentiment with historical comparison
3. **Polymarket Integration** - Prediction odds for Fed, elections, economy
4. **Catalyst Feed** - Unified news, earnings, and economic events
5. **Metric Explanations** - Click any metric to learn what it means
6. **Interactive AI Chat** - Ask questions without leaving the app
7. **Trading Mode Switcher** - Quick toggle between LEAPS/Swing strategies

---

### Flexible Trading Presets

Extended scanner presets to support both LEAPS and swing trading styles.

**Preset Categories:**
| Category | Description | DTE Range | Delta Range |
|----------|-------------|-----------|-------------|
| **Standard** | Risk levels (conservative, moderate, aggressive) | 365-730 | 0.55-0.80 |
| **LEAPS Strategy** | IV crush, growth, blue chip, turnaround | 365-730 | 0.55-0.80 |
| **Swing Trading** | Momentum, breakout, oversold, IV play | 30-60 | 0.40-0.55 |
| **Weekly Plays** | Quick momentum trades | 7-21 | 0.50-0.65 |
| **Earnings Plays** | Pre-earnings IV expansion | 14-45 | 0.45-0.55 |

**New Swing Presets:**
- `swing_momentum` - Ride the trend (4-8 weeks)
- `swing_breakout` - Technical breakout setups
- `swing_oversold` - Oversold bounce plays
- `swing_iv_play` - Low IV entry for leverage

**New Short-Term Presets:**
- `weekly_momentum` - Quick weekly profits
- `pre_earnings_iv` - IV expansion before earnings

---

---

## ✅ Recently Implemented (Jan-Feb 2026)

### Phase 3: Strategy Selector & Position Sizing

Complete strategy recommendation engine with intelligent Delta/DTE optimization.

**Backend Services:**
```
backend/app/services/strategy/
├── engine.py           # DeltaDTEOptimizer, strategy evaluation
├── position_sizing.py  # Kelly Criterion, risk-based sizing (0.5x safety)
```

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/strategy/recommend/{symbol}` | Get strategy recommendations |
| POST | `/api/v1/strategy/position-size` | Calculate position size |
| POST | `/api/v1/strategy/optimize-delta-dte` | Optimize delta/DTE for market regime |
| GET | `/api/v1/strategy/market-regime` | Get current market regime |

**Frontend Components:**
- `StrategySelector.jsx` - Full strategy recommendation UI
- `PositionSizer.jsx` - Position size calculator
- `RiskRewardChart.jsx` - Visual risk/reward display

---

### TradingView Charts Integration

Interactive TradingView charts embedded in stock detail view.

**Implementation:**
- `StockChart.jsx` - Full interactive chart with SMA, RSI indicators
- `MiniChart` - Quick overview chart
- Exchange mapping (NYSE, NASDAQ, AMEX) for correct symbol prefixes

---

### Smart Market Hours Auto-Refresh

Intelligent refresh that pauses when market is closed.

**Implementation:**
- `marketHours.js` - Market status utilities (holidays 2024-2026, early close days)
- `MarketRegimeBanner.jsx` - Smart 5-minute refresh during market hours only
- Market status indicator showing open/closed state

---

### Enhanced Stock Detail Modal

Tabbed interface for comprehensive stock analysis.

**Tabs:**
1. **Overview** - Composite scores, key metrics, returns, criteria checklist
2. **Chart** - TradingView interactive chart
3. **Strategy** - Strategy recommendations and position sizing
4. **Sentiment** - News, analyst ratings, insider trading
5. **Options** - LEAPS details, IV analysis, Return Calculator, P/L Chart

---

### Results Table Enhancements

- **IV Rank Badge** - Visual indicator (Low/Normal/High) with color coding
- **Strategy Badge** - Quick strategy suggestion (LEAPS/Spread/Long Call)
- **Exchange field** - Stored in screening results for chart integration

---

### Price Range Filter

Exclude expensive stocks (e.g., GOOGL at $1600+) from screening results.

**Implementation:**
- Backend: `price_min`/`price_max` in ScreeningCriteria, mandatory `price_ok` check
- Frontend: Price range sliders in CriteriaForm
- API: price_min/price_max in payload transformation

**Preset Values:**
| Preset | Price Min | Price Max |
|--------|-----------|-----------|
| Conservative | $10 | $300 |
| Moderate | $5 | $500 |
| Aggressive | $3 | $750 |

---

### Dynamic Alerts System

User-created, condition-based alerts with notification delivery.

**Backend Components:**
```
backend/app/
├── models/
│   └── user_alert.py        # UserAlert & AlertNotification models
├── services/alerts/
│   └── alert_service.py     # Alert condition checking & notifications
└── api/endpoints/
    └── user_alerts.py       # REST API endpoints
```

**Database Models:**
```python
# UserAlert - stores user-created alerts
class UserAlert(Base):
    name = Column(String(100))           # "NVDA Low IV Alert"
    symbol = Column(String(10))          # "NVDA"
    alert_type = Column(String(50))      # "iv_rank_below"
    threshold_value = Column(Float)      # 30.0
    notification_channels = Column(JSON) # ["telegram", "app"]
    frequency = Column(String(20))       # "once", "daily", "continuous"
    is_active = Column(Boolean)

# AlertNotification - triggered notification records
class AlertNotification(Base):
    alert_id = Column(Integer, ForeignKey)
    alert_name = Column(String)
    symbol = Column(String)
    message = Column(Text)
    channels_sent = Column(JSON)
    is_read = Column(Boolean)
```

**Alert Types:**
| Type | Description | Example |
|------|-------------|---------|
| `iv_rank_below` | IV Rank drops below threshold | IV < 30% |
| `iv_rank_above` | IV Rank rises above threshold | IV > 70% |
| `price_above` | Price crosses above level | Price > $150 |
| `price_below` | Price drops below level | Price < $100 |
| `rsi_oversold` | RSI indicates oversold | RSI < 30 |
| `rsi_overbought` | RSI indicates overbought | RSI > 70 |
| `price_cross_sma` | Price crosses above SMA | Price > SMA200 |
| `earnings_approaching` | Earnings within X days | 14 days |

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts/types` | Get available alert types |
| POST | `/api/v1/alerts` | Create new alert |
| GET | `/api/v1/alerts` | List user's alerts |
| PUT | `/api/v1/alerts/{id}` | Update alert |
| DELETE | `/api/v1/alerts/{id}` | Delete alert |
| POST | `/api/v1/alerts/{id}/toggle` | Enable/disable alert |
| POST | `/api/v1/alerts/{id}/check` | Manually check alert now |
| GET | `/api/v1/alerts/notifications` | List triggered notifications |
| POST | `/api/v1/alerts/notifications/{id}/read` | Mark notification as read |

**Frontend Components:**
```
frontend/src/
├── api/
│   └── userAlerts.js        # API client for alerts
└── components/alerts/
    ├── AlertBuilder.jsx     # Create new alerts
    └── UserAlertsList.jsx   # Manage existing alerts
```

**Notification Delivery:**
- **In-App**: All alerts recorded as notifications, viewable in UI
- **Telegram**: Sends formatted message via bot to configured users
- **Background Checking**: APScheduler runs every 5 minutes during market hours

**Key Features:**
1. Condition-based alerts tied to real-time market data
2. Multiple notification channels (app + Telegram)
3. Frequency options: once, daily, or continuous
4. Manual "Check Now" button for instant verification
5. Notification history with read/unread status
6. Automatic deactivation for one-time alerts

---

### Saved Scans (Persistent Results)

Preserve screening results across sessions with a dedicated page and automatic saving.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ SAVED SCANS                                            [Clear All]          │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Categories                   │ IV Crush Opportunity                         │
│                              │ Last updated: Feb 2, 10:30 AM                │
│ ★ IV Crush Opportunity (12)  │                                              │
│   Momentum LEAPS (8)         │ ┌────────┬───────┬───────┬───────┬───────┐  │
│   Blue Chip LEAPS (15)       │ │Symbol  │Score  │Price  │MktCap │IV Rank│  │
│                              │ ├────────┼───────┼───────┼───────┼───────┤  │
│ [Delete category]            │ │NVDA    │ 85.2  │$142.50│ 892B  │ 28.5% │  │
│                              │ │MSFT    │ 78.4  │$421.30│ 3.1T  │ 22.1% │  │
│                              │ │...     │       │       │       │       │  │
│                              │ └────────┴───────┴───────┴───────┴───────┘  │
└──────────────────────────────┴──────────────────────────────────────────────┘
```

**Backend Components:**
```
backend/app/
├── models/
│   └── saved_scan.py           # SavedScanResult & SavedScanMetadata models
└── api/endpoints/
    └── saved_scans.py          # REST API endpoints
```

**Database Models:**
```python
# SavedScanResult - stores individual stock results
class SavedScanResult(Base):
    scan_type = Column(String(100))      # "iv_crush", "momentum", etc.
    symbol = Column(String(20))
    company_name = Column(String(255))
    score = Column(Decimal)
    current_price = Column(Decimal)
    market_cap = Column(Decimal)
    iv_rank = Column(Decimal)
    stock_data = Column(JSON)            # Full stock data for flexibility
    scanned_at = Column(DateTime)

# SavedScanMetadata - tracks scan type info
class SavedScanMetadata(Base):
    scan_type = Column(String(100), unique=True)
    display_name = Column(String(255))
    stock_count = Column(Integer)
    last_run_at = Column(DateTime)
```

**API Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/saved-scans/categories` | List all saved scan categories |
| GET | `/api/v1/saved-scans/results/{scan_type}` | Get stocks for a scan type |
| POST | `/api/v1/saved-scans/save` | Save scan results (clears previous) |
| DELETE | `/api/v1/saved-scans/category/{scan_type}` | Delete entire category |
| DELETE | `/api/v1/saved-scans/stock/{scan_type}/{symbol}` | Delete single stock |
| DELETE | `/api/v1/saved-scans/all` | Clear all saved scans |
| GET | `/api/v1/saved-scans/check/{scan_type}` | Check if scan has results |
| GET | `/api/v1/saved-scans/check-all` | Get status of all scan types |

**Frontend Components:**
```
frontend/src/
├── api/
│   └── savedScans.js           # API client for saved scans
├── stores/
│   └── savedScansStore.js      # Zustand state management
└── pages/
    └── SavedScans.jsx          # Sidebar layout page
```

**Key Features:**
1. **Auto-Save**: Results automatically saved when preset scans complete
2. **Visual Indicators**: Green star badge on preset buttons showing saved count
3. **Sidebar Layout**: Categories on left, stocks on right (prevents bloating)
4. **Category Management**: Delete individual stocks, categories, or clear all
5. **Re-run Detection**: Running same scan replaces previous results
6. **Metadata Tracking**: Last run time, stock count per category

**Screener Integration:**
- Preset buttons show ★ badge with stock count if scan was previously run
- Auto-save triggers after streaming scan completes (preset-based only)
- Manual and custom scans are not auto-saved

---

## Summary

**Focus on being the BEST options trading tool - flexible for LEAPS AND swing trades.**

Priority order:
1. ✅ LEAPS-specific calculators (5x return, strike selection)
2. ✅ Options visualizations (P/L diagrams)
3. ✅ Settings management (API keys, configuration)
4. ✅ **Command Center Dashboard** (market intelligence hub)
5. ✅ **Flexible Trading Presets** (LEAPS + Swing support)
6. ✅ **Phase 3: Strategy Selector** (Delta/DTE optimization, position sizing)
7. ✅ **TradingView Charts** (interactive charts with exchange mapping)
8. ✅ **Smart Market Hours** (auto-refresh during trading hours only)
9. ✅ **Enhanced Stock Detail** (tabbed interface with all analysis)
10. ✅ **Price Range Filter** (exclude expensive stocks like GOOGL, AMZN)
11. ✅ **Dynamic Alerts** (condition-based alerts with Telegram notifications)
12. ✅ **Saved Scans** (persistent scan results with sidebar navigation)
13. Backtesting (builds credibility)
14. Pattern recognition & DSL (power user features)

The tool now supports your full trading workflow - from long-term LEAPS to quick swing trades.

---

## 🔄 Pending Features

### Backtesting Engine (High Priority)

Historical validation of screening strategies - critical for credibility.

**Needed:**
- Historical options data source (Polygon.io $29/mo or simulate with Black-Scholes)
- Backtest engine with win rate, Sharpe ratio, max drawdown metrics
- UI for running and viewing backtest results

### Pattern Recognition (Lower Priority)

Detect chart patterns ideal for LEAPS entries (Cup and Handle, Bull Flag, Double Bottom).
