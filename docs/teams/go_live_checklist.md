# Teams + SSO Go-Live Checklist

Use this checklist to close all prerequisites before broad rollout.

## Configuration

- [ ] Copy `.env.example` to `.env` and fill all backend + bot variables.
- [ ] Set `PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft`.
- [ ] Set `PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=false` in production.
- [ ] Set `MICROSOFT_TENANT_ID` to your single-tenant ID.
- [ ] Set `MICROSOFT_CLIENT_ID` to your Entra app/client ID.
- [ ] Ensure `BOT_APP_ID` and `BOT_APP_PASSWORD` are valid Azure Bot credentials.
- [ ] Set `TEAMS_OAUTH_CONNECTION_NAME` and create the same named OAuth connection in Azure Bot.

## Azure Setup

- [ ] Create Azure Bot resource and set messaging endpoint to `https://<host>/api/messages`.
- [ ] Confirm bot endpoint is publicly reachable over HTTPS.
- [ ] Configure Teams channel for the Azure Bot.
- [ ] Create Teams app package from `teams_app_manifest/`.
- [ ] Upload/install app in test tenant.

## Runtime Verification

- [ ] Backend health check passes: `GET /api/v1/health`.
- [ ] DB health check passes: `GET /api/v1/health/db`.
- [ ] Bot health check passes: `GET /health` on bot service.
- [ ] Teams message returns score, issues, suggestions, and improved prompt.
- [ ] `/api/v1/teams/message` stores records with `channel=teams`.
- [ ] Microsoft token resolves identity and persona mapping correctly.

## Security

- [ ] Rotate any accidental secrets in repository history and environment files.
- [ ] Store all secrets in secure vault (Azure Key Vault or equivalent).
- [ ] Restrict CORS origins for production frontend hosts.
- [ ] Confirm `x-api-key` is never logged in plaintext.

## Release

- [ ] Run pilot with selected users (at least one from each persona).
- [ ] Capture defects and fix critical issues.
- [ ] Obtain PM/security approval for org-wide rollout.
