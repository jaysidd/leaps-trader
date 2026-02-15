# PresetSelector Test Cases

## Overview

The `PresetSelector` is the "conductor's brain" of the autopilot pipeline (Layer 1). It reads cached market intelligence signals -- MRI (Macro Risk Index), market regime, Fear & Greed, and trade readiness -- and computes a weighted composite score on a -100 to +100 scale. That score is classified into one of six market conditions (`aggressive_bull`, `moderate_bull`, `neutral`, `cautious`, `defensive`, `skip`), each of which maps to a set of screening presets.

These tests matter because:
- **Incorrect classification** causes the system to scan with wrong presets (aggressive in a bear market, or defensive in a bull run).
- **Weight re-normalization bugs** cause missing signals to distort the composite instead of scaling gracefully.
- **Boundary errors** cause flickering between conditions on consecutive runs.
- **Panic override bugs** either miss true emergencies or trigger false halts.

Source file: `backend/app/services/automation/preset_selector.py`
Test file: `backend/tests/pipeline/test_layer1_preset_selector.py`
Mock data: `backend/tests/pipeline/mock_market.py`

---

## Signal Normalization Formulas

Each raw market signal is normalized to a **-100 to +100** scale where positive = bullish, negative = bearish.

### Regime Signal
```
raw = {"bullish": +80, "neutral": 0, "bearish": -80}.get(regime, 0)
confidence_multiplier = min(confidence / 100.0, 1.0)  if confidence is not None  else 0.7
signal = raw * confidence_multiplier
```
- Range: -80 to +80 (capped by the raw map, not by confidence)
- `None` regime produces `signal = None` (signal excluded entirely)
- `None` confidence defaults multiplier to 0.7

### MRI Signal (inverted)
```
signal = (50 - mri) * 2
```
- MRI 0 (lowest risk) = +100 (max bullish)
- MRI 50 (neutral) = 0
- MRI 100 (crisis) = -100 (max bearish)
- `None` MRI produces `signal = None`

### Fear & Greed Signal (direct)
```
signal = (fear_greed - 50) * 2
```
- F&G 0 (extreme fear) = -100
- F&G 50 (neutral) = 0
- F&G 100 (extreme greed) = +100
- `None` F&G produces `signal = None`

### Readiness Signal (inverted, with label fallback)
```
if readiness is not None:
    signal = (50 - readiness) * 2
elif readiness_label is not None:
    signal = {"green": 60, "yellow": 0, "red": -60}.get(readiness_label, 0)
else:
    signal = None
```
- Readiness 0 (green / best) = +100
- Readiness 50 (neutral) = 0
- Readiness 100 (red / worst) = -100
- Label fallback: `green` = +60, `yellow` = 0, `red` = -60
- Both `None` produces `signal = None`

---

## Signal Weights

```python
SIGNAL_WEIGHTS = {
    "regime":      0.35,   # Most reliable directional signal
    "mri":         0.30,   # Macro headwinds/tailwinds
    "fear_greed":  0.20,   # Sentiment gauge
    "readiness":   0.15,   # Catalyst/liquidity composite
}
# Sum = 1.00
```

When signals are missing, the remaining weights are **re-normalized proportionally**:
```
normalized_weight_i = weight_i / sum(available_weights)
```
Example: if only `regime` (0.35) and `mri` (0.30) are available, their normalized weights become `0.35/0.65 = 0.5385` and `0.30/0.65 = 0.4615`.

---

## Condition Thresholds

| Composite Score    | Condition         | Presets                                            | Max Pos |
|--------------------|-------------------|----------------------------------------------------|---------|
| >= 50              | `aggressive_bull` | `aggressive`, `growth_leaps`, `swing_momentum`     | 2       |
| >= 20 (and < 50)   | `moderate_bull`   | `moderate`, `blue_chip_leaps`, `swing_breakout`    | 2       |
| >= 0 (and < 20)    | `neutral`         | `moderate`, `low_iv_entry`, `deep_value`           | 1       |
| >= -20 (and < 0)   | `cautious`        | `conservative`, `blue_chip_leaps`                  | 1       |
| >= -50 (and < -20) | `defensive`       | `conservative`                                     | 1       |
| < -50              | `skip`            | *(none)*                                           | 0       |

**Hard override**: If `mri > 80 AND fear_greed < 10`, condition is forced to `skip` regardless of composite score. This is the only single-signal veto in the system.

---

## Bugs Fixed (B1-B5)

| #  | Bug Description                                    | Fix Applied                                        | File / Location                  |
|----|----------------------------------------------------|----------------------------------------------------|----------------------------------|
| B1 | `value_deep` preset name (typo)                    | Renamed to `deep_value` in MARKET_CONDITIONS       | `preset_selector.py` line 42     |
| B2 | Cache TTL was 10 minutes (too stale for fast markets) | Reduced to 5 minutes for regime and F&G caches   | `preset_selector.py` line 162    |
| B3 | `confidence=0` treated as falsy (skipped)          | Changed guard to `confidence is not None`          | `preset_selector.py` line 224    |
| B4 | Docstring claimed "no API calls" (inaccurate)      | Updated to describe stale-cache Alpaca fallback    | `preset_selector.py` line 132    |
| B5 | Silent fallback on all-missing data (unsafe auto)  | Fail-fast in auto mode; returns `skip` condition   | `preset_selector.py` line 272    |

---

## Test Categories

### P0 -- Boundary Classification (PS-U01)

These tests verify that the score-to-condition classifier produces the correct result at every threshold boundary. Each boundary is tested at the exact threshold value and at +/- epsilon.

| ID       | Description                              | Input (score, snapshot)                   | Expected Condition  | Rationale                                                                 |
|----------|------------------------------------------|-------------------------------------------|---------------------|---------------------------------------------------------------------------|
| PS-U01a  | Score exactly 50.0                       | `score=50.0, snapshot=BULLISH_MARKET`     | `aggressive_bull`   | Score >= 50 is the aggressive threshold; boundary must be inclusive.       |
| PS-U01b  | Score 49.9 (just below aggressive)       | `score=49.9, snapshot=MODERATE_BULL_MARKET` | `moderate_bull`   | 49.9 < 50 must fall to the next tier.                                     |
| PS-U01c  | Score 80.0 (well above aggressive)       | `score=80.0, snapshot=BULLISH_MARKET`     | `aggressive_bull`   | High scores must remain aggressive, no upper cap.                         |
| PS-U01d  | Score exactly 20.0                       | `score=20.0, snapshot=MODERATE_BULL_MARKET` | `moderate_bull`   | Score >= 20 is the moderate_bull threshold; boundary must be inclusive.    |
| PS-U01e  | Score 19.9 (just below moderate_bull)    | `score=19.9, snapshot=NEUTRAL_MARKET`     | `neutral`           | 19.9 < 20 must fall to neutral.                                          |
| PS-U01f  | Score exactly 0.0                        | `score=0.0, snapshot=NEUTRAL_MARKET`      | `neutral`           | Score >= 0 is neutral threshold; boundary must be inclusive.              |
| PS-U01g  | Score -0.1 (just below neutral)          | `score=-0.1, snapshot=BEARISH_MARKET`     | `cautious`          | Negative scores below 0 enter cautious zone.                             |
| PS-U01h  | Score exactly -20.0                      | `score=-20.0, snapshot=BEARISH_MARKET`    | `cautious`          | Score >= -20 is cautious threshold; boundary must be inclusive.           |
| PS-U01i  | Score -20.1 (just below cautious)        | `score=-20.1, snapshot=BEARISH_MARKET`    | `defensive`         | -20.1 < -20 must fall to defensive.                                      |
| PS-U01j  | Score exactly -50.0                      | `score=-50.0, snapshot=BEARISH_MARKET`    | `defensive`         | Score >= -50 is defensive threshold; boundary must be inclusive.          |
| PS-U01k  | Score -50.1 (just below defensive)       | `score=-50.1, snapshot=BEARISH_MARKET`    | `skip`              | -50.1 < -50 triggers skip (no scanning).                                 |
| PS-U01l  | Score -100.0 (theoretical minimum)       | `score=-100.0, snapshot=BEARISH_MARKET`   | `skip`              | Extreme negative score must map to skip.                                  |

**Implementation pattern:**
```python
def test_PS_U01a(selector):
    result = selector._classify_condition(50.0, BULLISH_MARKET)
    assert result == "aggressive_bull"
```

---

### P0 -- Confidence Scaling (PS-U02)

These tests verify that the regime confidence multiplier is applied correctly.

| ID       | Description                              | Input                                         | Expected Signal       | Rationale                                                               |
|----------|------------------------------------------|-----------------------------------------------|-----------------------|-------------------------------------------------------------------------|
| PS-U02a  | Full confidence (100%)                   | `regime="bullish", confidence=100`            | `regime_signal = 80.0`  | `80 * min(100/100, 1.0) = 80 * 1.0 = 80.0`                           |
| PS-U02b  | Moderate confidence (70%)                | `regime="bullish", confidence=70`             | `regime_signal = 56.0`  | `80 * 0.70 = 56.0`                                                    |
| PS-U02c  | Zero confidence (0%)                     | `regime="bullish", confidence=0`              | `regime_signal = 0.0`   | `80 * min(0/100, 1.0) = 80 * 0.0 = 0.0`. Bug B3 fixed this.          |
| PS-U02d  | Confidence > 100 (capped)               | `regime="bullish", confidence=150`            | `regime_signal = 80.0`  | `80 * min(150/100, 1.0) = 80 * 1.0 = 80.0`. Clamp prevents over-scaling. |
| PS-U02e  | `None` confidence (default 0.7)          | `regime="bullish", confidence=None`           | `regime_signal = 56.0`  | `80 * 0.7 = 56.0`. Default multiplier applied.                        |
| PS-U02f  | Bearish with full confidence             | `regime="bearish", confidence=100`            | `regime_signal = -80.0` | `-80 * 1.0 = -80.0`. Negative raw scales correctly.                   |
| PS-U02g  | Neutral regime (any confidence)          | `regime="neutral", confidence=85`             | `regime_signal = 0.0`   | `0 * 0.85 = 0.0`. Neutral raw is zero; confidence irrelevant.         |

**Implementation pattern:**
```python
def test_PS_U02a(selector):
    snapshot = {**NEUTRAL_MARKET, "regime": "bullish", "regime_confidence": 100}
    _, signals = selector._compute_composite_score(snapshot)
    assert signals["regime"] == 80.0
```

---

### P0 -- Weight Re-normalization (PS-U03)

These tests verify that when signals are missing, remaining weights are re-normalized proportionally so the composite stays on the -100 to +100 scale.

| ID       | Description                              | Available Signals                        | Expected Behavior                                                           | Rationale                                                               |
|----------|------------------------------------------|------------------------------------------|-----------------------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-U03a  | All 4 signals present                    | regime, mri, fg, readiness               | Weights used as-is (0.35, 0.30, 0.20, 0.15). Sum=1.0.                       | Baseline: no re-normalization needed.                                   |
| PS-U03b  | Only regime available                    | regime                                   | Regime gets normalized weight `0.35/0.35 = 1.0`. Composite = regime signal. | Single signal must carry full weight.                                   |
| PS-U03c  | Regime + MRI only                        | regime, mri                              | Weights become `0.35/0.65 = 0.5385` and `0.30/0.65 = 0.4615`.               | Two signals share weight proportionally.                                |
| PS-U03d  | MRI + F&G only (no regime)               | mri, fg                                  | Weights become `0.30/0.50 = 0.60` and `0.20/0.50 = 0.40`.                   | Non-regime signals still compute correctly.                             |
| PS-U03e  | All signals missing                      | *(none)*                                 | `available_weight = 0`, composite returns `0.0`.                             | Zero-division guard: no signals = neutral fallback.                     |
| PS-U03f  | Three signals present (no readiness)     | regime, mri, fg                          | Weights become `0.35/0.85`, `0.30/0.85`, `0.20/0.85`.                        | Most common partial scenario (readiness often slow to cache).           |

**Implementation pattern (PS-U03b):**
```python
def test_PS_U03b(selector):
    snapshot = {**ALL_MISSING_MARKET, "regime": "bullish", "regime_confidence": 75}
    score, signals = selector._compute_composite_score(snapshot)
    # regime signal = 80 * 0.75 = 60.0
    # only signal, so normalized weight = 1.0
    assert score == 60.0
    assert signals["regime"] == 60.0
    assert signals["mri"] is None
    assert signals["fear_greed"] is None
    assert signals["readiness"] is None
```

---

### P0 -- Readiness Label Fallback (PS-U04)

These tests verify the fallback path when `readiness` score is `None` but `readiness_label` is available.

| ID       | Description                              | Input                                       | Expected Signal        | Rationale                                                               |
|----------|------------------------------------------|---------------------------------------------|------------------------|-------------------------------------------------------------------------|
| PS-U04a  | Label "green", score None                | `readiness=None, readiness_label="green"`   | `readiness_signal = 60`  | Green label = bullish proxy, mapped to +60.                            |
| PS-U04b  | Label "yellow", score None               | `readiness=None, readiness_label="yellow"`  | `readiness_signal = 0`   | Yellow label = neutral proxy, mapped to 0.                             |
| PS-U04c  | Label "red", score None                  | `readiness=None, readiness_label="red"`     | `readiness_signal = -60` | Red label = bearish proxy, mapped to -60.                              |
| PS-U04d  | Unknown label, score None                | `readiness=None, readiness_label="unknown"` | `readiness_signal = 0`   | Unknown labels default to 0 via `.get()` fallback.                     |
| PS-U04e  | Score present overrides label            | `readiness=30, readiness_label="red"`       | `readiness_signal = 40`  | Numeric score takes precedence: `(50-30)*2 = 40`. Label ignored.       |

**Implementation pattern (PS-U04a):**
```python
def test_PS_U04a(selector):
    _, signals = selector._compute_composite_score(LABEL_FALLBACK_GREEN)
    assert signals["readiness"] == 60
```

---

### P0 -- Panic Override (PS-S01/S02)

These tests verify the hard override: `mri > 80 AND fear_greed < 10` forces `skip` regardless of composite score.

| ID       | Description                              | Input                                           | Expected Condition  | Rationale                                                               |
|----------|------------------------------------------|-------------------------------------------------|---------------------|-------------------------------------------------------------------------|
| PS-S01a  | Both triggers active (mri=85, fg=8)      | `score=30.0, PANIC_MARKET`                      | `skip`              | Positive score overridden by panic. Both conditions met.                |
| PS-S01b  | Both triggers active, score=+80          | `score=80.0, PANIC_MARKET`                      | `skip`              | Even extremely bullish score cannot override panic.                     |
| PS-S01c  | Exact boundary: mri=81, fg=9             | `score=0.0, snapshot(mri=81, fg=9)`             | `skip`              | Boundary: mri > 80 (not >=) and fg < 10 (not <=). Both just trigger.   |
| PS-S01d  | Exact boundary: mri=80, fg=9             | `score=0.0, snapshot(mri=80, fg=9)`             | `neutral`           | mri=80 does NOT trigger (strictly > 80). No override.                  |
| PS-S01e  | Exact boundary: mri=81, fg=10            | `score=0.0, snapshot(mri=81, fg=10)`            | `neutral`           | fg=10 does NOT trigger (strictly < 10). No override.                   |
| PS-S02a  | High MRI only (mri=85, fg=25)            | `score=-10.0, NEAR_PANIC_MRI_ONLY`              | `cautious`          | Only MRI is extreme; both conditions required for panic.                |
| PS-S02b  | Low F&G only (mri=60, fg=5)              | `score=-10.0, NEAR_PANIC_FG_ONLY`               | `cautious`          | Only F&G is extreme; both conditions required for panic.                |
| PS-S02c  | MRI is None, fg=5                        | `score=-60.0, snapshot(mri=None, fg=5)`          | `skip`              | mri is None so panic check is `False`; skip comes from score < -50.    |
| PS-S02d  | F&G is None, mri=85                      | `score=-10.0, snapshot(mri=85, fg=None)`         | `cautious`          | fg is None so panic check is `False`; classified by score alone.        |
| PS-S02e  | Both None                                | `score=0.0, ALL_MISSING_MARKET`                  | `neutral`           | Both None = no panic check possible; score-based classification.        |

**Implementation pattern (PS-S01c):**
```python
def test_PS_S01c(selector):
    snapshot = {**BEARISH_MARKET, "mri": 81, "fear_greed": 9}
    result = selector._classify_condition(0.0, snapshot)
    assert result == "skip"
```

**Implementation pattern (PS-S01d):**
```python
def test_PS_S01d(selector):
    snapshot = {**BEARISH_MARKET, "mri": 80, "fear_greed": 9}
    result = selector._classify_condition(0.0, snapshot)
    assert result == "neutral"  # mri=80 is NOT > 80
```

---

### P0 -- Mapping Correctness (PS-C01/C02/C03)

These tests verify the static `MARKET_CONDITIONS` dictionary is correct and complete.

| ID       | Description                              | What is Checked                                         | Expected                                                    | Rationale                                                               |
|----------|------------------------------------------|---------------------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-C01   | All 6 conditions have required keys      | Each entry has `presets`, `max_positions`, `description` | All keys present, `presets` is a list, `max_positions` is int | Structural integrity of the mapping dict.                               |
| PS-C02   | `skip` maps to empty presets, 0 positions | `MARKET_CONDITIONS["skip"]`                             | `presets == []`, `max_positions == 0`                        | Skip must produce zero scanning activity.                               |
| PS-C03   | **Contract test**: every preset name in MARKET_CONDITIONS exists in `LEAPS_PRESETS` | Cross-reference all preset names against the catalog | No missing presets | This is the critical integration contract. A typo here (like B1 `value_deep`) causes runtime `KeyError` during scanning. |

**Implementation pattern (PS-C03):**
```python
def test_PS_C03():
    from app.data.presets_catalog import LEAPS_PRESETS
    for condition, mapping in MARKET_CONDITIONS.items():
        for preset_name in mapping["presets"]:
            assert preset_name in LEAPS_PRESETS, (
                f"Preset '{preset_name}' in condition '{condition}' "
                f"not found in LEAPS_PRESETS catalog"
            )
```

---

### P0 -- Cache Behavior (PS-INT01-04)

These are async integration tests for `_gather_market_snapshot()`. They require mocking the four data providers.

| ID        | Description                              | Setup                                                    | Expected                                                    | Rationale                                                               |
|-----------|------------------------------------------|----------------------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-INT01  | All providers return data                | Mock all 4 providers with valid responses                | Snapshot has all 8 fields populated, no `None` values        | Happy path: all caches warm.                                            |
| PS-INT02  | MRI provider raises exception            | `get_cached_mri()` raises `RuntimeError`                 | `mri=None`, `mri_regime=None`; other fields populated        | Single provider failure must not crash the whole method.                 |
| PS-INT03  | All providers raise exceptions           | All 4 providers raise                                    | All fields `None` except `timestamp`                         | Total failure produces empty snapshot, not an exception.                 |
| PS-INT04  | Regime cache stale, fresh fetch succeeds | `detector._cache_time` older than 5 minutes              | Fresh regime data fetched via `get_market_data()`            | Stale cache triggers live Alpaca call; result must still populate fields.|

**Implementation pattern (PS-INT02):**
```python
@pytest.mark.asyncio
async def test_PS_INT02(selector, monkeypatch):
    def mock_get_cached_mri():
        raise RuntimeError("Redis down")
    monkeypatch.setattr(
        "app.services.command_center.get_macro_signal_service",
        lambda: type("Mock", (), {"get_cached_mri": mock_get_cached_mri})()
    )
    # ... mock other providers normally ...
    snapshot = await selector._gather_market_snapshot(db=mock_db)
    assert snapshot["mri"] is None
    assert snapshot["regime"] is not None  # Other providers still work
```

---

### P0 -- Failure Resilience (PS-R01-04)

These tests verify graceful degradation when data is unavailable.

| ID       | Description                              | Input                                        | Expected                                                    | Rationale                                                               |
|----------|------------------------------------------|----------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-R01   | All signals None: score = 0.0            | `ALL_MISSING_MARKET`                         | `score = 0.0`, condition = `neutral`                         | Zero-division guard in composite calculation.                           |
| PS-R02   | Single signal drives entire classification | `PARTIAL_DATA_MARKET` (only regime)         | `score = 60.0`, condition = `aggressive_bull`                | Regime alone (bullish/conf=75) renormalized to full weight.             |
| PS-R03   | Label fallback changes classification    | `LABEL_FALLBACK_RED` vs `LABEL_FALLBACK_GREEN` | Red: `score=-6.0` (cautious), Green: `score=12.0` (neutral) | Label fallback must actually influence the composite.                   |
| PS-R04   | `select_presets()` returns valid dict even with empty snapshot | Mock `_gather_market_snapshot` returning `ALL_MISSING_MARKET` | Dict has all required keys: `condition`, `presets`, `max_positions`, `reasoning`, `market_snapshot` | End-to-end contract: callers depend on these keys existing. |

**Implementation pattern (PS-R01):**
```python
def test_PS_R01(selector):
    score, signals = selector._compute_composite_score(ALL_MISSING_MARKET)
    assert score == 0.0
    condition = selector._classify_condition(score, ALL_MISSING_MARKET)
    assert condition == "neutral"
```

---

### P1 -- Anti-Thrashing (PS-T01-03)

These tests check stability near classification boundaries. Repeated calls with the same input must produce the same output.

| ID       | Description                              | Input                                        | Expected                                                    | Rationale                                                               |
|----------|------------------------------------------|----------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-T01   | Deterministic at boundary (score=50.0)   | `score=50.0, BULLISH_MARKET` called 100 times | All 100 results = `aggressive_bull`                         | Classification is purely functional (no randomness), so deterministic.  |
| PS-T02   | Deterministic at boundary (score=19.9)   | `score=19.9, NEUTRAL_MARKET` called 100 times | All 100 results = `neutral`                                 | Same input must always produce same output.                             |
| PS-T03   | **SKIP (not implemented)**: Hysteresis near boundary | Score oscillates 49.5 to 50.5 on consecutive calls | Would need 2+ consecutive above 50 to promote | Hysteresis not implemented. See Future section. Mark as `xfail`. |

**Implementation pattern (PS-T01):**
```python
def test_PS_T01(selector):
    results = [
        selector._classify_condition(50.0, BULLISH_MARKET)
        for _ in range(100)
    ]
    assert all(r == "aggressive_bull" for r in results)
```

---

### P1 -- Scoring Math (PS-M01-05)

These tests verify the composite score against hand-computed arithmetic. Every number is verified by the formula. See the "Verified Composite Scores" table at the end of this document for the full derivation.

| ID       | Description                              | Input Snapshot          | Expected Composite | Signal Breakdown                                                        | Rationale                                |
|----------|------------------------------------------|-------------------------|--------------------|-------------------------------------------------------------------------|------------------------------------------|
| PS-M01   | Max bullish score                        | `MAX_BULLISH_MARKET`    | `93.0`             | regime=80.0, mri=100.0, fg=100.0, readiness=100.0                      | Upper bound of the scoring system.       |
| PS-M02   | Max bearish score                        | `MAX_BEARISH_MARKET`    | `-93.0`            | regime=-80.0, mri=-100.0, fg=-100.0, readiness=-100.0                  | Lower bound of the scoring system.       |
| PS-M03   | Neutral market score                     | `NEUTRAL_MARKET`        | `3.0`              | regime=0.0, mri=10.0, fg=0.0, readiness=0.0                            | Near-zero but slightly positive from MRI.|
| PS-M04   | Bullish market score                     | `BULLISH_MARKET`        | `53.6`             | regime=68.0, mri=50.0, fg=44.0, readiness=40.0                         | Confirms aggressive_bull classification. |
| PS-M05   | Bearish market score                     | `BEARISH_MARKET`        | `-51.6`            | regime=-64.0, mri=-40.0, fg=-56.0, readiness=-40.0                     | Confirms skip classification (< -50).    |

**Implementation pattern (PS-M01):**
```python
def test_PS_M01(selector):
    score, signals = selector._compute_composite_score(MAX_BULLISH_MARKET)
    assert signals["regime"] == pytest.approx(80.0)
    assert signals["mri"] == pytest.approx(100.0)
    assert signals["fear_greed"] == pytest.approx(100.0)
    assert signals["readiness"] == pytest.approx(100.0)
    # composite = 80*0.35 + 100*0.30 + 100*0.20 + 100*0.15 = 28 + 30 + 20 + 15 = 93.0
    assert score == pytest.approx(93.0)
```

---

### P1 -- Reasoning Output (PS-O01-03)

These tests verify the human-readable reasoning string built by `_build_reasoning()`.

| ID       | Description                              | Input                                                      | Expected Substring(s)                                       | Rationale                                                               |
|----------|------------------------------------------|------------------------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-O01   | Contains composite score                 | `condition="neutral", score=3.0, ...NEUTRAL_MARKET`        | `"Composite: +3.0/100"`                                     | Reasoning must include the composite for auditability.                  |
| PS-O02   | Contains regime info                     | `condition="aggressive_bull", score=53.6, ...BULLISH_MARKET` | `"Regime: bullish (85%)"` and `"+68"`                      | Regime label, confidence, and signal score must appear.                 |
| PS-O03   | Shows "unavailable" for missing F&G      | `condition="neutral", score=0.0, ...` with `fg=None`       | `"F&G: unavailable"`                                        | Missing signals must be explicitly noted, not silently omitted.         |

**Implementation pattern (PS-O01):**
```python
def test_PS_O01(selector):
    _, signal_scores = selector._compute_composite_score(NEUTRAL_MARKET)
    reasoning = selector._build_reasoning("neutral", 3.0, signal_scores, NEUTRAL_MARKET)
    assert "Composite: +3.0/100" in reasoning
```

---

### P2 -- Edge Cases (PS-E01-07)

These tests document quirky but valid behaviors.

| ID       | Description                              | Input                                                      | Expected                                                    | Rationale                                                               |
|----------|------------------------------------------|------------------------------------------------------------|-------------------------------------------------------------|-------------------------------------------------------------------------|
| PS-E01   | Regime = unrecognized string             | `regime="sideways", confidence=80`                         | `regime_signal = 0.0` (`regime_map.get("sideways", 0)`)     | Unknown regime treated as neutral, not error.                           |
| PS-E02   | MRI = 50 (exact neutral)                 | `mri=50`                                                   | `mri_signal = 0.0`                                          | `(50-50)*2 = 0`. Midpoint maps exactly to zero.                        |
| PS-E03   | F&G = 50 (exact neutral)                 | `fear_greed=50`                                            | `fg_signal = 0.0`                                           | `(50-50)*2 = 0`. Midpoint maps exactly to zero.                        |
| PS-E04   | Readiness score = 0 (best possible)      | `readiness=0`                                              | `readiness_signal = 100.0`                                  | `(50-0)*2 = 100`. Maximum bullish readiness.                           |
| PS-E05   | All signals at midpoint                  | `mri=50, regime=neutral/100, fg=50, readiness=50`          | `composite = 0.0`                                           | All signals = 0 after normalization, composite = 0.                     |
| PS-E06   | Negative MRI (below range)               | `mri=-10`                                                  | `mri_signal = 120.0`                                        | `(50-(-10))*2 = 120`. No clamp in code. Signal exceeds [-100,+100].    |
| PS-E07   | F&G = 101 (above range)                  | `fear_greed=101`                                           | `fg_signal = 102.0`                                         | `(101-50)*2 = 102`. No clamp in code. Signal exceeds [-100,+100].      |

**Implementation pattern (PS-E01):**
```python
def test_PS_E01(selector):
    snapshot = {**NEUTRAL_MARKET, "regime": "sideways", "regime_confidence": 80}
    _, signals = selector._compute_composite_score(snapshot)
    assert signals["regime"] == 0.0  # "sideways" not in regime_map, defaults to 0
```

---

## Verified Composite Scores

Full hand-verified arithmetic for every mock snapshot. These are the canonical reference values tests should assert against.

### BULLISH_MARKET
```
regime:    80 * min(85/100, 1.0) = 80 * 0.85   =  +68.0
mri:       (50 - 25) * 2                        =  +50.0
fear_greed: (72 - 50) * 2                       =  +44.0
readiness: (50 - 30) * 2                        =  +40.0
available_weight = 0.35 + 0.30 + 0.20 + 0.15    =  1.00

composite = 68.0*0.35 + 50.0*0.30 + 44.0*0.20 + 40.0*0.15
          = 23.80 + 15.00 + 8.80 + 6.00
          = 53.60
condition = aggressive_bull (53.6 >= 50)
```

### MODERATE_BULL_MARKET
```
regime:    80 * min(70/100, 1.0) = 80 * 0.70   =  +56.0
mri:       (50 - 35) * 2                        =  +30.0
fear_greed: (55 - 50) * 2                       =  +10.0
readiness: (50 - 40) * 2                        =  +20.0
available_weight = 1.00

composite = 56.0*0.35 + 30.0*0.30 + 10.0*0.20 + 20.0*0.15
          = 19.60 + 9.00 + 2.00 + 3.00
          = 33.60
condition = moderate_bull (33.6 >= 20)
```

### NEUTRAL_MARKET
```
regime:    0 * min(60/100, 1.0) = 0 * 0.60     =    0.0
mri:       (50 - 45) * 2                        =  +10.0
fear_greed: (50 - 50) * 2                       =    0.0
readiness: (50 - 50) * 2                        =    0.0
available_weight = 1.00

composite = 0.0*0.35 + 10.0*0.30 + 0.0*0.20 + 0.0*0.15
          = 0.00 + 3.00 + 0.00 + 0.00
          = 3.00
condition = neutral (3.0 >= 0, < 20)
```

### BEARISH_MARKET
```
regime:    -80 * min(80/100, 1.0) = -80 * 0.80  =  -64.0
mri:       (50 - 70) * 2                         =  -40.0
fear_greed: (22 - 50) * 2                        =  -56.0
readiness: (50 - 70) * 2                         =  -40.0
available_weight = 1.00

composite = -64.0*0.35 + -40.0*0.30 + -56.0*0.20 + -40.0*0.15
          = -22.40 + -12.00 + -11.20 + -6.00
          = -51.60
condition = skip (-51.6 < -50)
```

### PANIC_MARKET
```
regime:    -80 * min(95/100, 1.0) = -80 * 0.95  =  -76.0
mri:       (50 - 85) * 2                         =  -70.0
fear_greed: (8 - 50) * 2                         =  -84.0
readiness: (50 - 90) * 2                         =  -80.0
available_weight = 1.00

composite = -76.0*0.35 + -70.0*0.30 + -84.0*0.20 + -80.0*0.15
          = -26.60 + -21.00 + -16.80 + -12.00
          = -76.40
condition = skip (panic override: mri=85 > 80 AND fg=8 < 10)
Note: Even without the panic override, -76.4 < -50 would still produce "skip".
```

### PARTIAL_DATA_MARKET (only regime available)
```
regime:    80 * min(75/100, 1.0) = 80 * 0.75   =  +60.0
mri:       None (excluded)
fear_greed: None (excluded)
readiness: None, label=None (excluded)
available_weight = 0.35

normalized_weight_regime = 0.35 / 0.35 = 1.0

composite = 60.0 * 1.0
          = 60.0
condition = aggressive_bull (60.0 >= 50)
```

### ALL_MISSING_MARKET
```
All signals = None
available_weight = 0.0 → early return

composite = 0.0
condition = neutral (0.0 >= 0)
```

### MAX_BULLISH_MARKET
```
regime:    80 * min(100/100, 1.0) = 80 * 1.0   =  +80.0
mri:       (50 - 0) * 2                         = +100.0
fear_greed: (100 - 50) * 2                      = +100.0
readiness: (50 - 0) * 2                         = +100.0
available_weight = 1.00

composite = 80.0*0.35 + 100.0*0.30 + 100.0*0.20 + 100.0*0.15
          = 28.00 + 30.00 + 20.00 + 15.00
          = 93.00
condition = aggressive_bull (93.0 >= 50)
```

### MAX_BEARISH_MARKET
```
regime:    -80 * min(100/100, 1.0) = -80 * 1.0  =  -80.0
mri:       (50 - 100) * 2                        = -100.0
fear_greed: (0 - 50) * 2                         = -100.0
readiness: (50 - 100) * 2                        = -100.0
available_weight = 1.00

composite = -80.0*0.35 + -100.0*0.30 + -100.0*0.20 + -100.0*0.15
          = -28.00 + -30.00 + -20.00 + -15.00
          = -93.00
condition = skip (-93.0 < -50)
```

### BOUNDARY_AGGRESSIVE (only regime available)
```
regime:    80 * min(62.5/100, 1.0) = 80 * 0.625 =  +50.0
mri:       None (excluded)
fear_greed: None (excluded)
readiness: None, label=None (excluded)
available_weight = 0.35

normalized_weight_regime = 0.35 / 0.35 = 1.0

composite = 50.0 * 1.0
          = 50.0
condition = aggressive_bull (50.0 >= 50, exact boundary)
```

### LABEL_FALLBACK_GREEN
```
regime:    0 * min(60/100, 1.0) = 0 * 0.60     =    0.0
mri:       (50 - 45) * 2                        =  +10.0
fear_greed: (50 - 50) * 2                       =    0.0
readiness: label "green" → +60.0 (fallback)
available_weight = 1.00

composite = 0.0*0.35 + 10.0*0.30 + 0.0*0.20 + 60.0*0.15
          = 0.00 + 3.00 + 0.00 + 9.00
          = 12.00
condition = neutral (12.0 >= 0, < 20)
```

### LABEL_FALLBACK_YELLOW
```
regime:    0 * 0.60  = 0.0
mri:       +10.0
fear_greed: 0.0
readiness: label "yellow" → 0.0 (fallback)
available_weight = 1.00

composite = 0.0*0.35 + 10.0*0.30 + 0.0*0.20 + 0.0*0.15
          = 0.00 + 3.00 + 0.00 + 0.00
          = 3.00
condition = neutral (3.0 >= 0, < 20)
```

### LABEL_FALLBACK_RED
```
regime:    0 * 0.60  = 0.0
mri:       +10.0
fear_greed: 0.0
readiness: label "red" → -60.0 (fallback)
available_weight = 1.00

composite = 0.0*0.35 + 10.0*0.30 + 0.0*0.20 + -60.0*0.15
          = 0.00 + 3.00 + 0.00 + -9.00
          = -6.00
condition = cautious (-6.0 >= -20, < 0)
```

### NEAR_PANIC_MRI_ONLY
```
regime:    -80 * min(90/100, 1.0) = -80 * 0.90  =  -72.0
mri:       (50 - 85) * 2                         =  -70.0
fear_greed: (25 - 50) * 2                        =  -50.0
readiness: (50 - 80) * 2                         =  -60.0
available_weight = 1.00

composite = -72.0*0.35 + -70.0*0.30 + -50.0*0.20 + -60.0*0.15
          = -25.20 + -21.00 + -10.00 + -9.00
          = -65.20
condition = skip (-65.2 < -50, no panic override because fg=25 >= 10)
Note: No panic override here, but score alone pushes to skip.
```

### NEAR_PANIC_FG_ONLY
```
regime:    -80 * min(75/100, 1.0) = -80 * 0.75  =  -60.0
mri:       (50 - 60) * 2                         =  -20.0
fear_greed: (5 - 50) * 2                         =  -90.0
readiness: (50 - 70) * 2                         =  -40.0
available_weight = 1.00

composite = -60.0*0.35 + -20.0*0.30 + -90.0*0.20 + -40.0*0.15
          = -21.00 + -6.00 + -18.00 + -6.00
          = -51.00
condition = skip (-51.0 < -50, no panic override because mri=60 <= 80)
Note: No panic override here either, but score alone pushes to skip.
```

---

## Complete Test Case Summary

| Priority | Category                    | Count | IDs                                 |
|----------|-----------------------------|-------|-------------------------------------|
| P0       | Boundary Classification     | 12    | PS-U01a through PS-U01l            |
| P0       | Confidence Scaling          | 7     | PS-U02a through PS-U02g            |
| P0       | Weight Re-normalization     | 6     | PS-U03a through PS-U03f            |
| P0       | Readiness Label Fallback    | 5     | PS-U04a through PS-U04e            |
| P0       | Panic Override              | 10    | PS-S01a through PS-S01e, PS-S02a through PS-S02e |
| P0       | Mapping Correctness         | 3     | PS-C01 through PS-C03              |
| P0       | Cache Behavior              | 4     | PS-INT01 through PS-INT04          |
| P0       | Failure Resilience          | 4     | PS-R01 through PS-R04              |
| P1       | Anti-Thrashing              | 3     | PS-T01 through PS-T03              |
| P1       | Scoring Math                | 5     | PS-M01 through PS-M05              |
| P1       | Reasoning Output            | 3     | PS-O01 through PS-O03              |
| P2       | Edge Cases                  | 7     | PS-E01 through PS-E07              |
|          | **Total**                   | **69**|                                     |

---

## Future: Hysteresis Recommendation

The current classifier is purely functional: `score >= threshold` determines the condition. When market signals oscillate near a boundary (e.g., composite flickering between 49.5 and 50.5), consecutive autopilot runs will alternate between `moderate_bull` and `aggressive_bull` presets -- causing different stocks to be scanned, different signals generated, and potentially conflicting trades.

**Recommended pattern**: Track the last classification and require N consecutive score readings above/below a threshold before promoting/demoting. Example:

```
# Promotion requires 2 consecutive readings above threshold
if score >= threshold AND last_condition was already at_or_above:
    promote()
else:
    hold_current()
```

This would be implemented as a stateful wrapper around `_classify_condition()` that stores the last N results. Test PS-T03 is reserved for this feature.

**Impact**: Without hysteresis, the selector is deterministic (same input = same output), which is easy to test. Hysteresis adds state, requiring tests for:
- Initial classification (cold start, no history)
- Promotion after N consecutive readings
- Demotion after N consecutive readings
- Reset on service restart

---

## Future: StrategyProfile Migration

Currently, preset names are bare strings (`"aggressive"`, `"moderate"`, etc.) stored in the `MARKET_CONDITIONS` dict and cross-referenced against `LEAPS_PRESETS`. This string-coupling is fragile (see bug B1: `value_deep` typo).

**Recommended pattern**: Replace string preset names with typed `StrategyProfile` dataclasses:

```python
@dataclass
class StrategyProfile:
    id: str
    risk_tier: Literal["aggressive", "moderate", "conservative"]
    max_positions: int
    screening_params: dict
    # ... etc
```

This would:
- Eliminate typo bugs at import time (no more runtime `KeyError`)
- Enable IDE autocompletion for preset fields
- Allow type-checking across the selector-to-screening boundary
- Make the contract test (PS-C03) unnecessary (the type system enforces it)

**Impact on tests**: PS-C03 would become a compile-time guarantee. PS-C01/C02 would shift to verifying `StrategyProfile` field values instead of dict structure.
