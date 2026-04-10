# Prompt Validator — Quick Reference Guide
**Infovision CoE AI/GenAI Practice | Demo Reference**
**Date:** April 2026 | All links verified as of demo date

---

## 1. Production & Deployment Links

| Resource | URL / Value | Notes |
|---|---|---|
| **Web UI (Production)** | https://promptvalidatorcompleterepo.vercel.app | Main demo URL |
| **API Base URL** | https://promptvalidatorcompleterepo.vercel.app/api/v1 | All REST endpoints prefix |
| **MCP Endpoint** | https://promptvalidatorcompleterepo.vercel.app/mcp | JSON-RPC 2.0 |
| **Health Check** | https://promptvalidatorcompleterepo.vercel.app/api/v1/health | Returns `{"status":"ok"}` |
| **API Docs (Swagger)** | https://promptvalidatorcompleterepo.vercel.app/docs | FastAPI auto-docs |
| **GitHub Repository** | https://github.com/Kishore-hubg/Prompt_eValidator_Code | Source code |
| **Vercel Dashboard** | https://vercel.com/dashboard | Deployment management |

---

## 2. REST API Endpoints

### Base URL: `https://promptvalidatorcompleterepo.vercel.app/api/v1`
### Default API Key: `infovision-dev-key`

#### Core Validation

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/validate` | None | Validate + improve a prompt |
| `POST` | `/improve` | None | Improve prompt only (no re-score) |
| `GET` | `/personas` | None | List all 5 personas |
| `GET` | `/guidelines` | None | Fetch prompt quality guidelines |

#### Health & Status

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Basic liveness check |
| `GET` | `/health/db` | None | Database connectivity check |
| `GET` | `/validation-mode` | None | Active LLM provider + scoring mode |
| `GET` | `/compliance/day2-checklist` | None | Data governance checklist |

#### Demo & Samples

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/demo-samples` | None | All 15 demo prompts (5 personas × 3 tiers) |
| `GET` | `/demo-sample?persona_id=persona_0&quality=poor` | None | Single sample prompt |

#### History & Analytics

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/history?limit=20` | None | Recent validation history |
| `GET` | `/analytics/summary` | Bearer Token | Validation statistics |
| `GET` | `/leaderboard/weekly?week_start=2026-04-07&limit=10` | Bearer Token | Weekly team leaderboard |
| `GET` | `/leadership/org-dashboard?week_start=2026-04-07` | Bearer Token | Org-wide dashboard |
| `GET` | `/leadership/team-report/{team_id}?week_start=2026-04-07` | Bearer Token | Team performance report |
| `GET` | `/user/weekly-summary?user_id=X&week_start=2026-04-07` | Bearer Token | Per-user weekly stats |
| `POST` | `/aggregation/weekly/refresh?week_start=2026-04-07` | Bearer Token | Refresh weekly intelligence |

#### Integration Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/mcp/validate` | Bearer Token | MCP-specific validation |
| `POST` | `/teams/message` | Bearer Token | Teams bot message handler |
| `POST` | `/slack/validate` | HMAC-SHA256 | Slack slash command handler |
| `POST` | `/auth/resolve` | Bearer Token | OAuth token → user resolution |
| `POST` | `/auth/map-persona` | Bearer Token | Map user email → persona |

#### Admin Dashboard

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/admin/login` | Body: `{username, password}` | Admin login → HMAC token |
| `GET` | `/admin/records?page=1&per_page=50&search=&persona_id=&rating=&channel=&date_from=&date_to=` | Admin Token | All validation records |

#### Sample API Call
```bash
curl -X POST "https://promptvalidatorcompleterepo.vercel.app/api/v1/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_text": "Write a Python function to handle user login",
    "persona_id": "persona_1",
    "auto_improve": true,
    "channel": "api"
  }'
```

---

## 3. MCP Protocol Endpoints

### Base: `https://promptvalidatorcompleterepo.vercel.app/mcp`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/mcp` | **Main** — Standard JSON-RPC 2.0 endpoint (Claude Desktop, Claude Code) |
| `GET` | `/mcp` | Returns 405 — SSE not supported |
| `POST` | `/mcp/list-tools` | Legacy: list available tools |
| `POST` | `/mcp/call-tool` | Legacy: call a specific tool |
| `GET` | `/mcp/resources` | List MCP resources |
| `GET` | `/mcp/capabilities` | MCP server capabilities |

### MCP Tools (7 Available)

| Tool Name | Description | Key Parameters |
|---|---|---|
| `validate_prompt` | Score + rate + improve in one call | `prompt_text`, `persona_id`, `auto_improve` (default: true) |
| `improve_prompt` | AI rewrite with strategy selection | `prompt_text`, `persona_id`, `strategy` (template/clarify/expand/simplify) |
| `list_personas` | List all 5 personas with criteria | None |
| `get_persona_details` | Detailed weights for a persona | `persona_id` |
| `query_history` | Search past validations | `user_email`, `persona_id`, `limit` |
| `get_analytics` | Aggregate trends | `time_period` (today/week/month/all) |
| `save_validation` | Persist result to audit trail | `prompt_text`, `score`, `rating`, `persona_id` |

### MCP Sample JSON-RPC Call
```bash
curl -X POST "https://promptvalidatorcompleterepo.vercel.app/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "validate_prompt",
      "arguments": {
        "prompt_text": "Write a Python function to handle login",
        "persona_id": "persona_1",
        "auto_improve": true
      }
    }
  }'
```

---

## 4. Claude Code CLI — MCP Registration

| Command | Purpose |
|---|---|
| `claude mcp add --transport http prompt-validator https://promptvalidatorcompleterepo.vercel.app/mcp` | Register MCP server |
| `claude mcp list` | Verify registration |
| `claude mcp remove prompt-validator` | Remove registration |

### Usage in Claude Code
```
Use prompt-validator to validate this prompt for persona_1: Write a Python login function
Use prompt-validator to list all personas
Use prompt-validator to get analytics for this week
```

---

## 5. Claude Desktop MCP — Config File

**File Location:** `C:\Users\<username>\AppData\Roaming\Claude\claude_desktop_config.json`

**Proxy File Location:** `C:\Users\<username>\.claude\mcp-proxy.js`

```json
{
  "mcpServers": {
    "prompt-validator": {
      "command": "node",
      "args": ["C:/Users/<username>/.claude/mcp-proxy.js"]
    }
  }
}
```

> **Important:** Replace `<username>` with actual Windows username before sharing.

---

## 6. Native Claude Skills — Commands

**Location:** `C:\Users\<username>\.claude\skills\`

| Slash Command | Skill File | Persona | Cost |
|---|---|---|---|
| `/validate-prompt <text>` | `validate-prompt/SKILL.md` | All Employees (Baseline) | $0 |
| `/validate-dev <text>` | `validate-dev/SKILL.md` | Developer + QA | $0 |
| `/validate-pm <text>` | `validate-pm/SKILL.md` | Technical PM / PM | $0 |
| `/validate-ba <text>` | `validate-ba/SKILL.md` | BA + Product Owner | $0 |
| `/validate-support <text>` | `validate-support/SKILL.md` | Support Staff | $0 |

### Usage Examples
```
/validate-prompt  Summarize the meeting notes
/validate-dev  Write a Python function to parse JWT tokens
/validate-pm  Give me a sprint update
/validate-ba  Extract requirements from the BRD document
/validate-support  Reply to an angry customer about billing
```

---

## 7. Slack Integration

| Item | Value |
|---|---|
| **Slash Command** | `/validate` |
| **Endpoint** | `https://promptvalidatorcompleterepo.vercel.app/api/v1/slack/validate` |
| **Auth Method** | HMAC-SHA256 signature (Slack Signing Secret) |
| **Response Type** | Ephemeral (visible to user only) |
| **Card Type** | Block Kit rich card |

### Slack Usage Syntax
```
/validate Write a Python function to handle user login
/validate persona:dev Write a Python function to handle user login
/validate persona:pm Generate a sprint status report for our team
/validate persona:ba Extract requirements from the BRD document
/validate persona:support Reply to a customer complaint about billing
```

---

## 8. Microsoft Teams Bot

| Item | Value |
|---|---|
| **Bot App ID** | `89f80bcf-efa3-4a07-a4a4-e766f3557e98` |
| **Endpoint** | `https://promptvalidatorcompleterepo.vercel.app/api/messages` |
| **Microsoft Tenant ID** | `ba5028ea-2f88-4298-bba5-cecf95342a75` |
| **Microsoft Client ID** | `7b6ec3f4-3759-48d6-a558-6a1bcd1824c6` |
| **Auth** | Microsoft Entra ID / Azure Bot Service |
| **Card Type** | Adaptive Cards |

### Teams Usage
```
@PromptValidator validate this: Write a Python function to handle login
@PromptValidator validate for pm: Generate a sprint status update
@PromptValidator list personas
@PromptValidator help
```

---

## 9. Persona IDs & Weights Reference

| Persona ID | Name | Top Dimensions | Best Used For |
|---|---|---|---|
| `persona_0` | All Employees | Clarity 18%, Context 14%, Specificity 14%, Output Format 14% | General/default — all roles |
| `persona_1` | Developer + QA | Tech Precision 18%, Edge Cases 18%, Testability 18%, Specificity 18% | Code, bug fix, test cases, automation |
| `persona_2` | Technical PM | Output Format 18%, Prioritization 14%, Actionability 14%, Context 14% | Sprint reports, status updates, estimates |
| `persona_3` | BA + Product Owner | Context 18%, Grounding 18%, Business Relevance 14%, Output Format 14% | BRD extraction, user stories, requirements |
| `persona_4` | Support Staff | Tone/Empathy 18%, Compliance 14%, Speed 14%, Clarity 14% | Customer replies, escalations, ticket responses |

---

## 10. Rating Scale

| Score Range | Rating | Action Required |
|---|---|---|
| 85 – 100 | **Excellent** | Production-ready — use as-is |
| 70 – 84 | **Good** | Minor tweaks recommended |
| 50 – 69 | **Needs Improvement** | Revise before submitting |
| 0 – 49 | **Poor** | Significant gaps — AI will produce generic/hallucinated output |

---

## 11. Good & Bad Prompt Examples by Persona

---

### Persona 0 — All Employees (Baseline)

| Quality | Prompt | Expected Score | Why |
|---|---|---|---|
| ✅ Excellent | Write a professional email to the BFSI client at Ziply Telecom summarising the outcomes of our Sprint 14 review meeting held on 28 March 2026. Audience: VP of Finance and Project Sponsor. Structure: (1) Opening, (2) Key decisions (bullet), (3) Risks with owners, (4) Next steps with due dates. Tone: formal. Max 350 words. No internal Slack references. | 85–100 | Strong action verb, full context, explicit format, audience, constraints, scope |
| 🟡 Medium | Summarize the Q4 revenue highlights from the earnings report. Mention any key figures or trends. | 50–69 | Has action verb and partial context but missing output format, constraints, audience |
| ❌ Poor | Help me write something for a client. | 0–30 | No action verb, no context, no output format, no constraints, completely open-ended |

---

### Persona 1 — Developer + QA

| Quality | Prompt | Expected Score | Why |
|---|---|---|---|
| ✅ Excellent | Using Python 3.12 and FastAPI 0.115+, implement a POST /api/v1/validate endpoint that accepts JSON with: prompt (str, required, max 2000 chars), persona_id (enum: persona_0–4), auto_improve (bool, default false). Validate with Pydantic v2. Return HTTP 422 for invalid input. Apply OWASP Top 10 — prevent prompt injection and XSS. Include edge cases: empty prompt, prompt > 2000 chars, invalid persona_id. Write pytest unit tests for each using FastAPI TestClient. Format: TC-ID \| Preconditions \| Steps \| Expected Result. 100% coverage on validation logic. | 85–100 | Language/version specified, edge cases explicit, test format declared, OWASP referenced, scope defined |
| 🟡 Medium | Using FastAPI and Pydantic v2, add a POST /api/v1/validate route that accepts prompt, persona_id, and auto_improve. Return 422 on bad input. Show the route and Pydantic model. | 50–69 | Language specified but no version, no edge cases, no test format, limited scope |
| ❌ Poor | Write some code to validate a prompt. | 0–30 | No language, no framework, no edge cases, no test structure, too generic |

**Additional Examples for Developer Persona:**

| Type | Prompt |
|---|---|
| ✅ Good | In TypeScript 5.x with Node.js 20 and Express 4, write a JWT middleware that validates Bearer tokens. Include edge cases: expired token, malformed token, missing Authorization header, and valid token. Return 401 with descriptive error message for each case. Output: middleware function + Mocha test suite with one test per edge case. |
| ❌ Bad | Add authentication to my app. |
| ✅ Good | Using Cypress 13, write E2E test cases for the login form at /login. Test: valid credentials (expect redirect to /dashboard), invalid password (expect error message), empty fields (expect validation error), SQL injection attempt in email field. Format: describe/it blocks with assertions. |
| ❌ Bad | Test the login page. |

---

### Persona 2 — Technical PM / PM

| Quality | Prompt | Expected Score | Why |
|---|---|---|---|
| ✅ Excellent | Generate a Sprint 14 status report for the Ziply Telecom Finance Modernisation engagement (T&M model, 8-week sprint). Period: 17–28 March 2026. Audience: Delivery Manager and Client Project Sponsor. Structure: (1) Executive Summary (3 sentences), (2) Completed vs Planned table with RAG status, (3) Top 3 risks by impact with owner and mitigation, (4) Next sprint commitments with dates and owners. Velocity: 42 story points delivered vs 45 planned (93%). Flag Red items in Executive Summary. Output: structured Markdown. | 85–100 | Report type declared, full sprint/team context, audience specified, engagement model included, velocity data provided, output format defined |
| 🟡 Medium | Write a Sprint 14 status update for the Ziply Finance project. Include what the team completed and main risks. Summarize next sprint priorities. | 50–69 | Has project context and structure intent but missing velocity data, audience, engagement model, RAG format |
| ❌ Poor | Give me an update on the project. | 0–30 | No sprint context, no team, no format, no audience — completely unusable |

**Additional Examples for PM Persona:**

| Type | Prompt |
|---|---|
| ✅ Good | Create a risk log for the Ziply Telecom GL migration project for the week ending 4 April 2026. Identify top 5 risks. Format: Risk ID \| Description \| Likelihood (H/M/L) \| Impact (H/M/L) \| Owner \| Mitigation Action \| Status. Audience: PMO Director. Engagement: Fixed Bid. Flag any risks with High Likelihood AND High Impact as critical. |
| ❌ Bad | List the project risks. |
| ✅ Good | Validate the estimate of 120 story points for the API integration module in Sprint 15. Reference: last 4 sprints delivered 38, 42, 45, 40 points. Team size: 4 developers. Comparable story: payment gateway integration (Sprint 11, 35 points, 2 developers). Output: estimate validation table with recommended range, confidence level (High/Medium/Low), and 2 risk factors. |
| ❌ Bad | Is 120 story points realistic? |

---

### Persona 3 — Business Analyst + Product Owner

| Quality | Prompt | Expected Score | Why |
|---|---|---|---|
| ✅ Excellent | Based on Section 4.2 (Data Migration Requirements) of the Ziply Finance Modernisation BRD v2.1 (March 2026), extract all functional requirements for GL Trial Balance data migration. Output: Requirement ID \| Requirement Text \| Source Section \| Acceptance Criteria (Given/When/Then). Only use explicit statements — do not infer. Prioritise using MoSCoW. Audience: Delivery team leads. | 85–100 | Source document cited, section specified, inference boundary declared, output format defined, audience named, prioritization framework included |
| 🟡 Medium | Extract the functional requirements for GL Trial Balance migration from the project BRD. List as bullet points. | 50–69 | Has task and partial context but no source reference, no inference boundary, no format structure |
| ❌ Poor | List the requirements for the project. | 0–20 | No source, no scope, no format, no inference boundary — extreme hallucination risk |

**Additional Examples for BA/PO Persona:**

| Type | Prompt |
|---|---|
| ✅ Good | From the user interview transcript (Customer Support Operations, Infovision, Feb 2026), identify all pain points related to ticket routing delays. Output: Pain Point ID \| Quote from Transcript \| Frequency Mentioned \| Impact (High/Med/Low). Do not infer — only cite explicit statements. Audience: Product Owner and UX Lead. |
| ❌ Bad | What are the customer pain points? |
| ✅ Good | Translate the following technical requirement into a user story for a business stakeholder audience: "The API must validate JWT tokens with RS256 signing using JWKS endpoint discovery." Format: As a [role], I want [capability], so that [benefit]. Include 3 testable acceptance criteria using Given/When/Then. |
| ❌ Bad | Write a user story for the authentication feature. |

---

### Persona 4 — Support Staff

| Quality | Prompt | Expected Score | Why |
|---|---|---|---|
| ✅ Excellent | Write a concise, empathetic customer-facing email response for a Ziply Telecom Retail tier customer who was double-charged on their February 2026 invoice. Ticket: #TKT-20260315-0042. Tone: apologetic and empathetic. Comply with Ziply SLA (24-hour resolution for Retail tier). Reference refund policy Section 3.1. Format: formal email with subject line, 3-paragraph body (acknowledgment, resolution, next steps), closing. Max 200 words. Confirm refund within 4 business hours and SMS notification. | 85–100 | Tone specified, channel declared, policy referenced, SLA cited, output format defined, customer context provided, length constrained |
| 🟡 Medium | Draft an email to a Ziply customer who was double-charged in February. Reference ticket #TKT-20260315-0042. Apologize and outline refund next steps professionally. Under 200 words. | 50–69 | Has tone intent and ticket reference but missing SLA, policy reference, empathy directive, format structure |
| ❌ Poor | Reply to an angry customer. | 0–20 | No tone, no channel, no policy, no issue context, no output format — highest risk persona failure |

**Additional Examples for Support Persona:**

| Type | Prompt |
|---|---|
| ✅ Good | Write a live chat response for a Ziply Business tier customer reporting that their internet has been down for 6 hours (ticket #TKT-20260406-0091). Tone: calm, professional, action-oriented. Reference SLA Tier 2 (4-hour response / 8-hour resolution). Output: 3-message chat sequence — acknowledgment, status update, escalation confirmation. Max 50 words per message. Do not use jargon. |
| ❌ Bad | Help with an internet outage complaint. |
| ✅ Good | Draft an internal escalation note for Supervisor review for ticket #TKT-20260405-0033. Customer: Ziply Enterprise tier. Issue: repeated billing errors over 3 months. Tone: factual and neutral. Include: issue summary, customer history (3 incidents), risk level (High — churn risk), recommended resolution, escalation owner. Format: structured internal note, max 250 words. |
| ❌ Bad | Write a note about a customer problem. |

---

## 12. Quick Test Commands

### Test All Channels (Copy-Paste Ready)

**Web UI:** Open https://promptvalidatorcompleterepo.vercel.app → Select persona → Paste prompt → Validate

**REST API:**
```bash
curl -s -X POST "https://promptvalidatorcompleterepo.vercel.app/api/v1/validate" \
  -H "Content-Type: application/json" \
  -d '{"prompt_text":"Write a Python login function","persona_id":"persona_1","auto_improve":true}' \
  | python -m json.tool
```

**MCP Health:**
```bash
curl -s -X POST "https://promptvalidatorcompleterepo.vercel.app/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

**Native Skills (Claude Code):**
```
/validate-dev  Write a Python login function
/validate-pm   Generate a sprint status report
/validate-ba   Extract requirements from the BRD
/validate-support  Reply to a double-charged customer
/validate-prompt  Summarize the meeting notes
```

**Claude Code MCP:**
```
Use prompt-validator to list all personas
Use prompt-validator to validate this prompt for persona_1: Write a Python login function
```

---

*Prompt Validator MVP | Infovision CoE AI/GenAI Practice | April 2026*
