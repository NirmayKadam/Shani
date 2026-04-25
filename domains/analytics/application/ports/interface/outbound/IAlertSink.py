from abc import ABC, abstractmethod
from domains.analytics.application.dto.AlertDTO import AlertDTO

class IAlertSink(ABC):
    @abstractmethod
    async def send_alert(self, payload: AlertDTO) -> None:
        pass
