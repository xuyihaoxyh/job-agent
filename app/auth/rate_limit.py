from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict, deque
from time import monotonic


class LoginRateLimiter:
    """Small single-process limiter for password attempts.

    It protects the default one-process deployment. A shared limiter should
    replace it if the application later runs with multiple workers.
    """

    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @staticmethod
    def key(client_host: str, login: str) -> str:
        value = f"{client_host}:{login.casefold().strip()}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def allowed(self, key: str) -> bool:
        async with self._lock:
            attempts = self._active_attempts(key)
            return len(attempts) < self._max_attempts

    async def record_failure(self, key: str) -> None:
        async with self._lock:
            attempts = self._active_attempts(key)
            attempts.append(monotonic())

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._attempts.pop(key, None)

    def _active_attempts(self, key: str) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = monotonic() - self._window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts
