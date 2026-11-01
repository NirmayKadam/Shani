import time
import uuid
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from domains.notifications.domain.entities import AlertRule
from domains.notifications.domain.value_objects import ConditionType, DeliveryChannel
from domains.notifications.api.router import get_manage_alerts_service
from domains.notifications.application.manage_alerts_service import ManageAlertRulesService
from shared.auth.jwt_verifier import SupabaseJwtVerifier

TEST_SECRET = "notifications-api-test-secret-0123456789"
TEST_USER = uuid.uuid4()


def _auth_header() -> dict:
    token = jwt.encode(
        {"sub": str(TEST_USER), "aud": "authenticated", "exp": int(time.time()) + 600},
        TEST_SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_manage_service():
    service = AsyncMock(spec=ManageAlertRulesService)
    app.dependency_overrides[get_manage_alerts_service] = lambda: service
    # Requests are authenticated against a test-only HS256 secret.
    with patch("shared.middleware.auth.get_jwt_verifier", return_value=SupabaseJwtVerifier(jwt_secret=TEST_SECRET)):
        yield service
    app.dependency_overrides.clear()


def test_create_alert_rule_endpoint(mock_manage_service):
    rule_id = uuid.uuid4()
    mock_manage_service.create_rule.return_value = AlertRule(
        id=rule_id,
        symbol="NIFTY",
        condition_type=ConditionType.ABOVE_PRICE,
        threshold=24500.0,
        channels=[DeliveryChannel.WEBSOCKET],
        cooldown_seconds=300,
        is_active=True,
    )

    payload = {
        "symbol": "NIFTY",
        "condition_type": "ABOVE_PRICE",
        "threshold": 24500.0,
        "channels": ["WEBSOCKET"],
        "cooldown_seconds": 300,
    }
    resp = TestClient(app).post("/v1/notifications/alerts", json=payload, headers=_auth_header())

    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "NIFTY"
    assert data["condition_type"] == "ABOVE_PRICE"
    assert data["threshold"] == 24500.0
    # The rule is created for the authenticated user
    assert mock_manage_service.create_rule.await_args[0][0].user_id == TEST_USER


def test_create_alert_rule_unauthenticated_fails(mock_manage_service):
    payload = {
        "symbol": "NIFTY",
        "condition_type": "ABOVE_PRICE",
        "threshold": 24500.0,
        "channels": ["WEBSOCKET"],
    }
    resp = TestClient(app).post("/v1/notifications/alerts", json=payload)
    assert resp.status_code == 401


def test_list_alert_rules_endpoint(mock_manage_service):
    mock_manage_service.list_active_rules.return_value = [
        AlertRule(
            id=uuid.uuid4(),
            symbol="BANKNIFTY",
            condition_type=ConditionType.IV_SPIKE,
            threshold=25.0,
            channels=[DeliveryChannel.WEBHOOK],
            is_active=True,
        )
    ]

    resp = TestClient(app).get("/v1/notifications/alerts?symbol=BANKNIFTY", headers=_auth_header())

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BANKNIFTY"
    assert mock_manage_service.list_active_rules.await_args.kwargs["user_id"] == TEST_USER
