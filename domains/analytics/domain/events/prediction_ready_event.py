"""
File Overview: Domain event indicating an ML inference result is ready.

All Functions/Classes:
- prediction_ready (class): Event for inference result notification. Data: model outputs -> read-model adapters.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from shared.domain.base_domain_event import BaseDomainEvent


class PredictionReadyEvent(BaseDomainEvent):
    pass
