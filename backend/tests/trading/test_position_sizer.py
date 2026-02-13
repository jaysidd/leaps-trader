"""
Tests for PositionSizer — position sizing calculations.

These are P0 tests that ensure the sizer correctly calculates share/contract
quantities, respects per-trade caps, handles edge cases (zero price, fractional
shares, expensive options), and picks the right sizing mode.
"""
import pytest

from app.services.trading.position_sizer import PositionSizer
from app.models.bot_config import SizingMode

from tests.trading.conftest import (
    make_bot_config, make_signal, make_account,
    SIZE_FIXED_DOLLAR, SIZE_PCT_PORTFOLIO, SIZE_RISK_BASED,
)


@pytest.fixture
def sizer():
    return PositionSizer()


# =====================================================================
# 1-2. Fixed dollar sizing (stocks)
# =====================================================================

def test_fixed_dollar_stock(sizer):
    """Fixed dollar: budget=$5000, price=$100 -> qty=50, notional=$5000."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=5000.0)
    signal = make_signal(entry_price=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    assert result.quantity == 50
    assert result.notional == 5000.0


def test_fixed_dollar_stock_floor(sizer):
    """Fixed dollar: price=$150, budget=$5000 -> qty=33 (floor), notional=$4950."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=5000.0)
    signal = make_signal(entry_price=150.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=150.0)

    assert result.rejected is False
    assert result.quantity == 33
    assert result.notional == 33 * 150.0


# =====================================================================
# 3. Percentage of portfolio sizing
# =====================================================================

def test_pct_portfolio_stock(sizer):
    """pct_portfolio: equity=$100000, allocation=5% -> budget=$5000."""
    config = make_bot_config(
        sizing_mode=SIZE_PCT_PORTFOLIO,
        max_portfolio_allocation_pct=5.0,
        max_per_stock_trade=10000.0,  # High cap so it doesn't interfere
    )
    signal = make_signal(entry_price=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    assert result.quantity == 50  # $5000 / $100 = 50
    assert result.notional == 5000.0


# =====================================================================
# 4-6. Risk-based sizing
# =====================================================================

def test_risk_based_stock(sizer):
    """Risk-based: equity=$100000, risk=1%, entry=$100, stop=$95 -> 200 shares.
    Budget=$20000, capped to max_per_stock_trade=$5000."""
    config = make_bot_config(
        sizing_mode=SIZE_RISK_BASED,
        risk_pct_per_trade=1.0,
        max_per_stock_trade=5000.0,
    )
    signal = make_signal(entry_price=100.0, stop_loss=95.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    # risk_amount = $1000, stop_distance = $5, shares = 200
    # budget = 200 * $100 = $20000, capped to $5000
    assert result.capped_reason != ""
    assert result.quantity == 50  # $5000 / $100 = 50 whole shares


def test_risk_based_zero_stop_distance_fallback(sizer):
    """Risk-based with entry==stop falls back to fixed dollar sizing."""
    config = make_bot_config(
        sizing_mode=SIZE_RISK_BASED,
        risk_pct_per_trade=1.0,
        max_per_stock_trade=1000.0,
    )
    signal = make_signal(entry_price=100.0, stop_loss=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    # Falls back to max_per_stock_trade = $1000, price=$100 -> 10 shares
    assert result.quantity == 10


def test_risk_based_no_stop_uses_default(sizer):
    """Risk-based with no stop_loss uses default_stop_loss_pct."""
    config = make_bot_config(
        sizing_mode=SIZE_RISK_BASED,
        risk_pct_per_trade=1.0,
        default_stop_loss_pct=10.0,
        max_per_stock_trade=50000.0,  # High so cap doesn't interfere
    )
    signal = make_signal(entry_price=100.0, stop_loss=None)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    # Fallback stop = 100 * (1 - 10/100) = 90, distance = 10
    # risk_amount = $1000, shares = 1000/10 = 100
    # budget = 100 * $100 = $10000
    assert result.quantity == 100
    assert result.notional == 10000.0


# =====================================================================
# 7-9. Fractional / whole share handling
# =====================================================================

def test_stock_fractional_shares(sizer):
    """Budget=$50, price=$150 -> is_fractional=True, is_notional_order=True."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=50.0)
    signal = make_signal(entry_price=150.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=150.0)

    assert result.rejected is False
    assert result.is_fractional is True
    assert result.is_notional_order is True
    assert result.quantity < 1.0


def test_stock_exact_whole_shares(sizer):
    """Budget=$1000, price=$100 -> qty=10, not fractional."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=1000.0)
    signal = make_signal(entry_price=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    assert result.quantity == 10
    assert result.is_fractional is False
    assert result.is_notional_order is False


def test_stock_rounds_down(sizer):
    """Budget=$1050, price=$100 -> qty=10 (floor), not 10.5."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=1050.0)
    signal = make_signal(entry_price=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    assert result.quantity == 10
    assert result.notional == 1000.0
    assert result.is_fractional is False


# =====================================================================
# 10-12. Edge cases — invalid price / tiny budget
# =====================================================================

def test_zero_price_rejected(sizer):
    """current_price=0 -> rejected with 'Invalid current price'."""
    config = make_bot_config()
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(signal, config, account, current_price=0)

    assert result.rejected is True
    assert "Invalid current price" in result.reject_reason


def test_negative_price_rejected(sizer):
    """current_price=-10 -> rejected with 'Invalid current price'."""
    config = make_bot_config()
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(signal, config, account, current_price=-10)

    assert result.rejected is True
    assert "Invalid current price" in result.reject_reason


def test_budget_too_small_rejected(sizer):
    """Budget=$0.01, price=$500 -> rejected (too small for a share)."""
    config = make_bot_config(sizing_mode=SIZE_FIXED_DOLLAR, max_per_stock_trade=0.01)
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(signal, config, account, current_price=500.0)

    assert result.rejected is True
    assert "too small" in result.reject_reason.lower()


# =====================================================================
# 13-15. Option sizing
# =====================================================================

def test_option_sizing(sizer):
    """Option: budget=$3000, premium=$5.00 -> contracts=6 (3000/500)."""
    config = make_bot_config(
        sizing_mode=SIZE_FIXED_DOLLAR,
        max_per_options_trade=3000.0,
    )
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(
        signal, config, account, current_price=150.0,
        asset_type="option", option_premium=5.0,
    )

    assert result.rejected is False
    assert result.quantity == 6   # 3000 / (5*100) = 6
    assert result.notional == 3000.0
    assert result.asset_type == "option"


def test_option_premium_too_expensive(sizer):
    """Option: budget=$300, premium=$5.00 -> contract_cost=$500 > budget -> rejected."""
    config = make_bot_config(
        sizing_mode=SIZE_FIXED_DOLLAR,
        max_per_options_trade=300.0,
    )
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(
        signal, config, account, current_price=150.0,
        asset_type="option", option_premium=5.0,
    )

    assert result.rejected is True
    assert "cannot buy 1 contract" in result.reject_reason.lower()


def test_option_no_premium_rejected(sizer):
    """Option: option_premium=None -> rejected."""
    config = make_bot_config(
        sizing_mode=SIZE_FIXED_DOLLAR,
        max_per_options_trade=3000.0,
    )
    signal = make_signal()
    account = make_account()

    result = sizer.calculate_size(
        signal, config, account, current_price=150.0,
        asset_type="option", option_premium=None,
    )

    assert result.rejected is True
    assert "premium not available" in result.reject_reason.lower()


# =====================================================================
# 16. Cap applied with reason
# =====================================================================

def test_cap_applied_with_reason(sizer):
    """Budget exceeds max -> capped, capped_reason non-empty."""
    config = make_bot_config(
        sizing_mode=SIZE_PCT_PORTFOLIO,
        max_portfolio_allocation_pct=50.0,  # 50% of $100k = $50k
        max_per_stock_trade=5000.0,         # But capped to $5000
    )
    signal = make_signal(entry_price=100.0)
    account = make_account(equity=100000.0)

    result = sizer.calculate_size(signal, config, account, current_price=100.0)

    assert result.rejected is False
    assert result.capped_reason != ""
    assert "Capped" in result.capped_reason
    assert result.quantity == 50  # $5000 / $100
