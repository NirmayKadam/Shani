import asyncio
from domains.analytics.ports.outbound.IAlertSink import IAlertSink
from domains.analytics.dto.AlertDTO import AlertDTO

class WebhookAdapter(IAlertSink):
    def __init__(self):
        self.semaphore = asyncio.Semaphore(50)
        
    async def send_alert(self, payload: AlertDTO) -> None:
        async with self.semaphore:
            pass # TODO: implement POST logic
