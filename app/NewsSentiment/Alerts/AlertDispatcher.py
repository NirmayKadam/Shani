# app/MarketSignals/AlertDispatcher.py
import logging
import aiohttp
import asyncio
import json
from app.Infrastructure.DatabaseClient import GetDatabasePool

Logger = logging.getLogger(__name__)

class AlertDispatcher:
    def __init__(self):
        # We'll use a short timeout for webhooks so we don't hold up the Celery worker
        self.Timeout = aiohttp.ClientTimeout(total=5)

    async def Dispatch(self, event_payload: dict) -> None:
        """
        Receives a Signal Event payload, looks up active webhook rules
        for the symbol, and fires off POST requests.
        """
        symbol = event_payload.get("symbol")
        if not symbol:
            return

        # 1. Fetch active webhooks for this symbol
        Pool = await GetDatabasePool()
        Query = """
            SELECT WebhookUrl 
            FROM AlertRules 
            WHERE Symbol = $1 AND IsActive = TRUE
        """
        Records = await Pool.fetch(Query, symbol)
        
        if not Records:
            Logger.debug(f"[{symbol}] No active webhooks found to dispatch alert.")
            return

        WebhookUrls = [r['webhookurl'] for r in Records if r['webhookurl']]
        if not WebhookUrls:
            return

        Logger.info(f"[{symbol}] Dispatching alert to {len(WebhookUrls)} webhooks...")

        # 2. Fire webhooks concurrently with strict rate limits (Max 50 sockets)
        Sem = asyncio.Semaphore(50)

        async def _BoundedWebhookCall(url: str):
            async with Sem:
                return await self._SendToWebhook(session, url, event_payload)

        async with aiohttp.ClientSession(timeout=self.Timeout) as session:
            tasks = [_BoundedWebhookCall(url) for url in WebhookUrls]
            resultados = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log any failures
            for url, res in zip(WebhookUrls, resultados):
                if isinstance(res, Exception):
                    Logger.error(f"Failed to deliver webhook to {url}: {res}")

    async def _SendToWebhook(self, session: aiohttp.ClientSession, url: str, payload: dict) -> None:
        headers = {"Content-Type": "application/json"}
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status >= 400:
                Logger.warning(f"Webhook {url} returned HTTP {resp.status}")
            else:
                Logger.debug(f"Webhook {url} delivered successfully.")
