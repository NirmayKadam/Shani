# app/DataIngestion/Tasks.py
#
# Celery tasks for data ingestion workers.
# Runs on the 'ingestion' queue (see CeleryApp.py task_routes).

import asyncio
import logging
from app.CeleryApp import CeleryApp

Logger = logging.getLogger(__name__)


@CeleryApp.task(name='ingestion.run_news_cycle', queue='ingestion', bind=True)
def RunIngestionCycleTask(self):
    """
    Periodic task (triggered by Celery Beat) that runs a single
    news ingestion cycle for all watchlist symbols.
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_RunNewsIngestionAsync())
    except Exception as exc:
        Logger.error(f"RunIngestionCycleTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60, max_retries=3)


async def _RunNewsIngestionAsync():
    from app.NewsSentiment.Ingestion.NewsIngestor import NewsIngestor

    Ingestor = NewsIngestor()
    await Ingestor.Initialise()
    try:
        Results = await Ingestor.IngestAll()
        Logger.info(f"News ingestion cycle complete: {Results}")
    finally:
        await Ingestor.Shutdown()


@CeleryApp.task(name='ingestion.run_tick_cycle', queue='ingestion', bind=True)
def RunTickIngestionTask(self):
    """
    Periodic task (triggered by Celery Beat) that runs a single
    tick ingestion cycle — pulls ticks from broker (or mock) and
    dispatches them to the derivatives queue.
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_RunTickIngestionAsync())
    except Exception as exc:
        Logger.error(f"RunTickIngestionTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30, max_retries=3)


async def _RunTickIngestionAsync():
    from app.Derivatives.Ingestion.TickIngestor import TickIngestor

    Ingestor = TickIngestor()
    await Ingestor.Initialise()
    try:
        Ticks = await Ingestor.IngestOnce()
        Logger.info(f"Tick ingestion cycle complete: {len(Ticks)} ticks processed")
    finally:
        await Ingestor.Shutdown()
