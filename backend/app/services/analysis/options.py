"""
Options analysis module - Greeks, IV, LEAPS analysis
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

from app.services.scoring.types import (
    CriterionResult,
    CoverageInfo,
    StageResult,
    GATE_CONFIGS,
    compute_coverage_adjusted_score,
    build_coverage_from_criteria,
)

# TastyTrade integration for enhanced IV data
try:
    from app.services.data_fetcher.tastytrade import get_tastytrade_service
    TASTYTRADE_AVAILABLE = True
except ImportError:
    TASTYTRADE_AVAILABLE = False


class OptionsAnalysis:
    """Analyze options data for LEAPS screening"""

    @staticmethod
    def filter_leaps_options(
        options_df: pd.DataFrame,
        current_date: datetime,
        min_dte: int = 250,
        max_dte: int = 730
    ) -> pd.DataFrame:
        """
        Filter options to get only LEAPS (>1 year expiration)

        Args:
            options_df: DataFrame with options data
            current_date: Current date
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration

        Returns:
            Filtered DataFrame with LEAPS only
        """
        if options_df.empty:
            return options_df

        try:
            df = options_df.copy()

            # Calculate days to expiration
            if 'expiration' in df.columns:
                df['expiration'] = pd.to_datetime(df['expiration'])
                df['dte'] = (df['expiration'] - current_date).dt.days

                # Filter for LEAPS
                leaps = df[(df['dte'] >= min_dte) & (df['dte'] <= max_dte)]
                return leaps

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error filtering LEAPS options: {e}")
            return pd.DataFrame()

    @staticmethod
    def find_atm_option(
        options_df: pd.DataFrame,
        current_price: float,
        option_type: str = 'call'
    ) -> Optional[Dict[str, Any]]:
        """
        Find at-the-money (ATM) or closest to ATM option

        Args:
            options_df: DataFrame with options data
            current_price: Current stock price
            option_type: 'call' or 'put'

        Returns:
            Dict with option details or None
        """
        if options_df.empty:
            return None

        try:
            # Filter by option type if column exists
            if 'type' in options_df.columns:
                options_df = options_df[options_df['type'] == option_type]

            # Find strike closest to current price
            options_df['distance'] = abs(options_df['strike'] - current_price)
            closest = options_df.loc[options_df['distance'].idxmin()]

            return {
                'strike': float(closest['strike']),
                'last_price': float(closest.get('lastPrice', 0)),
                'bid': float(closest.get('bid', 0)),
                'ask': float(closest.get('ask', 0)),
                'volume': int(closest.get('volume', 0)),
                'open_interest': int(closest.get('openInterest', 0)),
                'implied_volatility': float(closest.get('impliedVolatility', 0)),
            }

        except Exception as e:
            logger.error(f"Error finding ATM option: {e}")
            return None

    @staticmethod
    def calculate_options_score(option_data: Dict[str, Any], current_price: float) -> float:
        """
        Calculate options attractiveness score (0-100)

        Scoring criteria:
        - IV Rank (0-30 points) - lower is better for buying
        - Liquidity (0-25 points) - open interest and volume
        - Spread tightness (0-20 points) - bid-ask spread
        - Risk/Reward (0-25 points) - potential return

        Args:
            option_data: Dict with option details
            current_price: Current stock price

        Returns:
            Score from 0-100
        """
        score = 0.0

        try:
            # IV Rank (0-30 points) - assuming IV is percentage (0-2.0)
            # Lower IV is better for buying LEAPS options
            iv = option_data.get('implied_volatility', 1.0)
            if iv < 0.30:  # IV < 30% — ideal LEAPS entry
                score += 30
            elif iv < 0.50:  # IV < 50% — good value
                score += 20
            elif iv < 0.70:  # IV < 70% — acceptable for LEAPS
                score += 10

            # Liquidity (0-25 points) — 100 OI minimum for LEAPS
            open_interest = option_data.get('open_interest', 0)
            volume = option_data.get('volume', 0)

            if open_interest > 2000 and volume > 200:
                score += 25
            elif open_interest > 500 and volume > 50:
                score += 15
            elif open_interest > 100:
                score += 10

            # Spread tightness (0-20 points)
            bid = option_data.get('bid', 0)
            ask = option_data.get('ask', 0)

            if bid > 0 and ask > 0:
                mid_price = (bid + ask) / 2
                if mid_price > 0:
                    spread_pct = (ask - bid) / mid_price

                    if spread_pct < 0.05:  # < 5% spread — excellent
                        score += 20
                    elif spread_pct < 0.10:  # < 10% spread — good
                        score += 15
                    elif spread_pct < 0.15:  # < 15% spread — acceptable for LEAPS
                        score += 10

            # Premium cost as % of stock price (0-25 points)
            # Lower premium relative to stock price is better
            last_price = option_data.get('last_price', 0)
            if last_price > 0 and current_price > 0:
                premium_pct = last_price / current_price

                if premium_pct < 0.08:  # < 8% of stock price — great value
                    score += 25
                elif premium_pct < 0.12:  # < 12% of stock price — good
                    score += 15
                elif premium_pct < 0.20:  # < 20% of stock price — acceptable for ATM LEAPS
                    score += 10

            return score

        except Exception as e:
            logger.error(f"Error calculating options score: {e}")
            return 0.0

    @staticmethod
    def meets_options_criteria(
        option_data: Dict[str, Any],
        current_price: float
    ) -> Dict[str, bool]:
        """
        Check if LEAPS option meets screening criteria

        Criteria:
        - Implied Volatility: < 40% (cheap for LEAPS buying)
        - Open Interest: > 500 contracts (adequate liquidity)
        - Bid-Ask Spread: < 5% of mid-price
        - Premium Cost: < 12% of stock price

        Args:
            option_data: Dict with option details
            current_price: Current stock price

        Returns:
            Dict with criteria check results
        """
        criteria = {}

        try:
            # IV check — 70% threshold for LEAPS buying (lower = cheaper)
            iv = option_data.get('implied_volatility', 1.0)
            criteria['iv_ok'] = iv < 0.70

            # Liquidity check — 100 OI minimum for LEAPS (inherently less liquid)
            open_interest = option_data.get('open_interest', 0)
            criteria['liquidity_ok'] = open_interest > 100

            # Spread check — 15% max for LEAPS (wider spreads are normal for LEAPS)
            bid = option_data.get('bid', 0)
            ask = option_data.get('ask', 0)

            if bid > 0 and ask > 0:
                mid_price = (bid + ask) / 2
                spread_pct = (ask - bid) / mid_price if mid_price > 0 else 1
                criteria['spread_ok'] = spread_pct < 0.15
            else:
                criteria['spread_ok'] = False

            # Premium cost check — 20% max of stock price (ATM LEAPS are 15-35%)
            last_price = option_data.get('last_price', 0)
            if last_price > 0 and current_price > 0:
                premium_pct = last_price / current_price
                criteria['premium_ok'] = premium_pct < 0.20
            else:
                criteria['premium_ok'] = False

            return criteria

        except Exception as e:
            logger.error(f"Error checking options criteria: {e}")
            return {}

    @staticmethod
    def calculate_expected_return(
        current_price: float,
        option_premium: float,
        target_multiplier: float = 5.0
    ) -> float:
        """
        Calculate expected return ratio for a target multiplier

        For a 5x return on the option, how much does the stock need to move?

        Args:
            current_price: Current stock price
            option_premium: Option premium cost
            target_multiplier: Target return multiplier (5 for 5x)

        Returns:
            Expected stock price needed for target return
        """
        try:
            # For a 5x return on option, option value needs to be 5 * premium
            target_option_value = option_premium * target_multiplier

            # Assuming ITM call option, intrinsic value = stock_price - strike
            # For ATM option, strike ≈ current_price
            # So stock needs to reach: current_price + target_option_value
            expected_stock_price = current_price + target_option_value

            # Calculate how much stock needs to appreciate
            stock_appreciation_needed = (expected_stock_price - current_price) / current_price

            return stock_appreciation_needed

        except Exception as e:
            logger.error(f"Error calculating expected return: {e}")
            return 0.0

    @staticmethod
    def calculate_5x_return_analysis(
        current_price: float,
        strike: float,
        premium: float,
        dte: int,
        target_multipliers: List[float] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive 5x return analysis for LEAPS options.

        Calculates exactly what stock price is needed for various return multiples,
        along with annualized returns and probability estimates.

        Args:
            current_price: Current stock price
            strike: Option strike price
            premium: Option premium (cost per share)
            dte: Days to expiration
            target_multipliers: List of return targets (default: [2, 3, 5, 10])

        Returns:
            Dict with comprehensive return analysis
        """
        if target_multipliers is None:
            target_multipliers = [2.0, 3.0, 5.0, 10.0]

        try:
            results = {
                "current_price": current_price,
                "strike": strike,
                "premium": premium,
                "premium_per_contract": premium * 100,  # Cost for 1 contract
                "dte": dte,
                "break_even": strike + premium,
                "break_even_percent_move": ((strike + premium - current_price) / current_price) * 100,
                "targets": []
            }

            for multiplier in target_multipliers:
                # For a call option at expiration:
                # Profit = (Stock Price - Strike - Premium) * 100
                # For Nx return: (Stock Price - Strike - Premium) = Premium * (N - 1)
                # Therefore: Stock Price = Strike + Premium * N

                target_stock_price = strike + (premium * multiplier)
                stock_move_needed = ((target_stock_price - current_price) / current_price) * 100

                # Annualized return calculation
                years_to_expiry = dte / 365
                if years_to_expiry > 0:
                    # CAGR = (Final/Initial)^(1/years) - 1
                    annualized_stock_return = ((target_stock_price / current_price) ** (1 / years_to_expiry) - 1) * 100
                else:
                    annualized_stock_return = stock_move_needed

                # Intrinsic value at target
                intrinsic_at_target = max(0, target_stock_price - strike)

                # Profit per contract
                profit_per_contract = (intrinsic_at_target - premium) * 100

                multiplier_label = f"{int(multiplier)}x" if multiplier == int(multiplier) else f"{multiplier}x"
                target_info = {
                    "multiplier": multiplier_label,
                    "target_stock_price": round(target_stock_price, 2),
                    "stock_move_percent": round(stock_move_needed, 1),
                    "annualized_return_needed": round(annualized_stock_return, 1),
                    "profit_per_contract": round(profit_per_contract, 2),
                    "intrinsic_value_at_target": round(intrinsic_at_target, 2),
                    "feasibility": OptionsAnalysis._assess_feasibility(stock_move_needed, dte)
                }
                results["targets"].append(target_info)

            # Add time decay info
            results["time_decay_info"] = OptionsAnalysis._calculate_time_decay_profile(premium, dte)

            return results

        except Exception as e:
            logger.error(f"Error calculating 5x return analysis: {e}")
            return {"error": str(e)}

    @staticmethod
    def _assess_feasibility(percent_move: float, dte: int) -> str:
        """
        Assess the feasibility of a price target based on historical norms.

        Args:
            percent_move: Required percentage move
            dte: Days to expiration

        Returns:
            Feasibility rating string
        """
        # Annualize the required move
        years = dte / 365
        if years <= 0:
            return "N/A"

        annualized_move = (((1 + percent_move/100) ** (1/years)) - 1) * 100

        # Historical S&P 500 annualized return ~10%, with ~16% volatility
        # Individual stocks can vary significantly
        if annualized_move <= 15:
            return "Very Achievable"
        elif annualized_move <= 30:
            return "Achievable"
        elif annualized_move <= 50:
            return "Challenging"
        elif annualized_move <= 100:
            return "Aggressive"
        else:
            return "Very Aggressive"

    @staticmethod
    def _calculate_time_decay_profile(premium: float, dte: int) -> Dict[str, Any]:
        """
        Calculate time decay profile for LEAPS.

        LEAPS have slower theta decay initially, accelerating near expiration.

        Args:
            premium: Current option premium
            dte: Days to expiration

        Returns:
            Dict with time decay estimates
        """
        # Simplified theta decay model for LEAPS
        # Theta accelerates as sqrt(time) decreases

        decay_profile = []
        remaining_dte = dte

        # Milestones: 1 year out, 6 months, 3 months, 1 month, 2 weeks
        milestones = [
            (365, "1 year"),
            (180, "6 months"),
            (90, "3 months"),
            (30, "1 month"),
            (14, "2 weeks")
        ]

        for days, label in milestones:
            if dte >= days:
                # Rough approximation: premium decays proportionally to sqrt(time)
                # This is simplified - real theta is more complex
                time_factor = (days / dte) ** 0.5
                estimated_premium = premium * time_factor
                daily_decay = premium * (1 - time_factor) / (dte - days) if dte > days else 0

                decay_profile.append({
                    "milestone": label,
                    "dte_at_milestone": days,
                    "estimated_premium": round(estimated_premium, 2),
                    "estimated_daily_decay": round(daily_decay, 4),
                    "premium_lost_percent": round((1 - time_factor) * 100, 1)
                })

        return {
            "current_dte": dte,
            "decay_profile": decay_profile,
            "note": "LEAPS decay slowly initially, accelerating in final 90 days"
        }

    @staticmethod
    def calculate_profit_loss_table(
        strike: float,
        premium: float,
        current_price: float,
        price_range_percent: float = 50.0,
        num_points: int = 11
    ) -> Dict[str, Any]:
        """
        Calculate P/L at various stock prices for visualization.

        Args:
            strike: Option strike price
            premium: Option premium paid
            current_price: Current stock price
            price_range_percent: Range above/below current price to calculate
            num_points: Number of price points to calculate

        Returns:
            Dict with P/L table data
        """
        try:
            # Calculate price range
            min_price = current_price * (1 - price_range_percent / 100)
            max_price = current_price * (1 + price_range_percent / 100)

            price_step = (max_price - min_price) / (num_points - 1)

            pl_table = []
            break_even = strike + premium

            for i in range(num_points):
                stock_price = min_price + (i * price_step)

                # Call option P/L at expiration
                intrinsic = max(0, stock_price - strike)
                profit_per_share = intrinsic - premium
                profit_per_contract = profit_per_share * 100
                return_percent = (profit_per_share / premium) * 100 if premium > 0 else 0

                pl_table.append({
                    "stock_price": round(stock_price, 2),
                    "intrinsic_value": round(intrinsic, 2),
                    "profit_per_share": round(profit_per_share, 2),
                    "profit_per_contract": round(profit_per_contract, 2),
                    "return_percent": round(return_percent, 1),
                    "is_profitable": profit_per_share > 0,
                    "is_break_even": abs(stock_price - break_even) < price_step / 2,
                    "is_current_price": abs(stock_price - current_price) < price_step / 2
                })

            return {
                "strike": strike,
                "premium": premium,
                "current_price": current_price,
                "break_even": round(break_even, 2),
                "max_loss": round(premium * 100, 2),  # Per contract
                "pl_table": pl_table
            }

        except Exception as e:
            logger.error(f"Error calculating P/L table: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_leaps_summary(
        calls_df: pd.DataFrame,
        current_price: float,
        current_date: datetime
    ) -> Dict[str, Any]:
        """
        Get summary of available LEAPS call options

        Args:
            calls_df: DataFrame with call options
            current_price: Current stock price
            current_date: Current date

        Returns:
            Dict with LEAPS summary
        """
        try:
            # Filter for LEAPS
            leaps = OptionsAnalysis.filter_leaps_options(calls_df, current_date)

            if leaps.empty:
                return {'available': False}

            # Find ATM option
            atm_option = OptionsAnalysis.find_atm_option(leaps, current_price, 'call')

            if not atm_option:
                return {'available': False}

            # Calculate scores and criteria
            score = OptionsAnalysis.calculate_options_score(atm_option, current_price)
            criteria = OptionsAnalysis.meets_options_criteria(atm_option, current_price)

            return {
                'available': True,
                'count': len(leaps),
                'atm_option': atm_option,
                'score': score,
                'criteria_met': criteria,
                'criteria_count': sum(1 for v in criteria.values() if v),
            }

        except Exception as e:
            logger.error(f"Error getting LEAPS summary: {e}")
            return {'available': False}

    @staticmethod
    def get_enhanced_iv_data(symbol: str) -> Dict[str, Any]:
        """
        Get enhanced IV data from TastyTrade if available.

        Provides IV rank, IV percentile, and historical volatility
        for more accurate options analysis.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with IV metrics or empty dict if unavailable
        """
        if not TASTYTRADE_AVAILABLE:
            return {}

        try:
            service = get_tastytrade_service()
            if not service.is_available():
                return {}

            return service.get_enhanced_options_data(symbol)
        except Exception as e:
            logger.debug(f"TastyTrade data unavailable for {symbol}: {e}")
            return {}

    @staticmethod
    def calculate_options_score_enhanced(
        option_data: Dict[str, Any],
        current_price: float,
        symbol: str
    ) -> float:
        """
        Calculate options attractiveness score with TastyTrade IV rank.

        Enhanced scoring using TastyTrade's IV rank data for more
        accurate assessment of options pricing.

        Args:
            option_data: Dict with option details
            current_price: Current stock price
            symbol: Stock symbol for TastyTrade lookup

        Returns:
            Score from 0-100
        """
        # Start with base score calculation
        base_score = OptionsAnalysis.calculate_options_score(option_data, current_price)

        # Try to enhance with TastyTrade IV rank
        enhanced_data = OptionsAnalysis.get_enhanced_iv_data(symbol)

        if enhanced_data and enhanced_data.get('iv_rank') is not None:
            iv_rank = enhanced_data['iv_rank']

            # Adjust score based on IV rank (0-100 scale)
            # Lower IV rank = better time to buy options
            if iv_rank < 20:
                # Very low IV rank - excellent time to buy
                base_score = min(100, base_score + 15)
            elif iv_rank < 40:
                # Low IV rank - good time to buy
                base_score = min(100, base_score + 10)
            elif iv_rank > 85:
                # Very high IV rank - options very expensive
                base_score = max(0, base_score - 20)
            elif iv_rank > 70:
                # High IV rank - options are expensive
                base_score = max(0, base_score - 10)

            logger.debug(f"{symbol} IV rank: {iv_rank}, adjusted score: {base_score}")

        return base_score

    @staticmethod
    def get_leaps_summary_enhanced(
        calls_df: pd.DataFrame,
        current_price: float,
        current_date: datetime,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Get summary of available LEAPS call options with TastyTrade data.

        Enhanced version that includes IV rank and other TastyTrade metrics.

        Args:
            calls_df: DataFrame with call options
            current_price: Current stock price
            current_date: Current date
            symbol: Stock symbol

        Returns:
            Dict with LEAPS summary including TastyTrade data
        """
        # Get base summary
        summary = OptionsAnalysis.get_leaps_summary(calls_df, current_price, current_date)

        if not summary.get('available'):
            return summary

        # Enhance with TastyTrade data
        enhanced_data = OptionsAnalysis.get_enhanced_iv_data(symbol)

        if enhanced_data:
            summary['tastytrade'] = {
                'iv_rank': enhanced_data.get('iv_rank'),
                'iv_percentile': enhanced_data.get('iv_percentile'),
                'iv_30_day': enhanced_data.get('iv_30_day'),
                'hv_30_day': enhanced_data.get('hv_30_day'),
                'beta': enhanced_data.get('beta'),
                'leaps_expirations': enhanced_data.get('leaps_expirations', [])
            }

            # Recalculate score with IV rank if available
            if enhanced_data.get('iv_rank') is not None:
                summary['score'] = OptionsAnalysis.calculate_options_score_enhanced(
                    summary['atm_option'],
                    current_price,
                    symbol
                )

        return summary

    # --- v1 scoring methods ---

    @staticmethod
    def _compute_mid_price(
        bid: Optional[float],
        ask: Optional[float],
        last: Optional[float] = None,
    ) -> Optional[float]:
        """
        Mid price per v1 spec:
        mid = (bid + ask) / 2 if bid>0 and ask>0, else last if available, else None.
        """
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return (bid + ask) / 2
        if last is not None and last > 0:
            return last
        return None

    @staticmethod
    def evaluate(
        option_data: Optional[Dict[str, Any]],
        current_price: float,
        symbol: str,
        leaps_available: bool = True,
        has_options_data: bool = True,
    ) -> StageResult:
        """
        Tri-state options evaluation with coverage-adjusted score.

        Hard-fail precedence (D2): if no options data or no LEAPS,
        returns a hard fail with reason, NOT an UNKNOWN-with-neutral.

        Units (D5): IV as decimal (0.70 = 70%).
        """
        POINTS_TOTAL_MAX = 100.0

        # D2: Hard-fail if no options data at all
        if not has_options_data or option_data is None:
            return StageResult(
                stage_id="options",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=4),
                reason="no_options_data",
                points_total_max=POINTS_TOTAL_MAX,
            )

        # D2: Hard-fail if no LEAPS available
        if not leaps_available:
            return StageResult(
                stage_id="options",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=4),
                reason="no_leaps",
                points_total_max=POINTS_TOTAL_MAX,
            )

        try:
            criteria: Dict[str, CriterionResult] = {}
            points_earned = 0.0
            points_known_max = 0.0

            # Compute mid price per v1 pricing definitions
            bid = option_data.get('bid')
            ask = option_data.get('ask')
            last = option_data.get('last_price')
            mid = OptionsAnalysis._compute_mid_price(bid, ask, last)

            # Compute derived metrics
            spread_pct: Optional[float] = None
            if bid is not None and ask is not None and bid > 0 and ask > 0 and mid is not None and mid > 0:
                spread_pct = (ask - bid) / mid

            premium_pct: Optional[float] = None
            if mid is not None and mid > 0 and current_price > 0:
                premium_pct = mid / current_price

            # 1. IV (max 30) — lower is better for LEAPS buyers
            # Threshold: < 70% — growth stocks typically have 40-70% IV
            # Note: IV=0.0 from Alpaca means "not populated" (no snapshot data), treat as UNKNOWN
            iv = option_data.get('implied_volatility')
            if iv is not None and iv > 0:
                criteria['iv_ok'] = (
                    CriterionResult.PASS if iv < 0.70
                    else CriterionResult.FAIL
                )
                points_known_max += 30
                if iv < 0.30:
                    points_earned += 30
                elif iv < 0.50:
                    points_earned += 20
                elif iv < 0.70:
                    points_earned += 10
            else:
                criteria['iv_ok'] = CriterionResult.UNKNOWN

            # 2. Liquidity (max 25) — 100 OI minimum for LEAPS (inherently less liquid)
            # Note: Alpaca contract data often returns OI=0 when the field isn't populated
            # (especially for LEAPS outside market hours). Treat OI=0 with no bid/ask as UNKNOWN.
            open_interest = option_data.get('open_interest')
            volume = option_data.get('volume', 0) or 0
            has_market_data = (bid is not None and bid > 0) or (ask is not None and ask > 0)
            if open_interest is not None and (open_interest > 0 or has_market_data):
                criteria['liquidity_ok'] = (
                    CriterionResult.PASS if open_interest > 100
                    else CriterionResult.FAIL
                )
                points_known_max += 25
                if open_interest > 2000 and volume > 200:
                    points_earned += 25
                elif open_interest > 500 and volume > 50:
                    points_earned += 15
                elif open_interest > 100:
                    points_earned += 10
            else:
                criteria['liquidity_ok'] = CriterionResult.UNKNOWN

            # 3. Spread tightness (max 20) — 15% max for LEAPS (inherently wider spreads)
            if spread_pct is not None:
                criteria['spread_ok'] = (
                    CriterionResult.PASS if spread_pct < 0.15
                    else CriterionResult.FAIL
                )
                points_known_max += 20
                if spread_pct < 0.05:
                    points_earned += 20
                elif spread_pct < 0.10:
                    points_earned += 15
                elif spread_pct < 0.15:
                    points_earned += 10
            else:
                criteria['spread_ok'] = CriterionResult.UNKNOWN

            # 4. Premium efficiency (max 25) — 20% max of stock price (ATM LEAPS are 15-35%)
            if premium_pct is not None:
                criteria['premium_ok'] = (
                    CriterionResult.PASS if premium_pct < 0.20
                    else CriterionResult.FAIL
                )
                points_known_max += 25
                if premium_pct < 0.08:
                    points_earned += 25
                elif premium_pct < 0.12:
                    points_earned += 15
                elif premium_pct < 0.20:
                    points_earned += 10
            else:
                criteria['premium_ok'] = CriterionResult.UNKNOWN

            # IV Rank adjustment (TastyTrade data)
            enhanced_data = OptionsAnalysis.get_enhanced_iv_data(symbol)
            iv_rank_adjustment = 0
            if enhanced_data and enhanced_data.get('iv_rank') is not None:
                iv_rank = enhanced_data['iv_rank']
                if iv_rank < 20:
                    iv_rank_adjustment = 15
                elif iv_rank < 40:
                    iv_rank_adjustment = 10
                elif iv_rank > 85:
                    iv_rank_adjustment = -20
                elif iv_rank > 70:
                    iv_rank_adjustment = -10

            # Apply IV rank adjustment to earned points (affects coverage-adjusted score)
            points_earned = max(0.0, points_earned + iv_rank_adjustment)

            coverage = build_coverage_from_criteria(criteria)
            score_pct, score_points, score_pct_raw = compute_coverage_adjusted_score(
                points_earned, points_known_max, POINTS_TOTAL_MAX
            )

            # Clamp score_pct to 0-100 after IV rank adjustment
            if score_pct is not None:
                score_pct = max(0.0, min(100.0, score_pct))
            if score_points is not None:
                score_points = max(0.0, min(POINTS_TOTAL_MAX, score_points))

            return StageResult(
                stage_id="options",
                criteria=criteria,
                coverage=coverage,
                score_pct=score_pct,
                score_points=score_points,
                score_pct_raw=score_pct_raw,
                points_earned=points_earned,
                points_known_max=points_known_max,
                points_total_max=POINTS_TOTAL_MAX,
            )

        except Exception as e:
            logger.error(f"Error in options evaluate for {symbol}: {e}")
            return StageResult(
                stage_id="options",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=4),
                reason=f"error: {e}",
                points_total_max=POINTS_TOTAL_MAX,
            )
