"""
Pipeline E2E test infrastructure.

Sets up:
- Mocked external services (Alpaca, FMP, Claude, Telegram)
- Factory functions for test data

Most pipeline tests work with pure functions that take dicts/DataFrames,
so heavy database/service mocking is only needed for integration tests.
External service mocks are NOT autouse — test files opt in as needed.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Ensure backend is on the path
# ---------------------------------------------------------------------------
backend_dir = str(Path(__file__).resolve().parents[2])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


# ---------------------------------------------------------------------------
# Mock Claude AI service (opt-in per test)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_claude_service():
    """Mock Claude AI service — returns configurable validation."""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.call_claude = AsyncMock(return_value=(
        '{"confidence": 75, "reasoning": "Mock AI: setup looks valid"}',
        {"input_tokens": 100, "output_tokens": 50},
    ))
    mock.settings = MagicMock()
    mock.settings.CLAUDE_MODEL_FAST = "claude-3-haiku"
    mock.parser = MagicMock()
    mock.parser.extract_json = MagicMock(return_value={
        "confidence": 75,
        "reasoning": "Mock AI: setup looks valid",
    })

    with patch("app.services.signals.signal_validator.get_claude_service", return_value=mock):
        yield mock


# ---------------------------------------------------------------------------
# Re-export trading test factories (reuse existing ones)
# ---------------------------------------------------------------------------
from tests.trading.conftest import (  # noqa: E402, F401
    make_bot_config,
    make_bot_state,
    make_signal,
    make_trade,
    make_account,
)
