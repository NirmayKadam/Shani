"""
File Overview: Domain event indicating a technical or sentiment signal has been fired.

All Functions/Classes:
- signal_fired (class): Event for signal trigger notification. Data: signal data -> outbound handlers.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from shared.domain.base_domain_event import BaseDomainEvent


class SignalFiredEvent(BaseDomainEvent):
    pass
