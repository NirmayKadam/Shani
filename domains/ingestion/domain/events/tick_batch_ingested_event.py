"""
File Overview: Domain event indicating a batch of market ticks has been successfully ingested.

All Functions/Classes:
- tick_batch_ingested: Event signaling price data availability. Take tick batch and send to analytics processors.

Endpoints/APIs: None

Database Tables: None
"""
from shared.domain.base_domain_event import BaseDomainEvent
from shared.application.dto.base_dto import BaseDTO

class TickBatchIngestedEvent(BaseDomainEvent):
    pass
