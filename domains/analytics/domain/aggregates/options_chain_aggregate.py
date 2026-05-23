"""
File Overview: Aggregate for managing options chain data and detecting anomalies.

All Functions/Classes:
- options_chain_aggregate: Main aggregate class. Take ticks and send anomaly events.
- add_tick_batch: Process batch of order flow data. Take raw_tick_dto list and send anomalies.
- detect_anomalies: Core logic for outlier detection. Take internal ticks and send list of anomaly events.

Endpoints/APIs: None

Database Tables: None
"""
from typing import List, Optional

from domains.ingestion.application.dto.raw_tick_dto import RawTickDTO
from domains.analytics.domain.events.anomaly_detected_event import AnomalyDetectedEvent

class OptionsChainAggregate:
    OI_SURGE_THRESHOLD = 3.0
    VOL_SWEEP_THRESHOLD = 5.0

    def __init__(self):
        self.ticks: List[RawTickDTO] = []
        
    def add_tick_batch(self, ticks: List[RawTickDTO]) -> List[AnomalyDetectedEvent]:
        self.ticks.extend(ticks)
        return self.detect_anomalies()
        
    def detect_anomalies(self) -> List[AnomalyDetectedEvent]:
        anomalies = []
        for tick in self.ticks:
            pass # TODO: EWM logic
        return anomalies
