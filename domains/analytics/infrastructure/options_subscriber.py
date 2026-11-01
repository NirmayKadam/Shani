"""
File Overview: PDE Solver worker consuming options data from Redis Streams.
Calculates fair prices using Crank-Nicolson finite difference method.
The chain is priced with batched Crank-Nicolson solves (price_chain_cn: every contract in one
block-diagonal system per time step), split into chunks across a process pool: the solver loop
holds the GIL, so threads give no speed-up, while separate processes run in parallel.
Black-Scholes prices are computed vectorised in-process.

All Functions/Classes:
- OptionsPricingSubscriber: Real-time derivatives pricing engine. Data: raw ticks -> priced chains.
- start_consuming: Async listen loop. Data: Redis stream data -> process_event.
- process_event: Core orchestrator. Data: raw payload -> Redis Streams/PubSub.
- close: Shuts down the owned process pool.
- main: Entry point coroutine. Data: Environment config -> Engine bootstrap.

Environment:
- PRICING_WORKERS: process pool size (default: CPU count - 1, minimum 1).

Endpoints/APIs: None

Database Tables:
- Redis (Streams: stream:options.raw_fetched -> stream:options.priced, PubSub).
"""
import json
import asyncio
import logging
import multiprocessing
import os
from concurrent.futures import Executor, ProcessPoolExecutor
from datetime import datetime, timezone

from redis.asyncio import Redis
import numpy as np

from domains.analytics.domain.services.pde_solver import price_chain_cn
from domains.analytics.application.services.derivatives.black_scholes import bsm_prices
from shared.constants import RedisKeys, TTL, Streams, StreamGroups, Channels
from shared.infrastructure.event_bus.consumer import run_durable_consumer
from shared.infrastructure.event_bus.streams import DurableEventStream

logger = logging.getLogger("options_pricing_subscriber")


def _default_worker_count() -> int:
    """Pool size from PRICING_WORKERS, else leave one core for the event loop and other services."""
    configured = os.getenv("PRICING_WORKERS")
    if configured:
        return max(1, int(configured))
    return max(1, (os.cpu_count() or 2) - 1)


# A chain is split into at most PRICING_WORKERS chunks of at least this many contracts; each
# chunk is one batched Crank-Nicolson solve (smaller chunks lose more to process overhead).
_MIN_CONTRACTS_PER_CHUNK = 16


def _valid_iv(iv) -> bool:
    return iv is not None and iv > 0


def _price_chunk_sync(S0: float, T: float, r: float, q: float, strikes: list, sigmas: list, is_call: list) -> list:
    """Crank-Nicolson prices for a chunk of contracts, run in a pool worker process."""
    return price_chain_cn(S0, T, r, strikes, sigmas, is_call, q=q).tolist()


def _atm_iv_pct(S0: float, priced_chain: list):
    """At-the-money implied volatility in percent: the call IV of the strike nearest spot."""
    candidates = [row for row in priced_chain if row.get("call_iv")]
    if not candidates:
        return None
    atm = min(candidates, key=lambda row: abs(row["strike"] - S0))
    return round(atm["call_iv"] * 100.0, 4)


class OptionsPricingSubscriber:
    def __init__(self, redis_client: Redis, executor: Executor | None = None):
        self.redis = redis_client
        self.consume_stream = Streams.OPTIONS_RAW_FETCHED
        self.publish_stream = Streams.OPTIONS_PRICED
        self.pubsub_channel = Channels.OPTIONS_UPDATED
        # An injected executor is owned by the caller; otherwise a process pool is created on first use.
        self._executor = executor
        self._owns_executor = executor is None

    def _get_executor(self) -> Executor:
        if self._executor is None:
            workers = _default_worker_count()
            # spawn, not fork: the pool is created inside a running event loop with open Redis sockets.
            self._executor = ProcessPoolExecutor(
                max_workers=workers, mp_context=multiprocessing.get_context("spawn")
            )
            logger.info("Pricing process pool started with %d workers", workers)
        return self._executor

    def close(self) -> None:
        if self._owns_executor and self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    async def start_consuming(self, stop_event: asyncio.Event | None = None):
        """At-least-once consumption through a consumer group: a chain published while this
        process is down is priced after restart, and a failing chain is retried twice, then
        dead-lettered to Streams.OPTIONS_RAW_FETCHED_DLQ."""
        logger.info("PDE Solver Engine listening for raw options data...")
        await run_durable_consumer(
            self.redis,
            stream=self.consume_stream,
            group=StreamGroups.OPTIONS_PRICING,
            dlq_stream=Streams.OPTIONS_RAW_FETCHED_DLQ,
            handler=self.process_event,
            max_retries=2,
            batch_size=1,
            stop_event=stop_event,
        )

    async def _price_chain_pde(self, S0, T, r, q, strikes, sigmas, is_call) -> list:
        """Batched Crank-Nicolson prices, split into one chunk per pool worker."""
        executor = self._get_executor()
        workers = getattr(executor, "_max_workers", 1) or 1
        chunks = max(1, min(workers, len(strikes) // _MIN_CONTRACTS_PER_CHUNK))
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                executor, _price_chunk_sync, S0, T, r, q,
                [strikes[i] for i in idx], [sigmas[i] for i in idx], [is_call[i] for i in idx],
            )
            for idx in np.array_split(np.arange(len(strikes)), chunks)
        ]
        return [price for chunk in await asyncio.gather(*tasks) for price in chunk]

    async def process_event(self, message: dict):
        """Price one raw chain. message = {"symbol": str, "data": {spot_price, ..., strikes_data}}."""
        symbol = str(message["symbol"]).upper()
        data = message["data"]

        S0 = data["spot_price"]
        r = data["risk_free_rate"]
        T = data["time_to_maturity"]
        dividend_yield = data.get("dividend_yield", 0.0)

        # Group strikes by price to solve CE/PE together
        strikes_map = {}
        for s in data.get("strikes_data", []):
            strike = s["strike"]
            if strike not in strikes_map:
                strikes_map[strike] = {}
            strikes_map[strike][s["type"]] = {
                "iv": s.get("iv"),
                "ltp": s.get("ltp", 0.0)
            }

        # Legs with a usable implied volatility; the others stay unpriced (None)
        legs = [
            (strike, opt_type, leg["iv"])
            for strike, types in strikes_map.items()
            for opt_type, leg in types.items()
            if opt_type in ("CE", "PE") and _valid_iv(leg["iv"])
        ]
        prices: dict[tuple, tuple] = {}
        if legs:
            strikes = [leg[0] for leg in legs]
            sigmas = [leg[2] for leg in legs]
            is_call = [leg[1] == "CE" for leg in legs]
            pde = await self._price_chain_pde(S0, T, r, dividend_yield, strikes, sigmas, is_call)
            bsm = bsm_prices(S0, strikes, T, r, sigmas, is_call, q=dividend_yield)
            prices = {(leg[0], leg[1]): (round(p, 2), round(float(b), 2)) for leg, p, b in zip(legs, pde, bsm)}

        priced_chain = []
        for strike, types in strikes_map.items():
            call, put = types.get("CE", {}), types.get("PE", {})
            fair_call, bs_fair_call = prices.get((strike, "CE"), (None, None))
            fair_put, bs_fair_put = prices.get((strike, "PE"), (None, None))
            priced_chain.append({
                "strike": strike,
                "fair_call": fair_call,
                "fair_put": fair_put,
                "call_iv": call.get("iv") if _valid_iv(call.get("iv")) else None,
                "put_iv": put.get("iv") if _valid_iv(put.get("iv")) else None,
                "bs_fair_call": bs_fair_call,
                "bs_fair_put": bs_fair_put,
                "live_call": round(call.get("ltp") or 0.0, 2),
                "live_put": round(put.get("ltp") or 0.0, 2),
            })
        last_updated = datetime.now(timezone.utc).isoformat()

        # Cache in Redis for high performance read-model API querying
        cache_key = RedisKeys.MARKET_OPTIONS_PRICED.format(symbol=symbol)
        cache_payload = {
            "symbol": symbol,
            "chain": priced_chain,
            "last_updated": last_updated
        }
        await self.redis.set(cache_key, json.dumps(cache_payload), ex=TTL.MARKET_OPTIONS_PRICED)

        # Publish Durable Event: the priced chain plus the symbol-level snapshot alerts evaluate
        event = {
            "symbol": symbol,
            "spot_price": S0,
            "atm_iv_pct": _atm_iv_pct(S0, priced_chain),
            "expiry": data.get("expiry"),
            "last_updated": last_updated,
            "chain": priced_chain,
        }
        await DurableEventStream(self.redis).publish(self.publish_stream, event)

        # Publish Ephemeral Event (Live UX update). Browsers only use it as a "refetch" signal, so
        # a small notification replaces the full chain that used to be fanned out to every socket.
        await self.redis.publish(
            self.pubsub_channel.format(symbol=symbol),
            json.dumps({"symbol": symbol, "last_updated": last_updated}),
        )
        logger.debug("Priced %d strikes for %s. Surface published.", len(priced_chain), symbol)


async def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = Redis.from_url(redis_url)
    subscriber = OptionsPricingSubscriber(redis_client)
    try:
        await subscriber.start_consuming()
    finally:
        subscriber.close()
        await redis_client.aclose()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
