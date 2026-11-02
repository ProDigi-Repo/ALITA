"""Concurrency for many users on one backend process (REQ-83).

The chat pipelines mix async LLM calls with blocking Qdrant/Neo4j calls and CPU work. Run directly on the server's
event loop, one person's question would freeze every other request. Instead each chat runs on its own event loop in a
worker thread (``CHAT_THREADS`` at a time, further questions wait in line); the server loop only relays the events.

The request context goes along (``contextvars``): the databases the request may see (``visibility``) and the token
meter (``usage``) apply inside the thread exactly as before. pydantic-ai creates a new HTTP client per provider, so
nothing is shared between event loops.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")

_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()
_DONE = object()


def pool() -> ThreadPoolExecutor:
    """Shared worker threads for chat pipelines (size: CHAT_THREADS)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            from .config import get_settings
            _POOL = ThreadPoolExecutor(max_workers=max(1, get_settings().chat_threads), thread_name_prefix="chat")
        return _POOL


def _in_own_loop(ctx: contextvars.Context, factory: Callable[[], Awaitable[T]]) -> T:
    async def main() -> T:
        return await factory()
    return ctx.run(asyncio.run, main())


async def run_in_thread(factory: Callable[[], Awaitable[T]]) -> T:
    """Await ``factory()`` on its own event loop in a worker thread, with the caller's context."""
    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(pool(), _in_own_loop, ctx, factory)


async def stream_in_thread(factory: Callable[[], AsyncIterator[Any]], buffer: int = 256) -> AsyncIterator[Any]:
    """Iterate the async generator ``factory()`` on its own event loop in a worker thread and yield its items here.

    Errors of the generator are raised here. When the consumer stops early (client gone), the generator is cancelled."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=buffer)
    stop = threading.Event()
    ctx = contextvars.copy_context()

    def put(item) -> None:
        # blocks the worker when the client reads slowly (back-pressure), gives up once the consumer has stopped
        fut = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
        while not stop.is_set():
            try:
                fut.result(timeout=0.5)
                return
            except TimeoutError:
                continue
        fut.cancel()

    async def pump() -> None:
        gen = factory()
        try:
            async for item in gen:
                if stop.is_set():
                    break
                put(("item", item))
        except BaseException as e:     # noqa: BLE001 – handed to the consumer, which re-raises it
            put(("error", e))
        finally:
            await gen.aclose()
            put(("end", _DONE))

    future = loop.run_in_executor(pool(), lambda: ctx.run(asyncio.run, pump()))
    try:
        while True:
            kind, value = await queue.get()
            if kind == "end":
                break
            if kind == "error":
                raise value
            yield value
    finally:
        stop.set()
        while not queue.empty():       # unblock a worker waiting on a full queue
            queue.get_nowait()
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
        except (TimeoutError, asyncio.TimeoutError):
            pass                       # the worker ends on its own once its current step returns
        except Exception as e:  # noqa: BLE001 – already reported through the queue
            log.debug("chat worker ended with %s", e)
