"""
Market Regime Detection - Analyze VIX, breadth, and market conditions
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.analysis.technical import TechnicalAnalysis
from app.services.ai.claude_service import get_claude_service
from app.services.ai.prompts import MARKET_REGIME_PROMPT


class MarketRegimeDetector:
    """Detect current market regime for strategy adjustment."""

    def __init__(self):
        self.tech_analysis = TechnicalAnalysis()
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)

    async def get_market_data(self) -> Dict[str, Any]:
        """
        Fetch market-wide indicators for regime detection.

        Returns:
            Dict with VIX, SPY RSI, breadth metrics
        """
        try:
            data = {}

            # Get VIX data
            vix_data = alpaca_service.get_historical_prices("^VIX", period="1mo")
            if vix_data is not None and len(vix_data) > 0:
                data['vix'] = float(vix_data['Close'].iloc[-1])
                # Calculate 20-day SMA of VIX
                if len(vix_data) >= 20:
                    data['vix_sma'] = float(vix_data['Close'].tail(20).mean())
                else:
                    data['vix_sma'] = data['vix']

                # VIX trend
                if len(vix_data) >= 5:
                    vix_5d_ago = float(vix_data['Close'].iloc[-5])
                    if data['vix'] < vix_5d_ago * 0.95:
                        data['vix_trend'] = 'falling'
                    elif data['vix'] > vix_5d_ago * 1.05:
                        data['vix_trend'] = 'rising'
                    else:
                        data['vix_trend'] = 'stable'
                else:
                    data['vix_trend'] = 'unknown'
            else:
                data['vix'] = 20.0  # Default
                data['vix_sma'] = 20.0
                data['vix_trend'] = 'unknown'

            # Get SPY data for RSI and trend
            spy_data = alpaca_service.get_historical_prices("SPY", period="3mo")
            if spy_data is not None and len(spy_data) > 0:
                # Calculate RSI
                indicators = self.tech_analysis.calculate_all_indicators(spy_data)
                latest = self.tech_analysis.get_latest_indicators(indicators)
                data['spy_rsi'] = latest.get('rsi_14', 50)
                data['spy_price'] = float(spy_data['Close'].iloc[-1])

                # SPY vs 200 SMA
                if len(spy_data) >= 200:
                    sma_200 = float(spy_data['Close'].tail(200).mean())
                    pct_diff = ((data['spy_price'] - sma_200) / sma_200) * 100
                    data['spy_vs_200sma'] = f"{pct_diff:+.1f}%"
                    data['spy_above_200sma'] = data['spy_price'] > sma_200
                else:
                    data['spy_vs_200sma'] = "N/A"
                    data['spy_above_200sma'] = True
            else:
                data['spy_rsi'] = 50
                data['spy_vs_200sma'] = "N/A"
                data['spy_above_200sma'] = True

            # Get Put/Call ratio (using VIX as proxy - actual P/C would need options data)
            # Lower VIX typically correlates with lower P/C ratio
            # This is a simplified estimation
            if data['vix'] < 15:
                data['put_call_ratio'] = 0.70
            elif data['vix'] < 20:
                data['put_call_ratio'] = 0.80
            elif data['vix'] < 25:
                data['put_call_ratio'] = 0.95
            elif data['vix'] < 30:
                data['put_call_ratio'] = 1.10
            else:
                data['put_call_ratio'] = 1.30

            data['timestamp'] = datetime.now().isoformat()
            return data

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {
                'vix': 20.0,
                'vix_sma': 20.0,
                'vix_trend': 'unknown',
                'spy_rsi': 50,
                'spy_vs_200sma': 'N/A',
                'put_call_ratio': 0.90,
                'error': str(e)
            }

    def analyze_regime_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market regime using rule-based logic (fast, no AI).

        Returns:
            Dict with regime classification and recommendations
        """
        vix = data.get('vix', 20)
        vix_sma = data.get('vix_sma', 20)
        spy_rsi = data.get('spy_rsi', 50)
        spy_above_200 = data.get('spy_above_200sma', True)
        vix_trend = data.get('vix_trend', 'stable')

        # Determine regime
        regime = 'neutral'
        risk_mode = 'mixed'
        confidence = 5

        # Strong bullish signals
        if vix < 15 and spy_rsi > 50 and spy_above_200 and vix_trend in ['falling', 'stable']:
            regime = 'bullish'
            risk_mode = 'risk_on'
            confidence = 8

        # Moderate bullish
        elif vix < 20 and spy_rsi > 45 and spy_above_200:
            regime = 'bullish'
            risk_mode = 'risk_on'
            confidence = 7

        # Strong bearish signals
        elif vix > 30 and spy_rsi < 40 and not spy_above_200 and vix_trend == 'rising':
            regime = 'bearish'
            risk_mode = 'risk_off'
            confidence = 8

        # Moderate bearish
        elif vix > 25 or (spy_rsi < 35 and not spy_above_200):
            regime = 'bearish'
            risk_mode = 'risk_off'
            confidence = 6

        # Elevated caution
        elif vix > 20 and vix > vix_sma:
            regime = 'neutral'
            risk_mode = 'mixed'
            confidence = 5

        # Default bullish lean if nothing else
        elif spy_above_200:
            regime = 'bullish'
            risk_mode = 'mixed'
            confidence = 5

        # Delta and DTE recommendations based on regime
        if regime == 'bullish' and risk_mode == 'risk_on':
            delta_range = [0.50, 0.70]
            dte_range = [60, 120]
            sectors_favor = ['Technology', 'Consumer Cyclical', 'Communication Services']
            sectors_avoid = ['Utilities', 'Consumer Defensive']
        elif regime == 'bullish':
            delta_range = [0.55, 0.75]
            dte_range = [90, 180]
            sectors_favor = ['Technology', 'Healthcare', 'Industrials']
            sectors_avoid = ['Utilities']
        elif regime == 'bearish':
            delta_range = [0.70, 0.85]
            dte_range = [180, 365]
            sectors_favor = ['Healthcare', 'Consumer Defensive', 'Utilities']
            sectors_avoid = ['Technology', 'Consumer Cyclical']
        else:  # neutral
            delta_range = [0.60, 0.75]
            dte_range = [90, 180]
            sectors_favor = ['Healthcare', 'Technology']
            sectors_avoid = []

        # Generate summary
        if regime == 'bullish' and risk_mode == 'risk_on':
            summary = f"Risk-on environment. VIX at {vix:.1f} indicates low fear. Favor aggressive delta and shorter DTE."
        elif regime == 'bullish':
            summary = f"Moderately bullish. VIX at {vix:.1f} with SPY RSI {spy_rsi:.0f}. Standard long call setups favored."
        elif regime == 'bearish':
            summary = f"Elevated risk. VIX at {vix:.1f} signals caution. Use higher delta, longer DTE for safety."
        else:
            summary = f"Mixed signals. VIX at {vix:.1f}, SPY RSI {spy_rsi:.0f}. Be selective with entries."

        return {
            'regime': regime,
            'risk_mode': risk_mode,
            'confidence': confidence,
            'vix': vix,
            'vix_sma': vix_sma,
            'vix_trend': vix_trend,
            'spy_rsi': spy_rsi,
            'spy_vs_200sma': data.get('spy_vs_200sma', 'N/A'),
            'put_call_ratio': data.get('put_call_ratio', 0.90),
            'delta_range': delta_range,
            'dte_range': dte_range,
            'sectors_favor': sectors_favor,
            'sectors_avoid': sectors_avoid,
            'summary': summary,
            'timestamp': data.get('timestamp', datetime.now().isoformat()),
            'analysis_type': 'rules'
        }

    async def analyze_regime_ai(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use Claude AI to analyze market regime (slower, more nuanced).

        Returns:
            Dict with AI-enhanced regime analysis
        """
        claude = get_claude_service()
        if not claude.is_available():
            logger.warning("Claude not available, using rules-based analysis")
            return None

        try:
            prompt = MARKET_REGIME_PROMPT.format(
                vix=data.get('vix', 20),
                vix_sma=data.get('vix_sma', 20),
                vix_trend=data.get('vix_trend', 'unknown'),
                spy_rsi=data.get('spy_rsi', 50),
                spy_vs_200sma=data.get('spy_vs_200sma', 'N/A'),
                put_call_ratio=data.get('put_call_ratio', 0.90)
            )

            # Use fast model for regime detection
            response = await claude._call_claude(
                prompt,
                model=claude.settings.CLAUDE_MODEL_FAST,
                max_tokens=500,
                temperature=0.2
            )

            if not response:
                return None

            # Try to parse JSON from response
            try:
                # Find JSON in response
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                    ai_result = json.loads(json_str)

                    # Add metadata
                    ai_result['timestamp'] = data.get('timestamp', datetime.now().isoformat())
                    ai_result['analysis_type'] = 'ai'
                    ai_result['vix'] = data.get('vix', 20)
                    ai_result['vix_sma'] = data.get('vix_sma', 20)
                    ai_result['vix_trend'] = data.get('vix_trend', 'unknown')
                    ai_result['spy_rsi'] = data.get('spy_rsi', 50)
                    ai_result['spy_vs_200sma'] = data.get('spy_vs_200sma', 'N/A')
                    ai_result['put_call_ratio'] = data.get('put_call_ratio', 0.90)

                    return ai_result

            except json.JSONDecodeError:
                logger.warning("Could not parse AI response as JSON")
                return None

        except Exception as e:
            logger.error(f"Error in AI regime analysis: {e}")
            return None

    async def get_regime(self, use_ai: bool = False) -> Dict[str, Any]:
        """
        Get current market regime with caching.

        Args:
            use_ai: Whether to use Claude AI for analysis (slower but more nuanced)

        Returns:
            Dict with regime classification and recommendations
        """
        # Check cache
        now = datetime.now()
        cache_key = 'ai' if use_ai else 'rules'

        if (
            self._cache_time
            and now - self._cache_time < self._cache_ttl
            and cache_key in self._cache
        ):
            return self._cache[cache_key]

        # Fetch fresh data
        data = await self.get_market_data()

        # Analyze
        if use_ai:
            result = await self.analyze_regime_ai(data)
            if not result:
                # Fallback to rules
                result = self.analyze_regime_rules(data)
        else:
            result = self.analyze_regime_rules(data)

        # Cache result
        self._cache[cache_key] = result
        self._cache_time = now

        return result

    def clear_cache(self):
        """Clear the regime cache."""
        self._cache = {}
        self._cache_time = None


# Global instance
_regime_detector: Optional[MarketRegimeDetector] = None


def get_regime_detector() -> MarketRegimeDetector:
    """Get the global regime detector instance."""
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = MarketRegimeDetector()
    return _regime_detector
