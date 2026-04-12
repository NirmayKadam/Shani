# app/MachineLearning/Tasks.py
#
# Celery tasks for the Phase 5 ML Engine.

import os
import asyncio
import logging
from app.CeleryApp import CeleryApp
from app.MLForecasting.Inference.DailyPredictor import DailyPredictor

Logger = logging.getLogger(__name__)

_WATCHLIST_RAW = os.getenv("WATCHLIST_SYMBOLS", "NIFTY,BANKNIFTY,RELIANCE,INFY,HDFCBANK,TCS,ICICIBANK,AXISBANK").split(",")
_WATCHLIST = [s.strip() for s in _WATCHLIST_RAW if s.strip()]


@CeleryApp.task(name='ml.run_daily_predictions', queue='nlp', bind=True)
def RunDailyPredictionsTask(self):
    """
    Periodic task triggered by Celery Beat at 3:45 PM IST (Market Close).
    Iterates through the watchlist, generates ML forecasts for tomorrow,
    deposits them in Redis, and emits high-confidence webhooks via signals queue.
    """
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(_RunAllPredictionsAsync())
    except Exception as exc:
        Logger.error(f"RunDailyPredictionsTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60, max_retries=3)


async def _RunAllPredictionsAsync():
    from app.NewsSentiment.SignalTasks import DispatchAlertTask

    Logger.info(f"Running End-Of-Day ML Pipeline for {_WATCHLIST}")

    for Symbol in _WATCHLIST:
        Prediction = await DailyPredictor.PredictNextDay(Symbol)

        if not Prediction:
            continue

        ProbUp = Prediction["up_probability"]
        ProbDown = Prediction["down_probability"]

        # ── High Confidence Alerts ──
        # If the model is extremely confident (> 70%), fire a webhook
        IsHighConviction = False
        Headline = ""
        Confidence = 0.0

        if ProbUp >= 0.70:
            IsHighConviction = True
            Confidence = ProbUp
            Headline = f"🤖 AI PREDICTION (High Conviction): {Symbol} is projected BULLISH for tomorrow. (Confidence: {ProbUp:.1%})"
        elif ProbDown >= 0.70:
            IsHighConviction = True
            Confidence = ProbDown
            Headline = f"🤖 AI PREDICTION (High Conviction): {Symbol} is projected BEARISH for tomorrow. (Confidence: {ProbDown:.1%})"

        if IsHighConviction:
            # Format the event for the existing AlertDispatcher
            Event = {
                "symbol": Symbol.upper(),
                "event_type": "PREDICTION_BULLISH" if ProbUp >= 0.70 else "PREDICTION_BEARISH",
                "headline": Headline,
                "confidence": Confidence,
            }

            # Ship to AlertDispatcher
            DispatchAlertTask.apply_async(args=[Event], queue='signals')
            Logger.info(f"Emitted high-conviction ML alert for {Symbol}")

        # Sleep to avoid smashing YFinance API
        await asyncio.sleep(2.0)
