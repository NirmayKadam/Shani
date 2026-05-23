"""
File Overview: Domain event indicating a single news article has been successfully ingested.

All Functions/Classes:
- article_ingested: Event signaling news availability. Take ingested article and send to downstream processors.

Endpoints/APIs: None

Database Tables: None
"""
from shared.application.dto.base_dto import BaseDTO
from shared.domain.base_domain_event import BaseDomainEvent

class ArticleIngestedEvent(BaseDomainEvent):
    pass
