"""A bounded executor for the handful of genuinely heavy request handlers.

Starlette runs a synchronous ``def`` handler on the anyio worker pool (40
threads by default) shared by *every* sync route. That is fine while handlers
are small, but a few multi-second scans — a full workspace context assembly, a
deep file walk, a run export — can occupy the pool long enough that
``GET /api/health`` queues behind them and the server reads as down.

Heavy handlers therefore become ``async def`` and ``await run_heavy(...)``,
which moves them onto a **separate, deliberately small** pool. Two effects:

* the shared pool stays free for cheap reads, so health and snapshot-backed
  lists answer immediately;
* heavy work is self-limiting — two concurrent full scans, not forty, which is
  what a filesystem-bound job wants anyway.
"""

from __future__ import annotations

import asyncio
import atexit
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

__all__ = ["heavy_executor", "run_heavy", "shutdown_heavy_executor"]

_HEAVY_WORKERS = 2

_executor: ThreadPoolExecutor | None = None


def heavy_executor() -> ThreadPoolExecutor:
    """The process-wide heavy pool, created on first use."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_HEAVY_WORKERS, thread_name_prefix="molexp-heavy"
        )
        atexit.register(shutdown_heavy_executor)
    return _executor


def shutdown_heavy_executor(*, wait: bool = False) -> None:
    """Tear the pool down (server shutdown; safe to call more than once)."""
    global _executor
    executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=True)


async def run_heavy[T](fn: Callable[..., T], /, *args: object, **kwargs: object) -> T:
    """Run *fn* on the heavy pool and await its result.

    Keyword arguments are supported (``run_in_executor`` alone does not take
    them), so a handler can call a domain function in its natural shape.
    """
    loop = asyncio.get_running_loop()
    if kwargs:
        from functools import partial

        return await loop.run_in_executor(heavy_executor(), partial(fn, *args, **kwargs))
    return await loop.run_in_executor(heavy_executor(), fn, *args)
