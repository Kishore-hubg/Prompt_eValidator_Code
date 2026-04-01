# Claude prompt to extend this MVP

Use this prompt in Claude when you want to expand the MVP into a more enterprise-grade product.

```text
You are a senior full-stack engineer. Extend the attached Prompt Validator MVP without changing its core API contract.

Goals:
1. Keep the existing persona-aware validation engine.
2. Replace the rule-based improver with an LLM-backed improver behind a feature flag.
3. Add OAuth-ready user model and persona mapping.
4. Add Teams bot integration scaffolding.
5. Add MCP tool wrapper.
6. Add analytics dashboard endpoints.
7. Keep backward compatibility with the existing FastAPI routes and response schema.

Constraints:
- Python 3.11
- FastAPI backend
- SQLite for local dev, easy path to Postgres
- Frontend can remain simple and responsive
- Keep code modular and avoid over-engineering
- Do not break the existing API routes

Deliverables:
- Updated backend code
- Updated frontend
- Database migrations
- README changes
- Sample environment file
- Test cases
```
