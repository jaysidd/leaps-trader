"""
Health Monitor — centralized system health tracking.

Tracks scheduler job execution via Redis, checks dependency health
(DB, Redis, Alpaca, Scheduler), aggregates everything into a dashboard,
and sends Telegram alerts on status transitions.

All state is stored in Redis with short TTLs — no DB migrations needed.
"""
import time
import json
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger


# ── Job expectations for overdue detection ────────────────────────────────────

JOB_EXPECTATIONS = {
    "alert_checker":            {"interval": 300,   "tolerance": 2.5, "market_hours": False, "label": "Alert Checker"},
    "signal_checker":           {"interval": 300,   "tolerance": 2.5, "market_hours": True,  "label": "Signal Checker"},
    "mri_calculator":           {"interval": 900,   "tolerance": 2.5, "market_hours": False, "label": "MRI Calculator"},
    "market_snapshot_capture":  {"interval": 1800,  "tolerance": 2.5, "market_hours": False, "label": "Market Snapshots"},
    "catalyst_calculator":      {"interval": 3600,  "tolerance": 2.5, "market_hours": False, "label": "Catalyst Calculator"},
    "position_monitor":         {"interval": 60,    "tolerance": 3.0, "market_hours": True,  "label": "Position Monitor"},
    "bot_daily_reset":          {"interval": 86400, "tolerance": 1.5, "market_hours": False, "label": "Bot Daily Reset"},
    "bot_health_check":         {"interval": 300,   "tolerance": 2.5, "market_hours": False, "label": "Bot Health Check"},
    "auto_scan":                {"interval": 1800,  "tolerance": 2.5, "market_hours": True,  "label": "Auto Scan"},
    "health_alert":             {"interval": 600,   "tolerance": 2.5, "market_hours": False, "label": "Health Alert"},
}

# Alert cooldown in seconds (don't spam)
ALERT_COOLDOWN = 1800  # 30 minutes

# Dependency check cache TTL
DEP_CACHE_TTL = 60  # seconds


class HealthMonitor:
    """
    Centralized health monitoring for all subsystems.
    Stores state in Redis. No DB tables needed.
    """

    def __init__(self):
        self._redis = None
        self._dep_cache = {}
        self._dep_cache_time = 0

    @property
    def redis(self):
        """Lazy Redis client (avoids import-time connection)."""
        if self._redis is None:
            try:
                from app.services.cache import cache_service
                self._redis = cache_service.redis_client
            except Exception:
                pass
        return self._redis

    # ── Startup ───────────────────────────────────────────────────────────

    def record_startup(self):
        """Record when the application started."""
        try:
            r = self.redis
            if r:
                r.set("health:uptime_started_at", datetime.utcnow().isoformat())
                logger.info("Health monitor: startup recorded")
        except Exception as e:
            logger.debug(f"Health monitor: failed to record startup: {e}")

    def get_uptime_seconds(self) -> float:
        """Get seconds since last startup."""
        try:
            r = self.redis
            if r:
                started = r.get("health:uptime_started_at")
                if started:
                    start_dt = datetime.fromisoformat(started)
                    return (datetime.utcnow() - start_dt).total_seconds()
        except Exception:
            pass
        return 0

    # ── Job Tracking ──────────────────────────────────────────────────────

    def record_job_run(self, job_id: str, status: str, duration_sec: float, error: str = None):
        """
        Record a scheduler job execution.

        Args:
            job_id: Job identifier (e.g. "auto_scan", "signal_checker")
            status: "ok" or "error"
            duration_sec: How long the job took
            error: Error message if status == "error"
        """
        try:
            r = self.redis
            if not r:
                return

            prefix = f"health:job:{job_id}"
            pipe = r.pipeline()
            pipe.set(f"{prefix}:last_run", datetime.utcnow().isoformat())
            pipe.set(f"{prefix}:last_duration", f"{duration_sec:.3f}")
            pipe.set(f"{prefix}:last_status", status)

            if status == "ok":
                pipe.set(f"{prefix}:last_error", "")
                pipe.set(f"{prefix}:error_count", "0")
                pipe.incr(f"{prefix}:success_count")
            else:
                pipe.set(f"{prefix}:last_error", error or "unknown")
                pipe.incr(f"{prefix}:error_count")

            pipe.execute()
        except Exception as e:
            # Never let health tracking crash a job
            logger.debug(f"Health monitor: failed to record job {job_id}: {e}")

    def get_job_health(self, job_id: str) -> Optional[dict]:
        """Get health status for a single scheduler job."""
        if job_id not in JOB_EXPECTATIONS:
            return None

        expectations = JOB_EXPECTATIONS[job_id]
        result = {
            "job_id": job_id,
            "label": expectations.get("label", job_id),
            "expected_interval_sec": expectations["interval"],
            "last_run": None,
            "last_duration_sec": None,
            "last_status": "unknown",
            "last_error": None,
            "error_count": 0,
            "success_count": 0,
            "is_overdue": False,
            "next_expected_by": None,
        }

        try:
            r = self.redis
            if not r:
                return result

            prefix = f"health:job:{job_id}"
            last_run = r.get(f"{prefix}:last_run")
            last_duration = r.get(f"{prefix}:last_duration")
            last_status = r.get(f"{prefix}:last_status")
            last_error = r.get(f"{prefix}:last_error")
            error_count = r.get(f"{prefix}:error_count")
            success_count = r.get(f"{prefix}:success_count")

            if last_run:
                result["last_run"] = last_run
            if last_duration:
                result["last_duration_sec"] = round(float(last_duration), 3)
            if last_status:
                result["last_status"] = last_status
            if last_error:
                result["last_error"] = last_error if last_error else None
            result["error_count"] = int(error_count or 0)
            result["success_count"] = int(success_count or 0)

            # Compute overdue status
            if last_run:
                last_run_dt = datetime.fromisoformat(last_run)
                max_delay = expectations["interval"] * expectations["tolerance"]
                deadline = last_run_dt + timedelta(seconds=max_delay)
                result["next_expected_by"] = deadline.isoformat()

                now = datetime.utcnow()
                if now > deadline:
                    # Skip overdue check for market-hours jobs outside market hours
                    if expectations.get("market_hours") and not self._is_market_hours():
                        result["is_overdue"] = False
                    else:
                        result["is_overdue"] = True

        except Exception as e:
            logger.debug(f"Health monitor: failed to read job {job_id}: {e}")

        return result

    def get_all_jobs_health(self) -> dict:
        """Get health status for all scheduler jobs."""
        jobs = {}
        for job_id in JOB_EXPECTATIONS:
            jobs[job_id] = self.get_job_health(job_id)
        return jobs

    # ── Dependency Checks ─────────────────────────────────────────────────

    async def check_all_dependencies(self, force: bool = False) -> dict:
        """
        Check all critical dependencies. Results are cached for 60s
        to keep Railway health probes fast.
        """
        now = time.monotonic()
        if not force and self._dep_cache and (now - self._dep_cache_time) < DEP_CACHE_TTL:
            return self._dep_cache

        deps = {}
        deps["database"] = await self._check_database()
        deps["redis"] = self._check_redis()
        deps["alpaca"] = self._check_alpaca()
        deps["scheduler"] = self._check_scheduler()

        self._dep_cache = deps
        self._dep_cache_time = now

        return deps

    async def _check_database(self) -> dict:
        """Ping the database with SELECT 1."""
        start = time.monotonic()
        try:
            from app.database import engine
            import asyncio
            from sqlalchemy import text

            def _ping():
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

            await asyncio.to_thread(_ping)
            latency = (time.monotonic() - start) * 1000
            return {"ok": True, "latency_ms": round(latency, 1)}
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return {"ok": False, "latency_ms": round(latency, 1), "error": str(e)[:200]}

    def _check_redis(self) -> dict:
        """Ping Redis."""
        start = time.monotonic()
        try:
            r = self.redis
            if not r:
                return {"ok": False, "latency_ms": 0, "error": "Redis client not available"}
            r.ping()
            latency = (time.monotonic() - start) * 1000
            return {"ok": True, "latency_ms": round(latency, 1)}
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return {"ok": False, "latency_ms": round(latency, 1), "error": str(e)[:200]}

    def _check_alpaca(self) -> dict:
        """Check Alpaca API connectivity."""
        start = time.monotonic()
        try:
            from app.services.trading.alpaca_trading_service import alpaca_trading_service
            if not alpaca_trading_service.is_available:
                return {"ok": False, "latency_ms": 0, "error": "Alpaca not configured"}

            clock = alpaca_trading_service.get_clock()
            latency = (time.monotonic() - start) * 1000
            return {
                "ok": True,
                "latency_ms": round(latency, 1),
                "market_open": clock.get("is_open") if clock else None,
            }
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return {"ok": False, "latency_ms": round(latency, 1), "error": str(e)[:200]}

    def _check_scheduler(self) -> dict:
        """Check APScheduler status."""
        try:
            from app.main import scheduler
            running = scheduler.running
            jobs = scheduler.get_jobs()
            return {
                "ok": running,
                "running": running,
                "job_count": len(jobs),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── Dashboard Aggregation ─────────────────────────────────────────────

    async def get_dashboard(self) -> dict:
        """
        Full aggregated health dashboard — one API call gets everything.
        """
        deps = await self.check_all_dependencies()
        jobs = self.get_all_jobs_health()

        # Auto-scan specific info
        auto_scan_info = self._get_auto_scan_info(jobs.get("auto_scan"))

        # Trading bot health
        bot_info = self._get_bot_info()

        # Telegram status
        telegram_info = self._get_telegram_info()

        # Overall status
        overall = self._compute_overall_status(deps, jobs, bot_info)

        return {
            "overall_status": overall,
            "uptime_seconds": round(self.get_uptime_seconds(), 0),
            "checked_at": datetime.utcnow().isoformat(),
            "dependencies": deps,
            "scheduler_jobs": jobs,
            "auto_scan": auto_scan_info,
            "trading_bot": bot_info,
            "telegram": telegram_info,
        }

    def _get_auto_scan_info(self, job_health: dict) -> dict:
        """Get auto-scan specific health details."""
        info = {
            "enabled": False,
            "presets": [],
            "smart_scan_enabled": False,
            "last_run": None,
            "last_status": "unknown",
            "last_duration_sec": None,
            "is_overdue": False,
        }

        try:
            from app.services.settings_service import settings_service
            info["enabled"] = bool(settings_service.get_setting("automation.auto_scan_enabled"))
            presets_raw = settings_service.get_setting("automation.auto_scan_presets") or "[]"
            if isinstance(presets_raw, str):
                info["presets"] = json.loads(presets_raw)
            elif isinstance(presets_raw, list):
                info["presets"] = presets_raw
            info["smart_scan_enabled"] = bool(
                settings_service.get_setting("automation.smart_scan_enabled")
            )
        except Exception:
            pass

        if job_health:
            info["last_run"] = job_health.get("last_run")
            info["last_status"] = job_health.get("last_status", "unknown")
            info["last_duration_sec"] = job_health.get("last_duration_sec")
            info["is_overdue"] = job_health.get("is_overdue", False)

        return info

    def _get_bot_info(self) -> dict:
        """Get trading bot health from BotState."""
        info = {
            "status": "unknown",
            "circuit_breaker": "none",
            "consecutive_errors": 0,
            "last_health_check": None,
            "last_error": None,
            "open_positions": 0,
        }

        try:
            from app.database import SessionLocal
            from app.models.bot_state import BotState

            db = SessionLocal()
            try:
                state = db.query(BotState).first()
                if state:
                    info["status"] = state.status or "stopped"
                    info["circuit_breaker"] = state.circuit_breaker_level or "none"
                    info["consecutive_errors"] = state.consecutive_errors or 0
                    info["last_health_check"] = (
                        state.last_health_check.isoformat() if state.last_health_check else None
                    )
                    info["last_error"] = state.last_error
                    info["open_positions"] = (state.open_positions_count or 0)
            finally:
                db.close()
        except Exception as e:
            info["error"] = str(e)[:200]

        return info

    def _get_telegram_info(self) -> dict:
        """Get Telegram bot status."""
        try:
            from app.services.telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            return {
                "configured": bot.application is not None,
                "running": bot._running,
                "allowed_users": len(bot.allowed_users),
            }
        except Exception:
            return {"configured": False, "running": False, "allowed_users": 0}

    def _compute_overall_status(self, deps: dict, jobs: dict, bot_info: dict) -> str:
        """
        Compute overall system health.
          critical: DB or Redis down, or scheduler stopped
          degraded: Any job overdue, Alpaca down, bot errors ≥ 3
          healthy: Everything else
        """
        # Critical checks
        db_dep = deps.get("database", {})
        redis_dep = deps.get("redis", {})
        sched_dep = deps.get("scheduler", {})

        if not db_dep.get("ok"):
            return "critical"
        if not redis_dep.get("ok"):
            return "critical"
        if not sched_dep.get("ok"):
            return "critical"

        # Degraded checks
        alpaca_dep = deps.get("alpaca", {})
        if not alpaca_dep.get("ok") and alpaca_dep.get("error") != "Alpaca not configured":
            return "degraded"

        for job_id, job in jobs.items():
            if job and job.get("is_overdue"):
                return "degraded"
            if job and job.get("error_count", 0) >= 3:
                return "degraded"

        if bot_info.get("consecutive_errors", 0) >= 3:
            return "degraded"

        return "healthy"

    # ── Alerting ──────────────────────────────────────────────────────────

    def should_alert(self, current_status: str) -> bool:
        """
        Determine if a Telegram alert should be sent.
        Only alert on status transitions with a 30-minute cooldown.
        """
        try:
            r = self.redis
            if not r:
                return False

            last_status = r.get("health:last_alerted_status") or "healthy"
            last_alert_time = r.get("health:last_alert_time")

            # Only alert on status worsening
            severity = {"healthy": 0, "degraded": 1, "critical": 2}
            current_sev = severity.get(current_status, 0)
            last_sev = severity.get(last_status, 0)

            if current_sev <= last_sev:
                # Also send recovery alert when going from bad to healthy
                if current_status == "healthy" and last_status != "healthy":
                    pass  # Allow recovery alert
                else:
                    return False

            # Check cooldown
            if last_alert_time:
                last_dt = datetime.fromisoformat(last_alert_time)
                if (datetime.utcnow() - last_dt).total_seconds() < ALERT_COOLDOWN:
                    return False

            return True
        except Exception:
            return False

    def record_alert_sent(self, status: str):
        """Record that an alert was sent (for cooldown tracking)."""
        try:
            r = self.redis
            if r:
                r.set("health:last_alerted_status", status)
                r.set("health:last_alert_time", datetime.utcnow().isoformat())
        except Exception:
            pass

    def format_alert_message(self, dashboard: dict) -> str:
        """Format a Telegram-friendly health alert message."""
        status = dashboard.get("overall_status", "unknown")
        emoji_map = {"healthy": "\u2705", "degraded": "\u26a0\ufe0f", "critical": "\U0001f6a8"}
        emoji = emoji_map.get(status, "\u2753")

        lines = [f"{emoji} *System Health: {status.upper()}*\n"]

        # Dependencies
        deps = dashboard.get("dependencies", {})
        for name, info in deps.items():
            icon = "\u2705" if info.get("ok") else "\u274c"
            latency = f" ({info.get('latency_ms', 0):.0f}ms)" if info.get("ok") and info.get("latency_ms") else ""
            error = f" \u2014 {info.get('error', '')}" if not info.get("ok") and info.get("error") else ""
            lines.append(f"  {icon} {name}{latency}{error}")

        # Overdue jobs
        jobs = dashboard.get("scheduler_jobs", {})
        overdue = [jid for jid, j in jobs.items() if j and j.get("is_overdue")]
        if overdue:
            lines.append(f"\n*Overdue Jobs:* {', '.join(overdue)}")

        # Failed jobs
        errored = [jid for jid, j in jobs.items() if j and j.get("last_status") == "error"]
        if errored:
            lines.append(f"*Failed Jobs:* {', '.join(errored)}")

        # Bot state
        bot = dashboard.get("trading_bot", {})
        if bot.get("consecutive_errors", 0) >= 3:
            lines.append(f"\n*Bot Errors:* {bot['consecutive_errors']} consecutive")
        if bot.get("circuit_breaker") and bot["circuit_breaker"] != "none":
            lines.append(f"*Circuit Breaker:* {bot['circuit_breaker']}")

        uptime_hrs = dashboard.get("uptime_seconds", 0) / 3600
        lines.append(f"\n_Uptime: {uptime_hrs:.1f}h_")

        return "\n".join(lines)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _is_market_hours() -> bool:
        """Check if we're within US market hours (9:00-16:30 ET, weekdays)."""
        try:
            from zoneinfo import ZoneInfo
            ET = ZoneInfo("America/New_York")
            now_et = datetime.now(ET)

            # Skip weekends
            if now_et.weekday() >= 5:
                return False

            market_open = now_et.replace(hour=9, minute=0, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=30, second=0, microsecond=0)
            return market_open <= now_et <= market_close
        except Exception:
            return True  # Assume market hours if check fails


# Singleton
health_monitor = HealthMonitor()
