"""
Stock universe for automated scanning
Contains major indices and popular stocks for LEAPS screening
"""
from loguru import logger

# S&P 500 Large Caps (Top 100 by market cap)
SP500_TOP_100 = [
    # Mega Cap Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL", "AMD",
    "CRM", "ADBE", "CSCO", "ACN", "INTC", "IBM", "QCOM", "TXN", "AMAT", "ADI",

    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN",
    "SYK", "BSX", "GILD", "VRTX", "ISRG", "ELV", "CI", "CVS", "MDT", "REGN",

    # Financials
    "BRK.B", "V", "MA", "JPM", "BAC", "WFC", "MS", "GS", "C", "BLK",
    "SCHW", "AXP", "SPGI", "CB", "PGR", "MMC", "ICE", "CME", "AON", "TFC",

    # Consumer
    "COST", "HD", "WMT", "MCD", "NKE", "SBUX", "TJX", "LOW", "BKNG", "MAR",

    # Industrials
    "CAT", "GE", "RTX", "HON", "UPS", "BA", "LMT", "DE", "UNP", "ETN",

    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",

    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "DD", "DOW", "VMC", "MLM"
]

# High Growth Tech & Biotech (Small to Mid Cap)
GROWTH_STOCKS = [
    # Cloud/SaaS
    "SNOW", "DDOG", "NET", "CRWD", "ZS", "OKTA", "TEAM", "WDAY", "PANW", "FTNT",
    "ESTC", "MDB", "CFLT", "S", "PATH", "BILL", "HUBS", "ZM", "DOCN", "FROG",

    # Semiconductors
    "ARM", "ASML", "TSM", "LRCX", "KLAC", "SNPS", "CDNS", "MRVL", "MCHP", "ON",
    "NXPI", "MPWR", "WOLF", "SMCI", "ENTG", "SWKS", "QRVO", "SLAB", "CRUS", "ALGM",

    # Biotech
    "MRNA", "REGN", "VRTX", "BIIB", "ILMN", "INCY", "BMRN", "ALNY", "SGEN", "EXEL",
    "NBIX", "TECH", "RARE", "IONS", "FOLD", "BLUE", "SAGE", "EDIT", "CRSP", "NTLA",

    # Fintech
    "SQ", "PYPL", "COIN", "SOFI", "AFRM", "UPST", "HOOD", "NU", "LC", "OPEN",

    # EV & Clean Energy
    "RIVN", "LCID", "FSR", "CHPT", "BLNK", "ENPH", "SEDG", "RUN", "NOVA", "FSLR",

    # E-commerce & Consumer Tech
    "SHOP", "MELI", "SE", "BABA", "PDD", "JD", "CPNG", "DASH", "UBER", "LYFT",

    # Gaming & Entertainment
    "RBLX", "U", "DKNG", "PENN", "MTCH", "BMBL", "MSGS", "LYV", "NFLX", "DIS"
]

# Mid Cap Growth (Room to 5x)
MID_CAP_GROWTH = [
    # Software
    "PLTR", "GTLB", "MNDY", "IOT", "ASAN", "PCOR", "TENB", "RPD", "SUMO", "AI",

    # Healthcare/Medtech
    "DXCM", "PODD", "NVST", "TDOC", "LFST", "ONEM", "IRTC", "VCYT", "CRTO", "GH",

    # Industrial Tech
    "ROCK", "PL", "XPO", "CHRW", "JBHT", "KNX", "ODFL", "SAIA", "ARCB", "WERN",

    # Consumer
    "LULU", "DECK", "CROX", "SKX", "BIRK", "ONON", "GOOS", "TPR", "CPRI", "RL"
]

# Small Cap High Growth (Highest 5x Potential)
SMALL_CAP_GROWTH = [
    # Emerging Tech
    "IONQ", "RGTI", "BBAI", "SOUN", "SMCI", "RXRX", "ABCL", "GNOM", "ARQT", "QMCO",

    # Biotech Small Cap
    "RPTX", "PHAT", "TGTX", "CGEM", "JANX", "RCKT", "MLTX", "MNOV", "VKTX", "AKRO",

    # Clean Tech
    "BE", "PLUG", "FCEL", "BLDP", "CLSK", "RIOT", "MARA", "BITF", "HUT", "ARBK"
]

# All stock universes combined
ALL_UNIVERSES = {
    "sp500_top100": SP500_TOP_100,
    "growth_stocks": GROWTH_STOCKS,
    "mid_cap_growth": MID_CAP_GROWTH,
    "small_cap_growth": SMALL_CAP_GROWTH
}

def get_stock_universe(universe_name: str = "all"):
    """
    Get stock symbols from specified universe

    Args:
        universe_name: "sp500_top100", "growth_stocks", "mid_cap_growth",
                       "small_cap_growth", or "all"

    Returns:
        List of stock symbols
    """
    if universe_name == "all":
        # Combine all universes, remove duplicates
        all_stocks = []
        for stocks in ALL_UNIVERSES.values():
            all_stocks.extend(stocks)
        return list(set(all_stocks))

    return ALL_UNIVERSES.get(universe_name, [])

def get_universe_by_criteria(market_cap_max: int = None):
    """
    Get appropriate universe based on criteria

    Args:
        market_cap_max: Maximum market cap for filtering

    Returns:
        List of stock symbols
    """
    if market_cap_max is None or market_cap_max > 50_000_000_000:
        # Large cap focus
        return SP500_TOP_100 + GROWTH_STOCKS
    elif market_cap_max > 10_000_000_000:
        # Mid to large cap
        return GROWTH_STOCKS + MID_CAP_GROWTH
    else:
        # Small to mid cap (highest 5x potential)
        return MID_CAP_GROWTH + SMALL_CAP_GROWTH

def get_dynamic_universe(criteria: dict = None) -> list:
    """
    Get a dynamic stock universe from FMP screener, with fallback to hardcoded lists.

    Extracts market_cap_min/max and price_min/max from the preset criteria dict,
    calls FMP's company-screener API, and returns a deduplicated list of symbols.

    Falls back to get_universe_by_criteria() if FMP fails or returns empty.

    Args:
        criteria: Optional preset criteria dict with market_cap_min, market_cap_max, etc.

    Returns:
        List of stock symbols (500-1000+ from FMP, or 200 from hardcoded)
    """
    criteria = criteria or {}

    try:
        from app.services.data_fetcher.fmp_service import fmp_service

        if fmp_service.is_available:
            symbols = fmp_service.get_screener_universe(
                market_cap_min=criteria.get('market_cap_min', 500_000_000),
                market_cap_max=criteria.get('market_cap_max', 100_000_000_000),
                price_min=criteria.get('price_min', 5.0),
                price_max=criteria.get('price_max', 500.0),
                volume_min=100_000,
                limit=1000,
            )
            if symbols and len(symbols) >= 50:
                # Merge with hardcoded universe to ensure coverage of known good stocks
                hardcoded = get_universe_by_criteria(criteria.get('market_cap_max', 100_000_000_000))
                merged = list(dict.fromkeys(symbols + hardcoded))  # dedupe, preserve order
                logger.info(
                    f"Dynamic universe: {len(symbols)} FMP + {len(hardcoded)} hardcoded = {len(merged)} total"
                )
                return merged
            else:
                logger.warning(
                    f"FMP screener returned only {len(symbols) if symbols else 0} symbols, "
                    f"falling back to hardcoded universe"
                )
    except Exception as e:
        logger.warning(f"FMP screener failed, using hardcoded universe: {e}")

    # Fallback to hardcoded
    return get_universe_by_criteria(criteria.get('market_cap_max', 100_000_000_000))


# Quick access to different size categories
LARGE_CAP_UNIVERSE = SP500_TOP_100
MID_CAP_UNIVERSE = GROWTH_STOCKS + MID_CAP_GROWTH
SMALL_CAP_UNIVERSE = SMALL_CAP_GROWTH
FULL_UNIVERSE = get_stock_universe("all")

# Stats
print(f"Stock Universe Loaded:")
print(f"  S&P 500 Top 100: {len(SP500_TOP_100)} stocks")
print(f"  Growth Stocks: {len(GROWTH_STOCKS)} stocks")
print(f"  Mid Cap Growth: {len(MID_CAP_GROWTH)} stocks")
print(f"  Small Cap Growth: {len(SMALL_CAP_GROWTH)} stocks")
print(f"  Total Unique: {len(FULL_UNIVERSE)} stocks")
