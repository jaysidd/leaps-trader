"""
Prompt templates for Claude AI analysis

Enhanced with:
- System prompts for consistent persona
- JSON output specifications for parsing
- Chain-of-thought reasoning instructions
- Batch analysis support
"""

from typing import Dict, List, Any, Optional

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPT_TRADING_ANALYST = """You are an elite options trading analyst specializing in LEAPS (Long-Term Equity Anticipation Securities) strategies for 5x return potential.

Your expertise includes:
- Identifying undervalued stocks with strong fundamentals and growth catalysts
- Technical analysis for optimal entry timing
- Options pricing, Greeks, and volatility analysis
- Risk management and position sizing
- Market regime adaptation

Your analysis style:
- Data-driven and specific (use actual numbers, not vague statements)
- Risk-aware (always consider downside scenarios)
- Actionable (provide specific strikes, deltas, and timeframes)
- Concise (traders don't have time for fluff)

Always respond in valid JSON format when requested. Never include markdown code blocks or extra text outside the JSON structure."""

SYSTEM_PROMPT_MARKET_ANALYST = """You are an expert market analyst specializing in regime detection and macro analysis.

Your expertise includes:
- VIX and volatility analysis
- Market breadth indicators
- Sector rotation patterns
- Risk-on/risk-off regime identification
- Options flow analysis

Always respond in valid JSON format when requested. Be precise and actionable."""

# =============================================================================
# STOCK ANALYSIS PROMPTS
# =============================================================================

STOCK_ANALYSIS_PROMPT = """Analyze this stock for LEAPS potential and provide your assessment.

## Stock: {symbol} - {name}
Sector: {sector}
Current Price: ${current_price:.2f}
Market Cap: {market_cap_formatted}

## Screening Scores (0-100)
- Fundamental Score: {fundamental_score:.0f}
- Technical Score: {technical_score:.0f}
- Options Score: {options_score:.0f}
- Momentum Score: {momentum_score:.0f}
- **Composite Score: {score:.0f}**

## Key Fundamentals
{fundamentals_summary}

## Technical Indicators
{technical_summary}

## LEAPS Availability
{leaps_summary}

## Current Market Regime
{market_regime}

Analyze this data and respond with ONLY this JSON structure (no markdown, no extra text):
{{
    "conviction": <1-10 integer>,
    "bull_case": ["<point 1>", "<point 2>", "<point 3 if applicable>"],
    "bear_case": ["<risk 1>", "<risk 2>", "<risk 3 if applicable>"],
    "strategy": {{
        "type": "<Long Call | Bull Call Spread | LEAPS Diagonal | Wait>",
        "delta_range": [<min>, <max>],
        "dte_range": [<min>, <max>],
        "reasoning": "<why this strategy fits>"
    }},
    "catalyst": "<most important upcoming trigger>",
    "summary": "<one sentence bottom line>"
}}"""


QUICK_SCAN_PROMPT = """Quick assessment of {symbol} for LEAPS potential.

Price: ${current_price:.2f} | Score: {score:.0f}/100 | IV Rank: {iv_rank:.0f}%
Fundamentals: {fundamental_score:.0f} | Technical: {technical_score:.0f}

Respond with ONLY this JSON (no markdown):
{{
    "conviction": <1-10>,
    "verdict": "<Strong Buy | Buy | Hold | Avoid>",
    "one_liner": "<20 words max summary>"
}}"""


# =============================================================================
# MARKET REGIME PROMPTS
# =============================================================================

MARKET_REGIME_PROMPT = """Analyze current market conditions and determine the trading regime.

## Market Data
- VIX: {vix:.2f}
- VIX 20-day SMA: {vix_sma:.2f}
- VIX Trend: {vix_trend}
- S&P 500 RSI (14): {spy_rsi:.1f}
- S&P 500 vs 200 SMA: {spy_vs_200sma}
- Put/Call Ratio: {put_call_ratio:.2f}
- Market Breadth: {market_breadth}

Analyze this data using your expertise. Consider:
1. Is volatility elevated or suppressed relative to recent history?
2. Is the market overbought, oversold, or neutral?
3. What does the put/call ratio suggest about sentiment?
4. Is the trend intact or breaking down?

Respond with ONLY this JSON (no markdown, no extra text):
{{
    "regime": "<bullish | bearish | neutral | volatile>",
    "risk_mode": "<risk_on | risk_off | mixed>",
    "confidence": <1-10>,
    "vix_assessment": "<low | normal | elevated | fear>",
    "trend_strength": "<strong | moderate | weak | reversing>",
    "delta_recommendation": [<min>, <max>],
    "dte_recommendation": [<min>, <max>],
    "sectors_favor": ["<sector1>", "<sector2>"],
    "sectors_avoid": ["<sector1>"],
    "summary": "<one sentence market read>",
    "trading_stance": "<aggressive | normal | defensive | cash>"
}}"""


# =============================================================================
# OPTIONS STRATEGY PROMPTS
# =============================================================================

OPTIONS_STRATEGY_PROMPT = """Given this stock's profile, recommend the optimal options strategy.

## Stock: {symbol}
Price: ${current_price:.2f}
Trend: {trend_direction}
IV Rank: {iv_rank:.0f}%
Days to Earnings: {days_to_earnings}
AI Conviction: {conviction}/10
Market Regime: {market_regime}

## Available LEAPS
{leaps_options}

## Risk Parameters
Max Position Size: {max_position_pct}% of portfolio
Risk Tolerance: {risk_tolerance}

Think through:
1. Given the conviction level and market regime, how aggressive should we be?
2. Is IV favorable for buying options or selling premium?
3. Are earnings a risk to position around?
4. What delta gives the best risk/reward?

Respond with ONLY this JSON (no markdown):
{{
    "strategy": "<Long Call | Bull Call Spread | LEAPS Diagonal | Put Credit Spread | Calendar Spread | Wait>",
    "strike": <strike price as number>,
    "delta": <target delta 0.0-1.0>,
    "expiration_dte": <days to expiry>,
    "entry_price_estimate": <option price estimate>,
    "contracts": <suggested number based on position sizing>,
    "max_risk": <max dollar risk>,
    "profit_target_pct": <target % gain>,
    "stop_loss_pct": <stop % loss>,
    "time_stop_dte": <roll if below this DTE>,
    "reasoning": "<2-3 sentence explanation>",
    "confidence": <1-10>
}}"""


# =============================================================================
# BATCH ANALYSIS PROMPTS
# =============================================================================

BATCH_ANALYSIS_PROMPT = """Analyze these screening results and rank the opportunities.

## Screening Results
Total Stocks Screened: {total_screened}
Passed All Filters: {total_passed}
Current Market Regime: {market_regime}

## Top Candidates
{candidates_summary}

Analyze these candidates considering:
1. Which have the best risk/reward given current market?
2. Are there any sector concentrations to be aware of?
3. Which have upcoming catalysts?
4. What's the overall quality of this batch?

Respond with ONLY this JSON (no markdown):
{{
    "batch_quality": "<poor | fair | good | excellent>",
    "top_picks": [
        {{
            "symbol": "<ticker>",
            "conviction": <1-10>,
            "reasoning": "<one line>"
        }}
    ],
    "themes": ["<common pattern 1>", "<common pattern 2>"],
    "concerns": ["<red flag if any>"],
    "action_items": ["<what to do next>"],
    "summary": "<2 sentence executive summary>"
}}"""


BATCH_SUMMARY_PROMPT = """Summarize these {count} stocks for a quick portfolio overview.

{stocks_data}

Provide ONLY this JSON:
{{
    "sector_breakdown": {{"<sector>": <count>}},
    "avg_conviction": <average 1-10>,
    "top_3": ["<symbol1>", "<symbol2>", "<symbol3>"],
    "diversification_score": <1-10>,
    "overall_outlook": "<bullish | neutral | bearish>",
    "summary": "<one sentence>"
}}"""


# =============================================================================
# EXPLANATION PROMPTS
# =============================================================================

EXPLAIN_SCORE_PROMPT = """Explain why {symbol} received a composite score of {score:.0f}/100.

## Score Breakdown
- Fundamental: {fundamental_score:.0f}/100 (weight: 40%)
- Technical: {technical_score:.0f}/100 (weight: 30%)
- Options: {options_score:.0f}/100 (weight: 20%)
- Momentum: {momentum_score:.0f}/100 (weight: 10%)

## Criteria Results
{criteria_results}

Explain clearly using the actual numbers. Respond with ONLY this JSON:
{{
    "score_drivers": ["<what helped score>", "<what helped score>"],
    "score_detractors": ["<what hurt score>", "<what hurt score>"],
    "improvement_needed": ["<what would raise score>"],
    "bottom_line": "<one sentence assessment>"
}}"""


EXPLAIN_FAILURE_PROMPT = """Explain why {symbol} failed the screening process.

## Failure Point
Failed at: {failed_at}
Threshold: {threshold}
Actual Value: {actual_value}

## Available Data
{available_data}

Respond with ONLY this JSON:
{{
    "failure_reason": "<clear explanation>",
    "how_close": "<how far from passing>",
    "what_would_pass": "<specific change needed>",
    "worth_watching": <true | false>,
    "watch_reason": "<why or why not>"
}}"""


# =============================================================================
# RISK ASSESSMENT PROMPTS
# =============================================================================

RISK_ASSESSMENT_PROMPT = """Assess the key risks for this options position.

## Position
Stock: {symbol}
Strategy: {strategy}
Delta: {delta}
DTE: {dte}
Cost Basis: ${cost}

## Stock Context
{stock_context}

## Market Context
{market_context}

Think through all risk dimensions:
1. Stock-specific risks (earnings, competition, sector headwinds)
2. Options-specific risks (theta decay, IV crush, gamma risk)
3. Market risks (regime change, correlation breakdown)
4. Execution risks (liquidity, slippage)

Respond with ONLY this JSON:
{{
    "overall_risk": "<low | moderate | high | very_high>",
    "risks": [
        {{
            "risk": "<description>",
            "likelihood": "<low | medium | high>",
            "impact": "<low | medium | high>",
            "mitigation": "<how to reduce>"
        }}
    ],
    "max_loss_scenario": "<worst case description>",
    "position_size_recommendation": "<full | half | quarter | avoid>"
}}"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_fundamentals_summary(fundamentals: dict) -> str:
    """Format fundamentals dict into readable summary."""
    lines = []

    if fundamentals.get('revenue_growth'):
        lines.append(f"- Revenue Growth: {fundamentals['revenue_growth']*100:.1f}%")
    if fundamentals.get('earnings_growth'):
        lines.append(f"- Earnings Growth: {fundamentals['earnings_growth']*100:.1f}%")
    if fundamentals.get('profit_margins'):
        lines.append(f"- Profit Margin: {fundamentals['profit_margins']*100:.1f}%")
    if fundamentals.get('debt_to_equity') is not None:
        lines.append(f"- Debt/Equity: {fundamentals['debt_to_equity']:.0f}%")
    if fundamentals.get('roe'):
        lines.append(f"- ROE: {fundamentals['roe']*100:.1f}%")
    if fundamentals.get('pe_ratio'):
        lines.append(f"- P/E Ratio: {fundamentals['pe_ratio']:.1f}")
    if fundamentals.get('forward_pe'):
        lines.append(f"- Forward P/E: {fundamentals['forward_pe']:.1f}")
    if fundamentals.get('peg_ratio'):
        lines.append(f"- PEG Ratio: {fundamentals['peg_ratio']:.2f}")

    return '\n'.join(lines) if lines else "Limited fundamental data available"


def format_technical_summary(indicators: dict) -> str:
    """Format technical indicators into readable summary."""
    lines = []

    if indicators.get('rsi_14'):
        rsi = indicators['rsi_14']
        status = "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral"
        lines.append(f"- RSI(14): {rsi:.1f} ({status})")

    if indicators.get('sma_20') and indicators.get('sma_50'):
        trend = "Bullish" if indicators['sma_20'] > indicators['sma_50'] else "Bearish"
        lines.append(f"- SMA 20/50: {trend} crossover")

    if indicators.get('sma_200'):
        lines.append(f"- SMA 200: ${indicators['sma_200']:.2f}")

    if indicators.get('macd') and indicators.get('macd_signal'):
        macd_status = "Bullish" if indicators['macd'] > indicators['macd_signal'] else "Bearish"
        lines.append(f"- MACD: {macd_status}")

    if indicators.get('atr_14'):
        lines.append(f"- ATR(14): ${indicators['atr_14']:.2f}")

    if indicators.get('bb_position'):
        bb = indicators['bb_position']
        bb_status = "Near upper" if bb > 0.8 else "Near lower" if bb < 0.2 else "Middle"
        lines.append(f"- Bollinger: {bb_status} band")

    return '\n'.join(lines) if lines else "Limited technical data available"


def format_leaps_summary(leaps: dict) -> str:
    """Format LEAPS summary into readable text."""
    if not leaps:
        return "No LEAPS data available"

    lines = []

    if leaps.get('available_expirations'):
        lines.append(f"- Expirations: {len(leaps['available_expirations'])} available")
    if leaps.get('min_dte'):
        lines.append(f"- DTE Range: {leaps['min_dte']} - {leaps.get('max_dte', 'N/A')} days")
    if leaps.get('iv_rank') is not None:
        iv_status = "Low" if leaps['iv_rank'] < 30 else "High" if leaps['iv_rank'] > 70 else "Moderate"
        lines.append(f"- IV Rank: {leaps['iv_rank']:.0f}% ({iv_status})")
    if leaps.get('atm_call_premium'):
        lines.append(f"- ATM Call Premium: ${leaps['atm_call_premium']:.2f}")
    if leaps.get('open_interest'):
        lines.append(f"- Open Interest: {leaps['open_interest']:,}")
    if leaps.get('bid_ask_spread_pct'):
        spread = leaps['bid_ask_spread_pct']
        liquidity = "Good" if spread < 5 else "Poor" if spread > 15 else "Fair"
        lines.append(f"- Bid/Ask Spread: {spread:.1f}% ({liquidity} liquidity)")

    return '\n'.join(lines) if lines else "Limited LEAPS data available"


def format_market_cap(market_cap: float) -> str:
    """Format market cap into readable string."""
    if not market_cap:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap/1e12:.2f}T"
    elif market_cap >= 1e9:
        return f"${market_cap/1e9:.2f}B"
    elif market_cap >= 1e6:
        return f"${market_cap/1e6:.0f}M"
    else:
        return f"${market_cap:,.0f}"


def format_stocks_for_batch(stocks: List[Dict[str, Any]]) -> str:
    """Format a list of stocks for batch analysis prompt."""
    if not stocks:
        return "No stocks to analyze"

    lines = []
    for i, stock in enumerate(stocks[:10], 1):  # Limit to top 10
        symbol = stock.get('symbol', 'N/A')
        score = stock.get('score', 0)
        sector = stock.get('sector', 'N/A')
        price = stock.get('current_price', 0)
        conviction = stock.get('ai_conviction', 'N/A')

        lines.append(
            f"{i}. {symbol}: Score {score:.0f} | ${price:.2f} | {sector} | "
            f"Conviction: {conviction}"
        )

    return '\n'.join(lines)


def format_candidates_summary(candidates: List[Dict[str, Any]]) -> str:
    """Format screening candidates for batch analysis."""
    if not candidates:
        return "No candidates to summarize"

    lines = []
    for stock in candidates[:15]:  # Top 15
        symbol = stock.get('symbol', 'N/A')
        score = stock.get('score', 0)
        fund_score = stock.get('fundamental_score', 0)
        tech_score = stock.get('technical_score', 0)
        sector = stock.get('sector', 'N/A')
        price = stock.get('current_price', 0)

        lines.append(
            f"- {symbol} ({sector}): ${price:.2f} | "
            f"Score: {score:.0f} (F:{fund_score:.0f}/T:{tech_score:.0f})"
        )

    return '\n'.join(lines)


def get_system_prompt(prompt_type: str = "trading") -> str:
    """Get the appropriate system prompt."""
    if prompt_type == "market":
        return SYSTEM_PROMPT_MARKET_ANALYST
    return SYSTEM_PROMPT_TRADING_ANALYST
