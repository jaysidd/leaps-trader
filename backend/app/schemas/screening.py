"""Pydantic response schemas for screening endpoints (v1)."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class CoverageInfoSchema(BaseModel):
    known_count: int
    pass_count: int
    total_count: int


class ComponentAvailability(BaseModel):
    fundamental_available: bool = False
    technical_available: bool = False
    options_available: bool = False
    momentum_available: bool = False
    sentiment_available: bool = False


class LeapsSummarySchema(BaseModel):
    """Subset of LEAPS summary fields surfaced in the result."""
    available: Optional[bool] = None
    atm_option: Optional[Dict[str, Any]] = None
    tastytrade: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class ScreeningResultV1(BaseModel):
    """
    Single-stock screening result (v1).

    All fields except ``symbol`` are Optional so that partial results
    (e.g. a stock that failed at stage 1) still validate.
    """
    # --- identity ---
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    exchange: Optional[str] = None

    # --- pipeline status ---
    screened_at: Optional[str] = None
    passed_stages: List[str] = Field(default_factory=list)
    passed_all: Optional[bool] = None
    failed_at: Optional[str] = None
    error: Optional[str] = None

    # --- sub-scores ---
    fundamental_score: Optional[float] = None
    technical_score: Optional[float] = None          # 0-100 (pct, D3)
    technical_score_points: Optional[float] = None   # 0-90 (points, D3)
    options_score: Optional[float] = None
    momentum_score: Optional[float] = None
    sentiment_score: Optional[float] = None

    # --- composite ---
    score: float = 0
    composite_score: Optional[float] = None          # alias used by calculate_stock_scores

    # --- v1 structured output ---
    criteria: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    coverage: Dict[str, CoverageInfoSchema] = Field(default_factory=dict)
    component_availability: Optional[ComponentAvailability] = None

    # --- price / technical data ---
    current_price: Optional[float] = None
    price_change_percent: Optional[float] = None
    technical_indicators: Optional[Dict[str, Any]] = None

    # --- options data ---
    leaps_available: Optional[bool] = None
    leaps_summary: Optional[Dict[str, Any]] = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None

    # --- momentum ---
    returns: Optional[Dict[str, float]] = None

    # --- sentiment (Phase 2) ---
    sentiment: Optional[Dict[str, Any]] = None
    catalysts: Optional[Dict[str, Any]] = None
    earnings_risk: Optional[bool] = None
    insider_buying: Optional[bool] = None
    has_upgrade: Optional[bool] = None

    # --- backward compat: old criteria dicts ---
    fundamental_criteria: Optional[Dict[str, str]] = None
    technical_criteria: Optional[Dict[str, str]] = None
    options_criteria: Optional[Dict[str, str]] = None

    # --- scan-all-presets tagging ---
    matched_presets: Optional[List[str]] = None
    matched_preset_names: Optional[List[str]] = None

    class Config:
        extra = "allow"


class ScreenResponse(BaseModel):
    """Response wrapper for multi-stock screening endpoints."""
    results: List[ScreeningResultV1]
    total_screened: int
    total_passed: int
