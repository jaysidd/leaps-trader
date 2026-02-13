"""
Position Sizing Calculator

Uses Kelly Criterion with adjustments for:
- Market regime
- Conviction score
- Correlation with existing positions
- Upcoming catalysts
- Portfolio concentration limits
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum
from loguru import logger


class SizingMethod(str, Enum):
    """Position sizing methods."""
    KELLY = "kelly"
    FIXED_PERCENT = "fixed_percent"
    RISK_BASED = "risk_based"
    VOLATILITY_ADJUSTED = "volatility_adjusted"


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""
    recommended_size_pct: float  # % of portfolio
    recommended_size_dollars: float  # Dollar amount
    max_contracts: int  # Max number of option contracts
    max_risk_dollars: float  # Maximum loss

    # Sizing factors
    base_size_pct: float
    conviction_multiplier: float
    regime_multiplier: float
    catalyst_multiplier: float
    correlation_multiplier: float

    # Limits applied
    hit_max_position: bool = False
    hit_max_sector: bool = False
    hit_max_concentration: bool = False

    rationale: str = ""
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PositionSizer:
    """
    Position sizing calculator with Kelly Criterion and risk adjustments.

    Kelly Formula:
    f* = (bp - q) / b

    Where:
    - f* = fraction of portfolio to bet
    - b = odds (win size / loss size)
    - p = probability of winning
    - q = probability of losing (1 - p)

    We use a fractional Kelly (typically 0.5x) for safety.
    """

    # Default limits
    MAX_SINGLE_POSITION_PCT = 5.0  # Max 5% in any single position
    MAX_SECTOR_PCT = 20.0  # Max 20% in any sector
    MAX_CONCENTRATION_PCT = 30.0  # Max 30% in top 3 positions

    # Kelly fraction (conservative)
    KELLY_FRACTION = 0.5  # Half Kelly

    def __init__(self):
        pass

    def calculate_position_size(
        self,
        portfolio_value: float,
        conviction_score: int,  # 1-10
        win_probability: float = 0.55,  # Estimated probability of profit
        profit_target_pct: float = 100,  # Expected win %
        stop_loss_pct: float = 40,  # Expected loss %
        option_premium: float = 0,  # Cost per contract
        market_regime: str = "neutral",
        days_to_earnings: Optional[int] = None,
        sector: Optional[str] = None,
        existing_positions: Optional[List[Dict[str, Any]]] = None,
        method: SizingMethod = SizingMethod.KELLY
    ) -> PositionSizeResult:
        """
        Calculate optimal position size.

        Args:
            portfolio_value: Total portfolio value in dollars
            conviction_score: AI conviction score (1-10)
            win_probability: Estimated probability of hitting profit target
            profit_target_pct: Target profit as % of premium
            stop_loss_pct: Stop loss as % of premium
            option_premium: Option premium per contract
            market_regime: Current market regime
            days_to_earnings: Days until earnings (None if unknown)
            sector: Stock sector for concentration check
            existing_positions: List of existing positions for correlation
            method: Sizing method to use

        Returns:
            PositionSizeResult with recommended size and analysis
        """
        if method == SizingMethod.KELLY:
            base_size = self._kelly_sizing(
                win_probability,
                profit_target_pct / 100,
                stop_loss_pct / 100
            ) * 100  # Convert fraction to percentage
        elif method == SizingMethod.RISK_BASED:
            base_size = self._risk_based_sizing(stop_loss_pct / 100) * 100  # Convert fraction to percentage
        else:
            base_size = 2.0  # Default 2%

        # Apply adjustments
        conviction_mult = self._conviction_multiplier(conviction_score)
        regime_mult = self._regime_multiplier(market_regime)
        catalyst_mult = self._catalyst_multiplier(days_to_earnings)
        correlation_mult = self._correlation_multiplier(sector, existing_positions)

        # Calculate adjusted size
        adjusted_size = (
            base_size *
            conviction_mult *
            regime_mult *
            catalyst_mult *
            correlation_mult
        )

        # Apply limits
        final_size, hit_max_position = self._apply_position_limit(adjusted_size)
        final_size, hit_max_sector = self._apply_sector_limit(
            final_size, sector, existing_positions, portfolio_value
        )
        final_size, hit_max_concentration = self._apply_concentration_limit(
            final_size, existing_positions, portfolio_value
        )

        # Calculate dollar amounts
        size_dollars = portfolio_value * (final_size / 100)
        max_risk = size_dollars * (stop_loss_pct / 100)

        # Calculate max contracts if premium provided
        if option_premium > 0:
            contract_value = option_premium * 100  # Options are per 100 shares
            max_contracts = int(size_dollars / contract_value)
        else:
            max_contracts = 0

        # Generate rationale
        rationale = self._generate_rationale(
            base_size,
            conviction_mult,
            regime_mult,
            catalyst_mult,
            correlation_mult,
            final_size
        )

        # Generate warnings
        warnings = []
        if hit_max_position:
            warnings.append("Position capped at maximum single position limit")
        if hit_max_sector:
            warnings.append("Position reduced due to sector concentration")
        if hit_max_concentration:
            warnings.append("Position reduced due to portfolio concentration")
        if days_to_earnings and days_to_earnings <= 14:
            warnings.append(f"Earnings in {days_to_earnings} days - position size reduced")
        if conviction_score < 5:
            warnings.append("Low conviction - consider waiting for better setup")

        return PositionSizeResult(
            recommended_size_pct=round(final_size, 2),
            recommended_size_dollars=round(size_dollars, 2),
            max_contracts=max_contracts,
            max_risk_dollars=round(max_risk, 2),
            base_size_pct=round(base_size, 2),
            conviction_multiplier=round(conviction_mult, 2),
            regime_multiplier=round(regime_mult, 2),
            catalyst_multiplier=round(catalyst_mult, 2),
            correlation_multiplier=round(correlation_mult, 2),
            hit_max_position=hit_max_position,
            hit_max_sector=hit_max_sector,
            hit_max_concentration=hit_max_concentration,
            rationale=rationale,
            warnings=warnings
        )

    def _kelly_sizing(
        self,
        win_prob: float,
        win_size: float,
        loss_size: float
    ) -> float:
        """
        Calculate Kelly Criterion position size.

        Returns fraction as percentage (e.g., 0.05 = 5%)
        """
        if loss_size == 0:
            return 0.02  # Default

        b = win_size / loss_size  # Odds ratio
        p = win_prob
        q = 1 - p

        # Kelly formula
        kelly = (b * p - q) / b

        # Apply fractional Kelly for safety
        kelly = kelly * self.KELLY_FRACTION

        # Ensure positive and reasonable
        kelly = max(0, min(kelly, 0.10))  # Cap at 10%

        return kelly

    def _risk_based_sizing(self, loss_pct: float) -> float:
        """
        Size based on fixed risk per trade (1-2% of portfolio at risk).
        """
        target_risk = 0.02  # 2% portfolio risk per trade

        if loss_pct == 0:
            return 0.02

        # Position size = target risk / stop loss %
        size = target_risk / loss_pct

        return min(size, 0.10)  # Cap at 10%

    def _conviction_multiplier(self, conviction: int) -> float:
        """
        Adjust size based on conviction score.

        10 = 1.5x
        8-9 = 1.2x
        6-7 = 1.0x
        4-5 = 0.7x
        1-3 = 0.3x
        """
        if conviction >= 10:
            return 1.5
        elif conviction >= 8:
            return 1.2
        elif conviction >= 6:
            return 1.0
        elif conviction >= 4:
            return 0.7
        else:
            return 0.3

    def _regime_multiplier(self, regime: str) -> float:
        """
        Adjust size based on market regime.

        Bullish = 1.2x (can be more aggressive)
        Neutral = 1.0x
        Bearish = 0.7x (reduce long exposure)
        Volatile = 0.5x (reduce until clarity)
        """
        regime_lower = regime.lower()

        if regime_lower == 'bullish':
            return 1.2
        elif regime_lower == 'bearish':
            return 0.7
        elif regime_lower == 'volatile':
            return 0.5
        else:  # neutral
            return 1.0

    def _catalyst_multiplier(self, days_to_earnings: Optional[int]) -> float:
        """
        Reduce size near catalysts (earnings).

        <= 7 days = 0.3x (high risk)
        8-14 days = 0.6x
        15-30 days = 0.8x
        > 30 days = 1.0x
        """
        if days_to_earnings is None:
            return 1.0

        if days_to_earnings <= 7:
            return 0.3
        elif days_to_earnings <= 14:
            return 0.6
        elif days_to_earnings <= 30:
            return 0.8
        else:
            return 1.0

    def _correlation_multiplier(
        self,
        sector: Optional[str],
        existing_positions: Optional[List[Dict[str, Any]]]
    ) -> float:
        """
        Reduce size if correlated with existing positions.
        """
        if not existing_positions or not sector:
            return 1.0

        # Count same-sector positions
        same_sector_count = sum(
            1 for pos in existing_positions
            if pos.get('sector', '').lower() == sector.lower()
        )

        if same_sector_count >= 3:
            return 0.5
        elif same_sector_count >= 2:
            return 0.7
        elif same_sector_count >= 1:
            return 0.85
        else:
            return 1.0

    def _apply_position_limit(self, size_pct: float) -> tuple[float, bool]:
        """Apply maximum single position limit."""
        if size_pct > self.MAX_SINGLE_POSITION_PCT:
            return self.MAX_SINGLE_POSITION_PCT, True
        return size_pct, False

    def _apply_sector_limit(
        self,
        size_pct: float,
        sector: Optional[str],
        existing_positions: Optional[List[Dict[str, Any]]],
        portfolio_value: float
    ) -> tuple[float, bool]:
        """Apply sector concentration limit."""
        if not sector or not existing_positions:
            return size_pct, False

        # Calculate existing sector exposure
        sector_exposure = sum(
            pos.get('value', 0) for pos in existing_positions
            if pos.get('sector', '').lower() == sector.lower()
        )

        sector_pct = (sector_exposure / portfolio_value) * 100 if portfolio_value > 0 else 0

        # Check if adding this position would exceed limit
        if sector_pct + size_pct > self.MAX_SECTOR_PCT:
            max_allowed = max(0, self.MAX_SECTOR_PCT - sector_pct)
            return max_allowed, True

        return size_pct, False

    def _apply_concentration_limit(
        self,
        size_pct: float,
        existing_positions: Optional[List[Dict[str, Any]]],
        portfolio_value: float
    ) -> tuple[float, bool]:
        """Apply top 3 concentration limit."""
        if not existing_positions:
            return size_pct, False

        # Get top 3 position values
        positions_by_value = sorted(
            existing_positions,
            key=lambda x: x.get('value', 0),
            reverse=True
        )[:3]

        top3_value = sum(pos.get('value', 0) for pos in positions_by_value)
        top3_pct = (top3_value / portfolio_value) * 100 if portfolio_value > 0 else 0

        # This new position would be in top 3 if larger than smallest
        if len(positions_by_value) >= 3:
            smallest_top3 = positions_by_value[-1].get('value', 0)
            new_position_value = portfolio_value * (size_pct / 100)

            if new_position_value > smallest_top3:
                # Would replace smallest in top 3
                projected_top3_pct = top3_pct - (smallest_top3 / portfolio_value * 100) + size_pct

                if projected_top3_pct > self.MAX_CONCENTRATION_PCT:
                    max_allowed = max(0, self.MAX_CONCENTRATION_PCT - top3_pct + (smallest_top3 / portfolio_value * 100))
                    return max_allowed, True

        return size_pct, False

    def _generate_rationale(
        self,
        base_size: float,
        conviction_mult: float,
        regime_mult: float,
        catalyst_mult: float,
        correlation_mult: float,
        final_size: float
    ) -> str:
        """Generate human-readable rationale for position size."""
        parts = [f"Base size: {base_size:.1f}%"]

        if conviction_mult != 1.0:
            direction = "increased" if conviction_mult > 1.0 else "reduced"
            parts.append(f"Conviction {direction} by {abs(conviction_mult-1)*100:.0f}%")

        if regime_mult != 1.0:
            direction = "increased" if regime_mult > 1.0 else "reduced"
            parts.append(f"Market regime {direction} by {abs(regime_mult-1)*100:.0f}%")

        if catalyst_mult != 1.0:
            parts.append(f"Catalyst proximity reduced by {(1-catalyst_mult)*100:.0f}%")

        if correlation_mult != 1.0:
            parts.append(f"Correlation reduced by {(1-correlation_mult)*100:.0f}%")

        parts.append(f"Final size: {final_size:.2f}%")

        return " → ".join(parts)


# Global singleton
_position_sizer: Optional[PositionSizer] = None


def get_position_sizer() -> PositionSizer:
    """Get the global position sizer instance."""
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = PositionSizer()
    return _position_sizer
