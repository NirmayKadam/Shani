# app/domain/api/routers/websocket.py — WebSocket /ws/{symbol} for real-time push
#
# When a client connects, subscribes to all relevant Redis Pub/Sub channels
# for that symbol and forwards events as JSON messages in real-time.

import json
import asyncio
import logging
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import GetSettings
from app.shared.constants import Channels

Logger = logging.getLogger(__name__)

Router = APIRouter()

_CLIENT_QUEUE_MAX_SIZE = 200
_CLIENT_SEND_TIMEOUT_SECONDS = 5.0
_CLIENT_MAX_DROPPED_MESSAGES = 25


@dataclass
class _ClientConnection:
    websocket: WebSocket
    queue: asyncio.Queue[dict]
    sender_task: asyncio.Task
    dropped_messages: int = 0


@dataclass
class _SymbolSubscription:
    task: asyncio.Task
    stop_event: asyncio.Event
    ref_count: int = 0


class ConnectionManager:
    """Tracks active WS clients and shared Redis subscriptions per symbol."""

    def __init__(self):
        self._Connections: dict[str, dict[WebSocket, _ClientConnection]] = {}
        self._Subscribers: dict[str, _SymbolSubscription] = {}
        self._Lock = asyncio.Lock()

    async def connect(self, symbol: str, ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_CLIENT_QUEUE_MAX_SIZE)
        sender_task = asyncio.create_task(self._sender_loop(symbol, ws, queue))

        async with self._Lock:
            if symbol not in self._Connections:
                self._Connections[symbol] = {}
            self._Connections[symbol][ws] = _ClientConnection(
                websocket=ws,
                queue=queue,
                sender_task=sender_task,
            )
            total = len(self._Connections[symbol])
            await self._acquire_subscription_locked(symbol)

        Logger.info("WS connected: %s (total: %d)", symbol, total)

    async def disconnect(self, symbol: str, ws: WebSocket, close_ws: bool = True) -> None:
        connection: _ClientConnection | None = None
        subscription: _SymbolSubscription | None = None

        async with self._Lock:
            by_symbol = self._Connections.get(symbol)
            if by_symbol and ws in by_symbol:
                connection = by_symbol.pop(ws)
                if not by_symbol:
                    del self._Connections[symbol]
                subscription = await self._release_subscription_locked(symbol)

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

        if subscription is not None:
            await self._stop_subscription(symbol, subscription)

        Logger.info("WS disconnected: %s", symbol)

    async def broadcast(self, symbol: str, message: dict) -> None:
        """
        Queue a JSON message to all connected clients for a symbol.

        Messages are queued with bounded backpressure controls to prevent
        slow consumers from affecting fast consumers.
        """
        stale: list[WebSocket] = []

        async with self._Lock:
            connections = list(self._Connections.get(symbol, {}).values())
            for conn in connections:
                try:
                    conn.queue.put_nowait(message)
                    continue
                except asyncio.QueueFull:
                    pass

                # Queue is full: drop oldest, keep newest.
                try:
                    conn.queue.get_nowait()
                    conn.queue.put_nowait(message)
                    conn.dropped_messages += 1
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    conn.dropped_messages += 1

                if conn.dropped_messages >= _CLIENT_MAX_DROPPED_MESSAGES:
                    stale.append(conn.websocket)

        for ws in stale:
            Logger.warning("Disconnecting slow WS client for symbol=%s", symbol)
            await self.disconnect(symbol, ws)

    async def _acquire_subscription_locked(self, symbol: str) -> None:
        subscription = self._Subscribers.get(symbol)
        if subscription is None:
            stop_event = asyncio.Event()
            task = asyncio.create_task(_redis_listener(symbol, stop_event))
            subscription = _SymbolSubscription(task=task, stop_event=stop_event)
            self._Subscribers[symbol] = subscription

        subscription.ref_count += 1
        Logger.info("Redis subscriber acquired: %s (ref_count=%d)", symbol, subscription.ref_count)

    async def _release_subscription_locked(self, symbol: str) -> _SymbolSubscription | None:
        subscription = self._Subscribers.get(symbol)
        if subscription is None:
            return None

        subscription.ref_count = max(0, subscription.ref_count - 1)
        Logger.info("Redis subscriber released: %s (ref_count=%d)", symbol, subscription.ref_count)

        if subscription.ref_count > 0:
            return None

        self._Subscribers.pop(symbol, None)
        return subscription

    async def _stop_subscription(self, symbol: str, subscription: _SymbolSubscription) -> None:
        subscription.stop_event.set()
        subscription.task.cancel()
        await asyncio.gather(subscription.task, return_exceptions=True)
        Logger.info("Redis subscriber stopped: %s", symbol)

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
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            Logger.debug("WS sender loop ended for %s: %s", symbol, exc)
        finally:
            # Ensure this websocket is fully cleaned up if sender loop exits.
            await self.disconnect(symbol, ws, close_ws=False)


_Manager = ConnectionManager()


@Router.websocket("/ws/{symbol}")
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
    cfg = GetSettings()
    allowed = cfg.GetWatchlistAsList()
    symbol_upper = symbol.strip().upper()

    if symbol_upper not in allowed:
        await websocket.close(code=4001, reason=f"Symbol {symbol_upper} not in watchlist")
        return

    await _Manager.connect(symbol_upper, websocket)

    try:
        # Keep connection alive — listen for client messages (ping/pong)
        while True:
            data = await websocket.receive_text()
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


async def _redis_listener(symbol: str, stop_event: asyncio.Event):
    """Subscribe once per symbol and fan out messages to all sockets."""
    pubsub = None
    try:
        from app.shared.redis_client import GetRedisClient
        redis = await GetRedisClient()

        # Create a dedicated pub/sub connection for a symbol subscriber.
        pubsub = redis.pubsub()

        # Subscribe to all channels for this symbol
        channels = [
            Channels.HEADLINE_FETCHED.format(symbol=symbol),
            Channels.PRICE_UPDATED.format(symbol=symbol),
            Channels.OPTIONS_UPDATED.format(symbol=symbol),
            Channels.PRICE_TRIGGER.format(symbol=symbol),
            Channels.SENTIMENT_SCORED.format(symbol=symbol),
            Channels.AGGREGATE_UPDATED.format(symbol=symbol),
        ]

        await pubsub.subscribe(*channels)

        Logger.info(
            "WS Redis listener started for %s on %d channels",
            symbol,
            len(channels),
        )

        # Channel-to-type mapping
        type_map = {
            Channels.HEADLINE_FETCHED.format(symbol=symbol): "headline",
            Channels.PRICE_UPDATED.format(symbol=symbol): "price",
            Channels.OPTIONS_UPDATED.format(symbol=symbol): "options",
            Channels.PRICE_TRIGGER.format(symbol=symbol): "trigger",
            Channels.SENTIMENT_SCORED.format(symbol=symbol): "sentiment",
            Channels.AGGREGATE_UPDATED.format(symbol=symbol): "aggregate",
        }

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

            data_str = message["data"]
            if isinstance(data_str, bytes):
                data_str = data_str.decode("utf-8")

            msg_type = type_map.get(channel, "unknown")

            try:
                payload = json.loads(data_str)
                await _Manager.broadcast(symbol, {"type": msg_type, "data": payload})
            except (json.JSONDecodeError, Exception) as exc:
                Logger.debug("WS forward error: %s", exc)

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        Logger.error("Redis listener error for %s: %s", symbol, exc)
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
