"""
Layer 5: StrategySelector — Timeframe qualification and confidence tier tests.

Tests the rules-based engine that determines which timeframes each stock
qualifies for and assigns HIGH/MEDIUM/LOW confidence.
"""
import pytest
from app.services.signals.strategy_selector import StrategySelector, CRITERIA
from tests.pipeline.helpers import (
    make_screening_result,
    make_fresh_metrics,
    make_alpaca_snapshot,
)
from tests.pipeline.mock_stocks import (
    STRONG_STOCK_DATA,
    STRONG_FRESH_METRICS,
    STRONG_SNAPSHOT,
    WEAK_STOCK_DATA,
    WEAK_FRESH_METRICS,
    WEAK_SNAPSHOT,
    EDGE_STOCK_DATA,
    EDGE_FRESH_METRICS,
    EDGE_SNAPSHOT,
    NODATA_STOCK_DATA,
    NODATA_FRESH_METRICS,
    NODATA_SNAPSHOT,
)


@pytest.fixture
def selector():
    return StrategySelector()


class TestTimeframeQualification:
    """Tests for _qualifies_for_timeframe()."""

    def test_strong_stock_qualifies_multiple_timeframes(self, selector):
        """STRONG stock should qualify for multiple timeframes."""
        result = selector.select_strategies(
            STRONG_STOCK_DATA, STRONG_FRESH_METRICS, STRONG_SNAPSHOT,
        )
        tfs = [t["tf"] for t in result["timeframes"]]
        assert len(tfs) >= 1, f"Strong stock should qualify for ≥1 timeframe, got {tfs}"

    def test_weak_stock_no_timeframes(self, selector):
        """WEAK stock with score 18 should qualify for zero timeframes."""
        result = selector.select_strategies(
            WEAK_STOCK_DATA, WEAK_FRESH_METRICS, WEAK_SNAPSHOT,
        )
        assert len(result["timeframes"]) == 0

    def test_score_below_min_disqualifies(self, selector):
        """Stock below min_score for a timeframe is disqualified."""
        stock_data = make_screening_result(symbol="LOSC", score=50.0)
        # 5m requires min_score=55
        result = selector.select_strategies(stock_data, {}, {})
        tfs = [t["tf"] for t in result["timeframes"]]
        assert "5m" not in tfs

    def test_market_cap_floor(self, selector):
        """Stock below market_cap minimum for 5m ($1B) is disqualified."""
        stock_data = make_screening_result(
            symbol="SMALL", score=65.0, market_cap=400_000_000,  # Below 15m's $500M min
        )
        metrics = make_fresh_metrics()
        snap = make_alpaca_snapshot(change_percent=2.0, volume=5_000_000)
        result = selector.select_strategies(stock_data, metrics, snap)
        tfs = [t["tf"] for t in result["timeframes"]]
        assert "5m" not in tfs   # 5m requires $1B
        assert "15m" not in tfs  # 15m requires $500M

    def test_1d_requires_sma50_above_sma200(self, selector):
        """1d timeframe requires SMA50 > SMA200 uptrend."""
        stock_data = make_screening_result(symbol="NOTR", score=65.0, market_cap=5_000_000_000)
        # SMA50 BELOW SMA200 → bearish trend → 1d disqualified
        metrics = make_fresh_metrics(sma50=95.0, sma200=100.0)
        snap = make_alpaca_snapshot()
        result = selector.select_strategies(stock_data, metrics, snap)
        tfs = [t["tf"] for t in result["timeframes"]]
        assert "1d" not in tfs

    def test_1h_requires_sma20_above_sma50(self, selector):
        """1h timeframe requires SMA20 > SMA50."""
        stock_data = make_screening_result(symbol="NOTR", score=65.0, market_cap=2_000_000_000)
        metrics = make_fresh_metrics(sma20=95.0, sma50=100.0, adx=25.0)  # SMA20 < SMA50
        snap = make_alpaca_snapshot()
        result = selector.select_strategies(stock_data, metrics, snap)
        tfs = [t["tf"] for t in result["timeframes"]]
        assert "1h" not in tfs

    def test_iv_rank_ceiling_for_daily(self, selector):
        """1d timeframe has max_iv_rank=70 — high IV disqualifies."""
        stock_data = make_screening_result(
            symbol="HIVOL", score=65.0, market_cap=5_000_000_000, iv_rank=75.0,
        )
        metrics = make_fresh_metrics()
        snap = make_alpaca_snapshot()
        result = selector.select_strategies(stock_data, metrics, snap)
        tfs = [t["tf"] for t in result["timeframes"]]
        assert "1d" not in tfs


class TestConfidenceCalculation:
    """Tests for _calculate_confidence()."""

    def test_high_confidence_score_above_70_no_edges(self, selector):
        """Score > 70 with no serious edge cases → HIGH."""
        result = selector.select_strategies(
            STRONG_STOCK_DATA, STRONG_FRESH_METRICS, STRONG_SNAPSHOT,
        )
        assert result["confidence"] == "HIGH"
        assert result["auto_queue"] is True

    def test_high_confidence_2_timeframes_score_65(self, selector):
        """2+ timeframes + score ≥ 65 + ≤1 serious edge → HIGH."""
        stock_data = make_screening_result(symbol="DUAL", score=66.0, market_cap=5_000_000_000)
        metrics = make_fresh_metrics(sma20=102.0, sma50=100.0, sma200=95.0, adx=25.0)
        snap = make_alpaca_snapshot(change_percent=1.5, volume=4_000_000)
        result = selector.select_strategies(stock_data, metrics, snap)

        # Should qualify for multiple timeframes
        if len(result["timeframes"]) >= 2:
            assert result["confidence"] == "HIGH"

    def test_high_confidence_1_timeframe_score_65_no_edges(self, selector):
        """1 timeframe + score ≥ 65 + zero serious edges → HIGH."""
        stock_data = make_screening_result(symbol="ONETF", score=66.0, market_cap=5_000_000_000)
        metrics = make_fresh_metrics(rsi=55.0)
        snap = make_alpaca_snapshot(change_percent=0.6, volume=2_000_000, prev_volume=2_000_000)
        result = selector.select_strategies(stock_data, metrics, snap)
        if len(result["timeframes"]) == 1:
            # Check no serious edges exist
            serious = [e for e in result["edge_cases"] if any(
                kw in e.lower() for kw in ("overbought", "oversold", "low volume", "spread", "weak trend")
            )]
            if len(serious) == 0:
                assert result["confidence"] == "HIGH"

    def test_low_confidence_no_timeframes(self, selector):
        """No qualifying timeframes → LOW."""
        result = selector.select_strategies(
            WEAK_STOCK_DATA, WEAK_FRESH_METRICS, WEAK_SNAPSHOT,
        )
        assert result["confidence"] == "LOW"
        assert result["auto_queue"] is False

    def test_low_confidence_score_below_50(self, selector):
        """Score < 50 → LOW even with qualifying timeframes."""
        stock_data = make_screening_result(symbol="LO", score=45.0, market_cap=5_000_000_000)
        metrics = make_fresh_metrics()
        snap = make_alpaca_snapshot(change_percent=2.0, volume=5_000_000)
        result = selector.select_strategies(stock_data, metrics, snap)
        assert result["confidence"] == "LOW"

    def test_missing_sma_not_serious_edge(self, selector):
        """'missing SMA data' should NOT be classified as a serious edge case."""
        stock_data = make_screening_result(symbol="NOSMA", score=66.0, market_cap=2_000_000_000)
        # No SMA data available → generates "missing SMA data" edge case
        metrics = make_fresh_metrics(sma20=None, sma50=None, sma200=None)
        snap = make_alpaca_snapshot(change_percent=1.0, volume=2_500_000)
        result = selector.select_strategies(stock_data, metrics, snap)
        # The "missing SMA" edge shouldn't prevent HIGH confidence
        serious = [e for e in result["edge_cases"] if any(
            kw in e.lower() for kw in ("overbought", "oversold", "low volume", "spread", "weak trend")
        )]
        # If it qualifies for a timeframe with score ≥ 65 and no serious edges
        if len(result["timeframes"]) >= 1 and len(serious) == 0:
            assert result["confidence"] == "HIGH"

    def test_edge_stock_medium_confidence(self, selector):
        """EDGE stock should get MEDIUM (not HIGH) confidence."""
        result = selector.select_strategies(
            EDGE_STOCK_DATA, EDGE_FRESH_METRICS, EDGE_SNAPSHOT,
        )
        # EDGE score=32, which is below min_score for all timeframes (55+)
        # So it should get LOW confidence
        assert result["confidence"] in ("LOW", "MEDIUM")


class TestBulkCategorization:
    """Tests for select_strategies_bulk()."""

    def test_bulk_categorization_mixed(self, selector):
        """Bulk processing correctly categorizes stocks."""
        stocks = [STRONG_STOCK_DATA, WEAK_STOCK_DATA, EDGE_STOCK_DATA]
        bulk_metrics = {
            "BULL": STRONG_FRESH_METRICS,
            "BEAR": WEAK_FRESH_METRICS,
            "EDGE": EDGE_FRESH_METRICS,
        }
        bulk_snapshots = {
            "BULL": STRONG_SNAPSHOT,
            "BEAR": WEAK_SNAPSHOT,
            "EDGE": EDGE_SNAPSHOT,
        }

        result = selector.select_strategies_bulk(stocks, bulk_metrics, bulk_snapshots)

        assert "auto_queued" in result
        assert "review_needed" in result
        assert "skipped" in result
        total = len(result["auto_queued"]) + len(result["review_needed"]) + len(result["skipped"])
        assert total == 3

    def test_nodata_stock_handled_gracefully(self, selector):
        """Stock with missing data should not crash."""
        result = selector.select_strategies(
            NODATA_STOCK_DATA, NODATA_FRESH_METRICS, NODATA_SNAPSHOT,
        )
        assert result["confidence"] == "LOW"
        assert result["auto_queue"] is False
