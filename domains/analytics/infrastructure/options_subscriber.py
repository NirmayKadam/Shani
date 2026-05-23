"""
File Overview: PDE Solver worker consuming options data from Redis Streams.
Calculates fair prices using Crank-Nicolson finite difference method.

All Functions/Classes:
- OptionsPricingSubscriber: Real-time derivatives pricing engine. Data: raw ticks -> priced chains.
- start_consuming: Async listen loop. Data: Redis stream data -> process_event.
- process_event: Core orchestrator. Data: raw payload -> Redis Streams/PubSub.
- main: Entry point coroutine. Data: Environment config -> Engine bootstrap.

Endpoints/APIs: None

Database Tables:
- Redis (Streams: stream:options.raw_fetched -> stream:options.priced, PubSub).
"""
import json
import asyncio
import logging
import os

from redis.asyncio import Redis
from domains.analytics.application.derivatives.pde_solver import CrankNicolsonPDE

logger = logging.getLogger("options_pricing_subscriber")


class OptionsPricingSubscriber:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.consume_stream = "stream:options.raw_fetched"
        self.publish_stream = "stream:options.priced"
        self.pubsub_channel = "market.options_updated."

    async def start_consuming(self):
        # Use "$" to only read new messages (not replay history on restart)
        last_id = "$"
        logger.info("PDE Solver Engine listening for raw options data...")

        while True:
            # Block and wait for new raw options data
            events = await self.redis.xread({self.consume_stream: last_id}, count=1, block=5000)

            for stream, messages in events:
                for message_id, payload in messages:
                    await self.process_event(payload)
                    last_id = message_id

    async def process_event(self, payload: dict):
        symbol = payload[b"symbol"].decode("utf-8")
        data = json.loads(payload[b"data"].decode("utf-8"))

        S0 = data["spot_price"]
        r = data["risk_free_rate"]
        T = data["time_to_maturity"]

        # Group strikes by price to solve CE/PE together
        strikes_map = {}
        for s in data.get("strikes_data", []):
            st = s["strike"]
            if st not in strikes_map:
                strikes_map[st] = {}
            strikes_map[st][s["type"]] = s["iv"]

        priced_chain = []

        for strike, ivs in strikes_map.items():
            # Use specific IV if available, else fallback to 20%
            call_iv = ivs.get("CE", 0.20)
            put_iv = ivs.get("PE", 0.20)

            # Call Price
            call_solver = CrankNicolsonPDE(S0, strike, T, r, call_iv, 'call')
            call_price = call_solver.solve()

            # Put Price
            put_solver = CrankNicolsonPDE(S0, strike, T, r, put_iv, 'put')
            put_price = put_solver.solve()

            priced_chain.append({
                "strike": strike,
                "fair_call": round(call_price, 2),
                "fair_put": round(put_price, 2),
                "call_iv": call_iv,
                "put_iv": put_iv
            })

        # Publish Durable Event (for read-model updates)
        event_data = json.dumps({"symbol": symbol, "chain": priced_chain})
        await self.redis.xadd(self.publish_stream, {"data": event_data})

        # Publish Ephemeral Event (Live UX update)
        await self.redis.publish(f"{self.pubsub_channel}{symbol}", event_data)
        logger.info("Priced %d strikes for %s. Surface published.", len(priced_chain), symbol)


async def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = Redis.from_url(redis_url)
    subscriber = OptionsPricingSubscriber(redis_client)
    await subscriber.start_consuming()


if __name__ == "__main__":
    asyncio.run(main())
