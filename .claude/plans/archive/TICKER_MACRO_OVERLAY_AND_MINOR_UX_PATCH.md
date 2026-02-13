# TICKER_MACRO_OVERLAY_AND_MINOR_UX_PATCH.md
## Applies on top of: Macro Intelligence V2 + Current UI Implementation
## Priority: Medium (UX + Feature Completion)

This document defines:
1) Minor UX improvements to the Macro Intelligence page
2) The design and behavior of the **Ticker-level Macro Overlay**

No new catalysts are introduced here.
No backend refactors are required beyond new read-only endpoints.

---

# PART A — Minor UX Improvements (Low Effort, High ROI)

## A1. Liquidity Trend (7D) Empty State

### Current State
- Displays: “No historical data available”

### Required Change
Replace empty state message with:

> “Trend will appear after 2–3 data points (expected within 24–48 hours).”

### Rationale
- Reassures users the system is warming up
- Prevents false bug reports
- Sets correct expectation for time-series behavior

---

## A2. Trade Readiness Visual Emphasis

### Goal
Trade Readiness should visually dominate over MRI on the Macro Intelligence page.

### Required Adjustments (choose one or more)
- Slightly thicker ring on Trade Readiness gauge
- Slight glow or accent border
- Maintain left-most positioning (already correct)

### Rationale
- Trade Readiness answers: “Can I act now?”
- MRI answers: “What regime are we in?”
- Actionability should lead.

---

## A3. Confidence Color Semantics (Optional but Recommended)

### Suggested Mapping
- Confidence < 40% → gray / muted amber
- 40–70% → yellow
- >70% → green

### Rationale
Prevents over-weighting low-confidence signals while preserving visibility.

---

# PART B — Ticker-Level “Macro Overlay” Design

## Purpose
Provide **macro-aware context directly on the stock detail page**, without forcing users to open the full Macro Intelligence dashboard.

The overlay answers:
> “Does the current macro environment support this ticker *right now*?”

---

## Placement

### Location
- Stock Detail page
- Position: **above technical indicators**, below price/summary header

### Visibility Rule
- Always visible
- Compact by default
- Expandable for details

---

## Core Components (Required)

### 1. Macro Bias Badge

**Display**
- Label: `Macro Bias`
- Values:
  - Bullish
  - Neutral
  - Bearish

**Color**
- Green / Yellow / Red

**Computation**
