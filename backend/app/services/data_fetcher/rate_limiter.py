"""
Rate limiter for API requests
"""
import time
from collections import deque
from threading import Lock
from loguru import logger


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, max_requests: int, time_window: int):
        """
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()

    def wait_if_needed(self):
        """Wait if rate limit is exceeded"""
        with self.lock:
            now = time.time()

            # Remove old requests outside the time window
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            # If we're at the limit, wait
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    # Remove old requests again after sleeping
                    now = time.time()
                    while self.requests and self.requests[0] < now - self.time_window:
                        self.requests.popleft()

            # Record this request
            self.requests.append(time.time())

    def can_make_request(self) -> bool:
        """Check if we can make a request without waiting"""
        with self.lock:
            now = time.time()
            # Remove old requests
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()
            return len(self.requests) < self.max_requests


class DailyRateLimiter:
    """Daily rate limiter with reset at midnight"""

    def __init__(self, max_requests_per_day: int):
        self.max_requests = max_requests_per_day
        self.count = 0
        self.last_reset = time.time()
        self.lock = Lock()

    def wait_if_needed(self):
        """Check if we've exceeded daily limit"""
        with self.lock:
            # Reset if it's a new day (simplified - resets every 24 hours)
            now = time.time()
            if now - self.last_reset > 86400:  # 24 hours
                self.count = 0
                self.last_reset = now

            if self.count >= self.max_requests:
                raise Exception(f"Daily rate limit of {self.max_requests} exceeded")

            self.count += 1

    def get_remaining(self) -> int:
        """Get remaining requests for today"""
        with self.lock:
            return max(0, self.max_requests - self.count)
