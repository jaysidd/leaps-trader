"""
Finviz Elite API integration for stock screening
"""
import requests
import csv
from io import StringIO
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime, timedelta

from app.services.cache import cache
from app.services.data_fetcher.rate_limiter import RateLimiter


class FinvizService:
    """
    Finviz Elite API service for stock screening and fundamental data
    """

    BASE_URL = "https://elite.finviz.com/export.ashx"

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize Finviz service

        Args:
            api_token: Finviz Elite API token (required for API access)
        """
        self.api_token = api_token
        self.rate_limiter = RateLimiter(max_requests=1, time_window=1)  # 1 req/sec for Finviz
        if not api_token:
            logger.warning("Finviz API token not provided. Service will not be functional.")

    def _build_filter_url(self, filters: Dict[str, Any]) -> str:
        """
        Build Finviz screener URL with filters

        Args:
            filters: Dict of Finviz filter codes and values

        Returns:
            Complete URL with filters
        """
        # Convert filters dict to query parameters
        filter_params = []

        for key, value in filters.items():
            filter_params.append(f"{key}={value}")

        # Join all filters
        filter_string = "&".join(filter_params)

        # Add auth token
        url = f"{self.BASE_URL}?{filter_string}&auth={self.api_token}"

        return url

    def screen_stocks(
        self,
        market_cap_min: Optional[int] = None,
        market_cap_max: Optional[int] = None,
        revenue_growth_min: Optional[float] = None,
        eps_growth_min: Optional[float] = None,
        sector: Optional[str] = None,
        custom_filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Screen stocks using Finviz filters

        Finviz filter codes (common ones):
        - cap_smallover: Market Cap > $300M
        - cap_midover: Market Cap > $2B
        - cap_largeover: Market Cap > $10B
        - fa_salesqoq_pos: Sales Q/Q growth positive
        - fa_epsqoq_pos: EPS Q/Q growth positive
        - ta_rsi_os40: RSI oversold (< 40)
        - ta_rsi_ob60: RSI overbought (> 60)
        - sec_technology: Technology sector
        - sec_healthcare: Healthcare sector

        Args:
            market_cap_min: Minimum market cap
            market_cap_max: Maximum market cap
            revenue_growth_min: Minimum revenue growth percentage
            eps_growth_min: Minimum EPS growth percentage
            sector: Sector filter
            custom_filters: Dict of custom Finviz filter codes

        Returns:
            List of stock screening results
        """
        if not self.api_token:
            logger.error("Finviz API token not configured")
            return []

        # Build filters dict
        filters = custom_filters or {}

        # Map our criteria to Finviz filter codes
        if market_cap_min:
            if market_cap_min >= 10_000_000_000:
                filters['cap_largeover'] = ''  # > $10B
            elif market_cap_min >= 2_000_000_000:
                filters['cap_midover'] = ''  # > $2B
            elif market_cap_min >= 300_000_000:
                filters['cap_smallover'] = ''  # > $300M

        if revenue_growth_min and revenue_growth_min > 0:
            filters['fa_salesqoq_pos'] = ''  # Positive sales growth

        if eps_growth_min and eps_growth_min > 0:
            filters['fa_epsqoq_pos'] = ''  # Positive EPS growth

        # Sector mapping
        if sector:
            sector_map = {
                'Technology': 'sec_technology',
                'Healthcare': 'sec_healthcare',
                'Financial': 'sec_financial',
                'Consumer Cyclical': 'sec_consumer_cyclical',
                'Industrials': 'sec_industrials',
                'Energy': 'sec_energy',
            }
            sector_code = sector_map.get(sector)
            if sector_code:
                filters[sector_code] = ''

        # Check cache
        cache_key = f"finviz:screen:{str(filters)}"
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info("Returning cached Finviz screening results")
            return cached_data

        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()

            # Build URL and fetch
            url = self._build_filter_url(filters)
            logger.info(f"Fetching Finviz screener results...")

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Parse CSV response
            results = self._parse_csv_response(response.text)

            # Cache results for 1 hour
            cache.set(cache_key, results, ttl=3600)

            logger.success(f"Finviz screener returned {len(results)} stocks")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Finviz data: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing Finviz response: {e}")
            return []

    def _parse_csv_response(self, csv_text: str) -> List[Dict[str, Any]]:
        """
        Parse CSV response from Finviz

        Args:
            csv_text: Raw CSV text

        Returns:
            List of parsed stock data dicts
        """
        results = []

        try:
            csv_file = StringIO(csv_text)
            reader = csv.DictReader(csv_file)

            for row in reader:
                # Convert Finviz data to our format
                stock_data = {
                    'symbol': row.get('Ticker', ''),
                    'name': row.get('Company', ''),
                    'sector': row.get('Sector', ''),
                    'industry': row.get('Industry', ''),
                    'market_cap': self._parse_market_cap(row.get('Market Cap', '')),
                    'price': self._parse_number(row.get('Price', '')),
                    'volume': self._parse_volume(row.get('Volume', '')),
                    'pe_ratio': self._parse_number(row.get('P/E', '')),
                    'forward_pe': self._parse_number(row.get('Forward P/E', '')),
                    'peg_ratio': self._parse_number(row.get('PEG', '')),
                    'dividend_yield': self._parse_percentage(row.get('Dividend %', '')),
                    'roe': self._parse_percentage(row.get('ROE', '')),
                    'roa': self._parse_percentage(row.get('ROA', '')),
                    'debt_to_equity': self._parse_number(row.get('Debt/Eq', '')),
                    'current_ratio': self._parse_number(row.get('Current Ratio', '')),
                    'eps_growth_next_year': self._parse_percentage(row.get('EPS next Y', '')),
                    'sales_growth_qoq': self._parse_percentage(row.get('Sales Q/Q', '')),
                    'eps_growth_qoq': self._parse_percentage(row.get('EPS Q/Q', '')),
                    'rsi': self._parse_number(row.get('RSI (14)', '')),
                    'sma_20': self._parse_number(row.get('SMA20', '')),
                    'sma_50': self._parse_number(row.get('SMA50', '')),
                    'sma_200': self._parse_number(row.get('SMA200', '')),
                    'change': self._parse_percentage(row.get('Change', '')),
                    'volume_avg': self._parse_volume(row.get('Avg Volume', '')),
                }

                results.append(stock_data)

        except Exception as e:
            logger.error(f"Error parsing CSV row: {e}")

        return results

    def _parse_market_cap(self, value: str) -> Optional[int]:
        """Parse market cap from Finviz format (e.g., '123.45B', '456.78M')"""
        if not value or value == '-':
            return None

        try:
            value = value.strip()
            if value.endswith('B'):
                return int(float(value[:-1]) * 1_000_000_000)
            elif value.endswith('M'):
                return int(float(value[:-1]) * 1_000_000)
            elif value.endswith('K'):
                return int(float(value[:-1]) * 1_000)
            else:
                return int(float(value))
        except:
            return None

    def _parse_volume(self, value: str) -> Optional[int]:
        """Parse volume from Finviz format"""
        if not value or value == '-':
            return None

        try:
            value = value.strip()
            if value.endswith('M'):
                return int(float(value[:-1]) * 1_000_000)
            elif value.endswith('K'):
                return int(float(value[:-1]) * 1_000)
            else:
                return int(float(value))
        except:
            return None

    def _parse_percentage(self, value: str) -> Optional[float]:
        """Parse percentage from Finviz format (e.g., '12.34%')"""
        if not value or value == '-':
            return None

        try:
            value = value.strip().replace('%', '')
            return float(value) / 100
        except:
            return None

    def _parse_number(self, value: str) -> Optional[float]:
        """Parse number from Finviz format"""
        if not value or value == '-':
            return None

        try:
            return float(value.replace(',', ''))
        except:
            return None

    def get_stock_symbols_by_filters(self, filters: Dict[str, Any]) -> List[str]:
        """
        Get list of stock symbols matching filters

        Args:
            filters: Finviz filter codes

        Returns:
            List of stock symbols
        """
        results = self.screen_stocks(custom_filters=filters)
        return [stock['symbol'] for stock in results if stock.get('symbol')]


# Singleton instance (will be initialized with config)
finviz_service: Optional[FinvizService] = None


def initialize_finviz_service(api_token: Optional[str]):
    """
    Initialize the Finviz service with API token

    Args:
        api_token: Finviz Elite API token
    """
    global finviz_service
    finviz_service = FinvizService(api_token)
    logger.info("Finviz service initialized")
