import asyncio
import html
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from domains.notifications.domain.entities import NotificationEvent, AlertRule
from domains.notifications.ports.interface.outbound.i_notification_channel import (
    INotificationChannelAdapterPort,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_message(event: NotificationEvent, sender: str, destination: str) -> MIMEMultipart:
    esc = lambda value: html.escape(str(value))
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0b0e14; color: #e2e8f0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #1a202c; padding: 24px; border-radius: 8px;">
          <h2 style="color: #6366f1;">Market Alert Triggered</h2>
          <p><strong>Symbol:</strong> {esc(event.symbol)}</p>
          <p><strong>Condition:</strong> {esc(event.condition_type.value)}</p>
          <p><strong>Triggered Value:</strong> {esc(event.triggered_value)}</p>
          <p><strong>Threshold:</strong> {esc(event.threshold)}</p>
          <p style="padding: 12px; background-color: #2d3748; border-left: 4px solid #6366f1;">{esc(event.message)}</p>
          <hr style="border: 0; border-top: 1px solid #4a5568;" />
          <small style="color: #a0aec0;">AlphaStreams Quantitative Analytics Terminal</small>
        </div>
      </body>
    </html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[AlphaStreams Alert] {event.symbol} {event.condition_type.value}"
    msg["From"] = sender
    msg["To"] = destination
    msg.attach(MIMEText(event.message, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


class EmailNotificationChannelAdapter(INotificationChannelAdapterPort):
    """Outbound adapter formatting and sending HTML alert emails via SMTP.

    smtplib is blocking, so delivery runs in a worker thread and never stalls the event loop.
    """

    async def dispatch(self, event: NotificationEvent, rule: AlertRule) -> bool:
        destination = rule.email_destination
        if not destination:
            logger.warning(f"Email channel invoked for rule {rule.id} but email_destination missing")
            return False

        cfg = get_settings()
        if not cfg.SmtpHost:
            logger.warning("SMTP_HOST is not configured — skipping email dispatch")
            return False

        msg = _build_message(event, cfg.SmtpFromEmail, destination)
        try:
            await asyncio.to_thread(self._send, cfg, msg, destination)
            logger.info(f"Email alert delivered to {destination} for event {event.id}")
            return True
        except Exception as ex:
            logger.error(f"Failed to send email alert to {destination}: {ex}")
            return False

    @staticmethod
    def _send(cfg, msg: MIMEMultipart, destination: str) -> None:
        with smtplib.SMTP(cfg.SmtpHost, cfg.SmtpPort, timeout=10) as server:
            if cfg.SmtpUseTls:
                server.starttls()
            if cfg.SmtpUser and cfg.SmtpPassword:
                server.login(cfg.SmtpUser, cfg.SmtpPassword)
            server.sendmail(msg["From"], [destination], msg.as_string())
