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


# Teams Bot Framework messaging endpoint (no /api/v1 prefix)
@app.post("/api/messages", include_in_schema=False)
async def teams_messages(request):
    """Teams Bot Framework messaging endpoint.

    Azure Bot Service POSTs Activities here with:
    - Authorization header (bearer token from Azure)
    - JSON body with Activity schema
    """
    from fastapi.responses import JSONResponse
    try:
        from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
        from botbuilder.schema import Activity
        from teams_bot.bot import PromptValidatorTeamsBot
        from teams_bot.config import TeamsBotSettings

        # Initialize on each request (stateless)
        settings = TeamsBotSettings()
        adapter_settings = BotFrameworkAdapterSettings(
            settings.microsoft_app_id,
            settings.microsoft_app_password,
        )
        adapter = BotFrameworkAdapter(adapter_settings)

        async def on_error(context):
            await context.send_activity(f"Bot encountered an error or it has crashed.")

        adapter.on_turn_error = on_error
        bot = PromptValidatorTeamsBot(settings, adapter)

        # Validate content type
        content_type = request.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return JSONResponse({"error": "Content-Type must be application/json"}, status_code=415)

        # Parse activity from request body
        body = await request.json()
        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        # Process the activity through the adapter
        response = await adapter.process_activity(activity, auth_header, bot.on_turn)

        if response:
            return JSONResponse(data=response.body, status_code=response.status)
        return JSONResponse({}, status_code=201)

    except Exception as e:
        _log.error("Teams message processing error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(FRONTEND_DIR / "index.html")
