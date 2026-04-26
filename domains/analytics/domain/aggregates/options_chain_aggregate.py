from typing import List, Optional
from domains.ingestion.application.dto.raw_tick_dto import raw_tick_dto
from domains.analytics.domain.events.anomaly_detected import anomaly_detected

class options_chain_aggregate:
    OI_SURGE_THRESHOLD = 3.0
    VOL_SWEEP_THRESHOLD = 5.0

    def __init__(self):
        self.ticks: List[raw_tick_dto] = []
        
    def add_tick_batch(self, ticks: List[raw_tick_dto]) -> List[anomaly_detected]:
        self.ticks.extend(ticks)
        return self.detect_anomalies()
        
    def detect_anomalies(self) -> List[anomaly_detected]:
        anomalies = []
        for tick in self.ticks:
            pass # TODO: EWM logic
        return anomalies
