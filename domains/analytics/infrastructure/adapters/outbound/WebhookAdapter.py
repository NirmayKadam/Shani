import asyncio
from domains.analytics.application.ports.interface.outbound.IAlertSink import IAlertSink
from domains.analytics.application.dto.AlertDTO import AlertDTO

class WebhookAdapter(IAlertSink):
    def __init__(self, url: str = None):
        self._url = url
        self.semaphore = asyncio.Semaphore(50)
        
    async def send_alert(self, payload: AlertDTO) -> None:
        async with self.semaphore:
            pass # TODO: implement POST logic
