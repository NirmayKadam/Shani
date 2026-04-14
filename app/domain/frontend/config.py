from pydantic_settings import BaseSettings
from typing import List


class FrontendConfig(BaseSettings):
    BACKEND_BASE_URL: str = "http://localhost:8000"
    DEFAULT_SYMBOL: str = "NIFTY"
    SYMBOL_LIST: List[str] = [
        "NIFTY", "BANKNIFTY", "RELIANCE", "INFY", "HDFCBANK", 
        "TCS", "ICICIBANK", "SBIN", "ITC", "LART"
    ]
    WS_URL: str = "ws://localhost:8000/ws"

    class Config:
        env_prefix = "FRONTEND_"


Config = FrontendConfig()
