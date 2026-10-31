from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, model_validator
import uuid
from datetime import datetime

from domains.notifications.domain.value_objects import (
    ConditionType,
    DeliveryChannel,
    AlertStatus,
)


class CreateAlertRuleRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, json_schema_extra={"example": "NIFTY"}, description="Market symbol")
    condition_type: ConditionType = Field(..., description="ABOVE_PRICE / BELOW_PRICE compare the spot price; IV_SPIKE compares ATM implied volatility in percent")
    threshold: float = Field(..., gt=0, description="Spot price level, or IV in percent for IV_SPIKE")
    channels: List[DeliveryChannel] = Field(default=[DeliveryChannel.WEBSOCKET], min_length=1, description="Delivery channels")
    cooldown_seconds: int = Field(default=300, ge=10, le=86400, description="Minimum seconds between triggers")
    webhook_url: Optional[HttpUrl] = Field(default=None, description="HTTP Webhook URL (required for the WEBHOOK channel)")
    email_destination: Optional[str] = Field(
        default=None,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Destination email address (required for the EMAIL channel)",
    )

    @model_validator(mode="after")
    def _destinations_present(self):
        if DeliveryChannel.WEBHOOK in self.channels and not self.webhook_url:
            raise ValueError("webhook_url is required when the WEBHOOK channel is selected")
        if DeliveryChannel.EMAIL in self.channels and not self.email_destination:
            raise ValueError("email_destination is required when the EMAIL channel is selected")
        return self


class AlertRuleResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    condition_type: ConditionType
    threshold: float
    channels: List[DeliveryChannel]
    cooldown_seconds: int
    last_triggered_at: Optional[datetime] = None
    is_active: bool
    webhook_url: Optional[str] = None
    email_destination: Optional[str] = None
    created_at: datetime


class CreateAlertRuleResponse(AlertRuleResponse):
    # Returned only in the create response, and only for WEBHOOK rules: verify deliveries with
    # HMAC-SHA256(secret, raw body) == X-AlphaStreams-Signature. It cannot be retrieved later.
    webhook_secret: Optional[str] = None


class NotificationLogResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    symbol: str
    condition_type: ConditionType
    triggered_value: float
    threshold: float
    message: str
    channels: List[DeliveryChannel]
    status: AlertStatus
    error_message: Optional[str] = None
    timestamp: datetime
