The composite score is a weighted average of 4 sub-scores (5 when sentiment is enabled), each scored 0-100, producing a final 0-100 result.

Weighting Schemes
Default (no sentiment):

Component	Weight
Fundamental	40%
Technical	30%
Options	20%
Momentum	10%
With Sentiment (Phase 2):

Component	Weight
Fundamental	35%
Technical	25%
Options	15%
Momentum	10%
Sentiment	15%
Note: the weights you mentioned (35/25/15/10) match the with-sentiment scheme. The current default (without sentiment) is actually 40/30/20/10.

1. Fundamental Score (0-100 pts)
File: fundamental.py

Metric	Max Pts	Scoring Tiers
Revenue Growth	30	>50% = 30, >30% = 20, >20% = 10
Earnings Growth	30	>50% = 30, >30% = 20, >15% = 10
Profit Margins	20	>20% = 20, >10% = 10
Balance Sheet	10	D/E <50% & CR >2.0 = 10, D/E <100% & CR >1.5 = 5
ROE	10	>20% = 10, >15% = 5
Hard screening gates (must pass before scoring):

Market cap $500M-$50B and price $5-$500 (mandatory)
Need 3 of 5 remaining criteria: revenue growth >20%, earnings growth >15%, D/E <150%, current ratio >1.2, sector in growth list
2. Technical Score (0-90 pts)
File: engine.py (lines 347-398)

Component	Max Pts	Scoring
Trend Alignment	25	Price > SMA20 > SMA50 > SMA200 = 25, Price > SMA50 > SMA200 = 15
RSI Positioning	20	50-65 = 20, 40-50 or 65-70 = 10
MACD Momentum	20	MACD > Signal & Hist > 0 = 20, MACD > Signal = 10
Volume Strength	20	Vol > 1.5x avg = 20, Vol > 1.2x avg = 10
Breakout Detection	15	Price > 60-day resistance x 1.01 = 15 (bonus)
Note: max is 90 (not 100) because breakout is a bonus — a stock in a perfect uptrend without a breakout caps at 85.

Hard screening gates: Need 3 of 7 criteria (uptrend, RSI OK, MACD bullish, volume above avg, breakout, ATR/price >3%, ADX >25)

3. Options Score (0-100 pts)
File: options.py (lines 105-177)

Component	Max Pts	Scoring
IV Rank	30	IV <30% = 30, <50% = 20, <70% = 10
Liquidity	25	OI >500 & Vol >100 = 25, OI >200 & Vol >50 = 15, OI >100 = 10
Spread Tightness	20	Spread <5% mid = 20, <10% = 10
Premium Efficiency	25	Premium <5% stock = 25, <10% = 15, <15% = 10
IV Rank adjustment (from TastyTrade enhanced data):

IV Rank <20: +15 bonus pts
IV Rank 20-40: +10 bonus pts
IV Rank 70-85: -10 penalty
IV Rank >85: -20 penalty
Low IV is better for LEAPS buyers (cheaper options).

Hard screening gates: Need 2 of 4 criteria (IV <70%, OI >100, spread <10%, premium <15% of stock)

4. Momentum Score (0-100 pts)
File: engine.py (lines 400-436)

Period	Max Pts	Scoring
1-Month	30	>15% = 30, >10% = 20, >5% = 10
3-Month	30	>30% = 30, >20% = 20, >10% = 10
1-Year	40	>50% = 40, >30% = 25, >10% = 10
Returns are calculated from historical price data using standard trading-day counts (21/63/126/252 days).

Pipeline Flow

screen_single_stock(symbol)
│
├─ STAGE 1: Fundamental Filter (hard gate)
│  ├─ Market cap + price check (mandatory)
│  ├─ 5 criteria, need ≥3 to pass
│  └─ → fundamental_score (0-100)
│
├─ STAGE 2: Technical Filter (hard gate)
│  ├─ 1-year price data → SMA, RSI, MACD, ATR, ADX
│  ├─ 7 criteria, need ≥3 to pass
│  └─ → technical_score (0-90)
│
├─ STAGE 3: Options Filter (hard gate)
│  ├─ Options chain → LEAPS 365-730 DTE
│  ├─ 4 criteria, need ≥2 to pass
│  └─ → options_score (0-100)
│
├─ STAGE 4: Momentum (no gate)
│  ├─ 1m/3m/1y returns
│  └─ → momentum_score (0-100)
│
└─ STAGE 5: Composite
   └─ weighted_sum → score (0-100)
Each stage is a hard gate — if a stock fails at Stage 1, it never reaches Stage 2. Only stocks passing all 3 gates get a composite score. Failed stocks get passed_all = False with failed_at indicating which stage rejected them.

Example Calculation
A stock with scores: Fundamental=75, Technical=60, Options=80, Momentum=50

Default weights: (75 × 0.40) + (60 × 0.30) + (80 × 0.20) + (50 × 0.10) = 30 + 18 + 16 + 5 = 69

Design Observations
A few things worth noting as you review:

Technical max is 90, not 100 — the breakout bonus means non-breakout stocks cap at 85, which slightly compresses the technical component relative to other sub-scores that go to 100.

Fundamental criteria gate is lenient — only 3 of 5 needed, so a high-growth company with poor balance sheet still passes.

Options score rewards cheap IV — this aligns with LEAPS buying strategy (buy when vol is low), but could penalize names with structurally higher IV that are still good candidates.

Momentum has no negative scoring — a stock down 30% in a year scores 0, same as one down 5%. No distinction between mild weakness and severe decline.