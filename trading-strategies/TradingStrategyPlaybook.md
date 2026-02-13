# Trading Strategy Playbook

---

## Strategy: Day Trade (5m) — Large Cap (Top-25 List)

**Style:** Breakout + Pullback (separate signals)  
**Goal:** Clean intraday moves without early chop

### Filters (Must Pass)
- Skip bars after open: **3 bars (15 min)**
- Min ATR% (5m): **0.45–0.80** (start **0.55**)
- RVOL (5m): **1.20–1.60** (start **1.30**)
- Volume spike multiplier (vs VolMA20): **1.15–1.35** (start **1.20**)
- Optional market regime:
  - **SPY above EMA20** for longs
  - **SPY below EMA20** for shorts

### Buy Signal A: ORB Breakout Long
- **Define ORB High/Low:** first 15 minutes (3 bars)
- **Trigger (Long):**
  - Close crosses above ORB High
  - Volume spike = true
  - RVOL ≥ threshold
  - Price above EMA21 *(or EMA8 > EMA21)*
- **Stop / Exit:**
  - Stop = ORB High − `0.5 × ATR(14,5m)` **or** below breakout candle low
  - Exit if close back below ORB High (failed breakout)
  - Take profit / trim at **1R**, trail under **EMA8 (5m)**

### Sell Signal A: ORB Breakout Short
- Mirror conditions:
  - Close crosses below ORB Low
  - Same volume / RVOL / ATR filters
  - Trend confirm: **EMA8 < EMA21** or close < EMA21
  - Stop above ORB Low + `0.5 × ATR` **or** above breakdown candle high

### Buy Signal B: VWAP / EMA Pullback Continuation Long
- **Setup:** EMA8 > EMA21 and price above EMA21
- **Trigger (Long):**
  - Price tags VWAP *(or EMA21)* during pullback
  - Pullback volume < VolMA20 (contraction)
  - Close reclaims VWAP *(close > VWAP and prior close ≤ VWAP)*
  - RSI(14,5m) > 50 *(or MACD histogram > 0)*
- **Stop / Exit:**
  - Stop below pullback low
  - Exit if loses VWAP and can’t reclaim within **2 bars**

### Sell Signal B: VWAP / EMA Pullback Continuation Short
- Mirror:
  - EMA8 < EMA21 and price below EMA21
  - Tag VWAP / EMA21 from below, then reclaim down
  - RSI < 50 *(or MACD histogram < 0)*

---

## Strategy: Intraday Swing (15m) — Large Cap (Top-25 List)

**Style:** Breakout + Pullback  
**Goal:** Fewer, higher-quality trend legs

### Filters
- Skip bars after open: **2 bars (30 min)**
- Min ATR% (15m): **0.60–1.20** (start **0.80**)
- RVOL (15m): **1.10–1.50** (start **1.20**)
- Volume spike multiplier: **1.10–1.30** (start **1.15**)
- Trend bias: EMA8 vs EMA21 alignment

### Buy Signal A: Range Breakout Long (15m)
- **Range:** last 30 bars (configurable)
- **Trigger:**
  - Close crosses above range high
  - Volume spike = true
  - RVOL ≥ threshold
  - EMA8 > EMA21
  - RSI(14) ≥ 55 *(or MACD histogram rising > 0)*
- **Stop / Exit:**
  - Stop below range high − `0.6 × ATR(14,15m)` **or** breakout bar low
  - Exit if close returns inside range
  - Trail under EMA21 once in profit

### Sell Signal A: Range Breakdown Short
- Mirror below range low
- EMA8 < EMA21
- RSI ≤ 45

### Buy Signal B: VWAP Pullback Reclaim Long (15m)
- **Setup:** EMA8 > EMA21, price above EMA21
- **Trigger:**
  - Pullback touches VWAP
  - Volume contracts
  - Close reclaims VWAP
  - RSI crosses above 50 *(or MACD turns up)*
- **Stop / Exit:**
  - Stop below pullback low
  - Exit if closes below VWAP **2 bars in a row**

### Sell Signal B: VWAP Pullback Reclaim Short
- Mirror conditions

---

## Strategy: Swing (4H) — Large Cap (Top-25 List)

**Style:** Pullback Continuation (Primary) + Breakout (Secondary)  
**Goal:** Durable swing moves with fewer false signals

### Filters
- Min ATR% (4H): **0.90–1.60** (start **1.10**)
- RVOL (4H): **1.05–1.35** *(optional)*
- Regime:
  - Price above SMA50 and SMA50 > SMA200 (longs)
  - Inverse for shorts
- ADX(14): **> 18–25** (start **20**)

### Buy Signal A: 4H Pullback to EMA21 Reclaim Long
- **Setup:** Above SMA50 & SMA200, EMA8 > EMA21
- **Trigger:**
  - Pullback touches EMA21
  - Volume contraction (optional)
  - Close reclaims EMA21
  - RSI > 50 *(or MACD histogram > 0)*
- **Stop / Exit:**
  - Stop below pullback swing low **or** `1 × ATR`
  - Exit below SMA50 *(conservative)* or EMA21 for 2 closes *(aggressive)*
  - Trail under EMA21 or last higher low

### Sell Signal A: 4H Pullback to EMA21 Reclaim Short
- Mirror conditions

### Buy Signal B: 4H Breakout Long
- Swing high = highest high of last **20–55 bars**
- **Trigger:**
  - Close crosses above swing high
  - ADX > 20
  - RSI > 55
  - Volume spike optional
- **Stop / Exit:**
  - Stop below breakout − `1 × ATR`
  - Exit on close back below breakout

### Sell Signal B: 4H Breakdown Short
- Mirror conditions

---

## Small Cap (Clean Small Caps): S&P 600 Threshold Sets

---

## Strategy: Day Trade (5m) — S&P 600

**Goal:** Avoid dead movers and pure chaos

### Filters
- Min ATR% (5m): **0.9–1.4** (start **1.1**)
- RVOL (5m): **1.8–2.6** (start **2.1**)
- Volume spike multiplier: **1.4–1.8** (start **1.6**)
- Skip bars after open:
  - **2 bars (10 min)**
  - **3 bars (15 min)** if noisy

### Buy Signal A: Breakout Long (ORB or Premarket High)
- **Trigger:**
  - Close above ORB high
  - Volume spike + RVOL ≥ 2.1
  - RSI ≥ 55 *(or MACD histogram > 0)*
- **Stop / Exit:**
  - Stop below ORB high − `0.7 × ATR`
  - Exit if closes back below ORB high

### Sell Signal A: Breakout Short
- Mirror below ORB low
- RSI ≤ 45 *(or MACD histogram < 0)*

### Buy Signal B: VWAP Reclaim Pullback Long
- **Trigger:**
  - Touch VWAP
  - Volume contracts
  - Close reclaims VWAP
- **Stop / Exit:**
  - Stop below pullback low
  - Exit if VWAP fails reclaim within **1–2 bars**

### Sell Signal B: VWAP Reject Pullback Short
- Mirror conditions

---

## Optional “Quality Filters” (High Impact)

Apply as a final gate to reduce noise:
- **No-trade zone:** ATR% < min OR RVOL < min
- **Trend gate:** EMA8 / EMA21 alignment required
- **Momentum gate:** RSI > 50 (longs) / < 50 (shorts)
- **Failure rules:**
  - Exit failed breakouts
  - Exit failed VWAP/EMA reclaims (2 closes against reference)