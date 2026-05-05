/**
 * MSAL Authentication Module
 * Handles Microsoft Entra ID SSO for Prompt Validator WebUI.
 * Fetches MSAL config from /api/v1/auth/public-config on init.
 */

class PromptValidatorAuth {
  constructor(overrides = {}) {
    this.overrides = overrides;
    this.msalConfig = null;
    this.msalInstance = null;
    this.accountInfo = null;
    this.accessToken = null;
    this.idToken = null;        // ID token — used for backend /auth/resolve with OIDC scopes
    this._tokenExpiry = 0;      // ms epoch — used to skip acquireTokenSilent when still valid
    this.userProfile = null;
    this.initialized = false;
  }

  /**
   * Fetch public MSAL config from backend.
   * Caches in sessionStorage so redirect return skips the Vercel cold-start call.
   */
  async _fetchBackendConfig() {
    const CACHE_KEY = "_pv_auth_cfg";
    const CACHE_TTL = 3600 * 1000; // 1 hour

    // Use cached config on redirect return — avoids Vercel cold-start in the hot path
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (raw) {
        const { ts, data } = JSON.parse(raw);
        if (Date.now() - ts < CACHE_TTL) {
          console.log("Auth config: using cached config (skip backend call)");
          return data;
        }
      }
    } catch (_) { /* corrupt cache — fall through to fetch */ }

    try {
      // 10 s timeout — Vercel cold start on first load can be slow
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 10000);
      let res;
      try {
        res = await fetch("/api/v1/auth/public-config", { signal: ctrl.signal });
      } finally {
        clearTimeout(tid);
      }
      if (!res.ok) throw new Error(`Config fetch failed: ${res.status}`);
      const data = await res.json();
      // Cache before redirect so redirect-return is instant (no Vercel cold start)
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
      return data;
    } catch (err) {
      console.error("Failed to fetch auth config from backend:", err);
      return null;
    }
  }

  /**
   * Initialize MSAL.js — fetches config from backend first
   */
  async init() {
    if (this.initialized) return this.isAuthenticated();

    // Fetch backend config
    const backendConfig = await this._fetchBackendConfig();
    if (!backendConfig) {
      console.warn("Auth config unavailable — auth disabled");
      return false;
    }

    // Check if mock OAuth mode is enabled
    if (backendConfig.mock_oauth) {
      console.log("Mock OAuth mode: auth disabled");
      this.initialized = true;
      return true;
    }

    const msal = backendConfig.msal || {};
    const clientId = this.overrides.clientId || msal.client_id || "";
    const authority = this.overrides.authority || msal.authority || "";
    const scopes = this.overrides.scopes || msal.scopes || ["openid", "profile", "email"];

    if (!clientId || !authority) {
      console.warn("MSAL client_id or authority not configured in backend");
      return false;
    }

    this.msalConfig = { clientId, authority, scopes };

    // Check if MSAL.js is loaded
    if (!window.msal || !window.msal.PublicClientApplication) {
      console.warn("MSAL.js CDN not loaded — auth disabled");
      return false;
    }

    try {
      // Extract hostname for knownAuthorities (required for tenant-specific authorities)
      const authorityHost = new URL(authority).hostname; // e.g. "login.microsoftonline.com"

      this.msalInstance = new window.msal.PublicClientApplication({
        auth: {
          clientId,
          authority,
          redirectUri: window.location.origin,
          knownAuthorities: [authorityHost],
        },
        cache: {
          cacheLocation: "sessionStorage",
          storeAuthStateInCookie: false,
        },
      });

      await this.msalInstance.initialize();
      this.initialized = true;

      // Handle redirect callback (returning from Microsoft login)
      const response = await this.msalInstance.handleRedirectPromise();
      if (response) {
        this.accountInfo = response.account;
        this.accessToken = response.accessToken;
        this.idToken = response.idToken;           // capture ID token for backend
        this.msalInstance.setActiveAccount(this.accountInfo);
        // Fire-and-forget — do NOT await; Vercel cold-start JWKS + MongoDB can take
        // 5-10 s and would block the "Completing sign-in..." state indefinitely.
        // persona_id will populate in the background; app is usable immediately.
        this._resolveBackendUser().catch(e => console.warn("Backend resolve (bg):", e));
        return true;
      }

      // Already logged in?
      const accounts = this.msalInstance.getAllAccounts();
      if (accounts.length > 0) {
        this.accountInfo = accounts[0];
        this.msalInstance.setActiveAccount(this.accountInfo);
        // Silently acquire token — also captures idToken + expiry in one call (no 2nd call needed)
        const token = await this.getAccessToken();
        if (token) {
          this._resolveBackendUser().catch(e => console.warn("Backend resolve (bg):", e));
          return true;
        }
      }

      return false;
    } catch (err) {
      console.error("MSAL init error:", err);
      return false;
    }
  }

  isAuthenticated() {
    return !!this.accountInfo;
  }

  getUser() {
    if (!this.accountInfo) return null;
    return {
      email: this.accountInfo.username || "",
      name: this.accountInfo.name || "",
      personaId: this.userProfile?.persona_id || null,
    };
  }

  /**
   * Silently acquire access token; fall back to redirect if silent fails.
   * Also captures idToken and expiry so callers don't need a second MSAL call.
   */
  async getAccessToken() {
    if (!this.msalInstance || !this.accountInfo) return null;
    const request = { account: this.accountInfo, scopes: this.msalConfig.scopes };
    try {
      const res = await this.msalInstance.acquireTokenSilent(request);
      this.accessToken = res.accessToken;
      // Capture idToken in same call — avoids a second acquireTokenSilent elsewhere
      if (res.idToken) this.idToken = res.idToken;
      // Track expiry for addAuthHeader caching (bug #4)
      this._tokenExpiry = res.expiresOn instanceof Date
        ? res.expiresOn.getTime()
        : (Date.now() + 3600 * 1000);
      return res.accessToken;
    } catch (err) {
      console.warn("Silent token failed, redirecting for refresh:", err);
      try {
        await this.msalInstance.acquireTokenRedirect(request);
        return null; // navigates away
      } catch (redirectErr) {
        console.error("Token refresh redirect failed:", redirectErr);
        return null;
      }
    }
  }

  /**
   * Trigger Microsoft login via redirect (no popup — avoids popup blocker)
   * Sets sessionStorage flag so app knows a login is in progress.
   */
  async login() {
    if (!this.msalInstance) {
      console.error("MSAL not initialized");
      return false;
    }
    try {
      // Mark that we're mid-login so init() can show a "returning..." state
      sessionStorage.setItem("msal_login_in_progress", "1");
      await this.msalInstance.loginRedirect({
        scopes: this.msalConfig.scopes,
      });
      // loginRedirect() navigates away — code below won't run until redirect returns
      return true;
    } catch (err) {
      console.error("Login failed:", err);
      sessionStorage.removeItem("msal_login_in_progress");
      return false;
    }
  }

  /**
   * Resolve user with backend → get persona_id
   */
  async _resolveBackendUser() {
    // Use idToken (JWT with aud=client_id) — works with OIDC scopes (openid/profile/email).
    // accessToken with OIDC scopes targets MS Graph (aud=00000003-...), not our app.
    const token = this.idToken || this.accessToken;
    if (!token) return;
    try {
      // 8-second timeout — Vercel cold start (JWKS + MongoDB) can be slow
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      let res;
      try {
        res = await fetch("/api/v1/auth/resolve", {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": window._PROMPT_VALIDATOR_API_KEY || "infovision-dev-key",
          },
          body: JSON.stringify({
            access_token: token,           // idToken preferred; backend validates aud=client_id
            email_hint: this.accountInfo?.username,
          }),
        });
      } finally {
        clearTimeout(timeoutId);
      }
      if (res.ok) {
        this.userProfile = await res.json();
        console.log("SSO: user resolved:", this.userProfile.email, "→", this.userProfile.persona_id);
      } else {
        console.warn("Backend user resolve failed:", res.status);
      }
    } catch (err) {
      console.error("Backend resolve error:", err);
    }
  }

  /**
   * Logout
   */
  async logout() {
    if (!this.msalInstance) return;
    try {
      await this.msalInstance.logout({ account: this.accountInfo });
    } catch (err) {
      console.error("Logout failed:", err);
    }
    this.accountInfo = null;
    this.accessToken = null;
    this.userProfile = null;
  }

  /**
   * Add Authorization header to fetch config.
   * Uses cached token; only calls acquireTokenSilent when token is missing or
   * expiring within 5 minutes — avoids MSAL overhead on every API call.
   */
  async addAuthHeader(headers = {}) {
    const REFRESH_MARGIN = 5 * 60 * 1000; // refresh 5 min before expiry
    const needsRefresh = !this.accessToken || Date.now() > this._tokenExpiry - REFRESH_MARGIN;
    if (needsRefresh) {
      await this.getAccessToken(); // updates this.accessToken + this._tokenExpiry
    }
    return this.accessToken
      ? { ...headers, Authorization: `Bearer ${this.accessToken}` }
      : { ...headers };
  }
}

// Singleton
window.promptValidatorAuth = new PromptValidatorAuth();
