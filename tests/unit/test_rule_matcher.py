import uuid
from unittest.mock import AsyncMock
import pytest

from domains.notifications.domain.entities import AlertRule
from domains.notifications.domain.value_objects import (
    ConditionType,
    DeliveryChannel,
    AlertStatus,
)
from domains.notifications.domain.services.rule_matcher import RuleMatcherDomainService
from domains.notifications.application.evaluate_alerts_service import EvaluateAlertsService
from domains.notifications.ports.interface.outbound.i_notification_channel import (
    INotificationChannelAdapterPort,
)


def _rule(condition, threshold, channels=(DeliveryChannel.WEBSOCKET,), symbol="NIFTY"):
    return AlertRule(
        id=uuid.uuid4(),
        symbol=symbol,
        condition_type=condition,
        threshold=threshold,
        channels=list(channels),
    )


def test_rule_matcher_above_price_uses_spot():
    met, val, msg = RuleMatcherDomainService.match(_rule(ConditionType.ABOVE_PRICE, 24000.0), {"spot_price": 24150.0})
    assert met is True
    assert val == 24150.0
    assert "crossed above" in msg


def test_rule_matcher_below_price_not_met():
    met, val, _ = RuleMatcherDomainService.match(_rule(ConditionType.BELOW_PRICE, 24000.0), {"spot_price": 24150.0})
    assert met is False
    assert val == 24150.0


def test_rule_matcher_iv_spike_uses_atm_iv_percent():
    met, val, msg = RuleMatcherDomainService.match(_rule(ConditionType.IV_SPIKE, 20.0), {"atm_iv_pct": 25.5})
    assert met is True
    assert val == 25.5
    assert "%" in msg


def test_rule_matcher_missing_value_leaves_state_unknown():
    assert RuleMatcherDomainService.match(_rule(ConditionType.ABOVE_PRICE, 1.0), {"atm_iv_pct": 15.0})[0] is None
    assert RuleMatcherDomainService.match(_rule(ConditionType.IV_SPIKE, 1.0), {"spot_price": 24000.0})[0] is None


def test_rule_matcher_inactive_rule_is_skipped():
    rule = _rule(ConditionType.ABOVE_PRICE, 1.0)
    rule.is_active = False
    assert RuleMatcherDomainService.match(rule, {"spot_price": 24000.0})[0] is None


def _service(rules, transition_result=True, channels=None):
    repo = AsyncMock()
    repo.get_active_rules_by_symbol.return_value = rules
    repo.try_transition.return_value = transition_result
    if channels is None:
        ws = AsyncMock(spec=INotificationChannelAdapterPort)
        ws.dispatch.return_value = True
        channels = {DeliveryChannel.WEBSOCKET: ws}
    return EvaluateAlertsService(repository=repo, channels=channels), repo, channels


@pytest.mark.asyncio
async def test_evaluate_fires_on_crossing():
    rule = _rule(ConditionType.ABOVE_PRICE, 24000.0)
    service, repo, channels = _service([rule], transition_result=True)

    events = await service.evaluate_tick_event("NIFTY", {"spot_price": 24200.0})

    assert len(events) == 1
    assert events[0].triggered_value == 24200.0
    assert events[0].status == AlertStatus.DELIVERED
    repo.try_transition.assert_awaited_once()
    assert repo.try_transition.call_args[0][:2] == (rule.id, True)
    channels[DeliveryChannel.WEBSOCKET].dispatch.assert_awaited_once()
    repo.log_notification_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_does_not_refire_while_condition_holds():
    # The repository refuses the transition because the stored state is already TRUE.
    service, repo, channels = _service([_rule(ConditionType.ABOVE_PRICE, 24000.0)], transition_result=False)

    events = await service.evaluate_tick_event("NIFTY", {"spot_price": 24300.0})

    assert events == []
    channels[DeliveryChannel.WEBSOCKET].dispatch.assert_not_awaited()
    repo.log_notification_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_rearms_without_dispatch_when_condition_clears():
    rule = _rule(ConditionType.ABOVE_PRICE, 24000.0)
    service, repo, channels = _service([rule], transition_result=True)

    events = await service.evaluate_tick_event("NIFTY", {"spot_price": 23900.0})

    assert events == []
    assert repo.try_transition.call_args[0][:2] == (rule.id, False)
    channels[DeliveryChannel.WEBSOCKET].dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_skips_rules_whose_value_is_missing():
    service, repo, _ = _service([_rule(ConditionType.IV_SPIKE, 20.0)])

    assert await service.evaluate_tick_event("NIFTY", {"spot_price": 24000.0}) == []
    repo.try_transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_dispatches_only_the_rule_channels():
    ws = AsyncMock(spec=INotificationChannelAdapterPort)
    ws.dispatch.return_value = True
    webhook = AsyncMock(spec=INotificationChannelAdapterPort)
    webhook.dispatch.return_value = True
    rule = _rule(ConditionType.ABOVE_PRICE, 24000.0, channels=(DeliveryChannel.WEBHOOK,))
    service, _, _ = _service(
        [rule], channels={DeliveryChannel.WEBSOCKET: ws, DeliveryChannel.WEBHOOK: webhook}
    )

    events = await service.evaluate_tick_event("NIFTY", {"spot_price": 24100.0})

    webhook.dispatch.assert_awaited_once()
    ws.dispatch.assert_not_awaited()
    assert events[0].status == AlertStatus.DELIVERED


@pytest.mark.asyncio
async def test_evaluate_marks_failed_when_channel_missing_or_failing():
    failing = AsyncMock(spec=INotificationChannelAdapterPort)
    failing.dispatch.return_value = False
    rule = _rule(
        ConditionType.ABOVE_PRICE, 24000.0,
        channels=(DeliveryChannel.WEBHOOK, DeliveryChannel.EMAIL),
    )
    service, _, _ = _service([rule], channels={DeliveryChannel.WEBHOOK: failing})

    events = await service.evaluate_tick_event("NIFTY", {"spot_price": 24100.0})

    assert events[0].status == AlertStatus.FAILED
    assert "WEBHOOK delivery failed" in events[0].error_message
    assert "No adapter configured for EMAIL" in events[0].error_message
