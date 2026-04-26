import asyncio
from domains.analytics.application.ports.interface.outbound.i_alert_sink import i_alert_sink
from domains.analytics.application.dto.alert_dto import alert_dto

class webhook_adapter(i_alert_sink):
    def __init__(self, url: str = None):
        self._url = url
        self.semaphore = asyncio.Semaphore(50)
        
    async def send_alert(self, payload: alert_dto) -> None:
        async with self.semaphore:
            pass # TODO: implement POST logic
