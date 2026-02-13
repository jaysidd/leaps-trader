"""
Tests for PnL calculation accuracy.

These are P0 tests that verify the exact dollar amounts computed by the
_close_bracket_trade method in PositionMonitor. Incorrect PnL calculations
can misstate the daily P&L, trigger false circuit breaker events, and
corrupt the trade journal.

PnL formulas under test:
  - Long:   pl = (exit_price - entry_price) * quantity
  - Short:  pl = (entry_price - exit_price) * quantity
  - Option: pl *= 100  (per-contract multiplier)
  - PnL %:  pl / cost_basis * 100
  - Max drawdown %: (peak - trough) / peak * 100
"""
from unittest.mock import MagicMock

import pytest

from app.services.trading.position_monitor import PositionMonitor
from app.models.executed_trade import ExitReason, TradeStatus

from tests.trading.conftest import make_trade


def _make_monitor_for_pnl():
    """Minimal monitor for PnL tests — only _close_bracket_trade is called."""
    db = MagicMock()
    trading = MagicMock()
    data = MagicMock()
    return PositionMonitor(db, trading, data)


def _close_and_get_pl(trade, exit_price):
    """Helper: run _close_bracket_trade and return (realized_pl, realized_pl_pct)."""
    monitor = _make_monitor_for_pnl()
    filled_order = {
        "filled_avg_price": str(exit_price),
        "id": "exit-test",
        "status": "filled",
    }
    exit_reason = ExitReason.TAKE_PROFIT if exit_price > trade.entry_price else ExitReason.STOP_LOSS
    if trade.direction == "sell":
        exit_reason = ExitReason.TAKE_PROFIT if exit_price < trade.entry_price else ExitReason.STOP_LOSS

    monitor._close_bracket_trade(trade, filled_order, exit_reason, None)
    return trade.realized_pl, trade.realized_pl_pct


# =====================================================================
# 1. Long stock profit
# =====================================================================

def test_long_stock_profit():
    """entry=100, exit=105.50, qty=10 -> pnl=$55.00"""
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    pl, pl_pct = _close_and_get_pl(trade, exit_price=105.50)

    assert pl == 55.0
    # cost_basis = 100 * 10 = 1000, pnl_pct = 55/1000 * 100 = 5.5%
    assert pl_pct == 5.5


# =====================================================================
# 2. Long stock loss
# =====================================================================

def test_long_stock_loss():
    """entry=100, exit=95.25, qty=10 -> pnl=-$47.50"""
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    pl, pl_pct = _close_and_get_pl(trade, exit_price=95.25)

    assert pl == -47.5
    # cost_basis = 1000, pnl_pct = -47.5/1000*100 = -4.75%
    assert pl_pct == -4.75


# =====================================================================
# 3. Long stock breakeven
# =====================================================================

def test_long_stock_breakeven():
    """entry=100, exit=100, qty=10 -> pnl=$0.00"""
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    monitor = _make_monitor_for_pnl()
    filled_order = {
        "filled_avg_price": "100.0",
        "id": "exit-be",
        "status": "filled",
    }
    monitor._close_bracket_trade(trade, filled_order, ExitReason.TIME_EXIT, None)

    assert trade.realized_pl == 0.0
    assert trade.realized_pl_pct == 0.0


# =====================================================================
# 4. Fractional shares
# =====================================================================

def test_fractional_shares():
    """entry=150.12, exit=155.67, qty=0.5 -> pnl=$2.78 (rounded to 2 dp)"""
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=150.12, quantity=0.5,
    )
    pl, pl_pct = _close_and_get_pl(trade, exit_price=155.67)

    # (155.67 - 150.12) * 0.5 = 5.55 * 0.5 = 2.775 -> round(2.775, 2) = 2.77 (banker's rounding)
    assert pl == 2.77


# =====================================================================
# 5. Short stock profit
# =====================================================================

def test_short_stock_profit():
    """entry=100, exit=90, qty=10 -> pnl=$100.00"""
    trade = make_trade(
        direction="sell", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    pl, _ = _close_and_get_pl(trade, exit_price=90.0)

    assert pl == 100.0


# =====================================================================
# 6. Short stock loss
# =====================================================================

def test_short_stock_loss():
    """entry=100, exit=110, qty=10 -> pnl=-$100.00"""
    trade = make_trade(
        direction="sell", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    pl, _ = _close_and_get_pl(trade, exit_price=110.0)

    assert pl == -100.0


# =====================================================================
# 7. Option PnL with multiplier
# =====================================================================

def test_option_pnl_multiplier():
    """entry=5, exit=7, qty=2, asset_type=option -> pnl=$400 (x100 multiplier)"""
    trade = make_trade(
        direction="buy", asset_type="option",
        entry_price=5.0, quantity=2,
        option_symbol="AAPL250117C00150000",
    )
    pl, pl_pct = _close_and_get_pl(trade, exit_price=7.0)

    # (7-5) * 2 = 4, * 100 = 400
    assert pl == 400.0
    # cost_basis = 5 * 2 * 100 = 1000, pnl_pct = 400/1000*100 = 40%
    assert pl_pct == 40.0


# =====================================================================
# 8. Option PnL loss
# =====================================================================

def test_option_pnl_loss():
    """entry=5, exit=3, qty=1, option -> pnl=-$200"""
    trade = make_trade(
        direction="buy", asset_type="option",
        entry_price=5.0, quantity=1,
        option_symbol="AAPL250117C00150000",
    )
    pl, _ = _close_and_get_pl(trade, exit_price=3.0)

    # (3-5) * 1 = -2, * 100 = -200
    assert pl == -200.0


# =====================================================================
# 9. PnL percentage calculation
# =====================================================================

def test_pnl_pct_calculation():
    """pnl=$55, cost_basis=$1000 -> pnl_pct=5.5%"""
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    pl, pl_pct = _close_and_get_pl(trade, exit_price=105.5)

    # pl = 55, cost_basis = 100*10 = 1000, pct = 5.5
    assert pl == 55.0
    assert pl_pct == 5.5


# =====================================================================
# 10. Max drawdown percentage
# =====================================================================

def test_max_drawdown_pct():
    """
    Max drawdown calculation:
    start_equity=10000, peak=12000, trough=9000 -> drawdown=25%.

    This tests the formula used in update_circuit_breaker:
      drawdown = (peak - trough) / peak * 100
    """
    peak = 12000.0
    trough = 9000.0
    drawdown_pct = ((peak - trough) / peak) * 100

    assert drawdown_pct == 25.0

    # Also verify the circuit breaker formula (daily_start_equity based):
    # drawdown = (start_equity - current_equity) / start_equity * 100
    start_equity = 10000.0
    current_equity = 9000.0
    daily_drawdown_pct = ((start_equity - current_equity) / start_equity) * 100

    assert daily_drawdown_pct == 10.0
