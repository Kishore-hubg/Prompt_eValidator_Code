import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.settings import DATABASE_BACKEND, FRONTEND_DIR
from app.db.database import initialize_schema
from app.middleware.request_logging import RequestLoggingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

_log = logging.getLogger("prompt_validator.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB connections on first request — NOT at import time.
    This prevents Vercel build failures caused by MongoDB connection attempts
    during the serverless cold-start import phase."""
    try:
        if DATABASE_BACKEND == "mongodb":
            from app.db.mongo_db import init_mongo_indexes
            init_mongo_indexes()
            _log.info("MongoDB indexes initialised.")
        else:
            initialize_schema()
            _log.info("SQLite schema initialised.")
    except Exception as exc:
        _log.warning("DB init skipped (non-fatal at startup): %s", exc)
    yield


app = FastAPI(
    title="Prompt Validator MVP",
    version="1.0.0",
    description="Persona-aware prompt validation engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(router)

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(FRONTEND_DIR / "index.html")
