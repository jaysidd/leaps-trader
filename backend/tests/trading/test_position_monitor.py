"""
Tests for PositionMonitor — exit condition detection for open trades.

These are P0 tests that ensure stop losses, take profits, trailing stops,
EOD closes, option expiry, and roll alerts fire correctly. Incorrect exit
logic can cause catastrophic capital loss (e.g., a missed stop-loss) or
missed profit (e.g., a broken take-profit check).
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.trading.position_monitor import (
    PositionMonitor, ExitSignal, MonitorResult,
)
from app.models.executed_trade import ExitReason, TradeStatus

from tests.trading.conftest import (
    make_bot_config, make_bot_state, make_trade, make_account,
    TS_OPEN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monitor(mock_db, data_price=150.0, option_position_price=None):
    """Create a PositionMonitor with mocked dependencies."""
    trading_svc = MagicMock()
    trading_svc.get_position.return_value = (
        {"current_price": str(option_position_price)} if option_position_price else None
    )
    trading_svc.get_order.return_value = None
    trading_svc.get_all_positions.return_value = []
    trading_svc.get_clock.return_value = {
        "is_open": True,
        "next_close": "2025-01-15T16:00:00-05:00",
    }

    data_svc = MagicMock()
    data_svc.get_current_price.return_value = data_price

    return PositionMonitor(mock_db, trading_svc, data_svc)


# =====================================================================
# 1-3. Stop loss — long & short
# =====================================================================

def test_long_stop_loss_triggered(mock_db):
    """Long trade: SL=95, current=94 -> ExitSignal STOP_LOSS."""
    monitor = _make_monitor(mock_db, data_price=94.0)
    trade = make_trade(
        direction="buy", entry_price=100.0,
        stop_loss_price=95.0, take_profit_price=120.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.STOP_LOSS
    assert result.current_price == 94.0


def test_long_stop_loss_not_triggered(mock_db):
    """Long trade: SL=95, current=96 -> None (no exit)."""
    monitor = _make_monitor(mock_db, data_price=96.0)
    trade = make_trade(
        direction="buy", entry_price=100.0,
        stop_loss_price=95.0, take_profit_price=120.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is None


def test_short_stop_loss_triggered(mock_db):
    """Short trade: SL=105, current=106 -> ExitSignal STOP_LOSS."""
    monitor = _make_monitor(mock_db, data_price=106.0)
    trade = make_trade(
        direction="sell", entry_price=100.0,
        stop_loss_price=105.0, take_profit_price=80.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.STOP_LOSS


# =====================================================================
# 4-5. Take profit — long & short
# =====================================================================

def test_long_take_profit_triggered(mock_db):
    """Long trade: TP=120, current=121 -> ExitSignal TAKE_PROFIT."""
    monitor = _make_monitor(mock_db, data_price=121.0)
    trade = make_trade(
        direction="buy", entry_price=100.0,
        stop_loss_price=95.0, take_profit_price=120.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.TAKE_PROFIT


def test_short_take_profit_triggered(mock_db):
    """Short trade: TP=80, current=79 -> ExitSignal TAKE_PROFIT."""
    monitor = _make_monitor(mock_db, data_price=79.0)
    trade = make_trade(
        direction="sell", entry_price=100.0,
        stop_loss_price=105.0, take_profit_price=80.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.TAKE_PROFIT


# =====================================================================
# 6-8. Trailing stop
# =====================================================================

def test_long_trailing_stop_triggered(mock_db):
    """Long: trail=5%, high_water=110, current=104 -> trail_price=104.50, triggered."""
    monitor = _make_monitor(mock_db, data_price=104.0)
    trade = make_trade(
        direction="buy", entry_price=100.0,
        stop_loss_price=None, take_profit_price=None,
        trailing_stop_pct=5.0, trailing_stop_high_water=110.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.TRAILING_STOP
    assert result.trigger_price == 104.50  # 110 * (1 - 0.05)


def test_long_trailing_stop_high_water_updated(mock_db):
    """Long: trail=5%, high_water=100, current=110 -> high_water updated to 110, no exit."""
    monitor = _make_monitor(mock_db, data_price=110.0)
    trade = make_trade(
        direction="buy", entry_price=100.0,
        stop_loss_price=None, take_profit_price=None,
        trailing_stop_pct=5.0, trailing_stop_high_water=100.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is None
    assert trade.trailing_stop_high_water == 110.0


def test_short_trailing_stop_triggered(mock_db):
    """Short: trail=5%, high_water=90, current=95 -> trail_price=94.50, triggered."""
    monitor = _make_monitor(mock_db, data_price=95.0)
    trade = make_trade(
        direction="sell", entry_price=100.0,
        stop_loss_price=None, take_profit_price=None,
        trailing_stop_pct=5.0, trailing_stop_high_water=90.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.TRAILING_STOP
    assert result.trigger_price == 94.50  # 90 * (1 + 0.05)


# =====================================================================
# 9. Trailing stop — no entry price initializes from current
# =====================================================================

def test_trailing_stop_no_entry_price_initializes(mock_db):
    """No entry_price, no high_water -> initializes from current, logs warning."""
    monitor = _make_monitor(mock_db, data_price=100.0)
    trade = make_trade(
        direction="buy", entry_price=None,
        stop_loss_price=None, take_profit_price=None,
        trailing_stop_pct=5.0, trailing_stop_high_water=None,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    # Should not exit on first pass — just initializes high water
    assert result is None
    assert trade.trailing_stop_high_water == 100.0


# =====================================================================
# 10-11. EOD close — stocks vs options
# =====================================================================

def test_eod_close_stock(mock_db):
    """is_near_close=True, asset_type=stock -> ExitSignal TIME_EXIT."""
    monitor = _make_monitor(mock_db, data_price=150.0)
    trade = make_trade(
        direction="buy", asset_type="stock",
        stop_loss_price=None, take_profit_price=None,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=True)

    assert result is not None
    assert result.reason == ExitReason.TIME_EXIT


def test_eod_close_skips_options(mock_db):
    """is_near_close=True, asset_type=option -> None (LEAPS not auto-closed)."""
    monitor = _make_monitor(mock_db, option_position_price=5.0)
    trade = make_trade(
        direction="buy", asset_type="option",
        option_symbol="AAPL250117C00150000",
        option_expiry=date.today() + timedelta(days=365),
        stop_loss_price=None, take_profit_price=None,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=True)

    assert result is None


# =====================================================================
# 12-13. Option expiry
# =====================================================================

def test_option_expired(mock_db):
    """Option with expiry=today -> ExitSignal EXPIRED."""
    monitor = _make_monitor(mock_db, option_position_price=3.0)
    trade = make_trade(
        direction="buy", asset_type="option",
        option_symbol="AAPL250117C00150000",
        option_expiry=date.today(),
        stop_loss_price=None, take_profit_price=None,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is not None
    assert result.reason == ExitReason.EXPIRED


def test_option_not_expired(mock_db):
    """Option with expiry=30 days out -> None."""
    monitor = _make_monitor(mock_db, option_position_price=5.0)
    trade = make_trade(
        direction="buy", asset_type="option",
        option_symbol="AAPL250117C00150000",
        option_expiry=date.today() + timedelta(days=30),
        stop_loss_price=None, take_profit_price=None,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is None


# =====================================================================
# 14. No price available
# =====================================================================

def test_no_price_available_skips(mock_db):
    """get_current_price returns None -> None (skip, no false exit)."""
    monitor = _make_monitor(mock_db, data_price=None)
    trade = make_trade(
        direction="buy", stop_loss_price=95.0, take_profit_price=120.0,
    )

    result = monitor._check_single_position(trade, make_bot_config(), is_near_close=False)

    assert result is None


# =====================================================================
# 15-16. Roll alert — sent once, not twice
# =====================================================================

def test_roll_alert_sent_once(mock_db):
    """Option DTE=30 < roll_alert_dte=60, no [ROLL_ALERT_SENT] -> alert sent, notes tagged."""
    monitor = _make_monitor(mock_db, option_position_price=5.0)
    config = make_bot_config(leaps_roll_alert_dte=60, close_positions_eod=False)

    trade = make_trade(
        direction="buy", asset_type="option",
        option_symbol="AAPL250117C00150000",
        option_expiry=date.today() + timedelta(days=30),
        stop_loss_price=None, take_profit_price=None,
        notes="",
    )

    # Put the trade in the mock DB query result
    mock_db.query.return_value.filter.return_value.all.return_value = [trade]

    with patch.object(monitor, "_send_roll_alert"):
        with patch.object(monitor, "_reconcile_pending_entries", return_value=0):
            with patch.object(monitor, "_reconcile_bracket_exits", return_value=0):
                result = monitor.check_all_positions(config)

    assert result.roll_alerts_sent == 1
    assert "[ROLL_ALERT_SENT]" in (trade.notes or "")


def test_roll_alert_not_sent_twice(mock_db):
    """Notes already contains [ROLL_ALERT_SENT] -> no new alert."""
    monitor = _make_monitor(mock_db, option_position_price=5.0)
    config = make_bot_config(leaps_roll_alert_dte=60, close_positions_eod=False)

    trade = make_trade(
        direction="buy", asset_type="option",
        option_symbol="AAPL250117C00150000",
        option_expiry=date.today() + timedelta(days=30),
        stop_loss_price=None, take_profit_price=None,
        notes="Previous note [ROLL_ALERT_SENT]",
    )

    mock_db.query.return_value.filter.return_value.all.return_value = [trade]

    with patch.object(monitor, "_send_roll_alert") as mock_send:
        with patch.object(monitor, "_reconcile_pending_entries", return_value=0):
            with patch.object(monitor, "_reconcile_bracket_exits", return_value=0):
                result = monitor.check_all_positions(config)

    assert result.roll_alerts_sent == 0
    mock_send.assert_not_called()


# =====================================================================
# 17-20. PnL calculation via _close_bracket_trade
# =====================================================================

def test_pnl_calculation_long_profit(mock_db):
    """Long stock bracket exit: entry=100, exit=110, qty=10 -> pl=$100."""
    monitor = _make_monitor(mock_db)
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    filled_order = {"filled_avg_price": "110.0", "id": "exit-1", "status": "filled"}

    monitor._close_bracket_trade(trade, filled_order, ExitReason.TAKE_PROFIT, None)

    assert trade.realized_pl == 100.0
    assert trade.exit_price == 110.0
    assert trade.status == TradeStatus.CLOSED.value


def test_pnl_calculation_long_loss(mock_db):
    """Long stock bracket exit: entry=100, exit=90, qty=10 -> pl=-$100."""
    monitor = _make_monitor(mock_db)
    trade = make_trade(
        direction="buy", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    filled_order = {"filled_avg_price": "90.0", "id": "exit-2", "status": "filled"}

    monitor._close_bracket_trade(trade, filled_order, ExitReason.STOP_LOSS, None)

    assert trade.realized_pl == -100.0


def test_pnl_calculation_short(mock_db):
    """Short stock bracket exit: entry=100, exit=90, qty=10 -> pl=$100."""
    monitor = _make_monitor(mock_db)
    trade = make_trade(
        direction="sell", asset_type="stock",
        entry_price=100.0, quantity=10,
    )
    filled_order = {"filled_avg_price": "90.0", "id": "exit-3", "status": "filled"}

    monitor._close_bracket_trade(trade, filled_order, ExitReason.TAKE_PROFIT, None)

    assert trade.realized_pl == 100.0


def test_pnl_calculation_option(mock_db):
    """Option bracket exit: entry=5, exit=7, qty=1, multiplier=100 -> pl=$200."""
    monitor = _make_monitor(mock_db)
    trade = make_trade(
        direction="buy", asset_type="option",
        entry_price=5.0, quantity=1,
        option_symbol="AAPL250117C00150000",
    )
    filled_order = {"filled_avg_price": "7.0", "id": "exit-4", "status": "filled"}

    monitor._close_bracket_trade(trade, filled_order, ExitReason.TAKE_PROFIT, None)

    # (7-5) * 1 * 100 = $200
    assert trade.realized_pl == 200.0


# =====================================================================
# 21-22. check_all_positions integration
# =====================================================================

def test_check_all_positions_returns_multiple_exits(mock_db):
    """3 open trades, 2 should exit -> result.exit_signals has length 2."""
    monitor = _make_monitor(mock_db, data_price=90.0)

    trade1 = make_trade(
        id=1, direction="buy", entry_price=100.0,
        stop_loss_price=95.0, take_profit_price=120.0,
    )  # SL triggered (90 < 95)
    trade2 = make_trade(
        id=2, direction="buy", entry_price=100.0,
        stop_loss_price=85.0, take_profit_price=120.0,
    )  # No exit (90 > 85 and 90 < 120)
    trade3 = make_trade(
        id=3, direction="sell", entry_price=100.0,
        stop_loss_price=None, take_profit_price=80.0,
    )  # TP triggered for short (90 > 80? No. For short TP: current <= TP. 90 > 80, not triggered)
    # Adjust trade3 so it triggers: short SL at 95, current=90 -> no trigger
    # Let's use a scenario where trade3 also has SL triggered
    trade3 = make_trade(
        id=3, direction="buy", entry_price=100.0,
        stop_loss_price=92.0, take_profit_price=120.0,
    )  # SL triggered (90 < 92)

    mock_db.query.return_value.filter.return_value.all.return_value = [trade1, trade2, trade3]
    config = make_bot_config(close_positions_eod=False)

    with patch.object(monitor, "_reconcile_pending_entries", return_value=0):
        with patch.object(monitor, "_reconcile_bracket_exits", return_value=0):
            result = monitor.check_all_positions(config)

    assert result.positions_checked == 3
    assert len(result.exit_signals) == 2
    exit_ids = [es.trade_id for es in result.exit_signals]
    assert 1 in exit_ids
    assert 3 in exit_ids


def test_check_all_positions_no_trades(mock_db):
    """No open trades -> empty result."""
    monitor = _make_monitor(mock_db, data_price=150.0)
    mock_db.query.return_value.filter.return_value.all.return_value = []
    config = make_bot_config()

    with patch.object(monitor, "_reconcile_pending_entries", return_value=0):
        with patch.object(monitor, "_reconcile_bracket_exits", return_value=0):
            result = monitor.check_all_positions(config)

    assert result.positions_checked == 0
    assert len(result.exit_signals) == 0
