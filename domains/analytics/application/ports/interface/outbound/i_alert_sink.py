from abc import ABC, abstractmethod
from domains.analytics.application.dto.alert_dto import alert_dto

class i_alert_sink(ABC):
    @abstractmethod
    async def send_alert(self, payload: alert_dto) -> None:
        pass
