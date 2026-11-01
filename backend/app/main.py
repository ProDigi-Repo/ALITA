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
    from .project_teams import migrate_people_once
    get_settings().data_dir.mkdir(parents=True, exist_ok=True)
    store.ensure_collections()
    threading.Thread(target=migrate_people_once, daemon=True).start()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="ALITA API", version=__version__, lifespan=lifespan)
    application.middleware("http")(protect_request)  # front end and API are same-origin; no permissive CORS
    for router in ROUTERS:
        application.include_router(router)
    front = get_settings().frontend_dir
    if front.is_dir():   # mounted last: "/" must not shadow the API
        application.mount("/", StaticFiles(directory=front, html=True), name="frontend")
    return application


app = create_app()
