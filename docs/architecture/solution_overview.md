# Recommended Architecture

## Core principle
One backend engine serves all personas. Channel-specific layers should call the same scoring and autofix core.

## Persona model
- Persona 0: universal baseline
- Personas 1-4: role-specific overlays

## Evaluation stack
1. Common 95% checks
2. Persona-specific overlays
3. Score calculation
4. Actionable feedback generation
5. Autofix generation
6. Logging and analytics

## Suggested API set
- POST /api/v1/validate
- POST /api/v1/improve
- POST /api/v1/validate-and-improve
- GET /api/v1/history
- GET /api/v1/personas
- POST /api/v1/auth/map-persona
- POST /api/v1/mcp/validate
- POST /api/v1/teams/message
