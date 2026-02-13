"""
Fundamental analysis module
"""
from typing import Dict, Any, Optional
from loguru import logger

from app.services.scoring.types import (
    CriterionResult,
    CoverageInfo,
    GateConfig,
    StageResult,
    GATE_CONFIGS,
    compute_coverage_adjusted_score,
    build_coverage_from_criteria,
)


class FundamentalAnalysis:
    """Analyze fundamental metrics"""

    # Sectors eligible for LEAPS targeting
    GROWTH_SECTORS = [
        'Technology',
        'Healthcare',
        'Consumer Cyclical',
        'Communication Services',
        'Industrials',
        'Energy',  # Including renewables
        'Financial Services',  # V, MA, JPM, GS — valid LEAPS targets
        'Consumer Defensive',  # WMT, COST, PG, KO — blue chip staples
    ]

    @staticmethod
    def calculate_fundamental_score(fundamentals: Dict[str, Any]) -> float:
        """
        Calculate fundamental score (0-100)

        Scoring criteria:
        - Revenue growth (0-30 points)
        - Earnings growth (0-30 points)
        - Margin expansion (0-20 points)
        - Balance sheet health (0-10 points)
        - Sector momentum (0-10 points)

        Args:
            fundamentals: Dict with fundamental metrics

        Returns:
            Score from 0-100
        """
        score = 0.0

        try:
            # Revenue growth (0-30 points)
            revenue_growth = fundamentals.get('revenue_growth')
            if revenue_growth:
                if revenue_growth > 0.50:
                    score += 30
                elif revenue_growth > 0.30:
                    score += 20
                elif revenue_growth > 0.20:
                    score += 10

            # Earnings growth (0-30 points)
            earnings_growth = fundamentals.get('earnings_growth')
            if earnings_growth:
                if earnings_growth > 0.50:
                    score += 30
                elif earnings_growth > 0.30:
                    score += 20
                elif earnings_growth > 0.15:
                    score += 10

            # Profit margins (0-20 points)
            profit_margins = fundamentals.get('profit_margins')
            if profit_margins:
                if profit_margins > 0.20:
                    score += 20
                elif profit_margins > 0.10:
                    score += 10

            # Balance sheet health (0-10 points)
            debt_to_equity = fundamentals.get('debt_to_equity')
            current_ratio = fundamentals.get('current_ratio')

            if debt_to_equity is not None and current_ratio is not None:
                if debt_to_equity < 50 and current_ratio > 2:  # debt_to_equity in percentage
                    score += 10
                elif debt_to_equity < 100 and current_ratio > 1.5:
                    score += 5

            # Return on Equity (0-10 points)
            roe = fundamentals.get('roe')
            if roe:
                if roe > 0.20:
                    score += 10
                elif roe > 0.15:
                    score += 5

            return score

        except Exception as e:
            logger.error(f"Error calculating fundamental score: {e}")
            return 0.0

    @staticmethod
    def meets_fundamental_criteria(
        fundamentals: Dict[str, Any],
        stock_info: Dict[str, Any],
        custom_criteria: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        """
        Check if stock meets fundamental screening criteria

        Default criteria for 5x potential:
        - Market Cap: $500M - $50B
        - Stock Price: $5 - $500
        - Revenue Growth: >20% YoY
        - Earnings Growth: >15% YoY or turning profitable
        - Debt-to-Equity: <150%
        - Current Ratio: >1.2
        - In growth sector

        Args:
            fundamentals: Dict with fundamental metrics
            stock_info: Dict with stock info (sector, market cap)
            custom_criteria: Optional dict with custom thresholds

        Returns:
            Dict with criteria check results
        """
        # Use custom criteria if provided, otherwise use defaults
        criteria_thresholds = custom_criteria or {}

        market_cap_min = criteria_thresholds.get('market_cap_min', 500_000_000)
        market_cap_max = criteria_thresholds.get('market_cap_max')  # None = no upper limit (presets control this)
        price_min = criteria_thresholds.get('price_min', 5.0)
        price_max = criteria_thresholds.get('price_max', 500.0)
        revenue_growth_min = criteria_thresholds.get('revenue_growth_min', 10) / 100  # Convert from percentage
        earnings_growth_min = criteria_thresholds.get('earnings_growth_min', 5) / 100
        debt_to_equity_max = criteria_thresholds.get('debt_to_equity_max', 150)
        current_ratio_min = criteria_thresholds.get('current_ratio_min', 1.2)

        criteria = {}

        try:
            # Market cap check — min always applies, max only if preset specifies one
            market_cap = stock_info.get('market_cap') or fundamentals.get('market_cap')
            if market_cap:
                if market_cap_max is not None:
                    criteria['market_cap_ok'] = market_cap_min <= market_cap <= market_cap_max
                else:
                    criteria['market_cap_ok'] = market_cap >= market_cap_min
            else:
                criteria['market_cap_ok'] = False

            # Stock price check
            current_price = stock_info.get('current_price')
            if current_price:
                criteria['price_ok'] = price_min <= current_price <= price_max
                if not criteria['price_ok']:
                    logger.debug(f"Price filter: ${current_price:.2f} not in range ${price_min}-${price_max}")
            else:
                criteria['price_ok'] = False
                logger.debug(f"Price filter: No current_price in stock_info, failing filter")

            # Revenue growth check
            revenue_growth = fundamentals.get('revenue_growth')
            if revenue_growth is not None:
                criteria['revenue_growth_ok'] = revenue_growth > revenue_growth_min
            else:
                criteria['revenue_growth_ok'] = False

            # Earnings growth check
            earnings_growth = fundamentals.get('earnings_growth')
            if earnings_growth is not None:
                criteria['earnings_growth_ok'] = earnings_growth > earnings_growth_min
            else:
                # Check if turning profitable (has positive profit margins)
                profit_margins = fundamentals.get('profit_margins')
                if profit_margins and profit_margins > 0:
                    criteria['earnings_growth_ok'] = True
                else:
                    criteria['earnings_growth_ok'] = False

            # Debt-to-equity check
            debt_to_equity = fundamentals.get('debt_to_equity')
            if debt_to_equity is not None:
                criteria['debt_ok'] = debt_to_equity < debt_to_equity_max
            else:
                criteria['debt_ok'] = True  # Give benefit of doubt if no debt data

            # Current ratio check
            current_ratio = fundamentals.get('current_ratio')
            if current_ratio is not None:
                criteria['liquidity_ok'] = current_ratio > current_ratio_min
            else:
                criteria['liquidity_ok'] = True  # Give benefit of doubt

            # Sector check
            sector = stock_info.get('sector')
            if sector:
                criteria['sector_ok'] = sector in FundamentalAnalysis.GROWTH_SECTORS
            else:
                criteria['sector_ok'] = False

            return criteria

        except Exception as e:
            logger.error(f"Error checking fundamental criteria: {e}")
            return {}

    @staticmethod
    def get_criteria_summary(criteria: Dict[str, bool]) -> int:
        """
        Get summary of how many criteria are met

        Args:
            criteria: Dict with criteria check results

        Returns:
            Number of criteria met
        """
        return sum(1 for v in criteria.values() if v)

    @staticmethod
    def extract_key_metrics(fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and format key fundamental metrics

        Args:
            fundamentals: Raw fundamentals dict

        Returns:
            Dict with formatted key metrics
        """
        return {
            'market_cap': fundamentals.get('market_cap'),
            'revenue': fundamentals.get('revenue'),
            'revenue_growth': fundamentals.get('revenue_growth'),
            'earnings_growth': fundamentals.get('earnings_growth'),
            'profit_margins': fundamentals.get('profit_margins'),
            'operating_margins': fundamentals.get('operating_margins'),
            'pe_ratio': fundamentals.get('trailing_pe'),
            'peg_ratio': fundamentals.get('peg_ratio'),
            'debt_to_equity': fundamentals.get('debt_to_equity'),
            'current_ratio': fundamentals.get('current_ratio'),
            'roe': fundamentals.get('roe'),
            'roa': fundamentals.get('roa'),
            'eps': fundamentals.get('earnings_per_share'),
        }

    @staticmethod
    def evaluate(
        fundamentals: Dict[str, Any],
        stock_info: Dict[str, Any],
        custom_criteria: Optional[Dict[str, Any]] = None,
    ) -> StageResult:
        """
        Tri-state fundamental evaluation returning StageResult.

        Mandatory pre-gates (not counted toward 3-of-5):
          - market_cap_ok (must be KNOWN + PASS)
          - price_ok (must be KNOWN + PASS)

        5 tri-state criteria for the gate check:
          revenue_growth_ok, earnings_growth_ok, debt_ok, liquidity_ok, sector_ok

        Units (D5): growth rates as decimals, D/E as percentage points.
        """
        POINTS_TOTAL_MAX = 100.0
        criteria_thresholds = custom_criteria or {}

        market_cap_min = criteria_thresholds.get('market_cap_min', 500_000_000)
        market_cap_max = criteria_thresholds.get('market_cap_max')  # None = no upper limit (presets control this)
        price_min = criteria_thresholds.get('price_min', 5.0)
        price_max = criteria_thresholds.get('price_max', 500.0)
        revenue_growth_min = criteria_thresholds.get('revenue_growth_min', 20) / 100
        earnings_growth_min = criteria_thresholds.get('earnings_growth_min', 15) / 100
        debt_to_equity_max = criteria_thresholds.get('debt_to_equity_max', 150)
        current_ratio_min = criteria_thresholds.get('current_ratio_min', 1.2)

        try:
            # --- Mandatory pre-gates ---
            pre_gates: Dict[str, CriterionResult] = {}

            market_cap = stock_info.get('market_cap') or fundamentals.get('market_cap')
            if market_cap is not None:
                if market_cap_max is not None:
                    cap_ok = market_cap_min <= market_cap <= market_cap_max
                else:
                    cap_ok = market_cap >= market_cap_min
                pre_gates['market_cap_ok'] = (
                    CriterionResult.PASS if cap_ok
                    else CriterionResult.FAIL
                )
            else:
                pre_gates['market_cap_ok'] = CriterionResult.UNKNOWN

            current_price = stock_info.get('current_price')
            if current_price is not None:
                pre_gates['price_ok'] = (
                    CriterionResult.PASS
                    if price_min <= current_price <= price_max
                    else CriterionResult.FAIL
                )
            else:
                pre_gates['price_ok'] = CriterionResult.UNKNOWN

            # If either mandatory pre-gate is not PASS, hard-fail immediately
            for key in ('market_cap_ok', 'price_ok'):
                if pre_gates[key] != CriterionResult.PASS:
                    reason = f"{key}_failed" if pre_gates[key] == CriterionResult.FAIL else f"{key}_unknown"
                    return StageResult(
                        stage_id="fundamental",
                        criteria=pre_gates,
                        coverage=CoverageInfo(known_count=0, pass_count=0, total_count=5),
                        reason=reason,
                        points_total_max=POINTS_TOTAL_MAX,
                    )

            # --- 5 tri-state criteria ---
            criteria: Dict[str, CriterionResult] = {}

            # 1. Revenue growth
            revenue_growth = fundamentals.get('revenue_growth')
            if revenue_growth is not None:
                criteria['revenue_growth_ok'] = (
                    CriterionResult.PASS if revenue_growth > revenue_growth_min
                    else CriterionResult.FAIL
                )
            else:
                criteria['revenue_growth_ok'] = CriterionResult.UNKNOWN

            # 2. Earnings growth
            earnings_growth = fundamentals.get('earnings_growth')
            if earnings_growth is not None:
                criteria['earnings_growth_ok'] = (
                    CriterionResult.PASS if earnings_growth > earnings_growth_min
                    else CriterionResult.FAIL
                )
            else:
                profit_margins = fundamentals.get('profit_margins')
                if profit_margins is not None and profit_margins > 0:
                    criteria['earnings_growth_ok'] = CriterionResult.PASS
                elif profit_margins is not None:
                    criteria['earnings_growth_ok'] = CriterionResult.FAIL
                else:
                    criteria['earnings_growth_ok'] = CriterionResult.UNKNOWN

            # 3. Debt-to-equity
            debt_to_equity = fundamentals.get('debt_to_equity')
            if debt_to_equity is not None:
                criteria['debt_ok'] = (
                    CriterionResult.PASS if debt_to_equity < debt_to_equity_max
                    else CriterionResult.FAIL
                )
            else:
                criteria['debt_ok'] = CriterionResult.UNKNOWN

            # 4. Current ratio (liquidity)
            current_ratio = fundamentals.get('current_ratio')
            if current_ratio is not None:
                criteria['liquidity_ok'] = (
                    CriterionResult.PASS if current_ratio > current_ratio_min
                    else CriterionResult.FAIL
                )
            else:
                criteria['liquidity_ok'] = CriterionResult.UNKNOWN

            # 5. Sector (skip_sector_filter bypasses growth-sector gate)
            skip_sector = criteria_thresholds.get('skip_sector_filter', False)
            sector = stock_info.get('sector')
            if skip_sector:
                criteria['sector_ok'] = CriterionResult.PASS
            elif sector is not None:
                criteria['sector_ok'] = (
                    CriterionResult.PASS if sector in FundamentalAnalysis.GROWTH_SECTORS
                    else CriterionResult.FAIL
                )
            else:
                criteria['sector_ok'] = CriterionResult.UNKNOWN

            # --- Coverage-adjusted scoring ---
            # 5 buckets: revenue(30), earnings(30), margins(20), balance_sheet(10), ROE(10)
            points_earned = 0.0
            points_known_max = 0.0

            # Revenue growth bucket (max 30)
            if revenue_growth is not None:
                points_known_max += 30
                if revenue_growth > 0.50:
                    points_earned += 30
                elif revenue_growth > 0.30:
                    points_earned += 20
                elif revenue_growth > 0.20:
                    points_earned += 10

            # Earnings growth bucket (max 30)
            if earnings_growth is not None:
                points_known_max += 30
                if earnings_growth > 0.50:
                    points_earned += 30
                elif earnings_growth > 0.30:
                    points_earned += 20
                elif earnings_growth > 0.15:
                    points_earned += 10

            # Profit margins bucket (max 20)
            profit_margins = fundamentals.get('profit_margins')
            if profit_margins is not None:
                points_known_max += 20
                if profit_margins > 0.20:
                    points_earned += 20
                elif profit_margins > 0.10:
                    points_earned += 10

            # Balance sheet bucket (max 10) — requires both D/E and CR
            if debt_to_equity is not None and current_ratio is not None:
                points_known_max += 10
                if debt_to_equity < 50 and current_ratio > 2.0:
                    points_earned += 10
                elif debt_to_equity < 100 and current_ratio > 1.5:
                    points_earned += 5

            # ROE bucket (max 10)
            roe = fundamentals.get('roe')
            if roe is not None:
                points_known_max += 10
                if roe > 0.20:
                    points_earned += 10
                elif roe > 0.15:
                    points_earned += 5

            coverage = build_coverage_from_criteria(criteria)
            score_pct, score_points, score_pct_raw = compute_coverage_adjusted_score(
                points_earned, points_known_max, POINTS_TOTAL_MAX
            )

            # Merge pre-gates into criteria for the full output
            all_criteria = {**pre_gates, **criteria}

            return StageResult(
                stage_id="fundamental",
                criteria=all_criteria,
                coverage=coverage,
                score_pct=score_pct,
                score_points=score_points,
                score_pct_raw=score_pct_raw,
                points_earned=points_earned,
                points_known_max=points_known_max,
                points_total_max=POINTS_TOTAL_MAX,
            )

        except Exception as e:
            logger.error(f"Error in fundamental evaluate: {e}")
            return StageResult(
                stage_id="fundamental",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=5),
                reason=f"error: {e}",
                points_total_max=POINTS_TOTAL_MAX,
            )
