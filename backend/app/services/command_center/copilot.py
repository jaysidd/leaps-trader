"""
AI Copilot Service - Provides intelligent assistance for the Command Center
including morning briefs, metric explanations, and interactive chat
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger

from app.config import get_settings
from app.services.cache import cache
from app.services.ai.claude_service import get_claude_service, AnalysisResult


# =============================================================================
# COPILOT PROMPTS
# =============================================================================

MORNING_BRIEF_PROMPT = """
You are a professional trading analyst providing a morning brief for an options trader.
Based on the current market data, provide a concise, actionable morning brief.

CURRENT MARKET CONDITIONS:
{market_data}

PREDICTION MARKETS:
{polymarket_data}

NEWS CATALYSTS:
{news_data}

Generate a morning brief in this JSON format:
{{
    "greeting": "Good morning! Here's your market brief for {date}",
    "market_summary": "2-3 sentences about overall market conditions",
    "key_insight": "The most important thing to know today",
    "opportunities": ["List of 2-3 potential trading opportunities or setups to watch"],
    "risks": ["List of 2-3 risks or caution points"],
    "strategy_bias": "bullish/bearish/neutral - current market favors which approach",
    "recommended_focus": "What type of setups to look for today (e.g., 'LEAPS on pullbacks' or 'Swing trades on momentum')"
}}

Keep the tone professional but conversational. Focus on actionable insights.
"""

METRIC_EXPLANATION_PROMPT = """
You are a trading educator helping a trader understand financial metrics.
Explain the following metric in simple terms, with practical trading implications.

METRIC: {metric_name}
CURRENT VALUE: {metric_value}
CONTEXT: {context}

Provide explanation in this JSON format:
{{
    "definition": "Simple 1-2 sentence definition",
    "current_interpretation": "What the current value means",
    "trading_implication": "How this affects trading decisions",
    "historical_context": "How this compares to historical norms",
    "action_hint": "What a trader might consider doing based on this"
}}

Keep explanations clear and practical, avoiding jargon where possible.
"""

CHAT_SYSTEM_PROMPT = """
You are an AI trading assistant integrated into a LEAPS options trading platform.
You help traders understand market conditions, analyze stocks, and make better trading decisions.

Your capabilities:
- Explain market metrics and indicators
- Analyze stock fundamentals and technicals
- Provide options strategy recommendations
- Help interpret news and events
- Answer questions about trading concepts

Guidelines:
- Be concise and actionable
- Use plain language, avoid unnecessary jargon
- When uncertain, say so
- Always consider risk management
- Reference specific data when available
- Support both LEAPS (long-term) and swing (short-term) trading styles

Current context: The user is viewing a Command Center dashboard with market data, news, and prediction markets.
"""

STOCK_DETAIL_ANALYSIS_PROMPT = """
You are analyzing a stock for an options trader. Provide a comprehensive but concise analysis.

STOCK DATA:
{stock_data}

MARKET CONTEXT:
{market_context}

Provide analysis in this JSON format:
{{
    "summary": "2-3 sentence executive summary",
    "bull_case": ["3 key bullish points"],
    "bear_case": ["3 key bearish points"],
    "options_view": {{
        "leaps_suitable": true/false,
        "swing_suitable": true/false,
        "preferred_strategy": "description of best approach",
        "suggested_delta": "0.XX-0.XX range",
        "suggested_dte": "XX-XXX days"
    }},
    "key_levels": {{
        "support": "price level",
        "resistance": "price level"
    }},
    "catalyst_timeline": "upcoming events that could move the stock",
    "conviction": 1-10,
    "action": "BUY/WAIT/AVOID with brief reasoning"
}}
"""


class CopilotService:
    """
    AI Copilot for the Command Center.
    Provides morning briefs, metric explanations, and interactive assistance.
    """

    def __init__(self):
        self.settings = get_settings()
        self._claude_service = None

    def _get_claude(self):
        """Get Claude service instance"""
        if self._claude_service is None:
            self._claude_service = get_claude_service()
            if not self._claude_service.is_available():
                self._claude_service.initialize()
        return self._claude_service

    def is_available(self) -> bool:
        """Check if AI service is available"""
        claude = self._get_claude()
        return claude.is_available()

    # -------------------------------------------------------------------------
    # MORNING BRIEF
    # -------------------------------------------------------------------------

    async def generate_morning_brief(
        self,
        market_data: Dict[str, Any],
        polymarket_data: Dict[str, Any],
        news_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate AI-powered morning brief based on current market conditions.
        """
        # Cache key based on 15-minute windows so the brief stays fresh
        now = datetime.now()
        quarter = now.minute // 15
        cache_key = f"copilot:morning_brief:{now.strftime('%Y-%m-%d-%H')}:{quarter}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        claude = self._get_claude()
        if not claude.is_available():
            return self._get_fallback_brief(market_data)

        try:
            # Format market data for prompt
            market_summary = self._format_market_data(market_data)
            polymarket_summary = self._format_polymarket_data(polymarket_data)
            news_summary = self._format_news_data(news_data)

            prompt = MORNING_BRIEF_PROMPT.format(
                market_data=market_summary,
                polymarket_data=polymarket_summary,
                news_data=news_summary,
                date=datetime.now().strftime('%B %d, %Y'),
            )

            response_text, usage = await claude._call_claude(
                prompt,
                system_prompt=CHAT_SYSTEM_PROMPT,
                max_tokens=800,
                temperature=0.7,
            )

            if response_text:
                parsed = claude.parser.extract_json(response_text)
                if parsed:
                    result = {
                        'success': True,
                        'brief': parsed,
                        'generated_at': datetime.now().isoformat(),
                        'ai_powered': True,
                    }
                    # Cache for 15 minutes
                    cache.set(cache_key, result, ttl=900)
                    return result

            return self._get_fallback_brief(market_data)

        except Exception as e:
            logger.error(f"Error generating morning brief: {e}")
            return self._get_fallback_brief(market_data)

    def _get_fallback_brief(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a rule-based fallback brief when AI is unavailable.
        """
        # Extract key metrics
        indices = market_data.get('indices', [])
        fear_greed = market_data.get('fear_greed', {})
        volatility = market_data.get('volatility', {})

        spy = next((i for i in indices if i['symbol'] == 'SPY'), {})
        spy_change = spy.get('change_percent', 0)
        fg_score = fear_greed.get('value', 50)
        vix = volatility.get('vix', {}).get('value', 20)

        # Determine bias
        if spy_change > 0.5 and fg_score > 55:
            bias = 'bullish'
            summary = f"Markets are positive with SPY up {spy_change:.1f}%. Sentiment is in {fear_greed.get('rating', 'neutral')} territory."
        elif spy_change < -0.5 and fg_score < 45:
            bias = 'bearish'
            summary = f"Markets are under pressure with SPY down {abs(spy_change):.1f}%. Sentiment shows {fear_greed.get('rating', 'fear')}."
        else:
            bias = 'neutral'
            summary = f"Markets are mixed today. SPY is {'up' if spy_change > 0 else 'down'} {abs(spy_change):.1f}%."

        return {
            'success': True,
            'brief': {
                'greeting': f"Good {'morning' if datetime.now().hour < 12 else 'afternoon'}! Here's your market overview.",
                'market_summary': summary,
                'key_insight': f"VIX at {vix:.1f} indicates {'elevated' if vix > 20 else 'normal'} volatility expectations.",
                'opportunities': [
                    f"{'Look for entry points on pullbacks' if bias == 'bullish' else 'Consider defensive positions'}",
                ],
                'risks': [
                    f"{'Complacency risk if VIX stays low' if vix < 15 else 'Volatility could increase'}",
                ],
                'strategy_bias': bias,
                'recommended_focus': 'Wait for clearer signals' if bias == 'neutral' else f"{bias.title()} setups",
            },
            'generated_at': datetime.now().isoformat(),
            'ai_powered': False,
        }

    def _format_market_data(self, data: Dict[str, Any]) -> str:
        """Format market data for AI prompt"""
        lines = []

        # Indices
        indices = data.get('indices', [])
        for idx in indices:
            lines.append(f"- {idx['name']}: {idx['price']:.2f} ({idx['change_percent']:+.2f}%)")

        # Fear & Greed
        fg = data.get('fear_greed', {})
        if fg:
            lines.append(f"- Fear & Greed Index: {fg.get('value', 50)} ({fg.get('rating', 'Neutral')})")

        # VIX
        vol = data.get('volatility', {})
        if 'vix' in vol:
            vix = vol['vix']
            lines.append(f"- VIX: {vix.get('value', 20):.1f} ({vix.get('level', 'normal')})")

        # Sectors
        sectors = data.get('sectors', {}).get('leading', [])
        if sectors:
            top_sector = sectors[0]
            lines.append(f"- Leading Sector: {top_sector['name']} ({top_sector['change_percent']:+.2f}%)")

        return '\n'.join(lines)

    def _format_polymarket_data(self, data: Dict[str, Any]) -> str:
        """Format Polymarket data for AI prompt"""
        items = data.get('items', [])
        lines = []

        for item in items[:4]:
            change_str = f" ({item['change']:+.1f}%)" if item.get('change') else ""
            lines.append(f"- {item['label']}: {item['value']}{change_str}")

        return '\n'.join(lines) if lines else "No prediction market data available"

    def _format_news_data(self, data: Dict[str, Any]) -> str:
        """Format news data for AI prompt"""
        feed = data.get('feed', [])
        lines = []

        for item in feed[:5]:
            impact = f"[{item['impact'].upper()}]" if item.get('impact') else ""
            lines.append(f"- {impact} {item['title']}")

        return '\n'.join(lines) if lines else "No significant news catalysts"

    # -------------------------------------------------------------------------
    # METRIC EXPLANATIONS
    # -------------------------------------------------------------------------

    async def explain_metric(
        self,
        metric_name: str,
        metric_value: Any,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Get AI explanation for a specific metric.
        Used for hover tooltips and learning features.
        """
        cache_key = f"copilot:explain:{metric_name}:{str(metric_value)[:20]}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        claude = self._get_claude()
        if not claude.is_available():
            return self._get_fallback_explanation(metric_name, metric_value)

        try:
            prompt = METRIC_EXPLANATION_PROMPT.format(
                metric_name=metric_name,
                metric_value=metric_value,
                context=context or "General market analysis",
            )

            response_text, usage = await claude._call_claude(
                prompt,
                model=self.settings.CLAUDE_MODEL_FAST,  # Use fast model for tooltips
                max_tokens=400,
                temperature=0.3,
            )

            if response_text:
                parsed = claude.parser.extract_json(response_text)
                if parsed:
                    result = {
                        'success': True,
                        'explanation': parsed,
                        'ai_powered': True,
                    }
                    # Cache for 24 hours (definitions don't change)
                    cache.set(cache_key, result, ttl=86400)
                    return result

            return self._get_fallback_explanation(metric_name, metric_value)

        except Exception as e:
            logger.error(f"Error explaining metric {metric_name}: {e}")
            return self._get_fallback_explanation(metric_name, metric_value)

    def _get_fallback_explanation(self, metric_name: str, metric_value: Any) -> Dict[str, Any]:
        """
        Return pre-defined explanations for common metrics.
        """
        explanations = {
            'vix': {
                'definition': 'The VIX measures expected market volatility over the next 30 days.',
                'current_interpretation': f'At {metric_value}, volatility is {"elevated" if float(metric_value) > 20 else "normal"}.',
                'trading_implication': 'High VIX can mean cheaper stocks but expensive options.',
                'action_hint': 'Consider selling premium when VIX is high.',
            },
            'fear_greed': {
                'definition': 'CNN Fear & Greed Index measures market sentiment from 0 (extreme fear) to 100 (extreme greed).',
                'current_interpretation': f'At {metric_value}, sentiment is {"fearful" if float(metric_value) < 40 else "greedy" if float(metric_value) > 60 else "neutral"}.',
                'trading_implication': 'Extreme readings often signal potential reversals.',
                'action_hint': '"Be greedy when others are fearful."',
            },
            'rsi': {
                'definition': 'Relative Strength Index measures momentum on a 0-100 scale.',
                'current_interpretation': f'At {metric_value}, the stock is {"oversold" if float(metric_value) < 30 else "overbought" if float(metric_value) > 70 else "neutral"}.',
                'trading_implication': 'Extreme RSI can indicate potential reversal points.',
                'action_hint': 'Look for RSI divergences for better entry timing.',
            },
            'iv_rank': {
                'definition': 'IV Rank shows current implied volatility relative to its 52-week range.',
                'current_interpretation': f'At {metric_value}%, IV is {"high" if float(metric_value) > 50 else "low"} compared to the past year.',
                'trading_implication': 'Low IV Rank is better for buying options; high for selling.',
                'action_hint': 'LEAPS are cheaper when IV Rank is low.',
            },
            'delta': {
                'definition': 'Delta measures how much an option price changes per $1 move in the stock.',
                'current_interpretation': f'A delta of {metric_value} means the option moves ${float(metric_value):.2f} per $1 stock move.',
                'trading_implication': 'Higher delta = more stock-like behavior, lower risk.',
                'action_hint': 'LEAPS typically work best with 0.60-0.80 delta.',
            },
        }

        metric_key = metric_name.lower().replace(' ', '_')
        if metric_key in explanations:
            return {
                'success': True,
                'explanation': explanations[metric_key],
                'ai_powered': False,
            }

        return {
            'success': True,
            'explanation': {
                'definition': f'{metric_name} is a trading metric.',
                'current_interpretation': f'Current value is {metric_value}.',
                'trading_implication': 'Consider this metric in your analysis.',
                'action_hint': 'Research this metric for better understanding.',
            },
            'ai_powered': False,
        }

    # -------------------------------------------------------------------------
    # INTERACTIVE CHAT
    # -------------------------------------------------------------------------

    async def chat(
        self,
        message: str,
        context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Interactive chat with the AI copilot.
        Supports context-aware conversations about market data.
        """
        claude = self._get_claude()
        if not claude.is_available():
            return {
                'success': False,
                'error': 'AI service not available. Please configure ANTHROPIC_API_KEY in settings.',
                'response': None,
            }

        try:
            # Build context-enhanced prompt
            context_str = ""
            if context:
                context_str = f"\n\nCurrent context:\n{self._format_chat_context(context)}\n\n"

            # Build conversation history
            history_str = ""
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages
                    role = "User" if msg['role'] == 'user' else "Assistant"
                    history_str += f"{role}: {msg['content']}\n"

            full_prompt = f"{context_str}{history_str}User: {message}"

            response_text, usage = await claude._call_claude(
                full_prompt,
                system_prompt=CHAT_SYSTEM_PROMPT,
                model=self.settings.CLAUDE_MODEL_ADVANCED,
                max_tokens=1000,
                temperature=0.7,
            )

            if response_text:
                return {
                    'success': True,
                    'response': response_text,
                    'usage': {
                        'input_tokens': usage.input_tokens if usage else 0,
                        'output_tokens': usage.output_tokens if usage else 0,
                    }
                }

            return {
                'success': False,
                'error': 'No response from AI',
                'response': None,
            }

        except Exception as e:
            logger.error(f"Error in copilot chat: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': None,
            }

    def _format_chat_context(self, context: Dict[str, Any]) -> str:
        """Format context for chat prompt"""
        lines = []

        if 'current_page' in context:
            lines.append(f"User is viewing: {context['current_page']}")

        if 'selected_stock' in context:
            stock = context['selected_stock']
            lines.append(f"Selected stock: {stock.get('symbol')} at ${stock.get('price', 'N/A')}")

        if 'market_summary' in context:
            ms = context['market_summary']
            lines.append(f"Market condition: {ms.get('market_condition', {}).get('status', 'unknown')}")

        return '\n'.join(lines)

    # -------------------------------------------------------------------------
    # STOCK DETAIL ANALYSIS
    # -------------------------------------------------------------------------

    async def analyze_stock_detail(
        self,
        stock_data: Dict[str, Any],
        market_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive AI analysis for a stock detail page.
        """
        symbol = stock_data.get('symbol', 'UNKNOWN')
        cache_key = f"copilot:stock_analysis:{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        claude = self._get_claude()
        if not claude.is_available():
            return {
                'success': False,
                'error': 'AI service not available',
                'analysis': None,
            }

        try:
            # Format stock data
            stock_str = self._format_stock_data(stock_data)
            context_str = self._format_market_context(market_context) if market_context else "No market context provided"

            prompt = STOCK_DETAIL_ANALYSIS_PROMPT.format(
                stock_data=stock_str,
                market_context=context_str,
            )

            response_text, usage = await claude._call_claude(
                prompt,
                system_prompt=CHAT_SYSTEM_PROMPT,
                model=self.settings.CLAUDE_MODEL_ADVANCED,
                max_tokens=1200,
                temperature=0.5,
            )

            if response_text:
                parsed = claude.parser.extract_json(response_text)
                if parsed:
                    result = {
                        'success': True,
                        'analysis': parsed,
                        'symbol': symbol,
                        'generated_at': datetime.now().isoformat(),
                        'ai_powered': True,
                    }
                    # Cache for 30 minutes
                    cache.set(cache_key, result, ttl=1800)
                    return result

            return {
                'success': False,
                'error': 'Failed to parse AI response',
                'analysis': None,
            }

        except Exception as e:
            logger.error(f"Error analyzing stock {symbol}: {e}")
            return {
                'success': False,
                'error': str(e),
                'analysis': None,
            }

    def _format_stock_data(self, data: Dict[str, Any]) -> str:
        """Format stock data for AI prompt"""
        lines = [
            f"Symbol: {data.get('symbol', 'N/A')}",
            f"Name: {data.get('name', 'N/A')}",
            f"Price: ${data.get('current_price', 'N/A')}",
            f"Sector: {data.get('sector', 'N/A')}",
        ]

        # Fundamentals
        if data.get('fundamentals'):
            f = data['fundamentals']
            lines.append(f"\nFundamentals:")
            lines.append(f"- Market Cap: ${f.get('market_cap', 'N/A'):,}" if f.get('market_cap') else "- Market Cap: N/A")
            lines.append(f"- P/E Ratio: {f.get('trailing_pe', 'N/A')}")
            lines.append(f"- Revenue Growth: {f.get('revenue_growth', 'N/A')}")

        # Technical
        if data.get('technical_indicators'):
            t = data['technical_indicators']
            lines.append(f"\nTechnicals:")
            lines.append(f"- RSI: {t.get('rsi_14', 'N/A')}")
            lines.append(f"- 50 SMA: {t.get('sma_50', 'N/A')}")
            lines.append(f"- 200 SMA: {t.get('sma_200', 'N/A')}")

        # Options
        if data.get('leaps_summary'):
            o = data['leaps_summary']
            lines.append(f"\nOptions:")
            lines.append(f"- IV Rank: {o.get('iv_rank', 'N/A')}%")
            lines.append(f"- Available LEAPS: {o.get('available_expirations', 'N/A')}")

        return '\n'.join(lines)

    def _format_market_context(self, context: Dict[str, Any]) -> str:
        """Format market context for AI prompt"""
        lines = []

        if context.get('market_condition'):
            lines.append(f"Market Condition: {context['market_condition'].get('status', 'unknown')}")

        if context.get('fear_greed'):
            fg = context['fear_greed']
            lines.append(f"Fear & Greed: {fg.get('value', 50)} ({fg.get('rating', 'Neutral')})")

        if context.get('volatility', {}).get('vix'):
            vix = context['volatility']['vix']
            lines.append(f"VIX: {vix.get('value', 20)}")

        return '\n'.join(lines) if lines else "Normal market conditions"

    # -------------------------------------------------------------------------
    # USAGE STATS
    # -------------------------------------------------------------------------

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get AI usage statistics"""
        claude = self._get_claude()
        if claude.is_available():
            return claude.get_usage_stats()
        return {
            'available': False,
            'error': 'AI service not configured',
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_copilot_service: Optional[CopilotService] = None


def get_copilot_service() -> CopilotService:
    """Get the global CopilotService instance."""
    global _copilot_service
    if _copilot_service is None:
        _copilot_service = CopilotService()
    return _copilot_service
