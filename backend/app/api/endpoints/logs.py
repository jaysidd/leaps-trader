"""
Logs API endpoint — serves recent application logs from the Redis ring buffer.

The loguru redis_log_sink pushes JSON entries into Redis key "app:logs".
This endpoint reads them back with optional filtering by level, module, or
free-text search.
"""
import json
from typing import Optional

from fastapi import APIRouter, Query
from loguru import logger

from app.services.cache import cache_service

router = APIRouter()

LOG_KEY = "app:logs"


@router.get("/")
async def get_logs(
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARNING, ERROR, DEBUG)"),
    search: Optional[str] = Query(None, description="Free-text search in log messages"),
    module: Optional[str] = Query(None, description="Filter by module name"),
    limit: int = Query(200, ge=1, le=5000, description="Max entries to return"),
):
    """Fetch recent logs from the Redis ring buffer."""
    try:
        r = cache_service.redis_client
        raw = r.lrange(LOG_KEY, 0, min(limit * 2, 5000) - 1)  # Fetch extra to allow for filtering
    except Exception as e:
        logger.warning(f"Failed to read logs from Redis: {e}")
        return {"logs": [], "total": 0, "error": str(e)}

    logs = []
    for entry in raw:
        try:
            parsed = json.loads(entry)
            logs.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue

    # Apply filters
    if level:
        level_upper = level.upper()
        logs = [l for l in logs if l.get("level") == level_upper]
    if search:
        search_lower = search.lower()
        logs = [l for l in logs if search_lower in l.get("msg", "").lower()]
    if module:
        module_lower = module.lower()
        logs = [l for l in logs if module_lower in l.get("module", "").lower()]

    # Trim to requested limit
    logs = logs[:limit]

    return {"logs": logs, "total": len(logs)}
