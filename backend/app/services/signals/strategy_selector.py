"""
Strategy Selector — Rules-based engine for multi-timeframe strategy assignment.

Takes SavedScanResult stock_data + fresh FMP technical indicators + Alpaca
snapshot and determines:
  1. Which timeframes each stock qualifies for (5m, 15m, 1h, 1d)
  2. Confidence level (HIGH / MEDIUM / LOW)
  3. Human-readable reasoning string
  4. Whether to auto-queue or hold for manual/AI review

This is Layer 2 of the 4-layer intelligence pipeline:
  Screening → **Strategy Selection** → Signal Engine → AI Pre-Trade Validation
"""

from typing import Dict, List, Any, Optional, Tuple
from loguru import logger


# ---------------------------------------------------------------------------
# Configurable per-timeframe qualification criteria
# ---------------------------------------------------------------------------
CRITERIA = {
    "5m": {
        "min_score": 55,
        "min_iv_rank": 30,
        "min_volume_ratio": 1.2,     # today's vol / avg vol
        "min_pct_change": 1.0,       # stock must be moving today
        "max_spread_pct": 0.20,      # execution cost guard
        "min_market_cap": 1_000_000_000,
    },
    "15m": {
        "min_score": 55,
        "min_iv_rank": 20,
        "min_volume_ratio": 0.8,
        "min_pct_change": 0.5,
        "max_spread_pct": 0.30,
        "min_market_cap": 500_000_000,
    },
    "1h": {
        "min_score": 58,
        "min_iv_rank": 15,
        "max_iv_rank": 60,           # not too volatile for overnight hold
        "requires_trend": True,      # SMA20 > SMA50
        "min_adx": 20,
        "min_market_cap": 1_000_000_000,
    },
    "1d": {
        "min_score": 60,
        "min_market_cap": 2_000_000_000,
        "max_iv_rank": 70,
        "requires_trend": True,      # SMA50 > SMA200
    },
}

# Which strategies apply to each timeframe (used for queue entry)
TIMEFRAME_STRATEGIES = {
    "5m":  ["orb_breakout", "vwap_pullback", "range_breakout"],
    "15m": ["orb_breakout", "vwap_pullback", "range_breakout"],
    "1h":  ["vwap_pullback", "range_breakout", "trend_following"],
    "1d":  ["range_breakout", "trend_following", "mean_reversion"],
}


class StrategySelector:
    """
    Rules-based strategy selection using fresh market data + screening scores.
    Determines which timeframes each stock qualifies for and confidence level.
    """

    def select_strategies(
        self,
        stock_data: Dict[str, Any],
        fresh_metrics: Optional[Dict[str, Any]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a single stock and return strategy selection result.

        Args:
            stock_data: SavedScanResult.stock_data JSON (scores, fundamentals, etc.)
            fresh_metrics: Fresh FMP technical indicators (RSI, SMA, ATR, ADX, etc.)
                           from fmp_service.get_strategy_metrics(symbol)
            snapshot: Fresh Alpaca snapshot (current_price, volume, bid/ask, etc.)
                      from alpaca_service.get_snapshot(symbol)

        Returns:
            {
                "symbol": str,
                "timeframes": [{"tf": "5m", "strategy": "auto", "reasons": [...]}],
                "confidence": "HIGH" | "MEDIUM" | "LOW",
                "reasoning": str,
                "auto_queue": bool,
                "edge_cases": [str],
            }
        """
        symbol = stock_data.get("symbol", "???")
        score = _safe_float(stock_data.get("score"), 0)

        qualified_timeframes: List[Dict[str, Any]] = []
        all_reasons: List[str] = []
        edge_cases: List[str] = []

        for tf in ("5m", "15m", "1h", "1d"):
            ok, reasons, edges = self._qualifies_for_timeframe(
                tf, stock_data, fresh_metrics or {}, snapshot or {},
            )
            if ok:
                qualified_timeframes.append({
                    "tf": tf,
                    "strategy": "auto",  # signal engine picks best strategy
                    "reasons": reasons,
                })
                all_reasons.extend(reasons)
            edge_cases.extend(edges)

        confidence = self._calculate_confidence(
            score, qualified_timeframes, fresh_metrics or {}, edge_cases,
        )

        # Build human-readable reasoning
        if qualified_timeframes:
            tf_labels = [q["tf"] for q in qualified_timeframes]
            reasoning = (
                f"Score {score:.1f} qualifies for {', '.join(tf_labels)}. "
                + "; ".join(all_reasons[:4])  # cap at 4 reasons to keep it readable
            )
        else:
            reasoning = f"Score {score:.1f} — no timeframes qualified."
            if edge_cases:
                reasoning += " Edge cases: " + "; ".join(edge_cases[:3])

        auto_queue = confidence == "HIGH"

        result = {
            "symbol": symbol,
            "timeframes": qualified_timeframes,
            "confidence": confidence,
            "reasoning": reasoning,
            "auto_queue": auto_queue,
            "edge_cases": edge_cases,
            "score": score,
        }

        logger.debug(
            f"[StrategySelector] {symbol}: conf={confidence}, "
            f"tfs={[q['tf'] for q in qualified_timeframes]}, auto={auto_queue}"
        )
        return result

    def select_strategies_bulk(
        self,
        stocks: List[Dict[str, Any]],
        bulk_metrics: Optional[Dict[str, Dict[str, Any]]] = None,
        bulk_snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Process multiple stocks and categorize them.

        Returns:
            {
                "auto_queued": [...],   # HIGH confidence — ready to queue
                "review_needed": [...], # MEDIUM confidence — needs AI/manual review
                "skipped": [...],       # LOW confidence — filtered out
            }
        """
        bulk_metrics = bulk_metrics or {}
        bulk_snapshots = bulk_snapshots or {}

        auto_queued = []
        review_needed = []
        skipped = []

        for stock_data in stocks:
            symbol = stock_data.get("symbol", "")
            metrics = bulk_metrics.get(symbol, {})
            snap = bulk_snapshots.get(symbol, {})

            result = self.select_strategies(stock_data, metrics, snap)

            if result["confidence"] == "HIGH":
                auto_queued.append(result)
            elif result["confidence"] == "MEDIUM":
                review_needed.append(result)
            else:
                skipped.append(result)

        logger.info(
            f"[StrategySelector] Bulk results: "
            f"{len(auto_queued)} auto, {len(review_needed)} review, "
            f"{len(skipped)} skipped (of {len(stocks)} total)"
        )

        return {
            "auto_queued": auto_queued,
            "review_needed": review_needed,
            "skipped": skipped,
        }

    # ------------------------------------------------------------------
    # Internal: per-timeframe qualification
    # ------------------------------------------------------------------

    def _qualifies_for_timeframe(
        self,
        tf: str,
        stock_data: Dict[str, Any],
        fresh_metrics: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Check all criteria for a specific timeframe.

        Returns:
            (qualified: bool, reasons: list[str], edge_cases: list[str])
        """
        crit = CRITERIA.get(tf, {})
        reasons: List[str] = []
        edge_cases: List[str] = []

        score = _safe_float(stock_data.get("score"), 0)
        market_cap = _safe_float(stock_data.get("market_cap"), 0)
        iv_rank = _safe_float(stock_data.get("iv_rank"))
        iv_percentile = _safe_float(stock_data.get("iv_percentile"))
        # Use iv_percentile as fallback for iv_rank
        effective_iv = iv_rank if iv_rank is not None else iv_percentile

        # --- Snapshot-derived metrics ---
        current_price = _safe_float(snapshot.get("current_price"))
        pct_change = abs(_safe_float(snapshot.get("change_percent"), 0))
        spread_pct = _calculate_spread_pct(snapshot)
        volume_ratio = _calculate_volume_ratio(snapshot, stock_data)

        # --- Fresh FMP indicators (accept both key formats) ---
        rsi = _safe_float(fresh_metrics.get("rsi"))
        sma20 = _safe_float(fresh_metrics.get("sma20") or fresh_metrics.get("sma_20"))
        sma50 = _safe_float(fresh_metrics.get("sma50") or fresh_metrics.get("sma_50"))
        sma200 = _safe_float(fresh_metrics.get("sma200") or fresh_metrics.get("sma_200"))
        adx = _safe_float(fresh_metrics.get("adx"))
        atr = _safe_float(fresh_metrics.get("atr"))

        # ============================================================
        # Hard disqualifiers (any failure → skip this timeframe)
        # ============================================================

        # Score floor
        min_score = crit.get("min_score", 50)
        if score < min_score:
            return False, [], [f"{tf}: score {score:.1f} < {min_score}"]

        # Market cap floor
        min_mcap = crit.get("min_market_cap", 0)
        if min_mcap and market_cap < min_mcap:
            return False, [], [f"{tf}: mcap {market_cap/1e9:.1f}B < {min_mcap/1e9:.0f}B"]

        # IV rank floor (if we have IV data and criterion exists)
        if effective_iv is not None and "min_iv_rank" in crit:
            if effective_iv < crit["min_iv_rank"]:
                return False, [], [f"{tf}: IV rank {effective_iv:.0f} < {crit['min_iv_rank']}"]

        # IV rank ceiling (for overnight holds — avoid blowup risk)
        if effective_iv is not None and "max_iv_rank" in crit:
            if effective_iv > crit["max_iv_rank"]:
                return False, [], [f"{tf}: IV rank {effective_iv:.0f} > {crit['max_iv_rank']}"]

        # ============================================================
        # Soft criteria (generate reasons + edge cases)
        # ============================================================

        # --- Volume ratio ---
        min_vol_ratio = crit.get("min_volume_ratio")
        if min_vol_ratio is not None and volume_ratio is not None:
            if volume_ratio < min_vol_ratio:
                edge_cases.append(f"{tf}: low volume ratio {volume_ratio:.2f}")
                # For 5m this is a hard disqualifier (need active tape)
                if tf == "5m":
                    return False, [], edge_cases
            else:
                reasons.append(f"Vol ratio {volume_ratio:.1f}x")

        # --- Intraday movement ---
        min_pct = crit.get("min_pct_change")
        if min_pct is not None and pct_change < min_pct:
            edge_cases.append(f"{tf}: pct change {pct_change:.2f}% < {min_pct}%")
            if tf == "5m":
                return False, [], edge_cases

        # --- Spread guard ---
        max_spread = crit.get("max_spread_pct")
        if max_spread is not None and spread_pct is not None:
            if spread_pct > max_spread:
                edge_cases.append(f"{tf}: spread {spread_pct:.3f}% > {max_spread}%")
                if tf in ("5m", "15m"):
                    return False, [], edge_cases

        # --- Trend requirement (1h: SMA20 > SMA50, 1d: SMA50 > SMA200) ---
        if crit.get("requires_trend"):
            if tf == "1h":
                if sma20 is not None and sma50 is not None:
                    if sma20 <= sma50:
                        edge_cases.append(f"{tf}: SMA20 {sma20:.2f} ≤ SMA50 {sma50:.2f} (no uptrend)")
                        return False, [], edge_cases
                    reasons.append(f"SMA20 > SMA50 uptrend")
                else:
                    edge_cases.append(f"{tf}: missing SMA data to verify trend")
            elif tf == "1d":
                if sma50 is not None and sma200 is not None:
                    if sma50 <= sma200:
                        edge_cases.append(f"{tf}: SMA50 {sma50:.2f} ≤ SMA200 {sma200:.2f} (no uptrend)")
                        return False, [], edge_cases
                    reasons.append(f"SMA50 > SMA200 uptrend")
                else:
                    edge_cases.append(f"{tf}: missing SMA data to verify trend")

        # --- ADX filter (1h) ---
        min_adx = crit.get("min_adx")
        if min_adx is not None and adx is not None:
            if adx < min_adx:
                edge_cases.append(f"{tf}: ADX {adx:.1f} < {min_adx} (weak trend)")
                return False, [], edge_cases
            reasons.append(f"ADX {adx:.0f}")

        # --- Additional positive signals ---
        if score >= 70:
            reasons.append(f"Strong score {score:.0f}")
        if effective_iv is not None and 30 <= effective_iv <= 50:
            reasons.append(f"Favorable IV rank {effective_iv:.0f}")
        if rsi is not None:
            if 40 <= rsi <= 60:
                reasons.append(f"Neutral RSI {rsi:.0f}")
            elif rsi < 30:
                if tf == "1d":
                    reasons.append(f"Oversold RSI {rsi:.0f} (mean reversion)")
                else:
                    edge_cases.append(f"Oversold RSI {rsi:.0f}")
            elif rsi > 70:
                if tf == "1d":
                    reasons.append(f"Overbought RSI {rsi:.0f} (mean reversion)")
                else:
                    edge_cases.append(f"Overbought RSI {rsi:.0f}")

        return True, reasons, edge_cases

    # ------------------------------------------------------------------
    # Internal: confidence calculation
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        score: float,
        qualified_timeframes: List[Dict],
        fresh_metrics: Dict[str, Any],
        edge_cases: List[str],
    ) -> str:
        """
        Determine overall confidence for this stock.

        HIGH  → auto-queue, no human review needed
        MEDIUM → AI batch review or manual queue
        LOW   → skip entirely
        """
        n_tf = len(qualified_timeframes)

        # LOW: nothing qualified or terrible score
        if n_tf == 0 or score < 50:
            return "LOW"

        # Count serious edge cases (exclude informational ones)
        serious_edges = [e for e in edge_cases if any(
            kw in e.lower() for kw in
            ("overbought", "oversold", "low volume", "spread", "missing sma", "weak trend")
        )]

        # HIGH confidence thresholds
        if score > 70 and serious_edges == []:
            return "HIGH"
        if n_tf >= 2 and score >= 65 and len(serious_edges) <= 1:
            return "HIGH"
        if n_tf == 1 and score >= 68 and serious_edges == []:
            return "HIGH"

        # MEDIUM: something qualified but there are concerns
        if n_tf >= 1:
            return "MEDIUM"

        return "LOW"


# ======================================================================
# Module-level helpers
# ======================================================================

def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely convert a value to float, returning default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _calculate_spread_pct(snapshot: Dict[str, Any]) -> Optional[float]:
    """Calculate bid-ask spread as a percentage of mid-price."""
    quote = snapshot.get("latest_quote", {})
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    if bid is not None and ask is not None and bid > 0:
        mid = (bid + ask) / 2
        if mid > 0:
            return ((ask - bid) / mid) * 100
    return None


def _calculate_volume_ratio(
    snapshot: Dict[str, Any],
    stock_data: Dict[str, Any],
) -> Optional[float]:
    """Calculate today's volume relative to average volume."""
    # Try snapshot daily_bar volume first
    today_vol = _safe_float(
        snapshot.get("daily_bar", {}).get("volume")
    )
    if today_vol is None:
        today_vol = _safe_float(snapshot.get("volume"))

    if today_vol is None or today_vol == 0:
        return None

    # Try to find average volume from stock_data technical indicators
    tech = stock_data.get("technical_indicators", {})
    avg_vol = _safe_float(tech.get("avg_volume"))

    # Fallback: previous day volume from snapshot
    if avg_vol is None or avg_vol == 0:
        prev_vol = _safe_float(
            snapshot.get("prev_daily_bar", {}).get("volume")
        )
        if prev_vol and prev_vol > 0:
            avg_vol = prev_vol

    if avg_vol is None or avg_vol == 0:
        return None

    return today_vol / avg_vol


# Singleton instance
strategy_selector = StrategySelector()
