"""
AI Prompt Templates for Options Trading Assistant

Design Principles:
1. Give Claude a clear expert persona
2. Provide full context before asking for analysis
3. Request structured JSON output for programmatic use
4. Use chain-of-thought reasoning for complex decisions
5. Include your personal trading parameters
"""

# =============================================================================
# SYSTEM PROMPTS (Used as system message, sets Claude's persona)
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
# QUICK SCAN ANALYSIS (For batch processing, more concise)
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
# STRATEGY RECOMMENDATION (Options-specific)
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
# RISK ANALYSIS (Dedicated risk focus)
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
# HELPER FUNCTIONS FOR PROMPT FORMATTING
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