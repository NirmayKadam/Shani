from abc import ABC, abstractmethod
from typing import List, Optional
import uuid
from datetime import datetime

from domains.notifications.domain.entities import AlertRule, NotificationEvent


class IAlertRuleRepositoryPort(ABC):
    """Outbound port for AlertRule storage operations."""

    @abstractmethod
    async def save_rule(self, rule: AlertRule) -> AlertRule:
        """Persist a new or updated AlertRule."""
        pass

    @abstractmethod
    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Optional[AlertRule]:
        """Fetch alert rule by ID."""
        pass

    @abstractmethod
    async def get_active_rules_by_symbol(self, symbol: str) -> List[AlertRule]:
        """Fetch active alert rules for a specific market symbol."""
        pass

    @abstractmethod
    async def list_active_rules(self, user_id: Optional[uuid.UUID] = None) -> List[AlertRule]:
        """Fetch active alert rules, limited to one owner when user_id is given."""
        pass

    @abstractmethod
    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        """Delete alert rule by ID."""
        pass

    @abstractmethod
    async def try_transition(
        self, rule_id: uuid.UUID, condition_met: bool, now: datetime
    ) -> bool:
        """Atomically record a change in the rule's condition state.

        Returns True only when the stored state changed. A change to True is refused while
        the rule is still inside its cooldown window, so callers fire exactly when this
        returns True for condition_met=True.
        """
        pass

    @abstractmethod
    async def log_notification_event(self, event: NotificationEvent) -> NotificationEvent:
        """Persist notification dispatch log."""
        pass
