# AI Trading Assistant - Implementation Skill

## Overview

This skill contains the complete implementation guide for building an AI-powered options trading assistant using Claude API. It includes prompt templates, the Claude service module, and integration patterns.

---

## Project Context

**Goal**: Build an AI-powered options trading tool that:
- Saves hours of research time
- Reduces decision risk with clear reasoning
- Delivers high-quality trade setups with buy/sell signals
- Targets 3-5x returns on LEAPS options over 12-24 months

**Tech Stack**:
- Backend: FastAPI (Python)
- Frontend: React
- AI: Anthropic Claude API (claude-sonnet-4-20250514)
- Data: Yahoo Finance, TastyTrade API, NewsAPI

**User Profile** (single user, personal tool):
- Portfolio: $50,000-100,000
- Strategy: LEAPS with 0.50-0.80 delta, 12-24 month expiration
- Risk tolerance: Can handle 50-100% drawdowns on individual positions
- Goal: 5-10 high-conviction positions, not 50 mediocre ones

---

## Directory Structure

```
backend/
├── app/
│   ├── config.py                 # Add Claude API settings
│   ├── main.py                   # Register AI router
│   └── services/
│       └── ai/
│           ├── __init__.py
│           ├── claude_service.py # Main Claude integration
│           ├── prompts.py        # Prompt templates
│           └── market_regime.py  # VIX/breadth analysis
│   └── api/
│       └── endpoints/
│           └── ai_analysis.py    # AI API endpoints
frontend/
├── src/
│   ├── components/
│   │   └── ai/
│   │       ├── MarketRegimeBanner.jsx
│   │       ├── AIInsightsPanel.jsx
│   │       └── StockAIAnalysis.jsx
│   └── api/
│       └── ai.js
```

---

## Configuration

### backend/app/config.py

Add these settings to the Settings class:

```python
# Claude API Configuration
ANTHROPIC_API_KEY: str = ""
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS: int = 2048

# Cost tracking
CLAUDE_COST_PER_1K_INPUT_TOKENS: float = 0.003  # Sonnet pricing
CLAUDE_COST_PER_1K_OUTPUT_TOKENS: float = 0.015
CLAUDE_DAILY_BUDGET: float = 10.00  # $10/day default limit
```

### backend/.env

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### backend/requirements.txt

Add:
```
anthropic>=0.18.0
```

---

## Prompt Templates

### File: backend/app/services/ai/prompts.py

```python
"""
AI Prompt Templates for Options Trading Assistant

Design Principles:
1. Give Claude a clear expert persona
2. Provide full context before asking for analysis
3. Request structured JSON output for programmatic use
4. Use chain-of-thought reasoning for complex decisions
5. Include user's personal trading parameters
"""

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPT_TRADING_ANALYST = """You are an elite options trader and quantitative analyst with 20 years of experience. You specialize in identifying asymmetric risk/reward opportunities using LEAPS (Long-term Equity Anticipation Securities) for 3-5x returns over 12-24 months.

Your analysis style:
- Data-driven but not robotic—you explain the "story" behind the numbers
- Contrarian when the data supports it
- Obsessive about risk management and position sizing
- You think in probabilities, not certainties
- You're direct and opinionated—no wishy-washy "it depends" answers

You're advising a sophisticated retail trader who:
- Has a $50,000-100,000 portfolio
- Targets 3-5x returns on individual LEAPS positions
- Prefers 0.50-0.80 delta, 12-24 month expiration
- Can tolerate 50-100% drawdowns on individual positions if thesis intact
- Wants 5-10 high-conviction positions, not 50 mediocre ones
- Values quality of reasoning over quantity of ideas

Always be specific. Instead of "consider buying calls," say "buy the Jan 2026 $150 calls at 0.65 delta."
"""

SYSTEM_PROMPT_MARKET_ANALYST = """You are a macro strategist who specializes in reading market regimes to optimize options positioning. You combine:
- Volatility analysis (VIX term structure, skew)
- Breadth indicators (advance/decline, % above moving averages)
- Sentiment (put/call ratios, fund flows)
- Intermarket analysis (bonds, dollar, commodities)

Your job is to tell the trader: "Given current conditions, here's how to adjust your delta exposure, time horizon, and sector allocation."

Be decisive. Markets reward conviction.
"""

# =============================================================================
# MARKET REGIME ANALYSIS
# =============================================================================

MARKET_REGIME_PROMPT = """## Current Market Data

**Volatility**
- VIX: {vix:.2f}
- VIX 20-day SMA: {vix_sma:.2f}
- VIX Percentile (1Y): {vix_percentile:.0f}th
- VIX Term Structure: {vix_term_structure} (contango/backwardation)

**Breadth & Trend**
- S&P 500: {spy_price:.2f} ({spy_change_pct:+.1f}% today)
- SPY RSI(14): {spy_rsi:.1f}
- SPY vs 50-day SMA: {spy_vs_50sma:+.1f}%
- SPY vs 200-day SMA: {spy_vs_200sma:+.1f}%
- % of S&P 500 above 200 SMA: {breadth_200sma:.0f}%
- % of S&P 500 above 50 SMA: {breadth_50sma:.0f}%
- Advance/Decline Line: {ad_line_trend}

**Sentiment**
- Put/Call Ratio (equity): {put_call_ratio:.2f}
- Put/Call 10-day SMA: {put_call_sma:.2f}
- AAII Bull/Bear Spread: {aaii_spread:+.1f}%

**Intermarket**
- 10Y Treasury Yield: {ten_year_yield:.2f}% ({yield_change:+.0f} bps weekly)
- DXY (Dollar Index): {dxy:.1f}
- HYG (High Yield): {hyg_trend}

---

## Your Task

Analyze these conditions and provide your assessment in the following JSON format:

```json
{{
  "regime": "bullish" | "bearish" | "neutral" | "transitioning",
  "regime_confidence": 0-100,
  "risk_appetite": "risk_on" | "risk_off" | "selective",
  
  "volatility_assessment": {{
    "level": "low" | "normal" | "elevated" | "crisis",
    "trend": "rising" | "falling" | "stable",
    "implication": "string explaining what this means for options buyers"
  }},
  
  "breadth_assessment": {{
    "health": "strong" | "weakening" | "diverging" | "capitulation",
    "implication": "string"
  }},
  
  "positioning_guidance": {{
    "delta_range": [0.XX, 0.XX],
    "delta_rationale": "why this delta range",
    "dte_range": [min_days, max_days],
    "dte_rationale": "why this DTE range",
    "position_size_modifier": 0.5-1.5,
    "size_rationale": "why adjust size"
  }},
  
  "sector_allocation": {{
    "overweight": ["sector1", "sector2"],
    "underweight": ["sector3", "sector4"],
    "rationale": "brief explanation"
  }},
  
  "key_risks": [
    "risk 1 to monitor",
    "risk 2 to monitor"
  ],
  
  "summary": "2-3 sentence executive summary a trader can glance at"
}}
```

Think step-by-step before providing your JSON response. What is the market telling us right now?
"""

# =============================================================================
# STOCK ANALYSIS (Deep Dive)
# =============================================================================

STOCK_ANALYSIS_PROMPT = """## Stock Under Analysis: {symbol}

### Company Overview
- **Name**: {company_name}
- **Sector**: {sector} | **Industry**: {industry}
- **Market Cap**: ${market_cap_formatted} ({market_cap_category})
- **Description**: {business_description}

### Price & Valuation
- **Current Price**: ${current_price:.2f}
- **52-Week Range**: ${fifty_two_week_low:.2f} - ${fifty_two_week_high:.2f} (currently at {price_percentile:.0f}th percentile)
- **P/E (TTM)**: {pe_ratio:.1f} | **Forward P/E**: {forward_pe:.1f}
- **P/S**: {ps_ratio:.1f} | **P/B**: {pb_ratio:.1f}
- **PEG Ratio**: {peg_ratio:.2f}

### Fundamentals (Scored 0-100: {fundamental_score})
- **Revenue Growth (YoY)**: {revenue_growth:+.1f}%
- **EPS Growth (YoY)**: {eps_growth:+.1f}%
- **Gross Margin**: {gross_margin:.1f}%
- **Operating Margin**: {operating_margin:.1f}%
- **Net Margin**: {net_margin:.1f}%
- **ROE**: {roe:.1f}%
- **Debt/Equity**: {debt_to_equity:.2f}
- **Free Cash Flow Yield**: {fcf_yield:.1f}%

### Technical Indicators (Scored 0-100: {technical_score})
- **Trend**: {trend_description}
- **RSI(14)**: {rsi:.1f}
- **MACD**: {macd_signal} (histogram: {macd_histogram:+.3f})
- **Price vs 50 SMA**: {price_vs_50sma:+.1f}%
- **Price vs 200 SMA**: {price_vs_200sma:+.1f}%
- **ADX**: {adx:.1f} (trend strength)
- **Recent Pattern**: {chart_pattern}
- **Key Support**: ${support_level:.2f}
- **Key Resistance**: ${resistance_level:.2f}

### Options Data (Scored 0-100: {options_score})
- **IV Rank (1Y)**: {iv_rank:.0f}%
- **IV Percentile (1Y)**: {iv_percentile:.0f}%
- **Current IV**: {current_iv:.1f}%
- **HV(30)**: {hv_30:.1f}%
- **IV/HV Ratio**: {iv_hv_ratio:.2f}
- **Options Liquidity**: {options_liquidity} (volume: {avg_options_volume:,})
- **Put/Call OI Ratio**: {put_call_oi:.2f}
- **Unusual Activity**: {unusual_activity}

### Sentiment & Catalysts
- **Analyst Consensus**: {analyst_rating} (avg PT: ${analyst_pt:.2f}, {pt_upside:+.1f}% upside)
- **Earnings Date**: {next_earnings} ({days_to_earnings} days)
- **Recent News Sentiment**: {news_sentiment}
- **Insider Activity (90d)**: {insider_activity}

### LEAPS Available (Targeting 5x)
{leaps_chain_summary}

### Current Market Regime Context
- **Regime**: {market_regime}
- **Recommended Delta**: {regime_delta_range}
- **Sector Outlook**: {sector_outlook_for_this_stock}

---

## Your Task

Analyze {symbol} as a potential 5x LEAPS opportunity. Provide your analysis in this JSON format:

```json
{{
  "conviction_score": 1-10,
  "conviction_rationale": "one sentence explaining the score",
  
  "opportunity_type": "5x_candidate" | "2-3x_solid" | "income_play" | "avoid" | "wait_for_entry",
  
  "bull_case": {{
    "thesis": "the core reason this could 5x in plain English",
    "key_catalysts": [
      {{"catalyst": "description", "expected_timing": "Q1 2025", "impact": "high/medium/low"}}
    ],
    "upside_target": "$XXX (X.Xx from current)",
    "probability_estimate": "XX%"
  }},
  
  "bear_case": {{
    "thesis": "what would make this fail",
    "key_risks": [
      {{"risk": "description", "likelihood": "high/medium/low", "mitigation": "how to monitor or hedge"}}
    ],
    "downside_target": "$XXX",
    "probability_estimate": "XX%"
  }},
  
  "options_assessment": {{
    "iv_attractiveness": "cheap" | "fair" | "expensive",
    "iv_rationale": "why",
    "liquidity_sufficient": true/false,
    "earnings_risk": "description of how earnings affects entry timing"
  }},
  
  "recommended_action": {{
    "action": "buy_now" | "buy_on_pullback" | "wait_for_catalyst" | "avoid",
    "entry_strategy": "specific description",
    "entry_trigger": "what specific condition should prompt entry",
    "position_size": "X% of portfolio",
    "size_rationale": "why this size"
  }},
  
  "leaps_recommendation": {{
    "contract": "Jan 2026 $XXX Call" | "none",
    "strike_selection_rationale": "why this strike",
    "delta": 0.XX,
    "current_premium": "$X.XX",
    "break_even": "$XXX.XX",
    "max_loss": "$X,XXX (X% of position)",
    "target_exit": "$XX.XX (XXX% gain) when stock hits $XXX",
    "stop_loss": "close if stock breaks below $XXX or premium drops to $X.XX"
  }},
  
  "monitoring_checklist": [
    "specific thing to watch #1",
    "specific thing to watch #2",
    "specific thing to watch #3"
  ],
  
  "summary": "2-3 sentence summary a trader can quickly read"
}}
```

Think through this step-by-step:
1. First, assess the fundamental quality—is this a business that deserves to 5x?
2. Then, check the technicals—is the trend your friend or fighting you?
3. Evaluate the options pricing—are you paying fair value for the upside?
4. Consider timing—is now the right entry or should you wait?
5. Finally, size appropriately—how much conviction do you really have?
"""

# =============================================================================
# QUICK SCAN ANALYSIS (For batch processing)
# =============================================================================

QUICK_SCAN_PROMPT = """## Batch Analysis Request

Analyze these {count} stocks that passed initial screening for 5x LEAPS potential. For each, provide a quick assessment.

### Stocks to Analyze:
{stocks_data}

### Current Market Regime:
- Regime: {market_regime}
- Recommended Delta: {regime_delta_range}
- Risk Mode: {risk_mode}

---

Respond with a JSON array, one object per stock:

```json
[
  {{
    "symbol": "XXXX",
    "conviction": 1-10,
    "one_liner": "< 15 word summary of opportunity",
    "action": "strong_buy" | "buy" | "watch" | "avoid",
    "primary_catalyst": "the single biggest reason to buy",
    "primary_risk": "the single biggest reason it could fail",
    "entry_timing": "now" | "wait_for_pullback" | "post_earnings" | "avoid",
    "suggested_strike": "Month YYYY $XXX Call" or "none"
  }}
]
```

Rank them by conviction (highest first). Be ruthless—if it's not compelling, score it low.
"""

# =============================================================================
# STRATEGY RECOMMENDATION
# =============================================================================

STRATEGY_RECOMMENDATION_PROMPT = """## Strategy Recommendation Request: {symbol}

### Stock Profile
- **Current Price**: ${current_price:.2f}
- **Trend**: {trend_direction} (strength: {trend_strength}/10)
- **IV Rank**: {iv_rank:.0f}%
- **IV vs HV**: {iv_hv_comparison}
- **Days to Earnings**: {days_to_earnings}
- **Earnings Volatility**: {historical_earnings_move}% average move

### My Conviction & Outlook
- **AI Conviction Score**: {conviction_score}/10
- **Price Target**: ${price_target:.2f} ({target_upside:+.0f}%)
- **Target Timeframe**: {target_timeframe}
- **Thesis**: {one_line_thesis}

### Available Options (Relevant Strikes)
{options_chain_summary}

### Current Market Regime
- **Regime**: {market_regime}
- **Recommended Delta**: {regime_delta_range}
- **Regime DTE Preference**: {regime_dte_range}

### My Portfolio Context
- **Current Portfolio Delta**: {portfolio_delta}
- **Existing Position in {symbol}**: {existing_position}
- **Sector Exposure**: {sector_exposure}
- **Cash Available**: ${cash_available:,.0f}

---

## Your Task

Recommend the optimal options strategy. Consider:
1. Given IV rank, should I buy premium or is it expensive?
2. Given time to earnings, should I wait or go now?
3. Given my conviction, how aggressive should the strike be?
4. Given market regime, what delta makes sense?
5. Given my existing portfolio, does this add concentration risk?

Respond in JSON:

```json
{{
  "recommended_strategy": {{
    "name": "Long Call" | "Bull Call Spread" | "LEAPS" | "Cash-Secured Put" | "Wait",
    "rationale": "why this strategy over alternatives"
  }},
  
  "if_long_call_or_leaps": {{
    "contract": "MMM DD YYYY $XXX Call",
    "delta": 0.XX,
    "premium": "$X.XX per contract",
    "contracts": X,
    "total_cost": "$X,XXX",
    "break_even": "$XXX.XX",
    "profit_at_target": "$X,XXX (XXX%)",
    "max_loss": "$X,XXX",
    "greeks": {{
      "delta": X.XX,
      "gamma": X.XXXX,
      "theta": -$X.XX/day,
      "vega": $X.XX
    }}
  }},
  
  "if_spread": {{
    "long_leg": "MMM DD YYYY $XXX Call @ $X.XX",
    "short_leg": "MMM DD YYYY $XXX Call @ $X.XX",
    "net_debit": "$X.XX",
    "max_profit": "$X,XXX",
    "max_loss": "$X,XXX",
    "break_even": "$XXX.XX"
  }},
  
  "if_wait": {{
    "wait_for": "specific condition",
    "set_alert_at": "$XXX.XX",
    "alternative_action": "what to do in the meantime"
  }},
  
  "entry_execution": {{
    "order_type": "limit" | "market",
    "limit_price": "$X.XX",
    "good_til": "day" | "GTC",
    "notes": "any execution tips"
  }},
  
  "exit_plan": {{
    "profit_target_1": "close 50% at XXX% gain ($X.XX premium)",
    "profit_target_2": "close remaining at XXX% gain or stock at $XXX",
    "stop_loss": "close if premium drops to $X.XX or stock breaks $XXX",
    "time_stop": "re-evaluate if < 60 DTE with < 50% of target reached"
  }},
  
  "alternatives_considered": [
    {{"strategy": "name", "why_not": "reason it's inferior"}}
  ],
  
  "position_size_recommendation": {{
    "dollars": "$X,XXX",
    "percent_of_portfolio": "X%",
    "rationale": "why this size"
  }}
}}
```
"""

# =============================================================================
# RISK ANALYSIS
# =============================================================================

RISK_ANALYSIS_PROMPT = """## Risk Analysis: {symbol}

### Position Details
- **Position**: {position_description}
- **Entry Price**: ${entry_price:.2f}
- **Current Price**: ${current_price:.2f}
- **P/L**: {pnl_percent:+.1f}% (${pnl_dollars:+,.0f})
- **Days Held**: {days_held}
- **DTE Remaining**: {dte_remaining}

### Current Stock Status
{stock_summary}

### Recent Developments
{recent_news}

---

## Your Task

Analyze the risks to this position and recommend action:

```json
{{
  "risk_level": "low" | "moderate" | "elevated" | "high" | "critical",
  
  "thesis_intact": true | false,
  "thesis_assessment": "is the original bull case still valid?",
  
  "risks": [
    {{
      "risk": "description",
      "severity": "low" | "medium" | "high",
      "likelihood": "low" | "medium" | "high",
      "time_horizon": "immediate" | "near_term" | "medium_term",
      "indicator_to_watch": "what would signal this risk is materializing"
    }}
  ],
  
  "recommendation": {{
    "action": "hold" | "add" | "trim" | "close" | "hedge",
    "rationale": "why",
    "specific_execution": "exactly what to do"
  }},
  
  "if_hedge": {{
    "hedge_strategy": "description",
    "hedge_cost": "$XXX",
    "protection_level": "protects below $XXX"
  }},
  
  "updated_exit_plan": {{
    "new_stop_loss": "$XXX or $X.XX premium",
    "new_profit_target": "$XXX",
    "time_stop": "specific date or condition"
  }}
}}
```
"""

# =============================================================================
# DAILY BRIEFING
# =============================================================================

DAILY_BRIEFING_PROMPT = """## Daily Briefing Request

### Market Data (as of {timestamp})
{market_regime_data}

### My Current Positions
{positions_summary}

### Today's Earnings Calendar (Relevant to Positions/Watchlist)
{earnings_today}

### News Overnight
{overnight_news}

---

## Your Task

Provide my daily briefing in this format:

```json
{{
  "market_summary": "2-3 sentences on what happened and what to expect today",
  
  "regime_change": {{
    "changed": true | false,
    "from": "previous regime",
    "to": "current regime",
    "implication": "what this means for my positions"
  }},
  
  "position_alerts": [
    {{
      "symbol": "XXX",
      "alert_type": "earnings" | "stop_loss" | "profit_target" | "news" | "technical",
      "message": "specific alert",
      "action_required": true | false,
      "suggested_action": "what to do"
    }}
  ],
  
  "opportunities_today": [
    {{
      "symbol": "XXX",
      "opportunity": "description",
      "urgency": "act_today" | "this_week" | "monitor"
    }}
  ],
  
  "watchlist_updates": [
    {{
      "symbol": "XXX",
      "update": "what changed",
      "new_status": "ready_to_buy" | "still_watching" | "remove"
    }}
  ],
  
  "key_levels_today": [
    {{
      "index_or_stock": "SPY",
      "support": "$XXX",
      "resistance": "$XXX",
      "significance": "why these matter"
    }}
  ],
  
  "today_focus": "the single most important thing to pay attention to today"
}}
```
"""

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_leaps_chain(leaps_data: list) -> str:
    """Format LEAPS options chain for prompt inclusion."""
    if not leaps_data:
        return "No LEAPS data available"
    
    lines = []
    for leap in leaps_data:
        line = (
            f"- {leap['expiration']} ${leap['strike']:.0f}C | "
            f"Delta: {leap['delta']:.2f} | "
            f"Premium: ${leap['premium']:.2f} | "
            f"OI: {leap['open_interest']:,} | "
            f"Break-even: ${leap['break_even']:.2f} ({leap['break_even_pct']:+.1f}%)"
        )
        lines.append(line)
    return "\n".join(lines)


def format_market_cap(market_cap: float) -> tuple[str, str]:
    """Format market cap with category."""
    if market_cap >= 200e9:
        return f"{market_cap/1e9:.0f}B", "Mega Cap"
    elif market_cap >= 10e9:
        return f"{market_cap/1e9:.1f}B", "Large Cap"
    elif market_cap >= 2e9:
        return f"{market_cap/1e9:.1f}B", "Mid Cap"
    elif market_cap >= 300e6:
        return f"{market_cap/1e6:.0f}M", "Small Cap"
    else:
        return f"{market_cap/1e6:.0f}M", "Micro Cap"


def format_stocks_for_batch(stocks: list) -> str:
    """Format multiple stocks for batch analysis prompt."""
    formatted = []
    for i, stock in enumerate(stocks, 1):
        formatted.append(f"""
### {i}. {stock['symbol']} - {stock['company_name']}
- Price: ${stock['price']:.2f} | Sector: {stock['sector']}
- Composite Score: {stock['score']}/100
- Fundamental: {stock['fundamental_score']} | Technical: {stock['technical_score']} | Options: {stock['options_score']}
- IV Rank: {stock['iv_rank']:.0f}% | Trend: {stock['trend']}
- Key Metric: {stock['key_highlight']}
""")
    return "\n".join(formatted)
```

---

## Claude Service Implementation

### File: backend/app/services/ai/claude_service.py

```python
"""
Claude AI Service for Options Trading Analysis

This module provides the core integration with Anthropic's Claude API,
handling all AI-powered analysis for the trading assistant.
"""

import json
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field

import anthropic
from anthropic import APIError, RateLimitError as AnthropicRateLimitError

from app.config import settings
from app.services.ai.prompts import (
    SYSTEM_PROMPT_TRADING_ANALYST,
    SYSTEM_PROMPT_MARKET_ANALYST,
    MARKET_REGIME_PROMPT,
    STOCK_ANALYSIS_PROMPT,
    QUICK_SCAN_PROMPT,
    STRATEGY_RECOMMENDATION_PROMPT,
    RISK_ANALYSIS_PROMPT,
    DAILY_BRIEFING_PROMPT,
    format_leaps_chain,
    format_market_cap,
    format_stocks_for_batch,
)

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class AIAnalysisError(Exception):
    """Base exception for AI analysis errors."""
    pass


class RateLimitError(AIAnalysisError):
    """Claude API rate limit hit."""
    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s" if retry_after else "Rate limit exceeded")


class BudgetExceededError(AIAnalysisError):
    """Daily budget exceeded."""
    pass


class InvalidResponseError(AIAnalysisError):
    """Claude returned unparseable response."""
    def __init__(self, message: str, raw_response: str = ""):
        self.raw_response = raw_response
        super().__init__(message)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TokenUsage:
    """Track token usage for a single request."""
    input_tokens: int
    output_tokens: int
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    @property
    def estimated_cost(self) -> float:
        return (
            (self.input_tokens / 1000) * settings.CLAUDE_COST_PER_1K_INPUT_TOKENS +
            (self.output_tokens / 1000) * settings.CLAUDE_COST_PER_1K_OUTPUT_TOKENS
        )


@dataclass
class CostTracker:
    """Track daily API costs."""
    daily_costs: dict = field(default_factory=dict)
    daily_requests: dict = field(default_factory=dict)
    
    def _get_today(self) -> str:
        return datetime.now().date().isoformat()
    
    def add_usage(self, usage: TokenUsage) -> float:
        """Record token usage and return cost."""
        today = self._get_today()
        
        if today not in self.daily_costs:
            self.daily_costs = {today: 0.0}
            self.daily_requests = {today: 0}
        
        cost = usage.estimated_cost
        self.daily_costs[today] += cost
        self.daily_requests[today] += 1
        
        logger.debug(
            f"API call: {usage.input_tokens} in, {usage.output_tokens} out, "
            f"${cost:.4f} (daily total: ${self.daily_costs[today]:.2f})"
        )
        
        return cost
    
    def get_daily_cost(self) -> float:
        return self.daily_costs.get(self._get_today(), 0.0)
    
    def get_daily_requests(self) -> int:
        return self.daily_requests.get(self._get_today(), 0)
    
    def check_budget(self) -> bool:
        return self.get_daily_cost() < settings.CLAUDE_DAILY_BUDGET
    
    def get_remaining_budget(self) -> float:
        return max(0, settings.CLAUDE_DAILY_BUDGET - self.get_daily_cost())


@dataclass
class CachedResponse:
    """Cached API response with timestamp."""
    data: dict
    timestamp: datetime
    
    def is_expired(self, ttl: timedelta) -> bool:
        return datetime.now() - self.timestamp > ttl


@dataclass 
class AnalysisResult:
    """Standardized result from AI analysis."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None
    usage: Optional[TokenUsage] = None
    cached: bool = False


# =============================================================================
# RESPONSE PARSER
# =============================================================================

class ResponseParser:
    """Parse and validate Claude's JSON responses."""
    
    @staticmethod
    def extract_json(response_text: str) -> Optional[dict | list]:
        """Extract JSON from Claude's response, handling markdown code blocks."""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                return None
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            json_str = re.sub(r':\s*\.(\d)', r': 0.\1', json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None
    
    @staticmethod
    def validate_market_regime(data: dict) -> dict:
        """Validate and normalize market regime response."""
        required_fields = ['regime', 'risk_appetite', 'positioning_guidance', 'summary']
        
        for field in required_fields:
            if field not in data:
                raise InvalidResponseError(f"Missing required field: {field}")
        
        valid_regimes = ['bullish', 'bearish', 'neutral', 'transitioning']
        if data['regime'].lower() not in valid_regimes:
            data['regime'] = 'neutral'
        else:
            data['regime'] = data['regime'].lower()
        
        if 'regime_confidence' in data:
            data['regime_confidence'] = max(0, min(100, int(data['regime_confidence'])))
        
        return data
    
    @staticmethod
    def validate_stock_analysis(data: dict) -> dict:
        """Validate and normalize stock analysis response."""
        if 'conviction_score' in data:
            data['conviction_score'] = max(1, min(10, int(data['conviction_score'])))
        
        if 'bull_case' not in data:
            data['bull_case'] = {'thesis': 'Not analyzed', 'key_catalysts': []}
        if 'bear_case' not in data:
            data['bear_case'] = {'thesis': 'Not analyzed', 'key_risks': []}
        if 'recommended_action' not in data:
            data['recommended_action'] = {'action': 'wait_for_catalyst', 'entry_strategy': 'Needs manual review'}
        
        return data
    
    @staticmethod
    def validate_strategy_recommendation(data: dict) -> dict:
        """Validate strategy recommendation response."""
        if 'recommended_strategy' not in data:
            raise InvalidResponseError("Missing recommended_strategy field")
        
        valid_strategies = ['Long Call', 'Bull Call Spread', 'LEAPS', 'Cash-Secured Put', 'Wait', 'Avoid']
        strategy_name = data['recommended_strategy'].get('name', '')
        
        if strategy_name not in valid_strategies:
            logger.warning(f"Unexpected strategy: {strategy_name}")
        
        return data


# =============================================================================
# MAIN SERVICE CLASS
# =============================================================================

class ClaudeAnalysisService:
    """AI-powered analysis service using Claude."""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
        
        self.cost_tracker = CostTracker()
        self.parser = ResponseParser()
        
        self._cache: dict[str, CachedResponse] = {}
        self._cache_ttl = {
            'market_regime': timedelta(minutes=15),
            'stock_analysis': timedelta(minutes=30),
            'batch_analysis': timedelta(minutes=30),
        }
        
        self._max_retries = 3
        self._base_retry_delay = 1.0
        
        logger.info(f"ClaudeAnalysisService initialized with model: {self.model}")
    
    async def _call_claude(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> tuple[str, TokenUsage]:
        """Make a call to Claude API with retry logic."""
        if not self.cost_tracker.check_budget():
            raise BudgetExceededError(
                f"Daily budget of ${settings.CLAUDE_DAILY_BUDGET:.2f} exceeded. "
                f"Current spend: ${self.cost_tracker.get_daily_cost():.2f}"
            )
        
        max_tokens = max_tokens or self.max_tokens
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}]
                    )
                )
                
                response_text = response.content[0].text
                
                usage = TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens
                )
                self.cost_tracker.add_usage(usage)
                
                return response_text, usage
                
            except AnthropicRateLimitError as e:
                last_error = e
                retry_after = getattr(e, 'retry_after', None) or (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {retry_after}s (attempt {attempt + 1}/{self._max_retries})")
                
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(retry_after)
                else:
                    raise RateLimitError(retry_after=retry_after)
                    
            except APIError as e:
                last_error = e
                logger.error(f"Claude API error: {e}")
                
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    raise AIAnalysisError(f"Claude API error after {self._max_retries} attempts: {e}")
        
        raise AIAnalysisError(f"Unexpected error: {last_error}")
    
    def _get_cached(self, cache_key: str, cache_type: str) -> Optional[dict]:
        """Get cached response if valid."""
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            ttl = self._cache_ttl.get(cache_type, timedelta(minutes=15))
            if not cached.is_expired(ttl):
                logger.debug(f"Cache hit for {cache_key}")
                return cached.data
        return None
    
    def _set_cached(self, cache_key: str, data: dict):
        """Cache a response."""
        self._cache[cache_key] = CachedResponse(data=data, timestamp=datetime.now())
    
    # See full implementation in the conversation for all methods:
    # - get_market_regime()
    # - analyze_stock()
    # - analyze_batch()
    # - get_strategy_recommendation()
    # - analyze_position_risk()
    # - get_daily_briefing()
    # - Helper methods for formatting
    
    def get_usage_stats(self) -> dict:
        """Get current API usage statistics."""
        return {
            'daily_cost': self.cost_tracker.get_daily_cost(),
            'daily_requests': self.cost_tracker.get_daily_requests(),
            'remaining_budget': self.cost_tracker.get_remaining_budget(),
            'budget_limit': settings.CLAUDE_DAILY_BUDGET,
        }
    
    def clear_cache(self, cache_type: Optional[str] = None):
        """Clear cached responses."""
        if cache_type:
            keys_to_remove = [k for k in self._cache if k.startswith(cache_type)]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()


# Singleton instance
_service_instance: Optional[ClaudeAnalysisService] = None


def get_claude_service() -> ClaudeAnalysisService:
    """Get or create the Claude service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ClaudeAnalysisService()
    return _service_instance
```

---

## API Endpoints

### File: backend/app/api/endpoints/ai_analysis.py

```python
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel

from app.services.ai.claude_service import get_claude_service, ClaudeAnalysisService

router = APIRouter()


class StockAnalysisRequest(BaseModel):
    symbol: str
    include_regime: bool = True


class BatchAnalysisRequest(BaseModel):
    symbols: List[str]


@router.get("/regime")
async def get_market_regime(
    force_refresh: bool = False,
    service: ClaudeAnalysisService = Depends(get_claude_service)
):
    """Get current market regime analysis."""
    # Fetch market data (implement fetch_market_data)
    market_data = await fetch_market_data()
    
    result = await service.get_market_regime(market_data, force_refresh=force_refresh)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return {
        "regime": result.data,
        "cached": result.cached,
        "cost": result.usage.estimated_cost if result.usage else 0
    }


@router.post("/analyze/{symbol}")
async def analyze_stock(
    symbol: str,
    service: ClaudeAnalysisService = Depends(get_claude_service)
):
    """Get deep AI analysis for a stock."""
    stock_data = await fetch_stock_data(symbol)
    
    regime_result = await service.get_market_regime(await fetch_market_data())
    regime = regime_result.data if regime_result.success else None
    
    result = await service.analyze_stock(stock_data, market_regime=regime)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result.data


@router.post("/batch")
async def analyze_batch(
    request: BatchAnalysisRequest,
    service: ClaudeAnalysisService = Depends(get_claude_service)
):
    """Quick analysis of multiple stocks."""
    stocks_data = [await fetch_stock_data(s) for s in request.symbols]
    
    regime_result = await service.get_market_regime(await fetch_market_data())
    regime = regime_result.data if regime_result.success else None
    
    result = await service.analyze_batch(stocks_data, market_regime=regime)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result.data


@router.post("/strategy/{symbol}")
async def get_strategy(
    symbol: str,
    service: ClaudeAnalysisService = Depends(get_claude_service)
):
    """Get options strategy recommendation."""
    stock_data = await fetch_stock_data(symbol)
    options_chain = await fetch_options_chain(symbol)
    
    regime_result = await service.get_market_regime(await fetch_market_data())
    
    result = await service.get_strategy_recommendation(
        stock_data=stock_data,
        options_chain=options_chain,
        market_regime=regime_result.data if regime_result.success else None
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result.data


@router.get("/usage")
async def get_usage_stats(
    service: ClaudeAnalysisService = Depends(get_claude_service)
):
    """Get API usage statistics."""
    return service.get_usage_stats()
```

---

## Key Implementation Notes

1. **Always use JSON output format** - Prompts request structured JSON for programmatic use
2. **Cache aggressively** - Market regime cached 15 min, stock analysis 30 min
3. **Track costs** - Daily budget limit prevents runaway API costs
4. **Validate responses** - Parser handles malformed JSON and validates required fields
5. **Retry logic** - Automatic retries with exponential backoff for rate limits
6. **Singleton pattern** - Single service instance across all requests

## Testing

Test the Claude service with:

```python
import asyncio
from app.services.ai.claude_service import get_claude_service

async def test():
    service = get_claude_service()
    
    # Test market regime
    market_data = {
        'vix': 14.5,
        'vix_sma': 15.2,
        'spy_rsi': 58,
        # ... other fields
    }
    
    result = await service.get_market_regime(market_data)
    print(result.data)

asyncio.run(test())
```