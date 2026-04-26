import json
import asyncio
import os
from redis.asyncio import Redis
from domains.analytics.application.derivatives.pde_solver import CrankNicolsonPDE

class OptionsPricingSubscriber:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.consume_stream = "stream:options.raw_fetched"
        self.publish_stream = "stream:options.priced"
        self.pubsub_channel = "market.options_updated."

    async def start_consuming(self):
        last_id = "0"
        print("🎧 PDE Solver Engine listening for raw options data...")
        
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
        sigma = data["historical_volatility"]
        
        priced_chain = []
        
        # Run PDE Solver over the options chain
        for strike in data["strikes"]:
            # Call Price
            call_solver = CrankNicolsonPDE(S0, strike, T, r, sigma, 'call')
            call_price = call_solver.solve()
            
            # Put Price
            put_solver = CrankNicolsonPDE(S0, strike, T, r, sigma, 'put')
            put_price = put_solver.solve()
            
            priced_chain.append({
                "strike": strike,
                "fair_call": round(call_price, 2),
                "fair_put": round(put_price, 2)
            })
            
        # Publish Durable Event (for read-model updates)
        event_data = json.dumps({"symbol": symbol, "chain": priced_chain})
        await self.redis.xadd(self.publish_stream, {"data": event_data})
        
        # Publish Ephemeral Event (Live UX update)
        await self.redis.publish(f"{self.pubsub_channel}{symbol}", event_data)
        print(f"✅ Priced {len(priced_chain)} strikes for {symbol}. Surface published.")

async def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = Redis.from_url(redis_url)
    subscriber = OptionsPricingSubscriber(redis_client)
    await subscriber.start_consuming()

if __name__ == "__main__":
    asyncio.run(main())
