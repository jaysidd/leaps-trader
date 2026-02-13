# AI Trading Assistant - Phase 1 Implementation Plan

## Overview
Phase 1 establishes the foundation for AI-powered analysis: Claude API integration, market regime detection, and an AI Insights panel.

---

## Implementation Order

### Step 1: Add Claude API Configuration

**File: `backend/app/config.py`**
```python
# Add to Settings class:
ANTHROPIC_API_KEY: str = ""
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS: int = 1024
```

**File: `backend/.env`**
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

### Step 2: Create Claude Service Module

**Create: `backend/app/services/ai/`**
```
ai/
├── __init__.py
├── claude_service.py      # Main Claude integration
├── prompts.py             # Prompt templates
└── market_regime.py       # VIX/regime analysis
```

**File: `backend/app/services/ai/claude_service.py`**
```python
class ClaudeAnalysisService:
    """AI-powered stock analysis using Claude."""

    async def analyze_stock(stock_result: dict) -> dict:
        """Generate AI insights for a single stock."""

    async def analyze_batch(results: list) -> dict:
        """Summarize multiple screening results."""

    async def explain_opportunity(stock: dict, leaps: dict) -> str:
        """Explain why this is a 5x opportunity."""

    async def identify_risks(stock: dict) -> list:
        """Identify key risks to monitor."""

    async def get_strategy_recommendation(stock: dict, regime: dict) -> dict:
        """Recommend options strategy based on conditions."""
```

---

### Step 3: Create Prompt Templates

**File: `backend/app/services/ai/prompts.py`**
```python
STOCK_ANALYSIS_PROMPT = """
You are an expert options trader analyzing {symbol} for 5x LEAPS potential.

## Current Data
- Price: ${current_price}
- Sector: {sector}
- Market Cap: ${market_cap_formatted}

## Scores (0-100)
- Fundamental: {fundamental_score}
- Technical: {technical_score}
- Options: {options_score}
- Momentum: {momentum_score}
- Composite: {score}

## Technical Indicators
{technical_indicators}

## LEAPS Available
{leaps_summary}

## Task
Provide a concise analysis:
1. Bull Case (3 points max)
2. Bear Case/Risks (3 points max)
3. Recommended Entry Strategy
4. Key Catalysts to Watch
"""

MARKET_REGIME_PROMPT = """
Analyze current market conditions:

VIX: {vix}
VIX 20-day SMA: {vix_sma}
Put/Call Ratio: {put_call_ratio}
S&P 500 RSI: {spy_rsi}
% Above 200 SMA: {breadth}

Determine:
1. Market Regime (Bullish/Bearish/Neutral)
2. Risk Appetite (Risk-On/Risk-Off/Mixed)
3. Recommended Delta Range for Long Calls
4. Suggested DTE Range
5. Sectors to Favor
"""

OPTIONS_STRATEGY_PROMPT = """
Given this stock's profile:
- Trend: {trend_direction}
- IV Rank: {iv_rank}%
- Days to Earnings: {days_to_earnings}
- AI Conviction: {conviction}/10

Recommend the optimal options strategy from:
- Long Calls (specify delta, DTE)
- Bull Call Spread (specify strikes)
- LEAPS (0.70+ delta, 365+ DTE)
- Wait for better entry

Explain your reasoning briefly.
"""
```

---

### Step 4: Add Market Regime Detection

**File: `backend/app/services/ai/market_regime.py`**
```python
class MarketRegimeDetector:
    """Detect current market regime for strategy adjustment."""

    async def get_market_data(self) -> dict:
        """Fetch VIX, SPY RSI, breadth indicators."""
        # Use Yahoo Finance for VIX, SPY data

    async def analyze_regime(self) -> dict:
        """
        Returns:
        {
            'regime': 'bullish' | 'bearish' | 'neutral',
            'risk_mode': 'risk_on' | 'risk_off' | 'mixed',
            'vix': 14.2,
            'vix_trend': 'falling',
            'spy_rsi': 58,
            'breadth': 0.62,  # % stocks above 200 SMA
            'recommended_delta': [0.50, 0.70],
            'recommended_dte': [60, 90],
            'sectors_favor': ['Technology', 'Financials'],
            'sectors_avoid': ['Utilities', 'REITs'],
            'summary': 'Risk-on environment...'
        }
        """

    async def get_ai_regime_analysis(self, data: dict) -> dict:
        """Use Claude to analyze market conditions."""
```

---

### Step 5: Create AI API Endpoints

**File: `backend/app/api/endpoints/ai_analysis.py`**
```python
router = APIRouter()

@router.get("/regime")
async def get_market_regime():
    """Get current market regime analysis."""

@router.post("/insights/{symbol}")
async def get_stock_insights(symbol: str):
    """Get AI-powered insights for a stock."""

@router.post("/batch-insights")
async def get_batch_insights(symbols: List[str]):
    """Get AI insights for multiple stocks."""

@router.post("/explain/{symbol}")
async def explain_opportunity(symbol: str):
    """Explain why this stock has 5x potential."""

@router.post("/strategy/{symbol}")
async def get_strategy_recommendation(symbol: str):
    """Get AI-recommended options strategy."""
```

**Update: `backend/app/main.py`**
```python
from app.api.endpoints import ai_analysis

app.include_router(
    ai_analysis.router,
    prefix=f"{settings.API_V1_PREFIX}/ai",
    tags=["ai"]
)
```

---

### Step 6: Frontend - AI Insights Panel

**Create: `frontend/src/components/ai/`**
```
ai/
├── MarketRegimeBanner.jsx   # Top banner with regime info
├── AIInsightsPanel.jsx      # Expandable insights for stocks
└── StockAIAnalysis.jsx      # Detailed AI analysis modal
```

**File: `frontend/src/components/ai/MarketRegimeBanner.jsx`**
```jsx
// Shows current market regime at top of screener
// - Regime badge (Bullish/Bearish/Neutral)
// - VIX level with color coding
// - Recommended strategy type
// - Last updated timestamp
```

**File: `frontend/src/components/ai/AIInsightsPanel.jsx`**
```jsx
// Collapsible panel in results table
// - AI summary (2-3 sentences)
// - Bull/bear points
// - Recommended action
// - Risk warnings
```

**Update: `frontend/src/pages/Screener.jsx`**
- Add MarketRegimeBanner above tabs
- Add "AI Insights" column/button to ResultsTable
- Add AIInsightsPanel expandable row

---

### Step 7: Frontend API Client

**Create: `frontend/src/api/ai.js`**
```javascript
export const aiAPI = {
  getMarketRegime: async () => { ... },
  getStockInsights: async (symbol) => { ... },
  getBatchInsights: async (symbols) => { ... },
  explainOpportunity: async (symbol) => { ... },
  getStrategyRecommendation: async (symbol) => { ... },
};
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `backend/app/services/ai/__init__.py` | Package init |
| `backend/app/services/ai/claude_service.py` | Claude API integration |
| `backend/app/services/ai/prompts.py` | Prompt templates |
| `backend/app/services/ai/market_regime.py` | VIX/breadth analysis |
| `backend/app/api/endpoints/ai_analysis.py` | AI API endpoints |
| `frontend/src/components/ai/MarketRegimeBanner.jsx` | Regime display |
| `frontend/src/components/ai/AIInsightsPanel.jsx` | Stock insights |
| `frontend/src/api/ai.js` | AI API client |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/app/config.py` | Add Claude API settings |
| `backend/app/main.py` | Register AI router |
| `backend/requirements.txt` | Add `anthropic` package |
| `frontend/src/pages/Screener.jsx` | Add regime banner, insights |
| `frontend/src/components/screener/ResultsTable.jsx` | Add AI column |

---

## Testing Plan

1. **Unit Tests**
   - Test Claude service with mock responses
   - Test market regime detection logic
   - Test prompt formatting

2. **Integration Tests**
   - Test full flow: screening → AI analysis
   - Test regime detection with live data

3. **Manual Testing**
   - Run scan and verify AI insights appear
   - Check regime banner updates
   - Verify Claude API responses are helpful

---

## Dependencies

```txt
# backend/requirements.txt
anthropic>=0.18.0
```

---

## Environment Variables

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

## Estimated Effort

| Component | Effort |
|-----------|--------|
| Claude Service | 2-3 hours |
| Market Regime | 1-2 hours |
| API Endpoints | 1-2 hours |
| Frontend Components | 3-4 hours |
| Testing | 2-3 hours |
| **Total** | **10-14 hours** |

---

## Success Criteria

- [ ] Claude API successfully called with stock data
- [ ] Market regime detected and displayed
- [ ] AI insights shown in results table
- [ ] Strategy recommendations generated
- [ ] No API errors in production
