"""
Redis log sink for loguru — pushes structured log entries into a Redis list
acting as a fixed-size ring buffer (LPUSH + LTRIM).

Usage (in main.py):
    from loguru import logger
    from app.services.log_sink import redis_log_sink
    logger.add(redis_log_sink, level="INFO", format="{message}")
"""
import json

LOG_KEY = "app:logs"
MAX_LOG_ENTRIES = 5000


def redis_log_sink(message):
    """Loguru custom sink: push structured JSON log entry into Redis list."""
    record = message.record
    entry = json.dumps({
        "ts": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "level": record["level"].name,
        "msg": str(record["message"]),
        "module": record["module"],
        "func": record["function"],
        "line": record["line"],
    })
    try:
        from app.services.cache import cache_service
        r = cache_service.redis_client
        r.lpush(LOG_KEY, entry)
        r.ltrim(LOG_KEY, 0, MAX_LOG_ENTRIES - 1)
    except Exception:
        pass  # Never let logging crash the app
