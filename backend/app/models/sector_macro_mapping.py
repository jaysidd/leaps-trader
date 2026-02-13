"""
Sector Macro Mapping models for ticker-level macro bias calculation.
Provides sector-level defaults with optional per-ticker overrides.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class SectorMacroMapping(Base):
    """
    Sector-level default macro category weights.
    Scalable approach - tickers inherit from sector.
    """
    __tablename__ = "sector_macro_mappings"

    id = Column(Integer, primary_key=True, index=True)
    sector = Column(String(100), nullable=False, unique=True, index=True)

    # Category weights (should sum to 1.0)
    weight_fed_policy = Column(Float, default=0.2)
    weight_recession = Column(Float, default=0.2)
    weight_elections = Column(Float, default=0.1)
    weight_trade = Column(Float, default=0.1)
    weight_crypto = Column(Float, default=0.0)
    weight_markets = Column(Float, default=0.4)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SectorMacroMapping(sector={self.sector})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "sector": self.sector,
            "weights": {
                "fed_policy": self.weight_fed_policy,
                "recession": self.weight_recession,
                "elections": self.weight_elections,
                "trade": self.weight_trade,
                "crypto": self.weight_crypto,
                "markets": self.weight_markets,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_weights(self) -> dict:
        """Get weights as a dictionary"""
        return {
            "fed_policy": self.weight_fed_policy or 0.0,
            "recession": self.weight_recession or 0.0,
            "elections": self.weight_elections or 0.0,
            "trade": self.weight_trade or 0.0,
            "crypto": self.weight_crypto or 0.0,
            "markets": self.weight_markets or 0.0,
        }


class TickerMacroOverride(Base):
    """
    Optional per-ticker overrides for specific stocks.
    Only create when ticker needs different weights than sector default.
    """
    __tablename__ = "ticker_macro_overrides"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    sector = Column(String(100), nullable=True)  # Reference sector

    # Override weights (null = use sector default)
    weight_fed_policy = Column(Float, nullable=True)
    weight_recession = Column(Float, nullable=True)
    weight_elections = Column(Float, nullable=True)
    weight_trade = Column(Float, nullable=True)
    weight_crypto = Column(Float, nullable=True)
    weight_markets = Column(Float, nullable=True)

    # Custom market associations (specific Polymarket markets to track)
    custom_markets = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<TickerMacroOverride(symbol={self.symbol}, sector={self.sector})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "sector": self.sector,
            "weights": {
                "fed_policy": self.weight_fed_policy,
                "recession": self.weight_recession,
                "elections": self.weight_elections,
                "trade": self.weight_trade,
                "crypto": self.weight_crypto,
                "markets": self.weight_markets,
            },
            "custom_markets": self.custom_markets,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_weights(self, sector_mapping: SectorMacroMapping = None) -> dict:
        """
        Get effective weights, falling back to sector defaults for None values.

        Args:
            sector_mapping: Optional sector mapping to use as fallback

        Returns:
            Dictionary of category weights
        """
        sector_weights = sector_mapping.get_weights() if sector_mapping else {}
        default = 0.0

        return {
            "fed_policy": self.weight_fed_policy if self.weight_fed_policy is not None else sector_weights.get("fed_policy", default),
            "recession": self.weight_recession if self.weight_recession is not None else sector_weights.get("recession", default),
            "elections": self.weight_elections if self.weight_elections is not None else sector_weights.get("elections", default),
            "trade": self.weight_trade if self.weight_trade is not None else sector_weights.get("trade", default),
            "crypto": self.weight_crypto if self.weight_crypto is not None else sector_weights.get("crypto", default),
            "markets": self.weight_markets if self.weight_markets is not None else sector_weights.get("markets", default),
        }


# Default sector mappings as seed data
# Includes common variations of sector names from different data sources
DEFAULT_SECTOR_MAPPINGS = [
    {
        "sector": "Technology",
        "weight_fed_policy": 0.25,
        "weight_recession": 0.20,
        "weight_elections": 0.10,
        "weight_trade": 0.15,
        "weight_crypto": 0.00,
        "weight_markets": 0.30,
    },
    {
        "sector": "Semiconductors",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.15,
        "weight_elections": 0.10,
        "weight_trade": 0.25,
        "weight_crypto": 0.00,
        "weight_markets": 0.30,
    },
    {
        "sector": "Financials",
        "weight_fed_policy": 0.40,
        "weight_recession": 0.30,
        "weight_elections": 0.10,
        "weight_trade": 0.05,
        "weight_crypto": 0.00,
        "weight_markets": 0.15,
    },
    {
        "sector": "Financial Services",  # Yahoo Finance variant
        "weight_fed_policy": 0.40,
        "weight_recession": 0.30,
        "weight_elections": 0.10,
        "weight_trade": 0.05,
        "weight_crypto": 0.00,
        "weight_markets": 0.15,
    },
    {
        "sector": "Energy",
        "weight_fed_policy": 0.15,
        "weight_recession": 0.25,
        "weight_elections": 0.10,
        "weight_trade": 0.25,
        "weight_crypto": 0.00,
        "weight_markets": 0.25,
    },
    {
        "sector": "Healthcare",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.15,
        "weight_elections": 0.25,
        "weight_trade": 0.10,
        "weight_crypto": 0.00,
        "weight_markets": 0.30,
    },
    {
        "sector": "Consumer Discretionary",
        "weight_fed_policy": 0.25,
        "weight_recession": 0.30,
        "weight_elections": 0.10,
        "weight_trade": 0.15,
        "weight_crypto": 0.00,
        "weight_markets": 0.20,
    },
    {
        "sector": "Consumer Staples",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.20,
        "weight_elections": 0.10,
        "weight_trade": 0.10,
        "weight_crypto": 0.00,
        "weight_markets": 0.40,
    },
    {
        "sector": "Defense",
        "weight_fed_policy": 0.10,
        "weight_recession": 0.10,
        "weight_elections": 0.35,
        "weight_trade": 0.20,
        "weight_crypto": 0.00,
        "weight_markets": 0.25,
    },
    {
        "sector": "Crypto-Exposed",
        "weight_fed_policy": 0.10,
        "weight_recession": 0.10,
        "weight_elections": 0.10,
        "weight_trade": 0.05,
        "weight_crypto": 0.50,
        "weight_markets": 0.15,
    },
    {
        "sector": "Real Estate",
        "weight_fed_policy": 0.35,
        "weight_recession": 0.30,
        "weight_elections": 0.10,
        "weight_trade": 0.05,
        "weight_crypto": 0.00,
        "weight_markets": 0.20,
    },
    {
        "sector": "Utilities",
        "weight_fed_policy": 0.30,
        "weight_recession": 0.15,
        "weight_elections": 0.15,
        "weight_trade": 0.05,
        "weight_crypto": 0.00,
        "weight_markets": 0.35,
    },
    {
        "sector": "Industrials",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.25,
        "weight_elections": 0.10,
        "weight_trade": 0.20,
        "weight_crypto": 0.00,
        "weight_markets": 0.25,
    },
    {
        "sector": "Materials",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.25,
        "weight_elections": 0.10,
        "weight_trade": 0.20,
        "weight_crypto": 0.00,
        "weight_markets": 0.25,
    },
    {
        "sector": "Basic Materials",  # Yahoo Finance variant
        "weight_fed_policy": 0.20,
        "weight_recession": 0.25,
        "weight_elections": 0.10,
        "weight_trade": 0.20,
        "weight_crypto": 0.00,
        "weight_markets": 0.25,
    },
    {
        "sector": "Communication Services",
        "weight_fed_policy": 0.20,
        "weight_recession": 0.20,
        "weight_elections": 0.15,
        "weight_trade": 0.10,
        "weight_crypto": 0.00,
        "weight_markets": 0.35,
    },
]
