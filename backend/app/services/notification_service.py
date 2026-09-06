"""Notification service — transactional emails via Resend."""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.integrations.email_client import send_email

logger = structlog.stdlib.get_logger("intra_ai.service.notification")


class NotificationService:
    """Sends transactional emails for the hiring pipeline."""

    async def send_application_received(
        self,
        email: str,
        name: str,
        job_title: str,
    ) -> None:
        """Confirm application receipt to the candidate."""
        subject = f"Application Received - {job_title}"
        html = f"""
        <h2>Hi {name},</h2>
        <p>Thank you for applying for the <strong>{job_title}</strong> position.</p>
        <p>We have received your application and resume. Our team will review your qualifications
        and get back to you within 24-48 hours.</p>
        <p>Best regards,<br>Intra AI Team</p>
        """
        await send_email(email, subject, html)
        logger.info("notification_sent", type="application_received", to=email)

    async def send_shortlisted(
        self,
        email: str,
        name: str,
        job_title: str,
        scheduling_link: str,
    ) -> None:
        """Notify candidate they have been shortlisted with scheduling link."""
        subject = f"Congratulations! You've been shortlisted - {job_title}"
        html = f"""
        <h2>Hi {name},</h2>
        <p>Great news! After reviewing your application for <strong>{job_title}</strong>,
        we are pleased to inform you that you have been <strong>shortlisted</strong> for an interview.</p>
        <p>Please schedule your interview at your earliest convenience:</p>
        <p><a href="{scheduling_link}" style="background-color: #0A66C2; color: white;
        padding: 12px 24px; text-decoration: none; border-radius: 999px; display: inline-block;">
        Schedule Interview</a></p>
        <p>Best regards,<br>Intra AI Team</p>
        """
        await send_email(email, subject, html)
        logger.info("notification_sent", type="shortlisted", to=email)

    async def send_rejected(
        self,
        email: str,
        name: str,
        job_title: str,
        feedback: str | None = None,
    ) -> None:
        """Notify candidate of rejection with optional feedback."""
        subject = f"Application Update - {job_title}"
        feedback_section = ""
        if feedback:
            feedback_section = f"""
            <p><strong>Feedback:</strong></p>
            <p>{feedback}</p>
            """
        html = f"""
        <h2>Hi {name},</h2>
        <p>Thank you for your interest in the <strong>{job_title}</strong> position and
        for taking the time to apply.</p>
        <p>After careful review, we have decided to move forward with other candidates
        whose qualifications more closely match our requirements at this time.</p>
        {feedback_section}
        <p>We encourage you to apply for future openings that match your skills and experience.</p>
        <p>Best regards,<br>Intra AI Team</p>
        """
        await send_email(email, subject, html)
        logger.info("notification_sent", type="rejected", to=email)

    async def send_interview_reminder(
        self,
        email: str,
        name: str,
        job_title: str,
        interview_datetime: str,
    ) -> None:
        """Send an interview reminder to the candidate."""
        subject = f"Interview Reminder - {job_title}"
        html = f"""
        <h2>Hi {name},</h2>
        <p>This is a reminder that your interview for <strong>{job_title}</strong>
        is scheduled for <strong>{interview_datetime}</strong>.</p>
        <h3>Before your interview, please ensure:</h3>
        <ul>
            <li>Stable internet connection</li>
            <li>Working camera and microphone</li>
            <li>Quiet, well-lit environment</li>
            <li>You are alone in the room</li>
        </ul>
        <p>Best regards,<br>Intra AI Team</p>
        """
        await send_email(email, subject, html)
        logger.info("notification_sent", type="interview_reminder", to=email)
