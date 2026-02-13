"""
Claude AI Service for Options Trading Analysis

This module provides the core integration with Anthropic's Claude API,
handling all AI-powered analysis for the trading assistant.
"""

import json
import asyncio
import logging
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
        
        # Reset if new day
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
        """Get today's total cost."""
        return self.daily_costs.get(self._get_today(), 0.0)
    
    def get_daily_requests(self) -> int:
        """Get today's request count."""
        return self.daily_requests.get(self._get_today(), 0)
    
    def check_budget(self) -> bool:
        """Check if within daily budget."""
        return self.get_daily_cost() < settings.CLAUDE_DAILY_BUDGET
    
    def get_remaining_budget(self) -> float:
        """Get remaining daily budget."""
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
        """
        Extract JSON from Claude's response, handling markdown code blocks.
        """
        import re
        
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
    def validate_market_regime(data: dict) -> dict:
        """Validate and normalize market regime response."""
        required_fields = ['regime', 'risk_appetite', 'positioning_guidance', 'summary']
        
        for field in required_fields:
            if field not in data:
                raise InvalidResponseError(f"Missing required field: {field}")
        
        # Normalize regime value
        valid_regimes = ['bullish', 'bearish', 'neutral', 'transitioning']
        if data['regime'].lower() not in valid_regimes:
            data['regime'] = 'neutral'
        else:
            data['regime'] = data['regime'].lower()
        
        # Ensure confidence is 0-100
        if 'regime_confidence' in data:
            data['regime_confidence'] = max(0, min(100, int(data['regime_confidence'])))
        
        return data
    
    @staticmethod
    def validate_stock_analysis(data: dict) -> dict:
        """Validate and normalize stock analysis response."""
        # Ensure conviction score is 1-10
        if 'conviction_score' in data:
            data['conviction_score'] = max(1, min(10, int(data['conviction_score'])))
        
        # Ensure required nested structures exist
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
    """
    AI-powered analysis service using Claude.
    
    This service handles all interactions with the Claude API,
    including caching, cost tracking, and response parsing.
    """
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
        
        self.cost_tracker = CostTracker()
        self.parser = ResponseParser()
        
        # Cache configuration
        self._cache: dict[str, CachedResponse] = {}
        self._cache_ttl = {
            'market_regime': timedelta(minutes=15),
            'stock_analysis': timedelta(minutes=30),
            'batch_analysis': timedelta(minutes=30),
        }
        
        # Retry configuration
        self._max_retries = 3
        self._base_retry_delay = 1.0
        
        logger.info(f"ClaudeAnalysisService initialized with model: {self.model}")
    
    # -------------------------------------------------------------------------
    # CORE API METHODS
    # -------------------------------------------------------------------------
    
    async def _call_claude(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> tuple[str, TokenUsage]:
        """
        Make a call to Claude API with retry logic.
        
        Returns:
            Tuple of (response_text, token_usage)
        """
        if not self.cost_tracker.check_budget():
            raise BudgetExceededError(
                f"Daily budget of ${settings.CLAUDE_DAILY_BUDGET:.2f} exceeded. "
                f"Current spend: ${self.cost_tracker.get_daily_cost():.2f}"
            )
        
        max_tokens = max_tokens or self.max_tokens
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                # Run synchronous API call in thread pool
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
                
                # Extract response text
                response_text = response.content[0].text
                
                # Track usage
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
    
    # -------------------------------------------------------------------------
    # MARKET REGIME ANALYSIS
    # -------------------------------------------------------------------------
    
    async def get_market_regime(
        self,
        market_data: dict,
        force_refresh: bool = False
    ) -> AnalysisResult:
        """
        Analyze current market regime.
        
        Args:
            market_data: Dict containing VIX, SPY data, breadth indicators, etc.
            force_refresh: Bypass cache if True
            
        Returns:
            AnalysisResult with regime analysis
        """
        cache_key = "market_regime"
        
        # Check cache
        if not force_refresh:
            cached_data = self._get_cached(cache_key, 'market_regime')
            if cached_data:
                return AnalysisResult(success=True, data=cached_data, cached=True)
        
        try:
            # Format prompt with market data
            prompt = MARKET_REGIME_PROMPT.format(
                vix=market_data.get('vix', 0),
                vix_sma=market_data.get('vix_sma', 0),
                vix_percentile=market_data.get('vix_percentile', 50),
                vix_term_structure=market_data.get('vix_term_structure', 'unknown'),
                spy_price=market_data.get('spy_price', 0),
                spy_change_pct=market_data.get('spy_change_pct', 0),
                spy_rsi=market_data.get('spy_rsi', 50),
                spy_vs_50sma=market_data.get('spy_vs_50sma', 0),
                spy_vs_200sma=market_data.get('spy_vs_200sma', 0),
                breadth_200sma=market_data.get('breadth_200sma', 50),
                breadth_50sma=market_data.get('breadth_50sma', 50),
                ad_line_trend=market_data.get('ad_line_trend', 'neutral'),
                put_call_ratio=market_data.get('put_call_ratio', 1.0),
                put_call_sma=market_data.get('put_call_sma', 1.0),
                aaii_spread=market_data.get('aaii_spread', 0),
                ten_year_yield=market_data.get('ten_year_yield', 4.0),
                yield_change=market_data.get('yield_change', 0),
                dxy=market_data.get('dxy', 100),
                hyg_trend=market_data.get('hyg_trend', 'neutral'),
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_MARKET_ANALYST,
                max_tokens=1500,
                temperature=0.5,  # Lower temperature for more consistent regime detection
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError("Could not parse market regime response", response_text)
            
            # Validate
            validated_data = self.parser.validate_market_regime(parsed_data)
            
            # Add metadata
            validated_data['analyzed_at'] = datetime.now().isoformat()
            validated_data['model'] = self.model
            
            # Cache result
            self._set_cached(cache_key, validated_data)
            
            return AnalysisResult(
                success=True,
                data=validated_data,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Market regime analysis failed: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in market regime analysis: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # STOCK ANALYSIS
    # -------------------------------------------------------------------------
    
    async def analyze_stock(
        self,
        stock_data: dict,
        market_regime: Optional[dict] = None,
        force_refresh: bool = False
    ) -> AnalysisResult:
        """
        Deep analysis of a single stock for LEAPS opportunity.
        
        Args:
            stock_data: Comprehensive stock data dict
            market_regime: Current market regime (optional, will fetch if not provided)
            force_refresh: Bypass cache if True
            
        Returns:
            AnalysisResult with full stock analysis
        """
        symbol = stock_data.get('symbol', 'UNKNOWN')
        cache_key = f"stock_analysis_{symbol}"
        
        # Check cache
        if not force_refresh:
            cached_data = self._get_cached(cache_key, 'stock_analysis')
            if cached_data:
                return AnalysisResult(success=True, data=cached_data, cached=True)
        
        try:
            # Format market cap
            market_cap = stock_data.get('market_cap', 0)
            market_cap_formatted, market_cap_category = format_market_cap(market_cap)
            
            # Format LEAPS chain
            leaps_summary = format_leaps_chain(stock_data.get('leaps_chain', []))
            
            # Format technical indicators
            tech_indicators = self._format_technical_indicators(stock_data)
            
            # Prepare regime context
            regime_context = market_regime or {}
            
            prompt = STOCK_ANALYSIS_PROMPT.format(
                symbol=symbol,
                company_name=stock_data.get('company_name', symbol),
                sector=stock_data.get('sector', 'Unknown'),
                industry=stock_data.get('industry', 'Unknown'),
                market_cap_formatted=market_cap_formatted,
                market_cap_category=market_cap_category,
                business_description=stock_data.get('description', 'No description available')[:500],
                current_price=stock_data.get('current_price', 0),
                fifty_two_week_low=stock_data.get('fifty_two_week_low', 0),
                fifty_two_week_high=stock_data.get('fifty_two_week_high', 0),
                price_percentile=stock_data.get('price_percentile', 50),
                pe_ratio=stock_data.get('pe_ratio', 0) or 0,
                forward_pe=stock_data.get('forward_pe', 0) or 0,
                ps_ratio=stock_data.get('ps_ratio', 0) or 0,
                pb_ratio=stock_data.get('pb_ratio', 0) or 0,
                peg_ratio=stock_data.get('peg_ratio', 0) or 0,
                fundamental_score=stock_data.get('fundamental_score', 0),
                revenue_growth=stock_data.get('revenue_growth', 0) or 0,
                eps_growth=stock_data.get('eps_growth', 0) or 0,
                gross_margin=stock_data.get('gross_margin', 0) or 0,
                operating_margin=stock_data.get('operating_margin', 0) or 0,
                net_margin=stock_data.get('net_margin', 0) or 0,
                roe=stock_data.get('roe', 0) or 0,
                debt_to_equity=stock_data.get('debt_to_equity', 0) or 0,
                fcf_yield=stock_data.get('fcf_yield', 0) or 0,
                technical_score=stock_data.get('technical_score', 0),
                trend_description=stock_data.get('trend_description', 'Unknown'),
                rsi=stock_data.get('rsi', 50),
                macd_signal=stock_data.get('macd_signal', 'neutral'),
                macd_histogram=stock_data.get('macd_histogram', 0),
                price_vs_50sma=stock_data.get('price_vs_50sma', 0),
                price_vs_200sma=stock_data.get('price_vs_200sma', 0),
                adx=stock_data.get('adx', 0),
                chart_pattern=stock_data.get('chart_pattern', 'None detected'),
                support_level=stock_data.get('support_level', stock_data.get('current_price', 0) * 0.9),
                resistance_level=stock_data.get('resistance_level', stock_data.get('current_price', 0) * 1.1),
                options_score=stock_data.get('options_score', 0),
                iv_rank=stock_data.get('iv_rank', 50),
                iv_percentile=stock_data.get('iv_percentile', 50),
                current_iv=stock_data.get('current_iv', 30),
                hv_30=stock_data.get('hv_30', 25),
                iv_hv_ratio=stock_data.get('iv_hv_ratio', 1.0),
                options_liquidity=stock_data.get('options_liquidity', 'Medium'),
                avg_options_volume=stock_data.get('avg_options_volume', 0),
                put_call_oi=stock_data.get('put_call_oi', 1.0),
                unusual_activity=stock_data.get('unusual_activity', 'None detected'),
                analyst_rating=stock_data.get('analyst_rating', 'Hold'),
                analyst_pt=stock_data.get('analyst_pt', stock_data.get('current_price', 0)),
                pt_upside=stock_data.get('pt_upside', 0),
                next_earnings=stock_data.get('next_earnings', 'Unknown'),
                days_to_earnings=stock_data.get('days_to_earnings', 999),
                news_sentiment=stock_data.get('news_sentiment', 'Neutral'),
                insider_activity=stock_data.get('insider_activity', 'No recent activity'),
                leaps_chain_summary=leaps_summary,
                market_regime=regime_context.get('regime', 'unknown'),
                regime_delta_range=str(regime_context.get('positioning_guidance', {}).get('delta_range', [0.5, 0.7])),
                sector_outlook_for_this_stock=self._get_sector_outlook(stock_data.get('sector'), regime_context),
                technical_indicators=tech_indicators,
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=2500,
                temperature=0.7,
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError(f"Could not parse stock analysis for {symbol}", response_text)
            
            # Validate
            validated_data = self.parser.validate_stock_analysis(parsed_data)
            
            # Add metadata
            validated_data['symbol'] = symbol
            validated_data['analyzed_at'] = datetime.now().isoformat()
            validated_data['model'] = self.model
            
            # Cache result
            self._set_cached(cache_key, validated_data)
            
            return AnalysisResult(
                success=True,
                data=validated_data,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Stock analysis failed for {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error analyzing {symbol}: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # BATCH ANALYSIS (Quick Scan)
    # -------------------------------------------------------------------------
    
    async def analyze_batch(
        self,
        stocks: list[dict],
        market_regime: Optional[dict] = None,
    ) -> AnalysisResult:
        """
        Quick analysis of multiple stocks (for screening results).
        
        Args:
            stocks: List of stock data dicts
            market_regime: Current market regime
            
        Returns:
            AnalysisResult with array of quick analyses
        """
        if not stocks:
            return AnalysisResult(success=True, data=[])
        
        try:
            regime_context = market_regime or {}
            
            # Format stocks for batch prompt
            stocks_formatted = format_stocks_for_batch(stocks)
            
            prompt = QUICK_SCAN_PROMPT.format(
                count=len(stocks),
                stocks_data=stocks_formatted,
                market_regime=regime_context.get('regime', 'unknown'),
                regime_delta_range=str(regime_context.get('positioning_guidance', {}).get('delta_range', [0.5, 0.7])),
                risk_mode=regime_context.get('risk_appetite', 'selective'),
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=2000,
                temperature=0.6,
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError("Could not parse batch analysis", response_text)
            
            # Ensure it's a list
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            
            # Validate each result
            validated_results = []
            for item in parsed_data:
                if 'conviction' in item:
                    item['conviction'] = max(1, min(10, int(item['conviction'])))
                validated_results.append(item)
            
            return AnalysisResult(
                success=True,
                data=validated_results,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Batch analysis failed: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in batch analysis: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # STRATEGY RECOMMENDATION
    # -------------------------------------------------------------------------
    
    async def get_strategy_recommendation(
        self,
        stock_data: dict,
        options_chain: dict,
        market_regime: Optional[dict] = None,
        portfolio_context: Optional[dict] = None,
    ) -> AnalysisResult:
        """
        Get specific options strategy recommendation.
        
        Args:
            stock_data: Stock analysis data
            options_chain: Available options data
            market_regime: Current market regime
            portfolio_context: User's portfolio info
            
        Returns:
            AnalysisResult with strategy recommendation
        """
        symbol = stock_data.get('symbol', 'UNKNOWN')
        
        try:
            regime_context = market_regime or {}
            portfolio = portfolio_context or {}
            
            # Format options chain summary
            options_summary = self._format_options_chain(options_chain)
            
            prompt = STRATEGY_RECOMMENDATION_PROMPT.format(
                symbol=symbol,
                current_price=stock_data.get('current_price', 0),
                trend_direction=stock_data.get('trend_description', 'Unknown'),
                trend_strength=stock_data.get('trend_strength', 5),
                iv_rank=stock_data.get('iv_rank', 50),
                iv_hv_comparison=self._format_iv_hv_comparison(stock_data),
                days_to_earnings=stock_data.get('days_to_earnings', 999),
                historical_earnings_move=stock_data.get('historical_earnings_move', 5),
                conviction_score=stock_data.get('conviction_score', 5),
                price_target=stock_data.get('price_target', stock_data.get('current_price', 0) * 1.5),
                target_upside=stock_data.get('target_upside', 50),
                target_timeframe=stock_data.get('target_timeframe', '12-18 months'),
                one_line_thesis=stock_data.get('one_line_thesis', 'Strong growth potential'),
                options_chain_summary=options_summary,
                market_regime=regime_context.get('regime', 'unknown'),
                regime_delta_range=str(regime_context.get('positioning_guidance', {}).get('delta_range', [0.5, 0.7])),
                regime_dte_range=str(regime_context.get('positioning_guidance', {}).get('dte_range', [60, 180])),
                portfolio_delta=portfolio.get('total_delta', 0),
                existing_position=portfolio.get(f'position_{symbol}', 'None'),
                sector_exposure=portfolio.get('sector_exposure', {}),
                cash_available=portfolio.get('cash_available', 10000),
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=2000,
                temperature=0.6,
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError(f"Could not parse strategy recommendation for {symbol}", response_text)
            
            # Validate
            validated_data = self.parser.validate_strategy_recommendation(parsed_data)
            
            # Add metadata
            validated_data['symbol'] = symbol
            validated_data['generated_at'] = datetime.now().isoformat()
            
            return AnalysisResult(
                success=True,
                data=validated_data,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Strategy recommendation failed for {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error getting strategy for {symbol}: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # RISK ANALYSIS
    # -------------------------------------------------------------------------
    
    async def analyze_position_risk(
        self,
        position: dict,
        current_stock_data: dict,
        recent_news: Optional[str] = None,
    ) -> AnalysisResult:
        """
        Analyze risk for an existing position.
        
        Args:
            position: Position details (entry, current P/L, etc.)
            current_stock_data: Current stock data
            recent_news: Recent news summary
            
        Returns:
            AnalysisResult with risk analysis
        """
        symbol = position.get('symbol', 'UNKNOWN')
        
        try:
            # Calculate P/L
            entry_price = position.get('entry_price', 0)
            current_price = position.get('current_price', 0)
            pnl_dollars = current_price - entry_price
            pnl_percent = (pnl_dollars / entry_price * 100) if entry_price else 0
            
            prompt = RISK_ANALYSIS_PROMPT.format(
                symbol=symbol,
                position_description=position.get('description', f"{symbol} position"),
                entry_price=entry_price,
                current_price=current_price,
                pnl_percent=pnl_percent,
                pnl_dollars=pnl_dollars * position.get('contracts', 1) * 100,
                days_held=position.get('days_held', 0),
                dte_remaining=position.get('dte_remaining', 0),
                stock_summary=self._format_stock_summary(current_stock_data),
                recent_news=recent_news or "No significant recent news",
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=1500,
                temperature=0.5,
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError(f"Could not parse risk analysis for {symbol}", response_text)
            
            # Add metadata
            parsed_data['symbol'] = symbol
            parsed_data['analyzed_at'] = datetime.now().isoformat()
            
            return AnalysisResult(
                success=True,
                data=parsed_data,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Risk analysis failed for {symbol}: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in risk analysis for {symbol}: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # DAILY BRIEFING
    # -------------------------------------------------------------------------
    
    async def get_daily_briefing(
        self,
        market_data: dict,
        positions: list[dict],
        watchlist: list[dict],
        earnings_today: list[dict],
        overnight_news: str,
    ) -> AnalysisResult:
        """
        Generate daily trading briefing.
        
        Args:
            market_data: Current market regime data
            positions: List of current positions
            watchlist: Watchlist stocks
            earnings_today: Earnings happening today
            overnight_news: Summary of overnight news
            
        Returns:
            AnalysisResult with daily briefing
        """
        try:
            # Format positions summary
            positions_summary = self._format_positions_summary(positions)
            
            # Format earnings calendar
            earnings_formatted = self._format_earnings_calendar(earnings_today)
            
            prompt = DAILY_BRIEFING_PROMPT.format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
                market_regime_data=json.dumps(market_data, indent=2),
                positions_summary=positions_summary,
                earnings_today=earnings_formatted,
                overnight_news=overnight_news[:2000],  # Limit news length
            )
            
            response_text, usage = await self._call_claude(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRADING_ANALYST,
                max_tokens=2000,
                temperature=0.6,
            )
            
            # Parse response
            parsed_data = self.parser.extract_json(response_text)
            if not parsed_data:
                raise InvalidResponseError("Could not parse daily briefing", response_text)
            
            # Add metadata
            parsed_data['generated_at'] = datetime.now().isoformat()
            
            return AnalysisResult(
                success=True,
                data=parsed_data,
                raw_response=response_text,
                usage=usage
            )
            
        except (InvalidResponseError, AIAnalysisError) as e:
            logger.error(f"Daily briefing failed: {e}")
            return AnalysisResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error generating daily briefing: {e}")
            return AnalysisResult(success=False, error=f"Unexpected error: {e}")
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def _format_technical_indicators(self, stock_data: dict) -> str:
        """Format technical indicators for prompt."""
        indicators = []
        
        if rsi := stock_data.get('rsi'):
            status = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
            indicators.append(f"RSI(14): {rsi:.1f} ({status})")
        
        if macd := stock_data.get('macd_histogram'):
            signal = "Bullish" if macd > 0 else "Bearish"
            indicators.append(f"MACD: {signal} (histogram: {macd:+.3f})")
        
        if adx := stock_data.get('adx'):
            strength = "Strong" if adx > 25 else "Weak"
            indicators.append(f"ADX: {adx:.1f} ({strength} trend)")
        
        return "\n".join(indicators) if indicators else "No technical data available"
    
    def _format_options_chain(self, options_chain: dict) -> str:
        """Format options chain for prompt."""
        if not options_chain:
            return "No options data available"
        
        lines = []
        for exp_date, strikes in options_chain.items():
            lines.append(f"\n**{exp_date}**:")
            for strike_data in strikes[:5]:  # Limit to top 5 strikes per expiration
                lines.append(
                    f"  ${strike_data['strike']:.0f}C | "
                    f"Delta: {strike_data.get('delta', 0):.2f} | "
                    f"Premium: ${strike_data.get('premium', 0):.2f} | "
                    f"OI: {strike_data.get('open_interest', 0):,}"
                )
        
        return "\n".join(lines)
    
    def _format_iv_hv_comparison(self, stock_data: dict) -> str:
        """Format IV vs HV comparison."""
        iv = stock_data.get('current_iv', 30)
        hv = stock_data.get('hv_30', 25)
        
        if iv > hv * 1.2:
            return f"IV ({iv:.1f}%) > HV ({hv:.1f}%) - options expensive"
        elif iv < hv * 0.8:
            return f"IV ({iv:.1f}%) < HV ({hv:.1f}%) - options cheap"
        else:
            return f"IV ({iv:.1f}%) ≈ HV ({hv:.1f}%) - fairly priced"
    
    def _get_sector_outlook(self, sector: str, regime: dict) -> str:
        """Get sector outlook from regime analysis."""
        if not regime or not sector:
            return "Unknown"
        
        overweight = regime.get('sector_allocation', {}).get('overweight', [])
        underweight = regime.get('sector_allocation', {}).get('underweight', [])
        
        if sector in overweight:
            return f"Favorable (overweight in current regime)"
        elif sector in underweight:
            return f"Unfavorable (underweight in current regime)"
        else:
            return "Neutral"
    
    def _format_stock_summary(self, stock_data: dict) -> str:
        """Format brief stock summary for risk analysis."""
        return f"""
Price: ${stock_data.get('current_price', 0):.2f}
Trend: {stock_data.get('trend_description', 'Unknown')}
RSI: {stock_data.get('rsi', 50):.1f}
IV Rank: {stock_data.get('iv_rank', 50):.0f}%
Recent Performance: {stock_data.get('performance_1w', 0):+.1f}% (1W), {stock_data.get('performance_1m', 0):+.1f}% (1M)
"""
    
    def _format_positions_summary(self, positions: list[dict]) -> str:
        """Format positions for daily briefing."""
        if not positions:
            return "No open positions"
        
        lines = []
        for pos in positions:
            pnl = pos.get('unrealized_pnl_pct', 0)
            emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            lines.append(
                f"{emoji} {pos['symbol']}: {pos.get('description', 'Position')} | "
                f"P/L: {pnl:+.1f}% | DTE: {pos.get('dte', 'N/A')}"
            )
        
        return "\n".join(lines)
    
    def _format_earnings_calendar(self, earnings: list[dict]) -> str:
        """Format earnings calendar."""
        if not earnings:
            return "No relevant earnings today"
        
        lines = []
        for e in earnings:
            lines.append(f"- {e['symbol']}: {e.get('timing', 'Unknown')} | Est EPS: ${e.get('est_eps', 'N/A')}")
        
        return "\n".join(lines)
    
    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    
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
            logger.info(f"Cleared {len(keys_to_remove)} cached items for type: {cache_type}")
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared all {count} cached items")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# Create a singleton instance for use across the application
_service_instance: Optional[ClaudeAnalysisService] = None


def get_claude_service() -> ClaudeAnalysisService:
    """Get or create the Claude service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ClaudeAnalysisService()
    return _service_instance