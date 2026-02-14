"""
Market condition presets for PresetSelector tests.

Each dict represents a complete market_snapshot as returned by
PresetSelector._gather_market_snapshot().
"""

BULLISH_MARKET = {
    "mri": 25,
    "mri_regime": "low_risk",
    "regime": "bullish",
    "risk_mode": "risk_on",
    "regime_confidence": 85,
    "fear_greed": 72,
    "readiness": 30,
    "readiness_label": "green",
    "timestamp": "2026-02-13T10:00:00",
}

MODERATE_BULL_MARKET = {
    "mri": 35,
    "mri_regime": "moderate",
    "regime": "bullish",
    "risk_mode": "risk_on",
    "regime_confidence": 70,
    "fear_greed": 55,
    "readiness": 40,
    "readiness_label": "yellow",
    "timestamp": "2026-02-13T10:00:00",
}

NEUTRAL_MARKET = {
    "mri": 45,
    "mri_regime": "moderate",
    "regime": "neutral",
    "risk_mode": "neutral",
    "regime_confidence": 60,
    "fear_greed": 50,
    "readiness": 50,
    "readiness_label": "yellow",
    "timestamp": "2026-02-13T10:00:00",
}

BEARISH_MARKET = {
    "mri": 70,
    "mri_regime": "elevated",
    "regime": "bearish",
    "risk_mode": "risk_off",
    "regime_confidence": 80,
    "fear_greed": 22,
    "readiness": 70,
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

PANIC_MARKET = {
    "mri": 85,
    "mri_regime": "crisis",
    "regime": "bearish",
    "risk_mode": "risk_off",
    "regime_confidence": 95,
    "fear_greed": 8,  # Below 10 = extreme fear trigger
    "readiness": 90,
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

PARTIAL_DATA_MARKET = {
    "mri": None,
    "mri_regime": None,
    "regime": "bullish",
    "risk_mode": "risk_on",
    "regime_confidence": 75,
    "fear_greed": None,  # F&G unavailable
    "readiness": None,
    "readiness_label": None,
    "timestamp": "2026-02-13T10:00:00",
}

ALL_MISSING_MARKET = {
    "mri": None,
    "mri_regime": None,
    "regime": None,
    "risk_mode": None,
    "regime_confidence": None,
    "fear_greed": None,
    "readiness": None,
    "readiness_label": None,
    "timestamp": "2026-02-13T10:00:00",
}

# ---------------------------------------------------------------------------
# Extended snapshots for comprehensive PresetSelector tests
# ---------------------------------------------------------------------------

# Near-panic: MRI > 80 but F&G NOT < 10 → no panic override
NEAR_PANIC_MRI_ONLY = {
    "mri": 85,
    "mri_regime": "crisis",
    "regime": "bearish",
    "risk_mode": "risk_off",
    "regime_confidence": 90,
    "fear_greed": 25,       # Above 10 — no panic trigger
    "readiness": 80,
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

# Near-panic: F&G < 10 but MRI NOT > 80 → no panic override
NEAR_PANIC_FG_ONLY = {
    "mri": 60,              # Below 80 — no panic trigger
    "mri_regime": "elevated",
    "regime": "bearish",
    "risk_mode": "risk_off",
    "regime_confidence": 75,
    "fear_greed": 5,        # Below 10 — but needs MRI > 80 too
    "readiness": 70,
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

# Label fallback: readiness score=None, label="green" → signal=60
LABEL_FALLBACK_GREEN = {
    "mri": 45,
    "mri_regime": "moderate",
    "regime": "neutral",
    "risk_mode": "neutral",
    "regime_confidence": 60,
    "fear_greed": 50,
    "readiness": None,           # Score unavailable
    "readiness_label": "green",  # Fallback to label
    "timestamp": "2026-02-13T10:00:00",
}

# Label fallback: readiness score=None, label="yellow" → signal=0
LABEL_FALLBACK_YELLOW = {
    "mri": 45,
    "mri_regime": "moderate",
    "regime": "neutral",
    "risk_mode": "neutral",
    "regime_confidence": 60,
    "fear_greed": 50,
    "readiness": None,
    "readiness_label": "yellow",
    "timestamp": "2026-02-13T10:00:00",
}

# Label fallback: readiness score=None, label="red" → signal=-60
LABEL_FALLBACK_RED = {
    "mri": 45,
    "mri_regime": "moderate",
    "regime": "neutral",
    "risk_mode": "neutral",
    "regime_confidence": 60,
    "fear_greed": 50,
    "readiness": None,
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

# Max bullish: every signal at maximum → composite ≈ 93.0
MAX_BULLISH_MARKET = {
    "mri": 0,                   # (50-0)*2 = +100
    "mri_regime": "low_risk",
    "regime": "bullish",        # +80 base
    "risk_mode": "risk_on",
    "regime_confidence": 100,   # multiplier = 1.0 → regime signal = 80
    "fear_greed": 100,          # (100-50)*2 = +100
    "readiness": 0,             # (50-0)*2 = +100
    "readiness_label": "green",
    "timestamp": "2026-02-13T10:00:00",
}

# Max bearish: every signal at minimum → composite ≈ -93.0
MAX_BEARISH_MARKET = {
    "mri": 100,                 # (50-100)*2 = -100
    "mri_regime": "crisis",
    "regime": "bearish",        # -80 base
    "risk_mode": "risk_off",
    "regime_confidence": 100,   # multiplier = 1.0 → regime signal = -80
    "fear_greed": 0,            # (0-50)*2 = -100
    "readiness": 100,           # (50-100)*2 = -100
    "readiness_label": "red",
    "timestamp": "2026-02-13T10:00:00",
}

# Boundary: exactly 50.0 composite → aggressive_bull threshold
# Only regime available: bullish * conf=62.5 → signal=80*0.625=50.0
# With only 1 signal, renormalized weight = 1.0, so composite = 50.0
BOUNDARY_AGGRESSIVE = {
    "mri": None,
    "mri_regime": None,
    "regime": "bullish",
    "risk_mode": "risk_on",
    "regime_confidence": 62.5,  # 80 * 0.625 = 50.0 exactly
    "fear_greed": None,
    "readiness": None,
    "readiness_label": None,
    "timestamp": "2026-02-13T10:00:00",
}
