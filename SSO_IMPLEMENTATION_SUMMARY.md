# WebUI SSO Implementation Summary

## Status: ✅ Complete (Ready for Configuration & Testing)

WebUI now supports Microsoft Entra ID (Azure AD) Single Sign-On via MSAL.js.

---

## What Was Implemented

### Backend (Python/FastAPI)

**1. Auth Middleware** (`app/middleware/auth_sso.py`)
- Intercepts protected routes
- Validates JWT tokens from MSAL.js
- Extracts email + persona_id
- Returns 401 if token invalid
- Exempts endpoints with their own auth (Slack, Teams, MCP, admin)

**2. Main App Update** (`app/main.py`)
- Registers SSO middleware conditionally
- Only enabled when `OAUTH_PROVIDER_NAME=microsoft`
- Logs status on startup
- Falls back to mock OAuth if not configured

**3. Existing OAuth Support** (already present)
- `/api/v1/auth/resolve` — validates Microsoft tokens
- `/api/v1/auth/map-persona` — maps user to persona
- Microsoft JWKS validation
- JWT signature verification

### Frontend (JavaScript/HTML)

**1. Auth Module** (`frontend/src/auth.js`)
- MSAL.js wrapper class
- Token acquisition (silent + interactive flows)
- Backend user resolution
- Auto-refresh on expiry
- Injects `Authorization: Bearer` header into API calls

**2. HTML Updates** (`frontend/index.html`)
- MSAL.js 2.30.0 CDN link
- SSO login overlay (shows when not authenticated)
- "Sign in with Microsoft" button
- Auth initialization script
- Auto-hides main app until authenticated
- Graceful fallback to mock OAuth mode

**3. Auth Init Script** (embedded in HTML)
- Detects if user already authenticated
- Shows login overlay if needed
- Handles redirect callback flow
- Wraps window.fetch to inject auth header
- Error handling with user messages

---

## Files Created

```
backend/
  app/middleware/auth_sso.py               ← SSO JWT validation middleware
  
frontend/
  src/auth.js                               ← MSAL.js wrapper module
  index.html                                ← Updated with login UI + auth init
  
docs/
  SSO_SETUP.md                              ← Complete setup guide
  SSO_IMPLEMENTATION_SUMMARY.md             ← This file
  .env.sso.example                          ← Example environment config
```

---

## Architecture Flow

```
┌─────────────────────┐
│   User Browser      │
│  (MSAL.js loaded)   │
└──────────┬──────────┘
           │
           ├─→ [SSO Overlay Shown]
           │   User clicks "Sign in with Microsoft"
           │
           ├─→ [Redirect to Microsoft Entra ID]
           │   User enters credentials
           │
           ├─→ [Redirect to /auth/callback]
           │   MSAL stores tokens in sessionStorage
           │
           ├─→ [Call /api/v1/auth/resolve]
           │   POST {access_token, email_hint}
           │   X-API-Key: {api_key}
           │
           ├─→ [Backend Validates Token]
           │   SSO_AuthMiddleware intercepts
           │   Verifies JWT signature via MICROSOFT_JWKS_URL
           │   Extracts email + resolves persona
           │
           └─→ [Authenticated]
               Main app shown
               All subsequent API calls include Authorization header
               Tokens auto-refresh on expiry
```

---

## Configuration Required

### Minimum Setup (Production)

1. **Register Azure App**
   - Go to https://portal.azure.com → Entra ID → App Registrations
   - Create "Prompt Validator WebUI"
   - Type: Single-page application (SPA)
   - Redirect URIs:
     - `https://your-domain.com/auth/callback`
     - `https://your-domain.com/`
   - API Permissions: `openid`, `profile`, `email` (default)
   - Copy Client ID

2. **Set Environment Variables**
   ```bash
   PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft
   MICROSOFT_CLIENT_ID={app_client_id}
   MICROSOFT_TENANT_ID={your_tenant_id or domain}
   MICROSOFT_ALLOWED_AUDIENCES={client_id}
   ```

3. **Restart Backend**
   - Logs will show: `SSO Auth Middleware enabled for WebUI routes`

### Development Setup (Testing)

```bash
# Use mock OAuth (no Azure setup needed)
PROMPT_VALIDATOR_OAUTH_PROVIDER=mock-oauth
PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=true

# Or add ?mock=true to browser URL
# http://localhost:3000/?mock=true
```

---

## Testing Checklist

### Unit Test: Auth Module

```javascript
// In browser console
await window.promptValidatorAuth.init();
// → Should return true if already authenticated, false if not

window.promptValidatorAuth.getUser();
// → Should return {email, name, oid}

await window.promptValidatorAuth.getAccessToken();
// → Should return valid JWT token
```

### Integration Test: Login Flow

1. Open WebUI (not authenticated)
2. See SSO login overlay
3. Click "Sign in with Microsoft"
4. Redirected to login.microsoftonline.com
5. Enter credentials
6. Redirected back → main app shown
7. Open DevTools → Network tab
8. Any API call should have `Authorization: Bearer {token}` header

### API Test: Direct Call

```bash
# Get token from browser console
curl -X POST https://your-domain.com/api/v1/validate \
  -H "Authorization: Bearer {token_from_console}" \
  -H "Content-Type: application/json" \
  -d '{"prompt_text":"test","persona_id":"persona_0","auto_improve":false}'

# Should succeed (200 OK)
# Without token should get 401 Unauthorized
```

---

## What's NOT Implemented (Future)

- [ ] Token refresh in background
- [ ] SSO logout to Azure
- [ ] Multi-factor authentication
- [ ] Per-persona RBAC policies
- [ ] Tenant isolation (multi-tenant)
- [ ] User profile synchronization

---

## Deployment Readiness

### Before Production Deploy

- [ ] Register Azure app in your tenant
- [ ] Set `MICROSOFT_CLIENT_ID` env var
- [ ] Set `MICROSOFT_TENANT_ID` env var
- [ ] Update Azure app reply URLs to match domain
- [ ] Test login flow end-to-end on staging
- [ ] Verify backend logs show "SSO Auth Middleware enabled"
- [ ] Test WebUI routes return 401 without token
- [ ] Test Slack/Teams/MCP still work (should not require SSO)

### Rollback Plan

If SSO breaks production:
1. Set `PROMPT_VALIDATOR_OAUTH_PROVIDER=mock-oauth`
2. Restart backend
3. WebUI will use mock OAuth (no real login required)
4. Slack/Teams/MCP unaffected (have own auth)

---

## Security Notes

✅ **Implemented**
- MSAL.js token storage in sessionStorage (cleared on tab close)
- JWT signature validation via MICROSOFT_JWKS_URL
- Token expiry checks
- Bearer token injection only to this backend

⚠️ **TODO**
- Restrict CORS to your domain only (currently `allow_origins=["*"]`)
- HTTPS required in production (MSAL.js enforces this)
- Implement token refresh for long sessions
- Add rate limiting on /auth/resolve endpoint

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "MSAL.js not loaded" | CDN unreachable | Check browser console, use CDN mirror |
| "Missing Authorization header" | Browser not authenticated | Reload page, check SessionStorage has tokens |
| "Invalid Microsoft token" | Token expired or wrong issuer | Clear SessionStorage, login again |
| "Backend resolve failed" | MICROSOFT_CLIENT_ID not set | Set env var, check JWKS_URL reachable |
| "Blank page after login" | Auth init script didn't run | Check script errors in DevTools console |

---

## Next Steps

1. **Immediate**: Copy `.env.sso.example` to `.env`, update with your Azure app credentials
2. **Testing**: Run with mock OAuth first, verify login flow works
3. **Azure Setup**: Register app, update reply URLs
4. **Staging Deploy**: Deploy with real Azure credentials
5. **QA**: Full end-to-end testing with Microsoft login
6. **Production**: Deploy with confidence ✅

---

## Files to Review Before Deploying

- `SSO_SETUP.md` — Detailed setup guide
- `app/middleware/auth_sso.py` — Middleware implementation
- `frontend/src/auth.js` — Client-side auth module
- `.env.sso.example` — Configuration template

---

**Implementation Date**: 2026-05-05
**Status**: Ready for Configuration
**Estimated Time to Production**: 3-5 days (including Azure registration + QA)
