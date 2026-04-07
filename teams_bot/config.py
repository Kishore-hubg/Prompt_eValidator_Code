from __future__ import annotations

import os


class TeamsBotSettings:
    def __init__(self) -> None:
        # Bot Framework credentials (Azure Bot registration)
        self.microsoft_app_id = os.getenv("BOT_APP_ID", os.getenv("MICROSOFT_APP_ID", "")).strip()
        self.microsoft_app_password = os.getenv(
            "BOT_APP_PASSWORD",
            os.getenv("MICROSOFT_APP_PASSWORD", ""),
        ).strip()
        # Required for Single Tenant bots — must match the Azure Bot "App Tenant ID"
        self.microsoft_app_tenant_id = os.getenv(
            "BOT_APP_TENANT_ID",
            os.getenv("MICROSOFT_APP_TENANT_ID", ""),
        ).strip()

        # Optional Teams OAuth connection name for SSO token retrieval.
        self.oauth_connection_name = os.getenv("TEAMS_OAUTH_CONNECTION_NAME", "").strip()

        # Prompt Validator backend
        self.validator_api_base = os.getenv("VALIDATOR_API_BASE", "http://127.0.0.1:8000").strip().rstrip("/")
        self.validator_api_key = os.getenv("VALIDATOR_API_KEY", "").strip()
        self.validator_teams_endpoint = f"{self.validator_api_base}/api/v1/teams/message"

        # Service host/port for this bot process.
        self.host = os.getenv("TEAMS_BOT_HOST", "0.0.0.0").strip()
        self.port = int(os.getenv("TEAMS_BOT_PORT", "3975").strip())

