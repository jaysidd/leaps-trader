"""
Shared fixtures for replay E2E tests.

Provides:
- ReplayClock for simulated time
- Mock database session
- Automatic singleton cache cleanup between tests
- Data service stub factory
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure backend root and scripts are on sys.path
backend_dir = str(Path(__file__).resolve().parents[2])
scripts_dir = str(Path(backend_dir) / "scripts")
for p in (backend_dir, scripts_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# Disable strict preset catalog validation for replay tests
os.environ["PRESET_CATALOG_STRICT"] = "false"


@pytest.fixture
def replay_clock():
    """A ReplayClock fixed to 2026-02-10 (Tuesday), starting at 10:00 AM ET."""
    from scripts.replay.replay_services import ReplayClock
    return ReplayClock(datetime(2026, 2, 10), start_hour=10, start_minute=0)


@pytest.fixture
def mock_db():
    """A MagicMock standing in for a SQLAlchemy Session."""
    return MagicMock()


@pytest.fixture
def make_data_service():
    """Factory that creates a mock data service with injected daily_cache."""
    def _factory(spy_df):
        svc = MagicMock()
        svc.daily_cache = {"SPY": spy_df}
        return svc
    return _factory


@pytest.fixture(autouse=True)
def clear_singleton_caches():
    """Reset service singleton caches before and after each test.

    Prevents state leakage between tests. The regime detector is the
    primary singleton that caches data read by PresetSelector.
    """
    def _clear():
        try:
            from app.services.ai.market_regime import get_regime_detector
            get_regime_detector().clear_cache()
        except Exception:
            pass

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def reset_preset_selector_singleton():
    """Reset the PresetSelector singleton to ensure clean state.

    Without this, the singleton persists across tests and may carry
    stale references or validation state.
    """
    try:
        import app.services.automation.preset_selector as ps_module
        original = ps_module._preset_selector
        ps_module._catalog_validated = False
        yield
        ps_module._preset_selector = original
    except Exception:
        yield
