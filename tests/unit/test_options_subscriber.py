import unittest
import json
from unittest.mock import AsyncMock
import asyncio

from domains.analytics.infrastructure.options_subscriber import OptionsPricingSubscriber

class TestOptionsPricingSubscriber(unittest.IsolatedAsyncioTestCase):
    async def test_process_event(self):
        mock_redis = AsyncMock()
        subscriber = OptionsPricingSubscriber(mock_redis)

        # Mock payload from Redis Stream
        payload = {
            b"symbol": b"RELIANCE",
            b"data": json.dumps({
                "spot_price": 2500.0,
                "risk_free_rate": 0.065,
                "dividend_yield": 0.012,
                "time_to_maturity": 0.08,  # ~30 days
                "strikes_data": [
                    {"strike": 2500.0, "type": "CE", "iv": 0.18, "ltp": 45.0},
                    {"strike": 2500.0, "type": "PE", "iv": 0.19, "ltp": 42.0}
                ]
            }).encode("utf-8")
        }

        # Run process_event
        await subscriber.process_event(payload)

        # Check that it set cache in Redis
        mock_redis.set.assert_called_once()
        cache_key = mock_redis.set.call_args[0][0]
        self.assertIn("market:options:priced:RELIANCE", cache_key)

        cache_value = json.loads(mock_redis.set.call_args[0][1])
        self.assertEqual(cache_value["symbol"], "RELIANCE")
        self.assertEqual(len(cache_value["chain"]), 1)
        
        priced_strike = cache_value["chain"][0]
        self.assertEqual(priced_strike["strike"], 2500.0)
        self.assertIn("fair_call", priced_strike)
        self.assertIn("fair_put", priced_strike)
        self.assertIn("bs_fair_call", priced_strike)
        self.assertIn("bs_fair_put", priced_strike)
        self.assertEqual(priced_strike["live_call"], 45.0)
        self.assertEqual(priced_strike["live_put"], 42.0)

        # Verify BSM call/put fair values are correct and realistic
        self.assertTrue(40.0 < priced_strike["bs_fair_call"] < 80.0)
        self.assertTrue(30.0 < priced_strike["bs_fair_put"] < 60.0)

        # Check stream publishing
        mock_redis.xadd.assert_called_once()
        self.assertEqual(mock_redis.xadd.call_args[0][0], "stream:options.priced")

        # Check pubsub publishing
        mock_redis.publish.assert_called_once()
        self.assertIn("market.options_updated.RELIANCE", mock_redis.publish.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
