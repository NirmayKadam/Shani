# app/domain/api/routers/websocket.py — WebSocket /ws/{symbol} for real-time push
#
# When a client connects, subscribes to all relevant Redis Pub/Sub channels
# for that symbol and forwards events as JSON messages in real-time.

import json
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import GetSettings
from app.shared.constants import Channels

Logger = logging.getLogger(__name__)

Router = APIRouter()


class ConnectionManager:
    """Tracks active WebSocket connections per symbol."""

    def __init__(self):
        self._Connections: dict[str, list[WebSocket]] = {}

    async def connect(self, symbol: str, ws: WebSocket) -> None:
        await ws.accept()
        if symbol not in self._Connections:
            self._Connections[symbol] = []
        self._Connections[symbol].append(ws)
        Logger.info("WS connected: %s (total: %d)", symbol, len(self._Connections[symbol]))

    def disconnect(self, symbol: str, ws: WebSocket) -> None:
        if symbol in self._Connections:
            self._Connections[symbol] = [
                c for c in self._Connections[symbol] if c is not ws
            ]
            if not self._Connections[symbol]:
                del self._Connections[symbol]
        Logger.info("WS disconnected: %s", symbol)

    async def broadcast(self, symbol: str, message: dict) -> None:
        """Send a JSON message to all connected clients for a symbol."""
        connections = self._Connections.get(symbol, [])
        stale: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        # Clean up stale connections
        for ws in stale:
            self.disconnect(symbol, ws)


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

    # Start Redis Pub/Sub listener for this symbol
    listener_task = asyncio.create_task(
        _redis_listener(symbol_upper, websocket)
    )

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
        listener_task.cancel()
        _Manager.disconnect(symbol_upper, websocket)


async def _redis_listener(symbol: str, websocket: WebSocket):
    """Subscribe to Redis Pub/Sub channels and forward to WebSocket."""
    import redis.asyncio as aioredis

    try:
        from app.shared.redis_client import GetRedisClient
        redis = await GetRedisClient()

        # Create a dedicated pub/sub connection
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

        for ch in channels:
            await pubsub.subscribe(ch)

        Logger.info("WS Redis listener started for %s on %d channels", symbol, len(channels))

        # Channel-to-type mapping
        type_map = {
            Channels.HEADLINE_FETCHED.format(symbol=symbol): "headline",
            Channels.PRICE_UPDATED.format(symbol=symbol): "price",
            Channels.OPTIONS_UPDATED.format(symbol=symbol): "options",
            Channels.PRICE_TRIGGER.format(symbol=symbol): "trigger",
            Channels.SENTIMENT_SCORED.format(symbol=symbol): "sentiment",
            Channels.AGGREGATE_UPDATED.format(symbol=symbol): "aggregate",
        }

        async for message in pubsub.listen():
            if message["type"] != "message":
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
                await websocket.send_json({"type": msg_type, "data": payload})
            except (json.JSONDecodeError, Exception) as exc:
                Logger.debug("WS forward error: %s", exc)

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        Logger.error("Redis listener error for %s: %s", symbol, exc)
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:
            pass
