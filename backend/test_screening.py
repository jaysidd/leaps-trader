"""
Test script for screening engine
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.screening.engine import screening_engine
from loguru import logger


def main():
    """Test the screening engine with a few popular stocks"""

    # Test stocks - mix of tech, healthcare, growth stocks
    test_symbols = [
        'AAPL',  # Apple
        'NVDA',  # NVIDIA
        'TSLA',  # Tesla
        'AMD',   # AMD
        'PLTR',  # Palantir
    ]

    logger.info(f"Testing screening engine with {len(test_symbols)} stocks...")

    for symbol in test_symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"Screening {symbol}...")
        logger.info(f"{'='*60}")

        result = screening_engine.screen_single_stock(symbol)

        if result:
            print(f"\nSymbol: {symbol}")
            print(f"Name: {result.get('name')}")
            print(f"Sector: {result.get('sector')}")
            print(f"Market Cap: ${result.get('market_cap', 0):,.0f}")
            print(f"Current Price: ${result.get('current_price', 0):.2f}")
            print(f"\nPassed Stages: {result.get('passed_stages', [])}")
            print(f"Failed At: {result.get('failed_at', 'N/A')}")

            if result.get('passed_all'):
                print(f"\n✅ PASSED ALL FILTERS!")
                print(f"Composite Score: {result.get('score', 0):.2f}/100")
                print(f"  - Fundamental: {result.get('fundamental_score', 0):.2f}")
                print(f"  - Technical: {result.get('technical_score', 0):.2f}")
                print(f"  - Options: {result.get('options_score', 0):.2f}")
                print(f"  - Momentum: {result.get('momentum_score', 0):.2f}")
            else:
                print(f"\n❌ Failed at: {result.get('failed_at')}")

        else:
            print(f"❌ {symbol}: No result")

        print("\n")

    logger.success("Testing complete!")


if __name__ == "__main__":
    main()
