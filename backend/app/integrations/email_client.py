"""Email delivery via Resend API."""

from __future__ import annotations

import httpx
import structlog

from app.core.config import settings

logger = structlog.stdlib.get_logger("intra_ai.email")

_RESEND_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html_body: str) -> dict:
    """Send a transactional email through Resend. Returns the Resend response."""
    sender = settings.RESEND_FROM_EMAIL.strip()
    if not sender:
        # Preserve the existing fallback for other callers. Morgan requires an
        # explicit verified-domain sender before it can propose an email.
        sender = f"Intra AI <noreply@{settings.FRONTEND_URL.replace('https://', '').replace('http://', '')}>"
    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _RESEND_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    data = response.json()
    if response.status_code >= 400:
        logger.error("email_send_failed", to=to, subject=subject, response=data)
    else:
        logger.info("email_sent", to=to, subject=subject, resend_id=data.get("id"))

    return data
