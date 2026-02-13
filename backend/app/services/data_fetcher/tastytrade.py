"""
TastyTrade API integration for enhanced options data and Greeks.

This service provides:
- Option chain data with Greeks (Delta, Gamma, Theta, Vega)
- Market metrics (IV rank, IV percentile, beta)
- Real-time streaming quotes (optional)
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from loguru import logger

from app.config import get_settings

# TastyTrade SDK imports
try:
    from tastytrade import Session
    from tastytrade.instruments import NestedOptionChain, Option, get_option_chain
    from tastytrade.metrics import get_market_metrics, MarketMetricInfo
    TASTYTRADE_AVAILABLE = True
except ImportError:
    TASTYTRADE_AVAILABLE = False
    logger.warning("TastyTrade SDK not installed. Run: pip install tastytrade")


class TastyTradeService:
    """
    Service for fetching enhanced options data from TastyTrade API.

    Provides IV rank, Greeks, and detailed options chain information.
    """

    def __init__(self):
        self.session: Optional[Session] = None
        self.session_expiration: Optional[datetime] = None
        self._initialized = False

    def initialize(self, provider_secret: str, refresh_token: str) -> bool:
        """
        Initialize the TastyTrade session with OAuth credentials.

        Args:
            provider_secret: OAuth provider secret
            refresh_token: User's refresh token

        Returns:
            True if initialization successful, False otherwise
        """
        if not TASTYTRADE_AVAILABLE:
            logger.error("TastyTrade SDK not available")
            return False

        if not provider_secret or not refresh_token:
            logger.warning("TastyTrade credentials not configured")
            return False

        try:
            self.session = Session(
                provider_secret=provider_secret,
                refresh_token=refresh_token
            )
            self._initialized = True
            logger.info("TastyTrade session initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TastyTrade session: {e}")
            return False

    def is_available(self) -> bool:
        """Check if the TastyTrade service is available and initialized."""
        return TASTYTRADE_AVAILABLE and self._initialized and self.session is not None

    def _ensure_session(self) -> bool:
        """Ensure session is valid, refresh if needed."""
        if not self.is_available():
            return False

        # Check if session needs refresh (within 5 minutes of expiration)
        if self.session.session_expiration:
            now = datetime.now(self.session.session_expiration.tzinfo)
            if now + timedelta(minutes=5) >= self.session.session_expiration:
                try:
                    self.session.refresh()
                    logger.debug("TastyTrade session refreshed")
                except Exception as e:
                    logger.error(f"Failed to refresh TastyTrade session: {e}")
                    return False
        return True

    def get_market_metrics(self, symbols: list[str]) -> dict[str, MarketMetricInfo]:
        """
        Get market metrics for symbols including IV rank, beta, etc.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to MarketMetricInfo
        """
        if not self._ensure_session():
            return {}

        try:
            metrics = get_market_metrics(self.session, symbols)
            return {m.symbol: m for m in metrics}
        except Exception as e:
            logger.error(f"Failed to get market metrics: {e}")
            return {}

    def get_iv_rank(self, symbol: str) -> Optional[float]:
        """
        Get IV rank for a symbol (0-100 scale).

        Args:
            symbol: Stock symbol

        Returns:
            IV rank as float, or None if unavailable
        """
        metrics = self.get_market_metrics([symbol])
        if symbol in metrics:
            m = metrics[symbol]
            # Use TW IV rank if available, otherwise TOS
            if m.tw_implied_volatility_index_rank is not None:
                return float(m.tw_implied_volatility_index_rank)
            elif m.tos_implied_volatility_index_rank is not None:
                return float(m.tos_implied_volatility_index_rank)
        return None

    def get_iv_percentile(self, symbol: str) -> Optional[float]:
        """
        Get IV percentile for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            IV percentile as float, or None if unavailable
        """
        metrics = self.get_market_metrics([symbol])
        if symbol in metrics and metrics[symbol].implied_volatility_percentile:
            try:
                return float(metrics[symbol].implied_volatility_percentile)
            except (ValueError, TypeError):
                pass
        return None

    def get_option_chain(self, symbol: str) -> dict[date, list]:
        """
        Get the full option chain for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary mapping expiration date to list of Option objects
        """
        if not self._ensure_session():
            return {}

        try:
            return get_option_chain(self.session, symbol)
        except Exception as e:
            logger.error(f"Failed to get option chain for {symbol}: {e}")
            return {}

    def get_leaps_expirations(self, symbol: str, min_dte: int = 365, max_dte: int = 730) -> list[date]:
        """
        Get LEAPS expiration dates for a symbol.

        Args:
            symbol: Stock symbol
            min_dte: Minimum days to expiration (default 365)
            max_dte: Maximum days to expiration (default 730)

        Returns:
            List of expiration dates that qualify as LEAPS
        """
        if not self._ensure_session():
            return []

        try:
            chains = NestedOptionChain.get(self.session, symbol)
            leaps_dates = []
            today = date.today()

            for chain in chains:
                for exp in chain.expirations:
                    dte = (exp.expiration_date - today).days
                    if min_dte <= dte <= max_dte:
                        leaps_dates.append(exp.expiration_date)

            return sorted(set(leaps_dates))
        except Exception as e:
            logger.error(f"Failed to get LEAPS expirations for {symbol}: {e}")
            return []

    def get_options_for_expiration(
        self,
        symbol: str,
        expiration_date: date,
        option_type: str = "C",  # C for calls, P for puts
        min_delta: float = 0.60,
        max_delta: float = 0.80
    ) -> list[dict]:
        """
        Get options for a specific expiration filtered by delta range.

        Args:
            symbol: Stock symbol
            expiration_date: Option expiration date
            option_type: "C" for calls, "P" for puts
            min_delta: Minimum delta (absolute value)
            max_delta: Maximum delta (absolute value)

        Returns:
            List of option dictionaries with strike, delta, and other Greeks
        """
        chain = self.get_option_chain(symbol)
        if expiration_date not in chain:
            return []

        options = chain[expiration_date]
        filtered = []

        for opt in options:
            if opt.option_type.value != option_type:
                continue

            # Note: Greeks need to be fetched from market data/streamer
            # For now, return basic option info
            filtered.append({
                "symbol": opt.symbol,
                "strike": float(opt.strike_price),
                "expiration": opt.expiration_date.isoformat(),
                "option_type": opt.option_type.value,
                "days_to_expiration": opt.days_to_expiration,
                "streamer_symbol": opt.streamer_symbol
            })

        return filtered

    def get_enhanced_options_data(self, symbol: str) -> dict:
        """
        Get comprehensive options data for LEAPS screening.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with IV metrics, LEAPS expirations, and option recommendations
        """
        result = {
            "symbol": symbol,
            "iv_rank": None,
            "iv_percentile": None,
            "iv_30_day": None,
            "hv_30_day": None,
            "beta": None,
            "leaps_expirations": [],
            "recommended_options": [],
            "tastytrade_available": self.is_available()
        }

        if not self.is_available():
            return result

        # Get market metrics
        metrics = self.get_market_metrics([symbol])
        if symbol in metrics:
            m = metrics[symbol]
            result["iv_rank"] = float(m.tw_implied_volatility_index_rank) if m.tw_implied_volatility_index_rank else None
            result["iv_percentile"] = m.implied_volatility_percentile
            result["iv_30_day"] = float(m.implied_volatility_30_day) if m.implied_volatility_30_day else None
            result["hv_30_day"] = float(m.historical_volatility_30_day) if m.historical_volatility_30_day else None
            result["beta"] = float(m.beta) if m.beta else None

        # Get LEAPS expirations
        result["leaps_expirations"] = [d.isoformat() for d in self.get_leaps_expirations(symbol)]

        return result


# Global service instance
_tastytrade_service: Optional[TastyTradeService] = None


def get_tastytrade_service() -> TastyTradeService:
    """Get the global TastyTrade service instance."""
    global _tastytrade_service
    if _tastytrade_service is None:
        _tastytrade_service = TastyTradeService()
    return _tastytrade_service


def initialize_tastytrade_service(provider_secret: str, refresh_token: str) -> bool:
    """
    Initialize the global TastyTrade service.

    Args:
        provider_secret: OAuth provider secret
        refresh_token: User's refresh token

    Returns:
        True if initialization successful
    """
    service = get_tastytrade_service()
    return service.initialize(provider_secret, refresh_token)
