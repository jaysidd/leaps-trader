"""
Macro Signal Service - Computes MRI and detects macro signals/divergences
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from loguru import logger
from sqlalchemy.orm import Session

from app.services.command_center.polymarket import get_polymarket_service, MacroConfig, _macro_config
from app.services.cache import cache
from app.models.mri_snapshot import MRISnapshot
from app.models.polymarket_snapshot import PolymarketMarketSnapshot


# =============================================================================
# RISK CONVERSION CONFIGURATION
# =============================================================================

# Per-category scaling parameters
CATEGORY_SCALING = {
    'recession': {'alpha': 1.0, 'beta': 0, 'invert': False},
    'trade': {'alpha': 1.0, 'beta': 0, 'invert': False},
    'elections': {'alpha': 0.8, 'beta': 10, 'invert': False},  # Dampened
    'fed_policy': {'alpha': 1.0, 'beta': 0, 'invert': True},   # Inverted (high rate cut odds = bullish)
    'crypto': {'alpha': 0.5, 'beta': 0, 'invert': True},       # Dampened + inverted
}

# MRI Regime thresholds
MRI_REGIME_THRESHOLDS = {
    'risk_on': (0, 33),
    'transition': (34, 66),
    'risk_off': (67, 100),
}

# Divergence proxy mappings
DIVERGENCE_PROXIES = {
    'SPY': {'name': 'S&P 500', 'risk_categories': ['recession', 'fed_policy', 'trade'], 'inverse': False},
    'QQQ': {'name': 'Nasdaq', 'risk_categories': ['recession', 'fed_policy', 'trade'], 'inverse': False},
    '^VIX': {'name': 'VIX', 'risk_categories': ['recession'], 'inverse': True},
    'DX-Y.NYB': {'name': 'Dollar Index', 'risk_categories': ['fed_policy', 'trade'], 'inverse': False},
    'TLT': {'name': '20Y Treasury', 'risk_categories': ['fed_policy', 'recession'], 'inverse': False},
}


@dataclass
class DivergenceConfig:
    """Configuration for divergence detection."""
    # Prediction market window
    PREDICTION_WINDOW: str = "24h"
    PREDICTION_LEAD_HOURS: int = 6

    # Proxy price window
    PROXY_WINDOW: str = "24h"
    PROXY_VOLATILITY_PERIOD: int = 14  # ATR period in days

    # Thresholds
    PREDICTION_SIGNIFICANT_PCT: float = 10.0
    PROXY_STABLE_ATR_MULT: float = 0.5

    # Persistence rules
    PERSISTENCE_MIN_CHECKS: int = 2
    PERSISTENCE_WINDOW_MINUTES: int = 30


class DivergencePersistence:
    """Track divergence detections across scheduler runs."""

    def __init__(self):
        self._detections: Dict[str, List[datetime]] = {}

    def record_detection(self, key: str) -> None:
        """Record a divergence detection."""
        if key not in self._detections:
            self._detections[key] = []
        self._detections[key].append(datetime.utcnow())
        # Keep only last hour of detections
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self._detections[key] = [t for t in self._detections[key] if t > cutoff]

    def check_persistence(self, key: str, min_checks: int = 2, window_minutes: int = 30) -> bool:
        """
        Check if divergence persisted across min_checks scheduler runs.

        Args:
            key: Divergence identifier (e.g., "recession:SPY:+")
            min_checks: Minimum consecutive detections required
            window_minutes: Time window for counting detections

        Returns:
            True if divergence has persisted
        """
        if key not in self._detections:
            return False

        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent = [t for t in self._detections[key] if t > cutoff]

        return len(recent) >= min_checks

    def clear_old_detections(self, max_age_hours: int = 2) -> None:
        """Clear old detection records."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        for key in list(self._detections.keys()):
            self._detections[key] = [t for t in self._detections[key] if t > cutoff]
            if not self._detections[key]:
                del self._detections[key]


class MacroSignalService:
    """
    Service for computing Macro Risk Index (MRI) and detecting macro signals.
    """

    def __init__(self):
        self._polymarket = get_polymarket_service()
        self._config = _macro_config
        self._divergence_config = DivergenceConfig()
        self._divergence_persistence = DivergencePersistence()
        self._last_api_success: Optional[datetime] = None
        self._cached_mri: Optional[Dict] = None

    # -------------------------------------------------------------------------
    # MRI CALCULATION
    # -------------------------------------------------------------------------

    def _convert_to_risk_score(
        self,
        odds: float,
        category: str,
        history: List[float] = None
    ) -> float:
        """
        Convert raw prediction odds to risk score (0-100).
        Supports per-category scaling and optional z-score normalization.

        Args:
            odds: Raw probability from 0-100
            category: Category name
            history: Optional historical values for z-score normalization

        Returns:
            Risk score from 0-100
        """
        params = CATEGORY_SCALING.get(category, {'alpha': 1.0, 'beta': 0, 'invert': False})

        # Apply inversion if needed
        base_score = (100 - odds) if params['invert'] else odds

        # Apply linear scaling: alpha * score + beta
        scaled = params['alpha'] * base_score + params['beta']

        # Optional: z-score normalization vs rolling history
        if history and len(history) >= 10:
            mean = sum(history) / len(history)
            std = (sum((x - mean) ** 2 for x in history) / len(history)) ** 0.5
            if std > 0:
                z_score = (scaled - mean) / std
                # Convert z-score to 0-100 (centered at 50)
                scaled = 50 + (z_score * 15)  # 1 std = 15 points

        return max(0, min(100, scaled))

    def _get_regime(self, mri_score: float) -> str:
        """
        Determine regime from MRI score.

        Args:
            mri_score: MRI value from 0-100

        Returns:
            Regime string: 'risk_on', 'transition', or 'risk_off'
        """
        for regime, (low, high) in MRI_REGIME_THRESHOLDS.items():
            if low <= mri_score <= high:
                return regime
        return 'transition'

    def _calculate_mri_confidence(self, components: Dict[str, Dict]) -> float:
        """
        Calculate MRI confidence based on data quality.
        Low confidence suppresses alerts and flags UI.

        Args:
            components: Dict of category -> get_category_aggregate() result

        Returns:
            Confidence score from 0-100
        """
        factors = []

        # 1. Number of markets contributing (max 25 points)
        total_markets = sum(c.get('markets_used', 0) for c in components.values())
        factors.append(min(total_markets / 10, 1.0) * 25)

        # 2. Total liquidity (max 25 points)
        total_liquidity = sum(c.get('total_liquidity', 0) for c in components.values())
        factors.append(min(total_liquidity / 500000, 1.0) * 25)

        # 3. Category coverage (max 20 points)
        categories_with_data = sum(
            1 for c in components.values()
            if c.get('aggregate_probability') is not None
        )
        factors.append((categories_with_data / 5) * 20)

        # 4. Dispersion penalty (max 30 points)
        category_confidences = [
            c.get('confidence_score', 50)
            for c in components.values()
            if c.get('confidence_score') is not None
        ]
        if category_confidences:
            avg_category_confidence = sum(category_confidences) / len(category_confidences)
            factors.append((avg_category_confidence / 100) * 30)
        else:
            factors.append(0)

        return min(sum(factors), 100)

    def _detect_shock(self, current_mri: float, history_1h: List[float]) -> bool:
        """
        Flag rapid MRI changes that may warrant attention.

        Args:
            current_mri: Current MRI score
            history_1h: List of MRI values from past hour

        Returns:
            True if shock detected
        """
        if not history_1h:
            return False

        avg_1h = sum(history_1h) / len(history_1h)
        change = abs(current_mri - avg_1h)

        # Shock if >10 point move in 1 hour
        return change > 10

    def _compute_drivers(
        self,
        components: Dict[str, Dict],
        weights: Dict[str, float]
    ) -> List[Dict]:
        """
        Compute top drivers for MRI explainability.
        Sorted by contribution_points descending.

        Args:
            components: Category aggregates
            weights: Category weights

        Returns:
            List of top 3 drivers with contribution details
        """
        drivers = []

        for category, aggregate in components.items():
            if aggregate.get('aggregate_probability') is None:
                continue

            prob = aggregate['aggregate_probability']
            weight = weights.get(category, 0)

            # Compute risk contribution
            risk_score = self._convert_to_risk_score(prob, category)
            contribution = risk_score * weight

            # Determine direction
            params = CATEGORY_SCALING.get(category, {})
            if params.get('invert', False):
                # Inverted: high odds = low risk = risk_on
                direction = "risk_on" if prob > 50 else "risk_off"
            else:
                # Normal: high odds = high risk = risk_off
                direction = "risk_off" if prob > 50 else "risk_on"

            # Get key market info
            key_market = aggregate.get('key_market', {})

            drivers.append({
                "market_id": key_market.get('id') if key_market else None,
                "title": key_market.get('title') if key_market else f"{category} aggregate",
                "category": category,
                "probability": prob,
                "weight": weight,
                "contribution_points": round(contribution, 1),
                "direction": direction,
            })

        # Sort by contribution and take top 3
        drivers.sort(key=lambda x: x['contribution_points'], reverse=True)
        return drivers[:3]

    async def calculate_mri(self, db: Session = None) -> Dict[str, Any]:
        """
        Calculate the Macro Risk Index (MRI).

        Args:
            db: Optional database session for storing snapshot

        Returns:
            Dictionary with MRI score, regime, confidence, drivers, etc.
        """
        try:
            # Get category aggregates
            components = await self._polymarket.get_all_category_aggregates()

            # Mark API success
            self._last_api_success = datetime.utcnow()

            # Get category weights
            weights = self._config.CATEGORY_WEIGHTS

            # Calculate weighted MRI score
            mri_score = 0.0
            total_weight = 0.0
            component_scores = {}

            for category, weight in weights.items():
                aggregate = components.get(category, {})
                prob = aggregate.get('aggregate_probability')

                if prob is not None:
                    risk_score = self._convert_to_risk_score(prob, category)
                    mri_score += risk_score * weight
                    total_weight += weight
                    component_scores[category] = risk_score

            # Normalize if not all categories have data
            if total_weight > 0 and total_weight < 1.0:
                mri_score = mri_score / total_weight

            mri_score = round(mri_score, 1)

            # Determine regime
            regime = self._get_regime(mri_score)

            # Calculate confidence
            confidence_score = self._calculate_mri_confidence(components)

            # Get historical MRI for change calculation and shock detection
            history_1h = await self._get_mri_history(hours=1, db=db)
            history_24h = await self._get_mri_history(hours=24, db=db)

            # Detect shock
            shock_flag = self._detect_shock(mri_score, history_1h)

            # Compute drivers
            drivers = self._compute_drivers(components, weights)

            # Calculate changes
            change_1h = None
            change_24h = None
            if history_1h:
                change_1h = round(mri_score - history_1h[0], 1)
            if history_24h:
                change_24h = round(mri_score - history_24h[0], 1)

            # Aggregate metadata
            markets_included = sum(c.get('markets_used', 0) for c in components.values())
            total_liquidity = sum(c.get('total_liquidity', 0) for c in components.values())

            result = {
                "mri_score": mri_score,
                "regime": regime,
                "regime_label": self._get_regime_label(regime),
                "confidence_score": round(confidence_score, 0),
                "confidence_label": self._get_confidence_label(confidence_score),
                "shock_flag": shock_flag,
                "drivers": drivers,
                "components": {
                    "fed_policy": component_scores.get('fed_policy'),
                    "recession": component_scores.get('recession'),
                    "elections": component_scores.get('elections'),
                    "trade": component_scores.get('trade'),
                    "crypto": component_scores.get('crypto'),
                },
                "component_aggregates": components,
                "markets_included": markets_included,
                "total_liquidity": total_liquidity,
                "change_1h": change_1h,
                "change_24h": change_24h,
                "data_stale": False,
                "last_api_success": self._last_api_success.isoformat() if self._last_api_success else None,
                "calculated_at": datetime.utcnow().isoformat(),
            }

            # Cache result
            self._cached_mri = result

            # Store snapshot if db provided
            if db:
                await self._store_mri_snapshot(result, components, db)

            return result

        except Exception as e:
            logger.error(f"Error calculating MRI: {e}")

            # Return last known MRI marked as stale
            if self._cached_mri:
                return {
                    **self._cached_mri,
                    "data_stale": True,
                    "stale_since": self._last_api_success.isoformat() if self._last_api_success else None,
                }

            # No historical data - return null state
            return {
                "mri_score": None,
                "regime": "unknown",
                "regime_label": "Unknown",
                "confidence_score": 0,
                "confidence_label": "none",
                "data_stale": True,
                "error": str(e),
            }

    async def _get_mri_history(self, hours: int, db: Session = None) -> List[float]:
        """
        Get historical MRI values.

        Args:
            hours: Number of hours to look back
            db: Database session

        Returns:
            List of MRI values (oldest first)
        """
        if not db:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            snapshots = db.query(MRISnapshot).filter(
                MRISnapshot.calculated_at >= cutoff
            ).order_by(MRISnapshot.calculated_at.asc()).all()

            return [s.mri_score for s in snapshots]
        except Exception as e:
            logger.warning(f"Error fetching MRI history: {e}")
            return []

    async def _store_mri_snapshot(
        self,
        result: Dict,
        components: Dict,
        db: Session
    ) -> None:
        """Store MRI snapshot to database."""
        try:
            snapshot = MRISnapshot(
                mri_score=result['mri_score'],
                regime=result['regime'],
                confidence_score=result['confidence_score'],
                shock_flag=result['shock_flag'],
                drivers=result['drivers'],
                fed_policy_score=result['components'].get('fed_policy'),
                recession_score=result['components'].get('recession'),
                elections_score=result['components'].get('elections'),
                trade_score=result['components'].get('trade'),
                crypto_score=result['components'].get('crypto'),
                markets_included=result['markets_included'],
                total_liquidity=result['total_liquidity'],
                market_data=components,
                change_1h=result['change_1h'],
                change_24h=result['change_24h'],
                data_stale=result['data_stale'],
                last_api_success=self._last_api_success,
            )
            db.add(snapshot)
            db.commit()
        except Exception as e:
            logger.error(f"Error storing MRI snapshot: {e}")
            db.rollback()

    def _get_regime_label(self, regime: str) -> str:
        """Get human-readable regime label."""
        labels = {
            "risk_on": "Risk-On",
            "transition": "Transition",
            "risk_off": "Risk-Off",
            "unknown": "Unknown",
        }
        return labels.get(regime, regime)

    def _get_confidence_label(self, score: float) -> str:
        """Get confidence label from numeric score."""
        if score >= 70:
            return "high"
        elif score >= 40:
            return "medium"
        else:
            return "low"

    # -------------------------------------------------------------------------
    # STALENESS CHECKING
    # -------------------------------------------------------------------------

    def _check_staleness(self) -> Dict[str, Any]:
        """Check data freshness and return staleness info."""
        if not self._last_api_success:
            return {"stale": True, "stale_minutes": None, "suppress_alerts": True}

        minutes_since = (datetime.utcnow() - self._last_api_success).total_seconds() / 60

        return {
            "stale": minutes_since > self._config.STALE_THRESHOLD_MINUTES,
            "stale_minutes": round(minutes_since, 1),
            "suppress_alerts": minutes_since > self._config.STALE_THRESHOLD_MINUTES,
            "last_api_success": self._last_api_success.isoformat(),
        }

    def get_cached_mri(self) -> Optional[Dict]:
        """Get cached MRI result."""
        return self._cached_mri

    # -------------------------------------------------------------------------
    # NARRATIVE MOMENTUM DETECTION
    # -------------------------------------------------------------------------

    async def detect_narrative_momentum(
        self,
        category: str,
        threshold_pct: float = 10.0,
        timeframe: str = "24h"
    ) -> Optional[Dict]:
        """
        Detect significant shifts in category odds (narrative momentum).

        Args:
            category: Category to check
            threshold_pct: Minimum change percentage
            timeframe: Timeframe for change calculation

        Returns:
            Momentum info dict if significant shift detected, None otherwise
        """
        try:
            aggregate = await self._polymarket.get_category_aggregate(category)

            # Check if we have historical data for comparison
            # For now, we rely on individual market change tracking
            key_market = aggregate.get('key_market')
            if not key_market:
                return None

            # Get markets in category with change data
            markets = await self._polymarket.get_markets_by_category(category)

            significant_moves = []
            for market in markets:
                change = market.get('change_24h')
                if change and abs(change) >= threshold_pct:
                    significant_moves.append({
                        "market_id": market.get('id'),
                        "title": market.get('title'),
                        "current_odds": market.get('implied_probability'),
                        "change": change,
                        "direction": "up" if change > 0 else "down",
                    })

            if not significant_moves:
                return None

            # Aggregate direction
            total_change = sum(m['change'] for m in significant_moves)
            overall_direction = "bullish" if total_change < 0 else "bearish"  # Inverted for risk

            return {
                "category": category,
                "overall_direction": overall_direction,
                "total_change": round(total_change, 1),
                "markets_moving": len(significant_moves),
                "significant_moves": significant_moves[:5],
                "aggregate_probability": aggregate.get('aggregate_probability'),
                "confidence": aggregate.get('confidence_label'),
            }

        except Exception as e:
            logger.error(f"Error detecting narrative momentum for {category}: {e}")
            return None

    # -------------------------------------------------------------------------
    # DIVERGENCE DETECTION
    # -------------------------------------------------------------------------

    async def detect_divergences(self, db: Session = None) -> List[Dict]:
        """
        Compare prediction odds vs market proxies with persistence and volatility awareness.

        Args:
            db: Database session for historical data

        Returns:
            List of detected divergences
        """
        divergences = []

        try:
            # Get category aggregates
            components = await self._polymarket.get_all_category_aggregates()

            for proxy_symbol, config in DIVERGENCE_PROXIES.items():
                # Get proxy price data with ATR
                proxy_data = await self._get_proxy_with_volatility(proxy_symbol)
                if not proxy_data:
                    continue

                for category in config['risk_categories']:
                    aggregate = components.get(category, {})
                    if not aggregate.get('aggregate_probability'):
                        continue

                    # Get category odds change from key market
                    key_market = aggregate.get('key_market')
                    if not key_market:
                        continue

                    # For now, we need to look at individual market changes
                    markets = await self._polymarket.get_markets_by_category(category)
                    total_change = sum(m.get('change_24h', 0) or 0 for m in markets if m.get('change_24h'))
                    avg_change = total_change / len(markets) if markets else 0

                    odds_change = avg_change

                    # Volatility-aware threshold
                    proxy_change_pct = proxy_data['change_24h']
                    proxy_atr_pct = proxy_data['atr_percent']

                    # Divergence: prediction moves significantly but price within normal range
                    prediction_significant = abs(odds_change) > self._divergence_config.PREDICTION_SIGNIFICANT_PCT
                    price_within_noise = abs(proxy_change_pct) < proxy_atr_pct * self._divergence_config.PROXY_STABLE_ATR_MULT

                    if prediction_significant and price_within_noise:
                        # Check persistence
                        persistence_key = f"{category}:{proxy_symbol}:{'+' if odds_change > 0 else '-'}"
                        self._divergence_persistence.record_detection(persistence_key)

                        if self._divergence_persistence.check_persistence(
                            persistence_key,
                            min_checks=self._divergence_config.PERSISTENCE_MIN_CHECKS
                        ):
                            # Determine divergence type
                            if config['inverse']:
                                # For VIX: if prediction bullish (risk down) but VIX stable = bullish divergence
                                divergence_type = 'bullish_divergence' if odds_change < 0 else 'bearish_divergence'
                            else:
                                # For SPY: if prediction bearish (risk up) but price stable = bearish divergence
                                divergence_type = 'bearish_divergence' if odds_change > 0 else 'bullish_divergence'

                            divergences.append({
                                "type": divergence_type,
                                "prediction_category": category,
                                "prediction_change": round(odds_change, 1),
                                "proxy_symbol": proxy_symbol,
                                "proxy_name": config['name'],
                                "proxy_change": round(proxy_change_pct, 2),
                                "proxy_atr": round(proxy_atr_pct, 2),
                                "persistence_checks": self._divergence_config.PERSISTENCE_MIN_CHECKS,
                                "interpretation": self._generate_divergence_interpretation(
                                    category, odds_change, proxy_symbol, proxy_change_pct
                                ),
                                "severity": "high" if abs(odds_change) > 15 else "medium",
                            })

            return divergences

        except Exception as e:
            logger.error(f"Error detecting divergences: {e}")
            return []

    async def _get_proxy_with_volatility(self, symbol: str) -> Optional[Dict]:
        """
        Get proxy price data with ATR for volatility-aware divergence detection.

        Args:
            symbol: Proxy symbol

        Returns:
            Dict with change_24h and atr_percent, or None
        """
        try:
            from app.services.data_fetcher.alpaca_service import alpaca_service

            # Get current price and historical data
            import asyncio
            price_data = await asyncio.to_thread(lambda s=symbol: alpaca_service.get_historical_prices(s, period="1mo"))
            if price_data is None or price_data.empty:
                return None

            # Calculate 24h change
            if len(price_data) >= 2:
                current = price_data['close'].iloc[-1]
                prev_day = price_data['close'].iloc[-2]
                change_24h = ((current - prev_day) / prev_day) * 100
            else:
                return None

            # Calculate ATR percentage
            if len(price_data) >= self._divergence_config.PROXY_VOLATILITY_PERIOD:
                high = price_data['high'].tail(self._divergence_config.PROXY_VOLATILITY_PERIOD)
                low = price_data['low'].tail(self._divergence_config.PROXY_VOLATILITY_PERIOD)
                close = price_data['close'].tail(self._divergence_config.PROXY_VOLATILITY_PERIOD)

                tr1 = high - low
                tr2 = abs(high - close.shift(1))
                tr3 = abs(low - close.shift(1))

                tr = tr1.combine(tr2, max).combine(tr3, max)
                atr = tr.mean()
                atr_percent = (atr / current) * 100
            else:
                atr_percent = 2.0  # Default 2%

            return {
                "symbol": symbol,
                "current_price": current,
                "change_24h": change_24h,
                "atr_percent": atr_percent,
            }

        except Exception as e:
            logger.warning(f"Error getting proxy data for {symbol}: {e}")
            return None

    def _generate_divergence_interpretation(
        self,
        category: str,
        odds_change: float,
        proxy_symbol: str,
        proxy_change: float
    ) -> str:
        """Generate human-readable interpretation of divergence."""
        category_names = {
            'recession': 'recession probability',
            'fed_policy': 'rate cut expectations',
            'trade': 'trade war risk',
            'elections': 'political uncertainty',
            'crypto': 'crypto sentiment',
        }

        cat_name = category_names.get(category, category)
        direction = "increased" if odds_change > 0 else "decreased"

        if proxy_symbol in ['^VIX']:
            proxy_desc = f"VIX remained relatively stable ({proxy_change:+.1f}%)"
        else:
            proxy_desc = f"{proxy_symbol} showed little reaction ({proxy_change:+.1f}%)"

        return f"Prediction markets show {cat_name} has {direction} by {abs(odds_change):.1f}%, but {proxy_desc}. This divergence may indicate a pending market move."

    # -------------------------------------------------------------------------
    # TICKER MACRO BIAS
    # -------------------------------------------------------------------------

    async def get_ticker_macro_bias(
        self,
        symbol: str,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Get macro bias for a specific ticker based on sector weights.

        Args:
            symbol: Stock symbol
            db: Database session

        Returns:
            Ticker macro bias with explanation
        """
        try:
            from app.services.data_fetcher.fmp_service import fmp_service

            # Get stock sector
            import asyncio
            stock_info = await asyncio.to_thread(fmp_service.get_stock_info, symbol)
            sector = stock_info.get('sector', 'Unknown') if stock_info else 'Unknown'

            # Get sector weights (or defaults)
            weights = await self._get_ticker_weights(symbol, sector, db)

            # Get current category aggregates
            components = await self._polymarket.get_all_category_aggregates()

            # Calculate ticker-specific bias score
            bias_score = 0.0
            total_weight = 0.0
            category_contributions = []

            for category, weight in weights.items():
                if weight == 0 or category not in components:
                    continue

                aggregate = components.get(category, {})
                prob = aggregate.get('aggregate_probability')

                if prob is not None:
                    risk_score = self._convert_to_risk_score(prob, category)
                    contribution = risk_score * weight
                    bias_score += contribution
                    total_weight += weight

                    category_contributions.append({
                        "category": category,
                        "weight": weight,
                        "probability": prob,
                        "risk_score": round(risk_score, 1),
                        "contribution": round(contribution, 1),
                    })

            if total_weight > 0:
                bias_score = bias_score / total_weight

            # Determine bias label
            if bias_score <= 33:
                bias_label = "bullish"
                bias_color = "green"
            elif bias_score <= 66:
                bias_label = "neutral"
                bias_color = "yellow"
            else:
                bias_label = "bearish"
                bias_color = "red"

            # Sort contributions by absolute value
            category_contributions.sort(key=lambda x: abs(x['contribution']), reverse=True)

            return {
                "symbol": symbol,
                "sector": sector,
                "bias_score": round(bias_score, 1),
                "bias_label": bias_label,
                "bias_color": bias_color,
                "weights": weights,
                "category_contributions": category_contributions,
                "top_driver": category_contributions[0] if category_contributions else None,
                "calculated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error calculating ticker macro bias for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "bias_score": None,
                "bias_label": "unknown",
            }

    async def _get_ticker_weights(
        self,
        symbol: str,
        sector: str,
        db: Session = None
    ) -> Dict[str, float]:
        """Get macro category weights for a ticker."""
        from app.models.sector_macro_mapping import SectorMacroMapping, TickerMacroOverride, DEFAULT_SECTOR_MAPPINGS

        # Default weights if no DB or no mapping found
        default_weights = {
            'fed_policy': 0.25,
            'recession': 0.25,
            'elections': 0.15,
            'trade': 0.15,
            'crypto': 0.0,
        }

        if not db:
            # Try to get from default mappings
            for mapping in DEFAULT_SECTOR_MAPPINGS:
                if mapping['sector'].lower() == sector.lower():
                    return {
                        'fed_policy': mapping['weight_fed_policy'],
                        'recession': mapping['weight_recession'],
                        'elections': mapping['weight_elections'],
                        'trade': mapping['weight_trade'],
                        'crypto': mapping['weight_crypto'],
                    }
            return default_weights

        try:
            # Check for ticker override first
            override = db.query(TickerMacroOverride).filter(
                TickerMacroOverride.symbol == symbol.upper()
            ).first()

            if override:
                # Get sector mapping for fallback
                sector_mapping = None
                if override.sector:
                    sector_mapping = db.query(SectorMacroMapping).filter(
                        SectorMacroMapping.sector == override.sector
                    ).first()
                return override.get_weights(sector_mapping)

            # Get sector mapping
            sector_mapping = db.query(SectorMacroMapping).filter(
                SectorMacroMapping.sector == sector
            ).first()

            if sector_mapping:
                return sector_mapping.get_weights()

            return default_weights

        except Exception as e:
            logger.warning(f"Error getting ticker weights: {e}")
            return default_weights


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_macro_signal_service: Optional[MacroSignalService] = None


def get_macro_signal_service() -> MacroSignalService:
    """Get the global MacroSignalService instance."""
    global _macro_signal_service
    if _macro_signal_service is None:
        _macro_signal_service = MacroSignalService()
    return _macro_signal_service
