# Teams Bot Rollout — Day 5 Deliverable
## Infovision Prompt Validator · Microsoft Teams Integration

> **Goal:** Enable organisation-wide prompt validation via a Teams Bot so that
> any employee can type or paste a prompt directly in Teams and receive an
> Adaptive Card with a score, dimension breakdown, issues, suggestions, and an
> auto-improved prompt — all without leaving Teams.

---

## Architecture Overview

```
Microsoft Teams
      │  user sends message / command
      ▼
Azure Bot Service  (Bot App ID: 89f80bcf-…)
      │  POST /api/messages  (JWT-signed)
      ▼
Teams Bot  [port 3975]              ← teams_bot/app.py (aiohttp)
  PromptValidatorTeamsBot           ← teams_bot/bot.py (BotFrameworkAdapter)
      │  POST /api/v1/teams/message  (x-api-key)
      ▼
Prompt Validator API  [port 8000]   ← app/main.py (FastAPI / Uvicorn)
  handle_teams_message()            ← app/integrations/teams/bot.py
      │
      ├── resolve_persona_for_user() ← AAD email → persona lookup
      └── run_mcp_validation()       ← LLM scoring + autofix
```

**Two processes, one `.env`:**

| Service | Port | Entry point |
|---|---|---|
| Prompt Validator API | 8000 | `uvicorn app.main:app` |
| Teams Bot Bridge | 3975 | `python -m teams_bot.app` |

---

## Pre-requisites

| Item | Value (from `.env`) |
|---|---|
| Azure Bot App ID | `89f80bcf-efa3-4a07-a4a4-e766f3557e98` |
| Azure Bot App Password | `BOT_APP_PASSWORD` (in `.env`) |
| Microsoft Tenant ID | `ba5028ea-2f88-4298-bba5-cecf95342a75` |
| OAuth Connection Name | `TeamsSSO` |
| Validator API Key | `8f4f7f0c9f4f4b8b9f0f2f8f2d6a3b1c` |

---

## Step 1 — Azure Bot Registration (one-time setup)

1. Go to **Azure Portal → Azure Bot** (or Bot Channels Registration).
2. Set **Messaging endpoint** to your public URL:
   - Local dev (ngrok): `https://<ngrok-id>.ngrok.io/api/messages`
   - Production: `https://teams-bot.infovision.internal/api/messages`
3. Under **Configuration → Microsoft App ID**, confirm `89f80bcf-efa3-4a07-a4a4-e766f3557e98`.
4. Under **Channels**, enable **Microsoft Teams**.
5. Under **Configuration → OAuth Connection Settings**, verify the `TeamsSSO` connection:
   - Service Provider: **Azure Active Directory v2**
   - Client ID: `7b6ec3f4-3759-48d6-a558-6a1bcd1824c6`
   - Tenant ID: `ba5028ea-2f88-4298-bba5-cecf95342a75`
   - Scopes: `openid profile email User.Read`

---

## Step 2 — Local Development

### 2a. Start the Validator API

```bash
source .venv/bin/activate       # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Confirm: `curl http://localhost:8000/api/v1/health`

### 2b. Start the Teams Bot

```bash
./scripts/start_teams_bot.sh
# Or manually:
python -m teams_bot.app
```

The bot starts on `0.0.0.0:3975`.

### 2c. Expose the Bot with ngrok

```bash
ngrok http 3975
# Copy the HTTPS URL, e.g. https://abc123.ngrok.io
```

Update the Azure Bot **Messaging endpoint** to `https://abc123.ngrok.io/api/messages`.

### 2d. Test in Teams

Install the bot in Teams (App Studio or direct upload). Send any message to the
bot — you should receive an Adaptive Card response.

---

## Step 3 — Docker Compose (Staging / Production)

```bash
cd deploy
docker compose up --build -d
```

Both services start automatically. The Teams Bot waits for the API health check
before starting (`depends_on: condition: service_healthy`).

**Environment variables** are read from `../.env`. No secrets are baked into
images.

```bash
# Check logs
docker compose logs -f teams_bot
docker compose logs -f validator_api

# Health checks
curl http://localhost:8000/api/v1/health
curl http://localhost:3975/health
```

---

## Bot Commands Reference

| Command | Description |
|---|---|
| `/help` | Show all commands and persona list |
| `/persona` | Show persona selection Adaptive Card |
| `/set-persona <id>` | e.g. `/set-persona persona_1` |
| `/my-persona` | Show your active persona |
| `/last-score` | Replay your last validation result |
| *(any other text)* | Validate the text as a prompt |

### Persona IDs

| ID | Persona | Emoji |
|---|---|---|
| `persona_0` | All Employees | 🏢 |
| `persona_1` | Developer & QA | 💻 |
| `persona_2` | Technical PM | 📋 |
| `persona_3` | BA & PO | 📊 |
| `persona_4` | Support Staff | 🎧 |

---

## Adaptive Card Response

Every validation reply contains:

```
┌─────────────────────────────────────────┐
│  Prompt Validator          Score: 74    │
│  Persona: Developer & QA   Rating: Good │
├─────────────────────────────────────────┤
│  DIMENSIONS                             │
│  ✅ Clarity  ✅ Context  ❌ Output Fmt  │
│  ✅ Specificity  ✅ Task  ❌ Constraints│
├─────────────────────────────────────────┤
│  ISSUES TO FIX                          │
│  • No output format specified           │
│  • Missing technology constraints       │
├─────────────────────────────────────────┤
│  SUGGESTIONS                            │
│  → Add "Respond in JSON with keys…"     │
│  → Specify language version             │
├─────────────────────────────────────────┤
│  ✨ IMPROVED PROMPT                     │
│  You are a senior Python 3.11…          │
├─────────────────────────────────────────┤
│  [📋 Copy Improved Prompt] [🔄 Persona] │
└─────────────────────────────────────────┘
```

Score colours:
- ≥85 → Green (Excellent)
- ≥70 → Blue (Good)
- ≥50 → Amber (Needs Improvement)
- <50 → Red (Poor)

---

## Identity & Persona Resolution

The bot resolves identity in this order:

1. **`from_property.email`** — Teams sets this for most tenants
2. **`from_property.user_principal_name`** — UPN fallback (same as AAD login)
3. **OAuth token** (`TeamsSSO` connection) → `resolve_user_from_token()`
4. **AAD Object ID** → synthetic `<aad_id>@teams.local` (POC/dev fallback)
5. **`teams-anonymous@teams.local`** — last resort

Once email is resolved, `resolve_persona_for_user()` maps the email to the
employee's registered persona. Users can override with `/set-persona` for the
duration of their conversation.

---

## API Contract — Teams Endpoint

```
POST /api/v1/teams/message
x-api-key: <PROMPT_VALIDATOR_API_KEY>
Content-Type: application/json

{
  "user_email":   "jane.doe@infovision.com",   // optional
  "message_text": "Write me a Python function…",
  "persona_id":   "persona_1",                 // optional; auto-resolved if omitted
  "access_token": "eyJ...",                    // optional; Teams OAuth token
  "email_hint":   "jane.doe@infovision.com",   // optional
  "teams_user_id": "29:1abc..."                // optional; AAD object ID
}
```

Response:

```json
{
  "channel": "teams",
  "user_email": "jane.doe@infovision.com",
  "persona_id": "persona_1",
  "score": 74,
  "rating": "Good",
  "issues": ["No output format specified"],
  "suggestions": ["Add response format directive"],
  "improved_prompt": "You are a senior Python 3.11 developer…",
  "message": "[Teams Bot] Score 74 (Good) for Developer & QA. Use improved_prompt for best output."
}
```

---

## Security Checklist

- [x] All requests from the bot to the API use `x-api-key` header
- [x] Azure Bot Service signs all incoming activities with a JWT — `BotFrameworkAdapter` validates this automatically
- [x] `BOT_APP_PASSWORD` never logged or returned to clients
- [x] PII (email, prompt text) classified as `pii_high` per Data Strategy — stored with 24-month retention
- [x] Teams OAuth connection (`TeamsSSO`) scoped to `openid profile email User.Read` only
- [x] `PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=false` in production

---

## Rollout Checklist

- [ ] Azure Bot Registration messaging endpoint updated to production URL
- [ ] `BOT_APP_ID` and `BOT_APP_PASSWORD` confirmed in production secret store
- [ ] Docker Compose deployed: `docker compose up -d`
- [ ] Both health checks passing (API + Teams Bot)
- [ ] Bot published in Teams Admin Center (`Manage apps → Upload`)
- [ ] `TeamsSSO` OAuth connection tested end-to-end (user token resolved)
- [ ] Test message sent from at least one employee account
- [ ] `/set-persona persona_1` tested, score card rendered correctly
- [ ] Adaptive Card visible on Teams Desktop, Web, and Mobile
- [ ] Monitoring alerts configured for `SCORE_OUT_OF_RANGE` and `INGESTION_DEAD_LETTER_HIGH`

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bot responds "Unable to reach the validator service" | FastAPI not running or wrong `VALIDATOR_API_BASE` | Confirm API health: `curl http://localhost:8000/api/v1/health` |
| 401 from API | Wrong `VALIDATOR_API_KEY` | Match `VALIDATOR_API_KEY` in bot env to `PROMPT_VALIDATOR_API_KEY` in API env |
| Bot silent in Teams | Messaging endpoint wrong or ngrok expired | Update endpoint in Azure Portal; restart ngrok |
| Adaptive Card not rendering | Schema version mismatch | Card uses v1.4 — requires Teams Desktop/Web ≥ May 2022 |
| Persona auto-resolution fails | Email not in persona registry | Use `/set-persona` to manually choose; check `persona_criteria_source_truth.json` |
| `401 Unauthorized` from Bot Framework | `BOT_APP_PASSWORD` wrong | Rotate password in Azure Portal and update `.env` |

---

*Day 5 | Infovision CoE AI/GenAI Practice | Kishore Bodelu*
