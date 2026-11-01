from abc import ABC, abstractmethod
from typing import List, Optional
import uuid

from domains.notifications.domain.entities import AlertRule


class IManageAlertRulesUseCasePort(ABC):
    """Inbound port for managing user alert rules (user_id is the owner; None = no ownership)."""

    @abstractmethod
    async def create_rule(self, rule: AlertRule) -> AlertRule:
        """Create new alert rule."""
        pass

    @abstractmethod
    async def get_rule(self, rule_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> AlertRule:
        """Fetch one of the user's rules by ID."""
        pass

    @abstractmethod
    async def list_active_rules(
        self, symbol: Optional[str] = None, user_id: Optional[uuid.UUID] = None
    ) -> List[AlertRule]:
        """List the user's active alert rules, optionally filtered by symbol."""
        pass

    @abstractmethod
    async def delete_rule(self, rule_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> bool:
        """Delete one of the user's alert rules."""
        pass
