"""
Alpaca Trading Service
Order execution and position management
"""
from typing import Dict, Optional, List
from datetime import datetime
from loguru import logger

from app.config import get_settings

settings = get_settings()

# Alpaca SDK imports (with fallback for when not installed)
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
        TrailingStopOrderRequest,
        TakeProfitRequest,
        StopLossRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, OrderClass
    ALPACA_TRADING_AVAILABLE = True
except ImportError:
    ALPACA_TRADING_AVAILABLE = False
    logger.warning("alpaca-py trading module not installed. Install with: pip install alpaca-py")

# Timeout for Alpaca API calls (seconds). Prevents indefinite hangs.
ALPACA_REQUEST_TIMEOUT = 30


class AlpacaTradingService:
    """
    Alpaca Trading Service for order execution and position management.
    Supports both paper and live trading modes.
    """

    def __init__(self):
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY
        self._paper_mode = settings.ALPACA_PAPER

        self._client = None
        self._try_init()

    def _try_init(self):
        """Attempt to initialize the trading client. Safe to call multiple times."""
        if self._client is not None:
            return  # Already initialized

        if not ALPACA_TRADING_AVAILABLE:
            logger.error("Alpaca Trading SDK not available")
            return

        # Re-read keys from settings in case they were set after module import
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY

        if not self.api_key or not self.secret_key:
            logger.warning("Alpaca API keys not configured")
            return

        self._init_client()

    def _init_client(self):
        """Initialize trading client with current mode and timeout protection."""
        try:
            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self._paper_mode,
            )
            # Alpaca SDK doesn't expose a timeout parameter; patch the underlying
            # requests.Session so every HTTP call has a hard deadline.
            if hasattr(self._client, '_session'):
                _orig_request = self._client._session.request

                def _request_with_timeout(*args, **kwargs):
                    kwargs.setdefault("timeout", ALPACA_REQUEST_TIMEOUT)
                    return _orig_request(*args, **kwargs)

                self._client._session.request = _request_with_timeout
            mode = "PAPER" if self._paper_mode else "LIVE"
            logger.info(f"Alpaca trading client initialized ({mode} mode, timeout={ALPACA_REQUEST_TIMEOUT}s)")
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca trading client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if trading service is properly configured. Tries lazy init if not yet ready."""
        if self._client is None and ALPACA_TRADING_AVAILABLE:
            self._try_init()  # Lazy retry in case keys were set after module import
        return ALPACA_TRADING_AVAILABLE and self._client is not None

    def reinitialize(self, api_key: str = None, secret_key: str = None):
        """
        Reinitialize with new credentials. Called when API keys are updated
        via the Settings UI at runtime.
        """
        if api_key:
            self.api_key = api_key
        if secret_key:
            self.secret_key = secret_key
        self._client = None
        self._try_init()
        return self.is_available

    @property
    def is_paper_mode(self) -> bool:
        """Check if in paper trading mode"""
        return self._paper_mode

    @staticmethod
    def _parse_side(side: str) -> "OrderSide":
        """Strictly parse order side. Raises ValueError on invalid input."""
        normalized = side.lower().strip()
        if normalized == "buy":
            return OrderSide.BUY
        elif normalized == "sell":
            return OrderSide.SELL
        else:
            raise ValueError(f"Invalid order side: '{side}'. Must be 'buy' or 'sell'.")

    def set_paper_mode(self, paper: bool):
        """Switch between paper and live trading modes"""
        if paper != self._paper_mode:
            self._paper_mode = paper
            self._init_client()
            mode = "PAPER" if paper else "LIVE"
            logger.info(f"Switched to {mode} trading mode")

    def get_account(self) -> Optional[Dict]:
        """
        Get account information.

        Returns:
            Dict with: equity, buying_power, cash, portfolio_value, etc.
            None on error or when service is not configured.
        """
        if not self.is_available:
            return None

        try:
            account = self._client.get_account()
            return {
                "id": account.id,
                "status": account.status,
                "currency": account.currency,
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "equity": float(account.equity),
                "portfolio_value": float(account.portfolio_value),
                "last_equity": float(account.last_equity),
                "long_market_value": float(account.long_market_value),
                "short_market_value": float(account.short_market_value),
                "daytrade_count": account.daytrade_count,
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "transfers_blocked": account.transfers_blocked,
                "account_blocked": account.account_blocked,
                "paper_mode": self._paper_mode,
            }
        except Exception as e:
            logger.error(f"Alpaca get_account failed (callers will receive None): {e}")
            return None

    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        time_in_force: str = "day"
    ) -> Optional[Dict]:
        """
        Place a market order.

        Args:
            symbol: Stock ticker
            qty: Number of shares
            side: 'buy' or 'sell'
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order details dict
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK,
            }

            request = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=self._parse_side(side),
                time_in_force=tif_map.get(time_in_force.lower(), TimeInForce.DAY)
            )

            order = self._client.submit_order(request)

            logger.info(f"Market order placed: {side.upper()} {qty} {symbol} (ID: {order.id})")

            return {
                "order_id": str(order.id),
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "qty": float(order.qty),
                "status": order.status.value,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            }

        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return {"error": str(e)}

    def place_limit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
        time_in_force: str = "gtc"
    ) -> Optional[Dict]:
        """
        Place a limit order.

        Args:
            symbol: Stock ticker
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Limit price
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order details dict
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK,
            }

            request = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=self._parse_side(side),
                limit_price=limit_price,
                time_in_force=tif_map.get(time_in_force.lower(), TimeInForce.GTC)
            )

            order = self._client.submit_order(request)

            logger.info(f"Limit order placed: {side.upper()} {qty} {symbol} @ ${limit_price} (ID: {order.id})")

            return {
                "order_id": str(order.id),
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "qty": float(order.qty),
                "limit_price": float(order.limit_price),
                "status": order.status.value,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            }

        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return {"error": str(e)}

    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get position for a symbol with P/L calculation.

        Returns:
            Dict with: qty, avg_entry, current_price, market_value, unrealized_pl, unrealized_plpc
        """
        if not self.is_available:
            return None

        try:
            position = self._client.get_open_position(symbol.upper())

            return {
                "symbol": position.symbol,
                "qty": float(position.qty),
                "side": position.side.value,
                "avg_entry_price": float(position.avg_entry_price),
                "current_price": float(position.current_price),
                "market_value": float(position.market_value),
                "cost_basis": float(position.cost_basis),
                "unrealized_pl": float(position.unrealized_pl),
                "unrealized_plpc": float(position.unrealized_plpc) * 100,  # Convert to percentage
                "unrealized_intraday_pl": float(position.unrealized_intraday_pl),
                "unrealized_intraday_plpc": float(position.unrealized_intraday_plpc) * 100,
                "change_today": float(position.change_today) * 100,
            }

        except Exception as e:
            # Position not found is not an error
            if "position does not exist" in str(e).lower():
                return None
            logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def get_all_positions(self) -> List[Dict]:
        """Get all open positions"""
        if not self.is_available:
            return []

        try:
            positions = self._client.get_all_positions()

            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "side": p.side.value,
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc) * 100,
                }
                for p in positions
            ]

        except Exception as e:
            logger.error(f"Alpaca get_all_positions failed (returning empty list): {e}")
            return []

    def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
        percentage: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Close a position (full or partial).

        Args:
            symbol: Stock ticker
            qty: Number of shares to close (optional)
            percentage: Percentage of position to close (0-100) (optional)

        If neither qty nor percentage is specified, closes entire position.
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            close_options = {}

            if qty:
                close_options["qty"] = str(qty)
            elif percentage:
                close_options["percentage"] = str(percentage / 100)  # API expects decimal

            if close_options:
                order = self._client.close_position(symbol.upper(), close_options=close_options)
            else:
                order = self._client.close_position(symbol.upper())

            logger.info(f"Position closed: {symbol} (Order ID: {order.id})")

            return {
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": float(order.qty),
                "status": order.status.value,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            }

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {"error": str(e)}

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """Cancel an open order"""
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            self._client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return {"success": True, "order_id": order_id}

        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {"error": str(e)}

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order details"""
        if not self.is_available:
            return None

        try:
            order = self._client.get_order_by_id(order_id)

            return {
                "order_id": str(order.id),
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "qty": float(order.qty),
                "status": order.status.value,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "stop_price": float(order.stop_price) if order.stop_price else None,
            }

        except Exception as e:
            logger.error(f"Alpaca get_order({order_id}) failed: {e}")
            return None

    # =========================================================================
    # Bot-Enhanced Order Types
    # =========================================================================

    _TIF_MAP = {
        "day": "DAY",
        "gtc": "GTC",
        "ioc": "IOC",
        "fok": "FOK",
    }

    def _resolve_tif(self, tif_str: str):
        """Convert string to TimeInForce enum."""
        return getattr(TimeInForce, self._TIF_MAP.get(tif_str.lower(), "DAY"))

    def _format_order_result(self, order) -> Dict:
        """Standard order result dict from an Alpaca order object."""
        result = {
            "order_id": str(order.id),
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value if order.side else None,
            "type": order.type.value if order.type else None,
            "qty": float(order.qty) if order.qty else None,
            "status": order.status.value if order.status else None,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
            "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
            "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            "limit_price": float(order.limit_price) if order.limit_price else None,
            "stop_price": float(order.stop_price) if order.stop_price else None,
        }
        # Extract child order IDs for bracket orders
        if hasattr(order, "legs") and order.legs:
            for leg in order.legs:
                leg_type = leg.type.value if leg.type else ""
                if "limit" in leg_type:
                    result["tp_order_id"] = str(leg.id)
                elif "stop" in leg_type:
                    result["sl_order_id"] = str(leg.id)
        return result

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        take_profit_price: float,
        stop_loss_price: float,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict:
        """
        Place a bracket order (entry + take-profit + stop-loss in one atomic order).
        Stocks only — options don't support bracket orders on Alpaca.

        Args:
            symbol: Stock ticker
            qty: Number of shares (whole numbers only for bracket)
            side: 'buy' or 'sell'
            take_profit_price: Limit price for the take-profit leg
            stop_loss_price: Stop price for the stop-loss leg
            limit_price: If provided, entry is a limit order; otherwise market
            time_in_force: 'day' or 'gtc'
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            tp = TakeProfitRequest(limit_price=round(take_profit_price, 2))
            sl = StopLossRequest(stop_price=round(stop_loss_price, 2))

            if limit_price:
                request = LimitOrderRequest(
                    symbol=symbol.upper(),
                    qty=qty,
                    side=self._parse_side(side),
                    limit_price=round(limit_price, 2),
                    time_in_force=self._resolve_tif(time_in_force),
                    order_class=OrderClass.BRACKET,
                    take_profit=tp,
                    stop_loss=sl,
                )
            else:
                request = MarketOrderRequest(
                    symbol=symbol.upper(),
                    qty=qty,
                    side=self._parse_side(side),
                    time_in_force=self._resolve_tif(time_in_force),
                    order_class=OrderClass.BRACKET,
                    take_profit=tp,
                    stop_loss=sl,
                )

            order = self._client.submit_order(request)
            logger.info(
                f"Bracket order placed: {side.upper()} {qty} {symbol} "
                f"TP=${take_profit_price} SL=${stop_loss_price} (ID: {order.id})"
            )
            return self._format_order_result(order)

        except Exception as e:
            logger.error(f"Error placing bracket order for {symbol}: {e}")
            return {"error": str(e)}

    def place_stop_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_price: float,
        time_in_force: str = "day",
    ) -> Dict:
        """Place a stop (market) order. Triggers market sell/buy when stop_price is hit."""
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            request = StopOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=self._parse_side(side),
                stop_price=round(stop_price, 2),
                time_in_force=self._resolve_tif(time_in_force),
            )
            order = self._client.submit_order(request)
            logger.info(f"Stop order placed: {side.upper()} {qty} {symbol} @ stop ${stop_price} (ID: {order.id})")
            return self._format_order_result(order)

        except Exception as e:
            logger.error(f"Error placing stop order for {symbol}: {e}")
            return {"error": str(e)}

    def place_trailing_stop_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        trail_percent: Optional[float] = None,
        trail_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Dict:
        """
        Place a trailing stop order.

        Args:
            trail_percent: Trail by this percentage (e.g., 5.0 for 5%)
            trail_price: Trail by this dollar amount (e.g., 2.00 for $2)
            Exactly one of trail_percent or trail_price must be provided.
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            kwargs = {
                "symbol": symbol.upper(),
                "qty": qty,
                "side": self._parse_side(side),
                "time_in_force": self._resolve_tif(time_in_force),
            }
            if trail_percent is not None:
                kwargs["trail_percent"] = trail_percent
            elif trail_price is not None:
                kwargs["trail_price"] = trail_price
            else:
                return {"error": "Either trail_percent or trail_price must be provided"}

            request = TrailingStopOrderRequest(**kwargs)
            order = self._client.submit_order(request)
            trail_desc = f"{trail_percent}%" if trail_percent else f"${trail_price}"
            logger.info(f"Trailing stop placed: {side.upper()} {qty} {symbol} trail {trail_desc} (ID: {order.id})")
            return self._format_order_result(order)

        except Exception as e:
            logger.error(f"Error placing trailing stop for {symbol}: {e}")
            return {"error": str(e)}

    def place_notional_order(
        self,
        symbol: str,
        notional: float,
        side: str,
        time_in_force: str = "day",
    ) -> Dict:
        """
        Place a market order by dollar amount (fractional shares).
        Uses Alpaca's notional parameter instead of qty.

        Args:
            symbol: Stock ticker
            notional: Dollar amount to invest (e.g., 100.0 for $100)
            side: 'buy' or 'sell'
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            request = MarketOrderRequest(
                symbol=symbol.upper(),
                notional=round(notional, 2),
                side=self._parse_side(side),
                time_in_force=self._resolve_tif(time_in_force),
            )
            order = self._client.submit_order(request)
            logger.info(f"Notional order placed: {side.upper()} ${notional} of {symbol} (ID: {order.id})")
            return self._format_order_result(order)

        except Exception as e:
            logger.error(f"Error placing notional order for {symbol}: {e}")
            return {"error": str(e)}

    def place_option_order(
        self,
        option_symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        time_in_force: str = "day",
    ) -> Dict:
        """
        Place an option order. Always uses limit orders (best practice for options).
        Options TIF must be 'day' on Alpaca (no GTC for options).

        Args:
            option_symbol: Full OCC symbol (e.g., 'AAPL250117C00150000')
            qty: Number of contracts (whole numbers only)
            side: 'buy' or 'sell'
            limit_price: Limit price per share (not per contract)
        """
        if not self.is_available:
            return {"error": "Trading service not available"}

        try:
            request = LimitOrderRequest(
                symbol=option_symbol,
                qty=int(qty),
                side=self._parse_side(side),
                limit_price=round(limit_price, 2),
                time_in_force=TimeInForce.DAY,  # Options must be DAY on Alpaca
            )
            order = self._client.submit_order(request)
            logger.info(
                f"Option order placed: {side.upper()} {qty}x {option_symbol} "
                f"@ ${limit_price} (ID: {order.id})"
            )
            return self._format_order_result(order)

        except Exception as e:
            logger.error(f"Error placing option order for {option_symbol}: {e}")
            return {"error": str(e)}

    # =========================================================================
    # Kill Switch Methods
    # =========================================================================

    def cancel_all_orders(self) -> Dict:
        """Cancel ALL open orders. Used by kill switch."""
        if not self.is_available:
            return {"error": "Trading service not available", "count": 0}

        try:
            cancelled = self._client.cancel_orders()
            count = len(cancelled) if cancelled else 0
            logger.warning(f"KILL SWITCH: Cancelled {count} open orders")
            return {"success": True, "count": count}
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return {"error": str(e), "count": 0}

    def close_all_positions(self, cancel_orders: bool = True) -> Dict:
        """Close ALL open positions. Used by kill switch."""
        if not self.is_available:
            return {"error": "Trading service not available", "count": 0}

        try:
            closed = self._client.close_all_positions(cancel_orders=cancel_orders)
            count = len(closed) if closed else 0
            logger.warning(f"KILL SWITCH: Closed {count} positions")
            return {"success": True, "count": count}
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return {"error": str(e), "count": 0}

    def get_clock(self) -> Optional[Dict]:
        """Get market clock (is_open, next_open, next_close)."""
        if not self.is_available:
            return None
        try:
            clock = self._client.get_clock()
            return {
                "is_open": clock.is_open,
                "next_open": clock.next_open.isoformat() if clock.next_open else None,
                "next_close": clock.next_close.isoformat() if clock.next_close else None,
                "timestamp": clock.timestamp.isoformat() if clock.timestamp else None,
            }
        except Exception as e:
            logger.error(f"Alpaca get_clock failed: {e}")
            return None

    # =========================================================================
    # Original Methods (continued)
    # =========================================================================

    def get_orders(
        self,
        status: str = "open",
        limit: int = 50,
        symbols: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get orders with optional filters.

        Args:
            status: 'open', 'closed', 'all'
            limit: Max number of orders to return
            symbols: Filter by symbols (optional)
        """
        if not self.is_available:
            return []

        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            status_map = {
                "open": QueryOrderStatus.OPEN,
                "closed": QueryOrderStatus.CLOSED,
                "all": QueryOrderStatus.ALL,
            }

            request = GetOrdersRequest(
                status=status_map.get(status.lower(), QueryOrderStatus.OPEN),
                limit=limit,
                symbols=symbols
            )

            orders = self._client.get_orders(request)

            return [
                {
                    "order_id": str(o.id),
                    "symbol": o.symbol,
                    "side": o.side.value,
                    "type": o.type.value,
                    "qty": float(o.qty),
                    "status": o.status.value,
                    "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
                    "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                }
                for o in orders
            ]

        except Exception as e:
            logger.error(f"Alpaca get_orders failed (returning empty list): {e}")
            return []


# Singleton instance
alpaca_trading_service = AlpacaTradingService()
