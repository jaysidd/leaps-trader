"""
Tests for circuit breaker logic in RiskGateway.update_circuit_breaker().

The circuit breaker is a critical safety mechanism that prevents runaway
losses by escalating through WARNING -> PAUSED -> HALTED as daily drawdown
increases. It must NEVER auto-downgrade from a higher level — only manual
intervention (or daily reset) should clear it.
"""
import pytest

from app.services.trading.risk_gateway import RiskGateway
from app.models.bot_state import BotStatus, CircuitBreakerLevel

from tests.trading.conftest import (
    make_bot_config, make_bot_state,
    CB_NONE, CB_WARNING, CB_PAUSED, CB_HALTED,
    BOT_RUNNING, BOT_PAUSED, BOT_HALTED,
)


# =====================================================================
# 1. NONE -> WARNING
# =====================================================================

def test_circuit_breaker_none_to_warning(mock_db):
    """Drawdown 3.5% with warn_pct=3 -> WARNING level."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_NONE,
    )
    # 3.5% drawdown: equity dropped from 100k to 96.5k
    account = {"equity": 96500.0}

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CircuitBreakerLevel.WARNING.value
    assert state.circuit_breaker_level == CircuitBreakerLevel.WARNING.value
    assert state.circuit_breaker_triggered_at is not None


# =====================================================================
# 2. NONE -> PAUSED
# =====================================================================

def test_circuit_breaker_none_to_paused(mock_db):
    """Drawdown 6% with pause_pct=5 -> PAUSED, bot status=paused."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_NONE,
        status=BOT_RUNNING,
    )
    account = {"equity": 94000.0}  # 6% drawdown

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CircuitBreakerLevel.PAUSED.value
    assert state.status == BotStatus.PAUSED.value
    assert state.circuit_breaker_triggered_at is not None


# =====================================================================
# 3. NONE -> HALTED
# =====================================================================

def test_circuit_breaker_none_to_halted(mock_db):
    """Drawdown 11% with halt_pct=10 -> HALTED, bot status=halted."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_NONE,
        status=BOT_RUNNING,
    )
    account = {"equity": 89000.0}  # 11% drawdown

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CircuitBreakerLevel.HALTED.value
    assert state.status == BotStatus.HALTED.value


# =====================================================================
# 4. HALTED never downgrades
# =====================================================================

def test_circuit_breaker_never_downgrades_from_halted(mock_db):
    """Currently HALTED, drawdown improves to 2% -> stays HALTED."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_HALTED,
        status=BOT_HALTED,
    )
    account = {"equity": 98000.0}  # Only 2% drawdown now

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CircuitBreakerLevel.HALTED.value
    assert state.circuit_breaker_level == CircuitBreakerLevel.HALTED.value


# =====================================================================
# 5. PAUSED no auto-downgrade
# =====================================================================

def test_circuit_breaker_paused_no_auto_downgrade(mock_db):
    """Currently PAUSED, drawdown below pause threshold -> stays PAUSED."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_PAUSED,
        status=BOT_PAUSED,
    )
    account = {"equity": 97000.0}  # 3% drawdown, below pause 5%

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CircuitBreakerLevel.PAUSED.value
    assert state.circuit_breaker_level == CircuitBreakerLevel.PAUSED.value


# =====================================================================
# 6. Zero start equity — no change
# =====================================================================

def test_circuit_breaker_zero_start_equity(mock_db):
    """daily_start_equity=0 -> no change, returns current level."""
    gw = RiskGateway(mock_db)
    config = make_bot_config()
    state = make_bot_state(
        daily_start_equity=0,
        circuit_breaker_level=CB_NONE,
    )
    account = {"equity": 100000.0}

    level = gw.update_circuit_breaker(config, state, account)

    assert level == CB_NONE
    assert state.circuit_breaker_level == CB_NONE


# =====================================================================
# 7. Level change updates timestamp
# =====================================================================

def test_circuit_breaker_level_change_updates_timestamp(mock_db):
    """Level changes -> circuit_breaker_triggered_at is set."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
    )
    state = make_bot_state(
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_NONE,
        circuit_breaker_triggered_at=None,
    )
    account = {"equity": 96000.0}  # 4% -> WARNING

    gw.update_circuit_breaker(config, state, account)

    assert state.circuit_breaker_triggered_at is not None
    assert state.circuit_breaker_level == CircuitBreakerLevel.WARNING.value
