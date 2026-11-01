import asyncio
import secrets
from typing import List, Optional
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, status

from app.config.settings import get_settings
from shared.utils.symbol_validator import SymbolValidator
from shared.utils.url_safety import UnsafeUrlError, assert_public_https_url
from domains.notifications.api.schemas import (
    CreateAlertRuleRequest,
    CreateAlertRuleResponse,
    AlertRuleResponse,
)
from domains.notifications.domain.entities import AlertRule
from domains.notifications.domain.exceptions import AlertRuleNotFoundError
from domains.notifications.domain.value_objects import DeliveryChannel
from domains.notifications.application.manage_alerts_service import ManageAlertRulesService
from domains.notifications.infrastructure.persistence.alert_repository import PostgresAlertRuleRepository

router = APIRouter(prefix="/v1/notifications", tags=["Notifications & Alerts"])


def get_manage_alerts_service() -> ManageAlertRulesService:
    repo = PostgresAlertRuleRepository()
    return ManageAlertRulesService(repository=repo)


def current_user_id(request: Request) -> Optional[uuid.UUID]:
    """Owner from the verified token (set by APIKeyAuthMiddleware); None only in anonymous dev mode."""
    return getattr(request.state, "user_id", None)


async def _clean_symbol(symbol: str) -> str:
    """Canonical market symbol (e.g. RELIANCE -> RELIANCE.NS), the same key priced events use."""
    return (await asyncio.to_thread(SymbolValidator.get_clean_symbol, symbol.strip().upper())).upper()


@router.post("/alerts", response_model=CreateAlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    req: CreateAlertRuleRequest,
    service: ManageAlertRulesService = Depends(get_manage_alerts_service),
    user_id: Optional[uuid.UUID] = Depends(current_user_id),
):
    """Create a new real-time market alert rule owned by the caller."""
    webhook_url = str(req.webhook_url) if req.webhook_url else None
    if webhook_url:
        try:
            await asyncio.to_thread(assert_public_https_url, webhook_url, get_settings().WebhookAllowPrivate)
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    rule = AlertRule(
        id=uuid.uuid4(),
        symbol=await _clean_symbol(req.symbol),
        condition_type=req.condition_type,
        threshold=req.threshold,
        channels=req.channels,
        cooldown_seconds=req.cooldown_seconds,
        webhook_url=webhook_url,
        email_destination=req.email_destination,
        is_active=True,
        user_id=user_id,
        webhook_secret=secrets.token_hex(32) if DeliveryChannel.WEBHOOK in req.channels else None,
    )
    created = await service.create_rule(rule)
    return created


@router.get("/alerts", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    symbol: Optional[str] = None,
    service: ManageAlertRulesService = Depends(get_manage_alerts_service),
    user_id: Optional[uuid.UUID] = Depends(current_user_id),
):
    """List the caller's active alert rules, optionally filtered by symbol."""
    clean = await _clean_symbol(symbol) if symbol else None
    return await service.list_active_rules(symbol=clean, user_id=user_id)


@router.get("/alerts/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: uuid.UUID,
    service: ManageAlertRulesService = Depends(get_manage_alerts_service),
    user_id: Optional[uuid.UUID] = Depends(current_user_id),
):
    """Get details of one of the caller's alert rules."""
    try:
        return await service.get_rule(rule_id, user_id)
    except AlertRuleNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")


@router.delete("/alerts/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: uuid.UUID,
    service: ManageAlertRulesService = Depends(get_manage_alerts_service),
    user_id: Optional[uuid.UUID] = Depends(current_user_id),
):
    """Delete one of the caller's alert rules."""
    try:
        await service.delete_rule(rule_id, user_id)
    except AlertRuleNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
