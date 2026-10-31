import logging
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import asyncpg

from domains.notifications.domain.entities import AlertRule, NotificationEvent
from domains.notifications.domain.value_objects import (
    ConditionType,
    DeliveryChannel,
    AlertStatus,
)
from domains.notifications.ports.interface.outbound.i_alert_repository import (
    IAlertRuleRepositoryPort,
)
from shared.infrastructure.database import get_database_pool

logger = logging.getLogger(__name__)


class PostgresAlertRuleRepository(IAlertRuleRepositoryPort):
    """PostgreSQL / TimescaleDB implementation of IAlertRuleRepositoryPort using asyncpg."""

    _COLUMNS = (
        "id, symbol, condition_type, threshold, channels, cooldown_seconds, "
        "last_triggered_at, is_active, webhook_url, email_destination, created_at, "
        "last_condition_met, user_id"
    )

    def __init__(self, pool: Optional[asyncpg.Pool] = None):
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        return await get_database_pool()

    async def save_rule(self, rule: AlertRule) -> AlertRule:
        pool = await self._get_pool()
        channels_str = [c.value for c in rule.channels]
        query = """
            INSERT INTO AlertRules (
                id, symbol, condition_type, threshold, channels, cooldown_seconds,
                last_triggered_at, is_active, webhook_url, email_destination, created_at,
                user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                condition_type = EXCLUDED.condition_type,
                threshold = EXCLUDED.threshold,
                channels = EXCLUDED.channels,
                cooldown_seconds = EXCLUDED.cooldown_seconds,
                last_triggered_at = EXCLUDED.last_triggered_at,
                is_active = EXCLUDED.is_active,
                webhook_url = EXCLUDED.webhook_url,
                email_destination = EXCLUDED.email_destination;
        """
        async with pool.acquire() as conn:
            await conn.execute(
                query,
                rule.id,
                rule.symbol.upper(),
                rule.condition_type.value,
                float(rule.threshold),
                channels_str,
                int(rule.cooldown_seconds),
                rule.last_triggered_at,
                rule.is_active,
                rule.webhook_url,
                rule.email_destination,
                rule.created_at,
                rule.user_id,
            )
        return rule

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Optional[AlertRule]:
        pool = await self._get_pool()
        query = f"""
            SELECT {self._COLUMNS}
            FROM AlertRules
            WHERE id = $1;
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, rule_id)
            if not row:
                return None
            return self._map_row_to_alert_rule(row)

    async def get_active_rules_by_symbol(self, symbol: str) -> List[AlertRule]:
        pool = await self._get_pool()
        # Symbols are stored uppercase, so a plain equality uses idx_alert_rules_symbol.
        query = f"""
            SELECT {self._COLUMNS}
            FROM AlertRules
            WHERE symbol = $1 AND is_active = TRUE;
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, symbol.upper())
            return [self._map_row_to_alert_rule(r) for r in rows]

    async def list_active_rules(self) -> List[AlertRule]:
        pool = await self._get_pool()
        query = f"""
            SELECT {self._COLUMNS}
            FROM AlertRules
            WHERE is_active = TRUE
            ORDER BY created_at DESC;
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._map_row_to_alert_rule(r) for r in rows]

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        pool = await self._get_pool()
        query = "DELETE FROM AlertRules WHERE id = $1;"
        async with pool.acquire() as conn:
            result = await conn.execute(query, rule_id)
            # Result format: "DELETE 1" or "DELETE 0"
            return result.endswith("1")

    async def try_transition(
        self, rule_id: uuid.UUID, condition_met: bool, now: datetime
    ) -> bool:
        # One conditional UPDATE: only the first evaluator to see a state change wins, and a
        # change to TRUE (a firing) is refused inside the cooldown window. Parameters are cast
        # explicitly: in `$3 - make_interval(...)` Postgres would otherwise infer $3 as an interval.
        query = """
            UPDATE AlertRules
            SET last_condition_met = $2::boolean,
                last_triggered_at = CASE WHEN $2::boolean THEN $3::timestamptz ELSE last_triggered_at END
            WHERE id = $1::uuid
              AND is_active = TRUE
              AND last_condition_met IS DISTINCT FROM $2::boolean
              AND (
                  NOT $2::boolean
                  OR last_triggered_at IS NULL
                  OR last_triggered_at <= $3::timestamptz - make_interval(secs => cooldown_seconds)
              )
            RETURNING id;
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, rule_id, condition_met, now)
        return row is not None

    async def log_notification_event(self, event: NotificationEvent) -> NotificationEvent:
        pool = await self._get_pool()
        channels_str = [c.value for c in event.channels]
        query = """
            INSERT INTO NotificationLogs (
                id, rule_id, symbol, condition_type, triggered_value, threshold,
                message, channels, status, error_message, timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
        """
        async with pool.acquire() as conn:
            await conn.execute(
                query,
                event.id,
                event.rule_id,
                event.symbol.upper(),
                event.condition_type.value,
                float(event.triggered_value),
                float(event.threshold),
                event.message,
                channels_str,
                event.status.value,
                event.error_message,
                event.timestamp,
            )
        return event

    def _map_row_to_alert_rule(self, row: asyncpg.Record) -> AlertRule:
        channels = [DeliveryChannel(c) for c in row["channels"]]
        return AlertRule(
            id=row["id"],
            symbol=row["symbol"],
            condition_type=ConditionType(row["condition_type"]),
            threshold=float(row["threshold"]),
            channels=channels,
            cooldown_seconds=int(row["cooldown_seconds"]),
            last_triggered_at=row["last_triggered_at"],
            is_active=bool(row["is_active"]),
            webhook_url=row["webhook_url"],
            email_destination=row["email_destination"],
            created_at=row["created_at"],
            last_condition_met=row["last_condition_met"],
            user_id=row["user_id"],
        )
