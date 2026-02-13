"""
Robinhood broker integration service using robin_stocks library.
Handles authentication, portfolio data, and positions sync.
"""
import logging
import os
import pickle
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

# Check if robin_stocks is available
try:
    import robin_stocks.robinhood as rh
    ROBINHOOD_AVAILABLE = True
except ImportError:
    logger.warning("robin_stocks not installed. Install with: pip install robin_stocks")
    ROBINHOOD_AVAILABLE = False

# robin_stocks default pickle file location
_PICKLE_PATH = Path.home() / ".tokens" / "robinhood.pickle"


def _validate_pickle_file() -> dict:
    """
    Validate the robin_stocks session pickle file.

    Returns:
        dict with keys: exists, valid, error, path
    """
    result = {"exists": False, "valid": False, "error": None, "path": str(_PICKLE_PATH)}

    if not _PICKLE_PATH.exists():
        result["error"] = "Pickle file does not exist"
        return result

    result["exists"] = True

    # Check file size (empty or suspiciously small = corrupted)
    file_size = _PICKLE_PATH.stat().st_size
    if file_size == 0:
        result["error"] = "Pickle file is empty (0 bytes)"
        return result

    # Try to load and validate the pickle contents
    try:
        with open(_PICKLE_PATH, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and "access_token" in data:
            result["valid"] = True
        else:
            result["error"] = f"Pickle file has unexpected structure (type={type(data).__name__})"
    except (pickle.UnpicklingError, EOFError, ValueError) as e:
        result["error"] = f"Pickle file is corrupted: {e}"
    except Exception as e:
        result["error"] = f"Could not read pickle file: {e}"

    return result


def _remove_corrupt_pickle() -> bool:
    """Remove a corrupted pickle file so a fresh login can proceed."""
    try:
        if _PICKLE_PATH.exists():
            _PICKLE_PATH.unlink()
            logger.info("Removed corrupted Robinhood pickle file")
            return True
    except OSError as e:
        logger.error(f"Failed to remove corrupted pickle file: {e}")
    return False


class RobinhoodService:
    """
    Service for interacting with Robinhood accounts.
    Uses robin_stocks library for API access.
    """

    def __init__(self):
        self._logged_in = False
        self._username = None
        self._device_token = None

    @property
    def is_available(self) -> bool:
        """Check if robin_stocks library is installed"""
        return ROBINHOOD_AVAILABLE

    @property
    def is_logged_in(self) -> bool:
        """Check if currently logged in to Robinhood"""
        return self._logged_in and ROBINHOOD_AVAILABLE

    def validate_session(self) -> dict:
        """
        Validate the current session state including pickle file health.

        Returns:
            dict with: logged_in, pickle_valid, pickle_exists, error
        """
        pickle_info = _validate_pickle_file()
        return {
            "logged_in": self.is_logged_in,
            "pickle_exists": pickle_info["exists"],
            "pickle_valid": pickle_info["valid"],
            "pickle_path": pickle_info["path"],
            "error": pickle_info["error"],
        }

    def login(
        self,
        username: str,
        password: str,
        mfa_code: Optional[str] = None,
        device_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Login to Robinhood account.

        Args:
            username: Robinhood username (email)
            password: Account password
            mfa_code: 2FA code if MFA is enabled
            device_token: Stored device token for MFA bypass

        Returns:
            Dict with login status and any required actions
        """
        if not ROBINHOOD_AVAILABLE:
            return {
                "success": False,
                "error": "robin_stocks library not installed",
                "requires_mfa": False,
            }

        try:
            # Build login kwargs
            # robin_stocks uses pickle files for session persistence
            login_kwargs = {
                "username": username,
                "password": password,
                "expiresIn": 86400 * 30,  # 30 days
                "store_session": True,
            }

            if mfa_code:
                login_kwargs["mfa_code"] = mfa_code

            # Attempt login
            login_result = rh.login(**login_kwargs)

            if login_result:
                self._logged_in = True
                self._username = username
                # Generate a device token for our own tracking
                self._device_token = device_token or str(uuid.uuid4())

                return {
                    "success": True,
                    "device_token": self._device_token,
                    "requires_mfa": False,
                }
            else:
                return {
                    "success": False,
                    "error": "Login failed. Check credentials or MFA code.",
                    "requires_mfa": True,
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Robinhood login error: {error_msg}")

            # Check if MFA is required
            if "mfa" in error_msg.lower() or "verification" in error_msg.lower():
                return {
                    "success": False,
                    "error": "MFA code required",
                    "requires_mfa": True,
                }

            return {
                "success": False,
                "error": error_msg,
                "requires_mfa": False,
            }

    def logout(self) -> bool:
        """Logout from Robinhood"""
        if not ROBINHOOD_AVAILABLE:
            return False

        try:
            rh.logout()
            self._logged_in = False
            self._username = None
            return True
        except Exception as e:
            logger.error(f"Robinhood logout error: {e}")
            return False

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get account information including buying power and portfolio value.
        """
        if not self.is_logged_in:
            return None

        try:
            # Get account profile
            profile = rh.profiles.load_account_profile()

            # Get portfolio data
            portfolio = rh.profiles.load_portfolio_profile()

            # Get account holdings
            holdings = rh.account.build_holdings()

            # Calculate totals
            equity = float(portfolio.get("equity", 0) or 0)
            extended_hours_equity = float(portfolio.get("extended_hours_equity", 0) or equity)

            return {
                "account_type": profile.get("type", "unknown"),
                "buying_power": float(profile.get("buying_power", 0) or 0),
                "cash": float(profile.get("cash", 0) or 0),
                "cash_held_for_orders": float(profile.get("cash_held_for_orders", 0) or 0),
                "portfolio_value": extended_hours_equity,
                "equity": equity,
                "market_value": float(portfolio.get("market_value", 0) or 0),
                "total_positions": len(holdings) if holdings else 0,
                "created_at": profile.get("created_at"),
                "account_number": profile.get("account_number"),
            }
        except Exception as e:
            logger.error(f"Error getting Robinhood account info: {e}")
            return None

    def get_positions(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get all current stock positions.
        Returns None on API failure (vs [] for no positions).
        """
        if not self.is_logged_in:
            return None

        try:
            holdings = rh.account.build_holdings()
            positions = []

            for symbol, data in holdings.items():
                try:
                    position = {
                        "symbol": symbol,
                        "name": data.get("name", ""),
                        "quantity": float(data.get("quantity", 0) or 0),
                        "average_cost": float(data.get("average_buy_price", 0) or 0),
                        "current_price": float(data.get("price", 0) or 0),
                        "market_value": float(data.get("equity", 0) or 0),
                        "unrealized_pl": float(data.get("equity_change", 0) or 0),
                        "unrealized_pl_percent": float(data.get("percent_change", 0) or 0),
                        "day_change_percent": float(data.get("percentage", 0) or 0),
                        "asset_type": "stock",
                    }
                    positions.append(position)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing position for {symbol}: {e}")
                    continue

            return positions

        except Exception as e:
            logger.error(f"Error getting Robinhood positions: {e}")
            return None

    def get_option_positions(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get all current option positions with P/L.
        Returns None on API failure (vs [] for no positions).
        Uses Robinhood's native equity calculations when available.
        """
        if not self.is_logged_in:
            return []

        try:
            options = rh.options.get_open_option_positions()
            positions = []

            for option in options:
                try:
                    # Get option chain info
                    chain_symbol = option.get("chain_symbol", "")
                    option_type = option.get("type", "").lower()
                    strike = float(option.get("strike_price", 0) or 0)
                    expiration = option.get("expiration_date", "")
                    quantity = float(option.get("quantity", 0) or 0)

                    # Trade value multiplier (usually 100 for standard options)
                    multiplier = float(option.get("trade_value_multiplier", 100) or 100)

                    # IMPORTANT: Robinhood's average_price is the TOTAL cost per contract
                    # e.g., if you paid $4.70/share, average_price = 470 (= $4.70 × 100)
                    # This is NOT the per-share premium!
                    avg_price_total_per_contract = float(option.get("average_price", 0) or 0)

                    # Calculate per-share premium for display
                    avg_price_per_share = avg_price_total_per_contract / multiplier if multiplier > 0 else 0

                    # Get option ID from the option URL if not directly available
                    option_id = option.get("option_id", "")
                    if not option_id and option.get("option"):
                        # Extract ID from URL like https://api.robinhood.com/options/instruments/{id}/
                        option_url = option.get("option", "")
                        parts = option_url.rstrip("/").split("/")
                        option_id = parts[-1] if parts else ""

                    # Get current market data for live pricing (returns per-share price)
                    current_price_per_share = avg_price_per_share  # Default to avg if market data fails
                    if option_id:
                        try:
                            market_data = rh.options.get_option_market_data_by_id(option_id)
                            if market_data and len(market_data) > 0:
                                md = market_data[0]
                                # Prefer mark_price (mid of bid/ask), fallback to others
                                current_price_per_share = float(
                                    md.get("mark_price") or
                                    md.get("adjusted_mark_price") or
                                    md.get("last_trade_price") or
                                    avg_price_per_share or 0
                                )
                        except Exception as e:
                            logger.debug(f"Could not get market data for option {option_id}: {e}")

                    # Calculate total values
                    # cost_basis = total_per_contract × quantity (DON'T multiply by 100 again!)
                    # e.g., $470 (total per contract) × 2 contracts = $940
                    cost_basis = avg_price_total_per_contract * quantity

                    # market_value = per_share_price × quantity × 100
                    # e.g., $5.28/share × 2 contracts × 100 = $1,056
                    market_value = current_price_per_share * quantity * multiplier

                    # P/L calculation
                    unrealized_pl = market_value - cost_basis
                    unrealized_pl_percent = 0
                    if cost_basis > 0:
                        unrealized_pl_percent = (unrealized_pl / cost_basis) * 100

                    position = {
                        "symbol": chain_symbol,
                        "name": f"{chain_symbol} ${strike} {option_type.upper()} {expiration}",
                        "quantity": quantity,
                        "average_cost": avg_price_per_share,  # Per-share premium (e.g., $4.70)
                        "current_price": current_price_per_share,  # Per-share current price (e.g., $5.28)
                        "market_value": market_value,  # Total market value
                        "cost_basis": cost_basis,  # Total cost paid
                        "unrealized_pl": unrealized_pl,
                        "unrealized_pl_percent": unrealized_pl_percent,
                        "asset_type": "option",
                        "option_type": option_type,
                        "strike_price": strike,
                        "expiration_date": expiration,
                    }
                    positions.append(position)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing option position: {e}")
                    continue

            return positions

        except Exception as e:
            logger.error(f"Error getting Robinhood option positions: {e}")
            return None

    def get_crypto_positions(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get all current crypto positions with P/L.
        Returns None on API failure (vs [] for no positions).
        Uses robin_stocks crypto module.
        """
        if not self.is_logged_in:
            return None

        try:
            crypto_holdings = rh.crypto.get_crypto_positions()
            positions = []

            for holding in crypto_holdings:
                try:
                    currency = holding.get("currency", {})
                    symbol = currency.get("code", "") if isinstance(currency, dict) else str(currency)
                    if not symbol:
                        continue

                    quantity = float(holding.get("quantity", 0) or 0)
                    if quantity <= 0:
                        continue

                    cost_basis = float(holding.get("cost_bases", [{}])[0].get("direct_cost_basis", 0) or 0) if holding.get("cost_bases") else 0
                    avg_cost = cost_basis / quantity if quantity > 0 else 0

                    # Get live quote for current price
                    current_price = avg_cost  # Default fallback
                    try:
                        quote = rh.crypto.get_crypto_quote(symbol)
                        if quote:
                            current_price = float(quote.get("mark_price") or quote.get("bid_price") or avg_cost or 0)
                    except Exception as e:
                        logger.debug(f"Could not get crypto quote for {symbol}: {e}")

                    market_value = current_price * quantity
                    unrealized_pl = market_value - cost_basis if cost_basis > 0 else 0
                    unrealized_pl_percent = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0

                    position = {
                        "symbol": symbol,
                        "name": currency.get("name", symbol) if isinstance(currency, dict) else symbol,
                        "quantity": quantity,
                        "average_cost": avg_cost,
                        "current_price": current_price,
                        "market_value": market_value,
                        "cost_basis": cost_basis,
                        "unrealized_pl": unrealized_pl,
                        "unrealized_pl_percent": unrealized_pl_percent,
                        "asset_type": "crypto",
                    }
                    positions.append(position)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing crypto position: {e}")
                    continue

            return positions

        except Exception as e:
            logger.error(f"Error getting Robinhood crypto positions: {e}")
            return None

    def get_all_positions(self) -> Dict[str, Any]:
        """
        Get all positions (stocks, options, and crypto) with per-type success flags.

        Returns dict with:
          - stock/option/crypto: list of positions or None if fetch failed
          - combined: all successfully-fetched positions merged
        """
        stock_positions = self.get_positions()
        option_positions = self.get_option_positions()
        crypto_positions = self.get_crypto_positions()

        combined = []
        if stock_positions is not None:
            combined.extend(stock_positions)
        if option_positions is not None:
            combined.extend(option_positions)
        if crypto_positions is not None:
            combined.extend(crypto_positions)

        return {
            "stock": stock_positions,
            "option": option_positions,
            "crypto": crypto_positions,
            "combined": combined,
        }

    def get_portfolio_history(self, interval: str = "day", span: str = "month") -> Optional[Dict[str, Any]]:
        """
        Get historical portfolio values.

        Args:
            interval: Data interval - day, week
            span: Time span - day, week, month, 3month, year, 5year, all

        Returns:
            Dict with dates and equity values
        """
        if not self.is_logged_in:
            return None

        try:
            historicals = rh.profiles.load_portfolio_profile(info='historicals')

            if not historicals:
                # Fallback to load_portfolio_profile
                portfolio = rh.profiles.load_portfolio_profile()
                return {
                    "current_value": float(portfolio.get("equity", 0) or 0),
                    "history": [],
                }

            return {
                "history": historicals,
            }

        except Exception as e:
            logger.error(f"Error getting portfolio history: {e}")
            return None

    def get_dividends(self) -> List[Dict[str, Any]]:
        """Get dividend history"""
        if not self.is_logged_in:
            return []

        try:
            dividends = rh.account.get_dividends()
            return [
                {
                    "symbol": d.get("instrument", "").split("/")[-2] if d.get("instrument") else "",
                    "amount": float(d.get("amount", 0) or 0),
                    "rate": float(d.get("rate", 0) or 0),
                    "position": float(d.get("position", 0) or 0),
                    "payable_date": d.get("payable_date"),
                    "state": d.get("state"),
                }
                for d in dividends
            ]
        except Exception as e:
            logger.error(f"Error getting dividends: {e}")
            return []

    def get_recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent order history"""
        if not self.is_logged_in:
            return []

        try:
            orders = rh.orders.get_all_stock_orders()[:limit]
            return [
                {
                    "id": o.get("id"),
                    "symbol": o.get("symbol", ""),
                    "side": o.get("side"),
                    "type": o.get("type"),
                    "quantity": float(o.get("quantity", 0) or 0),
                    "price": float(o.get("average_price", 0) or o.get("price", 0) or 0),
                    "state": o.get("state"),
                    "created_at": o.get("created_at"),
                    "executed_notional": o.get("executed_notional"),
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Get Robinhood watchlist"""
        if not self.is_logged_in:
            return []

        try:
            watchlist = rh.account.get_watchlist_by_name(name="Default")
            if not watchlist:
                return []

            return [
                {
                    "symbol": item.get("symbol", ""),
                    "instrument": item.get("instrument"),
                }
                for item in watchlist
            ]
        except Exception as e:
            logger.error(f"Error getting watchlist: {e}")
            return []


# Singleton instance
_robinhood_service: Optional[RobinhoodService] = None


def get_robinhood_service() -> RobinhoodService:
    """Get the singleton Robinhood service instance"""
    global _robinhood_service
    if _robinhood_service is None:
        _robinhood_service = RobinhoodService()
    return _robinhood_service
