"""
Signal Analysis Prompt Templates for AI Deep Analysis

Adapted from the 21-prompt Trading Prompt Library into 4 composite templates:
1. SIGNAL_REGIME_PROMPT — Regime classifier (from Prompt #20: Regime Selector)
2. TREND_SIGNAL_ANALYSIS_PROMPT — Trending signals (Prompts #1,2,3,7,8,12,16)
3. MEAN_REVERSION_ANALYSIS_PROMPT — Range/oversold signals (Prompts #10,18,19)
4. BATCH_SIGNAL_SCANNER_PROMPT — Multi-signal ranking (Prompt #21)

Each template embeds the relevant mechanics, checklist, and failure modes
from the trading library, adapted for a stock scanner (not a trading bot).
"""

from typing import Dict, Any, List, Optional
import json

# =============================================================================
# SYSTEM PROMPTS (Signal-Specific)
# =============================================================================

SYSTEM_PROMPT_SIGNAL_ANALYST = """You are an elite trading signal analyst specializing in intraday and swing setups for options-focused traders managing $50K-100K portfolios.

Your analysis framework:
- Data-driven: use actual numbers from the signal snapshot, not vague statements
- Risk-first: always assess if the risk/reward justifies the trade
- Strategy-aware: match signals to the correct trading template (ORB, VWAP pullback, breakout, mean reversion)
- Options-literate: consider IV context, earnings proximity, and optimal structure
- Honest: if the setup is marginal, say so — "NO TRADE" is a valid answer

Output format: Always respond in valid JSON. Never include markdown code blocks or text outside the JSON structure.
Never hallucinate options strikes or prices — if chain data is not provided, recommend structure type and delta/DTE range only."""

SYSTEM_PROMPT_REGIME_CLASSIFIER = """You are a market regime classifier. Your only job is to determine if a stock's current setup is trending, mean-reverting, or mixed, based on technical indicators.

Be precise and fast. Always respond in valid JSON. Never include extra text."""

# =============================================================================
# TEMPLATE 1: REGIME CLASSIFICATION (Prompt #20 — Regime Selector)
# =============================================================================

SIGNAL_REGIME_PROMPT = """Classify the current regime for this signal setup.

## Signal: {symbol} ({strategy} / {timeframe})
Direction: {direction}

## Technical Snapshot
- RSI: {rsi}
- EMA8: ${ema8} | EMA21: ${ema21} | SMA50: ${sma50}
- ATR%: {atr_percent}%
- RVOL: {rvol}x
- Volume spike: {volume_spike}

## Institutional Context
- VWAP: ${vwap} | Price vs VWAP: {vwap_position}
- ORB High: ${orb_high} | ORB Low: ${orb_low}
- ADX: {adx}

## Additional Context
- IV Rank: {iv_rank}%
- Days to Earnings: {days_to_earnings}

Classify using these rules:
- TRENDING: ADX > 25 OR (EMA8 > EMA21 > SMA50 for longs, reverse for shorts) AND RVOL > 1.0
- MEAN_REVERSION: ADX < 20 OR RSI extreme (<30 or >70) OR price extended >2 ATR from 20EMA
- MIXED: Neither clearly trending nor mean-reverting

Respond with ONLY this JSON:
{{
    "regime": "trending|mean_reversion|mixed",
    "confidence": <1-10>,
    "strategy_group": "trend|mean_reversion",
    "reasoning": "<one sentence why>"
}}"""

# =============================================================================
# TEMPLATE 2: TREND SIGNAL ANALYSIS
# Incorporates Prompts: #1 (ORB+VWAP), #2 (VWAP Pullback), #3 (HOD/LOD Break),
#                        #7 (Breakout From Base), #8 (Pullback to MA),
#                        #12 (Debit Spread), #16 (Trend Rider Diagonal)
# =============================================================================

TREND_SIGNAL_ANALYSIS_PROMPT = """Analyze this TRENDING signal setup and determine if this is a trade worth taking.

## Signal: {symbol} — {name}
Strategy: {strategy} | Timeframe: {timeframe} | Direction: {direction}
Confidence Score: {confidence_score}/100
Generated: {generated_at}

## Trade Parameters (from Signal Engine)
- Entry Price: ${entry_price}
- Entry Zone: ${entry_zone_low} – ${entry_zone_high}
- Stop Loss: ${stop_loss}
- Target 1: ${target_1} | Target 2: ${target_2}
- Risk/Reward: {risk_reward}

## Technical Snapshot at Signal Time
- RSI: {rsi}
- EMA8: ${ema8} | EMA21: ${ema21} | SMA50: ${sma50}
- ATR%: {atr_percent}%
- RVOL: {rvol}x
- Volume spike: {volume_spike}

## Institutional / Market Structure
- VWAP: ${vwap} | Price vs VWAP: {vwap_position}
- ORB High: ${orb_high} | ORB Low: ${orb_low}
- Range High: ${range_high} | Range Low: ${range_low}
- Market structure: {market_structure}

## Market Regime Context
{regime_context}

## IV & Options Context
- IV Rank: {iv_rank}%
- Days to Earnings: {days_to_earnings}

## AI Reasoning from Signal Engine
{ai_reasoning}

---

## YOUR ANALYSIS FRAMEWORK

Apply the trading library's strategy-matching logic:

**ORB + VWAP Trend Continuation (#1):**
- Mechanics: Break AND close beyond ORH/ORL, trade in H1 trend direction, prefer pullback/retest
- Checklist: Trending day? VWAP supportive? Volume on break > 1.2x avg? RR adequate?
- Failure mode: False breakouts near weekly levels, low liquidity breaks

**VWAP Pullback Trend (#2):**
- Mechanics: Confirm H1 trend, wait for pullback to VWAP/EMA with reduced volume, enter on trigger close
- Checklist: Clear trend? Shallow controlled pullback? Trigger candle confirms? Liquid?
- Failure mode: Late-day parabolic moves that snap back through VWAP

**HOD/LOD Break Momentum (#3):**
- Mechanics: Tight consolidation near HOD/LOD, break with volume expansion in trend direction
- Checklist: Compression before break? Volume expands? Room to next level? VWAP supportive?
- Failure mode: False breaks in low volume or into major weekly resistance

**Breakout From Base (#7):**
- Mechanics: Multi-week base + tightening volatility, breakout with volume/RS
- Checklist: Weekly trend aligned? Base quality? Volume/RS improvement? No earnings trap?
- Failure mode: Breakout into heavy supply; quick reversal back into base

**Pullback-to-MA Continuation (#8):**
- Mechanics: Trend confirmed, pullback to 20/50 EMA with reduced volume, reversal close
- Checklist: Pullback lands in MA zone? Structure (HL/LH) forms? Not late-stage parabolic?
- Failure mode: MA breaks and flips to resistance/support

**Debit Spread (#12) — Options Structure:**
- If trending, prefer defined-risk debit spread to reduce IV exposure
- Long leg delta ~0.45-0.65, sell further OTM to cap cost
- Failure mode: Chop, underlying never follows through, time decay

**Trend Rider Diagonal (#16) — Options Structure:**
- If IV is high, prefer diagonal/calendar to reduce vega
- Sell near-term, buy longer-term for LEAPS exposure
- Failure mode: Chop + time decay overwhelms

---

Match this signal to the BEST fitting strategy template above, then score it.

Respond with ONLY this JSON:
{{
    "conviction": <1-10 integer>,
    "action": "<enter_now|wait_for_pullback|wait_for_trigger|skip>",
    "strategy_match": "<ORB Continuation|VWAP Pullback|Breakout From Base|Pullback to MA|HOD/LOD Break|Mixed>",
    "strategy_fit_score": <0-100>,
    "entry_assessment": {{
        "quality": "<excellent|good|fair|poor>",
        "timing": "<ideal|acceptable|early|late|missed>",
        "reasoning": "<why entry is good/bad>"
    }},
    "risk_assessment": {{
        "stop_quality": "<well_placed|too_tight|too_wide|missing>",
        "risk_reward": "<excellent|good|fair|poor>",
        "position_size_suggestion": "<full|half|quarter|skip>",
        "reasoning": "<risk reasoning>"
    }},
    "targets": {{
        "target_1": {{
            "price": <price or null>,
            "reasoning": "<why this target>"
        }},
        "target_2": {{
            "price": <price or null>,
            "reasoning": "<why this target>"
        }},
        "trail_method": "<swing_points|ema_trail|atr_trail|fixed>"
    }},
    "checklist": {{
        "trend_aligned": <true|false>,
        "volume_confirmed": <true|false>,
        "vwap_supportive": <true|false>,
        "room_to_target": <true|false>,
        "no_event_risk": <true|false>
    }},
    "failure_mode": "<what would invalidate this setup>",
    "options_play": {{
        "structure": "<long_call|debit_spread|diagonal|none>",
        "iv_assessment": "<cheap|fair|expensive>",
        "reasoning": "<why this structure>",
        "suggested_strike_area": "<ATM|slightly_OTM|deep_ITM|N/A>",
        "suggested_dte": "<X-Y days or N/A>"
    }},
    "summary": "<2-3 sentence actionable bottom line. Be specific about what to do and what would change your mind.>"
}}"""

# =============================================================================
# TEMPLATE 3: MEAN REVERSION SIGNAL ANALYSIS
# Incorporates Prompts: #10 (Oversold Bounce), #18 (High IV Mean Reversion),
#                        #19 (Earnings Vol Crush)
# =============================================================================

MEAN_REVERSION_ANALYSIS_PROMPT = """Analyze this MEAN REVERSION / OVERSOLD signal setup and determine if this is a trade worth taking.

## Signal: {symbol} — {name}
Strategy: {strategy} | Timeframe: {timeframe} | Direction: {direction}
Confidence Score: {confidence_score}/100
Generated: {generated_at}

## Trade Parameters (from Signal Engine)
- Entry Price: ${entry_price}
- Entry Zone: ${entry_zone_low} – ${entry_zone_high}
- Stop Loss: ${stop_loss}
- Target 1: ${target_1} | Target 2: ${target_2}
- Risk/Reward: {risk_reward}

## Technical Snapshot at Signal Time
- RSI: {rsi}
- EMA8: ${ema8} | EMA21: ${ema21} | SMA50: ${sma50}
- ATR%: {atr_percent}%
- RVOL: {rvol}x
- Volume spike: {volume_spike}

## Extension from Mean
- Distance from EMA20 in ATR multiples: {ema20_atr_distance}
- Price vs SMA50: {price_vs_sma50}%

## Institutional / Market Structure
- VWAP: ${vwap} | Price vs VWAP: {vwap_position}
- Range High: ${range_high} | Range Low: ${range_low}
- Market structure: {market_structure}

## Market Regime Context
{regime_context}

## IV & Options Context
- IV Rank: {iv_rank}%
- Days to Earnings: {days_to_earnings}

## AI Reasoning from Signal Engine
{ai_reasoning}

---

## YOUR ANALYSIS FRAMEWORK

Apply the trading library's mean-reversion logic:

**Oversold Bounce (#10):**
- Mechanics: Quantify extension (distance below 20EMA in ATR multiples), require stabilization (higher low, strong close, reclaim prior day high, divergence)
- Checklist: Extension unusually large vs ATR? Stabilization signal present? Not a broad market selloff? Target is the mean (20EMA)?
- Failure mode: News-driven downtrend where mean reversion never happens; "mild red" is NOT oversold

**High IV Mean Reversion (#18):**
- Mechanics: IV elevated (high IV rank), defined-risk premium selling aligned with range/MR thesis
- Checklist: IV actually elevated? Defined risk structure? Range/MR thesis has level support? No binary event imminent?
- WARNING: If IV is high, buying LEAPS/long calls is EXPENSIVE — flag this clearly
- Failure mode: IV stays high and price trends through short strike

**Earnings Volatility Crush (#19):**
- Mechanics: Pre-earnings IV inflation, post-earnings IV crush
- If earnings are within 14 days: CRITICAL WARNING about binary event risk
- Checklist: Earnings date confirmed? IV inflated vs normal? Position sized for gap risk?
- Failure mode: Earnings surprise larger than expected move → gap through strikes

---

Match this signal to the BEST fitting mean-reversion template, then score it.

Respond with ONLY this JSON:
{{
    "conviction": <1-10 integer>,
    "action": "<enter_now|wait_for_stabilization|wait_for_trigger|skip>",
    "strategy_match": "<Oversold Bounce|High IV Mean Reversion|Earnings Play|Range Fade|Mixed>",
    "strategy_fit_score": <0-100>,
    "entry_assessment": {{
        "quality": "<excellent|good|fair|poor>",
        "timing": "<ideal|acceptable|early|late|missed>",
        "reasoning": "<why entry is good/bad>"
    }},
    "risk_assessment": {{
        "stop_quality": "<well_placed|too_tight|too_wide|missing>",
        "risk_reward": "<excellent|good|fair|poor>",
        "position_size_suggestion": "<full|half|quarter|skip>",
        "reasoning": "<risk reasoning>"
    }},
    "targets": {{
        "target_1": {{
            "price": <price or null>,
            "reasoning": "<why this target>"
        }},
        "target_2": {{
            "price": <price or null>,
            "reasoning": "<why this target>"
        }},
        "trail_method": "<mean_revert_exit|swing_points|ema_trail|time_stop>"
    }},
    "checklist": {{
        "extended_from_mean": <true|false>,
        "stabilization_signal": <true|false>,
        "no_trend_day": <true|false>,
        "iv_context_favorable": <true|false>,
        "no_binary_event": <true|false>
    }},
    "failure_mode": "<what would invalidate this setup>",
    "options_play": {{
        "structure": "<long_call|debit_spread|credit_spread|iron_condor|diagonal|none>",
        "iv_assessment": "<cheap|fair|expensive|WARNING_elevated>",
        "reasoning": "<why this structure — especially flag if IV makes long calls expensive>",
        "suggested_strike_area": "<ATM|slightly_OTM|deep_ITM|N/A>",
        "suggested_dte": "<X-Y days or N/A>"
    }},
    "earnings_warning": "<null if no earnings risk, otherwise specific warning about binary event>",
    "summary": "<2-3 sentence actionable bottom line. Be specific about what to do and what would change your mind.>"
}}"""

# =============================================================================
# TEMPLATE 4: BATCH SIGNAL SCANNER (Prompt #21 — Multi-Symbol Scanner)
# =============================================================================

BATCH_SIGNAL_SCANNER_PROMPT = """Rank these trading signals and identify the BEST setup worth taking.

## Market Regime
{regime_context}

## Signals to Analyze

{signals_data}

---

## YOUR ANALYSIS FRAMEWORK (from Trading Library Prompt #21)

For each signal, quickly assess:
1. Strategy fit: Does the signal match its claimed strategy template?
2. Quality gates: Trend aligned? Volume confirmed? VWAP supportive? Room to target?
3. IV context: Is options pricing favorable or a warning?
4. Event risk: Any earnings/catalysts that add binary risk?

Rules:
- Rank by overall quality, not just confidence score
- Exclude signals with missing critical data or broken setups
- "NO TRADE" is valid if all signals are marginal
- The best setup should be clearly better than alternatives, not just "least bad"
- Maximum 5 signals analyzed

Respond with ONLY this JSON:
{{
    "batch_quality": "<poor|fair|good|excellent>",
    "quality_assessment": "<one sentence about overall signal quality today>",
    "ranked_signals": [
        {{
            "rank": <1-N>,
            "signal_id": <id>,
            "symbol": "<ticker>",
            "conviction": <1-10>,
            "action": "<enter_now|wait|skip>",
            "strategy_match": "<best fitting template>",
            "checklist_passed": <number of 5 quality gates passed>,
            "one_liner": "<20 word max summary>"
        }}
    ],
    "best_setup": {{
        "signal_id": <id of best signal or null>,
        "symbol": "<ticker or null>",
        "why_best": "<why this is the top pick>",
        "key_risk": "<main risk for the top pick>"
    }},
    "signals_to_skip": [
        {{
            "signal_id": <id>,
            "symbol": "<ticker>",
            "reason": "<why skip>"
        }}
    ],
    "summary": "<2-3 sentence executive summary of today's signal quality and the best opportunity.>"
}}"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_signal_for_analysis(signal_dict: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract and format signal data for prompt template variables.

    Takes a TradingSignal.to_dict() output and returns a flat dict
    of template-ready values with safe defaults.
    """
    tech = signal_dict.get("technical_snapshot") or {}
    inst = signal_dict.get("institutional_data") or {}
    entry_zone = signal_dict.get("entry_zone") or {}

    return {
        "symbol": signal_dict.get("symbol", "UNKNOWN"),
        "name": signal_dict.get("name") or signal_dict.get("symbol", "UNKNOWN"),
        "strategy": signal_dict.get("strategy", "unknown"),
        "timeframe": signal_dict.get("timeframe", "unknown"),
        "direction": signal_dict.get("direction", "unknown"),
        "confidence_score": _fmt_num(signal_dict.get("confidence_score"), "N/A"),
        "generated_at": signal_dict.get("generated_at", "N/A"),
        # Trade params
        "entry_price": _fmt_price(signal_dict.get("entry_price")),
        "entry_zone_low": _fmt_price(entry_zone.get("low") if isinstance(entry_zone, dict) else signal_dict.get("entry_zone_low")),
        "entry_zone_high": _fmt_price(entry_zone.get("high") if isinstance(entry_zone, dict) else signal_dict.get("entry_zone_high")),
        "stop_loss": _fmt_price(signal_dict.get("stop_loss")),
        "target_1": _fmt_price(signal_dict.get("target_1")),
        "target_2": _fmt_price(signal_dict.get("target_2")),
        "risk_reward": _fmt_num(signal_dict.get("risk_reward_ratio"), "N/A"),
        # Technical snapshot
        "rsi": _fmt_num(tech.get("rsi"), "N/A"),
        "ema8": _fmt_price(tech.get("ema8")),
        "ema21": _fmt_price(tech.get("ema21")),
        "sma50": _fmt_price(tech.get("sma50") or tech.get("sma_50")),
        "atr_percent": _fmt_num(tech.get("atr_percent"), "N/A"),
        "rvol": _fmt_num(tech.get("rvol"), "N/A"),
        "volume_spike": str(tech.get("volume_spike", "N/A")),
        # Institutional / structure
        "vwap": _fmt_price(inst.get("vwap")),
        "vwap_position": inst.get("vwap_position", "N/A"),
        "orb_high": _fmt_price(inst.get("opening_range_high") or inst.get("orb_high")),
        "orb_low": _fmt_price(inst.get("opening_range_low") or inst.get("orb_low")),
        "range_high": _fmt_price(inst.get("range_high")),
        "range_low": _fmt_price(inst.get("range_low")),
        "market_structure": inst.get("market_structure", "N/A"),
        "adx": _fmt_num(tech.get("adx") or inst.get("adx"), "N/A"),
        # AI reasoning from signal engine
        "ai_reasoning": signal_dict.get("ai_reasoning") or "No signal engine reasoning available.",
    }


def format_regime_context(regime: Optional[Dict[str, Any]]) -> str:
    """Format market regime into context string for prompts."""
    if not regime:
        return "Market regime: Not analyzed"

    parts = [
        f"Regime: {regime.get('regime', 'unknown').title()}",
        f"Risk Mode: {regime.get('risk_mode', 'unknown')}",
        f"Confidence: {regime.get('confidence', 'N/A')}/10",
        f"VIX: {regime.get('vix', 'N/A')}",
        f"Trading Stance: {regime.get('trading_stance', 'normal')}",
    ]
    summary = regime.get("summary")
    if summary:
        parts.append(f"Summary: {summary}")

    return " | ".join(parts)


def format_signal_for_batch(signal_dict: Dict[str, Any], index: int) -> str:
    """Format a single signal as a compact text block for batch analysis."""
    tech = signal_dict.get("technical_snapshot") or {}
    inst = signal_dict.get("institutional_data") or {}

    lines = [
        f"### Signal #{index} (ID: {signal_dict.get('id', 'N/A')})",
        f"Symbol: {signal_dict.get('symbol', 'N/A')} | Strategy: {signal_dict.get('strategy', 'N/A')} | "
        f"Timeframe: {signal_dict.get('timeframe', 'N/A')} | Direction: {signal_dict.get('direction', 'N/A')}",
        f"Confidence: {_fmt_num(signal_dict.get('confidence_score'), 'N/A')}/100 | "
        f"Entry: ${_fmt_price(signal_dict.get('entry_price'))} | Stop: ${_fmt_price(signal_dict.get('stop_loss'))} | "
        f"Target 1: ${_fmt_price(signal_dict.get('target_1'))} | R:R: {_fmt_num(signal_dict.get('risk_reward_ratio'), 'N/A')}",
        f"RSI: {_fmt_num(tech.get('rsi'), 'N/A')} | ATR%: {_fmt_num(tech.get('atr_percent'), 'N/A')}% | "
        f"RVOL: {_fmt_num(tech.get('rvol'), 'N/A')}x | VWAP: ${_fmt_price(inst.get('vwap'))} ({inst.get('vwap_position', 'N/A')})",
    ]

    # Add IV/earnings if available
    iv_rank = signal_dict.get("_iv_rank")
    earnings = signal_dict.get("_days_to_earnings")
    if iv_rank is not None or earnings is not None:
        lines.append(
            f"IV Rank: {_fmt_num(iv_rank, 'N/A')}% | Days to Earnings: {earnings or 'N/A'}"
        )

    reasoning = signal_dict.get("ai_reasoning")
    if reasoning:
        # Truncate long reasoning for batch
        short = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
        lines.append(f"Signal Reasoning: {short}")

    return "\n".join(lines)


def build_regime_prompt(signal_dict: Dict[str, Any], iv_rank: Optional[float] = None,
                        days_to_earnings: Optional[int] = None) -> str:
    """Build the regime classification prompt from signal data."""
    data = format_signal_for_analysis(signal_dict)
    data["iv_rank"] = _fmt_num(iv_rank, "N/A")
    data["days_to_earnings"] = str(days_to_earnings) if days_to_earnings is not None else "N/A"
    return SIGNAL_REGIME_PROMPT.format(**data)


def build_trend_analysis_prompt(
    signal_dict: Dict[str, Any],
    regime: Optional[Dict[str, Any]] = None,
    iv_rank: Optional[float] = None,
    days_to_earnings: Optional[int] = None,
) -> str:
    """Build the full trend signal analysis prompt."""
    data = format_signal_for_analysis(signal_dict)
    data["regime_context"] = format_regime_context(regime)
    data["iv_rank"] = _fmt_num(iv_rank, "N/A")
    data["days_to_earnings"] = str(days_to_earnings) if days_to_earnings is not None else "N/A"
    return TREND_SIGNAL_ANALYSIS_PROMPT.format(**data)


def build_mean_reversion_prompt(
    signal_dict: Dict[str, Any],
    regime: Optional[Dict[str, Any]] = None,
    iv_rank: Optional[float] = None,
    days_to_earnings: Optional[int] = None,
) -> str:
    """Build the full mean-reversion signal analysis prompt."""
    data = format_signal_for_analysis(signal_dict)
    data["regime_context"] = format_regime_context(regime)
    data["iv_rank"] = _fmt_num(iv_rank, "N/A")
    data["days_to_earnings"] = str(days_to_earnings) if days_to_earnings is not None else "N/A"

    # Compute extension from mean
    tech = signal_dict.get("technical_snapshot") or {}
    entry = signal_dict.get("entry_price") or 0
    ema21 = tech.get("ema21") or tech.get("ema_21") or 0
    atr_pct = tech.get("atr_percent") or 0
    sma50 = tech.get("sma50") or tech.get("sma_50") or 0

    if entry and ema21 and atr_pct and atr_pct > 0:
        atr_dollar = entry * (atr_pct / 100)
        distance = abs(entry - ema21) / atr_dollar if atr_dollar > 0 else 0
        data["ema20_atr_distance"] = f"{distance:.1f}"
    else:
        data["ema20_atr_distance"] = "N/A"

    if entry and sma50 and sma50 > 0:
        pct_diff = ((entry - sma50) / sma50) * 100
        data["price_vs_sma50"] = f"{pct_diff:+.1f}"
    else:
        data["price_vs_sma50"] = "N/A"

    return MEAN_REVERSION_ANALYSIS_PROMPT.format(**data)


def build_batch_scanner_prompt(
    signals: List[Dict[str, Any]],
    regime: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the batch signal scanner prompt for up to 5 signals."""
    # Limit to 5 signals
    signals_to_analyze = signals[:5]

    signal_blocks = []
    for i, sig in enumerate(signals_to_analyze, 1):
        signal_blocks.append(format_signal_for_batch(sig, i))

    signals_text = "\n\n".join(signal_blocks)

    return BATCH_SIGNAL_SCANNER_PROMPT.format(
        regime_context=format_regime_context(regime),
        signals_data=signals_text,
    )


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_signal_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a signal analysis response (trend or MR)."""
    # Clamp conviction 1-10
    if "conviction" in data:
        data["conviction"] = max(1, min(10, int(data.get("conviction", 5))))

    # Normalize action
    valid_actions = ["enter_now", "wait_for_pullback", "wait_for_trigger",
                     "wait_for_stabilization", "skip"]
    if data.get("action") not in valid_actions:
        data["action"] = "skip"

    # Clamp strategy_fit_score 0-100
    if "strategy_fit_score" in data:
        data["strategy_fit_score"] = max(0, min(100, int(data.get("strategy_fit_score", 50))))

    # Ensure checklist is a dict
    if not isinstance(data.get("checklist"), dict):
        data["checklist"] = {}

    # Ensure options_play is a dict
    if not isinstance(data.get("options_play"), dict):
        data["options_play"] = {
            "structure": "none",
            "iv_assessment": "N/A",
            "reasoning": "Insufficient data for options recommendation",
        }

    # Ensure summary exists
    if not data.get("summary"):
        data["summary"] = "Analysis complete. Review details above."

    return data


def validate_batch_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a batch scanner response."""
    valid_qualities = ["poor", "fair", "good", "excellent"]
    if data.get("batch_quality") not in valid_qualities:
        data["batch_quality"] = "fair"

    # Ensure ranked_signals is a list
    if not isinstance(data.get("ranked_signals"), list):
        data["ranked_signals"] = []

    # Clamp convictions in ranked signals
    for sig in data.get("ranked_signals", []):
        if "conviction" in sig:
            sig["conviction"] = max(1, min(10, int(sig.get("conviction", 5))))

    return data


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _fmt_price(val) -> str:
    """Format a price value or return 'N/A'."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_num(val, default: str = "N/A") -> str:
    """Format a numeric value or return default."""
    if val is None:
        return default
    try:
        num = float(val)
        # If integer-like, format without decimals
        if num == int(num) and abs(num) < 10000:
            return str(int(num))
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return default
