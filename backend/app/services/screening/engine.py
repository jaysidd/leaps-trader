"""
Main screening engine for identifying 5x LEAPS opportunities

Enhanced with Phase 2:
- Sentiment scoring (news, analyst, insider)
- Catalyst timing integration
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger

from app.services.data_fetcher.fmp_service import fmp_service
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.analysis.technical import TechnicalAnalysis
from app.services.analysis.fundamental import FundamentalAnalysis
from app.services.analysis.options import OptionsAnalysis
from app.services.analysis.sentiment import SentimentAnalyzer, get_sentiment_analyzer
from app.services.analysis.catalyst import CatalystService, get_catalyst_service
from app.services.scoring.types import (
    CriterionResult,
    CoverageInfo,
    StageResult,
    GATE_CONFIGS,
    compute_coverage_adjusted_score,
    build_coverage_from_criteria,
)


class ScreeningEngine:
    """
    Multi-stage screening engine for LEAPS candidates

    Stages:
    1. Fundamental Filter (5000 stocks → ~500)
    2. Technical Filter (~500 → ~100)
    3. Options Filter (~100 → ~30)
    4. Scoring & Ranking (Top 10-15)
    """

    def __init__(self):
        self.tech_analysis = TechnicalAnalysis()
        self.fund_analysis = FundamentalAnalysis()
        self.opt_analysis = OptionsAnalysis()
        self.sentiment_analyzer = get_sentiment_analyzer()
        self.catalyst_service = get_catalyst_service()

    @staticmethod
    def _check_valuation_filters(
        fundamentals: Dict[str, Any],
        custom_criteria: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Post-gate valuation checks.  Runs AFTER fundamental gate passes.

        Returns None if all checks pass, or a failure-reason string.

        Missing-data handling:
        - PEG None or 0 → skip (unreliable from Yahoo, 60-70% None)
        - P/E None → skip (negative-earnings stocks legitimately have no P/E)
        - Dividend yield None with dividend_yield_min set → treat as 0 → FAIL
        - All other None fields with a filter set → skip
        """
        if not custom_criteria:
            return None

        # P/E range
        pe_min = custom_criteria.get('pe_min')
        pe_max = custom_criteria.get('pe_max')
        trailing_pe = fundamentals.get('trailing_pe')
        if trailing_pe is not None:
            if pe_min is not None and trailing_pe < pe_min:
                return f"trailing_pe={trailing_pe:.1f} < pe_min={pe_min}"
            if pe_max is not None and trailing_pe > pe_max:
                return f"trailing_pe={trailing_pe:.1f} > pe_max={pe_max}"

        # Forward P/E
        forward_pe_max = custom_criteria.get('forward_pe_max')
        forward_pe = fundamentals.get('forward_pe')
        if forward_pe_max is not None and forward_pe is not None and forward_pe > forward_pe_max:
            return f"forward_pe={forward_pe:.1f} > forward_pe_max={forward_pe_max}"

        # PEG ratio — skip when None or 0 (unreliable)
        peg_max = custom_criteria.get('peg_max')
        peg_ratio = fundamentals.get('peg_ratio')
        if peg_max is not None and peg_ratio is not None and peg_ratio > 0:
            if peg_ratio > peg_max:
                return f"peg_ratio={peg_ratio:.2f} > peg_max={peg_max}"

        # Price-to-Book
        pb_max = custom_criteria.get('pb_max')
        price_to_book = fundamentals.get('price_to_book')
        if pb_max is not None and price_to_book is not None:
            if price_to_book > pb_max:
                return f"price_to_book={price_to_book:.2f} > pb_max={pb_max}"

        # Price-to-Sales
        ps_max = custom_criteria.get('ps_max')
        price_to_sales = fundamentals.get('price_to_sales')
        if ps_max is not None and price_to_sales is not None:
            if price_to_sales > ps_max:
                return f"price_to_sales={price_to_sales:.2f} > ps_max={ps_max}"

        # Dividend yield — None treated as 0 when min is set
        div_min = custom_criteria.get('dividend_yield_min')
        div_max = custom_criteria.get('dividend_yield_max')
        div_yield = fundamentals.get('dividend_yield')
        effective_yield = div_yield if div_yield is not None else 0.0
        if div_min is not None and effective_yield < div_min:
            return f"dividend_yield={effective_yield:.4f} < dividend_yield_min={div_min}"
        if div_max is not None and div_yield is not None and div_yield > div_max:
            return f"dividend_yield={div_yield:.4f} > dividend_yield_max={div_max}"

        # ROE
        roe_min = custom_criteria.get('roe_min')
        roe = fundamentals.get('roe')
        if roe_min is not None and roe is not None:
            if roe < roe_min:
                return f"roe={roe:.4f} < roe_min={roe_min}"

        # Profit margin
        pm_min = custom_criteria.get('profit_margin_min')
        profit_margins = fundamentals.get('profit_margins')
        if pm_min is not None and profit_margins is not None:
            if profit_margins < pm_min:
                return f"profit_margins={profit_margins:.4f} < profit_margin_min={pm_min}"

        # Beta range
        beta_min = custom_criteria.get('beta_min')
        beta_max = custom_criteria.get('beta_max')
        beta = fundamentals.get('beta')
        if beta is not None:
            if beta_min is not None and beta < beta_min:
                return f"beta={beta:.2f} < beta_min={beta_min}"
            if beta_max is not None and beta > beta_max:
                return f"beta={beta:.2f} > beta_max={beta_max}"

        return None  # All checks passed

    def screen_single_stock(
        self,
        symbol: str,
        custom_criteria: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Screen a single stock through all filters (v1).

        Uses tri-state criteria, coverage-adjusted sub-scores,
        momentum drawdown penalties, and composite rescaling.
        """
        logger.info(f"Screening {symbol}...")

        result: Dict[str, Any] = {
            'symbol': symbol,
            'screened_at': datetime.now().isoformat(),
            'passed_stages': [],
            'failed_at': None,
            'score': 0,
            'criteria': {},
            'coverage': {},
            'component_availability': {},
        }

        # Track StageResults for composite calculation
        fund_stage: Optional[StageResult] = None
        tech_stage: Optional[StageResult] = None
        opt_stage: Optional[StageResult] = None
        mom_stage: Optional[StageResult] = None

        try:
            # Get stock info
            stock_info = fmp_service.get_stock_info(symbol)
            if not stock_info:
                logger.warning(f"{symbol}: Failed to get stock info")
                result['failed_at'] = 'data_fetch'
                return result

            result['name'] = stock_info.get('name')
            result['sector'] = stock_info.get('sector')
            result['market_cap'] = stock_info.get('market_cap')
            result['exchange'] = stock_info.get('exchange')

            # STAGE 1: Fundamental Filter (v1)
            fundamentals = fmp_service.get_fundamentals(symbol)
            if not fundamentals:
                logger.warning(f"{symbol}: No fundamental data")
                result['failed_at'] = 'fundamentals'
                return result

            # Propagate valuation metrics for _matches_preset() and frontend
            result['trailing_pe'] = fundamentals.get('trailing_pe')
            result['peg_ratio'] = fundamentals.get('peg_ratio')
            result['price_to_book'] = fundamentals.get('price_to_book')
            result['dividend_yield'] = fundamentals.get('dividend_yield')
            result['beta'] = fundamentals.get('beta')
            result['roe'] = fundamentals.get('roe')
            result['profit_margins'] = fundamentals.get('profit_margins')

            fund_stage = self.fund_analysis.evaluate(
                fundamentals, stock_info, custom_criteria
            )
            result['fundamental_score'] = fund_stage.score_pct
            result['fundamental_criteria'] = {
                k: v.value for k, v in fund_stage.criteria.items()
            }
            result['criteria']['fundamental'] = result['fundamental_criteria']
            result['coverage']['fundamental'] = fund_stage.coverage.to_dict()

            # Check mandatory pre-gates
            pre_gate_fail = fund_stage.reason
            if pre_gate_fail:
                logger.info(f"{symbol}: Failed fundamental pre-gate: {pre_gate_fail}")
                result['failed_at'] = 'fundamentals_gate'
                return result

            # Check gate: ≥4 PASS of 5, ≥5 KNOWN of 5
            if not fund_stage.passes_gate(GATE_CONFIGS["fundamental"]):
                logger.info(f"{symbol}: Failed fundamental gate")
                result['failed_at'] = 'fundamentals_gate'
                return result

            result['passed_stages'].append('fundamental')

            # Post-gate valuation filters (new P/E, PEG, dividend, etc.)
            valuation_fail = self._check_valuation_filters(fundamentals, custom_criteria)
            if valuation_fail:
                logger.info(f"{symbol}: Failed post-gate valuation: {valuation_fail}")
                result['failed_at'] = 'valuation_filter'
                return result

            # STAGE 2: Technical Filter (v1)
            price_data = alpaca_service.get_historical_prices(symbol, period="2y")
            if price_data is None or price_data.empty:
                logger.warning(f"{symbol}: No price data")
                result['failed_at'] = 'price_data'
                return result

            # Calculate technical indicators
            price_data = self.tech_analysis.calculate_all_indicators(price_data)
            tech_indicators = self.tech_analysis.get_latest_indicators(price_data)

            result['technical_indicators'] = tech_indicators
            result['current_price'] = tech_indicators.get('current_price')
            result['price_change_percent'] = tech_indicators.get('price_change_percent')

            # Pre-compute expensive values
            avg_volume = self.tech_analysis.calculate_avg_volume(price_data, 50)
            is_breakout = self.tech_analysis.detect_breakout(price_data, 60)

            tech_stage = self._evaluate_technical(
                tech_indicators, price_data,
                avg_volume=avg_volume or 0, is_breakout=is_breakout
            )

            # D3: technical_score stays 0-100 (pct), add technical_score_points (0-90)
            result['technical_score'] = tech_stage.score_pct
            result['technical_score_points'] = tech_stage.score_points
            result['technical_criteria'] = {
                k: v.value for k, v in tech_stage.criteria.items()
            }
            result['criteria']['technical'] = result['technical_criteria']
            result['coverage']['technical'] = tech_stage.coverage.to_dict()

            # Check data sufficiency
            if tech_stage.reason == "insufficient_price_history":
                logger.info(f"{symbol}: Insufficient price history for technical gate")
                result['failed_at'] = 'technical_gate'
                return result

            # Check gate: ≥4 PASS of 7, ≥6 KNOWN of 7
            if not tech_stage.passes_gate(GATE_CONFIGS["technical"]):
                logger.info(f"{symbol}: Failed technical gate")
                result['failed_at'] = 'technical_gate'
                return result

            result['passed_stages'].append('technical')

            # STAGE 3: Options Filter (v1)
            current_price = tech_indicators.get('current_price', 0)
            if current_price <= 0:
                logger.warning(f"{symbol}: Invalid current price")
                result['failed_at'] = 'price_validation'
                return result

            # Get options data and LEAPS summary (for backward compat fields)
            options_data = alpaca_service.get_options_chain(symbol)
            has_options_data = bool(options_data and 'calls' in options_data)

            leaps_summary = {}
            leaps_available = False
            atm_option = None

            if has_options_data:
                leaps_summary = self.opt_analysis.get_leaps_summary_enhanced(
                    options_data['calls'],
                    current_price,
                    datetime.now(),
                    symbol
                )
                leaps_available = leaps_summary.get('available', False)
                atm_option = leaps_summary.get('atm_option')

            result['leaps_available'] = leaps_available
            result['leaps_summary'] = leaps_summary

            # Promote IV rank to top-level for easy frontend access
            tt = leaps_summary.get('tastytrade', {})
            result['iv_rank'] = tt.get('iv_rank')
            result['iv_percentile'] = tt.get('iv_percentile')

            # v1 options evaluation
            opt_stage = self.opt_analysis.evaluate(
                option_data=atm_option,
                current_price=current_price,
                symbol=symbol,
                leaps_available=leaps_available,
                has_options_data=has_options_data,
            )

            result['options_score'] = opt_stage.score_pct
            result['options_criteria'] = {
                k: v.value for k, v in opt_stage.criteria.items()
            }
            result['criteria']['options'] = result['options_criteria']
            result['coverage']['options'] = opt_stage.coverage.to_dict()

            # D2: Hard fail for no options data / no LEAPS
            if opt_stage.reason in ("no_options_data", "no_leaps"):
                logger.info(f"{symbol}: Failed options gate: {opt_stage.reason}")
                result['failed_at'] = 'options_gate'
                return result

            # Check gate: ≥3 PASS of 4, ≥4 KNOWN of 4
            if not opt_stage.passes_gate(GATE_CONFIGS["options"]):
                logger.info(f"{symbol}: Failed options gate")
                result['failed_at'] = 'options_gate'
                return result

            result['passed_stages'].append('options')

            # STAGE 4: Momentum (v1, no gate)
            returns = self.tech_analysis.calculate_returns(price_data)
            mom_stage = self._evaluate_momentum(returns)

            result['returns'] = returns
            result['momentum_score'] = mom_stage.score_pct
            result['criteria']['momentum'] = {
                k: v.value for k, v in mom_stage.criteria.items()
            }
            result['coverage']['momentum'] = mom_stage.coverage.to_dict()

            # STAGE 5: Composite Score (v1)
            composite = self._calculate_composite_score_v1(
                fund_stage, tech_stage, opt_stage, mom_stage
            )

            result['score'] = composite['score']
            result['component_availability'] = composite['component_availability']

            # Minimum composite score cutoff — stocks that pass all 3 quality gates
            # (fundamental, technical, options) already demonstrate merit.
            # The composite score is a coverage-adjusted weighted average that
            # naturally produces lower values (25-60 range for passing stocks).
            # A floor of 20 catches only the weakest gate-passers while letting
            # the downstream AI validator and signal engine do the real filtering.
            MIN_COMPOSITE_SCORE = 20
            if composite['score'] < MIN_COMPOSITE_SCORE:
                logger.info(
                    f"{symbol}: Composite score {composite['score']:.1f} < {MIN_COMPOSITE_SCORE} minimum — filtered out"
                )
                result['failed_at'] = 'composite_score_minimum'
                return result

            result['passed_stages'].append('scoring')
            result['passed_all'] = True

            logger.success(f"{symbol}: Passed all filters with score {composite['score']:.2f}")

            return result

        except Exception as e:
            logger.error(f"Error screening {symbol}: {e}")
            result['failed_at'] = 'error'
            result['error'] = str(e)
            return result

    def screen_multiple_stocks(
        self,
        symbols: List[str],
        custom_criteria: Optional[Dict[str, Any]] = None,
        max_workers: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Screen multiple stocks using bounded concurrency.

        Args:
            symbols: List of stock ticker symbols
            custom_criteria: Optional dict with custom screening thresholds
            max_workers: Max concurrent screening threads (respects rate limits)

        Returns:
            List of screening results, sorted by score
        """
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.screen_single_stock, symbol, custom_criteria): symbol
                for symbol in symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error screening {symbol} in thread pool: {e}")

        # Sort by score (descending)
        results.sort(key=lambda x: x.get('score', 0), reverse=True)

        return results

    def get_top_candidates(
        self,
        symbols: List[str],
        top_n: int = 15,
        custom_criteria: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get top N LEAPS candidates from screening

        Args:
            symbols: List of stock ticker symbols to screen
            top_n: Number of top candidates to return
            custom_criteria: Optional dict with custom screening thresholds

        Returns:
            List of top candidates
        """
        all_results = self.screen_multiple_stocks(symbols, custom_criteria)

        # Filter only stocks that passed all filters
        passed = [r for r in all_results if r.get('passed_all', False)]

        # Return top N
        return passed[:top_n]

    def _check_technical_criteria(
        self,
        indicators: Dict[str, Any],
        price_data,
        custom_criteria: Optional[Dict[str, Any]] = None,
        avg_volume: float = 0,
        is_breakout: bool = False
    ) -> Dict[str, bool]:
        """Check technical screening criteria"""
        criteria = {}

        # Use custom criteria if provided, otherwise use defaults
        criteria_thresholds = custom_criteria or {}
        rsi_min = criteria_thresholds.get('rsi_min', 40)
        rsi_max = criteria_thresholds.get('rsi_max', 70)

        try:
            price = indicators.get('current_price', 0)
            sma_50 = indicators.get('sma_50', 0)
            sma_200 = indicators.get('sma_200', 0)
            rsi = indicators.get('rsi_14', 50)
            adx = indicators.get('adx_14', 0)

            # Uptrend check
            criteria['uptrend'] = price > sma_50 > sma_200 if (price and sma_50 and sma_200) else False

            # RSI check with custom range
            criteria['rsi_ok'] = rsi_min <= rsi <= rsi_max if rsi else False

            # MACD crossover check
            macd_crossover = self.tech_analysis.check_macd_crossover(price_data, 20)
            criteria['macd_bullish'] = macd_crossover is not None and macd_crossover <= 20

            # Volume check (uses pre-computed avg_volume)
            volume = indicators.get('volume', 0)
            criteria['volume_above_avg'] = volume > avg_volume * 1.2 if (volume and avg_volume) else False

            # Breakout check (uses pre-computed value)
            criteria['breakout'] = is_breakout

            # ATR check (volatility)
            atr = indicators.get('atr_14', 0)
            criteria['volatility_ok'] = (atr / price) > 0.03 if (atr and price) else False

            # Trend strength check
            criteria['trend_strong'] = adx > 25 if adx else False

            return criteria

        except Exception as e:
            logger.error(f"Error checking technical criteria: {e}")
            return {}

    def _calculate_technical_score(
        self, indicators: Dict[str, Any], price_data,
        avg_volume: float = 0, is_breakout: bool = False
    ) -> float:
        """Calculate technical score (0-100)"""
        score = 0.0

        try:
            price = indicators.get('current_price', 0)
            sma_20 = indicators.get('sma_20', 0)
            sma_50 = indicators.get('sma_50', 0)
            sma_200 = indicators.get('sma_200', 0)
            rsi = indicators.get('rsi_14', 50)
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_hist = indicators.get('macd_histogram', 0)

            # Trend alignment (0-25 points)
            if price > sma_20 > sma_50 > sma_200:
                score += 25
            elif price > sma_50 > sma_200:
                score += 15

            # RSI positioning (0-20 points)
            if 50 <= rsi <= 65:
                score += 20
            elif 40 <= rsi < 50 or 65 < rsi <= 70:
                score += 10

            # MACD momentum (0-20 points)
            if macd > macd_signal and macd_hist > 0:
                score += 20
            elif macd > macd_signal:
                score += 10

            # Volume (0-20 points, uses pre-computed avg_volume)
            volume = indicators.get('volume', 0)
            if volume and avg_volume:
                if volume > avg_volume * 1.5:
                    score += 20
                elif volume > avg_volume * 1.2:
                    score += 10

            # Breakout (0-15 points, uses pre-computed value)
            if is_breakout:
                score += 15

            return score

        except Exception as e:
            logger.error(f"Error calculating technical score: {e}")
            return 0.0

    def _calculate_momentum_score(self, returns: Dict[str, float]) -> float:
        """Calculate momentum score (0-100)"""
        score = 0.0

        try:
            # 1-month performance (0-30 points)
            return_1m = returns.get('return_1m', 0)
            if return_1m > 0.15:
                score += 30
            elif return_1m > 0.10:
                score += 20
            elif return_1m > 0.05:
                score += 10

            # 3-month performance (0-30 points)
            return_3m = returns.get('return_3m', 0)
            if return_3m > 0.30:
                score += 30
            elif return_3m > 0.20:
                score += 20
            elif return_3m > 0.10:
                score += 10

            # 1-year performance (0-40 points)
            return_1y = returns.get('return_1y', 0)
            if return_1y > 0.50:
                score += 40
            elif return_1y > 0.30:
                score += 25
            elif return_1y > 0.10:
                score += 10

            return score

        except Exception as e:
            logger.error(f"Error calculating momentum score: {e}")
            return 0.0

    def _calculate_composite_score(
        self,
        fundamental_score: float,
        technical_score: float,
        options_score: float,
        momentum_score: float,
        sentiment_score: Optional[float] = None
    ) -> float:
        """
        Calculate weighted composite score

        Weights (without sentiment):
        - Fundamental: 40%
        - Technical: 30%
        - Options: 20%
        - Momentum: 10%

        Weights (with sentiment - Phase 2):
        - Fundamental: 35%
        - Technical: 25%
        - Options: 15%
        - Momentum: 10%
        - Sentiment: 15%

        Args:
            fundamental_score: Score from fundamental analysis (0-100)
            technical_score: Score from technical analysis (0-100)
            options_score: Score from options analysis (0-100)
            momentum_score: Score from momentum analysis (0-100)
            sentiment_score: Optional sentiment score (0-100)

        Returns:
            Weighted composite score (0-100)
        """
        if sentiment_score is not None:
            # Phase 2 weights with sentiment
            return (
                fundamental_score * 0.35 +
                technical_score * 0.25 +
                options_score * 0.15 +
                momentum_score * 0.10 +
                sentiment_score * 0.15
            )
        else:
            # Original weights without sentiment
            return (
                fundamental_score * 0.40 +
                technical_score * 0.30 +
                options_score * 0.20 +
                momentum_score * 0.10
            )

    # --- v1 scoring methods ---

    def _evaluate_technical(
        self,
        indicators: Dict[str, Any],
        price_data,
        avg_volume: float = 0,
        is_breakout: bool = False,
    ) -> StageResult:
        """
        Tri-state technical evaluation with coverage-adjusted score (0-90 max).
        RSI max=15, MACD max=15, non-breakout perfect=75, total max=90.
        """
        POINTS_TOTAL_MAX = 90.0

        # Data sufficiency check
        if not TechnicalAnalysis.has_sufficient_data(price_data):
            return StageResult(
                stage_id="technical",
                criteria={
                    'uptrend': CriterionResult.UNKNOWN,
                    'rsi_ok': CriterionResult.UNKNOWN,
                    'macd_bullish': CriterionResult.UNKNOWN,
                    'volume_above_avg': CriterionResult.UNKNOWN,
                    'breakout': CriterionResult.UNKNOWN,
                    'volatility_ok': CriterionResult.UNKNOWN,
                    'trend_strong': CriterionResult.UNKNOWN,
                },
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=7),
                reason="insufficient_price_history",
                points_total_max=POINTS_TOTAL_MAX,
            )

        try:
            criteria: Dict[str, CriterionResult] = {}

            price = indicators.get('current_price')
            sma_20 = indicators.get('sma_20')
            sma_50 = indicators.get('sma_50')
            sma_200 = indicators.get('sma_200')
            rsi = indicators.get('rsi_14')
            macd = indicators.get('macd')
            macd_signal = indicators.get('macd_signal')
            macd_hist = indicators.get('macd_histogram')
            volume = indicators.get('volume')
            atr = indicators.get('atr_14')
            adx = indicators.get('adx_14')

            # 1. Uptrend
            if price is not None and sma_50 is not None and sma_200 is not None:
                criteria['uptrend'] = (
                    CriterionResult.PASS if price > sma_50 > sma_200
                    else CriterionResult.FAIL
                )
            else:
                criteria['uptrend'] = CriterionResult.UNKNOWN

            # 2. RSI OK
            if rsi is not None:
                criteria['rsi_ok'] = (
                    CriterionResult.PASS if 40 <= rsi <= 70
                    else CriterionResult.FAIL
                )
            else:
                criteria['rsi_ok'] = CriterionResult.UNKNOWN

            # 3. MACD bullish
            if macd is not None and macd_signal is not None:
                criteria['macd_bullish'] = (
                    CriterionResult.PASS if macd > macd_signal
                    else CriterionResult.FAIL
                )
            else:
                criteria['macd_bullish'] = CriterionResult.UNKNOWN

            # 4. Volume above avg
            if volume is not None and avg_volume:
                criteria['volume_above_avg'] = (
                    CriterionResult.PASS if volume > avg_volume * 1.2
                    else CriterionResult.FAIL
                )
            else:
                criteria['volume_above_avg'] = CriterionResult.UNKNOWN

            # 5. Breakout (PASS/FAIL only)
            criteria['breakout'] = (
                CriterionResult.PASS if is_breakout else CriterionResult.FAIL
            )

            # 6. Volatility OK
            if atr is not None and price is not None and price > 0:
                criteria['volatility_ok'] = (
                    CriterionResult.PASS if (atr / price) > 0.03
                    else CriterionResult.FAIL
                )
            else:
                criteria['volatility_ok'] = CriterionResult.UNKNOWN

            # 7. Trend strong
            if adx is not None:
                criteria['trend_strong'] = (
                    CriterionResult.PASS if adx > 25
                    else CriterionResult.FAIL
                )
            else:
                criteria['trend_strong'] = CriterionResult.UNKNOWN

            # --- Coverage-adjusted scoring ---
            # Buckets: trend(25), rsi(15), macd(15), volume(20), breakout(15)
            points_earned = 0.0
            points_known_max = 0.0

            # Trend alignment (max 25)
            if price is not None and sma_20 is not None and sma_50 is not None and sma_200 is not None:
                points_known_max += 25
                if price > sma_20 > sma_50 > sma_200:
                    points_earned += 25
                elif price > sma_50 > sma_200:
                    points_earned += 15

            # RSI positioning (max 15)
            if rsi is not None:
                points_known_max += 15
                if 50 <= rsi <= 65:
                    points_earned += 15
                elif 40 <= rsi < 50 or 65 < rsi <= 70:
                    points_earned += 8

            # MACD momentum (max 15)
            if macd is not None and macd_signal is not None and macd_hist is not None:
                points_known_max += 15
                if macd > macd_signal and macd_hist > 0:
                    points_earned += 15
                elif macd > macd_signal:
                    points_earned += 8

            # Volume strength (max 20)
            if volume is not None and avg_volume:
                points_known_max += 20
                if volume > avg_volume * 1.5:
                    points_earned += 20
                elif volume > avg_volume * 1.2:
                    points_earned += 10

            # Breakout bonus (max 15) — always known (PASS/FAIL)
            points_known_max += 15
            if is_breakout:
                points_earned += 15

            coverage = build_coverage_from_criteria(criteria)
            score_pct, score_points, score_pct_raw = compute_coverage_adjusted_score(
                points_earned, points_known_max, POINTS_TOTAL_MAX
            )

            return StageResult(
                stage_id="technical",
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
            logger.error(f"Error in technical evaluate: {e}")
            return StageResult(
                stage_id="technical",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=7),
                reason=f"error: {e}",
                points_total_max=POINTS_TOTAL_MAX,
            )

    def _evaluate_momentum(self, returns: Dict[str, float]) -> StageResult:
        """
        Momentum evaluation with drawdown penalties, returning StageResult.
        Base scoring: 1M(30) + 3M(30) + 1Y(40) = 100.
        Penalties applied after base, then clamp 0-100.
        """
        POINTS_TOTAL_MAX = 100.0

        try:
            criteria: Dict[str, CriterionResult] = {}
            points_earned = 0.0
            points_known_max = 0.0
            penalty = 0

            # 1-month (max 30)
            return_1m = returns.get('return_1m')
            if return_1m is not None:
                criteria['return_1m_available'] = CriterionResult.PASS
                points_known_max += 30
                if return_1m > 0.15:
                    points_earned += 30
                elif return_1m > 0.10:
                    points_earned += 20
                elif return_1m > 0.05:
                    points_earned += 10
                # Drawdown penalty
                if return_1m < -0.10:
                    penalty += 15
                elif return_1m < -0.05:
                    penalty += 10
            else:
                criteria['return_1m_available'] = CriterionResult.UNKNOWN

            # 3-month (max 30)
            return_3m = returns.get('return_3m')
            if return_3m is not None:
                criteria['return_3m_available'] = CriterionResult.PASS
                points_known_max += 30
                if return_3m > 0.30:
                    points_earned += 30
                elif return_3m > 0.20:
                    points_earned += 20
                elif return_3m > 0.10:
                    points_earned += 10
                # Drawdown penalty
                if return_3m < -0.20:
                    penalty += 15
                elif return_3m < -0.10:
                    penalty += 10
            else:
                criteria['return_3m_available'] = CriterionResult.UNKNOWN

            # 1-year (max 40)
            return_1y = returns.get('return_1y')
            if return_1y is not None:
                criteria['return_1y_available'] = CriterionResult.PASS
                points_known_max += 40
                if return_1y > 0.50:
                    points_earned += 40
                elif return_1y > 0.30:
                    points_earned += 25
                elif return_1y > 0.10:
                    points_earned += 10
                # Drawdown penalty
                if return_1y < -0.30:
                    penalty += 20
                elif return_1y < -0.15:
                    penalty += 10
            else:
                criteria['return_1y_available'] = CriterionResult.UNKNOWN

            # Apply penalty to earned points, clamp at 0
            points_earned = max(0.0, points_earned - penalty)

            coverage = build_coverage_from_criteria(criteria)
            score_pct, score_points, score_pct_raw = compute_coverage_adjusted_score(
                points_earned, points_known_max, POINTS_TOTAL_MAX
            )

            return StageResult(
                stage_id="momentum",
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
            logger.error(f"Error in momentum evaluate: {e}")
            return StageResult(
                stage_id="momentum",
                criteria={},
                coverage=CoverageInfo(known_count=0, pass_count=0, total_count=3),
                reason=f"error: {e}",
                points_total_max=POINTS_TOTAL_MAX,
            )

    def _calculate_composite_score_v1(
        self,
        fundamental: StageResult,
        technical: StageResult,
        options: StageResult,
        momentum: StageResult,
        sentiment_score: Optional[float] = None,
        sentiment_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Composite score with rescaling and UNKNOWN handling.

        D1: When sentiment_mode=True but sentiment_score is None,
            use with-sentiment weights with S=50 (neutral), sentiment_available=false.
        D3: Uses score_points from each StageResult for composite math.
        """
        # Determine weight scheme
        use_sentiment_weights = sentiment_mode or sentiment_score is not None

        if use_sentiment_weights:
            weights = {"F": 0.35, "T": 0.25, "O": 0.15, "M": 0.10, "S": 0.15}
            RAW_MAX = 97.5
        else:
            weights = {"F": 0.40, "T": 0.30, "O": 0.20, "M": 0.10}
            RAW_MAX = 97.0

        availability: Dict[str, bool] = {}
        points: Dict[str, float] = {}

        for key, stage in [("F", fundamental), ("T", technical), ("O", options), ("M", momentum)]:
            if stage.score_points is not None:
                points[key] = stage.score_points
                availability[key] = True
            else:
                # D4/scale-aware neutral: 50% of that component's max points
                points[key] = 0.5 * stage.points_total_max
                availability[key] = False

        if use_sentiment_weights:
            if sentiment_score is not None:
                points["S"] = sentiment_score  # sentiment is 0-100, total_max=100
                availability["S"] = True
            else:
                points["S"] = 50.0  # neutral for sentiment (0.5 * 100)
                availability["S"] = False

        raw = sum(weights[k] * points[k] for k in weights)
        final = max(0.0, min(100.0, raw * (100.0 / RAW_MAX)))

        return {
            "score": round(final, 2),
            "component_availability": {
                "fundamental_available": availability.get("F", False),
                "technical_available": availability.get("T", False),
                "options_available": availability.get("O", False),
                "momentum_available": availability.get("M", False),
                "sentiment_available": availability.get("S", False),
            },
        }

    async def get_sentiment_data(
        self,
        symbol: str,
        company_name: Optional[str] = None,
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get sentiment analysis for a stock.

        Args:
            symbol: Stock ticker symbol
            company_name: Company name for news search
            current_price: Current stock price

        Returns:
            Dict with sentiment scores and metadata
        """
        try:
            sentiment_score = await self.sentiment_analyzer.analyze(
                symbol, company_name, current_price
            )
            return self.sentiment_analyzer.get_sentiment_summary(sentiment_score)
        except Exception as e:
            logger.error(f"Error getting sentiment for {symbol}: {e}")
            return {}

    async def get_catalyst_data(
        self,
        symbol: str,
        company_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get catalyst calendar for a stock.

        Args:
            symbol: Stock ticker symbol
            company_name: Company name

        Returns:
            Dict with catalyst data
        """
        try:
            calendar = await self.catalyst_service.get_catalyst_calendar(
                symbol, company_name
            )
            return {
                'next_earnings_date': (
                    calendar.next_earnings_date.isoformat()
                    if calendar.next_earnings_date else None
                ),
                'days_to_earnings': calendar.days_to_earnings,
                'next_dividend_date': (
                    calendar.next_dividend_date.isoformat()
                    if calendar.next_dividend_date else None
                ),
                'days_to_dividend': calendar.days_to_dividend,
                'catalyst_score': calendar.catalyst_score,
                'risk_level': calendar.risk_level,
                'recommendation': calendar.recommendation,
                'catalysts': [
                    {
                        'type': c.catalyst_type.value,
                        'date': c.date.isoformat(),
                        'description': c.description,
                        'impact': c.impact.value
                    }
                    for c in calendar.catalysts
                ]
            }
        except Exception as e:
            logger.error(f"Error getting catalysts for {symbol}: {e}")
            return {}

    async def screen_with_sentiment(
        self,
        symbol: str,
        custom_criteria: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Screen a single stock with sentiment analysis (async).

        This is the Phase 2 enhanced screening that includes:
        - All original screening stages
        - Sentiment scoring (news, analyst, insider)
        - Catalyst timing analysis

        Threading model:
            The synchronous ``screen_single_stock()`` is offloaded to a
            thread via ``run_in_executor`` to avoid blocking the event loop.
            Sentiment and catalyst fetches then run as native async tasks.

        Args:
            symbol: Stock ticker symbol
            custom_criteria: Optional custom screening thresholds

        Returns:
            Dict with screening results including sentiment
        """
        # Offload sync screening to thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, self.screen_single_stock, symbol, custom_criteria
        )

        if not result:
            return None

        # If stock passed basic screening, add sentiment
        if result.get('passed_all', False):
            sentiment_score_value: Optional[float] = None

            try:
                # Get sentiment and catalyst data concurrently
                sentiment_task = self.get_sentiment_data(
                    symbol,
                    result.get('name'),
                    result.get('current_price')
                )
                catalyst_task = self.get_catalyst_data(
                    symbol,
                    result.get('name')
                )

                sentiment_data, catalyst_data = await asyncio.gather(
                    sentiment_task, catalyst_task
                )

                # Add to result
                result['sentiment'] = sentiment_data
                result['catalysts'] = catalyst_data

                # Get sentiment score (may be missing if fetch failed)
                if sentiment_data and 'overall_score' in sentiment_data:
                    sentiment_score_value = sentiment_data['overall_score']
                result['sentiment_score'] = sentiment_score_value

                # Add sentiment-based flags
                flags = sentiment_data.get('flags', {})
                result['earnings_risk'] = flags.get('earnings_risk', False)
                result['insider_buying'] = flags.get('insider_buying', False)
                result['has_upgrade'] = flags.get('has_recent_upgrade', False)

            except Exception as e:
                logger.error(f"Error adding sentiment to {symbol}: {e}")
                # D1: Continue with sentiment_mode=True even if fetch failed

            # Recalculate composite with sentiment weights (D1: always use
            # with-sentiment scheme once caller opts in, even if score is None)
            fund_stage = StageResult(
                stage_id="fundamental", criteria={},
                coverage=CoverageInfo(0, 0, 5),
                score_pct=result.get('fundamental_score'),
                score_points=result.get('fundamental_score'),  # pct == points for 0-100 max
                points_total_max=100.0,
            )
            tech_stage = StageResult(
                stage_id="technical", criteria={},
                coverage=CoverageInfo(0, 0, 7),
                score_pct=result.get('technical_score'),
                score_points=result.get('technical_score_points'),
                points_total_max=90.0,
            )
            opt_stage = StageResult(
                stage_id="options", criteria={},
                coverage=CoverageInfo(0, 0, 4),
                score_pct=result.get('options_score'),
                score_points=result.get('options_score'),  # pct == points for 0-100 max
                points_total_max=100.0,
            )
            mom_stage = StageResult(
                stage_id="momentum", criteria={},
                coverage=CoverageInfo(0, 0, 3),
                score_pct=result.get('momentum_score'),
                score_points=result.get('momentum_score'),  # pct == points for 0-100 max
                points_total_max=100.0,
            )

            composite = self._calculate_composite_score_v1(
                fund_stage, tech_stage, opt_stage, mom_stage,
                sentiment_score=sentiment_score_value,
                sentiment_mode=True,
            )
            result['score'] = composite['score']
            result['component_availability'] = composite['component_availability']

            logger.info(
                f"{symbol}: Enhanced score with sentiment: {result['score']:.2f} "
                f"(sentiment: {sentiment_score_value})"
            )

        return result

    async def screen_multiple_with_sentiment(
        self,
        symbols: List[str],
        custom_criteria: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Screen multiple stocks with sentiment (async).

        Threading model:
            First pass offloads synchronous screening to a thread pool so the
            event loop remains free.  Second pass adds sentiment via native
            async tasks with a concurrency semaphore.

        Args:
            symbols: List of stock ticker symbols
            custom_criteria: Optional custom screening thresholds
            max_concurrent: Max concurrent sentiment fetches

        Returns:
            List of screening results sorted by score
        """
        results = []

        # First pass: offload sync screening to thread pool
        loop = asyncio.get_running_loop()
        for symbol in symbols:
            result = await loop.run_in_executor(
                None, self.screen_single_stock, symbol, custom_criteria
            )
            if result and result.get('passed_all', False):
                results.append(result)

        # Second pass: add sentiment to passed stocks (with concurrency limit)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def add_sentiment(result):
            async with semaphore:
                symbol = result['symbol']
                try:
                    sentiment_data = await self.get_sentiment_data(
                        symbol,
                        result.get('name'),
                        result.get('current_price')
                    )
                    catalyst_data = await self.get_catalyst_data(
                        symbol,
                        result.get('name')
                    )

                    result['sentiment'] = sentiment_data
                    result['catalysts'] = catalyst_data
                    result['sentiment_score'] = sentiment_data.get('overall_score', 50)

                    # Recalculate score
                    result['score'] = self._calculate_composite_score(
                        result.get('fundamental_score', 0),
                        result.get('technical_score', 0),
                        result.get('options_score', 0),
                        result.get('momentum_score', 0),
                        result['sentiment_score']
                    )
                except Exception as e:
                    logger.error(f"Error adding sentiment to {symbol}: {e}")

        # Add sentiment to all passed results
        await asyncio.gather(*[add_sentiment(r) for r in results])

        # Sort by score (descending)
        results.sort(key=lambda x: x.get('score', 0), reverse=True)

        return results


    def calculate_stock_scores(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Calculate scores for a stock without filter gates (v1).

        Unlike screen_single_stock(), this never short-circuits on filter failures.
        All 4 sub-scores are always computed (defaulting to None/neutral on error).
        Uses v1 StageResults with coverage-adjusted scoring and composite rescaling.
        """
        logger.info(f"Calculating scores for {symbol}...")

        result: Dict[str, Any] = {
            'symbol': symbol,
            'fundamental_score': None,
            'technical_score': None,
            'technical_score_points': None,
            'options_score': None,
            'momentum_score': None,
            'score': 0,
            'technical_indicators': {},
            'leaps_summary': {},
            'returns': {},
            'criteria': {},
            'coverage': {},
            'component_availability': {},
        }

        # Default StageResults (all UNKNOWN)
        fund_stage = StageResult(
            stage_id="fundamental", criteria={},
            coverage=CoverageInfo(0, 0, 5), points_total_max=100.0,
        )
        tech_stage = StageResult(
            stage_id="technical", criteria={},
            coverage=CoverageInfo(0, 0, 7), points_total_max=90.0,
        )
        opt_stage = StageResult(
            stage_id="options", criteria={},
            coverage=CoverageInfo(0, 0, 4), points_total_max=100.0,
        )
        mom_stage = StageResult(
            stage_id="momentum", criteria={},
            coverage=CoverageInfo(0, 0, 3), points_total_max=100.0,
        )

        try:
            # Basic info
            stock_info = fmp_service.get_stock_info(symbol)
            if not stock_info:
                logger.warning(f"{symbol}: Failed to get stock info for scoring")
                # Compute composite with all-UNKNOWN stages
                composite = self._calculate_composite_score_v1(
                    fund_stage, tech_stage, opt_stage, mom_stage
                )
                result['score'] = composite['score']
                result['composite_score'] = result['score']
                result['component_availability'] = composite['component_availability']
                return result

            result['name'] = stock_info.get('name')
            result['sector'] = stock_info.get('sector')
            result['market_cap'] = stock_info.get('market_cap')
            result['current_price'] = stock_info.get('currentPrice')

            # 1. Fundamental score
            try:
                fundamentals = fmp_service.get_fundamentals(symbol)
                if fundamentals:
                    # Propagate valuation metrics for frontend
                    result['trailing_pe'] = fundamentals.get('trailing_pe')
                    result['peg_ratio'] = fundamentals.get('peg_ratio')
                    result['price_to_book'] = fundamentals.get('price_to_book')
                    result['dividend_yield'] = fundamentals.get('dividend_yield')
                    result['beta'] = fundamentals.get('beta')
                    result['roe'] = fundamentals.get('roe')
                    result['profit_margins'] = fundamentals.get('profit_margins')

                    fund_stage = self.fund_analysis.evaluate(
                        fundamentals, stock_info
                    )
                    result['fundamental_score'] = fund_stage.score_pct
                    result['criteria']['fundamental'] = {
                        k: v.value for k, v in fund_stage.criteria.items()
                    }
                    result['coverage']['fundamental'] = fund_stage.coverage.to_dict()
            except Exception as e:
                logger.warning(f"{symbol}: Fundamental score failed: {e}")

            # 2. Technical score + momentum (share price_data)
            try:
                price_data = alpaca_service.get_historical_prices(symbol, period="2y")
                if price_data is not None and not price_data.empty:
                    price_data = self.tech_analysis.calculate_all_indicators(price_data)
                    tech_indicators = self.tech_analysis.get_latest_indicators(price_data)
                    result['technical_indicators'] = tech_indicators
                    result['current_price'] = tech_indicators.get('current_price', result['current_price'])

                    avg_volume = self.tech_analysis.calculate_avg_volume(price_data, 50)
                    is_breakout = self.tech_analysis.detect_breakout(price_data, 60)
                    tech_stage = self._evaluate_technical(
                        tech_indicators, price_data,
                        avg_volume=avg_volume or 0, is_breakout=is_breakout
                    )
                    result['technical_score'] = tech_stage.score_pct
                    result['technical_score_points'] = tech_stage.score_points
                    result['criteria']['technical'] = {
                        k: v.value for k, v in tech_stage.criteria.items()
                    }
                    result['coverage']['technical'] = tech_stage.coverage.to_dict()

                    returns = self.tech_analysis.calculate_returns(price_data)
                    result['returns'] = returns
                    mom_stage = self._evaluate_momentum(returns)
                    result['momentum_score'] = mom_stage.score_pct
                    result['criteria']['momentum'] = {
                        k: v.value for k, v in mom_stage.criteria.items()
                    }
                    result['coverage']['momentum'] = mom_stage.coverage.to_dict()
            except Exception as e:
                logger.warning(f"{symbol}: Technical/momentum score failed: {e}")

            # 3. Options score
            try:
                current_price = result.get('current_price', 0) or 0
                if current_price > 0:
                    options_data = alpaca_service.get_options_chain(symbol)
                    has_options_data = bool(options_data and 'calls' in options_data)
                    leaps_summary = {}
                    leaps_available = False
                    atm_option = None

                    if has_options_data:
                        leaps_summary = self.opt_analysis.get_leaps_summary_enhanced(
                            options_data['calls'], current_price, datetime.now(), symbol
                        )
                        leaps_available = leaps_summary.get('available', False)
                        atm_option = leaps_summary.get('atm_option')
                        result['leaps_summary'] = leaps_summary

                        tt = leaps_summary.get('tastytrade', {})
                        result['iv_rank'] = tt.get('iv_rank')
                        result['iv_percentile'] = tt.get('iv_percentile')

                    opt_stage = self.opt_analysis.evaluate(
                        option_data=atm_option,
                        current_price=current_price,
                        symbol=symbol,
                        leaps_available=leaps_available,
                        has_options_data=has_options_data,
                    )
                    result['options_score'] = opt_stage.score_pct
                    result['criteria']['options'] = {
                        k: v.value for k, v in opt_stage.criteria.items()
                    }
                    result['coverage']['options'] = opt_stage.coverage.to_dict()
            except Exception as e:
                logger.warning(f"{symbol}: Options score failed: {e}")

            # 4. Composite score (v1 rescaled)
            composite = self._calculate_composite_score_v1(
                fund_stage, tech_stage, opt_stage, mom_stage
            )
            result['score'] = composite['score']
            result['composite_score'] = result['score']
            result['component_availability'] = composite['component_availability']

            logger.info(f"{symbol}: Score calculated: {result['score']:.1f}")
            return result

        except Exception as e:
            logger.error(f"Error calculating scores for {symbol}: {e}")
            return result

    def calculate_batch_scores(
        self,
        symbols: List[str],
        max_workers: int = 4
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate scores for multiple stocks in parallel.

        Args:
            symbols: List of stock ticker symbols
            max_workers: Max concurrent threads

        Returns:
            Dict mapping symbol to scores dict
        """
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.calculate_stock_scores, symbol): symbol
                for symbol in symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                    if result:
                        results[symbol] = result
                except Exception as e:
                    logger.error(f"Error scoring {symbol} in batch: {e}")

        return results


# Singleton instance
screening_engine = ScreeningEngine()
