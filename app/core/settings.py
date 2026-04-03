from pathlib import Path
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=True)
DB_PATH = BASE_DIR / "prompt_validator.db"
FRONTEND_DIR = BASE_DIR / "frontend"
API_KEY = os.getenv("PROMPT_VALIDATOR_API_KEY", "infovision-dev-key")
OAUTH_PROVIDER_NAME = os.getenv("PROMPT_VALIDATOR_OAUTH_PROVIDER", "mock-oauth")
ALLOW_MOCK_OAUTH = os.getenv("PROMPT_VALIDATOR_ALLOW_MOCK_OAUTH", "true").strip().lower() == "true"

# Microsoft Entra ID / Teams SSO settings.
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common").strip()
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
_raw_allowed_audiences = os.getenv("MICROSOFT_ALLOWED_AUDIENCES", "").strip()
MICROSOFT_ALLOWED_AUDIENCES = [
    item.strip() for item in _raw_allowed_audiences.split(",") if item.strip()
]
if MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_ID not in MICROSOFT_ALLOWED_AUDIENCES:
    MICROSOFT_ALLOWED_AUDIENCES.append(MICROSOFT_CLIENT_ID)
MICROSOFT_ISSUER = os.getenv(
    "MICROSOFT_ISSUER",
    f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/v2.0",
).strip()
MICROSOFT_JWKS_URL = os.getenv(
    "MICROSOFT_JWKS_URL",
    f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/discovery/v2.0/keys",
).strip()

# Database: "mongodb" (default, MongoDB Atlas) or "sqlite" (optional local file).
DATABASE_BACKEND = os.getenv("DATABASE_BACKEND", "mongodb").strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _build_mongodb_uri_from_atlas_env() -> str:
    """
    Build an Atlas-style mongodb+srv URI when MONGODB_URI is not set.
    Required env vars: MONGODB_USER, MONGODB_PASSWORD, MONGODB_CLUSTER_HOST (host only, no scheme).
    Optional: MONGODB_APP_NAME (appName query param, common in Atlas UI).
    """
    user = os.getenv("MONGODB_USER", "").strip()
    password = os.getenv("MONGODB_PASSWORD", "").strip()
    host = os.getenv("MONGODB_CLUSTER_HOST", "").strip()
    if not (user and password and host):
        return ""
    safe_user = quote_plus(user)
    safe_pw = quote_plus(password)
    qs_parts = ["retryWrites=true", "w=majority"]
    app = os.getenv("MONGODB_APP_NAME", "").strip()
    if app:
        qs_parts.append(f"appName={quote_plus(app)}")
    return f"mongodb+srv://{safe_user}:{safe_pw}@{host}/?{'&'.join(qs_parts)}"


_raw_mongo_uri = os.getenv("MONGODB_URI", "").strip()
MONGODB_URI = _raw_mongo_uri or _build_mongodb_uri_from_atlas_env()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "prompt_validator").strip()

# Groq LLM (OpenAI-compatible chat completions) for semantic evaluation and rewrites.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
# Evaluation model — fast, deterministic scoring, reliable JSON schema output.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
# Rewrite model — reasoning-capable for 3-step fact extraction + contradiction detection.
# Defaults to deepseek-r1-distill-llama-70b (best Groq reasoning model).
# Override with GROQ_REWRITE_MODEL=llama-3.3-70b-versatile to use a single model.
GROQ_REWRITE_MODEL = os.getenv("GROQ_REWRITE_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))
GROQ_REQUESTS_PER_MINUTE = max(1, int(os.getenv("GROQ_REQUESTS_PER_MINUTE", "25")))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()
ANTHROPIC_TIMEOUT_SECONDS = float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "60"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
LLM_VALIDATE_REQUIRED = _env_bool("LLM_VALIDATE_REQUIRED", False)
LLM_STRICT_SCHEMA = _env_bool("LLM_STRICT_SCHEMA", True)
LLM_FALLBACK_ON_VALIDATE_FAILURE = _env_bool("LLM_FALLBACK_ON_VALIDATE_FAILURE", True)
LLM_BLEND_STATIC_WEIGHT = float(os.getenv("LLM_BLEND_STATIC_WEIGHT", "0.4"))
LLM_BLEND_LLM_WEIGHT = float(os.getenv("LLM_BLEND_LLM_WEIGHT", "0.6"))


def llm_blend_weights() -> tuple[float, float]:
    """Return normalized (static_weight, llm_weight) for blended score."""
    static_w = max(0.0, LLM_BLEND_STATIC_WEIGHT)
    llm_w = max(0.0, LLM_BLEND_LLM_WEIGHT)
    total = static_w + llm_w
    if total <= 0:
        return 1.0, 0.0
    return static_w / total, llm_w / total


# Slack Slash Command integration
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "").strip()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()  # optional: for proactive messages

# ── Token-optimisation settings (model-agnostic: apply to Groq and Anthropic) ──
# Static pre-screen: if the rules-engine static score is >= this threshold the
# LLM evaluation call is skipped entirely and the static result is returned
# directly.  Set to 0 to disable (always call LLM).  Default: 85 ("Excellent").
STATIC_PRESCREEN_THRESHOLD = float(os.getenv("STATIC_PRESCREEN_THRESHOLD", "85"))

# In-memory prompt result cache TTL in seconds.  Identical (prompt, persona,
# auto_improve) requests within this window return the cached result without
# calling the LLM.  Set to 0 to disable.  Default: 600 s (10 min).
PROMPT_CACHE_TTL_SECONDS = int(os.getenv("PROMPT_CACHE_TTL_SECONDS", "600"))
