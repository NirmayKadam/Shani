"""
File Overview: Outbound adapter wrapping Hugging Face NLP model (FinBERT) service.
"""
import logging

logger = logging.getLogger(__name__)


class HuggingFaceAdapter:
    def __init__(self):
        from domains.analytics.application.services.nlp.finbert_engine_service import FinBertEngineService
        self._engine = FinBertEngineService.get_instance()
        
    async def score_batch(self, texts: list[str]) -> list[dict]:
        return await self._engine.score_batch(texts)
