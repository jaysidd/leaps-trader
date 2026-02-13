# Trading Prompt Library (Full)

Educational templates only (not financial advice). These prompts are designed to reduce hallucinations: **if required data is missing, the assistant must ask for it** and must not fabricate prices, levels, times, indicators, or news.

## Global Placeholders (Use Anywhere)

- `{symbol}`: Ticker (e.g., AAPL)
- `{needed_score}`: Minimum Confluence Score to allow a setup (e.g., `8`)
- `{min_confidence}`: Minimum confidence % to allow a setup (e.g., `65`)
- `{risk_per_trade_pct}`: Risk budget per trade (e.g., `0.5`)
- `{timezone="ET"}`: Timezone for all timestamps
- `{now_timestamp="yyyy-mm-dd HH:MM:SS"}`: Current timestamp in `{timezone}`
- `{entry_tf="M15"}` `{trend_tf="H1"}` `{swing_tf="D"}`
- `{max_setups=1}` `{rr_min=1.5}`

---

## Stocks

### Stocks — Intraday

#### Stocks — Intraday — Trend

##### Prompt: Stocks — Intraday — Trend — ORB + VWAP Trend Continuation

**Description:** Finds a single high-quality **trend-following** intraday setup using an **Opening Range Break** confirmed by **VWAP + volume + market proxy alignment**. Outputs one JSON setup or “NO TRADE”.

```text
OBJECTIVE: Generate the single highest-quality intraday TREND setup for {symbol} using {entry_tf}-{trend_tf}.

REQUIRED DATA (if missing, reply with “NEEDED DATA” only):
- {now_timestamp} in {timezone}
- Today + yesterday OHLCV on M15 and H1
- Today premarket high/low (if available), today open, current price
- Session VWAP and relative volume (RVOL) or volume vs 20-bar average
- Market proxy (SPY/QQQ) M15/H1 trend direction

CRITICAL RULES:
- DO NOT invent prices, times, news, VWAP, RVOL, levels, or indicators.
- Only output a setup if Confluence Score ≥{needed_score} AND Confidence ≥{min_confidence}%.
- Output exactly 1 setup (best), else output “NO TRADE” with reasons.

TREND FILTER (H1):
- Bullish only if: price > H1 20EMA > H1 50EMA AND H1 structure = higher highs/higher lows.
- Bearish only if: price < H1 20EMA < H1 50EMA AND H1 structure = lower highs/lower lows.

SETUP (M15 ORB):
- Define Opening Range = first completed M15 candle after cash open.
- Long: break AND close above OR high, then either (a) pullback holds OR high or (b) reclaims VWAP after a shallow pullback.
- Short: break AND close below OR low, then either (a) pullback rejects OR low or (b) loses VWAP after a shallow bounce.

RISK:
- Stop must be structure-based + ATR buffer (1.0–1.5x M15 ATR) and logically invalidates the setup.
- Enforce RR ≥ {rr_min}. Include a breakeven rule.

CONFLUENCE SCORING (0–10):
- H1 trend alignment (2)
- OR level quality (clean break/close) (2)
- VWAP alignment (trend side + reclaim/hold) (2)
- Volume confirmation (break candle volume > 1.2x 20-bar avg OR RVOL high) (2)
- Market proxy alignment (SPY/QQQ same direction) (2)

ENTRY TIME CALCULATION:
- Entry is on the next {entry_tf} candle close after the trigger. Compute exact timestamp from {now_timestamp}.
- Format: yyyy-mm-dd HH:MM:SS

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "ORB+VWAP", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Intraday — Trend — VWAP Pullback Trend (Trend Day Playbook)

**Description:** Generates a **trend-day continuation** entry by buying/selling **VWAP pullbacks** in the H1 trend direction with volume-pattern confirmation.

```text
OBJECTIVE: Find one intraday TREND continuation setup for {symbol} that uses VWAP pullbacks (M15 entries, H1 direction).

REQUIRED DATA:
- {now_timestamp}, today M15/H1 OHLCV, VWAP, M15 ATR, volume vs 20-bar avg, current price
- Session high/low so far, key levels (prior day high/low, gap levels if any)

CRITICAL RULES:
- No numbers unless provided. If data missing → “NEEDED DATA”.
- Only trade in H1 trend direction. Must meet score ≥{needed_score} and confidence ≥{min_confidence}%.

TREND FILTER (H1):
- Trend = EMA stack (20/50) + structure (HH/HL or LH/LL). If mixed → NO TRADE.

SETUP (M15):
- Long: price above VWAP; wait for pullback that tags VWAP or M15 20EMA, then prints a higher low + bullish close back above VWAP/20EMA.
- Short: price below VWAP; wait for pullback into VWAP or M15 20EMA, then prints a lower high + bearish close back below VWAP/20EMA.

CONFIRMATIONS:
- Pullback volume should contract vs impulse; trigger candle volume should expand.
- Avoid entries directly into major resistance/support within 0.25–0.5x ATR.

SCORING (0–10):
- H1 trend (2), VWAP context (2), pullback quality (2), volume pattern (2), level confluence (2)

RISK/EXITS:
- Stop beyond pullback swing + 1.0x ATR buffer.
- TP1 at prior swing, TP2 at session high/low extension; move stop to breakeven after TP1.

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "VWAP Pullback", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Intraday — Trend — HOD/LOD Break + Tight Risk Momentum

**Description:** Scans for **high-of-day / low-of-day** breaks aligned with the H1 trend, requiring **compression + volume expansion** on the break.

```text
OBJECTIVE: Generate 1 momentum breakout setup for {symbol} (M15 entry) using High-of-Day/Low-of-Day breaks in trend direction.

REQUIRED DATA:
- Today intraday session high/low evolution, M15/H1 OHLCV, VWAP, volume stats, {now_timestamp}

RULES:
- Only if spread/liquidity acceptable (state assumptions; if unknown → ask).
- Must have clean consolidation beneath HOD (long) / above LOD (short) before break.

SETUP:
- Long: H1 bullish trend. M15 forms tight range below HOD with decreasing volume. Trigger = M15 close above HOD with volume expansion.
- Short: H1 bearish trend. M15 forms tight range above LOD with decreasing volume. Trigger = M15 close below LOD with volume expansion.

SCORING (0–10):
- Trend alignment (2), compression quality (2), breakout volume (2), VWAP alignment (2), market proxy alignment (2)

RISK:
- Stop below/above breakout range + 1.0x ATR buffer. RR ≥ {rr_min}. One re-entry max.

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "HOD/LOD Break", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

#### Stocks — Intraday — Mean Reversion

##### Prompt: Stocks — Intraday — Mean Reversion — VWAP Stretch Reversion (Range Regime Only)

**Description:** Mean reversion template that fades **VWAP extensions** only in a **range regime**, using rejection/RSI/divergence and clear path back to VWAP.

```text
OBJECTIVE: Generate 1 intraday MEAN REVERSION setup for {symbol} using VWAP stretch + rejection (M15 entries).

REQUIRED DATA:
- {now_timestamp}, M15/H1 OHLCV, VWAP, M15 ATR, RSI(14) or equivalent momentum measure, volume vs 20-bar avg
- Regime proxy: ADX(14) on H1 or a clear statement of whether the day is trending or ranging

CRITICAL RULES:
- If H1 is trending strongly (ADX high or clean EMA stack + impulse), prefer NO TRADE.
- Don’t invent VWAP/ATR/RSI values.

RANGE FILTER (must pass):
- H1 price oscillates around VWAP or EMAs without sustained impulse; OR ADX(14) low (if provided).

SETUP:
- Long MR: price deviates below VWAP by ≥ 1.5–2.5x M15 ATR, prints rejection (long lower wick + close back toward VWAP), and RSI shows oversold OR bullish divergence.
- Short MR: price deviates above VWAP by ≥ 1.5–2.5x M15 ATR, prints rejection (upper wick + close back), and RSI overbought OR bearish divergence.

SCORING (0–10):
- Stretch magnitude (2), rejection candle quality (2), volume climax then fade (2),
- VWAP distance/return path clear (2), major level confluence (prior day H/L, value area) (2)

RISK/EXITS:
- Stop beyond the extreme + ATR buffer. TP at VWAP (primary) and partial at mid-point if needed.
- Time stop: if no follow-through within N candles (ask for N or assume 4).

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "VWAP Stretch MR", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Intraday — Mean Reversion — Bollinger/Keltner Fade (Compression-to-Range)

**Description:** Fades band extremes via **outside → back inside** re-entry signals, only when the higher-timeframe context supports **range trading**.

```text
OBJECTIVE: Find 1 mean-reversion fade setup for {symbol} using Bollinger Bands (or Keltner) on M15.

REQUIRED DATA:
- M15 bands (settings you use), M15 ATR, VWAP, volume stats, H1 context, {now_timestamp}

RULES:
- Only fade band extremes if H1 is NOT in a strong trend.
- Prefer trades at confluence levels (prior day H/L, gap levels, volume profile POC if available).

SETUP:
- Long: M15 closes outside lower band then closes back inside band (re-entry) near a key level; target = mid-band/VWAP.
- Short: M15 closes outside upper band then closes back inside; target = mid-band/VWAP.

SCORING (0–10):
- Regime fit (2), band re-entry signal (2), key level (2), volume confirmation (2), risk/reward path (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "Band Fade MR", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Intraday — Mean Reversion — Gap Fill Mean Reversion (Conditional)

**Description:** Conditional **gap fill** framework using premarket + VWAP + rejection to avoid blindly fading strong trend days.

```text
OBJECTIVE: Generate 1 gap-fill setup for {symbol} (intraday mean reversion).

REQUIRED DATA:
- Yesterday close, today open, gap size (%), premarket high/low, M15 OHLCV, VWAP, {now_timestamp}

RULES:
- Identify gap type: small/large, with/without news (if unknown → ask).
- Only attempt gap fill if early price action rejects continuation and reclaims key intraday levels.

SETUP:
- If gapping up: watch failure to hold above premarket high or OR high; short trigger = M15 close back below VWAP + rejection.
- If gapping down: watch failure to hold below premarket low or OR low; long trigger = M15 close back above VWAP + rejection.

SCORING (0–10):
- Gap context (2), rejection signal (2), VWAP reclaim/lose (2), volume pattern (2), room to fill (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "Gap Fill MR", "timeframe": "{entry_tf}",
  "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "break_even_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

### Stocks — Swing

#### Stocks — Swing — Trend

##### Prompt: Stocks — Swing — Trend — Breakout From Base (Weekly/Daily Structure)

**Description:** Swing trend template that targets **base breakouts** using Weekly+Daily structure, volume expansion, and relative strength confirmation.

```text
OBJECTIVE: Generate 1 swing TREND setup for {symbol} using Daily + Weekly context (entries on D close or next open).

REQUIRED DATA:
- Weekly + Daily OHLCV (at least 6–12 months), key moving averages (20/50/200), volume averages
- Relative strength vs SPY (ratio or statement), upcoming events (earnings date if known)

CRITICAL RULES:
- If earnings is within X days, ask for X or default to 3 and flag “event risk”.
- Don’t invent prices/levels.

SETUP:
- Identify a multi-week base (range) with tightening volatility.
- Long: Weekly trend up (higher highs/lows). Daily breaks above base highs on volume expansion.
- Short: Weekly trend down. Daily breaks below base lows on volume expansion.

SCORING (0–10):
- Weekly trend alignment (2), base quality (2), breakout volume (2), RS vs SPY (2), risk-defined entry (2)

RISK/EXITS:
- Stop below breakout level (or last swing) + ATR buffer; scale out at 2R and trail with 20EMA or swing lows.

ENTRY TIME:
- If trigger is “daily close above/below level”, entry_time = next market open (ask for market calendar if needed).

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "Base Breakout", "timeframe": "{swing_tf}",
  "entry_type": "next_open|close_trigger", "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "trail_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Swing — Trend — Pullback-to-MA Trend Continuation

**Description:** Swing continuation prompt that buys/sells **pullbacks into the 20/50 EMA area** with volume contraction and reversal confirmation.

```text
OBJECTIVE: Find 1 swing trend continuation setup for {symbol} on pullback to Daily 20/50EMA.

REQUIRED DATA:
- Daily OHLCV, 20/50/200 EMAs, Daily ATR(14), volume avg, RS vs SPY

SETUP:
- Long: price above 50EMA; pullback to 20EMA/50EMA with declining volume; trigger = bullish reversal close (higher low + strong close).
- Short: price below 50EMA; pullback to 20EMA/50EMA with declining volume; trigger = bearish reversal close.

SCORING (0–10):
- Trend structure (2), MA confluence (2), pullback quality (2), trigger candle (2), overhead/supply room (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "MA Pullback Trend", "timeframe": "{swing_tf}",
  "entry_type": "next_open|close_trigger", "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "trail_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Swing — Trend — Volatility Contraction Pattern (VCP) Breakout

**Description:** Swing breakout prompt for **volatility contraction + volume dry-up** followed by a high-conviction breakout with defined risk.

```text
OBJECTIVE: Generate 1 swing breakout idea using volatility contraction (VCP-style) for {symbol}.

REQUIRED DATA:
- Daily OHLCV, ATR trend (contracting), volume trend (dry-up), key levels

SETUP:
- Series of contractions (ranges narrow), volume dries up, then breakout on expanding volume.
- Entry: daily close above trigger level; stop below last contraction low.

SCORING (0–10):
- Contraction quality (2), volume dry-up (2), breakout confirmation (2), trend context (2), risk/room (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "VCP Breakout", "timeframe": "{swing_tf}",
  "entry_type": "next_open|close_trigger", "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "trail_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

#### Stocks — Swing — Mean Reversion

##### Prompt: Stocks — Swing — Mean Reversion — Oversold Bounce (Multi-factor Mean Reversion)

**Description:** Swing mean reversion prompt that requires **extension + stabilization** (no “catching falling knives”) and targets a revert toward the mean (20EMA / breakdown level).

```text
OBJECTIVE: Produce 1 swing mean-reversion setup for {symbol} (bounce/revert) with strict risk control.

REQUIRED DATA:
- Daily OHLCV, RSI(14) (or similar), ATR(14), distance from 20/50EMA, recent support levels, event calendar (earnings)

RULES:
- Prefer broad market not in panic trend (ask for SPY trend / VIX regime if you use it).
- No catching falling knives: require stabilization signal.

SETUP:
- Long: price extended down (e.g., far below 20EMA), RSI oversold OR bullish divergence, and a reversal signal (higher low / strong close / reclaim prior day high).
- Target: mean reversion to 20EMA or prior breakdown level.

SCORING (0–10):
- Extension magnitude (2), stabilization/reversal (2), support confluence (2), market regime fit (2), clean R path (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "setup_name": "Oversold Bounce MR", "timeframe": "{swing_tf}",
  "entry_type": "next_open|close_trigger", "trigger": "...", "entry_time": "...", "entry_rule": "...",
  "stop_rule": "...", "tp_levels": ["...","..."], "trail_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "invalidation": "...", "notes": "..." }
```

##### Prompt: Stocks — Swing — Mean Reversion — Pair/Relative Mean Reversion (Beta-Neutral Concept)

**Description:** Pairs/relative-value mean reversion prompt that trades the **ratio z-score** between two tickers (requires ratio/z-score inputs).

```text
OBJECTIVE: Create 1 mean-reversion pairs idea: {symbol} vs {benchmark_or_peer}.

REQUIRED DATA:
- Price ratio series (symbol/peer) on Daily, z-score inputs (lookback), correlation, liquidity notes

RULES:
- If you can’t compute ratio/z-score from provided data, ask for it (don’t guess).

SETUP:
- Enter when ratio z-score is extreme (±Z) and prints reversal (z-score turning, ratio rejection).
- Prefer market-neutral sizing (dollar-neutral) and define both legs.

OUTPUT (JSON):
{ "pair": "...", "legs": [{"ticker":"...","side":"long/short","size_rule":"..."}, {"ticker":"...","side":"long/short","size_rule":"..."}],
  "signal": "...", "entry_rule": "...", "stop_rule": "...", "tp_rule": "...",
  "confluence_score": X, "confidence_pct": Y }
```

---

## Options

### Options — Intraday

#### Options — Intraday — Trend

##### Prompt: Options — Intraday — Trend — Defined-Risk Directional Debit Spread (Intraday)

**Description:** Builds an intraday **defined-risk** debit spread (calls/puts) only after an underlying trend trigger; requires an options chain snapshot to avoid hallucinated strikes/prices.

```text
OBJECTIVE: Generate 1 intraday TREND options setup for {symbol} using a defined-risk debit spread aligned with the underlying trend.

REQUIRED DATA (if missing → “NEEDED DATA”):
- Underlying: M15/H1 OHLCV, VWAP, ATR, key levels, {now_timestamp}
- Options chain snapshot: expiries available, strikes, bid/ask (or mid), OI/volume, IV (if available)

CRITICAL RULES:
- Do not output strikes/premiums without a chain snapshot.
- Only trade in direction of H1 trend; score ≥{needed_score}; confidence ≥{min_confidence}%.

UNDERLYING TRIGGER (must occur first):
- Same as a trend setup: ORB/VWAP pullback/HOD break (choose the best and state why).

OPTIONS CONSTRUCTION (debit spread):
- Choose DTE range (ask; default 7–21 DTE for non-0DTE names).
- Choose long leg delta range (ask; default 0.45–0.65).
- Sell leg to reduce cost; ensure defined max loss.
- Require tight liquidity: bid/ask not excessively wide (ask threshold).

RISK/EXITS:
- Max loss = debit paid; take profit rule (e.g., 30–60% of max profit) and time stop by end of day.
- Underlying invalidation must align with spread exit.

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "strategy": "debit_spread",
  "underlying_trigger": "...", "entry_time": "...",
  "spread_legs": [{"action":"buy","type":"call|put","strike": "...", "expiry":"..."}, {"action":"sell","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "max_profit": "...", "breakeven": "...",
  "exit_rules": {"profit_take":"...", "stop":"...", "time_stop":"..."},
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

##### Prompt: Options — Intraday — Trend — 0DTE/1DTE Defined-Risk (Index/ETF Only, Strict)

**Description:** Ultra-short-dated defined-risk template for very liquid **index/ETF** products only; requires full chain snapshot and rejects low-liquidity conditions.

```text
OBJECTIVE: If (and only if) {symbol} is a highly liquid index/ETF, produce 1 ultra-short-dated TREND setup with defined risk.

REQUIRED DATA:
- Underlying M15/H1 + VWAP + today’s levels + {now_timestamp}
- 0DTE/1DTE chain snapshot with liquidity metrics

STRICT RULES:
- If liquidity or chain data missing → NEEDED DATA.
- Only use defined-risk spreads. No naked short options.
- Must have crystal-clear trend regime; otherwise NO TRADE.

SETUP:
- Use ORB or VWAP pullback trigger in trend direction.
- Pick strikes with high liquidity; keep max loss within {risk_per_trade_pct}% of account.

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "strategy": "defined_risk_0dte",
  "underlying_trigger": "...", "entry_time": "...",
  "legs": [{"action":"buy","type":"call|put","strike": "...", "expiry":"..."}, {"action":"sell","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "exit_rules": {"profit_take":"...", "stop":"...", "time_stop":"..."},
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

#### Options — Intraday — Mean Reversion

##### Prompt: Options — Intraday — Mean Reversion — Credit Spread Fade at Extremes (Defined Risk)

**Description:** Sells premium with defined risk (credit spreads) after an **exhaustion + rejection** mean reversion signal; requires IV/liquidity context.

```text
OBJECTIVE: Produce 1 intraday mean-reversion options setup using a defined-risk credit spread after an exhaustion move.

REQUIRED DATA:
- Underlying: M15/H1, VWAP, ATR, RSI/divergence inputs, key levels, {now_timestamp}
- Options chain snapshot (same-day or near-term expiries), bid/ask, OI/volume, IV/IVR if you use it

RULES:
- Mean reversion only if day is range-like (state regime evidence).
- No chain → no strikes → ask for it.

UNDERLYING SIGNAL:
- Exhaustion + rejection at extreme (e.g., outside bands, VWAP stretch) then re-entry toward VWAP.

OPTIONS:
- For short put spread (bullish MR) or short call spread (bearish MR).
- Define max loss, profit target (e.g., 40–70% of credit), and hard stop.

SCORING (0–10):
- Regime fit (2), exhaustion/rejection (2), level confluence (2), IV context (2), liquidity (2)

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "strategy": "credit_spread",
  "underlying_signal": "...", "entry_time": "...",
  "legs": [{"action":"sell","type":"call|put","strike":"...","expiry":"..."}, {"action":"buy","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "profit_target": "...", "stop_rule": "...",
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

##### Prompt: Options — Intraday — Mean Reversion — Iron Condor (Range Thesis Only)

**Description:** Range-only intraday structure that sells both sides with defined risk; includes breach/defense rules and strict “no trend day” gating.

```text
OBJECTIVE: If the market is clearly ranging, generate 1 intraday iron condor plan for {symbol} with strict risk limits.

REQUIRED DATA:
- Underlying intraday range boundaries + VWAP + volatility context
- Options chain snapshot for selecting both sides

RULES:
- If trend regime → NO TRADE.
- Define max loss and planned exits (profit target + breach defense).

OUTPUT (JSON):
{ "symbol": "...", "strategy": "iron_condor", "regime": "range_only",
  "entry_time": "...",
  "legs": [
    {"action":"sell","type":"call","strike":"...","expiry":"..."},
    {"action":"buy","type":"call","strike":"...","expiry":"..."},
    {"action":"sell","type":"put","strike":"...","expiry":"..."},
    {"action":"buy","type":"put","strike":"...","expiry":"..."}
  ],
  "max_loss": "...", "profit_target": "...", "defense_rules": "...",
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

### Options — Swing

#### Options — Swing — Trend

##### Prompt: Options — Swing — Trend — Trend Rider With Debit Spread or Diagonal

**Description:** Swing trend options framework that selects **debit spread vs diagonal** based on IV context and trend trigger; requires chain across expiries.

```text
OBJECTIVE: Generate 1 swing TREND options setup for {symbol} using either a debit spread or diagonal, chosen by IV context.

REQUIRED DATA:
- Daily/Weekly trend, ATR, key levels, earnings date
- Options chain snapshot across multiple expiries + IV/IVR (if available)

RULES:
- If IV is high, prefer spreads/diagonals over naked long premium (state reasoning).
- No chain data → ask.

UNDERLYING TRIGGER:
- Daily breakout or pullback-to-MA continuation.

OUTPUT (JSON):
{ "symbol": "...", "bias": "long|short", "strategy": "debit_spread|diagonal",
  "underlying_trigger": "...", "entry_time": "...",
  "legs": [{"action":"...","type":"call|put","strike":"...","expiry":"..."}, {"action":"...","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "profit_plan": "...", "roll_rules": "...",
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

##### Prompt: Options — Swing — Trend — Protective Put / Collar (Risk-First)

**Description:** Hedging template for long stock exposure using **protective puts or collars**, emphasizing max loss, hedge cost, and roll/remove rules.

```text
OBJECTIVE: For a long stock thesis on {symbol}, produce a hedged swing plan using protective puts or a collar.

REQUIRED DATA:
- Stock entry thesis + timeframe, account constraints, options chain snapshot

RULES:
- Focus on risk containment: define worst-case loss, hedge cost, and when to remove/roll.

OUTPUT (JSON):
{ "symbol": "...", "strategy": "protective_put|collar",
  "stock_plan": {"entry_rule":"...", "stop_rule":"..."},
  "option_legs": [{"action":"...","type":"put|call","strike":"...","expiry":"..."}],
  "max_loss_estimate": "...", "hedge_cost": "...", "roll_rules": "...",
  "notes": "..." }
```

#### Options — Swing — Mean Reversion

##### Prompt: Options — Swing — Mean Reversion — High IV Mean Reversion (Premium Selling With Defined Risk)

**Description:** Swing mean reversion template that benefits from **IV normalization** (when IV is elevated) using defined-risk premium-selling structures.

```text
OBJECTIVE: When IV is elevated, generate 1 swing mean-reversion options idea that benefits from IV mean reversion (defined-risk only).

REQUIRED DATA:
- Daily context + expected range, IV rank/percentile (or IV vs 1y range), chain snapshot, earnings date

RULES:
- No IV context → ask for it.
- Avoid selling premium into binary events unless the plan is explicitly “earnings strategy”.

SETUP:
- Choose credit spread or iron condor aligned to a “range/mean reversion” thesis.
- Profit target, stop, and adjustment rules required.

OUTPUT (JSON):
{ "symbol": "...", "strategy": "credit_spread|iron_condor",
  "thesis": "range|mean_reversion", "entry_time": "...",
  "legs": [{"action":"...","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "profit_target": "...", "adjustment_rules": "...",
  "confluence_score": X, "confidence_pct": Y, "notes": "..." }
```

##### Prompt: Options — Swing — Mean Reversion — Earnings Volatility Crush (Event-Driven, Strict)

**Description:** Event-driven options prompt focused on **earnings volatility crush** dynamics; requires earnings timing + expected move/chain snapshot and mandates defined risk.

```text
OBJECTIVE: If {symbol} has earnings within N days, propose 1 earnings-specific options plan (defined risk) with explicit assumptions.

REQUIRED DATA:
- Earnings date/time, expected move (if available), chain snapshot, liquidity

RULES:
- If expected move/chain missing → ask.
- Must state: thesis (range vs directional), max loss, and why this structure fits IV crush dynamics.

OUTPUT (JSON):
{ "symbol": "...", "strategy": "defined_risk_earnings",
  "earnings_time": "...", "hold_through_earnings": true|false,
  "thesis": "range|directional", "expected_move": "...",
  "legs": [{"action":"...","type":"call|put","strike":"...","expiry":"..."}],
  "max_loss": "...", "profit_plan": "...", "risk_notes": "...",
  "confluence_score": X, "confidence_pct": Y }
```

---

## Meta / Utilities

### Prompt: Meta — Regime Selector (Picks Trend vs Mean Reversion Prompt)

**Description:** Classifies **intraday and swing regimes** (trend vs range vs mixed) and selects the best template; produces one setup only if score/confidence thresholds pass.

```text
OBJECTIVE: Given data for {symbol}, classify the current regime (trend vs range) for intraday and swing, then select the best matching setup template.

REQUIRED DATA:
- Intraday (M15/H1) + Daily data, VWAP, ATR, volume stats, and a market proxy (SPY/QQQ)

RULES:
- Output “NEEDED DATA” if anything required is missing.
- Produce: (1) regime classification, (2) which template to use, (3) one setup only if score/confidence thresholds pass.

OUTPUT (JSON):
{ "symbol": "...", "intraday_regime": "trend|range|mixed", "swing_regime": "trend|range|mixed",
  "recommended_template": "...", "setup": {... or "NO TRADE"}, "notes": "..." }
```

### Prompt: Meta — Multi-Symbol Scanner (1 Best Setup Across Watchlist)

**Description:** Chooses the **single best setup across a watchlist** under one category, excluding tickers with missing data and returning one winner only.

```text
OBJECTIVE: From a provided watchlist [{symbols}], find the single best setup across all symbols (stocks and/or options) under the chosen category.

REQUIRED DATA:
- For each symbol: the same OHLCV/indicator set used by the category prompt; plus options chain if options are allowed.

RULES:
- If any symbol lacks data, exclude it and list exclusions.
- Return only ONE setup total: highest confluence and confidence.

OUTPUT (JSON):
{ "winner_symbol": "...", "category": "...", "setup": {...},
  "excluded": [{"symbol":"...","missing":"..."}], "notes": "..." }
```

