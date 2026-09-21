from __future__ import annotations

import time
from collections import defaultdict, deque

from app.errors import ApiError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: float) -> None:
        now = time.time()
        q = self._hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            raise ApiError(429, "rate_limited", "Trop de requêtes. Réessaie dans un moment.")
        q.append(now)


limiter = RateLimiter()
