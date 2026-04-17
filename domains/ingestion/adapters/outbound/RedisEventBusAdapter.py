from domains.ingestion.ports.outbound.IEventPublisher import IEventPublisher
from shared.events.BaseDomainEvent import BaseDomainEvent

class RedisEventBusAdapter(IEventPublisher):
    def publish(self, event: BaseDomainEvent) -> None:
        # TODO: implement Celery task dispatch based on event_type
        pass
