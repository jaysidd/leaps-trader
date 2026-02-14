#!/usr/bin/env python3
"""
Historical Replay — replay a past trading day through the real pipeline.

Uses Alpaca Historical API to pre-fetch bars, then advances a simulated clock
bar-by-bar, running the REAL signal engine + risk gateway code at each tick.

Usage:
  cd backend && source venv/bin/activate
  python3 scripts/replay/replay_trading_day.py 2026-02-10
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --symbols AAPL,NVDA,SSRM
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --interval 15
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --no-cleanup
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --equity 50000
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --skip-screening
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --no-ai --no-risk-check
"""
import sys
import os
import argparse
import asyncio
import time
import uuid
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from replay_services import (
    ReplayClock,
    DatetimeProxy,
    ReplayDataService,
    ReplayTradingService,
    ReplayMarketIntelligence,
    ET,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI Colors (same as diagnose_pipeline.py)
# ═══════════════════════════════════════════════════════════════════════════════
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(title: str):
    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}")


def section(title: str):
    print(f"\n  {CYAN}── {title} {'─' * max(1, 56 - len(title))}{RESET}")


def timed(fn, *args, **kwargs):
    t0 = time.time()
    res = fn(*args, **kwargs)
    elapsed = (time.time() - t0) * 1000
    return res, elapsed


# ═══════════════════════════════════════════════════════════════════════════════
# Argument Parsing
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="Replay a past trading day through the real signal pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/replay/replay_trading_day.py 2026-02-10
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --symbols AAPL,NVDA
  python3 scripts/replay/replay_trading_day.py 2026-02-10 --interval 15 --equity 50000
        """,
    )
    p.add_argument("date", help="Trading date to replay (YYYY-MM-DD)")
    p.add_argument("--symbols", "-s", help="Comma-separated symbols (default: use DB queue)")
    p.add_argument("--interval", "-i", type=int, default=5,
                   help="Clock advance interval in minutes (default: 5)")
    p.add_argument("--equity", type=float, default=100_000,
                   help="Starting equity in dollars (default: 100000)")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Keep replay records in DB after completion")
    p.add_argument("--start-time", default="09:30",
                   help="Start time in HH:MM ET (default: 09:30)")
    p.add_argument("--end-time", default="15:55",
                   help="End time in HH:MM ET (default: 15:55)")
    p.add_argument("--timeframes", default="5m,1h",
                   help="Timeframes for signal queue items (default: 5m,1h)")
    p.add_argument("--skip-screening", action="store_true",
                   help="Skip screening — push all symbols directly to signal queue")
    p.add_argument("--no-ai", action="store_true",
                   help="Skip AI validation — use signal engine confidence directly")
    p.add_argument("--no-risk-check", action="store_true",
                   help="Skip Risk Gateway checks — execute all signals")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Verbose logging (show all quality gate details)")
    return p.parse_args()


def parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"{RED}Invalid date format: {date_str}. Use YYYY-MM-DD{RESET}")
        sys.exit(1)


def parse_time(time_str: str):
    """Parse HH:MM into (hour, minute) tuple."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


# ═══════════════════════════════════════════════════════════════════════════════
# Database Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def create_replay_queue_items(db, symbols: List[str], timeframes: List[str]) -> List:
    """Create tagged SignalQueue items for replay symbols."""
    from app.models.signal_queue import SignalQueue

    items = []
    for symbol in symbols:
        for tf in timeframes:
            item = SignalQueue(
                symbol=symbol.upper(),
                timeframe=tf,
                strategy="auto",
                status="active",
                source="replay",
                times_checked=0,
                signals_generated=0,
            )
            db.add(item)
            items.append(item)

    db.commit()

    # Refresh to get IDs
    for item in items:
        db.refresh(item)

    return items


def cleanup_replay_records(db, cleanup_audit=False):
    """Remove all replay-tagged records from the database."""
    from app.models.signal_queue import SignalQueue
    from app.models.trading_signal import TradingSignal

    sig_count = db.query(TradingSignal).filter(TradingSignal.source == "replay").delete()
    q_count = db.query(SignalQueue).filter(SignalQueue.source == "replay").delete()
    db.commit()
    return q_count, sig_count


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Logging
# ═══════════════════════════════════════════════════════════════════════════════

def log_audit(
    db, session_id: str, replay_date: str, clock,
    stage: str, decision: dict,
    symbol: str = None, passed: bool = None,
    score: float = None, reasoning: str = None,
):
    """Write a single audit log entry."""
    from app.models.replay_audit_log import ReplayAuditLog

    entry = ReplayAuditLog(
        replay_session_id=session_id,
        replay_date=replay_date,
        simulated_time=clock.current_time_et if clock else None,
        stage=stage,
        symbol=symbol,
        decision=decision,
        passed=passed,
        score=score,
        reasoning=reasoning,
    )
    db.add(entry)
    db.flush()
    return entry


# ═══════════════════════════════════════════════════════════════════════════════
# Datetime Patching
# ═══════════════════════════════════════════════════════════════════════════════

_original_datetimes = {}


def install_datetime_patches(clock: ReplayClock):
    """Patch datetime.now() in signal_engine and risk_gateway modules."""
    import sys

    # Get the actual MODULE objects (not the singleton instances)
    se_module = sys.modules.get("app.services.signals.signal_engine")
    rg_module = sys.modules.get("app.services.trading.risk_gateway")

    if se_module is None:
        import app.services.signals.signal_engine
        se_module = sys.modules["app.services.signals.signal_engine"]
    if rg_module is None:
        import app.services.trading.risk_gateway
        rg_module = sys.modules["app.services.trading.risk_gateway"]

    real_dt = datetime  # the real datetime class
    proxy = DatetimeProxy(clock, real_dt)

    _original_datetimes["signal_engine"] = getattr(se_module, "datetime", real_dt)
    _original_datetimes["risk_gateway"] = getattr(rg_module, "datetime", real_dt)
    _original_datetimes["_se_module"] = se_module
    _original_datetimes["_rg_module"] = rg_module

    se_module.datetime = proxy
    rg_module.datetime = proxy


def uninstall_datetime_patches():
    """Restore original datetime in patched modules."""
    se_module = _original_datetimes.get("_se_module")
    rg_module = _original_datetimes.get("_rg_module")

    if se_module and "signal_engine" in _original_datetimes:
        se_module.datetime = _original_datetimes["signal_engine"]
    if rg_module and "risk_gateway" in _original_datetimes:
        rg_module.datetime = _original_datetimes["risk_gateway"]

    _original_datetimes.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Position Monitoring (SL / TP checks)
# ═══════════════════════════════════════════════════════════════════════════════

def check_position_exits(
    trading_svc: ReplayTradingService,
    data_svc: ReplayDataService,
    signals_by_symbol: Dict[str, dict],
) -> List[Dict]:
    """
    Check each open position against its signal's stop_loss and target_1.
    Returns list of exit fills.
    """
    exits = []
    for symbol in list(trading_svc.positions.keys()):
        pos = trading_svc.positions.get(symbol)
        if pos is None:
            continue

        bar = data_svc._get_last_bar(symbol, "5m")
        if bar is None:
            continue

        current_price = float(bar.get("close", 0))
        low = float(bar.get("low", current_price))
        high = float(bar.get("high", current_price))

        sig = signals_by_symbol.get(symbol, {})
        stop_loss = sig.get("stop_loss")
        target = sig.get("target_1")

        exit_reason = None
        exit_price = None

        # Check stop loss (price dropped below SL)
        if stop_loss and low <= stop_loss:
            exit_reason = "STOP_LOSS"
            exit_price = stop_loss

        # Check take profit (price exceeded target)
        elif target and high >= target:
            exit_reason = "TAKE_PROFIT"
            exit_price = target

        if exit_reason and exit_price:
            order = {
                "id": f"exit-{symbol[:4].lower()}",
                "symbol": symbol,
                "qty": pos["qty"],
                "side": "sell",
                "type": "market",
                "status": "pending_fill",
            }
            fill = trading_svc._execute_fill(order, exit_price)
            fill["reason"] = exit_reason
            trading_svc.all_orders.append(order)
            exits.append(fill)

    return exits


# ═══════════════════════════════════════════════════════════════════════════════
# Pretty-Print Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def print_signal(signal, prefix="  "):
    """Pretty-print a TradingSignal object."""
    conf = signal.confidence_score or 0
    entry = signal.entry_price or 0
    sl = signal.stop_loss or 0
    tgt = signal.target_1 or 0
    rr = signal.risk_reward_ratio or 0

    color = GREEN if conf >= 75 else YELLOW if conf >= 62 else RED
    print(
        f"{prefix}{BOLD}{signal.symbol}{RESET} {signal.timeframe} "
        f"{signal.strategy}: "
        f"conf={color}{conf:.0f}{RESET}  "
        f"entry=${entry:.2f}  SL=${sl:.2f}  T1=${tgt:.2f}  "
        f"R:R={rr:.1f}"
    )


def print_fill(fill, prefix="  "):
    """Pretty-print a fill dict."""
    side_color = GREEN if fill["side"] == "buy" else RED
    reason = fill.get("reason", "")
    reason_str = f"  ({reason})" if reason else ""
    print(
        f"{prefix}{side_color}{fill['side'].upper()}{RESET} "
        f"{fill['symbol']} "
        f"{fill['qty']}x @ ${fill['price']:.2f} "
        f"(${fill['notional']:.2f})"
        f"{reason_str}"
    )


def print_positions(trading_svc: ReplayTradingService, prefix="  "):
    """Print current open positions with unrealized P/L."""
    if not trading_svc.positions:
        print(f"{prefix}{DIM}No open positions{RESET}")
        return

    for sym, pos in trading_svc.positions.items():
        pl = pos.get("unrealized_pl", 0)
        pl_pct = pos.get("unrealized_plpc", 0) * 100
        color = GREEN if pl >= 0 else RED
        print(
            f"{prefix}{BOLD}{sym}{RESET}: "
            f"${pos['avg_price']:.2f} → ${pos.get('current_price', 0):.2f}  "
            f"{color}{pl:+.2f} ({pl_pct:+.1f}%){RESET}  "
            f"qty={pos['qty']}"
        )


def print_day_summary(
    trading_svc: ReplayTradingService,
    all_signals: list,
    all_exits: list,
    replay_date: date,
    start_equity: float,
    ai_rejected: int = 0,
    risk_rejected: int = 0,
):
    """Print end-of-day summary."""
    header(f"Day Summary — {replay_date.strftime('%A %Y-%m-%d')}")

    total_fills = trading_svc.fills
    buys = [f for f in total_fills if f["side"] == "buy"]
    sells = [f for f in total_fills if f["side"] == "sell"]

    # Compute realized P/L from sells
    realized_pl = 0
    wins = 0
    losses = 0
    for sell in sells:
        # Find matching buy
        sym = sell["symbol"]
        buy_price = None
        for buy in buys:
            if buy["symbol"] == sym:
                buy_price = buy["price"]
                break
        if buy_price:
            trade_pl = (sell["price"] - buy_price) * sell["qty"]
            realized_pl += trade_pl
            if trade_pl >= 0:
                wins += 1
            else:
                losses += 1

    total_trades = len(buys)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    final_equity = trading_svc.equity

    section("Signals")
    print(f"  Generated:      {len(all_signals)}")
    if ai_rejected:
        print(f"  AI rejected:    {RED}{ai_rejected}{RESET}")
    if risk_rejected:
        print(f"  Risk rejected:  {RED}{risk_rejected}{RESET}")
    print(f"  Executed (buy):  {len(buys)}")

    section("Trades")
    if total_trades > 0:
        print(f"  Wins:     {GREEN}{wins}{RESET}")
        print(f"  Losses:   {RED}{losses}{RESET}")
        print(f"  Win rate: {win_rate:.0f}%")
    else:
        print(f"  {DIM}No trades executed{RESET}")

    # Exits by reason
    sl_exits = [e for e in all_exits if e.get("reason") == "STOP_LOSS"]
    tp_exits = [e for e in all_exits if e.get("reason") == "TAKE_PROFIT"]
    eod_exits = [e for e in all_exits if e.get("reason") == "EOD_CLOSE"]
    if sl_exits or tp_exits or eod_exits:
        section("Exits")
        if tp_exits:
            print(f"  Take profit: {GREEN}{len(tp_exits)}{RESET}")
        if sl_exits:
            print(f"  Stop loss:   {RED}{len(sl_exits)}{RESET}")
        if eod_exits:
            print(f"  EOD close:   {YELLOW}{len(eod_exits)}{RESET}")

    section("P/L")
    pl_color = GREEN if realized_pl >= 0 else RED
    eq_color = GREEN if final_equity >= start_equity else RED
    print(f"  Realized P/L:   {pl_color}${realized_pl:+.2f}{RESET}")
    print(f"  Final equity:   {eq_color}${final_equity:,.2f}{RESET}")
    print(f"  Starting equity: ${start_equity:,.2f}")

    print(f"\n{'═' * 70}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN REPLAY LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_replay(args):
    """Execute the full replay."""

    replay_date = parse_date(args.date)
    start_h, start_m = parse_time(args.start_time)
    end_h, end_m = parse_time(args.end_time)
    interval = args.interval
    equity = args.equity
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    verbose = args.verbose

    # Determine symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        # Pull from existing active queue items
        from app.database import SessionLocal
        from app.models.signal_queue import SignalQueue
        db = SessionLocal()
        items = db.query(SignalQueue).filter(
            SignalQueue.status == "active",
            SignalQueue.source != "replay",
        ).all()
        symbols = list(set(i.symbol for i in items))
        db.close()
        if not symbols:
            print(f"{RED}No symbols specified and no active queue items found.{RESET}")
            print(f"Usage: python3 scripts/replay/replay_trading_day.py {args.date} --symbols AAPL,NVDA")
            sys.exit(1)

    day_name = replay_date.strftime("%A")

    header(f"Historical Replay: {replay_date} ({day_name})")
    print(f"  Symbols:   {', '.join(symbols)}")
    print(f"  Interval:  {interval}min")
    print(f"  Equity:    ${equity:,.2f}")
    print(f"  Window:    {args.start_time} → {args.end_time} ET")
    print(f"  Timeframes: {', '.join(timeframes)}")

    # ── 1. Initialize Services ──────────────────────────────────────────────

    section("Initializing")

    clock = ReplayClock(replay_date, start_h, start_m)

    # Add market intelligence symbols (VIX, SPY) for regime/F&G calculation
    # These are needed for PresetSelector but NOT for signal queue
    intel_symbols = ["SPY"]  # VIX uses get_historical_prices with ^VIX symbol
    all_prefetch_symbols = list(set(symbols + intel_symbols))

    data_svc = ReplayDataService(clock, all_prefetch_symbols, timeframes=["5m", "1h", "1d"])
    trading_svc = ReplayTradingService(clock, equity)

    # Pre-fetch all bars
    print(f"  Loading historical bars from Alpaca (+ SPY for market intelligence)...")
    total_bars, fetch_ms = timed(data_svc.prefetch_bars)
    print(f"  {GREEN}✅ {total_bars:,} bars loaded across {len(symbols)} symbols ({fetch_ms:.0f}ms){RESET}")

    if total_bars == 0:
        print(f"\n  {RED}No bars returned — is {replay_date} a trading day? Check Alpaca API keys.{RESET}")
        sys.exit(1)

    # Install patches
    print(f"  Installing monkey-patches...")
    data_svc.install_patches()
    trading_svc.install_patches()
    install_datetime_patches(clock)
    print(f"  {GREEN}✅ bars  ✅ snapshot  ✅ clock  ✅ account  ✅ datetime{RESET}")

    # ── 2. Create DB Records + Market Intelligence ───────────────────────────

    from app.database import SessionLocal
    from app.services.signals.signal_engine import signal_engine

    db = SessionLocal()

    # Generate audit session ID
    session_id = str(uuid.uuid4())
    replay_date_str = str(replay_date)

    try:
        queue_items = create_replay_queue_items(db, symbols, timeframes)
        print(f"  {GREEN}✅ Created {len(queue_items)} queue items (source=replay){RESET}")

        # ── 2b. Load & Patch Market Intelligence ─────────────────────────────

        section("Market Intelligence (PresetSelector)")

        intel_svc = ReplayMarketIntelligence(clock, db)
        intel_results = intel_svc.load_historical_intelligence(data_svc)
        intel_svc.install_patches()

        # Report what we found
        mri_info = intel_results.get("mri", {})
        if mri_info and mri_info.get("score") is not None:
            print(f"  MRI:       {GREEN}✅ score={mri_info['score']}, "
                  f"regime={mri_info.get('regime', '?')} (from {mri_info.get('source', '?')}){RESET}")
        else:
            print(f"  MRI:       {YELLOW}⚠️  Not available for {replay_date} "
                  f"(PresetSelector will use other signals){RESET}")

        print(f"  Regime:    {GREEN}✅ Will compute from historical VIX/SPY{RESET}")
        print(f"  F&G:       {GREEN}✅ Will compute from historical VIX (fallback){RESET}")
        print(f"  Readiness: {GREEN}✅ Will compute with available components{RESET}")

        # ── 2c. Run PresetSelector ───────────────────────────────────────────

        section("PresetSelector Decision")

        try:
            preset_result = asyncio.get_event_loop().run_until_complete(
                intel_svc.run_preset_selector(db)
            )
        except RuntimeError:
            # No event loop running — create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                preset_result = loop.run_until_complete(
                    intel_svc.run_preset_selector(db)
                )
            finally:
                loop.close()

        condition = preset_result["condition"]
        presets = preset_result["presets"]
        composite = preset_result.get("composite_score", 0)
        reasoning = preset_result.get("reasoning", "")
        snapshot = preset_result.get("market_snapshot", {})

        # Color-code condition
        cond_colors = {
            "aggressive_bull": GREEN,
            "moderate_bull": GREEN,
            "neutral": YELLOW,
            "cautious": YELLOW,
            "defensive": RED,
            "skip": RED,
        }
        cond_color = cond_colors.get(condition, RESET)

        print(f"\n  Condition:  {cond_color}{BOLD}{condition}{RESET} "
              f"(composite: {composite:+.1f}/100)")
        print(f"  Presets:    {CYAN}{', '.join(presets) if presets else '(none — skip mode)'}{RESET}")
        print(f"  Reasoning:  {DIM}{reasoning}{RESET}")

        # Print detailed signal breakdown
        print(f"\n  {DIM}── Signal Breakdown ──{RESET}")
        for key in ["mri", "regime", "fear_greed", "readiness"]:
            val = snapshot.get(key)
            label_map = {
                "mri": "MRI Score",
                "regime": "Regime",
                "fear_greed": "Fear & Greed",
                "readiness": "Readiness",
            }
            if val is not None:
                print(f"  {label_map[key]:15s}: {val}")
            else:
                print(f"  {label_map[key]:15s}: {DIM}unavailable{RESET}")

        # ── Audit: Log PresetSelector decision ──
        log_audit(
            db, session_id, replay_date_str, clock,
            stage="preset_selection",
            decision={
                "condition": condition,
                "presets": presets,
                "composite_score": composite,
                "market_snapshot": {
                    k: v for k, v in snapshot.items()
                    if k != "timestamp"  # avoid datetime serialization issues
                },
                "reasoning": reasoning,
                "intel_sources": intel_results,
            },
            passed=condition != "skip",
            score=composite,
            reasoning=reasoning,
        )
        db.commit()
        print(f"\n  {GREEN}✅ PresetSelector decision logged to audit trail{RESET}")

        if condition == "skip":
            print(f"\n  {RED}{BOLD}PresetSelector says SKIP — extreme fear conditions.{RESET}")
            print(f"  {RED}No scanning would occur on this day. Ending replay.{RESET}")

            # Log summary and exit (cleanup handled by finally block)
            log_audit(
                db, session_id, replay_date_str, clock,
                stage="summary",
                decision={
                    "outcome": "skipped",
                    "reason": "preset_selector_skip",
                    "condition": condition,
                    "composite_score": composite,
                },
                passed=False,
                score=0,
                reasoning="PresetSelector classified conditions as skip — no trades",
            )
            db.commit()
            return  # finally block handles cleanup

        # ── 2d. Screening ─────────────────────────────────────────────────

        screened_symbols = list(symbols)  # default: all symbols pass

        if not args.skip_screening:
            section("Screening Engine")

            from app.services.screening.engine import ScreeningEngine
            from app.data.presets_catalog import LEAPS_PRESETS, resolve_preset

            screening_engine = ScreeningEngine()

            # Pick the FIRST preset for screening criteria
            # (PresetSelector may return multiple — use primary)
            primary_preset = presets[0] if presets else "moderate"
            preset_data = resolve_preset(primary_preset, source="replay", strict=False)
            if not preset_data:
                print(f"  {YELLOW}WARNING: Unknown preset '{primary_preset}', using 'moderate'{RESET}")
                preset_data = LEAPS_PRESETS["moderate"]
            # Strip 'description' key — not a screening parameter
            screening_criteria = {
                k: v for k, v in preset_data.items() if k != "description"
            }

            print(f"  Preset:   {CYAN}{primary_preset}{RESET}")
            print(f"  Criteria: market_cap_min={screening_criteria.get('market_cap_min', 'N/A')}, "
                  f"price={screening_criteria.get('price_min', '?')}-{screening_criteria.get('price_max', '?')}, "
                  f"rsi={screening_criteria.get('rsi_min', '?')}-{screening_criteria.get('rsi_max', '?')}")
            print(f"  Screening {len(symbols)} symbols...")

            screening_results = []
            passed_symbols = []
            failed_details = []

            for sym in symbols:
                try:
                    result = screening_engine.screen_single_stock(sym, screening_criteria)
                    screening_results.append(result)

                    if result and result.get("passed_all"):
                        passed_symbols.append(sym)
                        score = result.get("score", 0)
                        print(f"    {GREEN}✅ {sym}{RESET}: score={score:.1f}  "
                              f"stages={', '.join(result.get('passed_stages', []))}")

                        # Audit: log screening pass
                        log_audit(
                            db, session_id, replay_date_str, clock,
                            stage="screening",
                            symbol=sym,
                            decision={
                                "preset": primary_preset,
                                "passed_all": True,
                                "score": round(score, 2),
                                "passed_stages": result.get("passed_stages", []),
                                "component_availability": result.get("component_availability", {}),
                                "fundamental_score": result.get("fundamental_score"),
                                "technical_score": result.get("technical_score"),
                                "options_score": result.get("options_score"),
                                "momentum_score": result.get("momentum_score"),
                            },
                            passed=True,
                            score=round(score, 2),
                            reasoning=f"Passed all gates, composite={score:.1f}",
                        )
                    else:
                        failed_at = result.get("failed_at", "unknown") if result else "no_data"
                        failed_details.append((sym, failed_at))
                        print(f"    {RED}✗ {sym}{RESET}: failed at {YELLOW}{failed_at}{RESET}")

                        # Audit: log screening fail
                        log_audit(
                            db, session_id, replay_date_str, clock,
                            stage="screening",
                            symbol=sym,
                            decision={
                                "preset": primary_preset,
                                "passed_all": False,
                                "failed_at": failed_at,
                                "score": result.get("score", 0) if result else 0,
                                "passed_stages": result.get("passed_stages", []) if result else [],
                            },
                            passed=False,
                            score=result.get("score", 0) if result else 0,
                            reasoning=f"Failed at {failed_at}",
                        )

                except Exception as e:
                    failed_details.append((sym, f"error: {e}"))
                    print(f"    {RED}✗ {sym}{RESET}: {RED}error: {e}{RESET}")

                    log_audit(
                        db, session_id, replay_date_str, clock,
                        stage="screening",
                        symbol=sym,
                        decision={
                            "preset": primary_preset,
                            "passed_all": False,
                            "failed_at": "error",
                            "error": str(e),
                        },
                        passed=False,
                        score=0,
                        reasoning=f"Screening error: {e}",
                    )

            db.flush()

            # Summary
            print(f"\n  Results: {GREEN}{len(passed_symbols)} passed{RESET} / "
                  f"{RED}{len(failed_details)} failed{RESET} / "
                  f"{len(symbols)} total")

            if passed_symbols:
                screened_symbols = passed_symbols
                print(f"  Continuing with: {CYAN}{', '.join(screened_symbols)}{RESET}")
            else:
                print(f"\n  {RED}{BOLD}No symbols passed screening — "
                      f"no signals would be generated.{RESET}")
                print(f"  {YELLOW}Tip: Use --skip-screening to bypass and test "
                      f"signal engine directly.{RESET}")

                # Log summary and exit (cleanup handled by finally block)
                log_audit(
                    db, session_id, replay_date_str, clock,
                    stage="summary",
                    decision={
                        "outcome": "no_screening_passes",
                        "condition": condition,
                        "preset": primary_preset,
                        "symbols_screened": len(symbols),
                        "symbols_passed": 0,
                        "failed_details": [
                            {"symbol": s, "reason": r} for s, r in failed_details
                        ],
                    },
                    passed=False,
                    score=0,
                    reasoning=f"0/{len(symbols)} symbols passed screening with {primary_preset}",
                )
                db.commit()
                return  # finally block handles cleanup
        else:
            print(f"\n  {YELLOW}⏭️  --skip-screening: all {len(symbols)} symbols "
                  f"passed to signal queue{RESET}")

        # ── 2e. Rebuild Queue with Screened Symbols ───────────────────────

        # If screening filtered symbols, rebuild the queue
        if set(screened_symbols) != set(symbols):
            # Remove queue items for symbols that didn't pass
            removed_symbols = set(symbols) - set(screened_symbols)
            from app.models.signal_queue import SignalQueue

            for item in list(queue_items):
                if item.symbol in removed_symbols:
                    db.delete(item)
                    queue_items.remove(item)
            db.flush()
            print(f"  {DIM}Removed {len(removed_symbols)} symbols from queue: "
                  f"{', '.join(sorted(removed_symbols))}{RESET}")

        # ── 2f. Initialize Pipeline Services ──────────────────────────────

        from app.services.trading.risk_gateway import RiskGateway
        from app.services.trading.position_sizer import PositionSizer

        risk_gw = RiskGateway(db)
        pos_sizer = PositionSizer()

        # Build a virtual BotConfiguration for replay
        replay_bot_config = type("BotConfig", (), {
            "execution_mode": "full_auto",
            "max_trades_per_day": 10,
            "max_daily_loss": equity * 0.02,           # 2% daily loss limit
            "max_concurrent_positions": 5,
            "max_per_stock_trade": min(equity * 0.05, 500),  # 5% or $500
            "max_per_options_trade": 500,
            "max_portfolio_allocation_pct": 5.0,
            "max_total_invested_pct": 80.0,
            "min_confidence_to_execute": 62,
            "require_ai_analysis": False,
            "enabled_strategies": [
                "trend_following", "mean_reversion", "range_breakout",
                "vwap_pullback", "orb_breakout",
            ],
            "sizing_mode": "FIXED_DOLLAR",
            "risk_pct_per_trade": 1.0,
            "max_bid_ask_spread_pct": 15.0,
            "min_option_oi": 100,
            "cb_warn_pct": 1.0,
            "cb_pause_pct": 1.5,
            "cb_halt_pct": 2.0,
        })()

        # Build a virtual BotState for replay
        replay_bot_state = type("BotState", (), {
            "status": "RUNNING",
            "daily_trades_count": 0,
            "daily_pl": 0.0,
            "open_positions_count": 0,
            "circuit_breaker_level": "NONE",
        })()

        # Initialize AI validator if not bypassed
        ai_validator = None
        if not args.no_ai:
            try:
                from app.services.signals.signal_validator import SignalValidator
                ai_validator = SignalValidator()
                print(f"  {GREEN}✅ AI Validator initialized (Claude will review signals){RESET}")
            except Exception as e:
                print(f"  {YELLOW}⚠️  AI Validator not available: {e}. "
                      f"Using signal confidence directly.{RESET}")
                ai_validator = None
        else:
            print(f"  {YELLOW}⏭️  --no-ai: AI validation bypassed{RESET}")

        if not args.no_risk_check:
            print(f"  {GREEN}✅ Risk Gateway initialized (16 checks){RESET}")
        else:
            print(f"  {YELLOW}⏭️  --no-risk-check: Risk Gateway bypassed{RESET}")

        # ── 3. Main Replay Loop ─────────────────────────────────────────────

        end_time_et = datetime(
            replay_date.year, replay_date.month, replay_date.day,
            end_h, end_m, tzinfo=ZoneInfo("America/New_York"),
        )

        all_signals = []        # TradingSignal objects
        all_exits = []          # exit fill dicts
        signals_by_symbol = {}  # symbol → {stop_loss, target_1} for position monitoring
        tick_count = 0
        max_drawdown = 0
        peak_equity = equity
        risk_rejected = 0       # count of risk-rejected signals
        ai_rejected = 0         # count of AI-rejected signals

        print(f"\n  {BOLD}{clock.time_str()}{RESET} │ Market open. "
              f"{len(screened_symbols)} symbols in queue"
              f"{' (screened)' if not args.skip_screening else ''}.\n")

        while clock.current_time_et <= end_time_et:
            tick_count += 1
            t_str = clock.time_str()

            # ── Fill pending orders from previous tick ──
            fills = trading_svc.tick(data_svc)
            for fill in fills:
                print(f"  {t_str} │ {GREEN}FILL{RESET} ", end="")
                print_fill(fill, prefix="")

            # ── Check SL/TP exits ──
            exits = check_position_exits(trading_svc, data_svc, signals_by_symbol)
            for ex in exits:
                reason_color = RED if ex.get("reason") == "STOP_LOSS" else GREEN
                print(
                    f"  {t_str} │ {reason_color}{ex.get('reason', 'EXIT')}{RESET} "
                    f"{ex['symbol']} {ex['qty']}x @ ${ex['price']:.2f}"
                )
                all_exits.append(ex)

                # ── Audit: Log position exit ──
                sig_info = signals_by_symbol.get(ex["symbol"], {})
                entry_price = sig_info.get("entry_price", 0)
                realized_pl = (ex["price"] - entry_price) * ex["qty"] if entry_price else 0
                log_audit(
                    db, session_id, replay_date_str, clock,
                    stage="position_exit",
                    symbol=ex["symbol"],
                    decision={
                        "reason": ex.get("reason", "unknown"),
                        "exit_price": ex["price"],
                        "entry_price": entry_price,
                        "qty": ex["qty"],
                        "realized_pl": round(realized_pl, 2),
                    },
                    passed=realized_pl >= 0,
                    score=round(realized_pl, 2),
                    reasoning=f"{ex.get('reason', 'EXIT')} @ ${ex['price']:.2f}, P/L=${realized_pl:+.2f}",
                )

            # ── Update position marks ──
            trading_svc.update_positions(data_svc)

            # ── Track drawdown ──
            curr_eq = trading_svc.equity
            if curr_eq > peak_equity:
                peak_equity = curr_eq
            dd = peak_equity - curr_eq
            if dd > max_drawdown:
                max_drawdown = dd

            # ── Run signal engine ──
            # Reset last_checked_at so items pass cadence gating
            for item in queue_items:
                item.last_checked_at = None
                item.last_eval_bar_key = None  # Reset same-bar skip
                db.add(item)
            db.flush()

            try:
                new_signals = signal_engine.process_all_queue_items(db)
            except Exception as e:
                if verbose:
                    print(f"  {t_str} │ {RED}Signal engine error: {e}{RESET}")
                new_signals = []

            if new_signals:
                print(f"  {t_str} │ {MAGENTA}── Signal Check ──{RESET}")
                for sig in new_signals:
                    # Tag the signal for cleanup
                    sig.source = "replay"
                    db.add(sig)
                    db.flush()

                    all_signals.append(sig)
                    print_signal(sig, prefix=f"  {t_str} │   ")

                    # ── Audit: Log signal generation ──
                    log_audit(
                        db, session_id, replay_date_str, clock,
                        stage="signal_generation",
                        symbol=sig.symbol,
                        decision={
                            "strategy": sig.strategy,
                            "timeframe": sig.timeframe,
                            "direction": sig.direction,
                            "confidence": sig.confidence_score,
                            "entry_price": sig.entry_price,
                            "stop_loss": sig.stop_loss,
                            "target_1": sig.target_1,
                            "risk_reward": sig.risk_reward_ratio,
                            "quality_gates": getattr(sig, "quality_gates", None),
                        },
                        passed=True,
                        score=sig.confidence_score,
                        reasoning=f"{sig.strategy} {sig.timeframe} conf={sig.confidence_score}",
                    )

                    # Store SL/TP for position monitoring
                    signals_by_symbol[sig.symbol] = {
                        "stop_loss": sig.stop_loss,
                        "target_1": sig.target_1,
                        "entry_price": sig.entry_price,
                        "confidence": sig.confidence_score,
                    }

                    # ── PIPELINE STEP 1: AI Validation ──
                    entry = sig.entry_price or 0
                    if entry <= 0 or sig.direction != "buy":
                        continue

                    validated_confidence = sig.confidence_score or 0
                    ai_action = "auto_execute"  # default if AI bypassed

                    if ai_validator and not args.no_ai:
                        try:
                            ai_result = asyncio.get_event_loop().run_until_complete(
                                ai_validator.validate_signal(sig, db)
                            )
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                ai_result = loop.run_until_complete(
                                    ai_validator.validate_signal(sig, db)
                                )
                            finally:
                                loop.close()

                        validated_confidence = ai_result.get("confidence", validated_confidence)
                        ai_action = ai_result.get("action", "manual_review")
                        ai_reasoning = ai_result.get("reasoning", "")

                        # Audit AI validation
                        log_audit(
                            db, session_id, replay_date_str, clock,
                            stage="ai_validation",
                            symbol=sig.symbol,
                            decision={
                                "original_confidence": sig.confidence_score,
                                "validated_confidence": validated_confidence,
                                "action": ai_action,
                                "reasoning": ai_reasoning[:200],
                                "setup_valid": ai_result.get("setup_still_valid", True),
                            },
                            passed=ai_action != "reject",
                            score=validated_confidence,
                            reasoning=f"AI: {ai_action} (conf {sig.confidence_score}→{validated_confidence})",
                        )

                        if ai_action == "reject":
                            ai_rejected += 1
                            print(
                                f"  {t_str} │   "
                                f"{RED}→ AI REJECT{RESET} {sig.symbol} — "
                                f"conf {sig.confidence_score}→{validated_confidence} "
                                f"({ai_reasoning[:60]})"
                            )
                            continue
                        elif ai_action == "manual_review":
                            print(
                                f"  {t_str} │   "
                                f"{YELLOW}→ AI REVIEW{RESET} {sig.symbol} — "
                                f"conf {sig.confidence_score}→{validated_confidence} "
                                f"(executing in replay)"
                            )
                        else:
                            if verbose:
                                print(
                                    f"  {t_str} │   "
                                    f"{GREEN}→ AI OK{RESET} {sig.symbol} — "
                                    f"conf {sig.confidence_score}→{validated_confidence}"
                                )

                    # ── PIPELINE STEP 2: Risk Gateway ──
                    if not args.no_risk_check:
                        # Build account dict from ReplayTradingService
                        replay_account = trading_svc.get_account()

                        # Update bot state tracking
                        replay_bot_state.open_positions_count = len(trading_svc.positions)

                        risk_result = risk_gw.check_trade(
                            signal=sig,
                            bot_config=replay_bot_config,
                            bot_state=replay_bot_state,
                            account=replay_account,
                            asset_type="stock",
                            skip_bot_status_check=True,
                        )

                        # Audit risk check
                        log_audit(
                            db, session_id, replay_date_str, clock,
                            stage="risk_check",
                            symbol=sig.symbol,
                            decision={
                                "approved": risk_result.approved,
                                "reason": risk_result.reason,
                                "warnings": risk_result.warnings,
                                "account_equity": replay_account.get("equity", 0),
                                "buying_power": replay_account.get("buying_power", 0),
                                "open_positions": replay_bot_state.open_positions_count,
                                "daily_trades": replay_bot_state.daily_trades_count,
                                "circuit_breaker": replay_bot_state.circuit_breaker_level,
                            },
                            passed=risk_result.approved,
                            score=validated_confidence,
                            reasoning=risk_result.reason or "Risk check passed",
                        )

                        if not risk_result.approved:
                            risk_rejected += 1
                            print(
                                f"  {t_str} │   "
                                f"{RED}→ RISK REJECT{RESET} {sig.symbol} — "
                                f"{risk_result.reason}"
                            )
                            continue

                        if risk_result.warnings and verbose:
                            for w in risk_result.warnings:
                                print(
                                    f"  {t_str} │   "
                                    f"{YELLOW}⚠ {w}{RESET}"
                                )

                    # ── PIPELINE STEP 3: Position Sizing ──
                    replay_account = trading_svc.get_account()
                    size_result = pos_sizer.calculate_size(
                        signal=sig,
                        bot_config=replay_bot_config,
                        account=replay_account,
                        current_price=entry,
                        asset_type="stock",
                    )

                    if size_result.rejected:
                        print(
                            f"  {t_str} │   "
                            f"{YELLOW}→ SIZE REJECT{RESET} {sig.symbol} — "
                            f"{size_result.reject_reason}"
                        )
                        continue

                    qty = int(size_result.quantity)
                    if qty <= 0:
                        continue

                    # ── PIPELINE STEP 4: Execute ──
                    if trading_svc.cash >= qty * entry:
                        order = trading_svc.place_market_order(
                            sig.symbol, qty, "buy"
                        )
                        if order:
                            # Update bot state
                            replay_bot_state.daily_trades_count += 1

                            capped = f" ({size_result.capped_reason})" if size_result.capped_reason else ""
                            print(
                                f"  {t_str} │   "
                                f"{GREEN}→ ORDER{RESET} BUY {qty}x {sig.symbol} "
                                f"@ ~${entry:.2f} (${qty * entry:.2f})"
                                f"{capped}"
                            )
                            # ── Audit: Log trade execution ──
                            log_audit(
                                db, session_id, replay_date_str, clock,
                                stage="trade_execution",
                                symbol=sig.symbol,
                                decision={
                                    "side": "buy",
                                    "qty": qty,
                                    "target_price": entry,
                                    "notional": round(qty * entry, 2),
                                    "confidence": validated_confidence,
                                    "sizing_mode": replay_bot_config.sizing_mode,
                                    "ai_action": ai_action,
                                    "risk_passed": not args.no_risk_check,
                                },
                                passed=True,
                                score=validated_confidence,
                                reasoning=f"BUY {qty}x @ ~${entry:.2f} (conf={validated_confidence})",
                            )
                    else:
                        print(
                            f"  {t_str} │   "
                            f"{YELLOW}→ SKIP{RESET} {sig.symbol} — insufficient cash "
                            f"(need ${qty * entry:.2f}, have ${trading_svc.cash:.2f})"
                        )

            # ── Position summary (periodic, every 6 ticks = ~30min) ──
            if tick_count % 6 == 0 and trading_svc.positions:
                print(f"  {t_str} │ {DIM}── Positions ──{RESET}")
                print_positions(trading_svc, prefix=f"  {t_str} │   ")

            # ── Advance clock ──
            clock.advance(interval)

        # ── 4. EOD Close ────────────────────────────────────────────────────

        section("EOD Close")
        if trading_svc.positions:
            eod_closes = trading_svc.close_all_positions(data_svc)
            for close in eod_closes:
                print(f"  EOD │ ", end="")
                print_fill(close, prefix="")
                # Audit EOD exits
                sig_info = signals_by_symbol.get(close["symbol"], {})
                entry_p = sig_info.get("entry_price", 0)
                eod_pl = (close["price"] - entry_p) * close["qty"] if entry_p else 0
                log_audit(
                    db, session_id, replay_date_str, clock,
                    stage="position_exit",
                    symbol=close["symbol"],
                    decision={
                        "reason": "EOD_CLOSE",
                        "exit_price": close["price"],
                        "entry_price": entry_p,
                        "qty": close["qty"],
                        "realized_pl": round(eod_pl, 2),
                    },
                    passed=eod_pl >= 0,
                    score=round(eod_pl, 2),
                    reasoning=f"EOD close @ ${close['price']:.2f}, P/L=${eod_pl:+.2f}",
                )
            all_exits.extend(eod_closes)
        else:
            print(f"  {DIM}No open positions remaining.{RESET}")

        # ── 5. Summary ──────────────────────────────────────────────────────

        print_day_summary(
            trading_svc, all_signals, all_exits, replay_date, equity,
            ai_rejected=ai_rejected, risk_rejected=risk_rejected,
        )

        # Extra stats
        print(f"  {DIM}Ticks: {tick_count}  |  Max drawdown: ${max_drawdown:.2f}  |  "
              f"Peak equity: ${peak_equity:,.2f}{RESET}")

        # ── Audit: Log day summary ──
        buys = [f for f in trading_svc.fills if f["side"] == "buy"]
        sells = [f for f in trading_svc.fills if f["side"] == "sell"]
        realized_pl = 0
        wins = 0
        losses = 0
        for sell in sells:
            buy_price = None
            for buy in buys:
                if buy["symbol"] == sell["symbol"]:
                    buy_price = buy["price"]
                    break
            if buy_price:
                trade_pl = (sell["price"] - buy_price) * sell["qty"]
                realized_pl += trade_pl
                if trade_pl >= 0:
                    wins += 1
                else:
                    losses += 1

        log_audit(
            db, session_id, replay_date_str, clock,
            stage="summary",
            decision={
                "total_signals": len(all_signals),
                "total_buys": len(buys),
                "total_sells": len(sells),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / len(buys) * 100, 1) if buys else 0,
                "gross_pl": round(realized_pl, 2),
                "final_equity": round(trading_svc.equity, 2),
                "starting_equity": equity,
                "max_drawdown": round(max_drawdown, 2),
                "peak_equity": round(peak_equity, 2),
                "ticks": tick_count,
                "preset_condition": condition,
                "preset_presets": presets,
                "preset_composite_score": composite,
                "screening_skipped": args.skip_screening,
                "ai_validation_skipped": args.no_ai,
                "risk_check_skipped": args.no_risk_check,
                "ai_rejected": ai_rejected,
                "risk_rejected": risk_rejected,
                "symbols_input": len(symbols),
                "symbols_screened": len(screened_symbols),
            },
            passed=realized_pl >= 0,
            score=round(realized_pl, 2),
            reasoning=(
                f"{condition} → {len(all_signals)} signals, "
                f"{len(buys)} trades, {wins}W/{losses}L, "
                f"P/L=${realized_pl:+.2f}"
            ),
        )
        db.commit()

        print(f"\n  {GREEN}✅ Audit log: {session_id[:8]}... "
              f"(query: SELECT * FROM replay_audit_logs WHERE "
              f"replay_session_id = '{session_id}'){RESET}")

    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}Replay interrupted by user.{RESET}")
    except Exception as e:
        print(f"\n  {RED}Replay error: {e}{RESET}")
        import traceback
        traceback.print_exc()
    finally:
        # ── 6. Cleanup ──────────────────────────────────────────────────────

        section("Cleanup")

        # Restore patches
        data_svc.uninstall_patches()
        trading_svc.uninstall_patches()
        try:
            intel_svc.uninstall_patches()
        except NameError:
            pass  # intel_svc wasn't created yet
        uninstall_datetime_patches()
        print(f"  {GREEN}✅ Patches restored{RESET}")

        # Clean DB (audit logs are ALWAYS preserved — they're the whole point)
        if not args.no_cleanup:
            q_count, sig_count = cleanup_replay_records(db)
            print(f"  {GREEN}✅ Cleaned {q_count} queue items + {sig_count} signals{RESET}")
            print(f"  {CYAN}ℹ️  Audit logs preserved in replay_audit_logs table{RESET}")
        else:
            print(f"  {YELLOW}⏭️  --no-cleanup: replay records left in DB{RESET}")

        db.close()
        print(f"  {GREEN}✅ Done{RESET}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = parse_args()
    run_replay(args)
