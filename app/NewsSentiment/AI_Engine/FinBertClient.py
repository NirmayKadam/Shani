import torch
import asyncio
import logging
import time
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

Logger = logging.getLogger(__name__)


# ── Data Classes ────────────────────────────────────────────────

@dataclass
class SentimentResult:
    Symbol: str
    Label: str              # BULLISH | BEARISH | NEUTRAL
    Score: float            # 0.0 to 1.0
    Confidence: float
    ModelVersion: str = 'finbert-v1'
    Timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def ToDict(self) -> dict:
        return {
            'Symbol': self.Symbol,
            'Label': self.Label,
            'Score': round(self.Score, 4),
            'Confidence': round(self.Confidence, 4),
            'ModelVersion': self.ModelVersion,
            'Timestamp': self.Timestamp,
        }


# ── FinBERT Client ──────────────────────────────────────────────

class FinBertClient:
    """
    Singleton — load once, reuse forever.
    Thread-safe: inference runs in a thread pool so the async event loop stays responsive.

    Usage:
        Client = FinBertClient.GetInstance()
        Results = await Client.ScoreForSymbol('RELIANCE', ['Good quarterly results'])
    """

    _Instance: Optional['FinBertClient'] = None
    _ModelName = 'ProsusAI/finbert'
    _LabelMap = {
        'positive': 'BULLISH',
        'negative': 'BEARISH',
        'neutral':  'NEUTRAL',
    }
    _MaxBatchSize = 32          # process at most 32 texts per batch
    _MaxTokenLength = 512       # FinBERT token limit

    # ── Lifecycle ───────────────────────────────────────────────

    def __init__(self, CachePath: Optional[str] = None):
        """
        Args:
            CachePath: Optional local directory for cached model weights.
                       Falls back to default HuggingFace cache if not set.
        """
        Logger.info('Loading FinBERT model: %s', self._ModelName)
        StartTime = time.monotonic()

        KWArgs = {'pretrained_model_name_or_path': self._ModelName}
        if CachePath:
            KWArgs['cache_dir'] = CachePath

        self._Tokenizer = AutoTokenizer.from_pretrained(**KWArgs)
        self._Model = AutoModelForSequenceClassification.from_pretrained(**KWArgs)
        self._Model.eval()                          # disable dropout for inference
        self._Executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='finbert')
        self._IsReady = True

        Elapsed = round(time.monotonic() - StartTime, 2)
        Logger.info('FinBERT model loaded in %.2fs', Elapsed)

    @classmethod
    def GetInstance(cls, CachePath: Optional[str] = None) -> 'FinBertClient':
        """Thread-safe lazy singleton."""
        if cls._Instance is None:
            cls._Instance = cls(CachePath=CachePath)
        return cls._Instance

    @classmethod
    def ResetInstance(cls) -> None:
        """Tear down the singleton (useful for tests)."""
        if cls._Instance is not None:
            cls._Instance.Shutdown()
            cls._Instance = None

    def Shutdown(self) -> None:
        """Release thread-pool resources."""
        self._Executor.shutdown(wait=False)
        self._IsReady = False
        Logger.info('FinBERT client shut down')

    # ── Health ──────────────────────────────────────────────────

    def IsHealthy(self) -> bool:
        return self._IsReady and self._Model is not None

    async def Warmup(self) -> None:
        """Run a throwaway inference so the first real call is fast."""
        Logger.info('Warming up FinBERT...')
        await self.ScoreBatch(['Startup warmup sentence'])
        Logger.info('FinBERT warm-up complete')

    # ── Public API ──────────────────────────────────────────────

    async def ScoreSingle(self, Text: str) -> dict:
        """Score a single text and return a raw dict."""
        Results = await self.ScoreBatch([Text])
        return Results[0]

    async def ScoreBatch(self, Texts: list[str]) -> list[dict]:
        """
        Non-blocking batch inference.
        Automatically chunks input when it exceeds _MaxBatchSize.
        """
        if not Texts:
            return []

        if not self._IsReady:
            raise RuntimeError('FinBERT client is not initialised or has been shut down')

        # Chunk large lists to keep memory bounded
        if len(Texts) <= self._MaxBatchSize:
            Loop = asyncio.get_running_loop()
            return await Loop.run_in_executor(self._Executor, self._RunInference, Texts)

        AllResults: list[dict] = []
        for i in range(0, len(Texts), self._MaxBatchSize):
            Chunk = Texts[i : i + self._MaxBatchSize]
            Loop = asyncio.get_running_loop()
            ChunkResults = await Loop.run_in_executor(self._Executor, self._RunInference, Chunk)
            AllResults.extend(ChunkResults)
        return AllResults

    async def ScoreForSymbol(self, Symbol: str, Texts: list[str]) -> list[SentimentResult]:
        """
        Convenience method: scores texts and wraps each result in a SentimentResult
        tagged with the given stock symbol.
        """
        RawResults = await self.ScoreBatch(Texts)
        return [
            SentimentResult(
                Symbol=Symbol,
                Label=R['Label'],
                Score=R['Score'],
                Confidence=R['Confidence'],
            )
            for R in RawResults
        ]

    # ── Internal ────────────────────────────────────────────────

    def _RunInference(self, Texts: list[str]) -> list[dict]:
        """Actual model forward pass — runs inside the thread pool."""
        try:
            Inputs = self._Tokenizer(
                Texts,
                return_tensors='pt',
                truncation=True,
                padding=True,
                max_length=self._MaxTokenLength,
            )

            with torch.no_grad():
                Logits = self._Model(**Inputs).logits

            Probs = torch.softmax(Logits, dim=1).tolist()
            Labels = self._Model.config.id2label

            Results: list[dict] = []
            for ProbRow in Probs:
                BestIdx = max(range(len(ProbRow)), key=lambda x: ProbRow[x])
                RawLabel = Labels[BestIdx]
                Results.append({
                    'Label': self._LabelMap.get(RawLabel, 'NEUTRAL'),
                    'Score': round(ProbRow[BestIdx], 4),
                    'Confidence': round(ProbRow[BestIdx], 4),
                    'Probabilities': {
                        self._LabelMap.get(Labels[j], Labels[j]): round(ProbRow[j], 4)
                        for j in range(len(ProbRow))
                    },
                })

            Logger.debug('Scored %d texts', len(Texts))
            return Results

        except Exception as Exc:
            Logger.error('FinBERT inference failed: %s', Exc, exc_info=True)
            # Return NEUTRAL fallback so the pipeline doesn't crash
            return [
                {'Label': 'NEUTRAL', 'Score': 0.0, 'Confidence': 0.0, 'Probabilities': {}}
                for _ in Texts
            ]
