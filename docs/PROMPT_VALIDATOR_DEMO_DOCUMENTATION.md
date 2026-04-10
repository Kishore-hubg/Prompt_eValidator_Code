# Prompt Validator MVP — Demo Documentation
**Infovision Center of Excellence | AI/GenAI Practice**
**Prepared by:** Kishore, GenAI Practitioner
**Date:** April 2026 | **Version:** 1.0 | **Status:** Demo-Ready

---

## Table of Contents

1. [Executive Summary — Approaches Done vs Pending](#1-executive-summary)
2. [One-Pager: Each Approach](#2-one-pagers)
3. [Technical Stack by Approach](#3-technical-stack)
4. [Cost & Usability Comparison](#4-cost--usability-matrix)
5. [Blockers](#5-blockers)
6. [Pending Items in Current Implementation](#6-pending-items)

---

## 1. Executive Summary

### What Is Prompt Validator?

Prompt Validator is an enterprise-grade AI tool that evaluates the quality of prompts written by employees before they are submitted to any AI system. It scores prompts on a 0–100 scale against role-specific criteria (personas), flags issues, and auto-generates improved versions — reducing hallucination risk, improving output quality, and building organizational AI literacy.

---

### Approaches Implemented ✅

| # | Approach | Channel | Status |
|---|---|---|---|
| 1 | **Web UI** | Browser | ✅ Live on Vercel |
| 2 | **Slack Integration** | Slack `/validate` | ✅ Live |
| 3 | **Microsoft Teams Bot** | Teams chat | ✅ Live |
| 4 | **MCP — Claude Desktop** | AI assistant | ✅ Live |
| 5 | **MCP — Claude Code CLI** | Developer terminal | ✅ Live |
| 6 | **REST API** | Any system | ✅ Live |
| 7 | **Native Claude Skills** | Claude Code/Desktop | ✅ Live (NEW) |

### Approaches Pending ⏳

| # | Approach | Priority | Effort |
|---|---|---|---|
| 8 | **VS Code Extension** | High | Medium |
| 9 | **GitHub Copilot Plugin** | High | Medium |
| 10 | **Outlook / Email Add-in** | Medium | Medium |
| 11 | **Azure OpenAI Integration** | High | Low |
| 12 | **Power Automate Flow** | Medium | Low |
| 13 | **Browser Extension (Chrome/Edge)** | Low | High |
| 14 | **Mobile App (Teams mobile)** | Low | High |
| 15 | **Jira / Confluence Plugin** | Medium | Medium |
| 16 | **Multi-language Support** | Low | Medium |

---

## 2. One-Pagers

---

### Approach 1: Web UI

**What it is:** A browser-based single-page application deployed on Vercel. Any employee can open the URL, paste a prompt, select their role persona, and get an instant validation report with scoring, issues, and an AI-improved version.

**How it works:**
1. Employee opens `https://promptvalidatorcompleterepo.vercel.app`
2. Selects their persona (Developer, PM, BA, Support, or All Employees)
3. Types or pastes their prompt
4. Clicks Validate — receives score (0–100), rating (Excellent/Good/Needs Improvement/Poor), dimension breakdown, issues list, and improved prompt
5. Toggle "Auto Improve: ON/OFF" controls whether improved version is returned

**Key Features:**
- 5 persona profiles with role-specific weighted scoring
- Side-by-side diff view: original vs improved prompt
- Demo sample loader (Poor / Medium / Excellent quality examples per persona)
- Auto-improve toggle
- Mobile-responsive layout

**Who uses it:** All employees, L&D teams, managers running demos, onboarding trainers

**Deployment:** Vercel (Hobby plan, serverless Python FastAPI)

---

### Approach 2: Slack Integration

**What it is:** A Slack slash command `/validate` that employees can use directly inside any Slack channel or DM without leaving their workflow.

**How it works:**
1. Employee types `/validate [persona] Your prompt text here` in any Slack channel
2. Slack sends the request to the Vercel endpoint within 3 seconds
3. A rich Block Kit card is returned privately to the user with: score badge, rating, top 3 issues, suggestions, and improved prompt
4. Persona auto-detected from user email if not specified

**Key Features:**
- Background processing (ACKs Slack within 3s, posts result asynchronously)
- Rich Block Kit card with colour-coded score badge
- HMAC-SHA256 request signature verification (security)
- Persona auto-detection via email → persona mapping
- Improved prompt displayed (up to 2,800 characters in card)

**Who uses it:** All employees — especially developers and analysts who live in Slack

**Deployment:** Vercel serverless endpoint (`/api/v1/slack/validate`)

---

### Approach 3: Microsoft Teams Bot

**What it is:** A conversational bot deployed inside Microsoft Teams that responds to natural language validation requests in chat.

**How it works:**
1. Employee sends a message to the Prompt Validator bot in Teams: `@PromptValidator validate this for a PM: Generate a sprint status report`
2. Bot parses the request, resolves the user's email via Microsoft Entra ID (SSO)
3. Returns an Adaptive Card with score, rating, issues, improved prompt
4. Bot also supports: `list personas`, `help`, `improve [prompt]`

**Key Features:**
- Microsoft Bot Framework SDK integration
- Microsoft Entra ID SSO — user persona auto-resolved from Azure AD group membership
- Adaptive Cards for rich formatted responses
- Persistent conversation context within a session
- API-key protected endpoint

**Who uses it:** Corporate employees on Microsoft 365 ecosystem (especially non-developers)

**Deployment:** Bot Framework requires a persistent server (not serverless); currently deployed alongside Vercel using a separate process; production requires Azure App Service or Azure Container Apps

---

### Approach 4: MCP — Claude Desktop

**What it is:** A Model Context Protocol (MCP) server that exposes Prompt Validator as 7 native tools inside Claude Desktop. Users can ask Claude to validate prompts conversationally.

**How it works:**
1. Claude Desktop loads the MCP server via a custom Node.js proxy (`mcp-proxy.js`)
2. When the user asks: *"Validate this prompt for a developer persona: Write a Python function..."* — Claude automatically calls the `validate_prompt` tool
3. The tool calls the Vercel MCP endpoint and returns structured results
4. Claude presents the validation report in conversational format

**7 MCP Tools Available:**
| Tool | Description |
|---|---|
| `validate_prompt` | Score + rate + improve in one call |
| `improve_prompt` | AI rewrite with 4 strategies |
| `list_personas` | Show all 5 personas |
| `get_persona_details` | Detailed criteria for a persona |
| `query_history` | Search past validations |
| `get_analytics` | Usage trends and statistics |
| `save_validation` | Persist result to audit trail |

**Who uses it:** Power users, AI practitioners, prompt engineers using Claude Desktop

**Deployment:** Custom `mcp-proxy.js` (zero npm dependencies) bridges Claude Desktop stdio → Vercel HTTPS

---

### Approach 5: MCP — Claude Code CLI

**What it is:** Same MCP server as Claude Desktop but registered with the Claude Code command-line tool. Developers get Prompt Validator as native tools in their terminal AI assistant.

**How it works:**
1. Registered via: `claude mcp add --transport http prompt-validator https://promptvalidatorcompleterepo.vercel.app/mcp`
2. Developer types: `Use prompt-validator to validate this prompt for a BA persona: Extract requirements from the BRD`
3. Claude Code calls `validate_prompt` tool, returns validation report inline in terminal

**Who uses it:** Developers using Claude Code CLI in their day-to-day development workflow

**Deployment:** HTTP transport — points directly to Vercel MCP endpoint. No proxy needed for Claude Code.

---

### Approach 6: REST API

**What it is:** A fully documented REST API that any internal system, automation pipeline, or CI/CD workflow can call programmatically to validate prompts.

**How it works:**
```
POST /api/v1/validate
Authorization: Bearer infovision-dev-key
{
  "prompt_text": "Write a Python function",
  "persona_id": "persona_1",
  "auto_improve": true,
  "channel": "api"
}
```
Returns: score, rating, dimension breakdown, issues, suggestions, improved prompt, LLM provider used, guideline evaluation.

**Key Endpoints:**
| Endpoint | Purpose |
|---|---|
| `POST /api/v1/validate` | Core validation + improvement |
| `POST /api/v1/improve` | Standalone prompt improvement |
| `GET /api/v1/personas` | List all personas |
| `GET /api/v1/history` | Validation history |
| `GET /api/v1/analytics/summary` | Usage analytics |
| `GET /api/v1/leaderboard/weekly` | Weekly team leaderboard |
| `GET /api/v1/admin/records` | Admin: all records with filters |

**Who uses it:** Integration teams, automation scripts, CI/CD pipelines, internal developer tools

**Deployment:** Vercel serverless Python FastAPI

---

### Approach 7: Native Claude Skills (NEW)

**What it is:** Five Markdown skill files stored locally that turn Claude itself into the validator — with zero external API calls, zero cost, and instant response.

**How it works:**
1. Skill files stored at `~/.claude/skills/validate-*/SKILL.md`
2. Each skill contains the full persona rubric, weights, scoring formula, and output template
3. When invoked (`/validate-dev Write a Python function...`), Claude reads the rubric and evaluates the prompt using its own reasoning
4. Returns structured report: score, rating, dimension table, issues, improved prompt

**5 Skills Available:**
| Command | Persona |
|---|---|
| `/validate-prompt` | All Employees (baseline) |
| `/validate-dev` | Developer + QA |
| `/validate-pm` | Technical PM |
| `/validate-ba` | Business Analyst + PO |
| `/validate-support` | Support Staff |

**Who uses it:** Any Claude Code or Claude Desktop user who wants instant, free validation without network dependency

**Deployment:** Local files only — share as a zip. No infrastructure required.

---

## 3. Technical Stack

### By Approach

| Approach | Language | Framework | LLM | Database | Auth | Hosting |
|---|---|---|---|---|---|---|
| Web UI | HTML/CSS/JS | Vanilla JS | Groq llama-3.3-70b / Claude Sonnet | MongoDB Atlas | API Key | Vercel (Serverless) |
| Slack | Python 3.12 | FastAPI + BackgroundTasks | Groq / Claude | MongoDB Atlas | HMAC-SHA256 | Vercel (Serverless) |
| Teams | Python 3.12 | FastAPI + Bot Framework SDK | Groq / Claude | MongoDB Atlas | Microsoft Entra ID / JWT | Persistent Server |
| MCP Claude Desktop | Node.js (proxy) + Python | JSON-RPC 2.0 + FastAPI | Groq / Claude | MongoDB Atlas | None (local) | Vercel + Local proxy |
| MCP Claude Code | Python | JSON-RPC 2.0 + FastAPI | Groq / Claude | MongoDB Atlas | HTTP transport | Vercel |
| REST API | Python 3.12 | FastAPI | Groq / Claude | MongoDB Atlas / SQLite | Bearer Token | Vercel (Serverless) |
| Native Skills | Markdown | Claude reasoning | Claude (built-in) | None | None | Local files |

### Core Backend Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | FastAPI 0.115+ | REST endpoints, async request handling |
| **LLM Primary** | Anthropic claude-sonnet-4-6 | Prompt evaluation + improvement |
| **LLM Fallback 1** | Groq llama-3.3-70b-versatile | Free-tier fallback (currently active) |
| **LLM Fallback 2** | Static Rules Engine | Keyword + weight-based scoring (always available) |
| **Database (Prod)** | MongoDB Atlas | Validation records, analytics, audit trail |
| **Database (Dev)** | SQLite | Local development, zero-config |
| **Validation ORM** | SQLAlchemy 2.0 | Schema management, migrations |
| **Data Validation** | Pydantic v2 | Request/response schemas |
| **Deployment** | Vercel Serverless (Python) | Auto-scale, zero-ops |
| **MCP Protocol** | JSON-RPC 2.0 | Standard AI tool protocol |
| **Slack SDK** | HMAC + Block Kit | Slash command + rich card responses |
| **Teams SDK** | Bot Framework SDK (Python) | Adaptive Card bot |
| **Caching** | In-memory (SHA-256 keyed) | 10-min TTL, reduces LLM calls ~35% |
| **CI/CD** | GitHub → Vercel auto-deploy | Push to main = auto deploy |

---

## 4. Cost & Usability Matrix

### Cost Comparison

| Approach | Setup Cost | Per-Validation Cost | Monthly (50 users, 15/day) | Infrastructure Cost |
|---|---|---|---|---|
| Web UI | $0 | $0.003–$0.012* | $50–$200* | $0 (Vercel free) |
| Slack | $0 | $0.003–$0.012* | $50–$200* | $0 (Vercel free) |
| Teams | $0 | $0.003–$0.012* | $50–$200* | $10–$50/mo (persistent server) |
| MCP Claude Desktop | $0 | $0.003–$0.012* | $50–$200* | $0 (Vercel free) |
| MCP Claude Code | $0 | $0.003–$0.012* | $50–$200* | $0 (Vercel free) |
| REST API | $0 | $0.003–$0.012* | $50–$200* | $0 (Vercel free) |
| **Native Skills** | **$0** | **$0 (zero)** | **$0** | **$0** |

*Range: Haiku ($0.003) → Sonnet ($0.012). Currently $0 — Groq free tier active.

### Usability Comparison

| Aspect | Web UI | Slack | Teams | MCP Desktop | MCP CLI | REST API | Skills |
|---|---|---|---|---|---|---|---|
| **Ease of use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Works on laptop (offline)** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Works without internet** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Tracks user input** | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ❌ None |
| **Org-level governance** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Usage per engineer** | ✅ Dashboard | ✅ Dashboard | ✅ Dashboard | ✅ Dashboard | ✅ Dashboard | ✅ Dashboard | ❌ |
| **Persona adoption tracking** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Team evolution metrics** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Zero API cost** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **No infrastructure needed** | ❌ | ❌ | ❌ Proxy needed | ✅ | ✅ | ❌ | ✅ |
| **Shareable (teammate)** | ✅ URL | ✅ Slack config | ✅ Bot invite | ⚠️ JSON file | ✅ 1 command | ✅ API key | ✅ zip file |
| **Client system compatible** | ✅ | Depends on client Slack | ✅ M365 orgs | ✅ | ✅ Dev only | ✅ | ✅ |
| **Audit trail** | ✅ MongoDB | ✅ MongoDB | ✅ MongoDB | ✅ MongoDB | ✅ MongoDB | ✅ MongoDB | ❌ |
| **Admin dashboard** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

### Governance & Analytics Capabilities (Connected Channels Only)

| Governance Feature | Available? | Detail |
|---|---|---|
| **Track what users are prompting** | ✅ | Every prompt stored with user email, persona, channel, timestamp |
| **Per-engineer usage count** | ✅ | Weekly leaderboard + user summary API |
| **Persona needs-training analysis** | ✅ | Analytics by persona — average score, low-scoring dimensions |
| **Team evolution over time** | ✅ | Week-over-week score trends, org dashboard |
| **Score distribution** | ✅ | Poor/Needs Improvement/Good/Excellent breakdown per team |
| **Channel adoption** | ✅ | Slack vs Teams vs Web vs MCP usage split |
| **PII masking** | ✅ | Data governance rules applied before storage |
| **Admin search & filter** | ✅ | Search by user, date, persona, channel, rating |

---

## 5. Blockers

### Current Blockers

| # | Blocker | Impact | Status | Resolution |
|---|---|---|---|---|
| 1 | **Anthropic API Credits = $0** | Primary LLM unavailable | 🔴 Active | Falling back to Groq (transparent to user). Top up credits or set `LLM_PROVIDER=groq` explicitly. |
| 2 | **Teams bot requires persistent server** | Cannot run on Vercel serverless | 🟡 Partial | Teams endpoint exists on Vercel. For full production, needs Azure App Service or Container Apps. Demo works. |
| 3 | **GitHub Actions warmup workflow** | Cold starts possible if UptimeRobot fails | 🟡 Low risk | Requires GitHub PAT with `workflow` scope to push `.github/workflows/warmup.yml`. UptimeRobot currently mitigating. |
| 4 | **Claude Desktop MCP — mcp-remote incompatible with Node v24** | MCP tools fail in Claude Desktop | 🟢 Resolved | Replaced with custom `mcp-proxy.js` (zero dependencies). Working. |
| 5 | **Vercel cold start (8–10s)** | First request after inactivity is slow | 🟢 Mitigated | UptimeRobot pings `/api/v1/health` every 5 minutes. Function stays warm. |
| 6 | **Admin credentials hardcoded** | Security risk if repo is shared publicly | 🟡 Demo only | HMAC-signed token, not plaintext. For production: move to env var + proper auth. |
| 7 | **Native Skills — no audit trail** | Cannot track skill-based validations | 🟡 By design | Skills are local/offline by design. Use connected channels for governance requirements. |

---

## 6. Pending Items in Current Implementation

### High Priority (Before Production)

| # | Item | Area | Effort |
|---|---|---|---|
| 1 | **Replace admin hardcoded credentials** with env-var-based secret | Security | Small |
| 2 | **Set `LLM_PROVIDER=groq`** in Vercel env to stop Anthropic timeout retries | Backend | Trivial |
| 3 | **Top up Anthropic credits** or switch primary to claude-haiku-4-5 (4× cheaper) | Cost | Trivial |
| 4 | **Push GitHub Actions warmup workflow** (requires PAT with `workflow` scope) | DevOps | Small |
| 5 | **Teams persistent hosting** on Azure App Service (for production Teams bot) | Infrastructure | Medium |

### Medium Priority (Post-Demo Enhancements)

| # | Item | Area | Effort |
|---|---|---|---|
| 6 | **VS Code Extension** — validate prompt inline while typing | New Channel | Medium |
| 7 | **Azure OpenAI integration** — for clients who cannot use Groq/Anthropic | LLM | Small |
| 8 | **Power Automate connector** — validate prompts in M365 automation flows | New Channel | Small |
| 9 | **Commit untracked docs** — `docs/PROMPT_VALIDATOR_TECHNICAL_DOCUMENT.md` | Docs | Trivial |
| 10 | **Skill score calibration** — align native skill scoring closer to backend Groq scores | Quality | Small |
| 11 | **User onboarding flow** — guided first-use experience on Web UI | UX | Medium |
| 12 | **Email/Outlook add-in** — validate prompts directly in Outlook compose window | New Channel | Medium |

### Low Priority (Roadmap)

| # | Item | Area | Effort |
|---|---|---|---|
| 13 | **GitHub Copilot plugin** — validate code-gen prompts in VS Code/GitHub | New Channel | Large |
| 14 | **Multi-language prompt support** — scoring rubrics for non-English prompts | Feature | Large |
| 15 | **Prompt template library** — curated excellent prompts per persona as reusable templates | Feature | Medium |
| 16 | **Manager training dashboard** — which dimensions need coaching, trend reports | Analytics | Medium |
| 17 | **Benchmark mode** — compare prompt score before and after training sessions | Feature | Medium |
| 18 | **Jira/Confluence plugin** — validate prompts written in project management tools | New Channel | Large |

---

## Appendix: Validation Scoring Reference

### 5 Personas & Key Dimensions

| Persona ID | Name | Top Weighted Dimensions |
|---|---|---|
| persona_0 | All Employees | Clarity (18%), Context (14%), Specificity (14%), Output Format (14%), Ambiguity Reduction (14%) |
| persona_1 | Developer + QA | Technical Precision (18%), Edge Cases (18%), Testability (18%), Specificity (18%) |
| persona_2 | Technical PM | Output Format (18%), Reproducibility (14%), Context (14%), Prioritization (14%), Actionability (14%) |
| persona_3 | BA + Product Owner | Context (18%), Grounding (18%), Business Relevance (14%), Output Format (14%) |
| persona_4 | Support Staff | Tone/Empathy (18%), Compliance (14%), Speed (14%), Clarity (14%) |

### Rating Scale

| Score | Rating | Meaning |
|---|---|---|
| 85–100 | Excellent | Production-ready prompt |
| 70–84 | Good | Minor improvements recommended |
| 50–69 | Needs Improvement | Significant gaps — improve before use |
| 0–49 | Poor | Will likely produce generic/hallucinated output |

### LLM Provider Chain

```
Request arrives
      ↓
Static Pre-Screen (score ≥ 85?) → Yes → Return static result (no LLM cost)
      ↓ No
Anthropic Claude Sonnet (Primary)
      ↓ If credits = 0 or timeout
Groq llama-3.3-70b (Fallback — currently active, free)
      ↓ If rate limit exceeded
Static Rules Engine (always available, no external calls)
      ↓
Blend Score: 40% static + 60% LLM → Final score
      ↓
Store to MongoDB Atlas + return to channel
```

---

*Document generated: April 2026 | Infovision CoE AI/GenAI Practice*
*Deployment URL: https://promptvalidatorcompleterepo.vercel.app*
*Repository: https://github.com/Kishore-hubg/Prompt_eValidator_Code*
