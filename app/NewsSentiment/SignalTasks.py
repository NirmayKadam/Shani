# app/MarketSignals/Tasks.py
import asyncio
import logging
from app.CeleryApp import CeleryApp
from app.NewsSentiment.Alerts.SignalComposer import SignalComposer

Logger = logging.getLogger(__name__)

@CeleryApp.task(name='signals.compose_signal', queue='signals', bind=True)
def ComposeSignalTask(self, payload: dict):
    """
    Receives latest sentiment score payload from the NLP worker.
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(_ComposeSignalAsync(payload))
    except Exception as exc:
        Logger.error(f"ComposeSignalTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30, max_retries=3)

async def _ComposeSignalAsync(payload: dict):
    Composer = SignalComposer()
    SignalEvent = await Composer.ProcessNewSentiment(payload)
    
    if SignalEvent:
        # If the Composer generated a crossover event, emit to the Alert Dispatcher
        from app.MarketSignals.Tasks import DispatchAlertTask
        DispatchAlertTask.apply_async(
            args=[SignalEvent],
            queue='signals'
        )
        Logger.debug(f"Emitted DispatchAlertTask for {SignalEvent['symbol']}")

@CeleryApp.task(name='signals.dispatch_alert', queue='signals', bind=True)
def DispatchAlertTask(self, event_payload: dict):
    """
    Receives a triggered Signal Event and fires webhooks.
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(_DispatchAlertAsync(event_payload))
    except Exception as exc:
        Logger.error(f"DispatchAlertTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30, max_retries=3)

async def _DispatchAlertAsync(event_payload: dict):
    from app.NewsSentiment.Alerts.AlertDispatcher import AlertDispatcher
    Logger.info(f"🔔 ALERT DISPATCHER: Received event for {event_payload.get('symbol')} -> {event_payload.get('headline')}")
    
    Dispatcher = AlertDispatcher()
    await Dispatcher.Dispatch(event_payload)
