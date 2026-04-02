# Infovision Prompt Validator

**Prompt Validator MVP** — FastAPI backend for persona-based prompt scoring, auto-improvement, analytics, and Microsoft Teams integration.

## Overview

An enterprise-grade AI prompt quality validator that evaluates, scores, and rewrites prompts using LLM (Anthropic Claude) against persona-specific guidelines and data governance standards.

## What is Inside

- FastAPI MVP backend and Web UI
- LLM integration (Anthropic `claude-sonnet-4-6`) for evaluation and rewrite
- Persona-aware scoring engine (Developer+QA, Executive, Delivery Manager, Data Analyst, Customer Support)
- Microsoft Teams Bot with Adaptive Cards
- MongoDB Atlas backend
- Source-of-truth JSON files for personas and guidelines
- MCP integration, OAuth, analytics

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env           # fill in credentials
uvicorn app.main:app --reload
```

Web UI: `http://127.0.0.1:8000/`

## Teams Bot

```bash
python teams_bot/app.py        # runs on port 3975
```

## Repo Structure

```
app/
  api/          - FastAPI routes
  services/     - LLM, validation, scoring
  integrations/ - Teams, MCP, OAuth
  data/         - Persona + guideline JSON files
teams_bot/      - Microsoft Teams Bot Framework adapter
frontend/       - Web UI (vanilla JS + HTML)
docs/           - Technical documentation
```

## Environment Variables

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | `anthropic` (default) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` |
| `MONGODB_URI` | MongoDB Atlas connection string |
| `PROMPT_VALIDATOR_API_KEY` | API key for protected routes |
| `BOT_APP_ID` | Azure Bot App ID |
| `BOT_APP_PASSWORD` | Azure Bot App Password |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/validate` | POST | Validate and improve a prompt |
| `/api/v1/personas` | GET | List available personas |
| `/api/v1/teams/message` | POST | Teams bot message handler |
| `/api/v1/health` | GET | Health check |

## Author

**Kishore Bodelu** — Infovision CoE AI/GenAI Practice
