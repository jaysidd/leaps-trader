"""
Health monitoring API endpoints.

Provides a system health dashboard, individual dependency checks,
and scheduler job status for the monitoring UI.
"""
from fastapi import APIRouter
from loguru import logger

from app.services.health_monitor import health_monitor

router = APIRouter()


@router.get("/dashboard")
async def get_health_dashboard():
    """
    Aggregated health dashboard — all subsystems at a glance.

    Returns overall status, dependency health, scheduler job status,
    auto-scan health, trading bot state, and Telegram status.
    """
    try:
        return await health_monitor.get_dashboard()
    except Exception as e:
        logger.error(f"Health dashboard error: {e}")
        return {"overall_status": "unknown", "error": str(e)}


@router.get("/dependencies")
async def check_dependencies():
    """
    Check all critical dependencies (DB, Redis, Alpaca, Scheduler).
    Returns per-dependency status with latency measurements.
    """
    try:
        return await health_monitor.check_all_dependencies()
    except Exception as e:
        logger.error(f"Dependency check error: {e}")
        return {"error": str(e)}


@router.get("/jobs")
async def get_scheduler_jobs():
    """
    Status of all scheduler jobs.
    Includes last run, duration, error count, overdue status.
    """
    try:
        return health_monitor.get_all_jobs_health()
    except Exception as e:
        logger.error(f"Jobs health error: {e}")
        return {"error": str(e)}


@router.get("/jobs/{job_id}")
async def get_scheduler_job(job_id: str):
    """Status of a single scheduler job."""
    result = health_monitor.get_job_health(job_id)
    if result is None:
        return {"error": f"Unknown job: {job_id}"}
    return result


@router.post("/check")
async def force_health_check():
    """
    Force a full health check (refreshes all dependency + job data).
    Bypasses the 60s dependency cache. Useful for manual verification.
    """
    try:
        # Force-refresh dependencies
        deps = await health_monitor.check_all_dependencies(force=True)
        dashboard = await health_monitor.get_dashboard()
        return dashboard
    except Exception as e:
        logger.error(f"Forced health check error: {e}")
        return {"overall_status": "unknown", "error": str(e)}
