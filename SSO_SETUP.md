# WebUI SSO Setup Guide

Implements Microsoft Entra ID (Azure AD) Single Sign-On for Prompt Validator WebUI via MSAL.js.

## Architecture

```
User Browser (MSAL.js)
    ↓
    ├─→ Microsoft Entra ID Login
    ├─→ Get ID Token + Access Token
    └─→ Send token to /api/v1/auth/resolve
         ↓
    Backend (FastAPI)
         ├─→ Validate JWT signature + claims
         ├─→ Extract email + resolve persona
         └─→ Return user profile + persona_id
```

## Prerequisites

1. **Azure App Registration** in Microsoft Entra ID
   - Single-page application (SPA) platform
   - Redirect URI: `https://{your-domain}/auth/callback` and `http://localhost:3000/auth/callback` (dev)
   - API permissions: `openid`, `profile`, `email` scopes
   - Client ID (save this)

2. **Environment Variables** configured on backend

## Backend Setup

### 1. Set Environment Variables

```bash
# Required for SSO
PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft
MICROSOFT_TENANT_ID=your-tenant-id  # e.g., "infovision.com" or UUID
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_ALLOWED_AUDIENCES=your-client-id,other-audiences
MICROSOFT_ISSUER=https://login.microsoftonline.com/{tenant_id}/v2.0
MICROSOFT_JWKS_URL=https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
```

**Example for Infovision:**
```bash
PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft
MICROSOFT_TENANT_ID=infovision.com
MICROSOFT_CLIENT_ID=12345678-1234-1234-1234-123456789012
MICROSOFT_ALLOWED_AUDIENCES=12345678-1234-1234-1234-123456789012
```

### 2. Update .env file

Add to `.env`:
```
PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft
MICROSOFT_TENANT_ID=infovision.com
MICROSOFT_CLIENT_ID={YOUR_CLIENT_ID}
MICROSOFT_ALLOWED_AUDIENCES={YOUR_CLIENT_ID}
```

### 3. Restart Backend

```bash
# Backend automatically enables SSO middleware when OAUTH_PROVIDER=microsoft
# Logs will show: "SSO Auth Middleware enabled for WebUI routes"
```

## Frontend Setup

### 1. Environment Configuration

Create `.env.local` in project root or pass via window config:

```javascript
// In HTML or via script
window.AUTH_CONFIG = {
  clientId: "your-client-id",
  authority: "https://login.microsoftonline.com/infovision.com",
  redirectUri: "https://your-domain.com/auth/callback"
};
```

Or use localStorage:
```javascript
localStorage.setItem("MSAL_CLIENT_ID", "your-client-id");
localStorage.setItem("MSAL_AUTHORITY", "https://login.microsoftonline.com/infovision.com");
```

### 2. Auth JS Module

Frontend includes `/src/auth.js` which:
- Initializes MSAL.js
- Handles login/logout
- Manages access tokens
- Injects `Authorization: Bearer {token}` header into all API calls

### 3. Login UI

HTML includes SSO login overlay that:
- Shows if user not authenticated
- Provides "Sign in with Microsoft" button
- Handles redirect flow automatically
- Shows error messages on failure

## Deployment Checklist

### Production Setup

- [ ] Register Azure app in Microsoft Entra ID
- [ ] Set `MICROSOFT_CLIENT_ID` env var
- [ ] Set `MICROSOFT_TENANT_ID` env var
- [ ] Update Azure app reply URLs:
  - `https://{domain}/auth/callback`
  - `https://{domain}/`
- [ ] Set `PROMPT_VALIDATOR_OAUTH_PROVIDER=microsoft`
- [ ] Test login flow end-to-end
- [ ] Check backend logs for "SSO Auth Middleware enabled"

### Development Setup

```bash
# Use mock OAuth for local testing
export PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=true
export PROMPT_VALIDATOR_OAUTH_PROVIDER=mock-oauth

# Or add ?mock=true to browser URL
# http://localhost:3000/?mock=true
```

## Testing

### Manual Test Flow

1. Open WebUI: `https://your-domain.com`
2. See SSO login overlay
3. Click "Sign in with Microsoft"
4. Redirect to `https://login.microsoftonline.com/...`
5. Enter credentials
6. Redirect back to `/auth/callback`
7. MSAL stores tokens
8. WebUI shows main application
9. API calls include `Authorization: Bearer {token}`

### API Test (curl)

```bash
# Get token from browser console:
# token = await window.promptValidatorAuth.getAccessToken()

curl -X POST http://localhost:8000/api/v1/validate \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_text": "Sample prompt",
    "persona_id": "persona_0",
    "auto_improve": false
  }'
```

### Check Middleware

Backend logs:
```
SSO Auth Middleware enabled for WebUI routes
SSO auth OK: user@infovision.com on /api/v1/validate
```

## API Endpoints

### Protected Routes (require SSO token)
- `GET /assets/*` — WebUI static files
- `POST /api/v1/validate` — Via WebUI
- `GET /api/v1/personas` — Via WebUI
- `GET /api/v1/guidelines` — Via WebUI

### Open Routes (no auth required)
- `GET /api/v1/health` — Health check
- `POST /api/v1/auth/resolve` — OAuth endpoints
- `POST /api/v1/auth/map-persona`
- `POST /api/v1/slack/validate` — Slack has own verification
- `POST /api/v1/teams/message` — Teams has own verification

## Troubleshooting

### Error: "MSAL.js not loaded"
- Check CDN link in HTML head
- Browser console: `window.msal` should be defined

### Error: "Missing or invalid Authorization header"
- Browser not authenticated yet
- Check browser localStorage for MSAL_CLIENT_ID
- Clear browser cache and retry

### Error: "Backend resolve failed"
- MICROSOFT_CLIENT_ID not set
- MICROSOFT_JWKS_URL unreachable
- Check backend logs for token validation error

### Users see blank page after login
- Check `main-app` div is hidden initially
- Check auth init script runs before main app load
- Check browser console for JS errors

### Requests still go through without token (mock mode)
- `PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=true` is set
- Disable with `PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH=false`

## Security Notes

1. **Token Storage**
   - MSAL stores tokens in `sessionStorage` (cleared on tab close)
   - Not accessible to XSS via `sessionStorage.getItem()` but via DOM tree

2. **CORS**
   - Backend allows all origins (for testing)
   - Production: restrict to your domain only

3. **HTTPS Required**
   - MSAL.js requires HTTPS in production
   - Development can use `http://localhost`

4. **Token Expiry**
   - Tokens cached in `sessionStorage` for session duration
   - MSAL auto-refreshes when expired via silent flow

## Files Modified

- `frontend/index.html` — Added MSAL.js CDN + SSO login UI + auth init script
- `frontend/src/auth.js` — New MSAL.js wrapper module
- `app/middleware/auth_sso.py` — New SSO auth middleware
- `app/main.py` — Register middleware + import

## Next Steps

1. **Immediate**: Set env vars, test locally with mock OAuth
2. **Week 1**: Register Azure app, deploy to staging
3. **Week 2**: Run QA on Microsoft login flow
4. **Week 3**: Deploy to production

## References

- [MSAL.js Browser Docs](https://github.com/AzureAD/microsoft-authentication-library-for-js/tree/dev/lib/msal-browser)
- [Azure App Registration](https://learn.microsoft.com/en-us/azure/active-directory/develop/app-registrations-training-guide)
- [OAuth 2.0 + OIDC Flows](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)
