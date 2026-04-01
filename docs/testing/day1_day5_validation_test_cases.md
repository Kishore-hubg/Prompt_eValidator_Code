# Day 1 to Day 5 Validation Test Cases

This document is the executable test-case checklist for the phased rollout.
Mark each case as Pass/Fail with evidence (response payload, logs, DB snapshot, screenshots).

## Scope

- Day 1: Persona APIs and scoring flow
- Day 2: Data strategy and persistence validations
- Day 3: Authentication and persona mapping
- Day 4: Hosting readiness and MCP path
- Day 5: Microsoft Teams bot integration

## Common Preconditions

- Python dependencies installed: `pip install -r requirements.txt`
- Environment variables configured in `.env`
- API service running on `http://127.0.0.1:8000`
- For Day 5 tests, Teams bot bridge running on `http://127.0.0.1:3978`
- API key available from `.env` as `PROMPT_VALIDATOR_API_KEY`

---

## Day 1 - Complete API development for five personas

### D1-TC-01 Health endpoint
- **Objective:** Confirm service uptime.
- **Request:** `GET /api/v1/health`
- **Expected:** HTTP 200 and `{"status":"ok"}`.

### D1-TC-02 Personas endpoint returns all personas
- **Objective:** Confirm persona catalog availability.
- **Request:** `GET /api/v1/personas`
- **Expected:** HTTP 200 and list includes `persona_0`, `persona_1`, `persona_2`, `persona_3`, `persona_4`.

### D1-TC-03 Validate endpoint for persona_0
- **Objective:** Confirm baseline validation flow works.
- **Request:** `POST /api/v1/validate` with `persona_id=persona_0`.
- **Expected:** HTTP 200 with `score`, `rating`, `issues`, `suggestions`, `improved_prompt`, and `dimension_scores`.

### D1-TC-04 Validate endpoint for persona_1
- **Objective:** Confirm persona-specific scoring execution.
- **Request:** `POST /api/v1/validate` with `persona_id=persona_1`.
- **Expected:** HTTP 200 and `persona_id` in response equals `persona_1`.

### D1-TC-05 Validate endpoint for persona_2
- **Objective:** Confirm persona-specific scoring execution.
- **Request:** `POST /api/v1/validate` with `persona_id=persona_2`.
- **Expected:** HTTP 200 and `persona_id` in response equals `persona_2`.

### D1-TC-06 Validate endpoint for persona_3
- **Objective:** Confirm persona-specific scoring execution.
- **Request:** `POST /api/v1/validate` with `persona_id=persona_3`.
- **Expected:** HTTP 200 and `persona_id` in response equals `persona_3`.

### D1-TC-07 Validate endpoint for persona_4
- **Objective:** Confirm persona-specific scoring execution.
- **Request:** `POST /api/v1/validate` with `persona_id=persona_4`.
- **Expected:** HTTP 200 and `persona_id` in response equals `persona_4`.

### D1-TC-08 Improve endpoint auto-improves prompt
- **Objective:** Verify improve-only flow.
- **Request:** `POST /api/v1/improve` with valid prompt payload.
- **Expected:** HTTP 200 and `improved_prompt` is present/non-empty.

### D1-TC-09 Input validation for empty prompt
- **Objective:** Ensure request validation behavior is correct.
- **Request:** `POST /api/v1/validate` with `prompt_text=""`.
- **Expected:** HTTP 400 or schema validation error; no server crash.

---

## Day 2 - Data strategy and persistence implementation

### D2-TC-01 Database connectivity health
- **Objective:** Validate persistence connectivity.
- **Request:** `GET /api/v1/health/db`
- **Expected:** HTTP 200 with `backend` = `mongodb` or `sqlite`, and `status` = `ok`.

### D2-TC-02 Validation persistence record creation
- **Objective:** Confirm each validation is stored.
- **Steps:** Call `POST /api/v1/validate`, then `GET /api/v1/history?limit=20`.
- **Expected:** New history item exists with matching prompt text and score.

### D2-TC-03 Dimension score persistence
- **Objective:** Ensure dimension-level data is captured.
- **Steps:** Call `POST /api/v1/validate`, then `GET /api/v1/analytics/summary` with API key.
- **Expected:** `tables.dimension_scores` count increases.

### D2-TC-04 Channel usage tracking
- **Objective:** Confirm channel usage events are recorded.
- **Steps:** Call `POST /api/v1/validate` with `channel="web"` and `channel="mcp"` (via MCP endpoint), then read analytics summary.
- **Expected:** `validations_by_channel` includes used channels.

### D2-TC-05 Prompt rewrite persistence
- **Objective:** Confirm improved prompt artifacts are saved.
- **Steps:** Run validation with `auto_improve=true`, then fetch history/analytics.
- **Expected:** `tables.prompt_rewrites` count increases.

### D2-TC-06 Feedback event persistence
- **Objective:** Ensure feedback metadata is captured.
- **Steps:** Run validation and read analytics summary.
- **Expected:** `tables.feedback_events` count increases.

---

## Day 3 - Refinement, authentication setup, persona mapping

### D3-TC-01 API key enforcement on protected endpoints
- **Objective:** Confirm security baseline.
- **Request:** `POST /api/v1/auth/resolve` without `x-api-key`.
- **Expected:** HTTP 401.

### D3-TC-02 API key acceptance on protected endpoints
- **Objective:** Confirm valid key enables access path.
- **Request:** `POST /api/v1/auth/map-persona` with valid `x-api-key`.
- **Expected:** HTTP 200 with `mapped=true`.

### D3-TC-03 Persona mapping update and retrieval behavior
- **Objective:** Verify user-to-persona mapping lifecycle.
- **Steps:** Map `email` to `persona_3`; call `POST /api/v1/validate` with same email and `persona_id=persona_0`.
- **Expected:** Response resolves to mapped persona (`persona_3`).

### D3-TC-04 Microsoft token validation path rejects invalid token
- **Objective:** Confirm JWT validation path is active.
- **Request:** `POST /api/v1/auth/resolve` with malformed/invalid token and valid API key.
- **Expected:** HTTP 401 with invalid token message.

### D3-TC-05 Microsoft token email extraction behavior
- **Objective:** Verify user identity resolution rules.
- **Request:** `POST /api/v1/auth/resolve` with token containing `email`/`preferred_username` or with `email_hint`.
- **Expected:** Response includes resolved `email`, `display_name`, and `persona_id`.

### D3-TC-06 Analytics endpoint protection and payload
- **Objective:** Validate final API + data refinement checks.
- **Request:** `GET /api/v1/analytics/summary` with and without API key.
- **Expected:** without key -> 401; with key -> 200 + summary payload.

---

## Day 4 - Hosting + MCP implementation

### D4-TC-01 Local runtime smoke check
- **Objective:** Confirm hostable API behavior.
- **Steps:** Start app using `uvicorn app.main:app --reload`; call health endpoints.
- **Expected:** Startup success and health endpoints return 200.

### D4-TC-02 Deployment configuration review
- **Objective:** Validate deployment prerequisites.
- **Checks:** `pyproject.toml` entrypoint and env var coverage for DB/API key.
- **Expected:** Hosting config supports FastAPI startup and protected endpoints.

### D4-TC-03 MCP validate endpoint security
- **Objective:** Confirm MCP wrapper endpoint is protected.
- **Request:** `POST /api/v1/mcp/validate` without API key.
- **Expected:** HTTP 401.

### D4-TC-04 MCP validate functional response
- **Objective:** Confirm MCP route uses core engine and persists output.
- **Request:** `POST /api/v1/mcp/validate` with API key and valid prompt.
- **Expected:** HTTP 200 with standard validation payload fields.

### D4-TC-05 MCP channel persistence
- **Objective:** Ensure MCP invocations are tagged in persistence.
- **Steps:** Run MCP validation; read analytics summary/history.
- **Expected:** Channel usage includes `mcp`.

---

## Day 5 - Microsoft Teams integration via bot

### D5-TC-01 Teams bot health endpoint
- **Objective:** Confirm bot service is alive.
- **Request:** `GET http://127.0.0.1:3978/health`
- **Expected:** HTTP 200 and status payload.

### D5-TC-02 Teams bot content-type enforcement
- **Objective:** Validate endpoint input gate.
- **Request:** `POST /api/messages` with non-JSON content type.
- **Expected:** HTTP 415.

### D5-TC-03 Teams backend endpoint security
- **Objective:** Ensure teams adapter API is protected.
- **Request:** `POST /api/v1/teams/message` without `x-api-key`.
- **Expected:** HTTP 401.

### D5-TC-04 Teams backend functional response
- **Objective:** Validate API-level Teams flow.
- **Request:** `POST /api/v1/teams/message` with valid key and prompt text.
- **Expected:** HTTP 200 with score/rating/issues/suggestions/improved_prompt.

### D5-TC-05 Teams channel persistence
- **Objective:** Confirm org channel usage is recorded.
- **Steps:** Run D5-TC-04, then query history.
- **Expected:** New record exists with `channel=teams`.

### D5-TC-06 Bot Framework auth enforcement
- **Objective:** Confirm bot endpoint requires valid auth token.
- **Request:** `POST /api/messages` unsigned activity.
- **Expected:** Unauthorized/authentication failure path (no silent acceptance).

### D5-TC-07 End-to-end Teams signed activity
- **Objective:** Final org-ready E2E validation.
- **Steps:** Use Bot Framework Emulator or real Teams channel with valid bot credentials and messaging endpoint.
- **Expected:** User message in Teams returns scored response; backend records channel `teams`.

---

## Exit Criteria (Release Sign-off)

- All P0/P1 test cases pass for Day 1 through Day 5.
- No critical security gaps (`x-api-key`, token validation, bot auth) remain open.
- Persistence evidence exists for validations, dimensions, channel usage, and persona assignments.
- Teams signed-message flow passes in tenant-level test environment.

## Suggested Evidence Template

For each test case capture:

- Test Case ID
- Date/Tester
- Request payload
- Response status/body
- Log snippet
- Data proof (`history` or `analytics` extract)
- Final result: Pass/Fail
