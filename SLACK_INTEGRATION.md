# Slack Integration — Step-by-Step Setup Guide
## Infovision Prompt Validator · Slack Slash Command (`/validate`)

---

## How It Works

```
User types /validate <prompt>  (in any Slack channel or DM)
        │
        ▼
Slack API  →  POST /api/v1/slack/validate  (URL-encoded form)
        │         ↑ verified via HMAC-SHA256 (SLACK_SIGNING_SECRET)
        │
        ▼
FastAPI returns 200 + ephemeral "⏳ Validating..." ACK  (< 1s)
        │
        ▼  (background task)
run_mcp_validation()  →  Groq / Anthropic LLM scoring
        │
        ▼
Block Kit Card  →  POSTed to Slack response_url
        │
        ▼
Rich card appears in channel with:
  • Score (0–100) + Rating + Persona
  • Dimension breakdown (✅/❌ per criterion)
  • Issues found
  • Suggestions
  • ✨ Improved Prompt
```

---

## Commands

| Command | What it does |
|---|---|
| `/validate <prompt>` | Validate with default persona (All Employees) |
| `/validate persona_1: <prompt>` | Validate as Developer + QA |
| `/validate persona_2: <prompt>` | Validate as Technical PM |
| `/validate persona_3: <prompt>` | Validate as BA & PO |
| `/validate persona_4: <prompt>` | Validate as Support Staff |
| `/validate help` | Show usage guide |

---

## Part 1 — Create the Slack App

### Step 1 — Go to Slack API Dashboard

1. Open https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Fill in:
   - **App Name**: `Prompt Validator`
   - **Pick a workspace**: select your workspace
4. Click **Create App**

### Step 2 — Copy Signing Secret

1. In your app → left panel → **Basic Information**
2. Scroll to **App Credentials**
3. Copy **Signing Secret** (click "Show")
4. Paste into your `.env`:
   ```
   SLACK_SIGNING_SECRET=<paste here>
   ```

---

## Part 2 — Configure the Slash Command

### Step 3 — Create `/validate` Slash Command

1. Left panel → **Slash Commands** → **Create New Command**
2. Fill in:
   - **Command**: `/validate`
   - **Request URL**: `https://margy-nonevolutionary-korey.ngrok-free.dev/api/v1/slack/validate`
     *(replace with your ngrok URL or production URL)*
   - **Short Description**: `Validate and improve your prompt`
   - **Usage Hint**: `[persona_1:] <your prompt>`
   - **Escape channels, users, and links**: ✅ **Check this**
3. Click **Save**

### Step 4 — Install App to Workspace

1. Left panel → **Install App** → **Install to Workspace**
2. Click **Allow**
3. Copy the **Bot User OAuth Token** (`xoxb-...`) into `.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   ```
   *(Optional for slash commands — only needed for proactive bot messages)*

---

## Part 3 — Configure Scopes

### Step 5 — Add Required OAuth Scopes

1. Left panel → **OAuth & Permissions** → **Scopes**
2. Under **Bot Token Scopes**, add:
   - `commands` — receive slash command events
   - `chat:write` — send messages (for future bot features)
   - `users:read.email` — resolve user email to persona *(optional)*
3. Click **Save Changes**
4. **Reinstall the app** if prompted (left panel → Install App)

---

## Part 4 — Local Testing with ngrok

### Step 6 — Ensure Services Are Running

**Terminal 1 — FastAPI (port 8000):**
```bash
cd D:\prompt_validator_complete_repo
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — ngrok (port 8000, NOT 3975 for Slack):**
```bash
C:\ngrok-bin\ngrok.exe http 8000
```
> Note: Slack slash commands hit the **FastAPI** endpoint (port 8000) directly.
> The Teams bot bridge (port 3975) is separate.

### Step 7 — Update Slack Request URL with ngrok

Once ngrok is running, copy the forwarding URL and update your slash command:

1. Go to https://api.slack.com/apps → your app → **Slash Commands**
2. Edit `/validate`
3. Set **Request URL** to:
   ```
   https://<your-ngrok-subdomain>.ngrok-free.app/api/v1/slack/validate
   ```
4. Click **Save**

### Step 8 — Reload .env and Restart FastAPI

```bash
# Stop FastAPI (Ctrl+C), then restart to pick up SLACK_SIGNING_SECRET:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Part 5 — Test in Slack

### Step 9 — Test Commands

Open any Slack channel and try:

```
/validate help
```
→ Should show usage guide (ephemeral, visible only to you)

```
/validate Write some code to validate a prompt.
```
→ Immediate ACK: "⏳ Validating as All Employees..."
→ 3–5 seconds later: full Block Kit card appears in channel

```
/validate persona_1: Using FastAPI and Pydantic v2, add a POST /validate route that accepts JSON with prompt, persona_id. Return 422 on bad input.
```
→ Block Kit card with ~70+ score for Developer + QA persona

---

## Credential Reference

| Variable | Where to find it |
|---|---|
| `SLACK_SIGNING_SECRET` | api.slack.com/apps → Basic Information → App Credentials |
| `SLACK_BOT_TOKEN` | api.slack.com/apps → OAuth & Permissions → Bot User OAuth Token |

---

## Architecture

```
app/integrations/slack/
├── __init__.py           — package marker
├── verification.py       — HMAC-SHA256 signature check (SLACK_SIGNING_SECRET)
└── handler.py            — Block Kit builder + background processor

app/api/routes.py         — POST /api/v1/slack/validate  (no X-API-Key needed)
app/core/settings.py      — SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN
```

---

## Block Kit Card Example

When a user submits a Medium-quality prompt, they see:

```
┌─────────────────────────────────────────────────────┐
│  🔵 Prompt Validator  ·  Score: 68/100              │
├─────────────────────────────────────────────────────┤
│  Rating: 🔵 Good        Persona: Developer & QA     │
├─────────────────────────────────────────────────────┤
│  Your Prompt:                                       │
│  ┌─────────────────────────────────┐               │
│  │ Using FastAPI, add a /validate  │               │
│  │ route. Return 422 on bad input. │               │
│  └─────────────────────────────────┘               │
├─────────────────────────────────────────────────────┤
│  Dimension Breakdown:                               │
│  ✅ Technical Precision  ❌ Edge Cases               │
│  ✅ Testability          ✅ Specificity              │
├─────────────────────────────────────────────────────┤
│  Issues Found:                                      │
│  • No edge cases requested                         │
│  • Missing error scenario coverage                 │
├─────────────────────────────────────────────────────┤
│  Suggestions:                                       │
│  • Add boundary/null/timeout edge cases            │
│  • Declare exact output structure                  │
├─────────────────────────────────────────────────────┤
│  ✨ Improved Prompt:                                │
│  ┌─────────────────────────────────┐               │
│  │ Using FastAPI and Pydantic v2,  │               │
│  │ implement POST /validate...     │               │
│  └─────────────────────────────────┘               │
├─────────────────────────────────────────────────────┤
│  Infovision Prompt Validator via groq  ·  /validate help │
└─────────────────────────────────────────────────────┘
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `401 Invalid Slack signature` | Wrong SLACK_SIGNING_SECRET | Re-copy from Slack app → Basic Information |
| `dispatch_failed` in Slack | Request URL not reachable | Check ngrok is running, URL matches port 8000 |
| ACK received but no card | response_url POST failed | Check FastAPI logs; LLM may have timed out |
| `503` response | Both Anthropic + Groq unavailable | Check API keys; static fallback should still work |
| Slash command not found | App not installed to workspace | Install App → Workspace in Slack app settings |
| Signature error on Vercel | Clock drift > 5 min | Vercel clocks are synced; re-check signing secret |

---

## Production Deployment

When deploying to Vercel (no ngrok needed):

1. Add to Vercel environment variables:
   ```
   SLACK_SIGNING_SECRET=<your secret>
   SLACK_BOT_TOKEN=<your token>     # optional
   ```
2. Update slash command **Request URL** to:
   ```
   https://promptvalidatorcompleterepo.vercel.app/api/v1/slack/validate
   ```

> Note: On Vercel, `BackgroundTasks` run within the serverless function execution window.
> Vercel's default timeout is 10s (hobby) / 60s+ (pro). For slow LLM responses,
> consider upgrading to Pro or using `after()` with Fluid Compute.

---

## Current Status

| Step | Status |
|---|---|
| Code — `/api/v1/slack/validate` route | ✅ Complete |
| Code — Signature verification | ✅ Complete |
| Code — Block Kit card builder | ✅ Complete |
| Code — Background task processor | ✅ Complete |
| `SLACK_SIGNING_SECRET` in `.env` | ⚠️ Paste your value |
| Slack App created | ⚠️ Step 1–2 above |
| `/validate` slash command configured | ⚠️ Step 3 above |
| App installed to workspace | ⚠️ Step 4 above |
| ngrok running on port 8000 | ⚠️ Step 6–7 above |

---

*Last updated: 2026-04-03 | Infovision CoE AI/GenAI Practice*
