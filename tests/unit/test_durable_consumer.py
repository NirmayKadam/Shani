import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from shared.infrastructure.event_bus.consumer import run_durable_consumer
from shared.infrastructure.event_bus.streams import StreamMessage


def _bus_with(read_batches, stale=()):
    """A fake DurableEventStream whose read_group returns the given batches, then stops the loop."""
    bus = AsyncMock()
    bus.claim_stale.return_value = list(stale)
    stop = asyncio.Event()
    batches = list(read_batches)

    async def read_group(**_):
        if batches:
            return batches.pop(0)
        stop.set()
        return []

    bus.read_group.side_effect = read_group
    return bus, stop


async def _run(bus, stop, handler, **kwargs):
    with patch("shared.infrastructure.event_bus.consumer.DurableEventStream", return_value=bus):
        await run_durable_consumer(
            AsyncMock(), stream="s", group="g", dlq_stream="s:dlq", handler=handler,
            stop_event=stop, claim_every_seconds=0, **kwargs,
        )


@pytest.mark.unit
async def test_success_is_acked():
    msg = StreamMessage(stream="s", message_id="1-0", payload={"x": 1})
    bus, stop = _bus_with([[msg]])
    handler = AsyncMock()

    await _run(bus, stop, handler)

    handler.assert_awaited_once_with({"x": 1})
    bus.ack.assert_awaited_once_with("s", "g", "1-0")
    bus.retry_or_dead_letter.assert_not_awaited()
    bus.ensure_group.assert_awaited_once_with("s", "g", start_id="$")


@pytest.mark.unit
async def test_failure_is_retried_or_dead_lettered_not_acked():
    msg = StreamMessage(stream="s", message_id="2-0", payload={"x": 2}, retry_count=1)
    bus, stop = _bus_with([[msg]])
    handler = AsyncMock(side_effect=ValueError("bad chain"))

    await _run(bus, stop, handler)

    bus.ack.assert_not_awaited()
    kwargs = bus.retry_or_dead_letter.await_args.kwargs
    assert kwargs["dlq_stream"] == "s:dlq" and kwargs["message"] is msg


@pytest.mark.unit
async def test_messages_left_by_a_crashed_consumer_are_reclaimed():
    orphan = StreamMessage(stream="s", message_id="3-0", payload={"x": 3})
    bus, stop = _bus_with([[]], stale=[orphan])
    handler = AsyncMock()

    await _run(bus, stop, handler)

    handler.assert_any_await({"x": 3})
    bus.ack.assert_any_await("s", "g", "3-0")


@pytest.mark.unit
async def test_read_errors_do_not_kill_the_loop():
    bus, stop = _bus_with([])
    calls = {"n": 0}

    async def flaky(**_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("redis restarting")
        stop.set()
        return []

    bus.read_group.side_effect = flaky
    with patch("shared.infrastructure.event_bus.consumer.asyncio.sleep", new=AsyncMock()):
        await _run(bus, stop, AsyncMock())
    assert calls["n"] == 2
