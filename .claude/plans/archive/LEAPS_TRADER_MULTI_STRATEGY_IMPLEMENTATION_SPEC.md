# LEAPS Trader: Multi-Strategy Queue System - Implementation Spec

## Project Overview

**Application**: LEAPS Trader - Financial trading application with AI-powered options scanning

**Tech Stack**: 
- Backend: FastAPI (Python)
- Frontend: React + TypeScript
- Database: PostgreSQL + Prisma ORM
- AI: Claude API (Anthropic)
- Market Data: **Alpaca Markets API (Paid)**, **Financial Modeling Prep** (financialmodelingprep.com)
- Cache: Redis

**Data Source Advantages**:
- ✅ Real-time market data (Alpaca paid tier)
- ✅ Pre-calculated technical indicators (FMP)
- ✅ Reliable historical data with no rate limits
- ✅ Better spread/liquidity metrics
- ✅ Fundamental data for enhanced filtering (FMP)

**Current Location**: You have full codebase access via Claude Code MCP

---

## Objective

Transform the manual stock selection and timeframe assignment process into an intelligent, automated system that:

1. **Eliminates manual timeframe selection** (currently user picks 5m/15m/4h for each stock)
2. **Auto-queues HIGH confidence stocks** directly to signal processing
3. **Provides optional AI review** for MEDIUM confidence edge cases (batch only, not critical path)
4. **Updates timeframe strategies** by removing 4H, adding 1H and Daily

---

## Current Flow (What Needs Changing)

```
User runs preset scans
    ↓
Results saved to "Saved Scan" page (25 stocks with scores)
    ↓
User MANUALLY selects stocks via checkbox
    ↓
User MANUALLY chooses timeframe dropdown (5m, 15m, or 4h)
    ↓
Stocks queued to Signal Processing
    ↓
Results displayed
```

**Problem**: User decision fatigue, slow workflow, inconsistent strategy selection

---

## Target Flow (What We're Building)

```
User runs preset scans
    ↓
Results saved to "Saved Scan" page
    ↓
User clicks "Auto-Process Scan" button
    ↓
Rules-based engine analyzes all stocks (instant)
    ├─ HIGH confidence (8-12 stocks) → Auto-queue to Signal Processing ✅
    ├─ MEDIUM confidence (3-5 stocks) → Optional AI batch review 🤖
    └─ LOW confidence (10-15 stocks) → Skip ❌
    ↓
Signal Processing Queue ready with optimal timeframe strategies
```

**Key Principle**: AI is NOT in critical path. Rules handle 95% of decisions. AI only for uncertain edge cases when user opts in.

---

## Part 1: Timeframe Strategy Changes

### Remove 4H, Add 1H and Daily

**Current timeframes**: 5m, 15m, 4h
**New timeframes**: 5m, 15m, 1h, Daily

### New Strategy Definitions

| Timeframe | Name | Hold Duration | Use Case |
|-----------|------|---------------|----------|
| `5m` | Day Trade | 1-3 hours | Scalp/momentum plays, close before EOD |
| `15m` | Intraday Swing | 4-6 hours | Aggressive intraday, may hold near close |
| `1h` | Swing | Overnight to 3 days | Short-term swings, trend following |
| `Daily` | Swing | 3-10 days | Multi-day position trades |

### Implementation Tasks

1. **Update Database Schema**
   - Add `ONE_HOUR` and `DAILY` to Timeframe enum
   - Remove `FOUR_HOUR` references
   - Update existing records (migrate 4h → Daily or skip)

2. **Update All References**
   - Search codebase for "4h", "4H", "FOUR_HOUR"
   - Update dropdown options in frontend
   - Update signal processing logic
   - Update chart timeframe options

3. **Migration Script**
   - Create Prisma migration for enum change
   - Handle existing data gracefully

---

## Part 2: Database Schema Design

### New Tables/Models Needed

```prisma
// Example structure - adapt to your existing schema

enum Timeframe {
  FIVE_MIN     // "5m"
  FIFTEEN_MIN  // "15m"
  ONE_HOUR     // "1h"  ← NEW
  DAILY        // "Daily" ← NEW
  // Remove: FOUR_HOUR
}

enum ConfidenceLevel {
  HIGH    // Auto-queue
  MEDIUM  // Optional review
  LOW     // Skip
}

// NEW: Track strategy selection decisions
model StrategyDecision {
  id              String          @id @default(cuid())
  stockSymbol     String
  scanId          String
  timeframes      Timeframe[]     // Can have multiple
  confidence      ConfidenceLevel
  reasoning       String          // Why these timeframes?
  autoQueued      Boolean         @default(false)
  aiReviewed      Boolean         @default(false)
  aiReasoning     String?
  metrics         Json            // Store decision inputs
  createdAt       DateTime        @default(now())
  
  @@index([stockSymbol, scanId])
}

// NEW: Multi-strategy queue
model SignalQueue {
  id                   String    @id @default(cuid())
  stockSymbol          String
  timeframe            Timeframe
  strategyDecisionId   String
  status               String    @default("pending")
  queuedAt             DateTime  @default(now())
  processedAt          DateTime?
  
  @@index([status, queuedAt])
}

// Enhance existing Stock model
model Stock {
  // ... existing fields ...
  
  // NEW: Technical indicators for strategy selection
  spread        Float?
  sma20         Float?
  sma50         Float?
  rsi           Float?
  atr           Float?
  volumeRatio   Float?
  recentHigh    Float?
  recentLow     Float?
  
  strategyDecisions StrategyDecision[]
}
```

**Note**: Adapt to your existing schema structure. Key additions are StrategyDecision and SignalQueue tables.

---

## Part 3: Rules-Based Strategy Selection Algorithm

### Core Decision Logic (Conceptual)

```python
# Pseudocode - Claude Code will implement based on your architecture

class StrategySelector:
    """
    Rules-based strategy selection.
    NO AI in this class - pure deterministic logic.
    """
    
    def select_strategies(stock: StockData) -> StrategyDecision:
        """
        Main algorithm: Determine which timeframes to use.
        
        Returns: {
            timeframes: ["5m", "1h"],
            confidence: "HIGH",
            reasoning: "5m: High IV (45%), strong volume | 1h: Clean uptrend",
            auto_queue: True
        }
        """
        
        selected_timeframes = []
        reasons = []
        
        # Check 5m qualification
        if qualifies_for_5m(stock):
            selected_timeframes.append("5m")
            reasons.append(f"5m: High IV ({stock.ivRank}), volume {stock.volumeRatio}x")
        
        # Check 15m qualification
        if qualifies_for_15m(stock):
            selected_timeframes.append("15m")
            reasons.append(f"15m: Score {stock.score}, momentum {stock.pctChg}%")
        
        # Check 1h qualification (NEW)
        if qualifies_for_1h(stock):
            selected_timeframes.append("1h")
            reasons.append("1h: Clean trend, suitable for overnight")
        
        # Check Daily qualification (NEW)
        if qualifies_for_daily(stock):
            selected_timeframes.append("Daily")
            reasons.append(f"Daily: Strong score ({stock.score}), stable structure")
        
        # Special case: Exceptional scores get all strategies
        if stock.score > 70:
            return all_strategies_high_confidence(stock)
        
        # Calculate confidence based on signals
        confidence = calculate_confidence(stock, selected_timeframes)
        
        return StrategyDecision(
            timeframes=selected_timeframes,
            confidence=confidence,
            reasoning=" | ".join(reasons),
            auto_queue=(confidence == "HIGH")
        )
```

### Strategy Qualification Criteria

**Design these thresholds based on your data analysis:**

```python
# Example criteria - tune based on your backtesting

CRITERIA = {
    "5m": {
        "min_score": 55,
        "min_iv_rank": 0.30,      # Need volatility
        "min_volume": 1_000_000,
        "min_pct_change": 1.5,     # Must be moving today
        "max_spread": 0.20,        # Tight spreads only
        "min_market_cap": 1_000_000_000,  # 1B
    },
    "15m": {
        "min_score": 55,
        "min_iv_rank": 0.20,
        "min_volume": 500_000,
        "min_pct_change": 1.0,
    },
    "1h": {  # NEW
        "min_score": 58,
        "min_iv_rank": 0.15,
        "max_iv_rank": 0.60,       # Not too volatile for overnight
        "requires_clean_trend": True,
    },
    "Daily": {  # NEW
        "min_score": 60,
        "min_market_cap": 2_000_000_000,  # 2B
        "max_iv_rank": 0.70,       # Stable enough for multi-day
    }
}
```

### Confidence Calculation Logic

```python
def calculate_confidence(stock, selected_timeframes):
    """
    HIGH: Strong signals, auto-queue
    MEDIUM: Decent signals but edge cases detected, optional AI review
    LOW: Weak signals, skip
    """
    
    # No strategies selected = LOW
    if not selected_timeframes:
        return "LOW"
    
    # Exceptional score = HIGH
    if stock.score > 70:
        return "HIGH"
    
    # Multiple strategies + good score = HIGH
    if len(selected_timeframes) >= 2 and stock.score >= 65:
        return "HIGH"
    
    # Edge case detection (triggers MEDIUM confidence)
    edge_cases = []
    
    if stock.rsi > 70 and near_resistance(stock):
        edge_cases.append("Overbought at resistance")
    
    if stock.rsi < 30 and near_support(stock):
        edge_cases.append("Oversold at support")
    
    if stock.volumeRatio < 0.7 and stock.score > 60:
        edge_cases.append("Low volume despite good score")
    
    if stock.spread > 0.25:
        edge_cases.append("Wide spread")
    
    # Has edge cases = MEDIUM (needs review)
    if edge_cases:
        return "MEDIUM"
    
    # Default: HIGH if 2+ strategies, else MEDIUM
    return "HIGH" if len(selected_timeframes) >= 2 else "MEDIUM"
```

---

## Part 4: Batch Scan Processing Service

### Main Processing Flow

```python
# Conceptual service design

class ScanProcessor:
    """Process saved scans and auto-queue stocks."""
    
    async def process_saved_scan(scan_id: str):
        """
        Main entry point called when user clicks "Auto-Process Scan"
        
        Returns: {
            auto_queued: [8 stocks],      # HIGH confidence
            review_needed: [3 stocks],     # MEDIUM confidence  
            skipped: [14 stocks],          # LOW confidence
            stats: {...}
        }
        """
        
        # 1. Fetch all stocks from saved scan
        stocks = fetch_scan_results(scan_id)
        
        # 2. Calculate technical indicators if missing
        stocks = enrich_with_indicators(stocks)
        
        # 3. Run strategy selector on each stock
        results = {"auto_queued": [], "review_needed": [], "skipped": []}
        
        for stock in stocks:
            decision = StrategySelector.select_strategies(stock)
            
            # Save decision to database for audit
            save_decision(scan_id, stock, decision)
            
            # Route based on confidence
            if decision.confidence == "HIGH":
                results["auto_queued"].append(format_stock(stock, decision))
                auto_queue_to_signals(stock, decision)  # Queue immediately
                
            elif decision.confidence == "MEDIUM":
                results["review_needed"].append(format_stock(stock, decision))
                
            else:  # LOW
                results["skipped"].append(format_stock(stock, decision))
        
        return results
```

### Premium Data Integration: Alpaca + FMP

**You now have access to superior data sources. Use them strategically:**

#### Alpaca Markets API (Paid Tier)

**Use for:**
- Real-time intraday bars (5m, 15m, 1h) with no delays
- Accurate bid/ask spread data
- Reliable volume data
- Historical bars for backtesting

**API Endpoints:**
```python
# Example: Fetch intraday bars for 5m/15m/1h strategies
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

client = StockHistoricalDataClient(api_key, secret_key)

# Get 1-hour bars for last 60 days
request = StockBarsRequest(
    symbol_or_symbols="AAPL",
    timeframe=TimeFrame.Hour,  # Or TimeFrame.Minute for 5m/15m
    start=datetime.now() - timedelta(days=60)
)

bars = client.get_stock_bars(request)
```

**Advantages:**
- ✅ No rate limits on paid tier
- ✅ Real-time data for day trading strategies
- ✅ Reliable intraday data for 5m, 15m, 1h
- ✅ Better spread calculations (use actual bid/ask)

#### Financial Modeling Prep (FMP)

**Use for:**
- **Pre-calculated technical indicators** (no need to calculate yourself!)
- Fundamental metrics for enhanced filtering
- Daily historical data
- Company profiles and sector data

**API Endpoints:**

```python
import requests

FMP_API_KEY = "your_fmp_key"
BASE_URL = "https://financialmodelingprep.com/api/v3"

# 1. Get technical indicators (PRE-CALCULATED!)
def get_technical_indicators(symbol: str):
    """
    FMP provides RSI, SMA, EMA, ATR already calculated!
    """
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}"
    params = {
        "period": 14,  # For RSI
        "type": "rsi",
        "apikey": FMP_API_KEY
    }
    response = requests.get(url, params=params)
    return response.json()

# 2. Get SMA (20, 50, 200)
def get_sma(symbol: str, period: int):
    """Get Simple Moving Average."""
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}"
    params = {
        "period": period,
        "type": "sma",
        "apikey": FMP_API_KEY
    }
    response = requests.get(url, params=params)
    return response.json()

# 3. Get ATR (Average True Range)
def get_atr(symbol: str):
    """Get volatility measure."""
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}"
    params = {
        "period": 14,
        "type": "atr",
        "apikey": FMP_API_KEY
    }
    response = requests.get(url, params=params)
    return response.json()

# 4. Get real-time quote (for current price, spread)
def get_quote(symbol: str):
    """Get real-time quote data."""
    url = f"{BASE_URL}/quote/{symbol}"
    params = {"apikey": FMP_API_KEY}
    response = requests.get(url, params=params)
    data = response.json()[0]
    
    return {
        "price": data["price"],
        "change_pct": data["changesPercentage"],
        "volume": data["volume"],
        "avg_volume": data["avgVolume"],
        "market_cap": data["marketCap"],
        "day_high": data["dayHigh"],
        "day_low": data["dayLow"]
    }

# 5. Get historical prices (for custom calculations)
def get_historical_daily(symbol: str, days: int = 60):
    """Get daily historical data."""
    url = f"{BASE_URL}/historical-price-full/{symbol}"
    params = {
        "apikey": FMP_API_KEY,
        "from": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
        "to": datetime.now().strftime("%Y-%m-%d")
    }
    response = requests.get(url, params=params)
    return response.json()["historical"]
```

#### Recommended Data Strategy

**For Strategy Selection (Real-time Decision Making):**

```python
class EnhancedDataService:
    """
    Unified service combining Alpaca and FMP.
    Use the best source for each data type.
    """
    
    def __init__(self):
        self.alpaca_client = StockHistoricalDataClient(api_key, secret_key)
        self.fmp_key = FMP_API_KEY
        self.redis_client = redis.Redis()
    
    async def get_stock_metrics_for_strategy(self, symbol: str):
        """
        Get all metrics needed for strategy selection.
        Uses FMP for most data since it's pre-calculated.
        """
        
        cache_key = f"stock_metrics:{symbol}"
        cached = self.redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 1. Get real-time quote from FMP (fast, has everything)
        quote = get_quote(symbol)
        
        # 2. Get technical indicators from FMP (PRE-CALCULATED!)
        rsi_data = get_technical_indicators(symbol)
        sma20_data = get_sma(symbol, 20)
        sma50_data = get_sma(symbol, 50)
        atr_data = get_atr(symbol)
        
        # 3. Calculate derived metrics
        metrics = {
            # From quote
            "symbol": symbol,
            "price": quote["price"],
            "pctChg": quote["change_pct"],
            "volume": quote["volume"],
            "avgVolume": quote["avg_volume"],
            "mktCap": quote["market_cap"],
            
            # Technical indicators (pre-calculated by FMP!)
            "rsi": rsi_data[0]["rsi"] if rsi_data else None,
            "sma20": sma20_data[0]["sma"] if sma20_data else None,
            "sma50": sma50_data[0]["sma"] if sma50_data else None,
            "atr": atr_data[0]["atr"] if atr_data else None,
            
            # Derived metrics
            "recentHigh": quote["day_high"],
            "recentLow": quote["day_low"],
            "volumeRatio": quote["volume"] / quote["avg_volume"],
            "spread": self._calculate_spread_from_alpaca(symbol),  # Use Alpaca for real-time spread
            "ivRank": await self._get_iv_rank(symbol)  # Your existing IV calculation
        }
        
        # Cache for 5 minutes
        self.redis_client.setex(cache_key, 300, json.dumps(metrics))
        
        return metrics
    
    def _calculate_spread_from_alpaca(self, symbol: str) -> float:
        """
        Get real-time bid/ask spread from Alpaca.
        More accurate than estimating from quotes.
        """
        from alpaca.data.requests import StockLatestQuoteRequest
        
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quote = self.alpaca_client.get_stock_latest_quote(request)[symbol]
        
        bid = quote.bid_price
        ask = quote.ask_price
        mid = (bid + ask) / 2
        
        spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else 0
        return spread_pct
```

#### Benefits of This Approach

**Speed:**
- FMP pre-calculates indicators → No computation needed
- 1 API call to FMP gets most data
- Cache for 5 minutes → Minimal API usage

**Accuracy:**
- Alpaca spread data is real bid/ask (not estimated)
- FMP indicators are professionally calculated
- Real-time quotes ensure fresh data

**Reliability:**
- No rate limit issues (paid tiers)
- No calculation errors
- No stale Yahoo Finance data

**Cost Efficiency:**
```python
# Old way (Yahoo Finance):
# - Fetch 60 days of bars
# - Calculate RSI (pandas operations)
# - Calculate SMA 20, 50
# - Calculate ATR
# - Risk: Rate limits, slow, inconsistent
# Cost: Free but unreliable

# New way (FMP + Alpaca):
# - 1 FMP quote call (all metrics)
# - 3-4 FMP indicator calls (pre-calculated)
# - 1 Alpaca spread call (real-time)
# - Cache for 5 minutes
# Cost: ~5 API calls per stock, but reliable and fast
```

#### Implementation Note

Create a unified data service that abstracts the data sources:

```python
# backend/services/data_service.py

class MarketDataService:
    """
    Facade for all market data operations.
    Hides complexity of multiple data sources.
    """
    
    def __init__(self):
        self.fmp = FMPClient(api_key=FMP_KEY)
        self.alpaca = AlpacaClient(api_key=ALPACA_KEY, secret=ALPACA_SECRET)
        self.cache = RedisCache()
    
    async def get_stock_for_strategy_selection(self, symbol: str) -> EnhancedStockData:
        """
        ONE method to get everything needed for strategy selection.
        Handles caching, error handling, fallbacks.
        """
        pass
    
    async def get_intraday_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Get intraday bars from Alpaca for backtesting/validation.
        Use for 5m, 15m, 1h strategies.
        """
        pass
    
    async def get_daily_bars(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """
        Get daily bars from FMP for Daily strategy.
        """
        pass
```

**Cache Strategy:**
```python
# Cache keys and TTLs
CACHE_STRATEGY = {
    "stock_metrics": 300,      # 5 minutes (real-time quote)
    "technical_indicators": 3600,  # 1 hour (daily indicators)
    "intraday_bars": 60,       # 1 minute (for 5m/15m strategies)
    "daily_bars": 86400,       # 24 hours (historical data)
}
```

---

## Part 5: AI Integration (Edge Cases Only)

### When AI Gets Involved

**ONLY for MEDIUM confidence stocks AND ONLY when user clicks "AI Review" button**

### AI Review Service Design

```python
class AIReviewer:
    """
    Optional AI review for MEDIUM confidence stocks.
    Processes in BATCH to minimize API calls.
    """
    
    async def review_batch(stocks: List[StockData]) -> List[AIDecision]:
        """
        Review 3-10 uncertain stocks in ONE AI call.
        
        Input: [
            {symbol: "DOCN", concerns: ["Overbought", "At resistance"], ...},
            {symbol: "ZM", concerns: ["Earnings tomorrow"], ...},
        ]
        
        Output: [
            {symbol: "DOCN", decision: "QUEUE", timeframes: ["Daily"], reasoning: "..."},
            {symbol: "ZM", decision: "SKIP", timeframes: [], reasoning: "Earnings risk"},
        ]
        """
        
        # Build single prompt with all stocks
        prompt = build_batch_review_prompt(stocks)
        
        # Single Claude API call
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse JSON response
        return parse_ai_decisions(response)
```

### AI Prompt Structure

```python
def build_batch_review_prompt(stocks):
    """
    Example prompt structure for batch review.
    """
    
    stock_summaries = format_stocks_for_ai(stocks)
    market_context = get_current_market_conditions()
    
    return f"""You are a trading strategy analyst reviewing {len(stocks)} stocks with MEDIUM confidence signals.

Current market: {market_context}

Stocks to review:
{stock_summaries}

For each stock, decide:
- QUEUE (process it) with which timeframes
- SKIP (too risky)  
- WATCH (monitor but don't trade)

Respond in JSON format:
[
  {{"symbol": "DOCN", "decision": "QUEUE", "timeframes": ["5m", "Daily"], "reasoning": "Brief reason"}},
  ...
]

Focus on: risk/reward, edge case severity, market context alignment."""
```

**Cost management**: Batch 5-10 stocks per call instead of individual calls. Typical use: 1-3 AI calls per scan session.

---

## Part 6: API Endpoints Design

### Backend Routes

```python
# FastAPI router structure

@router.post("/api/scan-processing/process")
async def process_scan(scan_id: str):
    """
    Auto-process saved scan using rules-based selection.
    
    Response: {
        auto_queued: [...],     # Ready in signal queue
        review_needed: [...],   # Optional AI review
        skipped: [...],         # Not worth processing
        stats: {...}
    }
    """
    processor = ScanProcessor()
    return await processor.process_saved_scan(scan_id)


@router.post("/api/scan-processing/ai-review")
async def ai_review_batch(stocks: List[dict]):
    """
    OPTIONAL: AI review for MEDIUM confidence stocks.
    Only called when user clicks "AI Review" button.
    
    Response: {
        reviewed_stocks: [
            {symbol, ai_decision, ai_timeframes, ai_reasoning, ...}
        ]
    }
    """
    reviewer = AIReviewer()
    return await reviewer.review_batch(stocks)


@router.post("/api/scan-processing/queue-ai-approved")
async def queue_ai_approved(stocks: List[dict]):
    """
    Queue stocks that passed AI review to signal processing.
    """
    for stock in stocks:
        if stock['ai_decision'] == 'QUEUE':
            queue_to_signals(stock, stock['ai_timeframes'])
    
    return {"queued_count": len(stocks)}
```

---

## Part 7: Frontend Changes

### Updated Saved Scan Page Flow

```typescript
// Conceptual component structure

const SavedScanPage = () => {
  const [processedResults, setProcessedResults] = useState(null);
  const [aiReviewing, setAiReviewing] = useState(false);
  
  // Main action: Auto-process scan
  const handleAutoProcess = async () => {
    const result = await api.post('/scan-processing/process', {
      scan_id: currentScanId
    });
    
    setProcessedResults(result);
    
    // Show summary toast
    toast.success(
      `✅ ${result.auto_queued.length} queued | ` +
      `⚠️ ${result.review_needed.length} need review | ` +
      `❌ ${result.skipped.length} skipped`
    );
  };
  
  // Optional: AI review for MEDIUM confidence
  const handleAIReview = async () => {
    const aiResults = await api.post('/scan-processing/ai-review', {
      stocks: processedResults.review_needed
    });
    
    // Show AI recommendations modal
    showAIReviewModal(aiResults);
  };
  
  return (
    <div>
      {/* Main button */}
      <Button onClick={handleAutoProcess}>
        🚀 Auto-Process Scan ({scanResults.length} stocks)
      </Button>
      
      {/* Optional AI review button (only shows if MEDIUM confidence exists) */}
      {processedResults?.review_needed.length > 0 && (
        <Button onClick={handleAIReview} variant="secondary">
          🤖 AI Review ({processedResults.review_needed.length})
        </Button>
      )}
      
      {/* Results Display */}
      <ProcessingResults data={processedResults} />
    </div>
  );
};
```

### UI Components Needed

1. **Processing Summary Card**
   - Show counts: auto-queued, review needed, skipped
   - Visual stats with icons

2. **Auto-Queued Table**
   - Symbol, Price, Score, Timeframes (badges), Reasoning
   - Green styling, "Ready for signal processing" indicator

3. **Review Needed Table**
   - Symbol, Score, Concerns (in orange), Suggested timeframes
   - Yellow/warning styling

4. **AI Review Modal** (when user clicks AI review)
   - Show AI decisions for each stock
   - Allow user to approve/reject before queuing

5. **Skipped Table** (collapsible)
   - Symbol, Score, Why skipped
   - Gray/muted styling

---

## Part 8: Implementation Priorities

### Phase 1: Core Timeframe Changes (Day 1-2)
- [ ] Update database schema (Prisma migration)
- [ ] Add ONE_HOUR and DAILY enums
- [ ] Remove FOUR_HOUR references across codebase
- [ ] Update frontend dropdowns/selectors
- [ ] Test existing flows still work

### Phase 2: Rules-Based Selector (Day 3-5)
- [ ] Create StrategySelector service
- [ ] Implement qualification logic for each timeframe
- [ ] Implement confidence calculation
- [ ] Add technical indicator calculations
- [ ] Create ScanProcessor service
- [ ] Save decisions to StrategyDecision table

### Phase 3: Backend API (Day 6-7)
- [ ] Create /process endpoint
- [ ] Create /ai-review endpoint (stub for now)
- [ ] Create /queue-ai-approved endpoint
- [ ] Add proper error handling
- [ ] Write unit tests for selector logic

### Phase 4: Frontend Integration (Day 8-10)
- [ ] Update Saved Scan page UI
- [ ] Add "Auto-Process Scan" button
- [ ] Display processing results (3 categories)
- [ ] Add optional AI review button
- [ ] Create AI review modal
- [ ] Connect to new API endpoints

### Phase 5: AI Integration (Day 11-12)
- [ ] Implement AIReviewer service
- [ ] Build batch review prompt
- [ ] Parse AI JSON responses
- [ ] Handle AI errors gracefully
- [ ] Add AI review UI flow

### Phase 6: Testing & Refinement (Day 13-15)
- [ ] Test with real scan data
- [ ] Tune qualification thresholds
- [ ] Validate auto-queue accuracy
- [ ] Test AI review quality
- [ ] Performance optimization (caching, batch processing)
- [ ] Documentation

---

## Part 9: Key Technical Decisions for You (Claude Code)

### 1. Where to Calculate Technical Indicators?

**With FMP, you don't need to calculate - they're PRE-CALCULATED!**

**Options**:
- ~~A) During scan creation~~ (unnecessary)
- ~~B) Calculate on-demand~~ (unnecessary)
- **C) Fetch from FMP API (recommended)** ✅

**Implementation:**
```python
# Simply fetch from FMP - no calculation needed
metrics = {
    "rsi": fmp.get_rsi(symbol),      # Pre-calculated
    "sma20": fmp.get_sma(symbol, 20), # Pre-calculated
    "sma50": fmp.get_sma(symbol, 50), # Pre-calculated
    "atr": fmp.get_atr(symbol)        # Pre-calculated
}
```

**Benefits:**
- ✅ No pandas calculations
- ✅ No historical data fetching (for indicators)
- ✅ Faster (1 API call vs computing)
- ✅ Professionally calculated
- ✅ Cache for 1 hour (indicators don't change often)

### 2. How to Handle Existing 4H Data?

**Options**:
- A) Migrate all 4h → Daily
- B) Keep 4h historical, new scans use Daily
- C) Delete 4h records

**Recommendation**: Option B - Preserve history, migrate going forward

### 3. AI Timeout Handling?

If AI review takes >30 seconds or fails:
- Return original MEDIUM confidence stocks unchanged
- Log error, allow user to retry
- Don't block the workflow

### 4. Multi-Strategy Queue Structure?

Each stock can have multiple timeframes. How to queue?

**Option A**: One queue entry per stock-timeframe pair
```
Queue: [
  {symbol: "DOCN", timeframe: "5m", ...},
  {symbol: "DOCN", timeframe: "Daily", ...}
]
```

**Option B**: One entry with array of timeframes
```
Queue: [
  {symbol: "DOCN", timeframes: ["5m", "Daily"], ...}
]
```

**Recommendation**: Option A - Easier to process individually

---

## Part 10: Testing Approach

### Unit Tests Needed

```python
# Test strategy selection logic

def test_5m_qualification():
    stock = create_test_stock(
        score=65, ivRank=0.40, volume=2_000_000, pctChg=2.5
    )
    decision = selector.select_strategies(stock)
    assert "5m" in decision.timeframes

def test_confidence_calculation_high():
    stock = create_test_stock(score=72)
    decision = selector.select_strategies(stock)
    assert decision.confidence == "HIGH"
    assert decision.auto_queue == True

def test_edge_case_detection():
    stock = create_test_stock(
        score=65, rsi=75, nearResistance=True
    )
    decision = selector.select_strategies(stock)
    assert decision.confidence == "MEDIUM"
```

### Integration Tests

```python
def test_full_scan_processing():
    """Test complete flow from scan to queue."""
    scan_id = create_test_scan(25_stocks)
    
    result = await processor.process_saved_scan(scan_id)
    
    assert len(result['auto_queued']) > 0
    assert all_queued_stocks_in_signal_queue()
    assert all_decisions_saved_to_db()
```

### Manual Testing Checklist

- [ ] Process scan with 25 stocks, verify counts match expectations
- [ ] Verify HIGH confidence stocks are auto-queued
- [ ] Verify MEDIUM confidence stocks are flagged correctly
- [ ] Test AI review with 3-5 stocks
- [ ] Verify AI decisions can be queued
- [ ] Check all 4 timeframes work in signal processing
- [ ] Verify database migrations completed successfully

### Backtesting with Alpaca (Bonus)

**Your paid Alpaca subscription enables real backtesting:**

```python
# Use historical data to validate strategy selection accuracy

class StrategyBacktester:
    """Validate strategy selection against historical performance."""
    
    async def backtest_strategy_selection(self, lookback_days: int = 90):
        """
        Test if HIGH confidence selections actually perform well.
        """
        
        # 1. Get historical scans
        historical_scans = get_scans_from_last_N_days(lookback_days)
        
        results = {
            "high_confidence_trades": [],
            "medium_confidence_trades": [],
            "low_confidence_trades": []
        }
        
        for scan in historical_scans:
            for stock in scan.stocks:
                # Run strategy selector on historical data
                decision = selector.select_strategies(stock)
                
                # Get actual performance from Alpaca
                actual_performance = await self._get_actual_performance(
                    symbol=stock.symbol,
                    timeframes=decision.timeframes,
                    entry_date=scan.date
                )
                
                results[f"{decision.confidence.lower()}_trades"].append({
                    "symbol": stock.symbol,
                    "decision": decision,
                    "actual_performance": actual_performance
                })
        
        # Analyze: Did HIGH confidence actually outperform?
        return self._analyze_results(results)
    
    async def _get_actual_performance(self, symbol, timeframes, entry_date):
        """
        Use Alpaca to get what actually happened after the signal.
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        
        results = {}
        
        for tf in timeframes:
            # Fetch bars after entry date
            if tf == "5m":
                # Check 3-hour forward performance
                bars = alpaca_client.get_stock_bars(
                    StockBarsRequest(
                        symbol_or_symbols=symbol,
                        timeframe=TimeFrame.Minute,
                        start=entry_date,
                        end=entry_date + timedelta(hours=3)
                    )
                )
                results[tf] = calculate_return(bars)
            
            elif tf == "Daily":
                # Check 10-day forward performance
                bars = alpaca_client.get_stock_bars(
                    StockBarsRequest(
                        symbol_or_symbols=symbol,
                        timeframe=TimeFrame.Day,
                        start=entry_date,
                        end=entry_date + timedelta(days=10)
                    )
                )
                results[tf] = calculate_return(bars)
        
        return results
```

**Use backtesting to tune thresholds:**
- If HIGH confidence win rate < 60%, raise score thresholds
- If MEDIUM confidence outperforms, loosen edge case rules
- Continuously improve qualification criteria based on real data

---

## Part 11: API Cost Optimization

### Efficient Use of Premium Data Sources

**Even with paid subscriptions, optimize API usage:**

#### Request Batching Strategy

```python
# Bad: Individual requests per stock
for stock in stocks:
    rsi = fmp_client.get_rsi(stock.symbol)
    sma20 = fmp_client.get_sma(stock.symbol, 20)
    sma50 = fmp_client.get_sma(stock.symbol, 50)
    # 3 API calls per stock × 25 stocks = 75 calls

# Good: Batch requests
symbols = [s.symbol for s in stocks]
quotes = fmp_client.get_bulk_quotes(symbols)        # 1 call for all
rsi_data = fmp_client.get_bulk_rsi(symbols)         # 1 call for all
sma_data = fmp_client.get_bulk_sma(symbols, [20, 50])  # 1 call for all
# Total: 3 calls for 25 stocks
```

#### Smart Caching Hierarchy

```python
CACHE_STRATEGY = {
    # Data that changes frequently
    "real_time_quotes": {
        "ttl": 60,           # 1 minute
        "source": "FMP",
        "endpoint": "/quote/{symbol}"
    },
    
    # Data that changes slowly
    "technical_indicators": {
        "ttl": 3600,         # 1 hour
        "source": "FMP",
        "endpoint": "/technical_indicator/daily/{symbol}"
    },
    
    # Intraday bars for active strategies
    "intraday_bars_5m": {
        "ttl": 60,           # 1 minute
        "source": "Alpaca",
        "refresh_on_market_hours_only": True
    },
    
    # Historical data (rarely changes)
    "daily_bars_60d": {
        "ttl": 86400,        # 24 hours
        "source": "FMP",
    },
    
    # Market state (sector performance, etc.)
    "market_context": {
        "ttl": 300,          # 5 minutes
        "source": "FMP",
    }
}
```

#### API Call Budget

**Set daily limits to avoid overages:**

```python
# Example usage monitoring
class APIUsageTracker:
    """Track API usage to stay within reasonable limits."""
    
    def __init__(self):
        self.redis = redis.Redis()
        self.daily_limits = {
            "fmp": 10000,      # Adjust based on your plan
            "alpaca": 200      # Data API calls per minute
        }
    
    def track_call(self, provider: str, endpoint: str):
        """Increment usage counter."""
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"api_usage:{provider}:{today}"
        
        current = self.redis.incr(key)
        self.redis.expire(key, 86400)  # Reset daily
        
        # Alert if approaching limit
        if current > self.daily_limits[provider] * 0.8:
            log.warning(f"{provider} usage at {current} calls today")
        
        return current
    
    def can_make_call(self, provider: str) -> bool:
        """Check if within limits."""
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"api_usage:{provider}:{today}"
        current = int(self.redis.get(key) or 0)
        
        return current < self.daily_limits[provider]
```

#### Fallback Strategy

```python
class ResilientDataService:
    """Handle API failures gracefully."""
    
    async def get_stock_metrics(self, symbol: str):
        """Try FMP first, fallback to cache or Alpaca."""
        
        try:
            # Primary: FMP (most comprehensive)
            return await self._get_from_fmp(symbol)
        
        except RateLimitError:
            log.warning("FMP rate limit hit, using cache")
            cached = self._get_from_cache(symbol)
            if cached:
                return cached
            
            # Fallback: Get from Alpaca (less complete but works)
            return await self._get_from_alpaca(symbol)
        
        except Exception as e:
            log.error(f"Data fetch failed for {symbol}: {e}")
            # Last resort: Use cached data even if stale
            return self._get_stale_cache(symbol, max_age=3600)
```

#### Cost-Effective Scan Processing

```python
# Optimize the scan processing flow

async def process_saved_scan_efficiently(scan_id: str):
    """
    Process 25 stocks with minimal API calls.
    """
    
    # 1. Get all stock symbols
    stocks = fetch_scan_results(scan_id)
    symbols = [s.symbol for s in stocks]
    
    # 2. Batch fetch data (3-5 API calls total instead of 75+)
    quotes = await fmp.bulk_quotes(symbols)              # 1 call
    indicators = await fmp.bulk_indicators(symbols)       # 1 call
    spreads = await alpaca.bulk_latest_quotes(symbols)   # 1 call
    
    # 3. Build EnhancedStockData objects from cached responses
    enhanced_stocks = []
    for stock in stocks:
        enhanced = EnhancedStockData(
            **stock.dict(),
            rsi=indicators[stock.symbol]["rsi"],
            sma20=indicators[stock.symbol]["sma20"],
            # ... other pre-fetched data
        )
        enhanced_stocks.append(enhanced)
    
    # 4. Run strategy selector (no additional API calls needed)
    results = {"auto_queued": [], "review_needed": [], "skipped": []}
    for stock in enhanced_stocks:
        decision = selector.select_strategies(stock)
        # ... route based on confidence
    
    return results
```

#### Monitoring Dashboard

**Track usage in real-time:**

```python
# Add to admin panel
{
    "fmp_usage_today": 1247,
    "fmp_limit": 10000,
    "alpaca_usage_minute": 12,
    "alpaca_limit": 200,
    "cache_hit_rate": 0.73,  # 73% from cache
    "estimated_daily_cost": "$2.45"
}
```

---

## Part 12: Error Handling & Edge Cases

### Handle These Scenarios

1. **Missing technical indicators** (new stock, no history)
   - Default to MEDIUM confidence
   - Calculate on-the-fly if possible
   - Log for future background job

2. **All stocks are LOW confidence**
   - Show helpful message: "No strong setups detected in this scan"
   - Suggest adjusting scan criteria

3. **AI review fails**
   - Return stocks unchanged with MEDIUM confidence
   - Allow user to manually queue
   - Log error for monitoring

4. **Database connection issues**
   - Graceful degradation
   - Return cached results if available
   - Clear error messages to user

5. **Race conditions** (user processes same scan twice)
   - Check if already processed
   - Prevent duplicate queue entries
   - Show existing results

---

## Part 13: Configuration & Tuning

### Make These Thresholds Configurable

Store in environment variables or admin panel for easy tuning:

```python
# Example config structure

STRATEGY_CONFIG = {
    "5m": {
        "min_score": env.get("FIVE_MIN_MIN_SCORE", 55),
        "min_iv_rank": env.get("FIVE_MIN_MIN_IV", 0.30),
        # ... other thresholds
    },
    # ... other strategies
}

CONFIDENCE_THRESHOLDS = {
    "high_score": env.get("HIGH_SCORE_THRESHOLD", 70),
    "multi_strategy_score": env.get("MULTI_STRAT_SCORE", 65),
}
```

This allows tuning without code changes as you gather performance data.

---

## Success Criteria

### You'll know it's working when:

1. ✅ User clicks "Auto-Process", sees instant results (no manual selection)
2. ✅ 60-80% of stocks are HIGH confidence and auto-queued
3. ✅ 10-20% are MEDIUM confidence, available for AI review
4. ✅ AI review (when used) completes in <10 seconds for 5 stocks
5. ✅ Signal processing queue has stocks with correct timeframes
6. ✅ No more 4H references in codebase
7. ✅ All 4 new timeframes (5m, 15m, 1h, Daily) work in signal processing

### Performance Targets

- Scan processing: <2 seconds for 25 stocks (rules-based)
- AI review: <10 seconds for 5 stocks (batch)
- Database queries: <500ms per operation
- Frontend load: <1 second to show results

---

## Questions to Resolve During Implementation

1. **Where is the current "Saved Scan" page code?** (You'll find this)
2. **How are stocks currently stored?** (Check existing Stock model)
3. **Where are Alpaca/FMP API credentials stored?** (Check environment variables)
4. **Is there existing FMP/Alpaca integration?** (Search for existing API clients)
5. **How is signal processing currently triggered?** (Find queue mechanism)
6. **Where is Claude API client initialized?** (Find anthropic client)
7. **What's the current caching strategy?** (Check Redis usage patterns)

---

## FMP API Quick Reference

### Most Valuable Endpoints for Strategy Selection

```python
# Financial Modeling Prep base URL
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# 1. Real-time Quote (Get current price, volume, market cap)
GET {FMP_BASE}/quote/{symbol}?apikey={key}
Response: [{"symbol": "AAPL", "price": 150.25, "changesPercentage": 1.5, ...}]

# 2. Batch Quotes (Get multiple stocks at once)
GET {FMP_BASE}/quote/{symbol1},{symbol2},{symbol3}?apikey={key}
Response: [{...}, {...}, {...}]

# 3. Technical Indicators - RSI
GET {FMP_BASE}/technical_indicator/daily/{symbol}?period=14&type=rsi&apikey={key}
Response: [{"date": "2024-01-15", "rsi": 65.4}, ...]

# 4. Technical Indicators - SMA
GET {FMP_BASE}/technical_indicator/daily/{symbol}?period=20&type=sma&apikey={key}
Response: [{"date": "2024-01-15", "sma": 148.5}, ...]

# 5. Technical Indicators - EMA
GET {FMP_BASE}/technical_indicator/daily/{symbol}?period=20&type=ema&apikey={key}
Response: [{"date": "2024-01-15", "ema": 149.2}, ...]

# 6. Technical Indicators - ATR (Average True Range)
GET {FMP_BASE}/technical_indicator/daily/{symbol}?period=14&type=atr&apikey={key}
Response: [{"date": "2024-01-15", "atr": 2.35}, ...]

# 7. Historical Daily Prices (For custom calculations if needed)
GET {FMP_BASE}/historical-price-full/{symbol}?from={start_date}&to={end_date}&apikey={key}
Response: {"symbol": "AAPL", "historical": [{"date": "2024-01-15", "open": 148, ...}]}

# 8. Company Profile (For sector, industry, market cap)
GET {FMP_BASE}/profile/{symbol}?apikey={key}
Response: [{"symbol": "AAPL", "companyName": "Apple Inc", "sector": "Technology", ...}]

# 9. Key Metrics (For fundamental filters if needed)
GET {FMP_BASE}/key-metrics/{symbol}?period=quarter&apikey={key}
Response: [{"peRatio": 28.5, "debtToEquity": 1.2, ...}]

# 10. Sector Performance (For market context)
GET {FMP_BASE}/sector-performance?apikey={key}
Response: [{"sector": "Technology", "changesPercentage": "2.5%"}, ...]
```

### Alpaca API Quick Reference

```python
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

# Initialize client (paid tier)
client = StockHistoricalDataClient(api_key, secret_key)

# 1. Get latest quote (real-time bid/ask)
request = StockLatestQuoteRequest(symbol_or_symbols="AAPL")
quote = client.get_stock_latest_quote(request)
# Access: quote['AAPL'].ask_price, quote['AAPL'].bid_price

# 2. Get intraday bars (5m, 15m, 1h)
request = StockBarsRequest(
    symbol_or_symbols="AAPL",
    timeframe=TimeFrame.Minute,  # or TimeFrame.Hour
    start=datetime(2024, 1, 1),
    end=datetime.now()
)
bars = client.get_stock_bars(request)

# 3. Get daily bars
request = StockBarsRequest(
    symbol_or_symbols="AAPL",
    timeframe=TimeFrame.Day,
    start=datetime.now() - timedelta(days=60),
    end=datetime.now()
)
bars = client.get_stock_bars(request)

# 4. Batch request (multiple symbols)
request = StockBarsRequest(
    symbol_or_symbols=["AAPL", "GOOGL", "MSFT"],
    timeframe=TimeFrame.Hour,
    start=datetime.now() - timedelta(days=5)
)
bars = client.get_stock_bars(request)
```

### Recommended Data Flow

```python
# Efficient data gathering for 25 stocks

async def gather_all_data_for_scan(symbols: List[str]):
    """
    Get all data needed with minimal API calls.
    """
    
    # Step 1: FMP bulk quote (1 API call)
    quotes_url = f"{FMP_BASE}/quote/{','.join(symbols)}"
    quotes = await fetch_json(quotes_url)
    
    # Step 2: Get indicators for all symbols (parallel)
    tasks = []
    for symbol in symbols:
        tasks.append(get_indicators_for_symbol(symbol))
    
    indicators = await asyncio.gather(*tasks)  # ~4 calls per symbol
    
    # Step 3: Alpaca batch quotes (1 API call)
    alpaca_request = StockLatestQuoteRequest(symbol_or_symbols=symbols)
    spreads = alpaca_client.get_stock_latest_quote(alpaca_request)
    
    # Total: ~1 + (4 × 25) + 1 = ~102 API calls for 25 stocks
    # With caching: Reduce to <20 calls for repeat scans
    
    return combine_data(quotes, indicators, spreads)
```

---

## Final Notes

**Architecture Philosophy**:
- **Rules-first**: 95% of decisions via fast, deterministic rules
- **AI-optional**: Only for genuine edge cases, never blocking
- **Transparent**: Always show reasoning for decisions
- **Auditable**: Log all decisions to database
- **Performant**: Batch operations, cache aggressively

**Don't Overthink**:
- Start with simple threshold rules, refine later
- AI prompt doesn't need to be perfect v1
- Frontend can be basic, polish later
- Focus on working end-to-end flow first

**You Have Full Context**:
- Explore codebase structure
- Follow existing patterns
- Reuse services/utilities
- Ask if anything is unclear

---

## Premium Data Source Advantages Summary

### Why This Implementation is Better with Alpaca + FMP

**Speed Improvements:**
- ✅ FMP pre-calculates all technical indicators → No pandas operations
- ✅ Batch API calls → 3-5 calls instead of 75+ for 25 stocks
- ✅ Real-time data → No delays or stale Yahoo Finance data
- **Result**: Scan processing in <1 second vs 5-10 seconds

**Reliability Improvements:**
- ✅ No rate limit issues (paid tiers)
- ✅ Professional indicator calculations (no DIY errors)
- ✅ Accurate bid/ask spreads from Alpaca
- **Result**: Consistent, trustworthy data

**Feature Enhancements:**
- ✅ Real-time intraday bars for 5m/15m/1h strategies
- ✅ Backtesting with actual historical performance (Alpaca)
- ✅ Fundamental data for enhanced filtering (FMP)
- **Result**: More sophisticated strategy selection

**Cost Efficiency:**
```
Old approach (Yahoo Finance):
- Free but slow, unreliable
- Calculate everything yourself
- Rate limits, stale data
- No real-time capability

New approach (FMP + Alpaca):
- Paid but professional grade
- Pre-calculated indicators
- No rate limits
- Real-time capability
- Cost: ~$50-100/month total
- ROI: One good trade pays for months
```

**Data Quality Comparison:**

| Metric | Yahoo Finance | FMP + Alpaca |
|--------|--------------|---------------|
| Real-time data | ❌ Delayed 15min | ✅ Real-time |
| Technical indicators | ❌ Calculate yourself | ✅ Pre-calculated |
| Intraday bars | ⚠️ Limited | ✅ Full access |
| Bid/ask spread | ❌ Estimated | ✅ Actual |
| Rate limits | ❌ Frequent issues | ✅ No issues (paid) |
| Reliability | ⚠️ Sometimes down | ✅ Enterprise SLA |
| Historical depth | ⚠️ Limited | ✅ Years of data |
| Backtesting | ❌ Difficult | ✅ Built-in support |

**Implementation Impact:**

```python
# Before (Yahoo Finance)
def get_stock_metrics(symbol):
    # 1. Fetch 60 days of data (1 API call, slow)
    data = yfinance.download(symbol, period="60d")
    
    # 2. Calculate RSI (pandas operations)
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # 3. Calculate SMAs (more pandas)
    sma20 = data['Close'].rolling(20).mean()
    sma50 = data['Close'].rolling(50).mean()
    
    # 4. Calculate ATR (complex)
    # ... 20 lines of code
    
    # Total time: 2-5 seconds per stock
    # Risk: Rate limits, calculation errors, stale data

# After (FMP + Alpaca)
def get_stock_metrics(symbol):
    # 1. Fetch quote (1 API call, fast)
    quote = fmp.get_quote(symbol)
    
    # 2. Fetch pre-calculated indicators (1 API call)
    indicators = fmp.get_bulk_indicators(symbol, 
        types=["rsi", "sma20", "sma50", "atr"])
    
    # 3. Get real-time spread (1 API call)
    spread = alpaca.get_latest_quote(symbol).spread_pct
    
    # Total time: <500ms per stock
    # Benefits: Professional calculations, reliable, fast
```

---

## Implementation Checklist Summary

### Critical Path (Must Have)
- [ ] Remove 4H, add 1H and Daily timeframes
- [ ] Create StrategySelector with rules-based logic
- [ ] Create ScanProcessor for batch processing
- [ ] Add StrategyDecision and SignalQueue tables
- [ ] Create API endpoint: `/api/scan-processing/process`
- [ ] Update Saved Scan page with "Auto-Process" button
- [ ] Display 3-tier results (auto-queued, review, skipped)

### Optional Enhancements (Nice to Have)
- [ ] AI review service (batch processing)
- [ ] AI review UI flow
- [ ] Technical indicator caching in Redis
- [ ] Advanced error handling and retry logic
- [ ] Performance monitoring and logging

### Quality Assurance
- [ ] Unit tests for strategy selection
- [ ] Integration tests for full flow
- [ ] Manual testing with real scan data
- [ ] Performance benchmarking
- [ ] User acceptance testing

---

Good luck! 🚀