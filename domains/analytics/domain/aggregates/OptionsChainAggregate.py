from typing import List, Optional
from domains.ingestion.application.dto.RawTickDTO import RawTickDTO
from domains.analytics.domain.events.AnomalyDetected import AnomalyDetected

class OptionsChainAggregate:
    OI_SURGE_THRESHOLD = 3.0
    VOL_SWEEP_THRESHOLD = 5.0

    def __init__(self):
        self.ticks: List[RawTickDTO] = []
        
    def add_tick_batch(self, ticks: List[RawTickDTO]) -> List[AnomalyDetected]:
        self.ticks.extend(ticks)
        return self.detect_anomalies()
        
    def detect_anomalies(self) -> List[AnomalyDetected]:
        anomalies = []
        for tick in self.ticks:
            pass # TODO: EWM logic
        return anomalies
