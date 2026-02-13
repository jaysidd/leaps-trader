"""
Claude AI Analysis Service - Intelligent stock analysis using Anthropic's Claude

Enhanced with:
- Cost tracking and daily budget limits
- Response validation and JSON parsing
- Caching with configurable TTLs
- Retry logic with exponential backoff
- System prompts for consistent persona
"""

import json
import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from loguru import logger

try:
    import anthropic
    from anthropic import APIError, RateLimitError as AnthropicRateLimitError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Run: pip install anthropic")

from app.config import get_settings
from app.services.ai.prompts import (
    STOCK_ANALYSIS_PROMPT,
    QUICK_SCAN_PROMPT,
    OPTIONS_STRATEGY_PROMPT,
    EXPLAIN_SCORE_PROMPT,
    EXPLAIN_FAILURE_PROMPT,
    BATCH_ANALYSIS_PROMPT,
    MARKET_REGIME_PROMPT,
    RISK_ASSESSMENT_PROMPT,
    format_fundamentals_summary,
    format_technical_summary,
    format_leaps_summary,
    format_market_cap,
    format_candidates_summary,
    get_system_prompt,
    SYSTEM_PROMPT_TRADING_ANALYST,
    SYSTEM_PROMPT_MARKET_ANALYST,
)
from app.services.ai.signal_prompts import (
    SYSTEM_PROMPT_SIGNAL_ANALYST,
    SYSTEM_PROMPT_REGIME_CLASSIFIER,
    build_regime_prompt,
    build_trend_analysis_prompt,
    build_mean_reversion_prompt,
    build_batch_scanner_prompt,
    validate_signal_analysis,
    validate_batch_analysis,
)


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
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s" if retry_after
            else "Rate limit exceeded"
        )


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
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def get_estimated_cost(self, input_cost_per_1k: float, output_cost_per_1k: float) -> float:
        """Calculate estimated cost based on token rates."""
        return (
            (self.input_tokens / 1000) * input_cost_per_1k +
            (self.output_tokens / 1000) * output_cost_per_1k
        )


@dataclass
class CostTracker:
    """Track daily API costs."""
    daily_costs: Dict[str, float] = field(default_factory=dict)
    daily_requests: Dict[str, int] = field(default_factory=dict)
    daily_tokens: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def _get_today(self) -> str:
        return datetime.now().date().isoformat()

    def add_usage(self, usage: TokenUsage, cost: float) -> float:
        """Record token usage and return cost."""
        today = self._get_today()

        # Initialize if new day
        if today not in self.daily_costs:
            self.daily_costs = {today: 0.0}
            self.daily_requests = {today: 0}
            self.daily_tokens = {today: {'input': 0, 'output': 0}}

        self.daily_costs[today] += cost
        self.daily_requests[today] += 1
        self.daily_tokens[today]['input'] += usage.input_tokens
        self.daily_tokens[today]['output'] += usage.output_tokens

        logger.debug(
            f"API call: {usage.input_tokens} in, {usage.output_tokens} out, "
            f"${cost:.4f} (daily total: ${self.daily_costs[today]:.4f})"
        )

        return cost

    def get_daily_cost(self) -> float:
        """Get today's total cost."""
        return self.daily_costs.get(self._get_today(), 0.0)

    def get_daily_requests(self) -> int:
        """Get today's request count."""
        return self.daily_requests.get(self._get_today(), 0)

    def get_daily_tokens(self) -> Dict[str, int]:
        """Get today's token usage."""
        return self.daily_tokens.get(self._get_today(), {'input': 0, 'output': 0})

    def check_budget(self, budget: float) -> bool:
        """Check if within daily budget."""
        return self.get_daily_cost() < budget

    def get_remaining_budget(self, budget: float) -> float:
        """Get remaining daily budget."""
        return max(0, budget - self.get_daily_cost())


@dataclass
class CachedResponse:
    """Cached API response with timestamp."""
    data: Dict[str, Any]
    timestamp: datetime

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry has expired."""
        return (datetime.now() - self.timestamp).total_seconds() > ttl_seconds


@dataclass
class AnalysisResult:
    """Standardized result from AI analysis."""
    success: bool
    data: Optional[Dict[str, Any]] = None
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
    def extract_json(response_text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from Claude's response, handling markdown code blocks.
        """
        # Try to find JSON in code blocks first
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON (starts with { or [)
            json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                return None

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common issues
            json_str = json_str.replace("'", '"')  # Single to double quotes
            json_str = re.sub(r',\s*}', '}', json_str)  # Trailing commas in objects
            json_str = re.sub(r',\s*]', ']', json_str)  # Trailing commas in arrays
            json_str = re.sub(r':\s*\.(\d)', r': 0.\1', json_str)  # Fix .5 -> 0.5
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None

    @staticmethod
    def validate_stock_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize stock analysis response."""
        # Ensure conviction score is 1-10
        if 'conviction' in data:
            data['conviction'] = max(1, min(10, int(data.get('conviction', 5))))

        # Ensure required fields exist with defaults
        defaults = {
            'bull_case': [],
            'bear_case': [],
            'strategy': {'type': 'Wait', 'reasoning': 'Needs review'},
            'catalyst': 'No specific catalyst identified',
            'summary': 'Analysis pending'
        }

        for key, default in defaults.items():
            if key not in data:
                data[key] = default

        return data

    @staticmethod
    def validate_market_regime(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize market regime response."""
        # Normalize regime value
        valid_regimes = ['bullish', 'bearish', 'neutral', 'volatile']
        if 'regime' in data:
            if data['regime'].lower() not in valid_regimes:
                data['regime'] = 'neutral'
            else:
                data['regime'] = data['regime'].lower()

        # Ensure confidence is 1-10
        if 'confidence' in data:
            data['confidence'] = max(1, min(10, int(data.get('confidence', 5))))

        # Ensure delta/dte recommendations are lists
        if 'delta_recommendation' in data:
            if not isinstance(data['delta_recommendation'], list):
                data['delta_recommendation'] = [0.5, 0.7]

        if 'dte_recommendation' in data:
            if not isinstance(data['dte_recommendation'], list):
                data['dte_recommendation'] = [90, 180]

        return data

    @staticmethod
    def validate_strategy(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate strategy recommendation response."""
        # Ensure required fields
        if 'strategy' not in data:
            data['strategy'] = 'Wait'

        if 'confidence' in data:
            data['confidence'] = max(1, min(10, int(data.get('confidence', 5))))

        return data


# =============================================================================
# MAIN SERVICE CLASS
# =============================================================================

class ClaudeAnalysisService:
    """
    AI-powered analysis service using Claude.

    This service handles all interactions with the Claude API,
    including caching, cost tracking, and response parsing.
    """

    # Token costs per 1K by model tier
    MODEL_COSTS = {
        "sonnet": {"input": 0.003, "output": 0.015},     # Sonnet 4: $3/$15 per 1M
        "haiku":  {"input": 0.0008, "output": 0.004},    # Haiku 3.5: $0.80/$4 per 1M
        "opus":   {"input": 0.015, "output": 0.075},     # Opus 4.5: $15/$75 per 1M
    }
    DEFAULT_INPUT_COST_PER_1K = 0.003  # fallback
    DEFAULT_OUTPUT_COST_PER_1K = 0.015  # fallback
    DEFAULT_DAILY_BUDGET = 10.0  # $10 default daily budget

    def __init__(self):
        self.client: Optional[anthropic.Anthropic] = None
        self.settings = get_settings()
        self._available = False

        # Cost tracking
        self.cost_tracker = CostTracker()
        self.parser = ResponseParser()

        # Cache configuration (TTL in seconds)
        self._cache: Dict[str, CachedResponse] = {}
        self._cache_ttl = {
            'market_regime': 900,    # 15 minutes
            'stock_analysis': 1800,  # 30 minutes
            'batch_analysis': 1800,  # 30 minutes
            'quick_scan': 600,       # 10 minutes
            'signal_analysis': 1800, # 30 minutes
            'signal_batch': 1800,    # 30 minutes
        }

        # Retry configuration
        self._max_retries = 3
        self._base_retry_delay = 1.0

        # Cost configuration (can be overridden by settings)
        self._input_cost_per_1k = getattr(
            self.settings, 'CLAUDE_COST_PER_1K_INPUT_TOKENS',
            self.DEFAULT_INPUT_COST_PER_1K
        )
        self._output_cost_per_1k = getattr(
            self.settings, 'CLAUDE_COST_PER_1K_OUTPUT_TOKENS',
            self.DEFAULT_OUTPUT_COST_PER_1K
        )
        self._daily_budget = getattr(
            self.settings, 'CLAUDE_DAILY_BUDGET',
            self.DEFAULT_DAILY_BUDGET
        )

    def initialize(self, api_key: str = None) -> bool:
        """Initialize the Claude client."""
        if not ANTHROPIC_AVAILABLE:
            logger.error("anthropic package not available")
            return False

        key = api_key or self.settings.ANTHROPIC_API_KEY
        if not key:
            logger.warning("ANTHROPIC_API_KEY not configured")
            return False

        try:
            self.client = anthropic.Anthropic(api_key=key)
            self._available = True
            logger.info(
                f"Claude AI service initialized successfully "
                f"(primary: {self.settings.CLAUDE_MODEL_PRIMARY}, "
                f"advanced: {self.settings.CLAUDE_MODEL_ADVANCED}, "
                f"fast: {self.settings.CLAUDE_MODEL_FAST}, "
                f"budget: ${self._daily_budget:.2f}/day)"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Claude: {e}")
            return False

    def is_available(self) -> bool:
        """Check if Claude service is available."""
        return self._available and self.client is not None

    # -------------------------------------------------------------------------
    # CORE API METHODS
    # -------------------------------------------------------------------------

    async def _call_claude(
        self,
        prompt: str,
        system_prompt: str = None,
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.5
    ) -> Tuple[Optional[str], Optional[TokenUsage]]:
        """
        Make a call to Claude API with retry logic and cost tracking.

        Returns:
            Tuple of (response_text, token_usage) or (None, None) on failure
        """
        if not self.is_available():
            logger.warning("Claude service not available")
            return None, None

        # Check budget
        if not self.cost_tracker.check_budget(self._daily_budget):
            logger.warning(
                f"Daily budget of ${self._daily_budget:.2f} exceeded. "
                f"Current spend: ${self.cost_tracker.get_daily_cost():.4f}"
            )
            raise BudgetExceededError(
                f"Daily budget exceeded. Spent: ${self.cost_tracker.get_daily_cost():.2f}"
            )

        model = model or self.settings.CLAUDE_MODEL_PRIMARY
        max_tokens = max_tokens or self.settings.CLAUDE_MAX_TOKENS
        system = system_prompt or SYSTEM_PROMPT_TRADING_ANALYST

        last_error = None

        for attempt in range(self._max_retries):
            try:
                # Build messages
                messages = [{"role": "user", "content": prompt}]

                # Make API call
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=messages
                )

                if response.content and len(response.content) > 0:
                    response_text = response.content[0].text

                    # Track usage
                    usage = TokenUsage(
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        model=model
                    )

                    # Calculate and track cost (model-aware)
                    model_tier = "sonnet"  # default
                    if "opus" in model:
                        model_tier = "opus"
                    elif "haiku" in model:
                        model_tier = "haiku"
                    costs = self.MODEL_COSTS.get(model_tier, self.MODEL_COSTS["sonnet"])
                    cost = usage.get_estimated_cost(
                        costs["input"],
                        costs["output"]
                    )
                    self.cost_tracker.add_usage(usage, cost)

                    return response_text, usage

                return None, None

            except AnthropicRateLimitError as e:
                last_error = e
                retry_after = getattr(e, 'retry_after', None) or (2 ** attempt)
                logger.warning(
                    f"Rate limit hit, retrying in {retry_after}s "
                    f"(attempt {attempt + 1}/{self._max_retries})"
                )

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
                    raise AIAnalysisError(
                        f"Claude API error after {self._max_retries} attempts: {e}"
                    )

            except Exception as e:
                logger.error(f"Error calling Claude: {e}")
                return None, None

        raise AIAnalysisError(f"Unexpected error: {last_error}")

    async def call_claude(
        self,
        prompt: str,
        system_prompt: str = None,
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.5
    ) -> Tuple[Optional[str], Optional['TokenUsage']]:
        """
        Public wrapper around _call_claude for use by other services.
        Returns: (response_text, token_usage)
        """
        return await self._call_claude(
            prompt,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _get_cached(self, cache_key: str, cache_type: str) -> Optional[Dict[str, Any]]:
        """Get cached response if valid."""
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            ttl = self._cache_ttl.get(cache_type, 900)
            if not cached.is_expired(ttl):
                logger.debug(f"Cache hit for {cache_key}")
                return cached.data
            else:
                # Remove expired entry
                del self._cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, data: Dict[str, Any]):
        """Cache a response."""
        self._cache[cache_key] = CachedResponse(data=data, timestamp=datetime.now())

    # -------------------------------------------------------------------------
    # STOCK ANALYSIS
    # -------------------------------------------------------------------------

    async def analyze_stock(
        self,
        stock_result: Dict[str, Any],
        market_regime: Dict[str, Any] = None,
        force_refresh: bool = False
    ) -> AnalysisResult:
        """
        Generate comprehensive AI insights for a single stock.

        Args:
            stock_result: Screening result dict with scores and data
            market_regime: Current market regime (optional)
            force_refresh: Bypass cache if True

        Returns:
            AnalysisResult with AI analysis, conviction score, and recommendations
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        symbol = stock_result.get('symbol', 'Unknown')
        cache_key = f"stock_analysis_{symbol}"

        # Check cache
        if not force_refresh:
            cached_data = self._get_cached(cache_key, 'stock_analysis')
            if cached_data:
                return AnalysisResult(success=True, data=cached_data, cached=True)

        try:
            name = stock_result.get('name', symbol)

            # Format regime context
            regime_text = "Unknown"
            if market_regime:
                regime_text = (
                    f"{market_regime.get('regime', 'neutral').title()} | "
                    f"Risk: {market_regime.get('risk_mode', 'mixed')}"
                )

            # Format the prompt
            prompt = STOCK_ANALYSIS_PROMPT.format(
                symbol=symbol,
                name=name,
                sector=stock_result.get('sector', 'Unknown'),
                current_price=stock_result.get('current_price', 0),
                market_cap_formatted=format_market_cap(stock_result.get('market_cap')),
                fundamental_score=stock_result.get('fundamental_score', 0),
                technical_score=stock_result.get('technical_score', 0),
                options_score=stock_result.get('options_score', 0),
                momentum_score=stock_result.get('momentum_score', 0),
                score=stock_result.get('score', 0),
                fundamentals_summary=format_fundamentals_summary(
                    stock_result.get('fundamentals', {})
                ),
                technical_summary=format_technical_summary(
                    stock_result.get('technical_indicators', {})
                ),
                leaps_summary=format_leaps_summary(
                    stock_result.get('leaps_summary', {})
                ),
                market_regime=regime_text
            )

            # Call Claude with Opus 4.5 for deep analysis
            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                model=self.settings.CLAUDE_MODEL_ADVANCED,
                max_tokens=1500,
                temperature=0.5
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            # Try to parse JSON response
            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                # Validate and normalize
                validated_data = self.parser.validate_stock_analysis(parsed_data)
                validated_data['symbol'] = symbol
                validated_data['analyzed_at'] = datetime.now().isoformat()
                validated_data['model'] = self.settings.CLAUDE_MODEL_ADVANCED

                # Cache result
                self._set_cached(cache_key, validated_data)

                return AnalysisResult(
                    success=True,
                    data=validated_data,
                    raw_response=response_text,
                    usage=usage
                )
            else:
                # Fall back to text parsing for conviction
                conviction = self._extract_conviction(response_text)

                result_data = {
                    'symbol': symbol,
                    'analysis': response_text,
                    'conviction': conviction,
                    'analyzed_at': datetime.now().isoformat(),
                    'model': self.settings.CLAUDE_MODEL_ADVANCED
                }

                return AnalysisResult(
                    success=True,
                    data=result_data,
                    raw_response=response_text,
                    usage=usage
                )

        except (BudgetExceededError, RateLimitError) as e:
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error analyzing stock {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def quick_scan(
        self,
        stock_result: Dict[str, Any]
    ) -> AnalysisResult:
        """
        Quick assessment of a stock for LEAPS potential.
        Uses faster model and shorter response.
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        symbol = stock_result.get('symbol', 'Unknown')

        try:
            prompt = QUICK_SCAN_PROMPT.format(
                symbol=symbol,
                current_price=stock_result.get('current_price', 0),
                score=stock_result.get('score', 0),
                iv_rank=stock_result.get('leaps_summary', {}).get('iv_rank', 50),
                fundamental_score=stock_result.get('fundamental_score', 0),
                technical_score=stock_result.get('technical_score', 0)
            )

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                model=self.settings.CLAUDE_MODEL_FAST,
                max_tokens=300,
                temperature=0.3
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                parsed_data['symbol'] = symbol
                return AnalysisResult(
                    success=True,
                    data=parsed_data,
                    raw_response=response_text,
                    usage=usage
                )

            return AnalysisResult(
                success=True,
                data={'symbol': symbol, 'raw': response_text},
                raw_response=response_text,
                usage=usage
            )

        except Exception as e:
            logger.error(f"Error in quick scan for {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))

    # -------------------------------------------------------------------------
    # STRATEGY RECOMMENDATION
    # -------------------------------------------------------------------------

    async def get_strategy_recommendation(
        self,
        stock_result: Dict[str, Any],
        market_regime: Dict[str, Any] = None
    ) -> AnalysisResult:
        """
        Get AI-recommended options strategy for a stock.

        Args:
            stock_result: Screening result dict
            market_regime: Current market regime data

        Returns:
            AnalysisResult with strategy recommendation
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        try:
            symbol = stock_result.get('symbol', 'Unknown')
            leaps = stock_result.get('leaps_summary', {})
            indicators = stock_result.get('technical_indicators', {})

            # Determine trend direction
            trend = "Bullish"
            if indicators.get('sma_20') and indicators.get('sma_50'):
                if indicators['sma_20'] < indicators['sma_50']:
                    trend = "Bearish"
            rsi = indicators.get('rsi_14', 50)
            if rsi < 40:
                trend = "Bearish" if trend == "Bearish" else "Neutral"
            elif rsi > 60:
                trend = "Bullish"

            # Get IV rank
            iv_rank = leaps.get('iv_rank', 50)

            # Calculate conviction from composite score
            conviction = min(10, max(1, round(stock_result.get('score', 50) / 10)))

            prompt = OPTIONS_STRATEGY_PROMPT.format(
                symbol=symbol,
                current_price=stock_result.get('current_price', 0),
                trend_direction=trend,
                iv_rank=iv_rank,
                days_to_earnings=stock_result.get('days_to_earnings', 'Unknown'),
                conviction=conviction,
                market_regime=market_regime.get('regime', 'neutral') if market_regime else 'neutral',
                leaps_options=format_leaps_summary(leaps),
                max_position_pct=5,
                risk_tolerance='moderate'
            )

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                model=self.settings.CLAUDE_MODEL_ADVANCED,
                max_tokens=1000,
                temperature=0.5
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                validated_data = self.parser.validate_strategy(parsed_data)
                validated_data['symbol'] = symbol
                validated_data['conviction'] = conviction
                validated_data['iv_rank'] = iv_rank
                validated_data['trend'] = trend

                return AnalysisResult(
                    success=True,
                    data=validated_data,
                    raw_response=response_text,
                    usage=usage
                )

            return AnalysisResult(
                success=True,
                data={
                    'symbol': symbol,
                    'recommendation': response_text,
                    'conviction': conviction,
                    'iv_rank': iv_rank,
                    'trend': trend
                },
                raw_response=response_text,
                usage=usage
            )

        except Exception as e:
            logger.error(f"Error getting strategy for {stock_result.get('symbol')}: {e}")
            return AnalysisResult(success=False, error=str(e))

    # -------------------------------------------------------------------------
    # BATCH ANALYSIS
    # -------------------------------------------------------------------------

    async def analyze_batch(
        self,
        results: List[Dict[str, Any]],
        market_regime: Dict[str, Any] = None
    ) -> AnalysisResult:
        """
        Summarize multiple screening results.

        Args:
            results: List of screening results
            market_regime: Current market regime

        Returns:
            AnalysisResult with executive summary and top picks
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        if not results:
            return AnalysisResult(success=True, data={'summary': 'No stocks to analyze'})

        try:
            regime_text = "Not analyzed"
            if market_regime:
                regime_text = (
                    f"Regime: {market_regime.get('regime', 'unknown').title()}, "
                    f"Risk Mode: {market_regime.get('risk_mode', 'unknown')}"
                )

            prompt = BATCH_ANALYSIS_PROMPT.format(
                total_screened=len(results) + 50,  # Approximate
                total_passed=len(results),
                candidates_summary=format_candidates_summary(results),
                market_regime=regime_text
            )

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=1500,
                temperature=0.5
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                parsed_data['total_analyzed'] = len(results)
                parsed_data['analyzed_at'] = datetime.now().isoformat()

                return AnalysisResult(
                    success=True,
                    data=parsed_data,
                    raw_response=response_text,
                    usage=usage
                )

            return AnalysisResult(
                success=True,
                data={
                    'summary': response_text,
                    'total_analyzed': len(results)
                },
                raw_response=response_text,
                usage=usage
            )

        except Exception as e:
            logger.error(f"Error analyzing batch: {e}")
            return AnalysisResult(success=False, error=str(e))

    # -------------------------------------------------------------------------
    # EXPLANATION METHODS
    # -------------------------------------------------------------------------

    async def explain_score(self, stock_result: Dict[str, Any]) -> AnalysisResult:
        """
        Explain why a stock received its composite score.
        Uses fast model for quick explanations.
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        try:
            # Format criteria results
            criteria = stock_result.get('fundamental_criteria', {})
            tech_criteria = stock_result.get('technical_criteria', {})

            criteria_text = "Fundamental Criteria:\n"
            for key, passed in criteria.items():
                status = "PASS" if passed else "FAIL"
                criteria_text += f"  - {key}: {status}\n"

            criteria_text += "\nTechnical Criteria:\n"
            for key, passed in tech_criteria.items():
                status = "PASS" if passed else "FAIL"
                criteria_text += f"  - {key}: {status}\n"

            prompt = EXPLAIN_SCORE_PROMPT.format(
                symbol=stock_result.get('symbol', 'Unknown'),
                score=stock_result.get('score', 0),
                fundamental_score=stock_result.get('fundamental_score', 0),
                technical_score=stock_result.get('technical_score', 0),
                options_score=stock_result.get('options_score', 0),
                momentum_score=stock_result.get('momentum_score', 0),
                criteria_results=criteria_text
            )

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                model=self.settings.CLAUDE_MODEL_FAST,
                max_tokens=500,
                temperature=0.3
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                return AnalysisResult(
                    success=True,
                    data=parsed_data,
                    raw_response=response_text,
                    usage=usage
                )

            return AnalysisResult(
                success=True,
                data={'explanation': response_text},
                raw_response=response_text,
                usage=usage
            )

        except Exception as e:
            logger.error(f"Error explaining score: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def explain_failure(
        self,
        symbol: str,
        failed_at: str,
        available_data: Dict[str, Any],
        threshold: str = "N/A",
        actual_value: str = "N/A"
    ) -> AnalysisResult:
        """
        Explain why a stock failed screening.
        Uses fast model.
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        try:
            data_text = json.dumps(available_data, indent=2, default=str)

            prompt = EXPLAIN_FAILURE_PROMPT.format(
                symbol=symbol,
                failed_at=failed_at,
                threshold=threshold,
                actual_value=actual_value,
                available_data=data_text[:2000]  # Limit size
            )

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                model=self.settings.CLAUDE_MODEL_FAST,
                max_tokens=400,
                temperature=0.3
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                return AnalysisResult(
                    success=True,
                    data=parsed_data,
                    raw_response=response_text,
                    usage=usage
                )

            return AnalysisResult(
                success=True,
                data={'explanation': response_text},
                raw_response=response_text,
                usage=usage
            )

        except Exception as e:
            logger.error(f"Error explaining failure: {e}")
            return AnalysisResult(success=False, error=str(e))

    # -------------------------------------------------------------------------
    # SIGNAL DEEP ANALYSIS (Trading Prompt Library)
    # -------------------------------------------------------------------------

    async def analyze_signal(
        self,
        signal_data: Dict[str, Any],
        market_regime: Dict[str, Any] = None,
        iv_rank: float = None,
        days_to_earnings: int = None,
        force_refresh: bool = False,
    ) -> AnalysisResult:
        """
        AI Deep Analysis for a single trading signal.

        Uses a 2-step process:
        1. Classify regime with Haiku (fast, ~$0.001)
        2. Run full analysis with Sonnet using the appropriate template

        Args:
            signal_data: TradingSignal.to_dict() output
            market_regime: Market regime from regime detector (optional)
            iv_rank: IV rank percentage (0-100) from TastyTrade (optional)
            days_to_earnings: Days until next earnings (optional)
            force_refresh: Bypass cache

        Returns:
            AnalysisResult with structured deep analysis
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        signal_id = signal_data.get("id", "unknown")
        symbol = signal_data.get("symbol", "UNKNOWN")
        cache_key = f"signal_analysis_{signal_id}"

        # Check cache
        if not force_refresh:
            cached_data = self._get_cached(cache_key, "signal_analysis")
            if cached_data:
                return AnalysisResult(success=True, data=cached_data, cached=True)

        try:
            # Step 1: Regime classification (using primary model for reliability)
            regime_prompt = build_regime_prompt(signal_data, iv_rank, days_to_earnings)

            regime_text, regime_usage = await self._call_claude(
                regime_prompt,
                system_prompt=SYSTEM_PROMPT_REGIME_CLASSIFIER,
                model=self.settings.CLAUDE_MODEL_PRIMARY,
                max_tokens=200,
                temperature=0.2,
            )

            # Parse regime result
            regime_result = None
            strategy_group = "trend"  # default
            if regime_text:
                regime_result = self.parser.extract_json(regime_text)
                if regime_result:
                    strategy_group = regime_result.get("strategy_group", "trend")

            logger.info(
                f"🧠 Signal {symbol} regime classified as '{strategy_group}' "
                f"(confidence: {regime_result.get('confidence', '?') if regime_result else '?'}/10)"
            )

            # Step 2: Full analysis with appropriate template (Sonnet)
            if strategy_group == "mean_reversion":
                analysis_prompt = build_mean_reversion_prompt(
                    signal_data, market_regime, iv_rank, days_to_earnings
                )
            else:
                analysis_prompt = build_trend_analysis_prompt(
                    signal_data, market_regime, iv_rank, days_to_earnings
                )

            response_text, usage = await self._call_claude(
                analysis_prompt,
                system_prompt=SYSTEM_PROMPT_SIGNAL_ANALYST,
                model=self.settings.CLAUDE_MODEL_PRIMARY,
                max_tokens=2000,
                temperature=0.4,
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            # Parse and validate JSON
            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                validated = validate_signal_analysis(parsed_data)
                validated["signal_id"] = signal_id
                validated["symbol"] = symbol
                validated["regime_classification"] = regime_result
                validated["analyzed_at"] = datetime.now().isoformat()
                validated["model"] = self.settings.CLAUDE_MODEL_PRIMARY
                validated["analysis_type"] = strategy_group

                # Cache the result
                self._set_cached(cache_key, validated)

                return AnalysisResult(
                    success=True,
                    data=validated,
                    raw_response=response_text,
                    usage=usage,
                )
            else:
                # Fallback: return raw text with extracted conviction
                conviction = self._extract_conviction(response_text)
                fallback_data = {
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "conviction": conviction,
                    "summary": response_text[:500],
                    "regime_classification": regime_result,
                    "analyzed_at": datetime.now().isoformat(),
                    "model": self.settings.CLAUDE_MODEL_PRIMARY,
                    "analysis_type": strategy_group,
                }
                return AnalysisResult(
                    success=True,
                    data=fallback_data,
                    raw_response=response_text,
                    usage=usage,
                )

        except (BudgetExceededError, RateLimitError) as e:
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error in signal analysis for {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def analyze_signal_batch(
        self,
        signals: List[Dict[str, Any]],
        market_regime: Dict[str, Any] = None,
        force_refresh: bool = False,
    ) -> AnalysisResult:
        """
        AI batch analysis: rank multiple signals and identify the best setup.

        Args:
            signals: List of TradingSignal.to_dict() outputs (max 5)
            market_regime: Market regime (optional)
            force_refresh: Bypass cache

        Returns:
            AnalysisResult with ranked signals and best setup
        """
        if not self.is_available():
            return AnalysisResult(success=False, error="Claude service not available")

        if not signals:
            return AnalysisResult(success=True, data={"summary": "No signals to analyze"})

        # Limit to 5
        signals = signals[:5]

        # Build cache key from signal IDs
        sig_ids = sorted([str(s.get("id", "")) for s in signals])
        cache_key = f"signal_batch_{'_'.join(sig_ids)}"

        if not force_refresh:
            cached_data = self._get_cached(cache_key, "signal_batch")
            if cached_data:
                return AnalysisResult(success=True, data=cached_data, cached=True)

        try:
            prompt = build_batch_scanner_prompt(signals, market_regime)

            response_text, usage = await self._call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT_SIGNAL_ANALYST,
                model=self.settings.CLAUDE_MODEL_PRIMARY,
                max_tokens=2000,
                temperature=0.4,
            )

            if not response_text:
                return AnalysisResult(success=False, error="No response from Claude")

            parsed_data = self.parser.extract_json(response_text)

            if parsed_data:
                validated = validate_batch_analysis(parsed_data)
                validated["total_analyzed"] = len(signals)
                validated["analyzed_at"] = datetime.now().isoformat()
                validated["model"] = self.settings.CLAUDE_MODEL_PRIMARY

                self._set_cached(cache_key, validated)

                return AnalysisResult(
                    success=True,
                    data=validated,
                    raw_response=response_text,
                    usage=usage,
                )
            else:
                return AnalysisResult(
                    success=True,
                    data={
                        "summary": response_text[:500],
                        "total_analyzed": len(signals),
                    },
                    raw_response=response_text,
                    usage=usage,
                )

        except (BudgetExceededError, RateLimitError) as e:
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error in batch signal analysis: {e}")
            return AnalysisResult(success=False, error=str(e))

    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------

    def _extract_conviction(self, response: str) -> int:
        """Extract conviction score from response text (fallback parser)."""
        try:
            patterns = [
                r'"conviction":\s*(\d+)',
                r'Conviction:\s*(\d+)/10',
                r'AI Conviction:\s*(\d+)/10',
                r'\*\*AI Conviction:\s*(\d+)/10\*\*',
                r'conviction.*?(\d+)/10',
            ]

            for pattern in patterns:
                match = re.search(pattern, response, re.IGNORECASE)
                if match:
                    return min(10, max(1, int(match.group(1))))

            return 5  # Default if not found

        except Exception:
            return 5

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics."""
        tokens = self.cost_tracker.get_daily_tokens()
        return {
            'daily_cost': round(self.cost_tracker.get_daily_cost(), 4),
            'daily_requests': self.cost_tracker.get_daily_requests(),
            'daily_tokens': tokens,
            'remaining_budget': round(
                self.cost_tracker.get_remaining_budget(self._daily_budget), 4
            ),
            'budget_limit': self._daily_budget,
            'budget_used_pct': round(
                (self.cost_tracker.get_daily_cost() / self._daily_budget) * 100, 1
            ) if self._daily_budget > 0 else 0
        }

    def clear_cache(self, cache_type: Optional[str] = None):
        """Clear cached responses."""
        if cache_type:
            keys_to_remove = [k for k in self._cache if k.startswith(cache_type)]
            for key in keys_to_remove:
                del self._cache[key]
            logger.info(f"Cleared {len(keys_to_remove)} cached items for type: {cache_type}")
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared all {count} cached items")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_claude_service: Optional[ClaudeAnalysisService] = None


def get_claude_service() -> ClaudeAnalysisService:
    """Get the global Claude service instance."""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeAnalysisService()
    return _claude_service


def initialize_claude_service(api_key: str = None) -> bool:
    """Initialize the global Claude service."""
    service = get_claude_service()
    return service.initialize(api_key)
