"""
Options Strategy Recommendation Engine

Phase 3: Intelligent strategy selection based on:
- Market regime (bullish/bearish/neutral)
- IV rank (cheap/fair/expensive options)
- Conviction score (how aggressive to be)
- Days to earnings (event risk)
- Stock trend and momentum
- Portfolio context
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from loguru import logger

from app.services.ai.market_regime import get_regime_detector
from app.services.data_fetcher.tastytrade import get_tastytrade_service


class StrategyType(str, Enum):
    """Available options strategies."""
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    BULL_CALL_SPREAD = "bull_call_spread"
    BEAR_PUT_SPREAD = "bear_put_spread"
    LEAPS_CALL = "leaps_call"
    LEAPS_PUT = "leaps_put"
    CASH_SECURED_PUT = "cash_secured_put"
    COVERED_CALL = "covered_call"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    CALENDAR_SPREAD = "calendar_spread"
    DIAGONAL_SPREAD = "diagonal_spread"
    WAIT = "wait"
    AVOID = "avoid"


class RiskLevel(str, Enum):
    """Risk tolerance levels."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategyParams:
    """Parameters for a recommended strategy."""
    strategy_type: StrategyType
    confidence: int  # 1-10

    # Strike selection
    target_delta: float  # 0.0 - 1.0
    delta_range: Tuple[float, float]  # Acceptable range

    # Time selection
    target_dte: int  # Days to expiration
    dte_range: Tuple[int, int]  # Acceptable range

    # Position sizing
    max_position_pct: float  # % of portfolio
    max_risk_pct: float  # Max loss as % of portfolio

    # Entry/Exit
    entry_type: str  # "limit", "market", "scaled"
    profit_target_pct: float  # Target gain %
    stop_loss_pct: float  # Max loss %
    time_stop_dte: int  # Roll/close if below this DTE

    # Rationale
    rationale: str
    key_factors: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)


@dataclass
class StrategyRecommendation:
    """Complete strategy recommendation for a stock."""
    symbol: str
    strategy: StrategyParams
    alternatives: List[StrategyParams] = field(default_factory=list)

    # Context used for decision
    market_regime: str = "neutral"
    iv_rank: float = 50.0
    conviction_score: int = 5
    days_to_earnings: Optional[int] = None
    trend_direction: str = "neutral"

    # Specific contract suggestion (if available)
    suggested_contract: Optional[Dict[str, Any]] = None

    generated_at: datetime = field(default_factory=datetime.now)


class StrategyEngine:
    """
    Intelligent options strategy recommendation engine.

    Decision Matrix:
    ┌─────────────────┬────────────┬────────────────┬─────────────────────────┐
    │ Condition       │ IV Rank    │ Trend          │ Recommendation          │
    ├─────────────────┼────────────┼────────────────┼─────────────────────────┤
    │ High conviction │ < 30%      │ Bullish        │ LEAPS Call (0.70 delta) │
    │ High conviction │ 30-50%     │ Bullish        │ Long Call (0.60 delta)  │
    │ High conviction │ > 50%      │ Bullish        │ Bull Call Spread        │
    │ Med conviction  │ < 30%      │ Bullish        │ Long Call (0.50 delta)  │
    │ Med conviction  │ > 50%      │ Bullish        │ Bull Call Spread        │
    │ Any conviction  │ Any        │ Near earnings  │ Wait or Spread          │
    │ Low conviction  │ Any        │ Any            │ Wait / Avoid            │
    │ Any conviction  │ > 70%      │ Neutral        │ Iron Condor / Sell Prem │
    └─────────────────┴────────────┴────────────────┴─────────────────────────┘
    """

    # Strategy selection thresholds
    IV_CHEAP_THRESHOLD = 30
    IV_FAIR_THRESHOLD = 50
    IV_EXPENSIVE_THRESHOLD = 70

    CONVICTION_HIGH = 7
    CONVICTION_MED = 5
    CONVICTION_LOW = 3

    EARNINGS_DANGER_DAYS = 14
    EARNINGS_CAUTION_DAYS = 30

    def __init__(self):
        self.regime_detector = get_regime_detector()
        self.tastytrade = get_tastytrade_service()

    def _get_tastytrade_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch enhanced options data from TastyTrade if available.

        Returns:
            Dictionary with IV metrics, Greeks, and LEAPS expirations
        """
        if not self.tastytrade.is_available():
            return {}

        try:
            return self.tastytrade.get_enhanced_options_data(symbol)
        except Exception as e:
            logger.warning(f"Failed to get TastyTrade data for {symbol}: {e}")
            return {}

    async def recommend_strategy(
        self,
        stock_data: Dict[str, Any],
        market_regime: Optional[Dict[str, Any]] = None,
        conviction_score: int = 5,
        risk_tolerance: RiskLevel = RiskLevel.MODERATE,
        portfolio_context: Optional[Dict[str, Any]] = None
    ) -> StrategyRecommendation:
        """
        Generate strategy recommendation for a stock.

        Args:
            stock_data: Stock screening/analysis data
            market_regime: Current market regime (fetched if not provided)
            conviction_score: AI conviction score (1-10)
            risk_tolerance: User's risk tolerance
            portfolio_context: Current portfolio info for sizing

        Returns:
            StrategyRecommendation with primary and alternative strategies
        """
        symbol = stock_data.get('symbol', 'UNKNOWN')

        # Enhance with TastyTrade data if available
        tastytrade_data = self._get_tastytrade_data(symbol)
        if tastytrade_data:
            # Merge TastyTrade data into stock_data
            stock_data['tastytrade'] = tastytrade_data
            # Use TastyTrade IV rank if available (more accurate)
            if tastytrade_data.get('iv_rank') is not None:
                stock_data['iv_rank_tastytrade'] = tastytrade_data['iv_rank']
            if tastytrade_data.get('beta') is not None:
                stock_data['beta'] = tastytrade_data['beta']
            if tastytrade_data.get('leaps_expirations'):
                stock_data['leaps_expirations'] = tastytrade_data['leaps_expirations']

        # Get market regime if not provided
        if not market_regime:
            try:
                market_regime = await self.regime_detector.get_regime()
            except Exception:
                market_regime = {'regime': 'neutral', 'risk_mode': 'mixed'}

        # Extract key factors (prefer TastyTrade IV rank)
        iv_rank = self._get_iv_rank(stock_data)
        days_to_earnings = stock_data.get('days_to_earnings')
        trend = self._determine_trend(stock_data)
        regime = market_regime.get('regime', 'neutral')

        # Determine primary strategy
        primary_strategy = self._select_strategy(
            conviction=conviction_score,
            iv_rank=iv_rank,
            trend=trend,
            regime=regime,
            days_to_earnings=days_to_earnings,
            risk_tolerance=risk_tolerance
        )

        # Generate alternatives
        alternatives = self._generate_alternatives(
            primary_strategy,
            conviction_score,
            iv_rank,
            trend,
            regime
        )

        # Get specific contract suggestion if we have options data
        suggested_contract = None
        if stock_data.get('leaps_summary'):
            suggested_contract = self._suggest_contract(
                stock_data,
                primary_strategy
            )

        return StrategyRecommendation(
            symbol=symbol,
            strategy=primary_strategy,
            alternatives=alternatives,
            market_regime=regime,
            iv_rank=iv_rank,
            conviction_score=conviction_score,
            days_to_earnings=days_to_earnings,
            trend_direction=trend,
            suggested_contract=suggested_contract
        )

    def _get_iv_rank(self, stock_data: Dict[str, Any]) -> float:
        """
        Extract IV rank from stock data.

        Priority order:
        1. TastyTrade IV rank (most accurate, real-time)
        2. LEAPS summary IV rank
        3. Options data IV rank
        4. Default to 50 (neutral)
        """
        # Prefer TastyTrade IV rank (most accurate)
        if iv := stock_data.get('iv_rank_tastytrade'):
            return float(iv)

        # Check TastyTrade nested data
        if tastytrade := stock_data.get('tastytrade'):
            if iv := tastytrade.get('iv_rank'):
                return float(iv)

        # Fallback to LEAPS summary
        if leaps := stock_data.get('leaps_summary'):
            if iv := leaps.get('iv_rank'):
                return float(iv)

        # Fallback to options data
        if options := stock_data.get('options_data'):
            if iv := options.get('iv_rank'):
                return float(iv)

        return 50.0  # Default to neutral

    def _determine_trend(self, stock_data: Dict[str, Any]) -> str:
        """Determine trend direction from technical data."""
        indicators = stock_data.get('technical_indicators', {})

        # Check SMA alignment
        price = stock_data.get('current_price', 0)
        sma_50 = indicators.get('sma_50', 0)
        sma_200 = indicators.get('sma_200', 0)

        if price and sma_50 and sma_200:
            if price > sma_50 > sma_200:
                return 'bullish'
            elif price < sma_50 < sma_200:
                return 'bearish'

        # Check RSI
        rsi = indicators.get('rsi_14', 50)
        if rsi > 60:
            return 'bullish'
        elif rsi < 40:
            return 'bearish'

        return 'neutral'

    def _select_strategy(
        self,
        conviction: int,
        iv_rank: float,
        trend: str,
        regime: str,
        days_to_earnings: Optional[int],
        risk_tolerance: RiskLevel
    ) -> StrategyParams:
        """
        Select the optimal strategy based on all factors.
        """
        # Check for earnings risk first
        if days_to_earnings is not None and days_to_earnings <= self.EARNINGS_DANGER_DAYS:
            return self._earnings_strategy(conviction, iv_rank, days_to_earnings)

        # Low conviction = wait or avoid
        if conviction < self.CONVICTION_LOW:
            return StrategyParams(
                strategy_type=StrategyType.AVOID,
                confidence=2,
                target_delta=0,
                delta_range=(0, 0),
                target_dte=0,
                dte_range=(0, 0),
                max_position_pct=0,
                max_risk_pct=0,
                entry_type="none",
                profit_target_pct=0,
                stop_loss_pct=0,
                time_stop_dte=0,
                rationale="Conviction too low for any position",
                key_factors=["Low conviction score"],
                risks=["No clear edge identified"]
            )

        # Bearish trend in bullish regime = wait
        if trend == 'bearish' and regime == 'bullish':
            return self._wait_strategy("Stock bearish despite bullish market")

        # Bullish strategies
        if trend == 'bullish' or (trend == 'neutral' and regime == 'bullish'):
            return self._bullish_strategy(conviction, iv_rank, risk_tolerance, regime)

        # Bearish strategies
        if trend == 'bearish' or (trend == 'neutral' and regime == 'bearish'):
            return self._bearish_strategy(conviction, iv_rank, risk_tolerance)

        # Neutral/sideways
        if iv_rank > self.IV_EXPENSIVE_THRESHOLD:
            return self._neutral_high_iv_strategy(conviction)

        return self._wait_strategy("No clear directional edge")

    def _bullish_strategy(
        self,
        conviction: int,
        iv_rank: float,
        risk_tolerance: RiskLevel,
        regime: str
    ) -> StrategyParams:
        """Select bullish strategy based on IV and conviction."""

        # High conviction + cheap IV = LEAPS
        if conviction >= self.CONVICTION_HIGH and iv_rank < self.IV_CHEAP_THRESHOLD:
            delta = 0.70 if risk_tolerance == RiskLevel.AGGRESSIVE else 0.65
            return StrategyParams(
                strategy_type=StrategyType.LEAPS_CALL,
                confidence=min(10, conviction + 1),
                target_delta=delta,
                delta_range=(0.60, 0.80),
                target_dte=365,
                dte_range=(270, 540),
                max_position_pct=5.0 if risk_tolerance == RiskLevel.AGGRESSIVE else 3.0,
                max_risk_pct=5.0,
                entry_type="limit",
                profit_target_pct=150,
                stop_loss_pct=40,
                time_stop_dte=90,
                rationale="High conviction with cheap options - ideal for LEAPS",
                key_factors=[
                    f"IV Rank {iv_rank:.0f}% (cheap)",
                    f"Conviction {conviction}/10",
                    f"Market regime: {regime}"
                ],
                risks=[
                    "Long time horizon = more uncertainty",
                    "Large premium at risk"
                ]
            )

        # High conviction + fair IV = Long call
        if conviction >= self.CONVICTION_HIGH and iv_rank < self.IV_FAIR_THRESHOLD:
            delta = 0.60 if risk_tolerance == RiskLevel.AGGRESSIVE else 0.55
            return StrategyParams(
                strategy_type=StrategyType.LONG_CALL,
                confidence=conviction,
                target_delta=delta,
                delta_range=(0.50, 0.70),
                target_dte=90,
                dte_range=(60, 120),
                max_position_pct=3.0,
                max_risk_pct=3.0,
                entry_type="limit",
                profit_target_pct=100,
                stop_loss_pct=35,
                time_stop_dte=30,
                rationale="High conviction with fair IV - standard long call",
                key_factors=[
                    f"IV Rank {iv_rank:.0f}% (fair)",
                    f"Conviction {conviction}/10"
                ],
                risks=[
                    "Theta decay accelerates near expiration",
                    "IV crush risk if volatility drops"
                ]
            )

        # High conviction + expensive IV = Spread to reduce IV risk
        if conviction >= self.CONVICTION_HIGH:
            return StrategyParams(
                strategy_type=StrategyType.BULL_CALL_SPREAD,
                confidence=conviction - 1,
                target_delta=0.55,
                delta_range=(0.45, 0.65),
                target_dte=60,
                dte_range=(45, 90),
                max_position_pct=2.5,
                max_risk_pct=2.5,
                entry_type="limit",
                profit_target_pct=80,
                stop_loss_pct=50,
                time_stop_dte=21,
                rationale="High conviction but expensive IV - spread reduces vega risk",
                key_factors=[
                    f"IV Rank {iv_rank:.0f}% (expensive)",
                    "Spread caps max profit but limits IV risk"
                ],
                risks=[
                    "Capped upside if stock really runs",
                    "Requires precise strike selection"
                ]
            )

        # Medium conviction + cheap IV = Long call with smaller size
        if conviction >= self.CONVICTION_MED and iv_rank < self.IV_FAIR_THRESHOLD:
            return StrategyParams(
                strategy_type=StrategyType.LONG_CALL,
                confidence=conviction,
                target_delta=0.50,
                delta_range=(0.45, 0.60),
                target_dte=60,
                dte_range=(45, 90),
                max_position_pct=2.0,
                max_risk_pct=2.0,
                entry_type="limit",
                profit_target_pct=75,
                stop_loss_pct=30,
                time_stop_dte=21,
                rationale="Medium conviction with acceptable IV",
                key_factors=[
                    f"IV Rank {iv_rank:.0f}%",
                    f"Conviction {conviction}/10 - smaller size"
                ],
                risks=[
                    "Not maximum conviction",
                    "Consider waiting for better entry"
                ]
            )

        # Medium conviction + expensive IV = Spread
        if conviction >= self.CONVICTION_MED:
            return StrategyParams(
                strategy_type=StrategyType.BULL_CALL_SPREAD,
                confidence=conviction - 1,
                target_delta=0.50,
                delta_range=(0.40, 0.60),
                target_dte=45,
                dte_range=(30, 60),
                max_position_pct=2.0,
                max_risk_pct=2.0,
                entry_type="limit",
                profit_target_pct=60,
                stop_loss_pct=40,
                time_stop_dte=14,
                rationale="Medium conviction with expensive IV - spread required",
                key_factors=[
                    f"IV Rank {iv_rank:.0f}% (expensive)",
                    "Spread structure necessary"
                ],
                risks=[
                    "Limited upside",
                    "Medium conviction = smaller edge"
                ]
            )

        return self._wait_strategy("Conditions not optimal for entry")

    def _bearish_strategy(
        self,
        conviction: int,
        iv_rank: float,
        risk_tolerance: RiskLevel
    ) -> StrategyParams:
        """Select bearish strategy."""
        # For LEAPS-focused tool, bearish = usually wait or hedge
        if conviction >= self.CONVICTION_HIGH and iv_rank < self.IV_FAIR_THRESHOLD:
            return StrategyParams(
                strategy_type=StrategyType.LONG_PUT,
                confidence=conviction,
                target_delta=-0.50,
                delta_range=(-0.60, -0.40),
                target_dte=60,
                dte_range=(45, 90),
                max_position_pct=2.0,
                max_risk_pct=2.0,
                entry_type="limit",
                profit_target_pct=75,
                stop_loss_pct=30,
                time_stop_dte=21,
                rationale="Bearish conviction with reasonable IV",
                key_factors=[
                    "Strong bearish signals",
                    f"IV Rank {iv_rank:.0f}%"
                ],
                risks=[
                    "Fighting the long-term upward bias",
                    "Timing is harder for puts"
                ]
            )

        return self._wait_strategy("Bearish setup - LEAPS focus is bullish")

    def _neutral_high_iv_strategy(self, conviction: int) -> StrategyParams:
        """Strategy for neutral market with high IV."""
        return StrategyParams(
            strategy_type=StrategyType.IRON_CONDOR,
            confidence=min(7, conviction),
            target_delta=0.20,
            delta_range=(0.15, 0.25),
            target_dte=45,
            dte_range=(30, 60),
            max_position_pct=3.0,
            max_risk_pct=3.0,
            entry_type="limit",
            profit_target_pct=50,
            stop_loss_pct=100,
            time_stop_dte=14,
            rationale="High IV in neutral market - sell premium",
            key_factors=[
                "Elevated IV = rich premiums",
                "Range-bound expected"
            ],
            risks=[
                "Breakout would cause losses",
                "Requires active management"
            ]
        )

    def _earnings_strategy(
        self,
        conviction: int,
        iv_rank: float,
        days_to_earnings: int
    ) -> StrategyParams:
        """Strategy around earnings."""
        if days_to_earnings <= 7:
            return StrategyParams(
                strategy_type=StrategyType.WAIT,
                confidence=3,
                target_delta=0,
                delta_range=(0, 0),
                target_dte=0,
                dte_range=(0, 0),
                max_position_pct=0,
                max_risk_pct=0,
                entry_type="none",
                profit_target_pct=0,
                stop_loss_pct=0,
                time_stop_dte=0,
                rationale=f"Earnings in {days_to_earnings} days - wait for post-ER entry",
                key_factors=[
                    "IV will crush after earnings",
                    "Binary event risk too high"
                ],
                risks=["Missing a big move if you don't play earnings"]
            )

        # 7-14 days = spreads only
        return StrategyParams(
            strategy_type=StrategyType.BULL_CALL_SPREAD,
            confidence=min(6, conviction),
            target_delta=0.50,
            delta_range=(0.40, 0.60),
            target_dte=max(30, days_to_earnings + 14),
            dte_range=(21, 60),
            max_position_pct=1.5,
            max_risk_pct=1.5,
            entry_type="limit",
            profit_target_pct=50,
            stop_loss_pct=40,
            time_stop_dte=7,
            rationale=f"Earnings approaching ({days_to_earnings}d) - spread to limit IV risk",
            key_factors=[
                "Spread structure hedges IV crush",
                "Reduced position size"
            ],
            risks=[
                "Still exposed to earnings gap",
                "Should close/roll before ER"
            ]
        )

    def _wait_strategy(self, reason: str) -> StrategyParams:
        """Return a wait recommendation."""
        return StrategyParams(
            strategy_type=StrategyType.WAIT,
            confidence=4,
            target_delta=0,
            delta_range=(0, 0),
            target_dte=0,
            dte_range=(0, 0),
            max_position_pct=0,
            max_risk_pct=0,
            entry_type="none",
            profit_target_pct=0,
            stop_loss_pct=0,
            time_stop_dte=0,
            rationale=reason,
            key_factors=["Conditions not favorable"],
            risks=["May miss opportunity if conditions change quickly"]
        )

    def _generate_alternatives(
        self,
        primary: StrategyParams,
        conviction: int,
        iv_rank: float,
        trend: str,
        regime: str
    ) -> List[StrategyParams]:
        """Generate 1-2 alternative strategies."""
        alternatives = []

        # If primary is LEAPS, offer shorter-dated alternative
        if primary.strategy_type == StrategyType.LEAPS_CALL:
            alternatives.append(StrategyParams(
                strategy_type=StrategyType.LONG_CALL,
                confidence=conviction - 1,
                target_delta=0.55,
                delta_range=(0.50, 0.65),
                target_dte=90,
                dte_range=(60, 120),
                max_position_pct=2.5,
                max_risk_pct=2.5,
                entry_type="limit",
                profit_target_pct=80,
                stop_loss_pct=30,
                time_stop_dte=30,
                rationale="Shorter-dated alternative if you want less capital at risk",
                key_factors=["Lower premium", "Faster time decay"],
                risks=["Less time for thesis to play out"]
            ))

        # If primary is long call, offer spread alternative
        if primary.strategy_type == StrategyType.LONG_CALL and iv_rank > 40:
            alternatives.append(StrategyParams(
                strategy_type=StrategyType.BULL_CALL_SPREAD,
                confidence=conviction - 1,
                target_delta=0.50,
                delta_range=(0.45, 0.60),
                target_dte=60,
                dte_range=(45, 90),
                max_position_pct=2.0,
                max_risk_pct=2.0,
                entry_type="limit",
                profit_target_pct=60,
                stop_loss_pct=40,
                time_stop_dte=21,
                rationale="Spread alternative to reduce IV exposure",
                key_factors=["Lower vega risk", "Defined risk"],
                risks=["Capped upside"]
            ))

        # If waiting, offer small position alternative
        if primary.strategy_type == StrategyType.WAIT and conviction >= 5:
            alternatives.append(StrategyParams(
                strategy_type=StrategyType.LONG_CALL,
                confidence=conviction - 2,
                target_delta=0.45,
                delta_range=(0.40, 0.55),
                target_dte=60,
                dte_range=(45, 90),
                max_position_pct=1.0,
                max_risk_pct=1.0,
                entry_type="limit",
                profit_target_pct=50,
                stop_loss_pct=25,
                time_stop_dte=21,
                rationale="Small starter position if you don't want to miss the move",
                key_factors=["Reduced size", "Early entry"],
                risks=["Suboptimal timing", "Smaller size = less impact"]
            ))

        return alternatives[:2]  # Max 2 alternatives

    def _suggest_contract(
        self,
        stock_data: Dict[str, Any],
        strategy: StrategyParams
    ) -> Optional[Dict[str, Any]]:
        """Suggest a specific contract based on strategy params."""
        if strategy.strategy_type in [StrategyType.WAIT, StrategyType.AVOID]:
            return None

        leaps = stock_data.get('leaps_summary', {})
        current_price = stock_data.get('current_price', 0)

        if not current_price:
            return None

        # Calculate target strike based on delta
        # This is a rough approximation - real implementation would use options chain
        delta = strategy.target_delta
        if delta > 0:
            # For calls, higher delta = closer to/below current price
            strike_pct = 1.0 - (delta - 0.5) * 0.3  # Rough approximation
        else:
            # For puts
            strike_pct = 1.0 + (abs(delta) - 0.5) * 0.3

        suggested_strike = round(current_price * strike_pct / 5) * 5  # Round to $5

        # Use TastyTrade LEAPS expirations if available
        leaps_expirations = stock_data.get('leaps_expirations', [])
        if leaps_expirations and strategy.strategy_type in [StrategyType.LEAPS_CALL, StrategyType.LEAPS_PUT]:
            # Find expiration closest to target DTE
            target_date = datetime.now() + timedelta(days=strategy.target_dte)
            best_exp = None
            best_diff = float('inf')

            for exp_str in leaps_expirations:
                try:
                    exp_date = datetime.fromisoformat(exp_str)
                    diff = abs((exp_date - target_date).days)
                    if diff < best_diff:
                        best_diff = diff
                        best_exp = exp_date
                except ValueError:
                    continue

            if best_exp:
                exp_month = best_exp.strftime("%b %d, %Y")
                dte = (best_exp - datetime.now()).days
            else:
                target_exp = datetime.now() + timedelta(days=strategy.target_dte)
                exp_month = target_exp.strftime("%b %Y")
                dte = strategy.target_dte
        else:
            # Calculate expiration without TastyTrade
            target_exp = datetime.now() + timedelta(days=strategy.target_dte)
            exp_month = target_exp.strftime("%b %Y")
            dte = strategy.target_dte

        # Get TastyTrade metrics for additional info
        tastytrade = stock_data.get('tastytrade', {})
        iv_30_day = tastytrade.get('iv_30_day')
        hv_30_day = tastytrade.get('hv_30_day')

        result = {
            'type': 'call' if strategy.target_delta > 0 else 'put',
            'strike': suggested_strike,
            'expiration': exp_month,
            'target_delta': abs(strategy.target_delta),
            'estimated_premium': leaps.get('atm_call_premium'),  # Rough estimate
            'note': 'Use options chain for exact contract selection'
        }

        # Add TastyTrade IV info if available
        if iv_30_day:
            result['iv_30_day'] = round(iv_30_day * 100, 1)
        if hv_30_day:
            result['hv_30_day'] = round(hv_30_day * 100, 1)
        if iv_30_day and hv_30_day:
            iv_premium = ((iv_30_day / hv_30_day) - 1) * 100 if hv_30_day > 0 else 0
            result['iv_premium_pct'] = round(iv_premium, 1)
            result['iv_vs_hv'] = 'rich' if iv_premium > 20 else 'cheap' if iv_premium < -10 else 'fair'

        return result


# Global singleton
_strategy_engine: Optional[StrategyEngine] = None


class DeltaDTEOptimizer:
    """
    Optimizes delta and DTE selection based on market regime and stock characteristics.

    Regime-Based Delta Targets:
    - Bullish: Higher delta (0.60-0.75) to capture more upside
    - Neutral: Moderate delta (0.50-0.60) for balance
    - Bearish: Lower delta (0.40-0.50) for cheaper premium
    - Volatile: Lower delta with longer DTE for safety

    DTE Guidelines:
    - LEAPS: 270-540 days (capture long-term trends)
    - Standard: 45-90 days (active management)
    - Short-term: 21-45 days (momentum plays)
    """

    # Regime-specific delta ranges
    DELTA_RANGES = {
        'bullish': {
            'aggressive': (0.65, 0.80),
            'moderate': (0.55, 0.70),
            'conservative': (0.50, 0.60)
        },
        'bearish': {
            'aggressive': (0.45, 0.55),
            'moderate': (0.40, 0.50),
            'conservative': (0.35, 0.45)
        },
        'neutral': {
            'aggressive': (0.55, 0.65),
            'moderate': (0.50, 0.60),
            'conservative': (0.45, 0.55)
        },
        'volatile': {
            'aggressive': (0.45, 0.55),
            'moderate': (0.40, 0.50),
            'conservative': (0.35, 0.45)
        }
    }

    # Regime-specific DTE ranges
    DTE_RANGES = {
        'bullish': {
            'leaps': (270, 450),
            'standard': (60, 120),
            'short_term': (30, 60)
        },
        'bearish': {
            'leaps': (360, 540),  # Longer to weather storm
            'standard': (90, 150),
            'short_term': (45, 90)
        },
        'neutral': {
            'leaps': (300, 450),
            'standard': (45, 90),
            'short_term': (21, 45)
        },
        'volatile': {
            'leaps': (360, 540),  # Longer for safety
            'standard': (90, 180),
            'short_term': (60, 90)
        }
    }

    def optimize(
        self,
        strategy_type: StrategyType,
        market_regime: str,
        risk_tolerance: RiskLevel,
        iv_rank: float,
        days_to_earnings: Optional[int] = None,
        conviction: int = 5
    ) -> Dict[str, Any]:
        """
        Calculate optimal delta and DTE for given conditions.

        Returns:
            Dict with target_delta, delta_range, target_dte, dte_range
        """
        regime = market_regime.lower()
        risk = risk_tolerance.value if isinstance(risk_tolerance, RiskLevel) else risk_tolerance

        # Get base ranges
        delta_range = self.DELTA_RANGES.get(regime, self.DELTA_RANGES['neutral']).get(risk, (0.50, 0.60))

        # Determine DTE category based on strategy type
        if strategy_type in [StrategyType.LEAPS_CALL, StrategyType.LEAPS_PUT]:
            dte_category = 'leaps'
        elif strategy_type in [StrategyType.LONG_CALL, StrategyType.LONG_PUT]:
            dte_category = 'standard' if conviction >= 7 else 'short_term'
        else:
            dte_category = 'standard'

        dte_range = self.DTE_RANGES.get(regime, self.DTE_RANGES['neutral']).get(dte_category, (45, 90))

        # Adjust for IV rank
        delta_adj = self._iv_delta_adjustment(iv_rank)
        dte_adj = self._iv_dte_adjustment(iv_rank)

        adjusted_delta = (
            max(0.20, delta_range[0] + delta_adj),
            min(0.85, delta_range[1] + delta_adj)
        )
        adjusted_dte = (
            max(21, int(dte_range[0] * dte_adj)),
            min(720, int(dte_range[1] * dte_adj))
        )

        # Earnings adjustment
        if days_to_earnings is not None:
            if days_to_earnings <= 14:
                # Avoid expiration around earnings
                min_dte = days_to_earnings + 14
                adjusted_dte = (max(adjusted_dte[0], min_dte), max(adjusted_dte[1], min_dte + 30))

        # Calculate targets (midpoint of ranges)
        target_delta = round((adjusted_delta[0] + adjusted_delta[1]) / 2, 2)
        target_dte = int((adjusted_dte[0] + adjusted_dte[1]) / 2)

        return {
            'target_delta': target_delta,
            'delta_range': adjusted_delta,
            'target_dte': target_dte,
            'dte_range': adjusted_dte,
            'reasoning': self._generate_reasoning(
                regime, risk, iv_rank, conviction, strategy_type
            )
        }

    def _iv_delta_adjustment(self, iv_rank: float) -> float:
        """
        Adjust delta based on IV rank.
        - Low IV: Can afford higher delta (options are cheap)
        - High IV: Lower delta to reduce premium risk
        """
        if iv_rank < 30:
            return 0.05  # Shift up
        elif iv_rank > 70:
            return -0.10  # Shift down significantly
        elif iv_rank > 50:
            return -0.05  # Slight shift down
        return 0

    def _iv_dte_adjustment(self, iv_rank: float) -> float:
        """
        Adjust DTE based on IV rank.
        - Low IV: Can use shorter DTE (less theta, cheaper options)
        - High IV: Longer DTE to let IV normalize
        """
        if iv_rank < 30:
            return 0.9  # Slightly shorter
        elif iv_rank > 70:
            return 1.3  # Significantly longer
        elif iv_rank > 50:
            return 1.1  # Slightly longer
        return 1.0

    def _generate_reasoning(
        self,
        regime: str,
        risk: str,
        iv_rank: float,
        conviction: int,
        strategy_type: StrategyType
    ) -> str:
        """Generate explanation for delta/DTE selection."""
        parts = []

        parts.append(f"{regime.capitalize()} regime → {'higher' if regime == 'bullish' else 'moderate'} delta target")
        parts.append(f"{risk.capitalize()} risk tolerance adjusts delta range")

        if iv_rank < 30:
            parts.append("Low IV allows higher delta and shorter DTE")
        elif iv_rank > 70:
            parts.append("High IV suggests lower delta and longer DTE for safety")

        if strategy_type in [StrategyType.LEAPS_CALL, StrategyType.LEAPS_PUT]:
            parts.append("LEAPS strategy targets long-dated expirations")

        return "; ".join(parts)


def get_strategy_engine() -> StrategyEngine:
    """Get the global strategy engine instance."""
    global _strategy_engine
    if _strategy_engine is None:
        _strategy_engine = StrategyEngine()
    return _strategy_engine


def get_delta_dte_optimizer() -> DeltaDTEOptimizer:
    """Get a delta/DTE optimizer instance."""
    return DeltaDTEOptimizer()
