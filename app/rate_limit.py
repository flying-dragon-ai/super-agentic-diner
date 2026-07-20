"""Small Redis-backed fixed-window rate limiter with a process-local fallback."""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.memory._redis_client import get_redis_client


@dataclass
class _LocalWindow:
    started_at: float
    count: int


_local_lock = threading.Lock()
_local_windows: dict[str, _LocalWindow] = {}


def _principal(request: Request, identity: str | None) -> str:
    if identity:
        return identity[:256]
    client = request.client
    return client.host if client is not None else "unknown"


def _key(scope: str, principal: str) -> str:
    digest = hashlib.sha256(principal.encode("utf-8")).hexdigest()[:24]
    return f"coffee:rate:{scope}:{digest}"


def _local_increment(key: str, window_seconds: int) -> int:
    now = time.monotonic()
    with _local_lock:
        current = _local_windows.get(key)
        if current is None or now - current.started_at >= window_seconds:
            _local_windows[key] = _LocalWindow(started_at=now, count=1)
            return 1
        current.count += 1
        # Opportunistically cap memory if a process sees many one-off clients.
        if len(_local_windows) > 10_000:
            cutoff = now - window_seconds
            for stale_key, value in list(_local_windows.items())[:2000]:
                if value.started_at < cutoff:
                    _local_windows.pop(stale_key, None)
        return current.count


def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int = 60,
    identity: str | None = None,
) -> None:
    """Raise a structured HTTP 429 after ``limit`` requests in one window."""
    safe_limit = max(int(limit), 1)
    safe_window = max(int(window_seconds), 1)
    redis_key = _key(scope, _principal(request, identity))
    try:
        client = get_redis_client(decode_responses=True)
        count = client.eval(
            "local n=redis.call('INCR',KEYS[1]); "
            "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end; return n",
            1,
            redis_key,
            safe_window,
        )
        count = int(count)
    except Exception:
        count = _local_increment(redis_key, safe_window)

    if count > safe_limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": "请求过于频繁，请稍后重试",
            },
            headers={"Retry-After": str(safe_window)},
        )
