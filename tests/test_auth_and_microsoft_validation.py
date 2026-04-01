from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import routes
from app.db.database import get_db
from app.integrations.oauth import provider


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_auth_endpoints_exist_and_require_api_key(api_client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "resolve_user_from_token",
        lambda db, access_token, email_hint=None: {
            "email": "user@example.com",
            "display_name": "User",
            "provider": "microsoft",
            "persona_id": "persona_1",
        },
    )
    monkeypatch.setattr(
        routes,
        "map_persona",
        lambda db, email, persona_id, source: SimpleNamespace(
            user_email=email, persona_id=persona_id, source=source
        ),
    )

    no_key = api_client.post("/api/v1/auth/resolve", json={"access_token": "token"})
    assert no_key.status_code == 401

    bad_key = api_client.post(
        "/api/v1/auth/map-persona",
        headers={"x-api-key": "wrong-key"},
        json={"email": "user@example.com", "persona_id": "persona_2"},
    )
    assert bad_key.status_code == 401

    good_resolve = api_client.post(
        "/api/v1/auth/resolve",
        headers={"x-api-key": routes.API_KEY},
        json={"access_token": "token"},
    )
    assert good_resolve.status_code == 200
    assert good_resolve.json()["email"] == "user@example.com"

    good_map = api_client.post(
        "/api/v1/auth/map-persona",
        headers={"x-api-key": routes.API_KEY},
        json={"email": "user@example.com", "persona_id": "persona_2", "source": "manual"},
    )
    assert good_map.status_code == 200
    assert good_map.json()["mapped"] is True


def test_microsoft_validation_uses_jwks_issuer_audience_and_tenant(monkeypatch):
    class FakeJwkClient:
        def __init__(self):
            self.seen_token = None

        def get_signing_key_from_jwt(self, token):
            self.seen_token = token
            return SimpleNamespace(key="public-key")

    seen_decode_kwargs = {}
    jwk_client = FakeJwkClient()

    monkeypatch.setattr(provider, "MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setattr(provider, "MICROSOFT_ALLOWED_AUDIENCES", ["aud-a", "client-id"])
    monkeypatch.setattr(provider, "MICROSOFT_ISSUER", "https://issuer.example/v2.0")
    monkeypatch.setattr(provider, "MICROSOFT_TENANT_ID", "tenant-123")
    monkeypatch.setattr(provider, "MICROSOFT_JWKS_URL", "https://jwks.example/keys")
    monkeypatch.setattr(provider, "_jwk_client", jwk_client)

    def fake_decode(token, key, algorithms, audience, issuer):
        seen_decode_kwargs["token"] = token
        seen_decode_kwargs["key"] = key
        seen_decode_kwargs["algorithms"] = algorithms
        seen_decode_kwargs["audience"] = audience
        seen_decode_kwargs["issuer"] = issuer
        return {"tid": "tenant-123", "email": "user@example.com", "name": "Demo User"}

    monkeypatch.setattr(provider.jwt, "decode", fake_decode)

    identity = provider._resolve_user_from_microsoft_token("signed-token", email_hint=None)

    assert jwk_client.seen_token == "signed-token"
    assert seen_decode_kwargs["audience"] == ["aud-a", "client-id"]
    assert seen_decode_kwargs["issuer"] == "https://issuer.example/v2.0"
    assert seen_decode_kwargs["algorithms"] == ["RS256"]
    assert identity["email"] == "user@example.com"


def test_microsoft_validation_rejects_wrong_tenant(monkeypatch):
    class FakeJwkClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key="public-key")

    monkeypatch.setattr(provider, "MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setattr(provider, "MICROSOFT_ALLOWED_AUDIENCES", ["client-id"])
    monkeypatch.setattr(provider, "MICROSOFT_ISSUER", "https://issuer.example/v2.0")
    monkeypatch.setattr(provider, "MICROSOFT_TENANT_ID", "tenant-expected")
    monkeypatch.setattr(provider, "MICROSOFT_JWKS_URL", "https://jwks.example/keys")
    monkeypatch.setattr(provider, "_jwk_client", FakeJwkClient())
    monkeypatch.setattr(
        provider.jwt,
        "decode",
        lambda *args, **kwargs: {"tid": "tenant-other", "email": "user@example.com"},
    )

    with pytest.raises(HTTPException) as exc_info:
        provider._resolve_user_from_microsoft_token("signed-token", email_hint=None)

    assert exc_info.value.status_code == 401
    assert "tenant" in exc_info.value.detail.lower()
