# app/domain/sentiment/finbert_engine.py — FinBERT NLP model singleton
#
# Loads the ProsusAI/finbert model once and provides async batch scoring.
# Thread-safe: inference runs in a thread pool so the event loop stays responsive.

import torch
import asyncio
import logging
import time
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

Logger = logging.getLogger(__name__)


class FinBertEngine:
    """
    Singleton — load once, reuse forever.

    Usage:
        engine = FinBertEngine.get_instance()
        results = await engine.score_batch(["Good quarterly results", "Market crashes"])
    """

    _Instance: Optional['FinBertEngine'] = None
    _ModelName = 'ProsusAI/finbert'
    _LabelMap = {
        'positive': 'BULLISH',
        'negative': 'BEARISH',
        'neutral':  'NEUTRAL',
    }
    _MaxBatchSize = 32
    _MaxTokenLength = 512

    def __init__(self, cache_path: Optional[str] = None):
        Logger.info('Loading FinBERT model: %s', self._ModelName)
        start = time.monotonic()

        kwargs = {'pretrained_model_name_or_path': self._ModelName}
        if cache_path:
            kwargs['cache_dir'] = cache_path

        self._Tokenizer = AutoTokenizer.from_pretrained(**kwargs)
        self._Model = AutoModelForSequenceClassification.from_pretrained(**kwargs)
        self._Model.eval()
        self._Executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='finbert')
        self._IsReady = True

        elapsed = round(time.monotonic() - start, 2)
        Logger.info('FinBERT model loaded in %.2fs', elapsed)

    @classmethod
    def get_instance(cls, cache_path: Optional[str] = None) -> 'FinBertEngine':
        """Thread-safe lazy singleton."""
        if cls._Instance is None:
            cls._Instance = cls(cache_path=cache_path)
        return cls._Instance

    @classmethod
    def reset_instance(cls) -> None:
        if cls._Instance is not None:
            cls._Instance.shutdown()
            cls._Instance = None

    def shutdown(self) -> None:
        self._Executor.shutdown(wait=False)
        self._IsReady = False
        Logger.info('FinBERT engine shut down')

    def is_healthy(self) -> bool:
        return self._IsReady and self._Model is not None

    async def score_batch(self, texts: list[str]) -> list[dict]:
        """
        Non-blocking batch inference.

        Returns list of:
            {"label": "BULLISH", "score": 0.87, "confidence": 0.87,
             "probabilities": {"BULLISH": 0.87, "BEARISH": 0.08, "NEUTRAL": 0.05}}
        """
        if not texts:
            return []

        if not self._IsReady:
            raise RuntimeError('FinBERT engine is not initialised')

        if len(texts) <= self._MaxBatchSize:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._Executor, self._run_inference, texts)

        all_results: list[dict] = []
        for i in range(0, len(texts), self._MaxBatchSize):
            chunk = texts[i:i + self._MaxBatchSize]
            loop = asyncio.get_running_loop()
            chunk_results = await loop.run_in_executor(self._Executor, self._run_inference, chunk)
            all_results.extend(chunk_results)
        return all_results

    async def score_single(self, text: str) -> dict:
        results = await self.score_batch([text])
        return results[0]

    def _run_inference(self, texts: list[str]) -> list[dict]:
        """Actual model forward pass — runs inside the thread pool."""
        try:
            inputs = self._Tokenizer(
                texts,
                return_tensors='pt',
                truncation=True,
                padding=True,
                max_length=self._MaxTokenLength,
            )

            with torch.no_grad():
                logits = self._Model(**inputs).logits

            probs = torch.softmax(logits, dim=1).tolist()
            labels = self._Model.config.id2label

            results: list[dict] = []
            for prob_row in probs:
                best_idx = max(range(len(prob_row)), key=lambda x: prob_row[x])
                raw_label = labels[best_idx]
                mapped_label = self._LabelMap.get(raw_label, 'NEUTRAL')

                results.append({
                    'label': mapped_label,
                    'score': round(prob_row[best_idx], 4),
                    'confidence': round(prob_row[best_idx], 4),
                    'probabilities': {
                        self._LabelMap.get(labels[j], labels[j]): round(prob_row[j], 4)
                        for j in range(len(prob_row))
                    },
                })

            Logger.debug('Scored %d texts', len(texts))
            return results

        except Exception as exc:
            Logger.error('FinBERT inference failed: %s', exc, exc_info=True)
            return [
                {'label': 'NEUTRAL', 'score': 0.0, 'confidence': 0.0, 'probabilities': {}}
                for _ in texts
            ]


class HuggingFaceAdapter:
    def __init__(self):
        self._engine = FinBertEngine.get_instance()
        
    async def score_batch(self, texts: list[str]) -> list[dict]:
        return await self._engine.score_batch(texts)
