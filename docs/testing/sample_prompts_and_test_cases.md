# Prompt Validator — Sample Prompts & Full Test Cases
**Project:** INFOVISION Prompt Validator MVP
**Version:** 1.0 | **Date:** 2026-04-01
**Scope:** 20 Sample Prompts (positive + negative) + Full BRD Functional Test Suite

---

## TABLE OF CONTENTS

1. [Sample Prompts — 20 Scenarios (All Personas)](#1-sample-prompts)
2. [Reprompting Validation Pairs](#2-reprompting-validation-pairs)
3. [Full Functional Test Cases](#3-full-functional-test-cases)
   - TC-API: API Health & Configuration
   - TC-PER: Persona Routing & Validation
   - TC-SCR: Scoring Algorithm
   - TC-DIM: Dimension Breakdown
   - TC-LLM: LLM Functionality & Anti-Hallucination
   - TC-RPM: Reprompting / Auto-Improve
   - TC-DED: Deduplication
   - TC-AUTH: Authentication & Security
   - TC-DB: Data Persistence
   - TC-MCP: MCP Channel
   - TC-TMS: Teams Channel
   - TC-ANA: Analytics & Leadership
   - TC-EDG: Edge Cases & Error Handling

---

## 1. SAMPLE PROMPTS

### Rating Legend
| Score Range | Rating | Expected Outcome |
|---|---|---|
| 85–100 | ✅ Excellent | All or most dimensions Pass, 0–1 issues |
| 70–84 | 🟡 Good | Most dimensions Pass, 1–3 issues |
| 50–69 | 🟠 Needs Improvement | Mixed pass/fail, 3–5 issues |
| 0–49 | ❌ Poor | Most dimensions Fail, 5–6 issues |

---

### PERSONA 0 — All Employees (General Knowledge Worker)
**Dimensions:** clarity (18), context (14), specificity (14), output_format (14), ambiguity_reduction (14), constraints (10), actionability (10), accuracy (7)

---

#### SP-01 ✅ POSITIVE — Excellent prompt (Expected score: 88–100)
```
Prompt: Write a professional email to the BFSI client at Ziply Telecom summarising
the outcomes of our Sprint 14 review meeting held on 28 March 2026. The audience
is the client's VP of Finance and Project Sponsor. Structure the email as:
(1) Opening with meeting reference, (2) Key decisions made (bullet list),
(3) Risks identified with owner names, (4) Next steps with due dates.
Tone should be formal and concise. Maximum 350 words. Do not include internal
Slack references or pricing details.
```
**Why positive:**
- Clear action verb ("Write")
- Context: client, sprint number, date, audience role
- Output format declared: numbered sections + bullet list
- Constraints: tone, word limit, exclusions
- Specificity: named entities, dates, structure

**Expected dimension results:**

| Dimension | Expected | Reason |
|---|---|---|
| clarity | Pass | Direct instruction with action verb |
| context | Pass | Sprint 14, Ziply, VP of Finance, 28 Mar |
| specificity | Pass | Named client, sprint, structure sections |
| output_format | Pass | Explicit numbered + bullet structure |
| ambiguity_reduction | Pass | Tone + exclusion constraints stated |
| constraints | Pass | Word limit + exclusions defined |
| actionability | Pass | Deliverable is clear |
| accuracy | Pass | Specific factual grounding provided |

---

#### SP-02 ❌ NEGATIVE — Poor prompt (Expected score: 20–35)
```
Prompt: Help me write something for a client.
```
**Why negative:**
- No action verb context
- No client identity, meeting, or purpose
- No output format
- Completely open-ended
- No constraints

**Expected dimension results:**

| Dimension | Expected | Reason |
|---|---|---|
| clarity | Fail | "something" is undefined |
| context | Fail | No source, audience, or purpose |
| specificity | Fail | Zero specifics |
| output_format | Fail | No format stated |
| ambiguity_reduction | Fail | Fully ambiguous |
| constraints | Fail | None present |
| actionability | Fail | No deliverable defined |
| accuracy | Fail | No grounding |

---

#### SP-03 🟡 GOOD — Moderate prompt (Expected score: 65–78)
```
Prompt: Summarise the key highlights from our Q1 2026 business review for the
leadership team. Include financial performance, delivery milestones, and risks.
Use a table format where possible.
```
**Why moderate:**
- Has context and format hint
- Missing: audience specificity, tone, word constraints, source references
- Partial pass expected on ~5 of 8 dimensions

---

#### SP-04 🟠 NEEDS IMPROVEMENT — Below average (Expected score: 40–55)
```
Prompt: Create a report about our project.
```
**Why below average:**
- Minimal action verb present
- No client, no project identity, no structure
- No output format, no constraints
- Passes only "actionability" (marginally)

---

### PERSONA 1 — Developer + QA Engineer
**Dimensions:** technical_precision (18), edge_cases (18), testability (18), specificity (18), context (14), reproducibility (14), accuracy (14)

---

#### SP-05 ✅ POSITIVE — Excellent developer prompt (Expected score: 90–100)
```
Prompt: Using Python 3.12 and FastAPI 0.115+, implement a POST /api/v1/validate
endpoint that accepts a JSON body with fields: prompt (str, required, max 2000 chars),
persona_id (str, enum: persona_0 to persona_4), and auto_improve (bool, default false).
Validate input using Pydantic v2 BaseModel. Return HTTP 422 for invalid input.
Apply OWASP Top 10 input sanitisation — specifically prevent prompt injection and
XSS in prompt text. Include edge cases: empty prompt string, prompt exceeding 2000 chars,
invalid persona_id value. Write pytest unit tests for each edge case using
FastAPI TestClient. Expected test format: TC-ID | Preconditions | Steps | Expected Result.
```
**Why positive:**
- Language/framework/version explicit (Python 3.12, FastAPI 0.115+, Pydantic v2)
- OWASP security constraint named
- Edge cases explicitly listed
- Test format specified (pytest + TC-ID format)
- Reproducible (pinned versions, clear structure)

**Expected dimension results:**

| Dimension | Expected | Reason |
|---|---|---|
| technical_precision | Pass | Stack versions + Pydantic v2 + OWASP |
| edge_cases | Pass | 3 edge cases named explicitly |
| testability | Pass | pytest, TestClient, TC-ID format |
| specificity | Pass | Exact endpoint, fields, types, constraints |
| context | Pass | Codebase context: endpoint signature + schema |
| reproducibility | Pass | Pinned versions + defined steps |
| accuracy | Pass | Precise constraints (2000 chars, enum values) |

---

#### SP-06 ❌ NEGATIVE — Poor developer prompt (Expected score: 15–30)
```
Prompt: Write some code to validate a prompt.
```
**Why negative:**
- No language, framework, or version
- No function signature, no input/output schema
- No edge cases
- No test requirements
- Non-reproducible

**Expected dimension results:**

| Dimension | Expected | Reason |
|---|---|---|
| technical_precision | Fail | No language/version/framework |
| edge_cases | Fail | None mentioned |
| testability | Fail | No test format, no acceptance criteria |
| specificity | Fail | "some code" is undefined |
| context | Fail | No interface/class/signature |
| reproducibility | Fail | Cannot reproduce without specs |
| accuracy | Fail | No factual technical grounding |

---

#### SP-07 🟡 GOOD — QA-focused moderate prompt (Expected score: 68–80)
```
Prompt: Write pytest test cases for the /validate endpoint in FastAPI.
Cover the happy path where a valid persona_0 prompt is submitted and returns
a score between 0–100. Also cover the case where prompt is empty (expect 422).
Use FastAPI TestClient. Format: function name, docstring, assertions.
```
**Why moderate:**
- Has test format, TestClient, acceptance criteria
- Missing: Python version, security edge cases, TC-ID format, US reference

---

#### SP-08 🟠 NEEDS IMPROVEMENT — Partial developer prompt (Expected score: 42–58)
```
Prompt: Add error handling to the validate function so it doesn't crash.
```
**Why below average:**
- No language/framework specified
- No error types, no boundary conditions
- Not reproducible, not testable as-is
- Passes specificity partially ("validate function")

---

### PERSONA 2 — Technical Project Manager
**Dimensions:** output_format (18), reproducibility (14), context (14), specificity (14), prioritization (14), actionability (14), engagement_model_awareness (10), speed (7)

---

#### SP-09 ✅ POSITIVE — Excellent PM prompt (Expected score: 88–100)
```
Prompt: Generate a Sprint 14 status report for the Ziply Telecom Finance Modernisation
engagement (T&M model, 8-week sprint). Reporting period: 17–28 March 2026.
Audience: Delivery Manager and Client Project Sponsor.
Structure: (1) Executive Summary (3 sentences max), (2) Completed vs Planned work
table with RAG status, (3) Top 3 risks ranked by impact with owner and mitigation,
(4) Next sprint commitments with due dates.
Output as a structured Markdown report. Prioritise risks over achievements in narrative.
Reference velocity data: 42 story points delivered vs 45 planned.
```
**Why positive:**
- Report type declared first (Sprint 14 status report)
- Engagement model: T&M named
- Sprint context: number, team, dates, audience
- Prioritization: Top 3 risks ranked by impact
- Traceability: velocity data (42 vs 45 points)
- Output format: Markdown, labeled sections

---

#### SP-10 ❌ NEGATIVE — Poor PM prompt (Expected score: 18–32)
```
Prompt: Give me an update on the project.
```
**Why negative:**
- No report type, no sprint context, no dates
- No output format
- No prioritization criteria
- No engagement model context
- Non-reproducible (which project?)

---

#### SP-11 🟡 GOOD — Moderate PM prompt (Expected score: 65–79)
```
Prompt: Create a risk log for our current sprint for the client. Include risk name,
severity, owner, and mitigation. Sort by severity high to low. Output as a table.
```
**Why moderate:**
- Has output format (table), prioritization hint, structure
- Missing: sprint number, engagement model, dates, traceability data

---

#### SP-12 🟠 NEEDS IMPROVEMENT — Minimal PM prompt (Expected score: 38–52)
```
Prompt: Write a summary of this week's work for stakeholders.
```
**Why below average:**
- No structure, no sprint context, no dates
- "Stakeholders" is undefined
- Passes actionability weakly

---

### PERSONA 3 — Business Analyst + Product Owner
**Dimensions:** context (18), grounding (18), business_relevance (14), output_format (14), specificity (14), prioritization (4), accuracy (14)

---

#### SP-13 ✅ POSITIVE — Excellent BA/PO prompt (Expected score: 88–100)
```
Prompt: Based on Section 4.2 (Data Migration Requirements) of the Ziply Finance
Modernisation BRD document (version 2.1, March 2026), extract all functional
requirements related to GL Trial Balance data migration. For each requirement,
output: Requirement ID | Requirement Text | Source Section | Acceptance Criteria
(testable, using Given/When/Then format). Only use explicit statements from the
document — do not infer or add requirements not present in Section 4.2.
Prioritise using MoSCoW: Must Have vs Should Have. Audience: Delivery team leads.
```
**Why positive:**
- Source document + section explicitly referenced
- Citation/traceability required per item
- Inference policy stated: explicit-only
- Audience named: delivery team leads
- Acceptance criteria: testable Given/When/Then
- Prioritization: MoSCoW framework named
- Output format: table with IDs

---

#### SP-14 ❌ NEGATIVE — Poor BA/PO prompt (Expected score: 18–30)
```
Prompt: List the requirements for the project.
```
**Why negative:**
- No source document reference
- No section, no traceability
- No audience, no acceptance criteria
- No prioritization framework
- Completely open-ended inference allowed

---

#### SP-15 🟡 GOOD — Moderate BA prompt (Expected score: 68–80)
```
Prompt: Extract user stories from the attached requirements document for the
data migration module. Format as: As a [role], I want [goal] so that [benefit].
Include acceptance criteria for each story. Prioritise by business impact.
```
**Why moderate:**
- Has user story format, acceptance criteria, prioritization
- Missing: source document + section reference, inference policy, named audience

---

#### SP-16 🟠 NEEDS IMPROVEMENT — Weak PO prompt (Expected score: 40–55)
```
Prompt: Write user stories for login functionality.
```
**Why below average:**
- No source document, no section
- No acceptance criteria, no prioritization
- Passes specificity partially ("login functionality")

---

### PERSONA 4 — Support Staff
**Dimensions:** tone_empathy (18), compliance (14), speed (14), clarity (14), reproducibility (10), context (10), output_format (7), precision (7)

---

#### SP-17 ✅ POSITIVE — Excellent support prompt (Expected score: 88–100)
```
Prompt: Write an empathetic customer-facing email response for a Ziply Telecom
retail customer who has been double-charged on their invoice for February 2026.
The customer is frustrated and has submitted ticket #TKT-20260315-0042.
Tone: apologetic and empathetic. Comply with Ziply SLA policy (resolution within
24 hours). Reference the refund policy under Section 3.1 of the Customer Billing
Policy document. Output: formal email format with subject line, greeting, 3-paragraph
body, and closing. Maximum 200 words. Next action: confirm refund initiation
within 4 business hours.
```
**Why positive:**
- Tone directive: apologetic and empathetic
- SLA policy referenced (24-hour resolution)
- Policy document cited: Section 3.1
- Customer context: issue type (double charge), urgency (frustration), ticket ID
- Output format: email with labeled sections
- Speed: concise (200 words max), next action defined

---

#### SP-18 ❌ NEGATIVE — Poor support prompt (Expected score: 15–28)
```
Prompt: Reply to an angry customer.
```
**Why negative:**
- No tone directive
- No policy reference, no SLA
- No customer issue context
- No output format
- Not reproducible

---

#### SP-19 🟡 GOOD — Moderate support prompt (Expected score: 65–78)
```
Prompt: Write a polite response to a customer complaining about a delayed delivery.
Tone should be empathetic. Keep it brief (under 150 words). Include a next step
about tracking the order.
```
**Why moderate:**
- Has tone directive, brevity target, next action
- Missing: policy reference, SLA, compliance constraint, ticket/issue context

---

#### SP-20 🟠 NEEDS IMPROVEMENT — Below average support prompt (Expected score: 40–52)
```
Prompt: Help me write a response to a customer about a billing issue.
```
**Why below average:**
- Tone is absent
- No SLA, no policy reference
- Issue type vague ("billing issue")
- Passes context partially ("billing issue" present)

---

## 2. REPROMPTING VALIDATION PAIRS

These pairs test the **score must increase on improved prompt** rule.

---

### RP-01: Persona 0 — All Employees

**Round 1 (Original — Expected: ~35):**
```
Write something about our project status for the team.
```

**Round 2 (Improved — Expected: ~80+):**
```
Write a concise project status update email for the Infovision delivery team
covering Sprint 14 (17–28 March 2026). Structure: (1) What was completed this
sprint, (2) What is blocked with owner name, (3) Planned work for Sprint 15.
Tone: factual and brief. Maximum 200 words. Audience: internal delivery team only.
```
**Validation rule:** Score Round 2 > Score Round 1 by at least 30 points.

---

### RP-02: Persona 1 — Developer

**Round 1 (Original — Expected: ~22):**
```
Fix the bug in my code.
```

**Round 2 (Improved — Expected: ~85+):**
```
In Python 3.12 with FastAPI 0.115+, fix the bug in the POST /api/v1/validate
endpoint where a prompt with Unicode characters (e.g., Arabic text) causes a
500 Internal Server Error. Root cause: Pydantic v2 string validation failing
on non-ASCII input without explicit `allow_population_by_field_name=True`.
Expected fix: update the Pydantic model to accept Unicode. Add a pytest test
case covering Unicode input (Arabic, CJK, emoji). Expected result: HTTP 200
with valid JSON response. No changes to existing test suite should break.
```
**Validation rule:** technical_precision, edge_cases, testability all Pass in Round 2.

---

### RP-03: Persona 4 — Support Staff

**Round 1 (Original — Expected: ~20):**
```
Reply to a customer complaint.
```

**Round 2 (Improved — Expected: ~88+):**
```
Write an empathetic, apologetic email to a Telecom customer (ticket #TKT-20260318-0091)
who reported that their service was interrupted for 6 hours on 17 March 2026.
Comply with the SLA policy: acknowledge within 2 hours, resolve within 8 hours.
Tone: empathetic and reassuring. Reference the Service Continuity Policy, Section 2.3.
Output: formal email — subject line, 3-paragraph body, next steps, closing.
Max 180 words. Next action: escalation path to Tier 2 if not resolved in 8 hours.
```
**Validation rule:** tone_empathy, compliance, speed all Pass in Round 2.

---

## 3. FULL FUNCTIONAL TEST CASES

**Format:** TC-ID | Title | Endpoint | Input | Expected Result | Priority | Coverage Area

---

### TC-API: API Health & Configuration

---

#### TC-API-01
**Title:** Health check returns 200 with uptime info
**Endpoint:** `GET /api/v1/health`
**Input:** None
**Expected:**
```json
{ "status": "ok", "uptime_seconds": <number> }
```
HTTP 200
**Priority:** P0
**Notes:** Smoke test — must pass before any other tests

---

#### TC-API-02
**Title:** Validation mode returns scoring config
**Endpoint:** `GET /api/v1/validation-mode`
**Input:** None
**Expected:**
```json
{
  "scoring_mode": "weighted_pass_fail",
  "provider": "groq|anthropic|static",
  "source_of_truth": "persona_criteria_source_truth.json"
}
```
HTTP 200. Score scale must reference 0–100.
**Priority:** P1

---

#### TC-API-03
**Title:** Personas list returns all 5 personas
**Endpoint:** `GET /api/v1/personas`
**Input:** None
**Expected:** Array of 5 objects, each with `id`, `name`, `description`, `dimensions` array.
IDs must be: `persona_0`, `persona_1`, `persona_2`, `persona_3`, `persona_4`.
HTTP 200
**Priority:** P0

---

#### TC-API-04
**Title:** Guidelines endpoint returns guideline config
**Endpoint:** `GET /api/v1/guidelines`
**Input:** None
**Expected:**
```json
{
  "strict_mode": true,
  "strict_penalty_per_miss": 3,
  "strict_penalty_cap": 15,
  "global_checks": [ ... ]
}
```
HTTP 200. `global_checks` must have ≥ 1 entry.
**Priority:** P1

---

#### TC-API-05
**Title:** Day 2 compliance checklist returns 6 governance checks
**Endpoint:** `GET /api/v1/compliance/day2-checklist`
**Input:** `X-API-Key: infovision-dev-key` header
**Expected:** Array of 6 governance checks with `check`, `status`, `detail` fields.
HTTP 200
**Priority:** P1

---

### TC-PER: Persona Routing & Validation

---

#### TC-PER-01
**Title:** persona_0 validation scores SP-01 as Excellent
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "<SP-01 prompt text>",
  "persona_id": "persona_0"
}
```
**Expected:**
- HTTP 200
- `validation_score` ≥ 85
- `rating` = "Excellent"
- `dimension_scores` array: all 8 dimensions present
- `issues` count ≤ 2
- `strengths` count ≥ 3
**Priority:** P0

---

#### TC-PER-02
**Title:** persona_0 validation scores SP-02 as Poor
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Help me write something for a client.",
  "persona_id": "persona_0"
}
```
**Expected:**
- HTTP 200
- `validation_score` ≤ 40
- `rating` = "Poor"
- `issues` count ≥ 4
- `dimension_scores`: clarity, context, output_format should all show `passed: false`
**Priority:** P0

---

#### TC-PER-03
**Title:** persona_1 validation scores SP-05 as Excellent
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "<SP-05 prompt text>",
  "persona_id": "persona_1"
}
```
**Expected:**
- HTTP 200
- `validation_score` ≥ 88
- `technical_precision` dimension: `passed: true`
- `edge_cases` dimension: `passed: true`
- `testability` dimension: `passed: true`
- `issues` count = 0
**Priority:** P0

---

#### TC-PER-04
**Title:** persona_1 validation scores SP-06 as Poor
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Write some code to validate a prompt.",
  "persona_id": "persona_1"
}
```
**Expected:**
- `validation_score` ≤ 30
- `technical_precision` dimension: `passed: false`
- `edge_cases` dimension: `passed: false`
- `testability` dimension: `passed: false`
- `issues` count ≥ 4
**Priority:** P0

---

#### TC-PER-05
**Title:** persona_2 validation scores SP-09 as Excellent
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "<SP-09 prompt text>",
  "persona_id": "persona_2"
}
```
**Expected:**
- `validation_score` ≥ 85
- `output_format` dimension: `passed: true`
- `prioritization` dimension: `passed: true`
- `engagement_model_awareness` dimension: `passed: true`
- `traceability` references present in strengths
**Priority:** P0

---

#### TC-PER-06
**Title:** persona_2 validation scores SP-10 as Poor
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Give me an update on the project.",
  "persona_id": "persona_2"
}
```
**Expected:**
- `validation_score` ≤ 35
- `output_format`: `passed: false`
- `prioritization`: `passed: false`
- `context`: `passed: false`
- `issues` ≥ 4
**Priority:** P0

---

#### TC-PER-07
**Title:** persona_3 validation scores SP-13 as Excellent
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "<SP-13 prompt text>",
  "persona_id": "persona_3"
}
```
**Expected:**
- `validation_score` ≥ 85
- `grounding` dimension: `passed: true`
- `context` dimension: `passed: true`
- `business_relevance` dimension: `passed: true`
- `issues` count ≤ 1
**Priority:** P0

---

#### TC-PER-08
**Title:** persona_3 validation scores SP-14 as Poor
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "List the requirements for the project.",
  "persona_id": "persona_3"
}
```
**Expected:**
- `validation_score` ≤ 30
- `grounding`: `passed: false`
- `context`: `passed: false`
- `accuracy`: `passed: false`
- `issues` ≥ 4
**Priority:** P0

---

#### TC-PER-09
**Title:** persona_4 validation scores SP-17 as Excellent
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "<SP-17 prompt text>",
  "persona_id": "persona_4"
}
```
**Expected:**
- `validation_score` ≥ 85
- `tone_empathy` dimension: `passed: true`
- `compliance` dimension: `passed: true`
- `speed` dimension: `passed: true`
- `context` dimension: `passed: true`
**Priority:** P0

---

#### TC-PER-10
**Title:** persona_4 validation scores SP-18 as Poor
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Reply to an angry customer.",
  "persona_id": "persona_4"
}
```
**Expected:**
- `validation_score` ≤ 30
- `tone_empathy`: `passed: false`
- `compliance`: `passed: false`
- `issues` ≥ 4
**Priority:** P0

---

#### TC-PER-11
**Title:** Unknown persona_id defaults to persona_0
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Write a status update for the team.",
  "persona_id": "persona_99"
}
```
**Expected:**
- HTTP 200 (no crash)
- Response uses persona_0 scoring dimensions (8 dimensions including clarity, context)
- `persona_id` in response reflects persona_0 or the resolved default
**Priority:** P1

---

#### TC-PER-12
**Title:** Omitting persona_id defaults to persona_0
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Write a status update for the team."
}
```
**Expected:** HTTP 200, uses persona_0 dimensions
**Priority:** P1

---

### TC-SCR: Scoring Algorithm

---

#### TC-SCR-01
**Title:** Score is mathematically derived from dimension pass/fail
**Endpoint:** `POST /api/v1/validate`
**Input:** SP-05 (persona_1 — all 7 dimensions expected to pass)
**Expected:**
- All 7 dimensions Pass: total_weight = 18+18+18+18+14+14+14 = 114
- If all pass: base_score = 100.0
- guideline penalty ≥ 0
- final_score = 100 - penalty
- Verify: `validation_score` matches `(passed_weight / total_weight) × 100 - penalty`
**Priority:** P0

---

#### TC-SCR-02
**Title:** Score is 0 if all dimensions fail
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{ "prompt": "Do something.", "persona_id": "persona_1" }
```
**Expected:** `validation_score` ≤ 10 (near 0, accounting for any partial pass)
**Priority:** P1

---

#### TC-SCR-03
**Title:** Guideline penalty does not exceed strict_penalty_cap (15)
**Endpoint:** `POST /api/v1/validate`
**Input:** Any prompt with many missing global checks
**Expected:**
- `guideline_evaluation.penalty_applied` ≤ 15
- Even if 6 global checks fail at 3 pts each = 18 pts → must be capped at 15
**Priority:** P1

---

#### TC-SCR-04
**Title:** Score never goes below 0
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{ "prompt": "x", "persona_id": "persona_0" }
```
**Expected:** `validation_score` ≥ 0
**Priority:** P1

---

#### TC-SCR-05
**Title:** Score never exceeds 100
**Endpoint:** `POST /api/v1/validate`
**Input:** SP-01 (excellent prompt, no penalty expected)
**Expected:** `validation_score` ≤ 100
**Priority:** P1

---

#### TC-SCR-06
**Title:** Rating tiers map correctly to score ranges
**Validation:**
- score ≥ 85 → `rating` = "Excellent"
- 70 ≤ score < 85 → `rating` = "Good"
- 50 ≤ score < 70 → `rating` = "Needs Improvement"
- score < 50 → `rating` = "Poor"
**Priority:** P1
**Test:** Submit prompts expected to land in each tier and verify rating field.

---

#### TC-SCR-07
**Title:** Score on 0-10 scale in response matches 0-100 scale divided by 10
**Endpoint:** `POST /api/v1/validate`
**Expected:** If `validation_score` = 85, then `score_0_10` = 8.5 (±0.1)
**Priority:** P2

---

### TC-DIM: Dimension Breakdown

---

#### TC-DIM-01
**Title:** Response includes correct number of dimensions per persona
**Test Matrix:**

| Persona | Expected Dimension Count |
|---|---|
| persona_0 | 8 |
| persona_1 | 7 |
| persona_2 | 8 |
| persona_3 | 7 |
| persona_4 | 8 |

**Endpoint:** `POST /api/v1/validate` for each persona with any prompt
**Priority:** P0

---

#### TC-DIM-02
**Title:** Each dimension entry has required fields
**Expected schema per dimension:**
```json
{
  "dimension": "string",
  "passed": true|false,
  "weight": number,
  "score": number,
  "evidence": "string (optional)"
}
```
**Priority:** P0

---

#### TC-DIM-03
**Title:** technical_precision passes only when language+framework+version explicitly stated
**Input A (should pass):**
```json
{
  "prompt": "Using Python 3.12 and FastAPI 0.115+, implement...",
  "persona_id": "persona_1"
}
```
**Input B (should fail):**
```json
{
  "prompt": "Implement an API endpoint to validate prompts.",
  "persona_id": "persona_1"
}
```
**Expected:** technical_precision: true for A, false for B
**Priority:** P0

---

#### TC-DIM-04
**Title:** tone_empathy dimension passes only with explicit tone directive
**Input A (should pass):**
```json
{
  "prompt": "...Tone: empathetic and apologetic...",
  "persona_id": "persona_4"
}
```
**Input B (should fail):**
```json
{
  "prompt": "Write a response to an upset customer about their bill.",
  "persona_id": "persona_4"
}
```
**Expected:** tone_empathy: true for A, false for B
**Priority:** P0

---

#### TC-DIM-05
**Title:** grounding dimension passes only with explicit document reference
**Input A (should pass):**
```json
{
  "prompt": "Based on Section 4.2 of the Ziply BRD (version 2.1)...",
  "persona_id": "persona_3"
}
```
**Input B (should fail):**
```json
{
  "prompt": "Extract requirements for the data migration module.",
  "persona_id": "persona_3"
}
```
**Expected:** grounding: true for A, false for B
**Priority:** P0

---

#### TC-DIM-06
**Title:** engagement_model_awareness passes only when model named (T&M, fixed bid, etc.)
**Input A (should pass):**
```json
{
  "prompt": "...for the T&M engagement with Ziply...",
  "persona_id": "persona_2"
}
```
**Input B (should fail):**
```json
{
  "prompt": "Create a sprint report for the client project.",
  "persona_id": "persona_2"
}
```
**Expected:** engagement_model_awareness: true for A, false for B
**Priority:** P1

---

#### TC-DIM-07
**Title:** LLM does not add, rename, or remove dimensions (anti-hallucination)
**Test:** Submit SP-05 for persona_1. Verify dimension_scores contains ONLY these 7:
`technical_precision, edge_cases, testability, specificity, context, reproducibility, accuracy`
**No extra dimensions** (e.g., "clarity" belongs to persona_0 — must NOT appear for persona_1)
**Priority:** P0

---

#### TC-DIM-08
**Title:** Dimension score = weight if passed, 0 if failed
**Expected:** For each dimension in response:
- If `passed: true` → `score` = `weight`
- If `passed: false` → `score` = 0
**Priority:** P1

---

### TC-LLM: LLM Functionality & Anti-Hallucination

---

#### TC-LLM-01
**Title:** LLM evaluates only from prompt content — no inference
**Input:**
```json
{
  "prompt": "Write a Python function.",
  "persona_id": "persona_1"
}
```
**Expected:**
- `technical_precision` = false (no version in prompt)
- `edge_cases` = false (not mentioned)
- LLM must NOT pass dimensions for content not literally in the prompt
**Priority:** P0

---

#### TC-LLM-02
**Title:** Strengths reflect actual content in prompt
**Input:** SP-05 (contains Python 3.12, FastAPI, OWASP, pytest, edge cases)
**Expected:**
- Strengths mention "Python 3.12", "FastAPI", "OWASP", "pytest" or closely related terms
- Strengths do NOT mention topics absent from the prompt (e.g., "excellent CI/CD pipeline")
**Priority:** P0

---

#### TC-LLM-03
**Title:** Issues are non-duplicate across validation run
**Input:** SP-04 (poor prompt — "Create a report about our project.")
**Expected:**
- All items in `issues` array are unique (no semantic duplicates)
- E.g., "missing output format" and "no format specified" cannot both appear
**Priority:** P0

---

#### TC-LLM-04
**Title:** Maximum 6 issues returned
**Input:** SP-02 (all dimensions fail for persona_0)
**Expected:** `issues` array length ≤ 6
**Priority:** P0

---

#### TC-LLM-05
**Title:** Maximum 5 strengths returned
**Input:** SP-01 (all dimensions pass for persona_0)
**Expected:** `strengths` array length ≤ 5
**Priority:** P1

---

#### TC-LLM-06
**Title:** LLM fallback activates when provider unavailable
**Setup:** Set `GROQ_API_KEY` to an invalid value
**Input:** Any valid prompt
**Expected:**
- If `LLM_FALLBACK_ON_VALIDATE_FAILURE=true`: HTTP 200, uses static scoring, `rewrite_strategy` = "template"
- If `LLM_VALIDATE_REQUIRED=true`: HTTP 503 or error indicating provider unavailable
**Priority:** P1

---

#### TC-LLM-07
**Title:** Provider selection: auto mode prefers Groq when both configured
**Setup:** Both `GROQ_API_KEY` and `ANTHROPIC_API_KEY` set, `LLM_PROVIDER=auto`
**Expected:** Validation uses Groq as primary provider
**Priority:** P1

---

#### TC-LLM-08
**Title:** Provider selection: anthropic used when forced
**Setup:** `LLM_PROVIDER=anthropic`, valid `ANTHROPIC_API_KEY`
**Expected:** Response `provider` field = "anthropic"
**Priority:** P1

---

### TC-RPM: Reprompting / Auto-Improve

---

#### TC-RPM-01
**Title:** auto_improve=true returns non-empty improved_prompt
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{
  "prompt": "Write a project status update.",
  "persona_id": "persona_0",
  "auto_improve": true
}
```
**Expected:**
- `improved_prompt` field is non-empty string
- `improved_prompt` ≠ `original_prompt`
- `rewrite_strategy` = "llm" or "template"
**Priority:** P0

---

#### TC-RPM-02
**Title:** Improved prompt does NOT echo original prompt with heading
**Input:** Any prompt with `auto_improve: true`
**Expected:**
- `improved_prompt` does NOT start with or contain: `# Original user request`, `# Source Prompt`, `# Input Prompt`, `# Original Prompt`
- The improved_prompt is a standalone rewrite, not a concatenation
**Priority:** P0

---

#### TC-RPM-03
**Title:** Re-validating the improved prompt scores higher than the original
**Test Flow:**
1. Validate SP-02 → capture `score_1`
2. Capture `improved_prompt` from step 1
3. Validate the `improved_prompt` from step 1 as a new `prompt`
4. Capture `score_2`
**Expected:** `score_2 > score_1` (improved prompt must score higher)
**Priority:** P0

---

#### TC-RPM-04
**Title:** /improve endpoint returns same result as validate with auto_improve=true
**Test:**
1. Call `POST /api/v1/improve` with body `{ "prompt": "...", "persona_id": "persona_0" }`
2. Call `POST /api/v1/validate` with same body + `"auto_improve": true`
**Expected:** Both return an `improved_prompt` field; both score the same original prompt
**Priority:** P1

---

#### TC-RPM-05
**Title:** Improved prompt for persona_1 includes technical structure
**Input:** SP-06 with `auto_improve: true`
**Expected:** `improved_prompt` contains at least one of: language version, framework reference, edge case mention, test format, acceptance criteria
**Priority:** P1

---

#### TC-RPM-06
**Title:** Improved prompt for persona_4 includes tone directive
**Input:** SP-18 with `auto_improve: true`
**Expected:** `improved_prompt` contains tone indicator (e.g., "empathetic", "apologetic", "tone:") and compliance reference
**Priority:** P1

---

#### TC-RPM-07
**Title:** applied_guidelines and unresolved_gaps fields present in rewrite response
**Input:** Any prompt with `auto_improve: true`
**Expected:**
```json
{
  "applied_guidelines": ["string", ...],
  "unresolved_gaps": ["string", ...]
}
```
Both arrays present (may be empty if perfect rewrite)
**Priority:** P1

---

#### TC-RPM-08
**Title:** RP-01 reprompting pair: Score increases ≥ 30 points
**Test:** Validate RP-01 Round 1 then Round 2 independently
**Expected:** `score_round2 - score_round1 ≥ 30`
**Priority:** P0

---

#### TC-RPM-09
**Title:** RP-02 developer reprompting pair: All 3 key dimensions pass in Round 2
**Test:** Validate RP-02 Round 2
**Expected:** `technical_precision = true`, `edge_cases = true`, `testability = true`
**Priority:** P0

---

### TC-DED: Deduplication

---

#### TC-DED-01
**Title:** Identical issue strings are deduplicated
**Setup:** Simulate LLM returning duplicate issue: `["Missing output format", "Missing output format"]`
**Expected:** `issues` in API response contains only 1 entry, not 2
**Priority:** P0

---

#### TC-DED-02
**Title:** Semantically equivalent issues are deduplicated
**Setup:** Simulate LLM returning: `["No output format specified", "Output format is missing", "Please specify the output format"]`
**Expected:** Only 1 of the 3 appears in `issues` (they normalize to same 8-token key)
**Priority:** P0

---

#### TC-DED-03
**Title:** No suggestions returned when score is 100 and issues are empty
**Input:** An Excellent-scoring prompt (SP-01, SP-05, SP-13, SP-17)
**Expected:**
- If `validation_score` = 100 and `issues` = [] → `suggestions` = []
- No default persona suggestions injected when issues empty
**Priority:** P0

---

#### TC-DED-04
**Title:** At most 2 fallback suggestions returned when issues present but no keyword match
**Setup:** Simulate issues that have no matching keywords in suggestion_engine
**Expected:** `suggestions` array length ≤ 2 (fallback[:2] rule)
**Priority:** P1

---

#### TC-DED-05
**Title:** Keyword-matched suggestions are issue-specific, not generic defaults
**Input:** SP-06 for persona_1 (no language/framework)
**Expected:**
- Suggestions contain "[Developer] Specify language, framework, and version explicitly"
- Generic suggestions (not related to found issues) are NOT returned
**Priority:** P1

---

### TC-AUTH: Authentication & Security

---

#### TC-AUTH-01
**Title:** Protected endpoints return 401 without API key
**Endpoints to test:** `/analytics/summary`, `/mcp/validate`, `/teams/message`, `/leaderboard/weekly`, `/leadership/org-dashboard`
**Input:** No `X-API-Key` header
**Expected:** HTTP 401 for all
**Priority:** P0

---

#### TC-AUTH-02
**Title:** Protected endpoints return 401 with wrong API key
**Input:** `X-API-Key: wrong-key`
**Expected:** HTTP 401
**Priority:** P0

---

#### TC-AUTH-03
**Title:** Protected endpoints return 200 with correct API key
**Input:** `X-API-Key: infovision-dev-key`
**Expected:** HTTP 200 (or valid business-logic response, not 401/403)
**Priority:** P0

---

#### TC-AUTH-04
**Title:** /auth/resolve returns user persona info with valid API key
**Endpoint:** `POST /api/v1/auth/resolve`
**Input:**
```json
{ "email": "developer@infovision.com" }
```
With `X-API-Key: infovision-dev-key`
**Expected:** HTTP 200, response includes `persona_id`, `user_id`
**Priority:** P1

---

#### TC-AUTH-05
**Title:** /auth/map-persona assigns persona to user
**Endpoint:** `POST /api/v1/auth/map-persona`
**Input:**
```json
{ "user_id": "user123", "persona_id": "persona_1" }
```
With valid API key
**Expected:** HTTP 200, assignment confirmed
**Priority:** P1

---

#### TC-AUTH-06
**Title:** Invalid Microsoft JWT token returns 401
**Endpoint:** Any endpoint with Microsoft SSO auth
**Input:** Malformed or expired JWT
**Expected:** HTTP 401 with error detail mentioning token validation failure
**Priority:** P1

---

#### TC-AUTH-07
**Title:** Microsoft tenant mismatch returns 401
**Setup:** Configure expected tenant ID as `tenant_A`, send token with `tenant_B`
**Expected:** HTTP 401 with tenant mismatch error detail
**Priority:** P1

---

#### TC-AUTH-08
**Title:** Prompt content is masked in leadership endpoints
**Endpoint:** `GET /api/v1/leadership/org-dashboard`
**Expected:** Response does NOT contain raw `original_prompt` values.
Any prompt references must show `[REDACTED]` per data governance rules.
**Priority:** P0
**Regulation reference:** data_strategy_business_rules_source_truth.json — `leadership_endpoints_mask_prompt_fields: true`

---

### TC-DB: Data Persistence

---

#### TC-DB-01
**Title:** Database health check passes
**Endpoint:** `GET /api/v1/health/db`
**Input:** `X-API-Key: infovision-dev-key`
**Expected:** HTTP 200 with connection status and backend type (mongodb or sqlite)
**Priority:** P0

---

#### TC-DB-02
**Title:** Validation record is persisted after POST /validate
**Test Flow:**
1. Call `POST /api/v1/validate` with SP-01
2. Call `GET /api/v1/history?limit=1`
**Expected:** The most recent history record matches the validation just run (same prompt text, score, persona_id)
**Priority:** P0

---

#### TC-DB-03
**Title:** Dimension scores are persisted for each validation
**Test Flow:**
1. Validate SP-05 for persona_1
2. Query history or dimension record
**Expected:** dimension_scores stored: 7 entries matching persona_1 dimensions
**Priority:** P1

---

#### TC-DB-04
**Title:** Prompt rewrite is persisted when auto_improve=true
**Test Flow:**
1. Validate SP-02 with `auto_improve: true`
2. Query prompt_rewrites or history
**Expected:** Record contains `original_prompt`, `improved_prompt`, `rewrite_strategy`, `applied_guidelines`
**Priority:** P1

---

#### TC-DB-05
**Title:** Channel usage is tracked correctly for API channel
**Test Flow:**
1. Validate any prompt via `POST /api/v1/validate`
2. Query channel_usage
**Expected:** Record shows `delivery_channel = "api"` or `"API"`
**Priority:** P1

---

#### TC-DB-06
**Title:** History endpoint returns records in reverse-chronological order
**Endpoint:** `GET /api/v1/history?limit=5`
**Expected:** Records sorted newest first by `created_at`
**Priority:** P2

---

#### TC-DB-07
**Title:** PII fields are stored per data governance classification
**Data governance rule:** `original_prompt` and `corrected_prompt` are `pii_high`
**Expected:** These fields stored in persistence layer with appropriate metadata
**Note:** Masking must apply when exposed through leadership endpoints
**Priority:** P1

---

### TC-MCP: MCP Channel

---

#### TC-MCP-01
**Title:** MCP validate endpoint requires API key
**Endpoint:** `POST /api/v1/mcp/validate`
**Input:** No API key
**Expected:** HTTP 401
**Priority:** P0

---

#### TC-MCP-02
**Title:** MCP validate returns valid validation response
**Endpoint:** `POST /api/v1/mcp/validate`
**Input:**
```json
{
  "prompt": "<SP-05 text>",
  "persona_id": "persona_1"
}
```
With `X-API-Key: infovision-dev-key`
**Expected:** HTTP 200, same response schema as `/validate`, `delivery_channel` = "mcp" or "MCP"
**Priority:** P0

---

#### TC-MCP-03
**Title:** MCP channel persists channel=MCP in usage records
**Test Flow:**
1. Call MCP validate endpoint
2. Check channel_usage records
**Expected:** Entry with `delivery_channel = "MCP"` created
**Priority:** P1

---

### TC-TMS: Microsoft Teams Channel

---

#### TC-TMS-01
**Title:** Teams message endpoint requires API key
**Endpoint:** `POST /api/v1/teams/message`
**Input:** No API key
**Expected:** HTTP 401
**Priority:** P0

---

#### TC-TMS-02
**Title:** Teams message endpoint requires Content-Type: application/json
**Input:** Correct API key, body with text/plain Content-Type
**Expected:** HTTP 415 or 422
**Priority:** P1

---

#### TC-TMS-03
**Title:** Teams endpoint processes message and returns validation response
**Input:**
```json
{
  "type": "message",
  "text": "<SP-01 prompt text>",
  "from": { "id": "user@infovision.com" }
}
```
With valid API key
**Expected:** HTTP 200 with validation score and feedback for Teams
**Priority:** P1

---

#### TC-TMS-04
**Title:** Teams channel persists channel=teams in usage records
**Test Flow:**
1. Call Teams message endpoint
2. Check channel_usage
**Expected:** Record with `delivery_channel = "teams"` or `"TEAMS"`
**Priority:** P1

---

### TC-ANA: Analytics & Leadership

---

#### TC-ANA-01
**Title:** Analytics summary returns usage metrics
**Endpoint:** `GET /api/v1/analytics/summary`
**Input:** Valid API key
**Expected:**
- HTTP 200
- Response includes: `total_validations`, `average_score`, `top_persona`
**Priority:** P1

---

#### TC-ANA-02
**Title:** Weekly leaderboard returns ranked users
**Endpoint:** `GET /api/v1/leaderboard/weekly`
**Input:** Valid API key
**Expected:** Array of user entries ranked by score descending. Fields: `user_id`, `score`, `rank`
**Priority:** P2

---

#### TC-ANA-03
**Title:** Org dashboard masks PII prompt fields
**Endpoint:** `GET /api/v1/leadership/org-dashboard`
**Input:** Valid API key
**Expected:**
- No `original_prompt` or `corrected_prompt` raw values
- Prompt fields show `[REDACTED]`
- Aggregate metrics (avg_score, team_counts) visible
**Priority:** P0

---

#### TC-ANA-04
**Title:** Team report returns team-specific metrics
**Endpoint:** `GET /api/v1/leadership/team-report/{team_id}`
**Input:** Valid API key, `team_id = "team_infovision"`
**Expected:** HTTP 200 with team-level average score, persona distribution, improvement trend
**Priority:** P2

---

#### TC-ANA-05
**Title:** Weekly intelligence refresh returns success
**Endpoint:** `POST /api/v1/aggregation/weekly/refresh`
**Input:** Valid API key
**Expected:** HTTP 200, no errors. Aggregation pipeline completed indicator present.
**Priority:** P2

---

### TC-EDG: Edge Cases & Error Handling

---

#### TC-EDG-01
**Title:** Empty prompt returns HTTP 400
**Endpoint:** `POST /api/v1/validate`
**Input:**
```json
{ "prompt": "", "persona_id": "persona_0" }
```
**Expected:** HTTP 400 or 422, error message indicating empty prompt not allowed
**Priority:** P0

---

#### TC-EDG-02
**Title:** Whitespace-only prompt returns HTTP 400
**Input:**
```json
{ "prompt": "   ", "persona_id": "persona_0" }
```
**Expected:** HTTP 400 or 422
**Priority:** P1

---

#### TC-EDG-03
**Title:** Prompt exceeding maximum length returns HTTP 422
**Input:** Prompt string of 2001+ characters
**Expected:** HTTP 422 with field validation error
**Priority:** P1

---

#### TC-EDG-04
**Title:** Malformed JSON body returns HTTP 422
**Input:** `{"prompt": "test"` (missing closing brace)
**Expected:** HTTP 422
**Priority:** P1

---

#### TC-EDG-05
**Title:** Non-string prompt field returns HTTP 422
**Input:**
```json
{ "prompt": 12345, "persona_id": "persona_0" }
```
**Expected:** HTTP 422
**Priority:** P1

---

#### TC-EDG-06
**Title:** Unicode prompt is handled without 500 error
**Input:**
```json
{
  "prompt": "كتابة تقرير حالة المشروع للعميل في الربع الأول 2026.",
  "persona_id": "persona_0"
}
```
**Expected:** HTTP 200, valid JSON response with score
**Priority:** P1

---

#### TC-EDG-07
**Title:** Emoji in prompt is handled without 500 error
**Input:**
```json
{
  "prompt": "Write a 🎯 status update 📊 for Q1 2026 including 🚀 achievements.",
  "persona_id": "persona_0"
}
```
**Expected:** HTTP 200, valid JSON response
**Priority:** P1

---

#### TC-EDG-08
**Title:** Very long persona_id string does not crash server
**Input:**
```json
{
  "prompt": "Write a report.",
  "persona_id": "persona_" + "x" * 500
}
```
**Expected:** HTTP 200 (defaults to persona_0) or HTTP 422 (input validation)
**Priority:** P2

---

#### TC-EDG-09
**Title:** Concurrent validation requests do not interfere with each other
**Test:** Send 5 simultaneous POST /validate requests, each with different personas
**Expected:** All 5 return HTTP 200 with different persona-appropriate dimension breakdowns.
No cross-contamination of persona scoring.
**Priority:** P1

---

#### TC-EDG-10
**Title:** Validation history limit parameter is respected
**Endpoint:** `GET /api/v1/history?limit=3`
**Expected:** At most 3 records returned regardless of total history size
**Priority:** P2

---

#### TC-EDG-11
**Title:** Score field in response is always numeric
**Input:** Any valid prompt
**Expected:** `validation_score` is a `number` (float or int), never a string or null
**Priority:** P0

---

#### TC-EDG-12
**Title:** SCORE_OUT_OF_RANGE alert condition: score outside 0–100
**Data governance rule:** Alert `SCORE_OUT_OF_RANGE` severity P1 must fire
**Validation:** No response ever returns `validation_score < 0` or `> 100`
**Priority:** P0

---

## TEST EXECUTION SUMMARY

### Priority Distribution

| Priority | Count | Description |
|---|---|---|
| P0 | 32 | Critical — must pass, blocks release |
| P1 | 28 | High — must pass for full feature coverage |
| P2 | 8 | Medium — regression / edge coverage |
| **Total** | **68** | **Full test suite** |

---

### Coverage Matrix

| Area | Test IDs | Count |
|---|---|---|
| API Health & Config | TC-API-01 to TC-API-05 | 5 |
| Persona Routing | TC-PER-01 to TC-PER-12 | 12 |
| Scoring Algorithm | TC-SCR-01 to TC-SCR-07 | 7 |
| Dimension Breakdown | TC-DIM-01 to TC-DIM-08 | 8 |
| LLM Functionality | TC-LLM-01 to TC-LLM-08 | 8 |
| Reprompting | TC-RPM-01 to TC-RPM-09 | 9 |
| Deduplication | TC-DED-01 to TC-DED-05 | 5 |
| Authentication | TC-AUTH-01 to TC-AUTH-08 | 8 |
| Data Persistence | TC-DB-01 to TC-DB-07 | 7 |
| MCP Channel | TC-MCP-01 to TC-MCP-03 | 3 |
| Teams Channel | TC-TMS-01 to TC-TMS-04 | 4 |
| Analytics/Leadership | TC-ANA-01 to TC-ANA-05 | 5 |
| Edge Cases | TC-EDG-01 to TC-EDG-12 | 12 |
| **Total** | | **93** |

---

### Exit Criteria (Release Gate)

- [ ] All P0 test cases pass (32/32)
- [ ] All P1 test cases pass (28/28)
- [ ] All 5 personas return correct dimension count
- [ ] No dimension hallucination (TC-DIM-07 passes)
- [ ] No PII leakage through leadership endpoints (TC-AUTH-08, TC-ANA-03 pass)
- [ ] Reprompting always increases score (TC-RPM-03 passes)
- [ ] Score always in range 0–100 (TC-SCR-04, TC-SCR-05, TC-EDG-12 pass)
- [ ] Deduplication prevents duplicate issues/suggestions (TC-DED-01, TC-DED-02, TC-DED-03 pass)
- [ ] LLM fallback does not break API (TC-LLM-06 passes)
- [ ] Unicode and emoji inputs handled (TC-EDG-06, TC-EDG-07 pass)

---

*Document generated: 2026-04-01 | Infovision CoE AI/GenAI Practice*
