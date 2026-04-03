# Teams Integration — Step-by-Step Setup Guide
## Infovision Prompt Validator · Microsoft Teams Bot

---

## Architecture

```
Microsoft Teams (user types prompt)
        │
        ▼
Azure Bot Service  ──► POST /api/messages  (JWT-signed)
        │
        ▼
Teams Bot Bridge  [port 3975]          ← teams_bot/app.py  (aiohttp)
  PromptValidatorTeamsBot              ← teams_bot/bot.py   (BotFrameworkAdapter)
        │
        ▼  POST /api/v1/teams/message  (X-API-Key)
        │
        ▼
Prompt Validator API  [port 8000]      ← app/main.py  (FastAPI)
  handle_teams_message()               ← app/integrations/teams/bot.py
        │
        ├── resolve_persona_for_user() → AAD email → persona lookup
        └── run_llm_validation()       → Groq/Anthropic LLM scoring + rewrite
```

---

## Credentials Reference

| Variable | Value |
|---|---|
| `BOT_APP_ID` | `89f80bcf-efa3-4a07-a4a4-e766f3557e98` |
| `MICROSOFT_TENANT_ID` | `ba5028ea-2f88-4298-bba5-cecf95342a75` |
| `MICROSOFT_CLIENT_ID` | `7b6ec3f4-3759-48d6-a558-6a1bcd1824c6` |
| `TEAMS_OAUTH_CONNECTION_NAME` | `TeamsSSO` |
| `VALIDATOR_API_KEY` | `8f4f7f0c9f4f4b8b9f0f2f8f2d6a3b1c` |
| Teams App GUID | `30a56efa-d58c-4e4b-a52d-f34018e4d8b9` |
| Vercel URL | `https://promptvalidatorcompleterepo.vercel.app` |

---

## Part 1 — Local Development Setup

### Step 1 — Install dependencies

```bash
pip install botbuilder-core botbuilder-integration-aiohttp aiohttp httpx python-dotenv
```

### Step 2 — Start the Prompt Validator API (Terminal 1)

```bash
cd D:\prompt_validator_complete_repo
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:
```bash
curl http://127.0.0.1:8000/api/v1/health
# Expected: {"status":"ok"}
```

### Step 3 — Start the Teams Bot Bridge (Terminal 2)

```bash
cd D:\prompt_validator_complete_repo
python -m teams_bot.app
```

Verify:
```bash
curl http://127.0.0.1:3975/health
# Expected: {"status":"ok"}
```

### Step 4 — Start ngrok to expose port 3975 (Terminal 3)

```bash
ngrok http 3975
```

Note the **Forwarding** URL, e.g.:
```
https://a1b2-203-0-113-1.ngrok-free.app  →  http://localhost:3975
```

Your **messaging endpoint** will be:
```
https://margy-nonevolutionary-korey.ngrok-free.dev/api/messages
```

> Keep this terminal open — ngrok must stay running during testing.
> **Current live tunnel:** https://margy-nonevolutionary-korey.ngrok-free.dev → http://localhost:3975

---

## Part 2 — Azure Bot Configuration

### Step 5 — Set Messaging Endpoint in Azure Portal

1. Go to [https://portal.azure.com](https://portal.azure.com)
2. Search for **Bot Services** → open your bot (`BOT_APP_ID: 89f80bcf-...`)
3. Left panel → **Configuration**
4. Set **Messaging endpoint** to:
   ```
   https://margy-nonevolutionary-korey.ngrok-free.dev/api/messages
   ```
5. Click **Apply**

### Step 6 — Enable Microsoft Teams Channel

1. In your Azure Bot → left panel → **Channels**
2. Click **Microsoft Teams** → **Save**
3. Status should show **Running**

### Step 7 — Configure OAuth Connection (TeamsSSO)

1. In your Azure Bot → left panel → **Configuration** → **Add OAuth Connection Settings**
2. Fill in:
   - **Name**: `TeamsSSO`
   - **Service Provider**: `Azure Active Directory v2`
   - **Client ID**: `7b6ec3f4-3759-48d6-a558-6a1bcd1824c6`
   - **Client Secret**: *(your Azure AD app secret)*
   - **Tenant ID**: `ba5028ea-2f88-4298-bba5-cecf95342a75`
   - **Scopes**: `openid profile email User.Read`
3. Click **Save** → **Test Connection** (should return a token)

---

## Part 3 — Teams App Installation

### Step 8 — Upload the Teams App Manifest

The ZIP file is at:
```
D:\prompt_validator_complete_repo\prompt-validator-teams-app.zip
```

It contains:
- `manifest.json` — App definition (schema v1.17)
- `color.png` — 192×192 app icon
- `outline.png` — 32×32 outline icon

**Upload method (Developer/Sideload):**
1. Open Microsoft Teams
2. Click **Apps** (bottom-left)
3. Click **Manage your apps** → **Upload an app**
4. Select **Upload a custom app**
5. Browse to `prompt-validator-teams-app.zip` → **Open**
6. Click **Add** → **Add to a team** (or **Add** for personal use)

**Upload method (Teams Admin Center — org-wide):**
1. Go to [https://admin.teams.microsoft.com](https://admin.teams.microsoft.com)
2. **Teams apps** → **Manage apps** → **Upload**
3. Upload `prompt-validator-teams-app.zip`
4. Approve and publish to org

### Step 9 — Test the Bot in Teams

Once installed, open a chat with the bot and try:

| Command | Expected Response |
|---|---|
| `/help` | Lists all commands with descriptions |
| `/persona` | Shows all 5 personas as Adaptive Card |
| `/set-persona persona_1` | Confirms persona set to Developer + QA |
| `/my-persona` | Shows active persona |
| `Write some code to validate a prompt.` | Returns Adaptive Card with score ~0, Poor rating |

---

## Part 4 — Production Deployment

### Step 10 — Update .env for Production

When deploying the bot bridge to a cloud host (e.g., Azure Container App, Railway, Render):

```env
VALIDATOR_API_BASE=https://promptvalidatorcompleterepo.vercel.app
VALIDATOR_API_KEY=8f4f7f0c9f4f4b8b9f0f2f8f2d6a3b1c
TEAMS_BOT_HOST=0.0.0.0
TEAMS_BOT_PORT=3975
```

### Step 11 — Update Azure Bot Messaging Endpoint (Production)

Replace the ngrok URL with your cloud host URL:
```
https://<your-cloud-host>/api/messages
```

### Step 12 — Update manifest validDomains (Production)

Edit `teams_app_manifest/manifest.json` → `validDomains`:
```json
"validDomains": [
  "promptvalidatorcompleterepo.vercel.app",
  "<your-cloud-host-domain>"
]
```

Re-zip and re-upload the manifest.

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Bot bridge not starting | `botbuilder-core` not installed | `pip install botbuilder-core botbuilder-integration-aiohttp aiohttp` |
| `401 Unauthorized` from Azure | Wrong BOT_APP_ID or PASSWORD | Check `.env` BOT_APP_ID matches Azure Bot registration |
| Bot responds in Teams but no score | FastAPI not running | Start `uvicorn app.main:app --port 8000` |
| `503` from validate API | GROQ rate limit or Anthropic billing | Wait 60s, LLM_FALLBACK handles it automatically |
| ngrok expired URL | ngrok free tier rotates URLs | Restart ngrok, update Azure Bot messaging endpoint |
| Teams shows "Bot is not available" | Messaging endpoint wrong | Check ngrok is running, endpoint URL is correct |
| OAuth test fails | TeamsSSO not configured | Complete Step 7 in Azure Bot settings |

---

## File Reference

| File | Purpose |
|---|---|
| `teams_bot/app.py` | aiohttp server — receives Teams messages on port 3975 |
| `teams_bot/bot.py` | Bot logic — commands, Adaptive Cards, API calls |
| `teams_bot/config.py` | Loads env vars for bot |
| `app/integrations/teams/bot.py` | FastAPI handler — persona resolution + validation |
| `app/api/routes.py` | `POST /api/v1/teams/message` endpoint |
| `teams_app_manifest/manifest.json` | Teams app definition |
| `teams_app_manifest/color.png` | 192×192 app icon |
| `teams_app_manifest/outline.png` | 32×32 outline icon |
| `prompt-validator-teams-app.zip` | Ready-to-upload Teams app package |

---

## Current Status

| Step | Status |
|---|---|
| Code — Bot Bridge | ✅ Complete |
| Code — API endpoint | ✅ Complete |
| Code — Adaptive Cards | ✅ Complete |
| Credentials in .env | ✅ Complete |
| Bot dependencies installed | ✅ Complete |
| Teams App Manifest + ZIP | ✅ Complete |
| Bot bridge running locally (port 3975) | ✅ Running |
| ngrok installed and running | ✅ Running (see terminal) |
| Azure Bot — Messaging Endpoint | ⚠️ Set to ngrok URL (Step 5) |
| Azure Bot — Teams Channel enabled | ⚠️ Enable in Azure Portal (Step 6) |
| OAuth Connection (TeamsSSO) | ⚠️ Configure in Azure Bot (Step 7) |
| Teams App uploaded | ⚠️ Upload ZIP (Step 8) |

---

*Last updated: 2026-04-03 | Infovision CoE AI/GenAI Practice*
