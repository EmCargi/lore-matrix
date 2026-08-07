"""
Canonical thread-safe concurrency helpers for parallel pipeline stages.
"""
import threading
import time


class RateLimiter:
    """
    Thread-safe rate limiter to control requests per second.
    """
    def __init__(self, delay_seconds):
        self.delay_seconds = delay_seconds
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        if self.delay_seconds <= 0:
            return
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay_seconds:
                sleep_time = self.delay_seconds - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()


def make_safe_print():
    """
    Returns a thread-safe print that prevents interleaved stdout lines.
    """
    lock = threading.Lock()
    original_print = print

    def safe_print(*args, **kwargs):
        kwargs.setdefault('flush', True)
        with lock:
            original_print(*args, **kwargs)

    return safe_print
