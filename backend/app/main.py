"""
LEAPS Trader - FastAPI Application
"""
import asyncio
import time
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.api.endpoints import screener, stocks, ai_analysis, sentiment, strategy
from app.api.endpoints import settings as settings_endpoints
from app.api.endpoints import command_center
from app.api.endpoints import webhooks
from app.api.endpoints import user_alerts
from app.api.endpoints import signals
from app.api.endpoints import trading
from app.api.endpoints import heatmap
from app.api.endpoints import saved_scans
from app.api.endpoints import portfolio
from app.api.endpoints import macro
from app.api.endpoints import macro_intelligence
from app.api.endpoints import websocket as ws_endpoints
from app.api.endpoints import bot as bot_endpoints
from app.api.endpoints import backtesting as backtesting_endpoints
from app.api.endpoints import scan_processing
from app.api.endpoints import autopilot as autopilot_endpoints
from app.api.endpoints import logs as logs_endpoints
from app.api.endpoints import health as health_endpoints
from app.services.health_monitor import health_monitor
from app.services.data_fetcher.finviz import initialize_finviz_service
from app.services.settings_service import settings_service
from app.services.data_fetcher.tastytrade import initialize_tastytrade_service
from app.services.telegram_bot import initialize_telegram_bot, get_telegram_bot
from app.services.ai.claude_service import initialize_claude_service, get_claude_service
from app.services.alerts.alert_service import alert_service
from app.services.signals.signal_engine import signal_engine
from app.database import SessionLocal
from app.api.auth import require_trading_auth
from app.api.endpoints.app_auth import router as app_auth_router, verify_token, _get_app_password

# Global scheduler instance
scheduler = AsyncIOScheduler()

app_settings = get_settings()

# ── Redis log sink (structured logs → Redis ring buffer) ──────────────────
from app.services.log_sink import redis_log_sink
try:
    logger.add(redis_log_sink, level="INFO", format="{message}")
    logger.info("Redis log sink registered")
except Exception as e:
    logger.warning(f"Failed to register Redis log sink: {e}")

# Create FastAPI app
app = FastAPI(
    title=app_settings.PROJECT_NAME,
    version="1.0.0",
    description="Stock screening tool for identifying 5x LEAPS opportunities"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── App-wide password protection middleware ──────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware

_AUTH_SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/")
_AUTH_SKIP_EXACT = ("/",)


class AppPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        app_pw = _get_app_password()
        if not app_pw:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # Always allow CORS preflight
        if method == "OPTIONS":
            return await call_next(request)

        # Allow public paths (exact match or prefix match)
        if path in _AUTH_SKIP_EXACT or any(path.startswith(p) for p in _AUTH_SKIP_PREFIXES):
            return await call_next(request)

        # Allow WebSocket
        if path.startswith("/ws"):
            return await call_next(request)

        # Check token from header or query param (EventSource/SSE can't set headers)
        token = request.headers.get("X-App-Token", "") or request.query_params.get("token", "")
        if not verify_token(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Please log in."},
            )

        return await call_next(request)


app.add_middleware(AppPasswordMiddleware)


# ── Rate limiting (simple in-memory, per-IP) ────────────────────────────────
import time
from collections import defaultdict

_rate_limit_store: dict = defaultdict(list)  # ip → [timestamps]
RATE_LIMIT_REQUESTS = 120     # max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60  # sliding window


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple in-memory rate limiter (per-IP, sliding window)."""
    path = request.url.path
    # Skip health, static, and WebSocket
    if path in ("/", "/health") or path.startswith("/ws"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    # Prune old entries
    timestamps = _rate_limit_store[client_ip]
    _rate_limit_store[client_ip] = [t for t in timestamps if t > cutoff]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


# ── Request timeout middleware (120s default) ────────────────────────────────
REQUEST_TIMEOUT_SECONDS = 120
_LONG_RUNNING_PATHS = {"/api/v1/backtesting/run", "/api/v1/screener/run", "/api/v1/ai/"}


@app.middleware("http")
async def request_timeout_middleware(request: Request, call_next):
    """Guard against runaway requests with a timeout."""
    path = request.url.path
    # Skip WebSocket upgrades and known long-running endpoints
    if path.startswith("/ws") or any(path.startswith(p) for p in _LONG_RUNNING_PATHS):
        return await call_next(request)
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(f"Request timed out after {REQUEST_TIMEOUT_SECONDS}s: {request.method} {path}")
        return JSONResponse(status_code=504, content={"detail": "Request timed out"})


# ┌─────────────────────────────────────────────────────────────────────┐
# │ DOC UPDATE: Adding/removing a router here? Also update:            │
# │   ARCHITECTURE.md → "Backend API Routers" table + Changelog        │
# │   .claude/CLAUDE.md → "Key Entry Points" if it's a major router    │
# └─────────────────────────────────────────────────────────────────────┘

# App auth (login/check) — must be before protected routes
app.include_router(
    app_auth_router,
    prefix=f"{app_settings.API_V1_PREFIX}/auth",
    tags=["auth"]
)

app.include_router(
    screener.router,
    prefix=f"{app_settings.API_V1_PREFIX}/screener",
    tags=["screener"]
)

app.include_router(
    stocks.router,
    prefix=f"{app_settings.API_V1_PREFIX}/stocks",
    tags=["stocks"]
)

app.include_router(
    ai_analysis.router,
    prefix=f"{app_settings.API_V1_PREFIX}/ai",
    tags=["ai"]
)

app.include_router(
    sentiment.router,
    prefix=f"{app_settings.API_V1_PREFIX}/sentiment",
    tags=["sentiment"]
)

app.include_router(
    strategy.router,
    prefix=f"{app_settings.API_V1_PREFIX}/strategy",
    tags=["strategy"]
)

app.include_router(
    settings_endpoints.router,
    prefix=f"{app_settings.API_V1_PREFIX}/settings",
    tags=["settings"]
)

app.include_router(
    command_center.router,
    prefix=f"{app_settings.API_V1_PREFIX}/command-center",
    tags=["command-center"]
)

app.include_router(
    webhooks.router,
    prefix=f"{app_settings.API_V1_PREFIX}/webhooks",
    tags=["webhooks"]
)

app.include_router(
    user_alerts.router,
    prefix=f"{app_settings.API_V1_PREFIX}/alerts",
    tags=["alerts"]
)

app.include_router(
    signals.router,
    prefix=f"{app_settings.API_V1_PREFIX}/signals",
    tags=["signals"]
)

app.include_router(
    trading.router,
    prefix=f"{app_settings.API_V1_PREFIX}/trading",
    tags=["trading"]
)

app.include_router(
    heatmap.router,
    prefix=f"{app_settings.API_V1_PREFIX}/heatmap",
    tags=["heatmap"]
)

app.include_router(
    saved_scans.router,
    prefix=f"{app_settings.API_V1_PREFIX}/saved-scans",
    tags=["saved-scans"]
)

app.include_router(
    portfolio.router,
    prefix=f"{app_settings.API_V1_PREFIX}/portfolio",
    tags=["portfolio"]
)

app.include_router(
    macro.router,
    prefix=f"{app_settings.API_V1_PREFIX}/command-center/macro",
    tags=["macro"]
)

app.include_router(
    macro_intelligence.router,
    prefix=f"{app_settings.API_V1_PREFIX}/command-center/macro-intelligence",
    tags=["macro-intelligence"]
)

# WebSocket endpoints (no API prefix - direct at /ws)
app.include_router(
    ws_endpoints.router,
    prefix="/ws",
    tags=["websocket"]
)

# Trading Bot endpoints
app.include_router(
    bot_endpoints.router,
    prefix=f"{app_settings.API_V1_PREFIX}/trading/bot",
    tags=["trading-bot"]
)

# Backtesting endpoints
app.include_router(
    backtesting_endpoints.router,
    prefix=f"{app_settings.API_V1_PREFIX}/backtesting",
    tags=["backtesting"]
)

# Scan Processing endpoints (StrategySelector pipeline)
app.include_router(
    scan_processing.router,
    prefix=f"{app_settings.API_V1_PREFIX}/scan-processing",
    tags=["scan-processing"]
)

# Autopilot endpoints (smart scan control + logs)
app.include_router(
    autopilot_endpoints.router,
    prefix="/api/v1/autopilot",
    tags=["autopilot"],
)

# Logs endpoint (Redis log buffer viewer)
app.include_router(
    logs_endpoints.router,
    prefix="/api/v1/logs",
    tags=["logs"],
)

# Health monitoring dashboard
app.include_router(
    health_endpoints.router,
    prefix="/api/v1/health",
    tags=["health"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "LEAPS Trader API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """
    Enhanced health check — pings all critical dependencies.
    Returns 200 for healthy/degraded, 503 only when truly critical (DB/Redis down).
    Cached 60s to keep Railway's 30s probe fast.
    """
    try:
        deps = await health_monitor.check_all_dependencies()
        overall = health_monitor._compute_overall_status(
            deps, health_monitor.get_all_jobs_health(), health_monitor._get_bot_info()
        )
        status_code = 503 if overall == "critical" else 200
        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall,
                "service": "leaps-trader-api",
                "uptime_seconds": round(health_monitor.get_uptime_seconds(), 0),
                "dependencies": deps,
            },
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "healthy", "service": "leaps-trader-api"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


async def check_alerts_job():
    """Background job to check all active alerts"""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        triggered = await asyncio.to_thread(alert_service.check_all_alerts, db)
        if triggered:
            logger.info(f"Alert check complete: {len(triggered)} alerts triggered")
    except Exception as e:
        logger.error(f"Error in alert check job: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("alert_checker", _status, time.monotonic() - _start, _error)


async def check_signals_job():
    """Background job to process signal queue and generate trading signals.
    After signal generation, auto-analyzes high-confidence signals with AI
    and sends Telegram strong buy alerts for conviction ≥ 7."""
    _start = time.monotonic()
    _status, _error = "ok", None

    from zoneinfo import ZoneInfo
    from datetime import datetime

    ET = ZoneInfo("America/New_York")
    now_et = datetime.now(ET)

    # Skip weekends
    if now_et.weekday() >= 5:
        return

    # Skip outside market hours (9:30 AM - 4:00 PM ET)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et < market_open or now_et > market_close:
        return

    # Check Alpaca clock for holidays / early closes
    try:
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        if alpaca_trading_service.is_available:
            clock = alpaca_trading_service._client.get_clock()
            if not clock.is_open:
                return
    except Exception:
        pass  # proceed if clock check fails — weekday+hours check is sufficient

    db = SessionLocal()
    try:
        new_signals = await asyncio.to_thread(signal_engine.process_all_queue_items, db)
        if new_signals:
            logger.info(f"Signal check complete: {len(new_signals)} signals generated")

        # ── AI Pre-Trade Validation (Layer 4) ─────────────────────────
        # Use a dedicated DB session so validator commits don't interfere
        # with the main session used by signal_engine / auto_trader.
        validated_signals = new_signals or []
        if new_signals:
            validation_db = SessionLocal()
            try:
                from app.services.signals.signal_validator import signal_validator
                validation_results = await signal_validator.validate_batch(new_signals, validation_db)
                # Only pass approved signals to auto-trader
                approved_ids = {
                    r["signal_id"] for r in validation_results if r.get("approved")
                }
                validated_signals = [s for s in new_signals if s.id in approved_ids]
                rejected_count = len(new_signals) - len(validated_signals)
                if rejected_count:
                    logger.info(
                        f"Signal validation: {len(validated_signals)} approved, "
                        f"{rejected_count} held for review/rejected"
                    )
                # Refresh validated signals in the main session so auto-trader sees them
                for s in validated_signals:
                    db.refresh(s)
            except Exception as e:
                logger.error(f"Signal validation error (passing all to auto-trader): {e}")
                validated_signals = new_signals  # Fail open — don't block trading
            finally:
                validation_db.close()

        # ── Auto-Trading Pipeline ─────────────────────────────────────
        if validated_signals:
            try:
                from app.services.trading.auto_trader import auto_trader
                executed_trades = await asyncio.to_thread(
                    auto_trader.process_new_signals, validated_signals, db
                )
                if executed_trades:
                    logger.info(f"Auto-trader executed {len(executed_trades)} trades")
            except Exception as e:
                logger.error(f"Auto-trader error: {e}")

        # ── Auto AI Analysis for high-confidence signals ──────────────
        if new_signals:
            try:
                from app.services.ai.auto_analysis import get_auto_analysis_service
                auto_svc = get_auto_analysis_service()

                for ts in new_signals:
                    confidence = ts.confidence_score or 0
                    if auto_svc.should_auto_analyze(confidence):
                        # Open a fresh session for the async analysis
                        analysis_db = SessionLocal()
                        try:
                            signal_dict = ts.to_dict()
                            await auto_svc.auto_analyze_signal(
                                signal_id=ts.id,
                                signal_dict=signal_dict,
                                db_session=analysis_db,
                            )
                        except Exception as e:
                            logger.error(f"Auto-analysis error for {ts.symbol}: {e}")
                        finally:
                            analysis_db.close()
            except Exception as e:
                logger.error(f"Error in auto-analysis pipeline: {e}")

    except Exception as e:
        logger.error(f"Error in signal check job: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("signal_checker", _status, time.monotonic() - _start, _error)


async def calculate_mri_job():
    """Background job to calculate and store MRI snapshot"""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        from app.services.command_center import get_macro_signal_service
        service = get_macro_signal_service()
        mri = await service.calculate_mri(db=db)
        logger.info(f"MRI calculated: {mri.get('mri_score')} ({mri.get('regime')})")
    except Exception as e:
        logger.error(f"Error in MRI calculation job: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("mri_calculator", _status, time.monotonic() - _start, _error)


async def capture_market_snapshots_job():
    """Background job to capture Polymarket market snapshots for time-series"""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        from app.services.command_center import get_polymarket_service
        from app.models.polymarket_snapshot import PolymarketMarketSnapshot
        from datetime import datetime

        polymarket = get_polymarket_service()

        # Get all trading markets with quality scores
        markets = await polymarket.get_trading_markets(limit=100)

        snapshots_created = 0
        for market in markets:
            quality_score = polymarket.calculate_market_quality_score(market)

            # Parse end_date
            end_date = None
            end_date_str = market.get('end_date')
            if end_date_str:
                try:
                    end_date_str = end_date_str.replace('Z', '+00:00')
                    end_date = datetime.fromisoformat(end_date_str)
                except Exception:
                    pass

            snapshot = PolymarketMarketSnapshot(
                market_id=market.get('id', ''),
                category=market.get('category', 'other'),
                title=market.get('title', ''),
                implied_probability=market.get('primary_odds', 50),
                quality_score=quality_score,
                liquidity=market.get('liquidity'),
                volume=market.get('volume'),
                volume_24h=market.get('volume'),  # Use volume as proxy for now
                end_date=end_date,
                days_to_resolution=polymarket._compute_days_to_resolution(market),
            )
            db.add(snapshot)
            snapshots_created += 1

        db.commit()
        logger.info(f"Market snapshots captured: {snapshots_created} markets")
    except Exception as e:
        logger.error(f"Error in market snapshot job: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("market_snapshot_capture", _status, time.monotonic() - _start, _error)


async def calculate_catalysts_job():
    """Background job to calculate and store catalyst snapshots (Macro Intelligence)"""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        from app.services.command_center import get_catalyst_service
        service = get_catalyst_service()
        snapshot = await service.save_snapshot(db)
        if snapshot:
            logger.info(
                f"Catalysts calculated: Liquidity={snapshot.liquidity_score}, "
                f"Readiness={snapshot.trade_readiness_score} ({snapshot.readiness_label})"
            )
        else:
            logger.debug("Catalysts: No significant change, skipped storage")
    except Exception as e:
        logger.error(f"Error in catalyst calculation job: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("catalyst_calculator", _status, time.monotonic() - _start, _error)


async def monitor_positions_job():
    """Background job to monitor open positions for SL/TP/trailing stop exits (every 1 min)."""
    _start = time.monotonic()
    _status, _error = "ok", None

    from zoneinfo import ZoneInfo
    from datetime import datetime

    ET = ZoneInfo("America/New_York")
    now_et = datetime.now(ET)

    # Skip weekends
    if now_et.weekday() >= 5:
        return

    # Skip outside market hours
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=5, second=0, microsecond=0)  # 5 min buffer
    if now_et < market_open or now_et > market_close:
        return

    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        result = await asyncio.to_thread(auto_trader.run_position_monitor, db)
        if result.get("exits", 0) > 0:
            logger.info(f"Position monitor: {result['exits']} exits executed")
    except Exception as e:
        logger.error(f"Position monitor error: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("position_monitor", _status, time.monotonic() - _start, _error)


async def bot_daily_reset_job():
    """Background job to reset daily counters at market open (9:30 AM ET)."""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        await asyncio.to_thread(auto_trader.daily_reset, db)
    except Exception as e:
        logger.error(f"Bot daily reset error: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("bot_daily_reset", _status, time.monotonic() - _start, _error)


async def bot_health_check_job():
    """Background job to verify bot state consistency (every 5 min)."""
    _start = time.monotonic()
    _status, _error = "ok", None
    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        await asyncio.to_thread(auto_trader.run_health_check, db)
    except Exception as e:
        logger.error(f"Bot health check error: {e}")
        _status, _error = "error", str(e)
        db.rollback()
    finally:
        db.close()
        health_monitor.record_job_run("bot_health_check", _status, time.monotonic() - _start, _error)


@app.post("/restart", dependencies=[Depends(require_trading_auth)])
async def restart_server():
    """Restart the server (triggers uvicorn reload). Requires API token auth."""
    import os
    import asyncio

    logger.info("Server restart requested...")

    async def do_restart():
        await asyncio.sleep(0.5)
        # Touch a file to trigger uvicorn's --reload
        os.utime(__file__, None)

    asyncio.create_task(do_restart())
    return {"status": "restarting"}


async def auto_scan_job(skip_market_check: bool = False):
    """
    Scheduled scan automation (interval-based or daily cron).

    Reads auto-scan settings from AppSettings:
      - automation.auto_scan_enabled: bool
      - automation.auto_scan_presets: JSON list of preset ID strings
      - automation.auto_scan_auto_process: bool (run StrategySelector after scan)
      - automation.auto_scan_mode: "interval" or "daily_cron"

    In interval mode, skips outside market hours (9:30-16:00 ET, weekdays only).
    Pipeline: Run screener per-preset → save results to SavedScans → optionally auto-process

    Args:
        skip_market_check: If True, bypass market-hours/weekend/holiday guards (for testing).
    """
    _start = time.monotonic()
    _status, _error = "ok", None
    from app.services.settings_service import settings_service

    enabled = settings_service.get_setting("automation.auto_scan_enabled")
    if not enabled:
        return

    # Market-hours guard for interval mode (bypassed when skip_market_check=True)
    scan_mode = settings_service.get_setting("automation.auto_scan_mode") or "interval"
    if scan_mode == "interval" and not skip_market_check:
        from zoneinfo import ZoneInfo

        ET = ZoneInfo("America/New_York")
        now_et = datetime.now(ET)

        # Skip weekends
        if now_et.weekday() >= 5:
            return

        # Skip outside market hours (9:00 AM - 4:30 PM ET, slightly wider for pre/post scan)
        market_open = now_et.replace(hour=9, minute=0, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=30, second=0, microsecond=0)
        if now_et < market_open or now_et > market_close:
            return

        # Check Alpaca clock for holidays / early closes
        try:
            from app.services.trading.alpaca_trading_service import alpaca_trading_service
            if alpaca_trading_service.is_available:
                clock = alpaca_trading_service._client.get_clock()
                if not clock.is_open:
                    return
        except Exception:
            pass  # proceed if clock check fails

    # ── Smart Scan: auto-select presets from market intelligence ──
    smart_mode = settings_service.get_setting("automation.smart_scan_enabled")
    smart_selection = None

    if smart_mode:
        try:
            from app.services.automation.preset_selector import get_preset_selector
            selector = get_preset_selector()
            smart_db = SessionLocal()
            try:
                smart_selection = await selector.select_presets(smart_db)
            finally:
                smart_db.close()

            if not smart_selection or not smart_selection.get("presets"):
                logger.info(
                    f"[AutoScan] Smart mode: skipping scan "
                    f"({smart_selection.get('reasoning', 'no presets') if smart_selection else 'selector failed'})"
                )
                # Log skip event
                try:
                    from app.models.autopilot_log import AutopilotLog
                    log_db = SessionLocal()
                    try:
                        log_db.add(AutopilotLog(
                            event_type="scan_skipped",
                            market_condition=smart_selection.get("condition") if smart_selection else None,
                            market_snapshot=smart_selection.get("market_snapshot") if smart_selection else None,
                            details={"reasoning": smart_selection.get("reasoning") if smart_selection else "selector failed"},
                        ))
                        log_db.commit()
                    finally:
                        log_db.close()
                except Exception:
                    pass
                return

            presets = smart_selection["presets"]
            auto_process = True  # Always auto-process in smart mode
            snap = smart_selection['market_snapshot']
            logger.info(
                f"[AutoScan] Smart mode: {smart_selection['condition']} "
                f"(score={snap.get('composite_score', '?')}) → {presets} | "
                f"{smart_selection.get('reasoning', '')}"
            )
        except Exception as e:
            logger.error(f"[AutoScan] Smart scan error, falling back to manual presets: {e}")
            smart_mode = False  # Fall through to manual preset reading

    if not smart_mode:
        presets_raw = settings_service.get_setting("automation.auto_scan_presets")
        if not presets_raw:
            logger.info("[AutoScan] No presets configured, skipping")
            return

        import json
        try:
            presets = json.loads(presets_raw) if isinstance(presets_raw, str) else presets_raw
        except (json.JSONDecodeError, TypeError):
            logger.error(f"[AutoScan] Invalid presets config: {presets_raw}")
            return

        if not isinstance(presets, list) or not presets:
            return

        auto_process = settings_service.get_setting("automation.auto_scan_auto_process")

    logger.info(f"[AutoScan] Starting scan: {presets}, auto_process={auto_process}, smart={smart_mode}")

    # Log scan_started event
    try:
        from app.models.autopilot_log import AutopilotLog
        log_db = SessionLocal()
        try:
            log_db.add(AutopilotLog(
                event_type="scan_started",
                market_condition=smart_selection["condition"] if smart_selection else None,
                market_snapshot=smart_selection["market_snapshot"] if smart_selection else None,
                presets_selected=presets,
            ))
            log_db.commit()
        finally:
            log_db.close()
    except Exception:
        pass

    # Imports needed for screening + saving
    from app.data.presets_catalog import LEAPS_PRESETS, _PRESET_DISPLAY_NAMES, resolve_preset
    from app.api.endpoints.screener import (
        screening_engine, convert_numpy_types
    )
    from app.data.stock_universe import get_dynamic_universe
    from app.models.saved_scan import SavedScanResult, SavedScanMetadata

    db = SessionLocal()
    try:
        total_scanned = 0
        total_saved = 0
        total_queued = 0
        preset_summaries = []

        for preset in presets:
            try:
                # Validate preset exists (strict=False: skip unknown, don't crash)
                preset_data = resolve_preset(preset, source="auto_scan", strict=False)
                if not preset_data:
                    continue

                preset_criteria = {k: v for k, v in preset_data.items() if k != "description"}
                display_name = _PRESET_DISPLAY_NAMES.get(preset, preset)
                logger.info(f"[AutoScan] Running preset: {preset} ({display_name})")

                # Get dynamic stock universe for this preset (FMP screener + fallback)
                stock_universe = get_dynamic_universe(preset_criteria)
                logger.info(f"[AutoScan] Preset '{preset}': screening {len(stock_universe)} stocks")

                # Run screening engine in batches (same as stream_scan endpoint)
                all_passed = []
                fail_counts: dict = {}  # Diagnostic: aggregate failure reasons
                batch_size = 15

                for i in range(0, len(stock_universe), batch_size):
                    batch = stock_universe[i:i + batch_size]
                    batch_results = await asyncio.to_thread(
                        screening_engine.screen_multiple_stocks,
                        batch,
                        preset_criteria
                    )
                    if batch_results:
                        batch_results = convert_numpy_types(batch_results)
                        for r in batch_results:
                            if r.get('passed_all', False):
                                all_passed.append(r)
                            else:
                                fa = r.get('failed_at', 'unknown')
                                fail_counts[fa] = fail_counts.get(fa, 0) + 1

                all_passed.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
                # No artificial cap — save all passing stocks
                total_scanned += len(stock_universe)

                # ── Diagnostic: log failure breakdown ──
                if fail_counts:
                    sorted_fails = sorted(fail_counts.items(), key=lambda x: -x[1])
                    breakdown = ", ".join(f"{k}={v}" for k, v in sorted_fails)
                    logger.info(
                        f"[AutoScan] Preset '{preset}': failure breakdown ({sum(fail_counts.values())} failed): {breakdown}"
                    )

                logger.info(f"[AutoScan] Preset '{preset}': {len(all_passed)} stocks passed screening")

                if not all_passed:
                    preset_summaries.append(f"  {display_name}: 0 passed")
                    continue

                # ── Save results to SavedScans ──────────────────────────────
                # Clear existing results for this preset
                db.query(SavedScanResult).filter(
                    SavedScanResult.scan_type == preset
                ).delete()

                saved_count = 0
                for stock in all_passed:
                    db.add(SavedScanResult(
                        scan_type=preset,
                        symbol=stock.get("symbol", ""),
                        company_name=stock.get("company_name") or stock.get("name"),
                        score=stock.get("composite_score") or stock.get("score"),
                        current_price=stock.get("current_price") or stock.get("price"),
                        market_cap=stock.get("market_cap"),
                        iv_rank=stock.get("iv_rank"),
                        iv_percentile=stock.get("iv_percentile"),
                        stock_data=stock,
                        scanned_at=datetime.now()
                    ))
                    saved_count += 1

                # Update or create metadata
                metadata = db.query(SavedScanMetadata).filter(
                    SavedScanMetadata.scan_type == preset
                ).first()
                if metadata:
                    metadata.stock_count = saved_count
                    metadata.last_run_at = datetime.now()
                    metadata.display_name = display_name
                else:
                    db.add(SavedScanMetadata(
                        scan_type=preset,
                        display_name=display_name,
                        stock_count=saved_count,
                        last_run_at=datetime.now()
                    ))

                db.commit()
                total_saved += saved_count
                logger.info(f"[AutoScan] Preset '{preset}': saved {saved_count} results")

                # ── Auto-process: run StrategySelector pipeline ─────────────
                queued_this_preset = 0
                if auto_process and all_passed:
                    try:
                        from app.services.signals.strategy_selector import strategy_selector
                        from app.services.data_fetcher.fmp_service import fmp_service
                        from app.services.data_fetcher.alpaca_service import alpaca_service
                        from app.models.signal_queue import SignalQueue

                        stocks_data = []
                        for stock in all_passed:
                            sd = dict(stock)
                            sd.setdefault("symbol", "")
                            sd.setdefault("score", sd.get("composite_score", 0))
                            sd.setdefault("name", sd.get("company_name", ""))
                            stocks_data.append(sd)

                        symbols = [s["symbol"] for s in stocks_data]

                        bulk_metrics = {}
                        try:
                            bulk_metrics = await asyncio.to_thread(
                                fmp_service.get_bulk_strategy_metrics, symbols
                            )
                        except Exception:
                            pass

                        bulk_snapshots = {}
                        try:
                            bulk_snapshots = await asyncio.to_thread(
                                alpaca_service.get_multi_snapshots, symbols
                            )
                        except Exception:
                            pass

                        categorized = strategy_selector.select_strategies_bulk(
                            stocks_data, bulk_metrics, bulk_snapshots
                        )

                        # Queue HIGH confidence stocks
                        for result in categorized["auto_queued"]:
                            symbol = result["symbol"]
                            for tf_entry in result["timeframes"]:
                                existing = db.query(SignalQueue).filter(
                                    SignalQueue.symbol == symbol,
                                    SignalQueue.timeframe == tf_entry["tf"],
                                    SignalQueue.status == "active",
                                ).first()
                                if not existing:
                                    db.add(SignalQueue(
                                        symbol=symbol,
                                        timeframe=tf_entry["tf"],
                                        strategy="auto",
                                        source="auto_scan",
                                        status="active",
                                        confidence_level=result["confidence"],
                                        strategy_reasoning=result["reasoning"],
                                    ))
                                    queued_this_preset += 1

                        db.commit()
                        total_queued += queued_this_preset
                        logger.info(
                            f"[AutoScan] Preset '{preset}' auto-processed: "
                            f"{len(categorized['auto_queued'])} HIGH, "
                            f"{len(categorized['review_needed'])} MEDIUM, "
                            f"{queued_this_preset} queued"
                        )
                    except Exception as e:
                        logger.error(f"[AutoScan] Auto-process error for {preset}: {e}")
                        db.rollback()

                preset_summaries.append(
                    f"  {display_name}: {saved_count} saved, {queued_this_preset} queued"
                )

            except Exception as e:
                logger.error(f"[AutoScan] Error running preset {preset}: {e}")
                preset_summaries.append(f"  {preset}: ERROR — {e}")

        # Send Telegram summary
        try:
            bot = get_telegram_bot()
            if bot and bot.is_running:
                summary_text = (
                    f"📊 Auto-scan complete\n"
                    f"Presets: {len(presets)} | Scanned: {total_scanned} | "
                    f"Saved: {total_saved} | Queued: {total_queued}\n"
                    + "\n".join(preset_summaries)
                )
                await bot.send_alert(summary_text, alert_type="info")
        except Exception:
            pass

        # ── Top-N Candidate Filter ──────────────────────────────────────
        if smart_mode and total_queued > 0:
            try:
                from app.models.signal_queue import SignalQueue
                from app.models.bot_config import BotConfiguration

                config = db.query(BotConfiguration).first()
                max_candidates = config.autopilot_max_candidates if config else 2

                if total_queued > max_candidates:
                    # Keep top N by confidence, deprioritize the rest
                    active_items = db.query(SignalQueue).filter(
                        SignalQueue.source == "auto_scan",
                        SignalQueue.status == "active",
                    ).order_by(SignalQueue.confidence_level.desc()).all()

                    for i, item in enumerate(active_items):
                        if i >= max_candidates:
                            item.status = "deprioritized"

                    db.commit()
                    deprioritized = max(0, len(active_items) - max_candidates)
                    logger.info(
                        f"[AutoScan] Top-N filter: kept {max_candidates}, "
                        f"deprioritized {deprioritized}"
                    )
            except Exception as e:
                logger.error(f"[AutoScan] Top-N filter error: {e}")

        # ── Log scan_complete event ──────────────────────────────────────
        try:
            from app.models.autopilot_log import AutopilotLog
            log_db2 = SessionLocal()
            try:
                log_db2.add(AutopilotLog(
                    event_type="scan_complete",
                    market_condition=smart_selection["condition"] if smart_selection else None,
                    market_snapshot=smart_selection["market_snapshot"] if smart_selection else None,
                    presets_selected=presets,
                    candidates_found=total_saved,
                    signals_generated=total_queued,
                    details={"preset_summaries": preset_summaries},
                ))
                log_db2.commit()
            finally:
                log_db2.close()
        except Exception:
            pass

        logger.info(
            f"[AutoScan] Complete: {len(presets)} presets, "
            f"{total_scanned} scanned, {total_saved} saved, {total_queued} queued"
        )

    except Exception as e:
        logger.error(f"[AutoScan] Job error: {e}")
        _status, _error = "error", str(e)
        db.rollback()

        # Log scan_failed event so UI doesn't show orphaned "scan started"
        try:
            from app.models.autopilot_log import AutopilotLog
            fail_db = SessionLocal()
            try:
                fail_db.add(AutopilotLog(
                    event_type="scan_failed",
                    market_condition=smart_selection["condition"] if smart_selection else None,
                    market_snapshot=smart_selection["market_snapshot"] if smart_selection else None,
                    presets_selected=presets if 'presets' in dir() else None,
                    details={"error": str(e)},
                ))
                fail_db.commit()
            finally:
                fail_db.close()
        except Exception:
            pass
    finally:
        db.close()
        health_monitor.record_job_run("auto_scan", _status, time.monotonic() - _start, _error)


async def health_alert_job():
    """Send Telegram alert if system health degrades (every 10 min)."""
    _start = time.monotonic()
    _status, _error = "ok", None
    try:
        dashboard = await health_monitor.get_dashboard()
        current_status = dashboard.get("overall_status", "unknown")

        if health_monitor.should_alert(current_status):
            message = health_monitor.format_alert_message(dashboard)
            bot = get_telegram_bot()
            if bot and bot._running:
                sent = await bot.broadcast_to_allowed_users(message)
                if sent:
                    logger.info(f"Health alert sent ({current_status}) to {sent} users")
                health_monitor.record_alert_sent(current_status)
    except Exception as e:
        logger.error(f"Health alert job error: {e}")
        _status, _error = "error", str(e)
    finally:
        health_monitor.record_job_run("health_alert", _status, time.monotonic() - _start, _error)


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("Starting LEAPS Trader API...")
    health_monitor.record_startup()
    # Mask credentials in database URL before logging
    db_url = str(app_settings.DATABASE_URL)
    if "@" in db_url:
        # Mask everything between :// and @ (credentials)
        scheme_end = db_url.find("://")
        at_pos = db_url.rfind("@")
        if scheme_end != -1 and at_pos != -1:
            db_url = db_url[:scheme_end + 3] + "***:***@" + db_url[at_pos + 1:]
    logger.info(f"Database: {db_url}")
    logger.info(f"Redis: {app_settings.REDIS_HOST}:{app_settings.REDIS_PORT}")

    # Initialize database settings
    try:
        from app.database import init_db
        init_db()
        settings_service.seed_defaults()
        settings_service.seed_api_status()
        settings_service.seed_sector_mappings()
        logger.info("Database and settings initialized")

        # Clean up orphaned scan_started events from deploys that killed mid-scan
        try:
            from app.models.autopilot_log import AutopilotLog
            from sqlalchemy import func
            cleanup_db = SessionLocal()
            try:
                # Find scan_started events with no matching scan_complete/scan_failed after them
                orphaned = cleanup_db.query(AutopilotLog).filter(
                    AutopilotLog.event_type == "scan_started",
                ).all()
                cleaned = 0
                for started in orphaned:
                    # Check if there's a completion event after this start
                    has_completion = cleanup_db.query(AutopilotLog).filter(
                        AutopilotLog.event_type.in_(["scan_complete", "scan_failed"]),
                        AutopilotLog.timestamp > started.timestamp,
                    ).first()
                    if not has_completion:
                        started.event_type = "scan_interrupted"
                        started.details = {"reason": "Process restarted before scan completed"}
                        cleaned += 1
                if cleaned:
                    cleanup_db.commit()
                    logger.info(f"Cleaned up {cleaned} orphaned scan_started events")
            finally:
                cleanup_db.close()
        except Exception as e:
            logger.warning(f"Scan cleanup skipped: {e}")
    except Exception as e:
        logger.warning(f"Settings initialization skipped: {e}")

    # Initialize Finviz service if token is configured
    if app_settings.FINVIZ_API_TOKEN:
        initialize_finviz_service(app_settings.FINVIZ_API_TOKEN)
        logger.info("Finviz Elite API enabled")
    else:
        logger.info("Finviz Elite API not configured (optional)")

    # Initialize TastyTrade service if credentials are configured
    if app_settings.TASTYTRADE_PROVIDER_SECRET and app_settings.TASTYTRADE_REFRESH_TOKEN:
        if initialize_tastytrade_service(
            app_settings.TASTYTRADE_PROVIDER_SECRET,
            app_settings.TASTYTRADE_REFRESH_TOKEN
        ):
            logger.info("TastyTrade API enabled (enhanced options data)")
        else:
            logger.warning("TastyTrade API initialization failed")
    else:
        logger.info("TastyTrade API not configured (optional - for enhanced Greeks/IV data)")

    # Initialize Claude AI service if API key is configured
    if app_settings.ANTHROPIC_API_KEY:
        if initialize_claude_service(app_settings.ANTHROPIC_API_KEY):
            logger.info(f"Claude AI enabled (model: {app_settings.CLAUDE_MODEL_PRIMARY})")
        else:
            logger.warning("Claude AI initialization failed")
    else:
        logger.info("Claude AI not configured (optional - for AI-powered analysis)")

    # Initialize Telegram bot if token is configured
    if app_settings.TELEGRAM_BOT_TOKEN:
        if initialize_telegram_bot(
            app_settings.TELEGRAM_BOT_TOKEN,
            app_settings.TELEGRAM_ALLOWED_USERS
        ):
            # Start the bot
            bot = get_telegram_bot()
            await bot.start()
            logger.info("Telegram bot started")
        else:
            logger.warning("Telegram bot initialization failed")
    else:
        logger.info("Telegram bot not configured (optional - for remote commands)")

    # ┌─────────────────────────────────────────────────────────────────────┐
    # │ DOC UPDATE: Adding/removing a scheduler job? Also update:          │
    # │   ARCHITECTURE.md → "Background Jobs" table + Changelog            │
    # └─────────────────────────────────────────────────────────────────────┘
    try:
        now = datetime.now()

        # Check alerts every 5 minutes during market hours
        scheduler.add_job(
            check_alerts_job,
            'interval',
            minutes=5,
            id='alert_checker',
            replace_existing=True,
            misfire_grace_time=300,
            max_instances=1,
            next_run_time=now + timedelta(seconds=30),
        )

        # Check signal queue every 5 minutes for trading signals
        scheduler.add_job(
            check_signals_job,
            'interval',
            minutes=5,
            id='signal_checker',
            replace_existing=True,
            misfire_grace_time=300,
            max_instances=1,
            next_run_time=now + timedelta(seconds=60),
        )

        # Calculate MRI every 15 minutes
        scheduler.add_job(
            calculate_mri_job,
            'interval',
            minutes=15,
            id='mri_calculator',
            replace_existing=True,
            misfire_grace_time=900,
            max_instances=1,
            next_run_time=now + timedelta(seconds=90),
        )

        # Capture market snapshots every 30 minutes for time-series
        scheduler.add_job(
            capture_market_snapshots_job,
            'interval',
            minutes=30,
            id='market_snapshot_capture',
            replace_existing=True,
            misfire_grace_time=1800,
            max_instances=1,
            next_run_time=now + timedelta(seconds=120),
        )

        # Calculate catalysts every 60 minutes (smart cadence skips if unchanged)
        scheduler.add_job(
            calculate_catalysts_job,
            'interval',
            minutes=60,
            id='catalyst_calculator',
            replace_existing=True,
            misfire_grace_time=3600,
            max_instances=1,
            next_run_time=now + timedelta(seconds=150),
        )

        # ── Trading Bot Scheduler Jobs ──────────────────────────────
        # Position monitor: every 1 minute during market hours
        scheduler.add_job(
            monitor_positions_job,
            'interval',
            minutes=1,
            id='position_monitor',
            replace_existing=True,
            misfire_grace_time=60,
            max_instances=1,
            next_run_time=now + timedelta(seconds=15),
        )

        # Daily reset: 9:30 AM ET weekdays
        scheduler.add_job(
            bot_daily_reset_job,
            'cron',
            day_of_week='mon-fri',
            hour=9,
            minute=30,
            timezone='America/New_York',
            id='bot_daily_reset',
            replace_existing=True,
            misfire_grace_time=3600,
            max_instances=1,
        )

        # Health check: every 5 minutes
        scheduler.add_job(
            bot_health_check_job,
            'interval',
            minutes=5,
            id='bot_health_check',
            replace_existing=True,
            misfire_grace_time=300,
            max_instances=1,
            next_run_time=now + timedelta(seconds=45),
        )

        # Auto-Scan: interval-based (default 30min) or daily cron (8:30 CT)
        try:
            scan_mode = settings_service.get_setting("automation.auto_scan_mode") or "interval"
            scan_interval = settings_service.get_setting("automation.auto_scan_interval_minutes") or 30
            scan_interval = max(15, min(120, int(scan_interval)))  # clamp 15-120 min
        except Exception:
            scan_mode = "interval"
            scan_interval = 30

        if scan_mode == "daily_cron":
            scheduler.add_job(
                auto_scan_job,
                'cron',
                day_of_week='mon-fri',
                hour=8,
                minute=30,
                timezone='America/Chicago',
                id='auto_scan',
                replace_existing=True,
                misfire_grace_time=300,
                max_instances=1,
            )
            auto_scan_schedule = "daily 8:30CT"
        else:
            scheduler.add_job(
                auto_scan_job,
                'interval',
                minutes=scan_interval,
                id='auto_scan',
                replace_existing=True,
                misfire_grace_time=300,
                max_instances=1,
                next_run_time=now + timedelta(seconds=180),
            )
            auto_scan_schedule = f"every {scan_interval}min (market hours)"

        # Health alert: every 10 minutes — sends Telegram on status degradation
        scheduler.add_job(
            health_alert_job,
            'interval',
            minutes=10,
            id='health_alert',
            replace_existing=True,
            misfire_grace_time=600,
            max_instances=1,
            next_run_time=now + timedelta(seconds=300),  # First check 5min after startup
        )

        scheduler.start()
        logger.info(
            "Schedulers started (alerts: 5min, signals: 5min, positions: 1min, "
            "bot_reset: 9:30ET, health: 5min, MRI: 15min, snapshots: 30min, "
            f"catalysts: 60min, auto_scan: {auto_scan_schedule}, health_alert: 10min)"
        )
    except Exception as e:
        logger.error(f"Failed to start alert scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Shutting down LEAPS Trader API...")

    # Stop alert scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Alert scheduler stopped")

    # Stop Telegram bot if running
    bot = get_telegram_bot()
    if bot.is_running():
        await bot.stop()
        logger.info("Telegram bot stopped")

    # Close all aiohttp sessions to prevent resource leaks
    sessions_closed = 0
    try:
        from app.services.data_fetcher.fmp_service import fmp_service
        await fmp_service.close()
        sessions_closed += 1
    except Exception:
        pass
    try:
        from app.services.command_center import (
            get_market_data_service, get_news_service, get_news_feed_service,
            get_polymarket_service,
        )
        await get_market_data_service().close()
        sessions_closed += 1
        await get_news_service().close()
        sessions_closed += 1
        await get_news_feed_service().close()
        sessions_closed += 1
        await get_polymarket_service().close()
        sessions_closed += 1
    except Exception:
        pass
    try:
        from app.services.data_providers.fred.fred_service import get_fred_service
        await get_fred_service().close()
        sessions_closed += 1
    except Exception:
        pass
    if sessions_closed:
        logger.info(f"Closed {sessions_closed} aiohttp session(s)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
