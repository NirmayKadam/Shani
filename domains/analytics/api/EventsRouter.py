# domains/analytics/api/EventsRouter.py — WebSocket /ws/{symbol} for real-time push
#
# When a client connects, subscribes to all relevant Redis Pub/Sub channels
# for that symbol and forwards events as JSON messages in real-time.

import json
import asyncio
import logging
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import GetSettings
from shared.constants import Channels

Logger = logging.getLogger(__name__)

router = APIRouter()

_CLIENT_QUEUE_MAX_SIZE = 200
_CLIENT_SEND_TIMEOUT_SECONDS = 5.0
_CLIENT_MAX_DROPPED_MESSAGES = 25
_CLIENT_STALE_SECONDS = 120.0
_CLEANUP_INTERVAL_SECONDS = 15.0


@dataclass
class _ClientConnection:
    websocket: WebSocket
    queue: asyncio.Queue[dict]
    sender_task: asyncio.Task
    dropped_messages: int = 0
    last_activity_ts: float = 0.0


class ConnectionManager:
    """Tracks active WS clients and a shared Redis subscription fan-out."""

    def __init__(self):
        self._Connections: dict[str, dict[WebSocket, _ClientConnection]] = {}
        self._GlobalSubscriberTask: asyncio.Task | None = None
        self._GlobalSubscriberStopEvent: asyncio.Event | None = None
        self._CleanupTask: asyncio.Task | None = None
        self._CleanupStopEvent: asyncio.Event | None = None
        self._Lock = asyncio.Lock()

    async def connect(self, symbol: str, ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_CLIENT_QUEUE_MAX_SIZE)
        sender_task = asyncio.create_task(self._sender_loop(symbol, ws, queue))
        now = asyncio.get_running_loop().time()

        async with self._Lock:
            if symbol not in self._Connections:
                self._Connections[symbol] = {}
            self._Connections[symbol][ws] = _ClientConnection(
                websocket=ws,
                queue=queue,
                sender_task=sender_task,
                last_activity_ts=now,
            )
            total = len(self._Connections[symbol])
            await self._ensure_background_tasks_locked()

        Logger.info("WS connected: %s (total: %d)", symbol, total)

    async def disconnect(self, symbol: str, ws: WebSocket, close_ws: bool = True) -> None:
        connection: _ClientConnection | None = None

        async with self._Lock:
            by_symbol = self._Connections.get(symbol)
            if by_symbol and ws in by_symbol:
                connection = by_symbol.pop(ws)
                if not by_symbol:
                    del self._Connections[symbol]
                await self._stop_background_tasks_if_idle_locked()

        if close_ws:
            try:
                await ws.close()
            except Exception:
                pass

        if connection is not None:
            current = asyncio.current_task()
            if connection.sender_task is not current and not connection.sender_task.done():
                connection.sender_task.cancel()
                await asyncio.gather(connection.sender_task, return_exceptions=True)

        Logger.info("WS disconnected: %s", symbol)

    async def mark_client_alive(self, symbol: str, ws: WebSocket) -> None:
        now = asyncio.get_running_loop().time()
        async with self._Lock:
            conn = self._Connections.get(symbol, {}).get(ws)
            if conn is not None:
                conn.last_activity_ts = now

    async def broadcast(self, symbol: str, message: dict) -> None:
        """
        Queue a JSON message to all connected clients for a symbol.

        Messages are queued with bounded backpressure controls to prevent
        slow consumers from affecting fast consumers.
        """
        stale: list[WebSocket] = []

        async with self._Lock:
            connections = list(self._Connections.get(symbol, {}).values())
            now = asyncio.get_running_loop().time()
            for conn in connections:
                try:
                    conn.queue.put_nowait(message)
                    conn.last_activity_ts = now
                    continue
                except asyncio.QueueFull:
                    pass

                # Queue is full: drop oldest, keep newest.
                try:
                    conn.queue.get_nowait()
                    conn.queue.put_nowait(message)
                    conn.dropped_messages += 1
                    conn.last_activity_ts = now
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    conn.dropped_messages += 1

                if conn.dropped_messages >= _CLIENT_MAX_DROPPED_MESSAGES:
                    stale.append(conn.websocket)

        for ws in stale:
            Logger.warning("Disconnecting slow WS client for symbol=%s", symbol)
            await self.disconnect(symbol, ws)

    async def _ensure_background_tasks_locked(self) -> None:
        if self._GlobalSubscriberTask is None or self._GlobalSubscriberTask.done():
            self._GlobalSubscriberStopEvent = asyncio.Event()
            self._GlobalSubscriberTask = asyncio.create_task(
                _redis_global_listener(self._GlobalSubscriberStopEvent)
            )
            Logger.info("WS global Redis subscriber started")

        if self._CleanupTask is None or self._CleanupTask.done():
            self._CleanupStopEvent = asyncio.Event()
            self._CleanupTask = asyncio.create_task(self._cleanup_loop(self._CleanupStopEvent))
            Logger.info("WS stale-client cleanup loop started")

    async def _stop_background_tasks_if_idle_locked(self) -> None:
        if self._Connections:
            return

        subscriber_task = self._GlobalSubscriberTask
        subscriber_stop = self._GlobalSubscriberStopEvent
        cleanup_task = self._CleanupTask
        cleanup_stop = self._CleanupStopEvent

        self._GlobalSubscriberTask = None
        self._GlobalSubscriberStopEvent = None
        self._CleanupTask = None
        self._CleanupStopEvent = None

        if subscriber_stop is not None:
            subscriber_stop.set()
        if cleanup_stop is not None:
            cleanup_stop.set()

        tasks = [t for t in (subscriber_task, cleanup_task) if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            Logger.info("WS background tasks stopped (no active clients)")

    async def _sender_loop(
        self,
        symbol: str,
        ws: WebSocket,
        queue: asyncio.Queue[dict],
    ) -> None:
        try:
            while True:
                message = await queue.get()
                await asyncio.wait_for(
                    ws.send_json(message),
                    timeout=_CLIENT_SEND_TIMEOUT_SECONDS,
                )
                await self.mark_client_alive(symbol, ws)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            Logger.debug("WS sender loop ended for %s: %s", symbol, exc)
        finally:
            # Ensure this websocket is fully cleaned up if sender loop exits.
            await self.disconnect(symbol, ws, close_ws=False)

    async def _cleanup_loop(self, stop_event: asyncio.Event) -> None:
        try:
            loop = asyncio.get_running_loop()
            while not stop_event.is_set():
                await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
                now = loop.time()
                stale_clients: list[tuple[str, WebSocket]] = []

                async with self._Lock:
                    for symbol, by_socket in self._Connections.items():
                        for ws, conn in by_socket.items():
                            idle_seconds = now - conn.last_activity_ts
                            if idle_seconds >= _CLIENT_STALE_SECONDS:
                                stale_clients.append((symbol, ws))

                for symbol, ws in stale_clients:
                    Logger.info("Disconnecting stale WS client for %s", symbol)
                    await self.disconnect(symbol, ws)
        except asyncio.CancelledError:
            pass


_Manager = ConnectionManager()


@router.websocket("/ws/{symbol}")
async def WebSocketEndpoint(websocket: WebSocket, symbol: str):
    """
    Real-time WebSocket endpoint for a symbol.

    Subscribes to Redis Pub/Sub channels and pushes events:
        - {"type": "headline", "data": {...}}
        - {"type": "price", "data": {...}}
        - {"type": "sentiment", "data": {...}}
        - {"type": "options", "data": {...}}
        - {"type": "trigger", "data": {...}}
    """
    # Validate symbol format and existence
    from shared.utils.symbol_validator import SymbolValidator
    if not SymbolValidator.validate(symbol_upper):
        await websocket.close(code=4001, reason=f"Symbol {symbol_upper} is invalid or not supported")
        return

    symbol_clean = SymbolValidator.get_clean_symbol(symbol_upper)
    await _Manager.connect(symbol_clean, websocket)

    try:
        # Keep connection alive — listen for client messages (ping/pong)
        while True:
            data = await websocket.receive_text()
            await _Manager.mark_client_alive(symbol_upper, websocket)
            # Client can send {"action": "ping"} to keep alive
            if data:
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        Logger.info("WebSocket client disconnected: %s", symbol_upper)
    except Exception as exc:
        Logger.error("WebSocket error for %s: %s", symbol_upper, exc)
    finally:
        await _Manager.disconnect(symbol_upper, websocket)


def _derive_type_and_symbol(channel: str) -> tuple[str, str]:
    """Map Redis channel name to event type and symbol."""
    prefixes = {
        "headlines.fetched.": "headline",
        "market.price_updated.": "price",
        "market.options_updated.": "options",
        "market.price_trigger.": "trigger",
        "sentiment.scored.": "sentiment",
        "sentiment.aggregate_updated.": "aggregate",
    }
    for prefix, msg_type in prefixes.items():
        if channel.startswith(prefix):
            symbol = channel[len(prefix):].upper()
            return msg_type, symbol
    return "unknown", ""


async def _redis_global_listener(stop_event: asyncio.Event):
    """Subscribe once globally and fan out messages by symbol."""
    pubsub = None
    try:
        from shared.infrastructure.redis_client import GetRedisClient
        redis = await GetRedisClient()

        # Create one shared pub/sub connection for all WS clients.
        pubsub = redis.pubsub()

        patterns = [
            Channels.HEADLINE_FETCHED.format(symbol="*"),
            Channels.PRICE_UPDATED.format(symbol="*"),
            Channels.OPTIONS_UPDATED.format(symbol="*"),
            Channels.PRICE_TRIGGER.format(symbol="*"),
            Channels.SENTIMENT_SCORED.format(symbol="*"),
            Channels.AGGREGATE_UPDATED.format(symbol="*"),
        ]

        await pubsub.psubscribe(*patterns)

        Logger.info(
            "WS global Redis listener started on %d channel patterns",
            len(patterns),
        )

        while not stop_event.is_set():
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message is None:
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")
            if not isinstance(channel, str):
                continue

            data_str = message["data"]
            if isinstance(data_str, bytes):
                data_str = data_str.decode("utf-8")

            msg_type, symbol = _derive_type_and_symbol(channel)
            if not symbol:
                continue

            try:
                payload = json.loads(data_str)
                await _Manager.broadcast(symbol, {"type": msg_type, "data": payload})
            except (json.JSONDecodeError, Exception) as exc:
                Logger.debug("WS forward error: %s", exc)

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        Logger.error("Global Redis listener error: %s", exc)
    finally:
        if pubsub is not None:
            try:
                await pubsub.punsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
