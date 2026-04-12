# app/DerivativesAnalytics/Tasks.py
#
# Celery tasks for the derivatives analytics engine.
# Runs on the 'derivatives' queue (see CeleryApp.py task_routes).

import asyncio
import logging
from app.CeleryApp import CeleryApp

Logger = logging.getLogger(__name__)


@CeleryApp.task(name='derivatives.process_tick_batch', queue='derivatives', bind=True)
def ProcessTickBatchTask(self, tick_dicts: list[dict]):
    """
    Receives a batch of tick dicts from the ingestion layer and
    runs them through the MetricsComputer (PCR + IV + Anomalies).
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_ProcessTickBatchAsync(tick_dicts))
    except Exception as exc:
        Logger.error(f"ProcessTickBatchTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=15, max_retries=3)


async def _ProcessTickBatchAsync(tick_dicts: list[dict]):
    from app.Derivatives.Analytics.MetricsComputer import MetricsComputer

    Computer = MetricsComputer()
    Summary = await Computer.ProcessTickBatch(tick_dicts)
    Logger.info(f"Tick batch processed: {Summary}")
