#!/usr/bin/env python3
"""
Pipeline Diagnostic Script — tests each layer of the signal-to-trade pipeline
with REAL data and prints color-coded results.

Usage:
  cd backend
  source venv/bin/activate
  python3 scripts/diagnose_pipeline.py              # Test all layers with AAPL
  python3 scripts/diagnose_pipeline.py NVDA          # Test with a specific symbol
  python3 scripts/diagnose_pipeline.py --layer 1     # Test only Layer 1 (Screening)
  python3 scripts/diagnose_pipeline.py --execute      # Include Layer 6 (paper trade)
  python3 scripts/diagnose_pipeline.py --api-guide    # Print curl commands only
"""
import sys
import os
import argparse
import time
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI Colors
# ═══════════════════════════════════════════════════════════════════════════════
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PASS = f"{GREEN}✅ PASS{RESET}"
FAIL = f"{RED}❌ FAIL{RESET}"
WARN = f"{YELLOW}⚠️  WARN{RESET}"
SKIP = f"{DIM}⏭️  SKIP{RESET}"
INFO = f"{CYAN}ℹ️  INFO{RESET}"


def header(title: str):
    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}\n")


def section(title: str):
    print(f"\n{CYAN}── {title} {'─' * max(1, 60 - len(title))}{RESET}\n")


def result_line(label: str, status: str, detail: str = ""):
    pad = 30 - len(label)
    det = f"  {DIM}({detail}){RESET}" if detail else ""
    print(f"  {label}{'.' * max(1, pad)} {status}{det}")


def timed(fn, *args, **kwargs):
    """Run fn and return (result, elapsed_ms)."""
    t0 = time.time()
    res = fn(*args, **kwargs)
    elapsed = (time.time() - t0) * 1000
    return res, elapsed


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 0: Pre-flight Checks
# ═══════════════════════════════════════════════════════════════════════════════
def layer_0_preflight():
    """Check all dependencies are up."""
    header("Layer 0: Pre-flight Checks")
    results = {}

    # ── Database ──
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        result_line("PostgreSQL", PASS)
        results["db"] = True
        db.close()
    except Exception as e:
        result_line("PostgreSQL", FAIL, str(e)[:80])
        results["db"] = False

    # ── Redis ──
    try:
        from app.services.cache import cache_service
        cache_service.redis_client.ping()
        result_line("Redis", PASS)
        results["redis"] = True
    except Exception as e:
        result_line("Redis", FAIL, str(e)[:80])
        results["redis"] = False

    # ── Alpaca Data Service ──
    try:
        from app.services.data_fetcher.alpaca_service import alpaca_service
        if alpaca_service.is_available:
            result_line("Alpaca Data", PASS)
            results["alpaca_data"] = True
        else:
            result_line("Alpaca Data", FAIL, "not configured or keys missing")
            results["alpaca_data"] = False
    except Exception as e:
        result_line("Alpaca Data", FAIL, str(e)[:80])
        results["alpaca_data"] = False

    # ── Alpaca Trading ──
    try:
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        acct, ms = timed(alpaca_trading_service.get_account)
        if acct:
            equity = acct.get("equity", 0)
            bp = acct.get("buying_power", 0)
            paper = acct.get("paper_mode", "?")
            result_line("Alpaca Trading", PASS,
                        f"equity=${equity:,.2f}  bp=${bp:,.2f}  paper={paper}  {ms:.0f}ms")
            results["alpaca_trading"] = True
            results["account"] = acct
        else:
            result_line("Alpaca Trading", FAIL, "get_account() returned None")
            results["alpaca_trading"] = False
    except Exception as e:
        result_line("Alpaca Trading", FAIL, str(e)[:80])
        results["alpaca_trading"] = False

    # ── Market Status ──
    try:
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        clock = alpaca_trading_service.get_clock()
        if clock:
            is_open = clock.get("is_open", False)
            next_event = clock.get("next_close" if is_open else "next_open", "?")
            status = f"{GREEN}OPEN{RESET}" if is_open else f"{YELLOW}CLOSED{RESET}"
            result_line("Market", status,
                        f"{'closes' if is_open else 'opens'}: {next_event}")
            results["market_open"] = is_open
        else:
            result_line("Market", WARN, "clock unavailable")
            results["market_open"] = None
    except Exception as e:
        result_line("Market", WARN, str(e)[:80])
        results["market_open"] = None

    # ── Bot Status ──
    try:
        from app.database import SessionLocal
        from app.models.bot_state import BotState
        from app.models.bot_config import BotConfiguration
        db = SessionLocal()
        state = db.query(BotState).first()
        config = db.query(BotConfiguration).first()
        if state:
            bot_status = state.status or "unknown"
            if bot_status == "running":
                result_line("Bot Status", f"{GREEN}{bot_status.upper()}{RESET}")
            elif bot_status == "stopped":
                result_line("Bot Status", f"{RED}{bot_status.upper()}{RESET}",
                            "start bot to enable auto-trading")
            else:
                result_line("Bot Status", f"{YELLOW}{bot_status.upper()}{RESET}")
            results["bot_status"] = bot_status
        else:
            result_line("Bot Status", WARN, "no BotState record")
            results["bot_status"] = "no_record"

        if config:
            mode = config.execution_mode or "unknown"
            result_line("Execution Mode", INFO, mode)
            result_line("Paper Mode", INFO, str(config.paper_mode))
            results["execution_mode"] = mode
            results["paper_mode"] = config.paper_mode
        else:
            result_line("Bot Config", WARN, "no BotConfiguration record")
            results["execution_mode"] = "unknown"
        db.close()
    except Exception as e:
        result_line("Bot Status", FAIL, str(e)[:80])
        results["bot_status"] = "error"

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1: Screening
# ═══════════════════════════════════════════════════════════════════════════════
def layer_1_screening(symbol: str):
    """Screen a single stock through the 4-stage pipeline."""
    header(f"Layer 1: Screening — {symbol}")

    try:
        from app.services.screening.engine import ScreeningEngine
        engine = ScreeningEngine()
        result, ms = timed(engine.screen_single_stock, symbol)

        if not result:
            result_line("Screening", FAIL, "returned None")
            return None

        # Stock info
        name = result.get("name", "?")
        score = result.get("score", 0)
        failed_at = result.get("failed_at")
        passed_stages = result.get("passed_stages", [])

        print(f"  Stock: {BOLD}{symbol}{RESET} — {name}")
        print(f"  Composite Score: {BOLD}{score:.1f}{RESET} (min: 30)")
        print(f"  Time: {ms:.0f}ms\n")

        # Gate results
        criteria = result.get("criteria", {})
        coverage = result.get("coverage", {})

        for stage in ["fundamental", "technical", "options", "momentum"]:
            stage_crit = criteria.get(stage, {})
            stage_cov = coverage.get(stage, {})

            if stage in passed_stages:
                status = PASS
            elif failed_at == stage:
                status = FAIL
            else:
                status = f"{DIM}not reached{RESET}"

            known = stage_cov.get("known_count", "?")
            total = stage_cov.get("total_count", "?")
            pass_count = stage_cov.get("pass_count", "?")
            pct = stage_cov.get("score_pct")
            pct_str = f"  score={pct:.1f}%" if pct is not None else ""

            print(f"  {BOLD}{stage.title():12s}{RESET} {status}  "
                  f"pass={pass_count}/{total} known={known}/{total}{pct_str}")

            # Show individual criteria
            if isinstance(stage_crit, dict):
                for k, v in stage_crit.items():
                    icon = "✅" if v == "PASS" else "❌" if v == "FAIL" else "❓"
                    print(f"    {icon} {k}: {v}")

        # Verdict
        print()
        if score >= 30 and not failed_at:
            result_line("Layer 1 Verdict", PASS, f"score={score:.1f} ≥ 30")
        elif failed_at:
            result_line("Layer 1 Verdict", FAIL, f"failed at {failed_at}")
        else:
            result_line("Layer 1 Verdict", FAIL, f"score={score:.1f} < 30")

        return result

    except Exception as e:
        result_line("Screening", FAIL, str(e)[:120])
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2: Strategy Selection
# ═══════════════════════════════════════════════════════════════════════════════
def layer_2_strategy(symbol: str, screening_result: dict):
    """Run StrategySelector on screening result."""
    header(f"Layer 2: Strategy Selection — {symbol}")

    try:
        from app.services.signals.strategy_selector import StrategySelector
        from app.services.data_fetcher.alpaca_service import alpaca_service

        selector = StrategySelector()

        # Build stock_data from screening result (mimics SavedScanResult format)
        stock_data = {
            "symbol": symbol,
            "score": screening_result.get("score", 0),
            "name": screening_result.get("name", ""),
            **screening_result,
        }

        # Get fresh snapshot for real-time data
        snapshot = None
        try:
            snapshot, snap_ms = timed(alpaca_service.get_snapshot, symbol)
            if snapshot:
                print(f"  Alpaca snapshot: {GREEN}OK{RESET} ({snap_ms:.0f}ms)")
            else:
                print(f"  Alpaca snapshot: {YELLOW}None{RESET} (market may be closed)")
        except Exception as e:
            print(f"  Alpaca snapshot: {YELLOW}error{RESET} — {e}")

        result, ms = timed(selector.select_strategies, stock_data, None, snapshot)

        confidence = result.get("confidence", "?")
        timeframes = result.get("timeframes", [])
        reasoning = result.get("reasoning", "")
        auto_queue = result.get("auto_queue", False)
        edge_cases = result.get("edge_cases", [])

        conf_color = GREEN if confidence == "HIGH" else YELLOW if confidence == "MEDIUM" else RED
        print(f"\n  Confidence: {conf_color}{BOLD}{confidence}{RESET}")
        print(f"  Auto-queue: {'Yes' if auto_queue else 'No'}")
        print(f"  Time: {ms:.0f}ms\n")

        if timeframes:
            print(f"  Qualifying Timeframes:")
            for tf_info in timeframes:
                tf = tf_info.get("tf", "?")
                reasons = tf_info.get("reasons", [])
                print(f"    ✅ {tf}: {'; '.join(reasons[:3])}")
        else:
            print(f"  {RED}No timeframes qualified{RESET}")

        if edge_cases:
            print(f"\n  Edge Cases:")
            for ec in edge_cases[:5]:
                print(f"    ⚠️  {ec}")

        print(f"\n  Reasoning: {DIM}{reasoning[:200]}{RESET}")

        # Verdict
        print()
        if timeframes:
            result_line("Layer 2 Verdict", PASS,
                        f"{len(timeframes)} timeframe(s), confidence={confidence}")
        else:
            result_line("Layer 2 Verdict", FAIL, "no timeframes qualified")

        return result

    except Exception as e:
        result_line("Strategy Selection", FAIL, str(e)[:120])
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 3: Signal Engine (Quality Gates + Confidence)
# ═══════════════════════════════════════════════════════════════════════════════
def layer_3_signal_engine(symbol: str, strategy_result: dict):
    """Test signal engine quality gates and confidence calculation."""
    header(f"Layer 3: Signal Engine — {symbol}")

    try:
        from app.services.signals.signal_engine import SignalEngine
        from app.services.data_fetcher.alpaca_service import alpaca_service
        from app.database import SessionLocal
        from app.models.signal_queue import SignalQueue

        engine = SignalEngine()
        db = SessionLocal()

        # Check existing queue items
        section("Signal Queue Status")
        queue_items = db.query(SignalQueue).filter(
            SignalQueue.symbol == symbol,
            SignalQueue.status == "active",
        ).all()
        if queue_items:
            print(f"  Found {len(queue_items)} active queue item(s) for {symbol}:")
            for qi in queue_items:
                checked = qi.last_checked_at.strftime("%H:%M:%S") if qi.last_checked_at else "never"
                print(f"    • tf={qi.timeframe} strategy={qi.strategy} "
                      f"checked={checked} signals={qi.signals_generated}")
        else:
            print(f"  {YELLOW}No active queue items for {symbol}{RESET}")
            print(f"  (Add via: POST /api/v1/signals/queue/add-single)")

        # Pick a timeframe to test
        timeframes = strategy_result.get("timeframes", []) if strategy_result else []
        test_tf = timeframes[0]["tf"] if timeframes else "1h"
        print(f"\n  Testing with timeframe: {BOLD}{test_tf}{RESET}")

        # Fetch bars
        section(f"Alpaca Bars ({test_tf})")
        try:
            bars_result, bars_ms = timed(
                alpaca_service.get_bars_with_enhanced_indicators, symbol, test_tf
            )
            if bars_result is None or (isinstance(bars_result, tuple) and bars_result[0] is None):
                result_line("Bars Fetch", FAIL, "returned None")
                db.close()
                return None

            if isinstance(bars_result, tuple):
                df, eval_idx = bars_result
            else:
                df = bars_result
                eval_idx = -2

            bar_count = len(df) if df is not None else 0
            print(f"  Bars received: {bar_count} ({bars_ms:.0f}ms)")
            print(f"  Eval index: {eval_idx}")

            if bar_count > 0:
                last_bar = df.iloc[eval_idx] if eval_idx < len(df) else df.iloc[-1]
                bar_time = last_bar.get("datetime", last_bar.name) if hasattr(last_bar, "get") else last_bar.name
                print(f"  Last eval bar: {bar_time}")
                print(f"  Close: ${last_bar.get('close', last_bar.get('Close', '?'))}")
                vol = last_bar.get("volume", last_bar.get("Volume", 0))
                print(f"  Volume: {vol:,.0f}" if isinstance(vol, (int, float)) else f"  Volume: {vol}")

                # Show key indicators if available
                for ind in ["rsi", "atr_percent", "rvol", "ema8", "ema21"]:
                    val = last_bar.get(ind)
                    if val is not None:
                        print(f"  {ind}: {val:.2f}" if isinstance(val, float) else f"  {ind}: {val}")
        except Exception as e:
            result_line("Bars Fetch", FAIL, str(e)[:120])
            import traceback
            traceback.print_exc()
            db.close()
            return None

        # Quality gates
        section("Quality Gates")
        try:
            # Determine cap size
            cap_size = "large_cap"  # default
            if strategy_result:
                score = strategy_result.get("score", 50)
                # Simple heuristic — real pipeline uses FMP market cap
                cap_size = "large_cap"

            # Build params dict matching what signal engine expects
            params = {
                "cap_size": cap_size,
                "timeframe": test_tf,
            }

            gate_pass, gate_scores = engine._score_quality_gates(
                df, params, symbol, cap_size, test_tf, eval_idx
            )

            if gate_pass:
                result_line("Quality Gates", PASS)
            else:
                result_line("Quality Gates", FAIL, "hard-fail on structural check")

            print(f"\n  Gate Scores:")
            for k, v in gate_scores.items():
                print(f"    {k}: {v:.2f}" if isinstance(v, float) else f"    {k}: {v}")

        except Exception as e:
            result_line("Quality Gates", FAIL, str(e)[:120])
            gate_pass = False
            gate_scores = {}
            import traceback
            traceback.print_exc()

        # Confidence calculation
        section("Confidence Calculation")
        try:
            confidence = engine._calculate_confidence(
                df,
                direction="long",
                params={"cap_size": cap_size, "timeframe": test_tf},
                eval_idx=eval_idx,
                gate_scores=gate_scores if gate_scores else None,
            )

            min_conf = 62  # MIN_CONFIDENCE
            if confidence >= min_conf:
                result_line("Confidence", PASS, f"{confidence:.1f} ≥ {min_conf}")
            else:
                result_line("Confidence", FAIL, f"{confidence:.1f} < {min_conf}")

            print(f"\n  Confidence Score: {BOLD}{confidence:.1f}{RESET}")
            print(f"  MIN_CONFIDENCE: {min_conf}")
            print(f"  Gap: {confidence - min_conf:+.1f} points")

        except Exception as e:
            result_line("Confidence", FAIL, str(e)[:120])
            confidence = 0
            import traceback
            traceback.print_exc()

        # Check existing signals
        section("Existing Signals")
        from app.models.trading_signal import TradingSignal
        signals = db.query(TradingSignal).filter(
            TradingSignal.symbol == symbol,
            TradingSignal.status == "active",
        ).order_by(TradingSignal.generated_at.desc()).limit(5).all()

        if signals:
            print(f"  Found {len(signals)} active signal(s):")
            for sig in signals:
                gen_at = sig.generated_at.strftime("%m/%d %H:%M") if sig.generated_at else "?"
                print(f"    #{sig.id}: {sig.direction} {sig.strategy} "
                      f"conf={sig.confidence_score:.0f} tf={sig.timeframe} "
                      f"at={gen_at} val={sig.validation_status or 'none'}")
        else:
            print(f"  {YELLOW}No active signals for {symbol}{RESET}")

        # Verdict
        print()
        if gate_pass and confidence >= 62:
            result_line("Layer 3 Verdict", PASS,
                        f"gates=OK, confidence={confidence:.1f}")
        elif not gate_pass:
            result_line("Layer 3 Verdict", FAIL, "quality gates hard-fail")
        else:
            result_line("Layer 3 Verdict", FAIL,
                        f"confidence {confidence:.1f} < 62")

        layer_result = {
            "gate_pass": gate_pass,
            "gate_scores": gate_scores,
            "confidence": confidence,
            "signals": [s.id for s in signals],
            "bar_count": bar_count,
        }
        db.close()
        return layer_result

    except Exception as e:
        result_line("Signal Engine", FAIL, str(e)[:120])
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 4: Signal Validation
# ═══════════════════════════════════════════════════════════════════════════════
def layer_4_validation(symbol: str, layer3_result: dict):
    """Check validation status of existing signals."""
    header(f"Layer 4: Signal Validation — {symbol}")

    signal_ids = layer3_result.get("signals", []) if layer3_result else []
    if not signal_ids:
        print(f"  {DIM}No signals to validate — Layer 3 produced no signals{RESET}")
        result_line("Layer 4 Verdict", SKIP, "no signals available")
        return None

    try:
        from app.database import SessionLocal
        from app.models.trading_signal import TradingSignal
        db = SessionLocal()

        for sid in signal_ids[:3]:
            sig = db.query(TradingSignal).get(sid)
            if not sig:
                continue

            val_status = sig.validation_status or "not_validated"
            val_reasoning = sig.validation_reasoning or "—"

            if val_status == "validated":
                status_str = f"{GREEN}APPROVED{RESET}"
            elif val_status == "rejected":
                status_str = f"{RED}REJECTED{RESET}"
            else:
                status_str = f"{YELLOW}{val_status}{RESET}"

            print(f"  Signal #{sid}: {status_str}")
            print(f"    Confidence: {sig.confidence_score:.0f}")
            print(f"    Direction: {sig.direction}")
            print(f"    Strategy: {sig.strategy}")
            if val_reasoning != "—":
                print(f"    Reasoning: {DIM}{val_reasoning[:200]}{RESET}")
            print()

        result_line("Layer 4 Verdict", INFO, f"{len(signal_ids)} signal(s) checked")
        db.close()
        return {"signal_ids": signal_ids}

    except Exception as e:
        result_line("Validation", FAIL, str(e)[:120])
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 5: Trade Execution Preview
# ═══════════════════════════════════════════════════════════════════════════════
def layer_5_preview(symbol: str, layer3_result: dict):
    """Preview trade execution (risk check + sizing) without placing order."""
    header(f"Layer 5: Execution Preview — {symbol}")

    signal_ids = layer3_result.get("signals", []) if layer3_result else []
    if not signal_ids:
        print(f"  {DIM}No signals available for preview{RESET}")
        print(f"  To test: add {symbol} to queue, wait for signal, then re-run")
        result_line("Layer 5 Verdict", SKIP, "no signals")
        return None

    try:
        from app.database import SessionLocal
        from app.services.trading.auto_trader import auto_trader
        db = SessionLocal()

        signal_id = signal_ids[0]
        print(f"  Previewing signal #{signal_id}...\n")

        preview, ms = timed(auto_trader.preview_signal, signal_id, db)

        if "error" in preview:
            result_line("Preview", FAIL, preview["error"])
            db.close()
            return None

        # Risk check
        risk = preview.get("risk_check", {})
        approved = risk.get("approved", False)
        reason = risk.get("reason", "")
        warnings = risk.get("warnings", [])

        section("Risk Check (16 gates)")
        if approved:
            result_line("Risk Check", PASS)
        else:
            result_line("Risk Check", FAIL, reason)

        if warnings:
            for w in warnings:
                print(f"    ⚠️  {w}")

        # Sizing
        sizing = preview.get("sizing", {})
        section("Position Sizing")
        quantity = sizing.get("quantity", 0)
        notional = sizing.get("notional", 0)
        rejected = sizing.get("rejected", False)
        reject_reason = sizing.get("reject_reason", "")
        capped = sizing.get("capped_reason", "")

        if rejected:
            result_line("Sizing", FAIL, reject_reason)
        else:
            result_line("Sizing", PASS,
                        f"qty={quantity}, notional=${notional:,.2f}")

        if capped:
            print(f"    Capped: {capped}")

        print(f"\n  Asset Type: {sizing.get('asset_type', '?')}")
        print(f"  Fractional: {sizing.get('is_fractional', '?')}")

        # Account
        acct = preview.get("account", {})
        section("Account")
        print(f"  Equity: ${acct.get('equity', 0):,.2f}")
        print(f"  Buying Power: ${acct.get('buying_power', 0):,.2f}")
        print(f"  Current Price: ${preview.get('current_price', 0):,.2f}")

        # Config
        cfg = preview.get("config", {})
        section("Config Snapshot")
        print(f"  Paper Mode: {cfg.get('paper_mode', '?')}")
        print(f"  Sizing Mode: {cfg.get('sizing_mode', '?')}")
        print(f"  Max Stock Trade: ${cfg.get('max_per_stock_trade', 0):,.2f}")

        # Verdict
        print()
        if approved and not rejected:
            result_line("Layer 5 Verdict", PASS,
                        f"risk=OK, size={quantity} @ ${notional:,.2f}")
        elif not approved:
            result_line("Layer 5 Verdict", FAIL, f"risk rejected: {reason}")
        else:
            result_line("Layer 5 Verdict", FAIL, f"sizing rejected: {reject_reason}")

        db.close()
        return {"approved": approved, "sizing": sizing, "signal_id": signal_id}

    except Exception as e:
        result_line("Preview", FAIL, str(e)[:120])
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 6: Order Placement (optional)
# ═══════════════════════════════════════════════════════════════════════════════
def layer_6_execute(symbol: str, layer5_result: dict):
    """Actually place a paper trade. Requires --execute flag + confirmation."""
    header(f"Layer 6: Order Execution — {symbol}")

    if not layer5_result or not layer5_result.get("approved"):
        print(f"  {DIM}Cannot execute — preview was not approved{RESET}")
        result_line("Layer 6 Verdict", SKIP, "preview not approved")
        return None

    signal_id = layer5_result.get("signal_id")
    sizing = layer5_result.get("sizing", {})

    print(f"  Signal: #{signal_id}")
    print(f"  Quantity: {sizing.get('quantity', 0)}")
    print(f"  Notional: ${sizing.get('notional', 0):,.2f}")
    print(f"  Asset Type: {sizing.get('asset_type', 'stock')}")
    print()

    confirm = input(f"  {YELLOW}Place this paper trade? (yes/no): {RESET}").strip().lower()
    if confirm != "yes":
        print(f"\n  {DIM}Execution cancelled by user{RESET}")
        result_line("Layer 6 Verdict", SKIP, "cancelled by user")
        return None

    try:
        from app.database import SessionLocal
        from app.services.trading.auto_trader import auto_trader
        db = SessionLocal()

        result, ms = timed(auto_trader.execute_manual_signal, signal_id, db)

        if "error" in result:
            result_line("Execution", FAIL, result["error"])
        elif "trade" in result:
            trade = result["trade"]
            print(f"\n  {GREEN}Trade placed successfully!{RESET}")
            print(f"  Trade ID: {trade.get('id', '?')}")
            print(f"  Order ID: {trade.get('entry_order_id', '?')}")
            print(f"  Time: {ms:.0f}ms")
            result_line("Layer 6 Verdict", PASS, "order placed")
        else:
            result_line("Execution", WARN, f"unexpected response: {json.dumps(result)[:100]}")

        db.close()
        return result

    except Exception as e:
        result_line("Execution", FAIL, str(e)[:120])
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 7: Position Monitor + Trade Journal
# ═══════════════════════════════════════════════════════════════════════════════
def layer_7_monitor():
    """Check current positions and trade journal."""
    header("Layer 7: Position Monitor + Trade Journal")

    try:
        from app.services.trading.alpaca_trading_service import alpaca_trading_service

        # Positions
        section("Open Positions")
        try:
            positions = alpaca_trading_service.get_all_positions()
            if positions:
                print(f"  {len(positions)} open position(s):")
                for p in positions[:10]:
                    sym = p.get("symbol", "?")
                    qty = p.get("qty", 0)
                    mkt_val = p.get("market_value", 0)
                    pnl = p.get("unrealized_pl", 0)
                    pnl_pct = p.get("unrealized_plpc", 0)
                    pnl_color = GREEN if float(pnl) >= 0 else RED
                    print(f"    {sym}: {qty} shares, ${float(mkt_val):,.2f} "
                          f"P/L: {pnl_color}${float(pnl):,.2f} ({float(pnl_pct)*100:.1f}%){RESET}")
            else:
                print(f"  {DIM}No open positions{RESET}")
        except Exception as e:
            print(f"  {RED}Error fetching positions: {e}{RESET}")

        # Recent orders
        section("Recent Orders (today)")
        try:
            orders = alpaca_trading_service.get_orders(status="all", limit=10)
            if orders:
                print(f"  {len(orders)} recent order(s):")
                for o in orders[:5]:
                    sym = o.get("symbol", "?")
                    side = o.get("side", "?")
                    qty = o.get("qty", 0)
                    status = o.get("status", "?")
                    otype = o.get("type", "?")
                    created = o.get("created_at") or o.get("submitted_at") or "?"
                    if hasattr(created, "strftime"):
                        created = created.strftime("%m/%d %H:%M")
                    elif isinstance(created, str) and len(created) > 16:
                        created = created[:16]
                    status_color = GREEN if status in ("filled", "new") else YELLOW
                    print(f"    {sym}: {side} {qty} ({otype}) — "
                          f"{status_color}{status}{RESET}  {created}")
            else:
                print(f"  {DIM}No recent orders{RESET}")
        except Exception as e:
            print(f"  {RED}Error fetching orders: {e}{RESET}")

        # Trade journal from DB
        section("Trade Journal (recent)")
        try:
            from app.database import SessionLocal
            from app.models.executed_trade import ExecutedTrade
            db = SessionLocal()
            trades = db.query(ExecutedTrade).order_by(
                ExecutedTrade.created_at.desc()
            ).limit(5).all()
            if trades:
                print(f"  {len(trades)} recent trade(s) in journal:")
                for t in trades:
                    created = t.created_at.strftime("%m/%d %H:%M") if t.created_at else "?"
                    print(f"    {t.symbol}: {t.side} {t.quantity} — "
                          f"status={t.status} at={created}")
            else:
                print(f"  {DIM}No trades in journal{RESET}")
            db.close()
        except Exception as e:
            print(f"  {YELLOW}Trade journal: {e}{RESET}")

        result_line("Layer 7 Verdict", PASS, "monitor check complete")
        return True

    except Exception as e:
        result_line("Monitor", FAIL, str(e)[:120])
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Summary Report
# ═══════════════════════════════════════════════════════════════════════════════
def print_summary(results: dict):
    """Print final pipeline health report."""
    header("Pipeline Health Report")

    preflight = results.get("preflight", {})
    issues = []

    # Pre-flight
    pf_items = []
    for key, label in [("db", "DB"), ("redis", "Redis"),
                       ("alpaca_data", "Alpaca"), ("alpaca_trading", "Trading")]:
        if preflight.get(key):
            pf_items.append(f"{GREEN}✅{label}{RESET}")
        else:
            pf_items.append(f"{RED}❌{label}{RESET}")
            issues.append(f"{label} is not available")

    if preflight.get("market_open") is False:
        pf_items.append(f"{YELLOW}⚠️ Mkt CLOSED{RESET}")
        issues.append("Market is CLOSED — signals only generate during market hours")
    elif preflight.get("market_open"):
        pf_items.append(f"{GREEN}✅Mkt OPEN{RESET}")

    bot = preflight.get("bot_status", "unknown")
    if bot == "running":
        pf_items.append(f"{GREEN}✅Bot{RESET}")
    elif bot == "stopped":
        pf_items.append(f"{RED}❌Bot STOPPED{RESET}")
        issues.append("Bot is STOPPED — start it to enable auto-trading")
    else:
        pf_items.append(f"{YELLOW}⚠️ Bot {bot}{RESET}")
        issues.append(f"Bot is {bot}")

    print(f"  Pre-flight:  {' '.join(pf_items)}")

    # Layers
    layer_map = {
        1: ("Screening", results.get("layer1")),
        2: ("Strategy", results.get("layer2")),
        3: ("Signal Engine", results.get("layer3")),
        4: ("Validation", results.get("layer4")),
        5: ("Execution Preview", results.get("layer5")),
        6: ("Order Placement", results.get("layer6")),
        7: ("Monitor", results.get("layer7")),
    }

    for n, (name, res) in layer_map.items():
        if res is None:
            print(f"  Layer {n}:     {DIM}⏭️  {name} — skipped{RESET}")
        elif res is False:
            print(f"  Layer {n}:     {RED}❌ {name} — FAILED{RESET}")
        elif isinstance(res, dict):
            # Check for known failure indicators
            if res.get("failed_at"):
                detail = res.get("failed_at", "")
                print(f"  Layer {n}:     {RED}❌ {name}{RESET}  {DIM}(failed: {detail}){RESET}")
            elif isinstance(res.get("confidence"), (int, float)) and res["confidence"] < 62:
                conf = res["confidence"]
                print(f"  Layer {n}:     {RED}❌ {name}{RESET}  {DIM}(confidence: {conf:.1f} < 62){RESET}")
                issues.append(f"Signal confidence ({conf:.1f}) below MIN_CONFIDENCE (62)")
            elif isinstance(res.get("confidence"), str) and res["confidence"] in ("LOW",):
                conf = res["confidence"]
                tfs = res.get("timeframes", [])
                if not tfs:
                    print(f"  Layer {n}:     {RED}❌ {name}{RESET}  {DIM}(confidence={conf}, no timeframes){RESET}")
                else:
                    print(f"  Layer {n}:     {YELLOW}⚠️  {name}{RESET}  {DIM}(confidence={conf}){RESET}")
            elif res.get("approved") is False:
                reason = res.get("reason", "risk rejected")
                print(f"  Layer {n}:     {RED}❌ {name}{RESET}  {DIM}({reason}){RESET}")
            elif res.get("gate_pass") is False:
                print(f"  Layer {n}:     {RED}❌ {name}{RESET}  {DIM}(quality gates hard-fail){RESET}")
            else:
                # Assume pass
                detail_parts = []
                if "score" in res and isinstance(res["score"], (int, float)):
                    detail_parts.append(f"score={res['score']:.1f}")
                if "confidence" in res and isinstance(res["confidence"], (int, float)):
                    detail_parts.append(f"conf={res['confidence']:.1f}")
                elif "confidence" in res and isinstance(res["confidence"], str):
                    detail_parts.append(f"conf={res['confidence']}")
                det = ", ".join(detail_parts)
                print(f"  Layer {n}:     {GREEN}✅ {name}{RESET}  {DIM}({det}){RESET}" if det
                      else f"  Layer {n}:     {GREEN}✅ {name}{RESET}")
        else:
            print(f"  Layer {n}:     {GREEN}✅ {name}{RESET}")

    if issues:
        print(f"\n  {YELLOW}{BOLD}⚠️  ISSUES FOUND:{RESET}")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    else:
        print(f"\n  {GREEN}{BOLD}All layers passed!{RESET}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
# API Guide
# ═══════════════════════════════════════════════════════════════════════════════
def print_api_guide():
    """Print copy-paste curl commands for each pipeline stage."""
    header("API Walkthrough Guide — curl commands")

    BASE = "http://localhost:8000"

    commands = [
        ("1. System Health", "GET", f"{BASE}/api/v1/health/dashboard",
         "Check all dependencies, scheduler jobs, bot state"),

        ("2. Scheduler Jobs", "GET", f"{BASE}/api/v1/health/jobs",
         "Check signal_checker, auto_scan, position_monitor job status"),

        ("3. Screen a Stock", "GET", f"{BASE}/api/v1/screener/screen/single/AAPL",
         "Run 4-stage screening pipeline on a single stock"),

        ("4. Add to Signal Queue", "POST", f"{BASE}/api/v1/signals/queue/add-single",
         "Queue a stock for signal processing",
         '\'{"symbol":"AAPL","name":"Apple Inc","timeframe":"1h","strategy":"auto"}\''),

        ("5. View Signal Queue", "GET", f"{BASE}/api/v1/signals/queue",
         "List all queue items with check times and signal counts"),

        ("6. View Signals", "GET", f"{BASE}/api/v1/signals/",
         "List all trading signals with confidence scores"),

        ("7. Signal Stats", "GET", f"{BASE}/api/v1/signals/stats/summary",
         "Queue + signal + execution summary counts"),

        ("8. Bot Status", "GET", f"{BASE}/api/v1/trading/bot/status",
         "Bot running/stopped, equity, positions, circuit breaker"),

        ("9. Bot Config", "GET", f"{BASE}/api/v1/trading/bot/config",
         "Execution mode, sizing, risk params"),

        ("10. Start Bot", "POST", f"{BASE}/api/v1/trading/bot/start",
          "Start the trading bot (required for auto-execution)"),

        ("11. Preview Signal", "GET", f"{BASE}/api/v1/trading/bot/preview-signal/1",
          "Risk check + sizing preview WITHOUT placing order"),

        ("12. Execute Signal", "POST", f"{BASE}/api/v1/trading/bot/execute-signal/1",
          "Manually execute signal through full pipeline"),

        ("13. Pending Approvals", "GET", f"{BASE}/api/v1/trading/bot/pending-approvals",
          "Signals awaiting approval (semi_auto mode)"),

        ("14. Positions", "GET", f"{BASE}/api/v1/trading/positions",
          "All open positions with P/L"),

        ("15. Orders", "GET", f"{BASE}/api/v1/trading/orders?status=all",
          "Recent orders (open, closed, cancelled)"),

        ("16. Trade Journal", "GET", f"{BASE}/api/v1/trading/bot/trades",
          "All executed trades with journal entries"),

        ("17. Performance", "GET", f"{BASE}/api/v1/trading/bot/performance/today",
          "Today's P/L, win rate, trade count"),

        ("18. Test Scan", "POST", f"{BASE}/api/v1/autopilot/test-scan",
          "Trigger smart scan BYPASSING market hours check"),

        ("19. Market State", "GET", f"{BASE}/api/v1/autopilot/market-state",
          "MRI, regime, Fear & Greed, condition classification"),

        ("20. Logs", "GET", f"{BASE}/api/v1/logs/?level=ERROR&limit=50",
          "Recent error logs from Redis"),
    ]

    for entry in commands:
        name, method, url = entry[0], entry[1], entry[2]
        desc = entry[3]
        body = entry[4] if len(entry) > 4 else None

        print(f"  {BOLD}{name}{RESET}")
        print(f"  {DIM}{desc}{RESET}")
        if method == "GET":
            print(f"  {CYAN}curl -s {url} | python3 -m json.tool{RESET}")
        elif body:
            print(f"  {CYAN}curl -s -X POST {url} -H 'Content-Type: application/json' -d {body} | python3 -m json.tool{RESET}")
        else:
            print(f"  {CYAN}curl -s -X POST {url} | python3 -m json.tool{RESET}")
        print()

    # Common debugging scenarios
    section("Common Debug Scenarios")
    print(f"""
  {BOLD}Q: No signals being generated?{RESET}
  1. Check queue: curl -s {BASE}/api/v1/signals/queue | python3 -m json.tool
  2. Check if signal_checker ran: curl -s {BASE}/api/v1/health/jobs | python3 -m json.tool
  3. Check logs for rejections: curl -s '{BASE}/api/v1/logs/?search=confidence&limit=20' | python3 -m json.tool

  {BOLD}Q: Signals exist but no trades?{RESET}
  1. Check bot status: curl -s {BASE}/api/v1/trading/bot/status | python3 -m json.tool
  2. Preview a signal: curl -s {BASE}/api/v1/trading/bot/preview-signal/{{ID}} | python3 -m json.tool
  3. Check execution mode: should be 'full_auto' or 'semi_auto', NOT 'signal_only'

  {BOLD}Q: Bot running but still no trades?{RESET}
  1. Check risk rejections: curl -s '{BASE}/api/v1/logs/?search=risk&limit=20' | python3 -m json.tool
  2. Check circuit breaker: look at 'circuit_breaker_level' in bot status
  3. Check confidence threshold: config.min_confidence_to_execute vs signal scores

  {BOLD}Q: Market is closed, how to test?{RESET}
  1. Trigger scan: curl -s -X POST {BASE}/api/v1/autopilot/test-scan | python3 -m json.tool
  2. Use this diagnostic script (works outside market hours with cached data)
""")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Diagnostic — test each layer with real data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/diagnose_pipeline.py                # Test all layers with AAPL
  python3 scripts/diagnose_pipeline.py NVDA            # Test with NVDA
  python3 scripts/diagnose_pipeline.py --layer 1       # Screening only
  python3 scripts/diagnose_pipeline.py --layer 3       # Signal engine only
  python3 scripts/diagnose_pipeline.py --execute       # Include paper trade
  python3 scripts/diagnose_pipeline.py --api-guide     # Print curl commands
        """,
    )
    parser.add_argument("symbol", nargs="?", default="AAPL",
                        help="Stock symbol to test (default: AAPL)")
    parser.add_argument("--layer", type=int, choices=range(0, 8),
                        help="Run only this layer (0=preflight, 1-7)")
    parser.add_argument("--execute", action="store_true",
                        help="Include Layer 6: place a real paper trade")
    parser.add_argument("--api-guide", action="store_true",
                        help="Print curl commands for manual API testing")

    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.api_guide:
        print_api_guide()
        return

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  LEAPS Trader — Pipeline Diagnostic{RESET}")
    print(f"{BOLD}  Symbol: {symbol}   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'=' * 70}{RESET}")

    results = {}
    run_layer = args.layer  # None = all

    # Layer 0: Pre-flight
    if run_layer is None or run_layer == 0:
        results["preflight"] = layer_0_preflight()

    # Layer 1: Screening
    if run_layer is None or run_layer == 1:
        results["layer1"] = layer_1_screening(symbol)

    # Layer 2: Strategy Selection
    if run_layer is None or run_layer == 2:
        screening = results.get("layer1")
        if screening is None and run_layer == 2:
            # Need screening result — run it
            screening = layer_1_screening(symbol)
        results["layer2"] = layer_2_strategy(symbol, screening)

    # Layer 3: Signal Engine
    if run_layer is None or run_layer == 3:
        strategy = results.get("layer2")
        results["layer3"] = layer_3_signal_engine(symbol, strategy)

    # Layer 4: Validation
    if run_layer is None or run_layer == 4:
        l3 = results.get("layer3")
        results["layer4"] = layer_4_validation(symbol, l3)

    # Layer 5: Execution Preview
    if run_layer is None or run_layer == 5:
        l3 = results.get("layer3")
        results["layer5"] = layer_5_preview(symbol, l3)

    # Layer 6: Order Execution (only with --execute)
    if (run_layer is None or run_layer == 6) and args.execute:
        l5 = results.get("layer5")
        results["layer6"] = layer_6_execute(symbol, l5)
    elif run_layer == 6 and not args.execute:
        print(f"\n  {YELLOW}Layer 6 requires --execute flag{RESET}")

    # Layer 7: Position Monitor
    if run_layer is None or run_layer == 7:
        results["layer7"] = layer_7_monitor()

    # Summary (only when running all layers)
    if run_layer is None:
        print_summary(results)


if __name__ == "__main__":
    main()
