"""
Position Sizer — calculate how many shares/contracts to trade.

Three sizing modes:
  1. Fixed Dollar: Use max_per_*_trade directly
  2. Percentage of Portfolio: Allocate X% of equity
  3. Risk-Based: Dollar risk / stop distance = shares

All modes enforce the per-trade cap as a hard ceiling.
"""
import math
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from app.models.bot_config import BotConfiguration, SizingMode
from app.models.trading_signal import TradingSignal


@dataclass
class SizeResult:
    """Output of position sizing calculation."""
    quantity: float                # Shares or contracts
    notional: float                # Dollar value of the position
    is_fractional: bool = False    # True if fractional shares (stocks only)
    is_notional_order: bool = False  # True if should use notional order (fractional)
    asset_type: str = "stock"
    capped_reason: str = ""        # Non-empty if size was reduced to fit limits
    rejected: bool = False         # True if position cannot be sized (e.g., too expensive)
    reject_reason: str = ""


class PositionSizer:
    """Calculate position size based on bot configuration."""

    def calculate_size(
        self,
        signal: TradingSignal,
        bot_config: BotConfiguration,
        account: dict,
        current_price: float,
        asset_type: str = "stock",
        option_premium: Optional[float] = None,
    ) -> SizeResult:
        """
        Calculate position size.

        Args:
            signal: TradingSignal with entry_price, stop_loss, etc.
            bot_config: User configuration
            account: Alpaca account dict
            current_price: Current price of the underlying stock
            asset_type: "stock" or "option"
            option_premium: Per-share premium for options (multiply by 100 for contract cost)
        """
        if current_price <= 0:
            return SizeResult(
                quantity=0, notional=0, asset_type=asset_type,
                rejected=True, reject_reason="Invalid current price",
            )

        equity = account.get("equity", 0)

        # Determine dollar budget based on sizing mode
        if asset_type == "option":
            max_budget = bot_config.max_per_options_trade
        else:
            max_budget = bot_config.max_per_stock_trade

        budget = self._calculate_budget(
            bot_config, signal, equity, max_budget, current_price,
        )

        # Apply hard cap
        capped_reason = ""
        if budget > max_budget:
            capped_reason = f"Capped from ${budget:.2f} to max ${max_budget:.2f}"
            budget = max_budget

        # Size the position
        if asset_type == "option":
            return self._size_option(
                budget, option_premium, bot_config, capped_reason,
            )
        else:
            return self._size_stock(
                budget, current_price, capped_reason,
            )

    def _calculate_budget(
        self,
        config: BotConfiguration,
        signal: TradingSignal,
        equity: float,
        max_budget: float,
        current_price: float,
    ) -> float:
        """Determine dollar budget based on sizing mode."""

        if config.sizing_mode == SizingMode.FIXED_DOLLAR.value:
            return max_budget

        elif config.sizing_mode == SizingMode.PCT_PORTFOLIO.value:
            return equity * (config.max_portfolio_allocation_pct / 100)

        elif config.sizing_mode == SizingMode.RISK_BASED.value:
            # Risk amount = equity * risk_pct_per_trade%
            risk_amount = equity * (config.risk_pct_per_trade / 100)

            # Need stop_loss to calculate stop distance
            entry = signal.entry_price or current_price
            stop = signal.stop_loss
            if not stop or stop <= 0:
                # Fallback: use default stop loss percentage
                stop = entry * (1 - config.default_stop_loss_pct / 100)

            stop_distance = abs(entry - stop)
            if stop_distance <= 0:
                logger.warning(
                    f"Zero stop distance for {signal.symbol}, "
                    f"falling back to fixed dollar"
                )
                return max_budget

            # Shares = risk_amount / stop_distance
            shares = risk_amount / stop_distance
            budget = shares * current_price

            logger.debug(
                f"Risk-based sizing: risk=${risk_amount:.2f}, "
                f"stop_dist=${stop_distance:.2f}, "
                f"shares={shares:.2f}, budget=${budget:.2f}"
            )
            return budget

        # Fallback
        return max_budget

    def _size_stock(
        self,
        budget: float,
        current_price: float,
        capped_reason: str,
    ) -> SizeResult:
        """Size a stock position. Supports fractional shares."""
        shares = budget / current_price

        if shares < 0.001:
            return SizeResult(
                quantity=0, notional=0, asset_type="stock",
                rejected=True,
                reject_reason=f"Budget ${budget:.2f} too small for {current_price}",
            )

        # Decide fractional vs whole
        if shares >= 1.0 and shares == int(shares):
            # Exact whole number
            return SizeResult(
                quantity=int(shares),
                notional=int(shares) * current_price,
                is_fractional=False,
                is_notional_order=False,
                asset_type="stock",
                capped_reason=capped_reason,
            )
        elif shares < 1.0:
            # Fractional — use notional order
            return SizeResult(
                quantity=round(shares, 6),
                notional=round(budget, 2),
                is_fractional=True,
                is_notional_order=True,
                asset_type="stock",
                capped_reason=capped_reason,
            )
        else:
            # > 1 share but not whole — round down to whole shares
            # (Alpaca supports fractional with notional, but bracket orders need whole)
            whole_shares = math.floor(shares)
            return SizeResult(
                quantity=whole_shares,
                notional=whole_shares * current_price,
                is_fractional=False,
                is_notional_order=False,
                asset_type="stock",
                capped_reason=capped_reason,
            )

    def _size_option(
        self,
        budget: float,
        option_premium: Optional[float],
        config: BotConfiguration,
        capped_reason: str,
    ) -> SizeResult:
        """Size an option position. Must be whole contracts."""
        if option_premium is None or option_premium <= 0:
            return SizeResult(
                quantity=0, notional=0, asset_type="option",
                rejected=True,
                reject_reason="Option premium not available for sizing",
            )

        contract_cost = option_premium * 100  # 1 contract = 100 shares
        contracts = int(budget / contract_cost)

        if contracts < 1:
            return SizeResult(
                quantity=0, notional=0, asset_type="option",
                rejected=True,
                reject_reason=(
                    f"Budget ${budget:.2f} cannot buy 1 contract "
                    f"(cost ${contract_cost:.2f})"
                ),
            )

        return SizeResult(
            quantity=contracts,
            notional=contracts * contract_cost,
            is_fractional=False,
            is_notional_order=False,
            asset_type="option",
            capped_reason=capped_reason,
        )
