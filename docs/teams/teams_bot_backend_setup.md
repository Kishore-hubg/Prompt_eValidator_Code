# Teams Bot Backend Setup

This service receives Microsoft Teams activities via Bot Framework and forwards prompt messages to the Prompt Validator API endpoint:

- `POST /api/v1/teams/message`

## 1) Install dependencies

```bash
pip install -r requirements.txt
```

## 2) Environment variables

Set the bot framework and validator variables:

- `BOT_APP_ID` (Azure Bot App ID)
- `BOT_APP_PASSWORD` (Azure Bot secret)
- `TEAMS_OAUTH_CONNECTION_NAME` (optional; needed for Teams SSO token retrieval)
- `VALIDATOR_API_BASE` (example: `https://your-validator-host`)
- `VALIDATOR_API_KEY` (must match validator backend API key)
- `TEAMS_BOT_HOST` (default `0.0.0.0`)
- `TEAMS_BOT_PORT` (default `3978`)

## 3) Run the bot bridge

```bash
python -m teams_bot.app
```

Bot endpoint:

- `POST /api/messages`

Health endpoint:

- `GET /health`

## 4) Configure Azure Bot and Teams app

1. Create Azure Bot registration.
2. Set messaging endpoint to:
   - `https://<your-bot-host>/api/messages`
3. Create Teams app manifest referencing the same Bot App ID.
4. Install app in Teams and test in personal chat and team channel mention.

## 5) Runtime behavior

The bot:

1. Reads incoming Teams message text.
2. Attempts to obtain user email from activity.
3. Attempts to obtain Teams SSO access token if `TEAMS_OAUTH_CONNECTION_NAME` is configured.
4. Calls validator endpoint with:
   - `user_email` (if available)
   - `access_token` (if available)
   - `email_hint`
   - `message_text`
5. Replies in Teams with score, issues, suggestions, and improved prompt.

## 6) Full go-live prerequisites

See `docs/teams/go_live_checklist.md`.

