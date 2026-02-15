"""
Redis log sink for loguru — pushes structured log entries into a Redis list
acting as a fixed-size ring buffer (LPUSH + LTRIM).

Usage (in main.py):
    from loguru import logger
    from app.services.log_sink import redis_log_sink
    logger.add(redis_log_sink, level="INFO", format="{message}")
"""
import json
import time

LOG_KEY = "app:logs"
MAX_LOG_ENTRIES = 5000

# Circuit breaker: skip Redis writes for 60s after a failure
_circuit_open_until = 0.0


def redis_log_sink(message):
    """Loguru custom sink: push structured JSON log entry into Redis list."""
    global _circuit_open_until

    # Skip if circuit breaker is open (Redis recently failed)
    if time.monotonic() < _circuit_open_until:
        return

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
        # Open circuit breaker — don't retry for 60 seconds
        _circuit_open_until = time.monotonic() + 60
