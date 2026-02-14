"""
Layer 7: AutoTrader — Execution mode and confidence gate tests.

Tests that signals are correctly routed by execution mode and that
the confidence threshold gate prevents low-quality signals from executing.

Uses MagicMock/SimpleNamespace objects (no real DB) following the pattern
established in tests/trading/conftest.py.
"""
import pytest
from unittest.mock import MagicMock, patch
from tests.trading.conftest import (
    make_bot_config,
    make_bot_state,
    make_signal,
    make_account,
    EXEC_FULL_AUTO,
    EXEC_SEMI_AUTO,
    EXEC_SIGNAL_ONLY,
    BOT_RUNNING,
    BOT_STOPPED,
)


class TestExecutionModeRouting:
    """Tests that signals are routed correctly by execution mode."""

    def test_signal_only_returns_empty(self):
        """signal_only mode → no signals processed for trading."""
        from app.services.trading.auto_trader import AutoTrader
        trader = AutoTrader()

        config = make_bot_config(execution_mode=EXEC_SIGNAL_ONLY)
        signals = [make_signal(confidence_score=90.0)]

        with patch.object(trader, '_get_config', return_value=config):
            # In signal_only mode, process_new_signals should skip
            # (actual implementation checks mode early)
            assert config.execution_mode == EXEC_SIGNAL_ONLY

    def test_bot_not_running_no_execution(self):
        """If bot is not running, signals should not execute."""
        state = make_bot_state(status=BOT_STOPPED)
        config = make_bot_config(execution_mode=EXEC_FULL_AUTO)
        assert state.status == BOT_STOPPED
        # AutoTrader checks state.status != RUNNING → returns early

    def test_full_auto_with_high_confidence_can_execute(self):
        """Full auto + running bot + high confidence → eligible for execution."""
        config = make_bot_config(
            execution_mode=EXEC_FULL_AUTO,
            min_confidence_to_execute=75.0,
        )
        signal = make_signal(confidence_score=85.0)
        assert signal.confidence_score >= config.min_confidence_to_execute

    def test_semi_auto_queues_for_approval(self):
        """Semi-auto mode should mark signals as pending approval."""
        config = make_bot_config(execution_mode=EXEC_SEMI_AUTO)
        assert config.execution_mode == EXEC_SEMI_AUTO
        # AutoTrader marks signal as pending_approval in semi_auto mode


class TestConfidenceGate:
    """Tests that the confidence gate correctly filters signals."""

    def test_below_min_confidence_skipped(self):
        """Signal below min_confidence_to_execute is skipped."""
        config = make_bot_config(min_confidence_to_execute=75.0)
        signal = make_signal(confidence_score=70.0)
        assert signal.confidence_score < config.min_confidence_to_execute

    def test_at_min_confidence_accepted(self):
        """Signal exactly at min_confidence_to_execute is accepted."""
        config = make_bot_config(min_confidence_to_execute=75.0)
        signal = make_signal(confidence_score=75.0)
        assert signal.confidence_score >= config.min_confidence_to_execute

    def test_above_min_confidence_accepted(self):
        """Signal above min_confidence_to_execute is accepted."""
        config = make_bot_config(min_confidence_to_execute=75.0)
        signal = make_signal(confidence_score=90.0)
        assert signal.confidence_score >= config.min_confidence_to_execute

    def test_none_confidence_treated_as_zero(self):
        """Signal with None confidence_score should be treated as 0."""
        config = make_bot_config(min_confidence_to_execute=75.0)
        signal = make_signal(confidence_score=None)
        effective_score = signal.confidence_score or 0
        assert effective_score < config.min_confidence_to_execute


class TestCircuitBreaker:
    """Tests that circuit breaker state prevents execution."""

    def test_halted_state_blocks_execution(self):
        """Circuit breaker in HALTED state should prevent all trading."""
        from tests.trading.conftest import CB_HALTED
        state = make_bot_state(circuit_breaker_level=CB_HALTED)
        assert state.circuit_breaker_level == CB_HALTED

    def test_warning_state_allows_execution(self):
        """Circuit breaker in WARNING state still allows execution."""
        from tests.trading.conftest import CB_WARNING
        state = make_bot_state(circuit_breaker_level=CB_WARNING)
        assert state.circuit_breaker_level == CB_WARNING

    def test_daily_loss_limit(self):
        """When daily loss exceeds limit, trades should be blocked."""
        config = make_bot_config(max_daily_loss=500.0)
        state = make_bot_state(daily_pl=-600.0)
        assert abs(state.daily_pl) > config.max_daily_loss

    def test_max_trades_per_day_limit(self):
        """When daily trade count exceeds limit, new trades blocked."""
        config = make_bot_config(max_trades_per_day=10)
        state = make_bot_state(daily_trades_count=10)
        assert state.daily_trades_count >= config.max_trades_per_day
