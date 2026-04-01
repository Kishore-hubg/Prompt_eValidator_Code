from __future__ import annotations

from aiohttp import web
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

from teams_bot.bot import PromptValidatorTeamsBot
from teams_bot.config import TeamsBotSettings

SETTINGS = TeamsBotSettings()

ADAPTER_SETTINGS = BotFrameworkAdapterSettings(
    SETTINGS.microsoft_app_id,
    SETTINGS.microsoft_app_password,
)
ADAPTER = BotFrameworkAdapter(ADAPTER_SETTINGS)
BOT = PromptValidatorTeamsBot(SETTINGS, ADAPTER)


async def on_error(context: TurnContext, error: Exception):
    await context.send_activity(f"Bot encountered an error: {error}")


ADAPTER.on_turn_error = on_error


async def messages(request: web.Request) -> web.Response:
    if "application/json" not in (request.headers.get("Content-Type", "") or ""):
        return web.Response(status=415)

    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    if response:
        return web.json_response(data=response.body, status=response.status)
    return web.Response(status=201)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", lambda _: web.json_response({"status": "ok"}))
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=SETTINGS.host, port=SETTINGS.port)

