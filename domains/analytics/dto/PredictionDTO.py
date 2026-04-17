from datetime import datetime
from shared.dto.BaseDTO import BaseDTO

class PredictionDTO(BaseDTO):
    symbol: str
    bullish_prob: float
    model_version: str
    predicted_at: datetime
