"""
File Overview: Domain event indicating a detected market anomaly in the options chain.

All Functions/Classes:
- anomaly_detected (class): Event for anomaly metadata transfer. Data: detection data -> outbound adapters.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from shared.domain.base_domain_event import BaseDomainEvent


class AnomalyDetectedEvent(BaseDomainEvent):
    pass
