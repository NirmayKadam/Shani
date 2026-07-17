import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from domains.analytics.api.events_router_api import ConnectionManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_manager_cleanup_recursion_fix():
    manager = ConnectionManager()
    mock_ws = AsyncMock()

    with patch("domains.analytics.api.events_router_api._redis_global_listener", return_value=AsyncMock()):
        await manager.connect("TCS", mock_ws)

        # Cancel actual background tasks to avoid dangling async loops in test
        if manager._CleanupTask:
            manager._CleanupTask.cancel()
        if manager._GlobalSubscriberTask:
            manager._GlobalSubscriberTask.cancel()
        if manager._PollingTask:
            manager._PollingTask.cancel()

        await asyncio.gather(
            *[t for t in (manager._CleanupTask, manager._GlobalSubscriberTask, manager._PollingTask) if t],
            return_exceptions=True
        )

        # Set the current running task as _CleanupTask to simulate it triggering the disconnect
        current_task = asyncio.current_task()
        manager._CleanupTask = current_task
        manager._GlobalSubscriberTask = None
        manager._PollingTask = None

        # Disconnecting should trigger _stop_background_tasks_if_idle_locked
        # Since _CleanupTask is the current task, it must not cancel/await itself
        await manager.disconnect("TCS", mock_ws)

        assert "TCS" not in manager._Connections
        assert manager._CleanupTask is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_manager_subscriber_recursion_fix():
    manager = ConnectionManager()
    mock_ws = AsyncMock()

    with patch("domains.analytics.api.events_router_api._redis_global_listener", return_value=AsyncMock()):
        await manager.connect("TCS", mock_ws)

        # Cancel actual background tasks
        if manager._CleanupTask:
            manager._CleanupTask.cancel()
        if manager._GlobalSubscriberTask:
            manager._GlobalSubscriberTask.cancel()
        if manager._PollingTask:
            manager._PollingTask.cancel()

        await asyncio.gather(
            *[t for t in (manager._CleanupTask, manager._GlobalSubscriberTask, manager._PollingTask) if t],
            return_exceptions=True
        )

        # Set the current running task as _GlobalSubscriberTask to simulate it triggering the disconnect
        current_task = asyncio.current_task()
        manager._GlobalSubscriberTask = current_task
        manager._CleanupTask = None
        manager._PollingTask = None

        # Disconnecting should trigger _stop_background_tasks_if_idle_locked
        # Since _GlobalSubscriberTask is the current task, it must not cancel/await itself
        await manager.disconnect("TCS", mock_ws)

        assert "TCS" not in manager._Connections
        assert manager._GlobalSubscriberTask is None
