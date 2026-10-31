import asyncio
import hashlib
import hmac
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from shared.auth.jwt_verifier import AuthError, SupabaseJwtVerifier
from shared.middleware.auth import APIKeyAuthMiddleware
from shared.utils.url_safety import UnsafeUrlError, assert_public_https_url

SECRET = "test-hs256-secret-at-least-32-bytes-long!!"
USER = "8f14e45f-ceea-467a-9575-6f9c8e0a3b11"


def _token(sub=USER, key=SECRET, alg="HS256", aud="authenticated", exp_in=3600, headers=None):
    claims = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_in}
    return jwt.encode(claims, key, algorithm=alg, headers=headers)


# ── JWT verifier ────────────────────────────────────────────────

@pytest.mark.unit
class TestJwtVerifier:
    def test_valid_hs256(self):
        assert SupabaseJwtVerifier(jwt_secret=SECRET).verify(_token())["sub"] == USER

    @pytest.mark.parametrize("token,reason", [
        (lambda: _token(exp_in=-10), "expired"),
        (lambda: _token(aud="anon"), "Invalid token"),
        (lambda: _token(key="another-secret-that-is-also-long-enough!!"), "Invalid token"),
        (lambda: "not.a.jwt", "Malformed"),
        (lambda: "", "Missing"),
    ])
    def test_rejected(self, token, reason):
        with pytest.raises(AuthError, match=reason):
            SupabaseJwtVerifier(jwt_secret=SECRET).verify(token())

    def test_unsigned_alg_none_rejected(self):
        token = jwt.encode({"sub": USER, "aud": "authenticated", "exp": int(time.time()) + 60}, None, algorithm="none")
        with pytest.raises(AuthError, match="Unsupported"):
            SupabaseJwtVerifier(jwt_secret=SECRET).verify(token)

    def test_hs256_refused_without_secret(self):
        verifier = SupabaseJwtVerifier(supabase_url="https://example.supabase.co")
        with pytest.raises(AuthError, match="HS256"):
            verifier.verify(_token())

    def test_es256_via_jwks(self):
        private_key = ec.generate_private_key(ec.SECP256R1())
        verifier = SupabaseJwtVerifier(supabase_url="https://example.supabase.co")
        verifier._jwks = MagicMock()
        verifier._jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private_key.public_key())
        token = _token(key=private_key, alg="ES256", headers={"kid": "k1"})
        assert verifier.verify(token)["sub"] == USER

    def test_configured(self):
        assert not SupabaseJwtVerifier().configured
        assert SupabaseJwtVerifier(jwt_secret=SECRET).configured


# ── Auth middleware ─────────────────────────────────────────────

def _client(verifier, production=False, internal_key=""):
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)

    @app.get("/v1/notifications/alerts")
    async def alerts(request: Request):
        uid = request.state.user_id
        return {"user_id": str(uid) if uid else None}

    @app.get("/v1/ingestion/options/NIFTY")
    async def ingestion():
        return {"ok": True}

    @app.get("/v1/pricer/ticker/NIFTY")
    async def public():
        return {"ok": True}

    settings = SimpleNamespace(is_production=production, InternalApiKey=internal_key)
    patches = [
        patch("shared.middleware.auth.get_settings", return_value=settings),
        patch("shared.middleware.auth.get_jwt_verifier", return_value=verifier),
    ]
    for p in patches:
        p.start()
    return TestClient(app), patches


@pytest.fixture
def make_client():
    started = []

    def factory(*args, **kwargs):
        client, patches = _client(*args, **kwargs)
        started.extend(patches)
        return client

    yield factory
    for p in started:
        p.stop()


@pytest.mark.unit
class TestAuthMiddleware:
    def test_user_route_requires_valid_token(self, make_client):
        client = make_client(SupabaseJwtVerifier(jwt_secret=SECRET))
        assert client.get("/v1/notifications/alerts").status_code == 401
        bad = client.get("/v1/notifications/alerts", headers={"Authorization": "Bearer junk"})
        assert bad.status_code == 401
        ok = client.get("/v1/notifications/alerts", headers={"Authorization": f"Bearer {_token()}"})
        assert ok.status_code == 200 and ok.json()["user_id"] == USER

    def test_anonymous_in_development_without_auth_config(self, make_client):
        client = make_client(SupabaseJwtVerifier(), production=False)
        resp = client.get("/v1/notifications/alerts")
        assert resp.status_code == 200 and resp.json()["user_id"] is None

    def test_production_fails_closed_without_auth_config(self, make_client):
        client = make_client(SupabaseJwtVerifier(), production=True)
        assert client.get("/v1/notifications/alerts").status_code == 401

    def test_public_routes_stay_public(self, make_client):
        client = make_client(SupabaseJwtVerifier(jwt_secret=SECRET), production=True)
        assert client.get("/v1/pricer/ticker/NIFTY", headers={"Authorization": "Bearer junk"}).status_code == 200

    def test_internal_key(self, make_client):
        client = make_client(SupabaseJwtVerifier(), internal_key="k3y")
        assert client.get("/v1/ingestion/options/NIFTY").status_code == 401
        assert client.get("/v1/ingestion/options/NIFTY", headers={"X-Internal-API-Key": "k3y"}).status_code == 200

    def test_internal_routes_closed_in_production_without_key(self, make_client):
        client = make_client(SupabaseJwtVerifier(), production=True, internal_key="")
        assert client.get("/v1/ingestion/options/NIFTY").status_code == 503


# ── Rule ownership ──────────────────────────────────────────────

@pytest.mark.unit
class TestOwnership:
    def _service(self, owner):
        from domains.notifications.application.manage_alerts_service import ManageAlertRulesService
        repo = AsyncMock()
        repo.get_rule_by_id.return_value = SimpleNamespace(id=uuid.uuid4(), user_id=owner)
        repo.delete_rule.return_value = True
        return ManageAlertRulesService(repo), repo

    def test_other_users_rule_is_not_found(self):
        from domains.notifications.domain.exceptions import AlertRuleNotFoundError
        service, repo = self._service(owner=uuid.uuid4())
        with pytest.raises(AlertRuleNotFoundError):
            asyncio.run(service.delete_rule(uuid.uuid4(), user_id=uuid.UUID(USER)))
        repo.delete_rule.assert_not_awaited()

    def test_owner_can_delete(self):
        service, repo = self._service(owner=uuid.UUID(USER))
        assert asyncio.run(service.delete_rule(uuid.uuid4(), user_id=uuid.UUID(USER)))
        repo.delete_rule.assert_awaited_once()

    def test_listing_is_scoped_to_user(self):
        service, repo = self._service(owner=None)
        asyncio.run(service.list_active_rules(user_id=uuid.UUID(USER)))
        repo.list_active_rules.assert_awaited_once_with(uuid.UUID(USER))


# ── WebSocket alert routing ─────────────────────────────────────

@pytest.mark.unit
def test_alerts_reach_only_their_owner():
    from domains.analytics.api.events_router_api import ConnectionManager, _ClientConnection

    async def scenario():
        manager = ConnectionManager()
        owner_q, other_q, anon_q = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
        manager._Connections["NIFTY"] = {
            "owner": _ClientConnection(MagicMock(), owner_q, MagicMock(), user_id=USER),
            "other": _ClientConnection(MagicMock(), other_q, MagicMock(), user_id=str(uuid.uuid4())),
            "anon": _ClientConnection(MagicMock(), anon_q, MagicMock()),
        }
        await manager.broadcast("NIFTY", {"type": "alert", "data": {"user_id": USER, "message": "hi"}})
        await manager.broadcast("NIFTY", {"type": "price", "data": {"last_price": 1}})
        return owner_q.qsize(), other_q.qsize(), anon_q.qsize()

    owner, other, anon = asyncio.run(scenario())
    assert (owner, other, anon) == (2, 1, 1)  # everyone gets prices; only the owner gets the alert


# ── SSRF guard and webhook signature ────────────────────────────

@pytest.mark.unit
class TestWebhookSafety:
    @pytest.mark.parametrize("url", [
        "http://example.com/hook",          # not https
        "https://127.0.0.1/hook",           # loopback
        "https://169.254.169.254/latest",   # cloud metadata
        "https://10.0.0.5/hook",            # private
        "https://[::1]/hook",               # IPv6 loopback
        "ftp://example.com/x",
    ])
    def test_rejects_unsafe_urls(self, url):
        with pytest.raises(UnsafeUrlError):
            assert_public_https_url(url)

    def test_accepts_public_https(self):
        with patch("shared.utils.url_safety.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            assert_public_https_url("https://hooks.example.com/alerts")

    def test_rejects_host_resolving_to_private(self):
        with patch("shared.utils.url_safety.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("192.168.1.10", 443))]):
            with pytest.raises(UnsafeUrlError, match="non-public"):
                assert_public_https_url("https://rebind.example.com/alerts")

    def test_signature_uses_rule_secret(self):
        from domains.notifications.infrastructure.channels.webhook_channel import sign_payload
        body = b'{"a":1}'
        assert sign_payload("s3cret", body) == hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


# ── Symbol validator cache ──────────────────────────────────────

@pytest.mark.unit
def test_validator_does_not_cache_network_errors():
    from shared.utils.symbol_validator import SymbolValidator

    with patch("shared.utils.symbol_validator.yf.Ticker", side_effect=OSError("network down")):
        assert SymbolValidator.validate("ZZTOPCO") is False
    history = MagicMock()
    history.history.return_value.empty = False
    with patch("shared.utils.symbol_validator.yf.Ticker", return_value=history), \
         patch("domains.analytics.api.instruments_loader.instruments_catalog.is_valid_symbol", return_value=False):
        assert SymbolValidator.validate("ZZTOPCO") is True  # the earlier failure was not cached
