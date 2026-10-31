import logging
from typing import List, Dict, Any, Mapping, Optional
from datetime import datetime, timezone
import uuid

from domains.notifications.domain.entities import NotificationEvent
from domains.notifications.domain.value_objects import AlertStatus, DeliveryChannel
from domains.notifications.domain.services.rule_matcher import RuleMatcherDomainService
from domains.notifications.ports.interface.inbound.i_evaluate_alerts import (
    IEvaluateAlertsUseCasePort,
)
from domains.notifications.ports.interface.outbound.i_alert_repository import (
    IAlertRuleRepositoryPort,
)
from domains.notifications.ports.interface.outbound.i_notification_channel import (
    INotificationChannelAdapterPort,
)

logger = logging.getLogger(__name__)


class EvaluateAlertsService(IEvaluateAlertsUseCasePort):
    """Application service for evaluating symbol-level market snapshots against active alert rules.

    A rule fires once when its condition changes from not met to met (a crossing), and re-arms
    when the condition stops holding. The repository's atomic transition also enforces cooldown.
    """

    def __init__(
        self,
        repository: IAlertRuleRepositoryPort,
        channels: Optional[Mapping[DeliveryChannel, INotificationChannelAdapterPort]] = None,
    ):
        self._repo = repository
        self._channels = dict(channels or {})

    async def evaluate_tick_event(
        self, symbol: str, tick_payload: Dict[str, Any]
    ) -> List[NotificationEvent]:
        active_rules = await self._repo.get_active_rules_by_symbol(symbol)
        if not active_rules:
            return []

        now = datetime.now(timezone.utc)
        triggered_events: List[NotificationEvent] = []

        for rule in active_rules:
            condition_met, actual_val, msg = RuleMatcherDomainService.match(rule, tick_payload)
            if condition_met is None:
                continue

            changed = await self._repo.try_transition(rule.id, condition_met, now)
            if not (condition_met and changed):
                continue

            event = NotificationEvent(
                id=uuid.uuid4(),
                rule_id=rule.id,
                symbol=rule.symbol.upper(),
                condition_type=rule.condition_type,
                triggered_value=actual_val,
                threshold=rule.threshold,
                message=msg,
                channels=rule.channels,
                timestamp=now,
                status=AlertStatus.PENDING,
            )

            error_details = []
            for channel_type in rule.channels:
                adapter = self._channels.get(channel_type)
                if adapter is None:
                    error_details.append(f"No adapter configured for {channel_type.value}")
                    continue
                try:
                    if not await adapter.dispatch(event, rule):
                        error_details.append(f"{channel_type.value} delivery failed")
                except Exception as ex:
                    error_details.append(f"{channel_type.value}: {ex}")

            if error_details:
                event.status = AlertStatus.FAILED
                event.error_message = "; ".join(error_details)
            else:
                event.status = AlertStatus.DELIVERED

            await self._repo.log_notification_event(event)
            triggered_events.append(event)
            logger.info("Triggered alert %s for rule %s on %s", event.id, rule.id, symbol)

        return triggered_events
