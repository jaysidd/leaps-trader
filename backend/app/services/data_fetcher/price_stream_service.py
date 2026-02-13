"""
Real-time Price Stream Service
WebSocket streaming via Alpaca StockDataStream
"""
import asyncio
import threading
from typing import Dict, Set, Optional, Callable, Any
from datetime import datetime, timezone
from loguru import logger

from app.config import get_settings

settings = get_settings()

# Alpaca SDK imports
try:
    from alpaca.data.live import StockDataStream
    from alpaca.data.enums import DataFeed
    ALPACA_STREAM_AVAILABLE = True
except ImportError as e:
    ALPACA_STREAM_AVAILABLE = False
    logger.warning(f"alpaca-py live streaming not available: {e}")
except Exception as e:
    ALPACA_STREAM_AVAILABLE = False
    logger.error(f"alpaca-py live streaming unexpected error: {e}")

# Map string feed names to DataFeed enum
FEED_MAP = {
    "iex": DataFeed.IEX,
    "sip": DataFeed.SIP,
} if ALPACA_STREAM_AVAILABLE else {}


class PriceStreamService:
    """
    Manages real-time price streaming from Alpaca.

    - Connects to Alpaca's WebSocket stream (IEX feed on free tier)
    - Subscribes to trades/quotes for requested symbols
    - Broadcasts updates to all registered callbacks (FastAPI WebSocket clients)
    """

    def __init__(self):
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY
        self.data_feed = settings.ALPACA_DATA_FEED  # 'iex' (free) or 'sip' (paid)

        self._stream: Optional[StockDataStream] = None
        self._subscribed_symbols: Set[str] = set()
        self._callbacks: Set[Callable] = set()
        self._running = False
        self._stream_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

        # Latest prices cache (for new subscribers)
        self._latest_prices: Dict[str, Dict[str, Any]] = {}

        # Event loop reference for async callbacks
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_available(self) -> bool:
        """Check if streaming is available"""
        return (
            ALPACA_STREAM_AVAILABLE
            and bool(self.api_key)
            and bool(self.secret_key)
        )

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to receive price updates"""
        self._callbacks.add(callback)
        logger.debug(f"Registered price stream callback. Total: {len(self._callbacks)}")

    def unregister_callback(self, callback: Callable) -> None:
        """Unregister a callback"""
        self._callbacks.discard(callback)
        logger.debug(f"Unregistered price stream callback. Total: {len(self._callbacks)}")

    def _broadcast_sync(self, data: Dict[str, Any]) -> None:
        """Broadcast price update to all registered callbacks (sync version)"""
        for callback in list(self._callbacks):
            try:
                if asyncio.iscoroutinefunction(callback):
                    # Schedule async callback on the event loop
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(callback(data), self._loop)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in price stream callback: {e}")

    def _handle_trade(self, trade) -> None:
        """Handle incoming trade data from Alpaca (sync handler)"""
        try:
            symbol = trade.symbol
            price_data = {
                "type": "trade",
                "symbol": symbol,
                "price": float(trade.price),
                "size": int(trade.size),
                "timestamp": trade.timestamp.isoformat() if trade.timestamp else datetime.now(timezone.utc).isoformat(),
                "conditions": list(getattr(trade, 'conditions', []) or []),
            }

            # Update cache
            with self._lock:
                self._latest_prices[symbol] = {
                    "price": price_data["price"],
                    "timestamp": price_data["timestamp"],
                }

            self._broadcast_sync(price_data)
        except Exception as e:
            logger.error(f"Error handling trade: {e}")

    def _handle_quote(self, quote) -> None:
        """Handle incoming quote data from Alpaca (sync handler)"""
        try:
            symbol = quote.symbol
            quote_data = {
                "type": "quote",
                "symbol": symbol,
                "bid": float(quote.bid_price) if quote.bid_price else None,
                "ask": float(quote.ask_price) if quote.ask_price else None,
                "bid_size": int(quote.bid_size) if quote.bid_size else 0,
                "ask_size": int(quote.ask_size) if quote.ask_size else 0,
                "timestamp": quote.timestamp.isoformat() if quote.timestamp else datetime.now(timezone.utc).isoformat(),
            }

            # Calculate mid price for cache
            if quote_data["bid"] and quote_data["ask"]:
                mid = (quote_data["bid"] + quote_data["ask"]) / 2
                with self._lock:
                    self._latest_prices[symbol] = {
                        "price": mid,
                        "bid": quote_data["bid"],
                        "ask": quote_data["ask"],
                        "timestamp": quote_data["timestamp"],
                    }

            self._broadcast_sync(quote_data)
        except Exception as e:
            logger.error(f"Error handling quote: {e}")

    def _run_stream_thread(self) -> None:
        """Run the Alpaca stream in a background thread"""
        if not self.is_available:
            logger.error("Alpaca streaming not available")
            return

        try:
            feed_enum = FEED_MAP.get(self.data_feed, DataFeed.IEX)
            self._stream = StockDataStream(
                api_key=self.api_key,
                secret_key=self.secret_key,
                feed=feed_enum,
            )

            # Subscribe handlers with initial symbols
            with self._lock:
                symbols = list(self._subscribed_symbols)

            if symbols:
                self._stream.subscribe_trades(self._handle_trade, *symbols)
                self._stream.subscribe_quotes(self._handle_quote, *symbols)
                logger.info(f"Subscribed to {len(symbols)} symbols: {symbols[:5]}{'...' if len(symbols) > 5 else ''}")

            logger.info(f"Starting Alpaca price stream (feed: {self.data_feed})")
            self._running = True

            # Run stream (this blocks until stopped)
            self._stream.run()

        except Exception as e:
            logger.error(f"Price stream error: {e}")
        finally:
            self._running = False
            logger.info("Price stream thread exited")

    async def start(self) -> None:
        """Start the price stream"""
        if self._running:
            logger.debug("Price stream already running")
            return

        if not self.is_available:
            logger.warning("Cannot start price stream - Alpaca not available")
            return

        # Capture the current event loop for async callbacks
        self._loop = asyncio.get_event_loop()

        # Start stream in background thread
        self._stream_thread = threading.Thread(
            target=self._run_stream_thread,
            daemon=True,
            name="alpaca-price-stream"
        )
        self._stream_thread.start()
        logger.info("Price stream thread started")

    async def stop(self) -> None:
        """Stop the price stream"""
        self._running = False

        if self._stream:
            try:
                self._stream.stop()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
            self._stream = None

        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=5.0)
            self._stream_thread = None

        logger.info("Price stream stopped")

    async def subscribe(self, symbols: Set[str]) -> None:
        """Subscribe to symbols for price updates"""
        async with self._async_lock:
            new_symbols = symbols - self._subscribed_symbols

            if not new_symbols:
                return

            with self._lock:
                self._subscribed_symbols.update(new_symbols)

            logger.info(f"Subscribing to symbols: {new_symbols}")

            if self._stream and self._running:
                try:
                    self._stream.subscribe_trades(self._handle_trade, *new_symbols)
                    self._stream.subscribe_quotes(self._handle_quote, *new_symbols)
                except Exception as e:
                    logger.error(f"Error subscribing to symbols: {e}")

    async def unsubscribe(self, symbols: Set[str]) -> None:
        """Unsubscribe from symbols"""
        async with self._async_lock:
            with self._lock:
                symbols_to_remove = symbols & self._subscribed_symbols

            if not symbols_to_remove:
                return

            with self._lock:
                self._subscribed_symbols -= symbols_to_remove

            logger.info(f"Unsubscribing from symbols: {symbols_to_remove}")

            if self._stream and self._running:
                try:
                    self._stream.unsubscribe_trades(*symbols_to_remove)
                    self._stream.unsubscribe_quotes(*symbols_to_remove)
                except Exception as e:
                    logger.error(f"Error unsubscribing from symbols: {e}")

    def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the latest cached price for a symbol"""
        with self._lock:
            return self._latest_prices.get(symbol)

    def get_all_latest_prices(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached latest prices"""
        with self._lock:
            return dict(self._latest_prices)

    @property
    def subscribed_symbols(self) -> Set[str]:
        """Get currently subscribed symbols"""
        with self._lock:
            return set(self._subscribed_symbols)

    @property
    def is_running(self) -> bool:
        """Check if stream is running"""
        return self._running


# Singleton instance
_price_stream_service: Optional[PriceStreamService] = None


def get_price_stream_service() -> PriceStreamService:
    """Get singleton price stream service instance"""
    global _price_stream_service
    if _price_stream_service is None:
        _price_stream_service = PriceStreamService()
    return _price_stream_service
