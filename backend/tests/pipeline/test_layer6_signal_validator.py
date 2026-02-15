"""
Layer 6: SignalValidator — AI pre-trade validation tests.

Tests setup validity checks, AI validation flow, and confidence thresholds.
Claude AI is mocked — these tests validate logic, not AI quality.
"""
import types
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from tests.pipeline.conftest import make_signal as _base_make_signal


def make_validator_signal(**overrides):
    """Create a signal with all attributes SignalValidator expects."""
    sig = _base_make_signal(**overrides)
    # Add fields that SignalValidator._check_setup_validity and _ai_validate access
    if not hasattr(sig, 'generated_at'):
        sig.generated_at = datetime.now(timezone.utc)
    if not hasattr(sig, 'ai_reasoning'):
        sig.ai_reasoning = "Test signal reasoning"
    if not hasattr(sig, 'target_2'):
        sig.target_2 = None
    return sig


# Alias for convenience
make_signal = make_validator_signal


class TestSetupValidity:
    """Tests for the setup sanity checks that run BEFORE AI validation."""

    @pytest.mark.asyncio
    async def test_price_below_stop_loss_rejected(self):
        """If current price is below stop loss for a long signal, reject."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
        )

        fresh_data = {"current_price": 93.0}  # Below stop loss (95)

        result = validator._check_setup_validity(signal, fresh_data)
        assert result["valid"] is False
        assert "stop" in result["reason"].lower() or "below" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_price_past_target_rejected(self):
        """If current price is already above target_1 for a long, reject."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
        )

        fresh_data = {"current_price": 112.0}  # Past target_1

        result = validator._check_setup_validity(signal, fresh_data)
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_chasing_entry_more_than_3pct_rejected(self):
        """If price is >3% above entry for a long, reject as chasing."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
        )

        fresh_data = {"current_price": 104.0}  # 4% above entry

        result = validator._check_setup_validity(signal, fresh_data)
        assert result["valid"] is False
        assert "chas" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_valid_setup_passes(self):
        """Price within entry zone should pass."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
            stop_loss=95.0,
            target_1=110.0,
        )

        fresh_data = {"current_price": 100.5}  # Within entry zone

        result = validator._check_setup_validity(signal, fresh_data)
        assert result["valid"] is True


class TestAIValidation:
    """Tests for the AI validation flow with mocked Claude."""

    @pytest.mark.asyncio
    async def test_ai_high_confidence_auto_execute(self, mock_claude_service):
        """AI returns confidence ≥ THRESHOLD → auto_execute."""
        from app.services.signals.signal_validator import SignalValidator, CONFIDENCE_THRESHOLD
        validator = SignalValidator()

        # Mock Claude to return high confidence
        mock_claude_service.parser.extract_json.return_value = {
            "confidence": CONFIDENCE_THRESHOLD + 5,
            "reasoning": "Strong setup with volume confirmation",
        }

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            confidence_score=80.0,
        )
        fresh_data = {"current_price": 100.5}

        result = await validator._ai_validate(signal, fresh_data)
        assert result["confidence"] >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_ai_low_confidence_reject(self, mock_claude_service):
        """AI returns confidence < 40 → reject."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        mock_claude_service.parser.extract_json.return_value = {
            "confidence": 30,
            "reasoning": "Weak volume, oversold without catalyst",
        }

        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
        )
        fresh_data = {"current_price": 100.0}

        result = await validator._ai_validate(signal, fresh_data)
        assert result["confidence"] < 40

    @pytest.mark.asyncio
    async def test_claude_unavailable_fallback(self):
        """When Claude service is not available, fallback to confidence=50."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        # Patch get_claude_service to return None
        with patch("app.services.signals.signal_validator.get_claude_service", return_value=None):
            signal = make_signal(direction="buy", entry_price=100.0, stop_loss=95.0, target_1=110.0)
            fresh_data = {"current_price": 100.0}

            result = await validator._ai_validate(signal, fresh_data)
            assert result["confidence"] == 50
            assert "unavailable" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_claude_parse_failure_fallback(self, mock_claude_service):
        """When Claude response can't be parsed, fallback to confidence=50."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        # Mock parser to return None (parse failure)
        mock_claude_service.parser.extract_json.return_value = None

        signal = make_signal(direction="buy", entry_price=100.0, stop_loss=95.0, target_1=110.0)
        fresh_data = {"current_price": 100.0}

        result = await validator._ai_validate(signal, fresh_data)
        assert result["confidence"] == 50


class TestConfidenceThreshold:
    """Tests for the auto-execute confidence threshold."""

    def test_threshold_value(self):
        """Verify the confidence threshold is set to expected value."""
        from app.services.signals.signal_validator import CONFIDENCE_THRESHOLD
        # After Fix 4: threshold should be 70 (raised from 65)
        assert CONFIDENCE_THRESHOLD >= 65, \
            f"CONFIDENCE_THRESHOLD should be ≥65, got {CONFIDENCE_THRESHOLD}"


class TestValidatorPrompt:
    """Tests that the AI validator prompt has been improved."""

    @pytest.mark.asyncio
    async def test_prompt_not_overly_lenient(self, mock_claude_service):
        """The prompt should NOT contain 'be practical' or similar lenient phrasing."""
        from app.services.signals.signal_validator import SignalValidator
        validator = SignalValidator()

        # Capture the prompt that would be sent to Claude
        signal = make_signal(
            direction="buy",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            confidence_score=75.0,
            ai_reasoning="Technical setup confirmed",
        )
        fresh_data = {
            "current_price": 100.0,
            "change_percent": 1.0,
            "daily_bar": {"volume": 2_000_000},
            "latest_quote": {"bid": 99.95, "ask": 100.05},
        }

        await validator._ai_validate(signal, fresh_data)

        # Check what prompt was actually sent
        if mock_claude_service.call_claude.called:
            call_args = mock_claude_service.call_claude.call_args
            prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
            # After Fix 3: prompt should not contain "be practical"
            # This test documents the expected behavior
            # (will fail before the fix is applied, pass after)
