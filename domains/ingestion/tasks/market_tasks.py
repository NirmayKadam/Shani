"""
File Overview: Celery tasks for advanced market data fetching and stream publishing.
Fetches option chain from internal NSE proxy API, persists to TimescaleDB, and publishes
to Redis Streams for PDE solver consumption.
Uses persistent event loop per worker thread (shared with ingestion_tasks).

All Functions/Classes:
- _fetch_and_publish_options_async: Core logic for chain retrieval and publishing.
    Data: symbol -> raw chain -> TimescaleDB + Redis Stream.
- fetch_and_publish_options: Celery task wrapper. Data: symbol -> async fetcher.

Endpoints/APIs: GET /v1/ingestion/options/{symbol} (Internal proxy, consumed by this task)

Database Tables: TimescaleDB (tickdata), Redis (Streams: stream:options.raw_fetched)
"""
import json
import logging
import asyncio
from celery import shared_task
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import Streams

# Reuse persistent loop from ingestion_tasks
from domains.ingestion.tasks.ingestion_tasks import _get_or_create_loop

logger = logging.getLogger(__name__)


async def _fetch_and_publish_options_async(symbol: str):
    from shared.infrastructure.database import get_database_pool
    from datetime import datetime, timezone
    from domains.ingestion.infrastructure.outbound.adapter_factory import get_market_data_adapter
    from domains.ingestion.application.services.ingestion_service import build_option_chain_snapshot
    from shared.constants import RedisKeys, TTL
    from shared.utils.market_time import nearest_expiry, parse_expiry, years_to_expiry, risk_free_rate_for

    redis = await get_redis_client()
    db_pool = await get_database_pool()
    adapter = get_market_data_adapter(redis_client=redis)

    try:
        dtos = await adapter.fetch_option_chain(symbol)

        if not dtos:
            logger.warning("[%s] No option chain data", symbol)
            return

        # Single writer for the raw chain read model (PCR, expiries, /pricer cache)
        snapshot = build_option_chain_snapshot(symbol, dtos)
        await redis.set(
            RedisKeys.MARKET_OPTIONS.format(symbol=symbol.upper()),
            json.dumps(snapshot, default=str),
            ex=TTL.MARKET_OPTIONS,
        )

        # Fetch dividend yield dynamically from the yfinance adapter
        price_info = await adapter.fetch_price(symbol)
        dividend_yield = price_info.get("dividend_yield", 0.0) if price_info else 0.0

        S0 = dtos[0].underlying_price
        timestamp = datetime.now(timezone.utc)

        # Price only the nearest live expiry: strikes from different expiries need different T
        # and would otherwise collide in the strike-keyed pricing map.
        pricing_expiry = nearest_expiry(d.expiry for d in dtos)
        T = years_to_expiry(pricing_expiry) if pricing_expiry else None
        if T is None:
            logger.warning("[%s] No parseable live expiry in chain; skipping pricing", symbol)

        strikes_payload = []
        db_records = []
        for dto in dtos:
            # Every expiry is persisted to TimescaleDB
            db_records.append((
                timestamp, symbol, "NSE", dto.option_type, dto.ltp, dto.oi, dto.volume,
                parse_expiry(dto.expiry), dto.strike, dto.iv, S0
            ))

            # Near-the-money (+/- 10%) strikes of the pricing expiry go to the PDE solver
            if T is not None and dto.expiry == pricing_expiry and dto.strike and S0 * 0.9 <= dto.strike <= S0 * 1.1:
                strikes_payload.append({
                    "strike": dto.strike,
                    "type": dto.option_type,
                    "iv": dto.iv,
                    "ltp": dto.ltp
                })

        # 1. Bulk Insert into TimescaleDB
        if db_records:
            async with db_pool.acquire() as conn:
                await conn.copy_records_to_table(
                    'tickdata',
                    records=db_records,
                    columns=[
                        'timestamp', 'symbol', 'exchange', 'instrumenttype', 'lastprice',
                        'openinterest', 'volume', 'expirydate', 'strikeprice', 'impliedvolatility', 'underlyingprice'
                    ]
                )

        if not strikes_payload:
            return

        # 2. Publish to Redis Stream for PDE Solver
        payload = {
            "spot_price": S0,
            "risk_free_rate": risk_free_rate_for(symbol),
            "dividend_yield": dividend_yield,
            "time_to_maturity": T,
            "expiry": pricing_expiry,
            "strikes_data": strikes_payload
        }

        await redis.xadd(Streams.OPTIONS_RAW_FETCHED, {
            "symbol": symbol,
            "data": json.dumps(payload)
        })
        logger.debug("Published raw options for %s: %d ticks saved to DB, %d strikes to stream.",
                     symbol, len(db_records), len(strikes_payload))

    except Exception as e:
        logger.error("Error fetching/publishing options for %s: %s", symbol, e, exc_info=True)
    finally:
        await adapter.close()


@shared_task(queue='ingestion', name='ingestion.fetch_and_publish_options')
def fetch_and_publish_options(symbol: str = "NIFTY"):
    """
    Pulls raw chain from NSE wrapper and drops it into Redis Streams.
    """
    loop = _get_or_create_loop()
    loop.run_until_complete(_fetch_and_publish_options_async(symbol))
