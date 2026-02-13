Hybrid architecture (simple + scalable)

You will create 4 watchlist alerts total
	•	S&P 500: LONG + SHORT
	•	S&P 600: LONG + SHORT

…and each watchlist alert will use one indicator instance that’s tuned for that universe/timeframe/playbook.

Why only 4? Because watchlist alerts scan every symbol in the list—so you don’t need 500 separate alerts.

⸻

Step 1 — Build two watchlists
	1.	Watchlist A: S&P 500
	2.	Watchlist B: S&P 600

(If TradingView has built-in lists, use those. If not, import tickers.)

⸻

Step 2 — Add your script twice (two instances)

On any chart (pick a random symbol), add the indicator two times.

Instance #1 = Large Caps (S&P 500) — “LC”

Use the S&P 500 tuned values:

For 5m Day Trade Breakout (ORB)
	•	Style: Day Trade
	•	Playbook: Breakout
	•	Cap Profile: Large Cap
	•	ORB: ON
	•	ORB Bars: 3
	•	Skip bars after open: 3
	•	Min ATR% (Day): 0.45–0.60 (start 0.50)
	•	RVOL (Large): 1.20
	•	Volume spike mult: 1.15
	•	Market filter: ON
	•	RS filter: OFF

📌 Save these as an indicator template: “LC 5m ORB Breakout”

⸻

Instance #2 = Small Caps (S&P 600) — “SC600”

Use the S&P 600 tuned values:

For 5m Day Trade Breakout
	•	Style: Day Trade
	•	Playbook: Breakout
	•	Cap Profile: Small Cap
	•	ORB: optional (start ON)
	•	ORB Bars: 2–3 (start 2)
	•	Skip bars after open: 2
	•	Min ATR% (Day): 1.1
	•	RVOL (Small): 2.1
	•	Volume spike mult: 1.6
	•	Market filter: OFF
	•	RS filter: OFF

📌 Save as template: “SC600 5m Breakout”

⸻

What about your 15m + 4H pullback strategies?

Those are great — but here’s the catch:

A watchlist alert can only use one indicator configuration at a time.
So if you want both Breakout (5m) and Pullback (15m/4H) scanning the whole watchlist, you’ll add more instances and more alerts.

A practical hybrid that’s still manageable is:

Recommended “Full Hybrid” (8 alerts total)

For each universe (SP500 and SC600):
	•	5m Breakout LONG + SHORT (2 alerts)
	•	15m Pullback LONG + SHORT (2 alerts)

That’s 4 alerts per universe × 2 universes = 8 alerts total.

Most people stop there because 4H swing alerts on the whole index can be too many unless you tighten heavily.

⸻

Step 3 — Add the Pullback instances (recommended)

Add two more instances of the indicator:

Instance #3 = Large Caps 15m Pullback (LC 15m)
	•	Style: Intraday Swing
	•	Playbook: Pullback
	•	Pullback ref: VWAP
	•	Need reclaim: ON
	•	Volume contraction: ON
	•	Skip bars: 2
	•	Min ATR%: 0.70
	•	RVOL (Large): 1.20
	•	Volume spike mult: 1.10–1.15
	•	Market filter: ON
	•	RS filter: ON

Template name: “LC 15m Pullback”

⸻

Instance #4 = Small Caps 15m Pullback (SC600 15m)
	•	Style: Intraday Swing
	•	Playbook: Pullback
	•	Pullback ref: VWAP
	•	Need reclaim: ON
	•	Volume contraction: ON
	•	Skip bars: 1
	•	Min ATR%: 1.6
	•	RVOL (Small): 1.7
	•	Volume spike mult: 1.3
	•	Market filter: optional (start OFF)

Template name: “SC600 15m Pullback”

⸻

Step 4 — Create watchlist alerts (the “scanner” part)

A) S&P 500 watchlist alerts

Create these 4 alerts:
	1.	LC 5m Breakout — LONG Signal
Custom message:
LC SP500 5m ORB BREAKOUT LONG | {{ticker}} | Close={{close}}
	2.	LC 5m Breakout — SHORT Signal
LC SP500 5m ORB BREAKOUT SHORT | {{ticker}} | Close={{close}}
	3.	LC 15m Pullback — LONG Signal
LC SP500 15m PULLBACK LONG | {{ticker}} | Close={{close}}
	4.	LC 15m Pullback — SHORT Signal
LC SP500 15m PULLBACK SHORT | {{ticker}} | Close={{close}}

B) S&P 600 watchlist alerts

Same 4 alerts but referencing the SC600 indicator instances:
	5.	SC600 5m Breakout — LONG Signal
SC600 5m BREAKOUT LONG | {{ticker}} | Close={{close}}
	6.	SC600 5m Breakout — SHORT Signal
SC600 5m BREAKOUT SHORT | {{ticker}} | Close={{close}}
	7.	SC600 15m Pullback — LONG Signal
SC600 15m PULLBACK LONG | {{ticker}} | Close={{close}}
	8.	SC600 15m Pullback — SHORT Signal
SC600 15m PULLBACK SHORT | {{ticker}} | Close={{close}}

How to create the watchlist alert
	•	Open Watchlist panel → menu → Add alert on list
	•	Select the watchlist (SP500 or SP600)
	•	Condition: choose the correct indicator instance → LONG Signal (then create another for SHORT)
	•	Once per bar close ✅
	•	Create

⸻

Step 5 — Optional: add 4H swing alerts (only if you want fewer, higher-quality pings)

If you do add 4H, tighten hard:
	•	SP500 4H min ATR%: 1.2–1.5, RS+Market ON
	•	SC600 4H min ATR%: 2.0–2.6, ADX 20+, RVOL ~1.25

Otherwise you’ll get too many “meh” swing alerts.

⸻

Quick “signal quality” knobs

If alerts are too noisy:
	•	Raise min ATR% by +0.2
	•	Raise RVOL by +0.1–0.3
	•	Turn Market filter ON (large caps)
	•	Increase skip bars by +1

If alerts are too quiet:
	•	Lower min ATR% by -0.2
	•	Lower RVOL by -0.1–0.2
