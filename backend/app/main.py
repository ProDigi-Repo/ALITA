"""FastAPI application: access middleware, API routers (``app/routes``), reviewer sessions and the static front end."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__, store
from .access import protect_request
from .config import get_settings
from .routes import ROUTERS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup: data folder and Qdrant collections, the job queue (REQ-83: jobs of a previous run are marked interrupted,
    left-over staged uploads removed, more threads for blocking routes), people migration in the background."""
    import shutil

    from anyio import to_thread

    from .jobs import QUEUE, write_lock
    from .project_teams import migrate_people_once
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    store.ensure_collections()
    QUEUE.load()
    shutil.rmtree(s.data_dir / "incoming", ignore_errors=True)   # uploads of jobs that cannot run any more
    to_thread.current_default_thread_limiter().total_tokens = max(40, s.chat_threads * 2)

    def migrate() -> None:
        with write_lock():
            migrate_people_once()
    threading.Thread(target=migrate, daemon=True).start()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app: access middleware, all routers and the static front end at "/"."""
    application = FastAPI(title="ALITA API", version=__version__, lifespan=lifespan)
    application.middleware("http")(protect_request)  # front end and API are same-origin; no permissive CORS
    for router in ROUTERS:
        application.include_router(router)
    front = get_settings().frontend_dir
    if front.is_dir():   # mounted last: "/" must not shadow the API
        application.mount("/", StaticFiles(directory=front, html=True), name="frontend")
    return application


app = create_app()
