"""Resume storage helpers for the non-AWS local/Supabase path.

AWS is intentionally paused for the current implementation phase. Uploaded
resumes still need a durable object store so recruiter dossiers can open the
original file. Supabase Storage is used when S3 is not configured.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.stdlib.get_logger("intra_ai.resume_storage")

_EXTENSION_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "rtf": "application/rtf",
}


def file_extension(filename: str | None, content_type: str | None = None) -> str:
    """Return a safe, supported extension for a resume upload."""
    name = (filename or "").lower().strip()
    match = re.search(r"\.([a-z0-9]+)$", name)
    if match and match.group(1) in _EXTENSION_CONTENT_TYPES:
        return match.group(1)

    content = (content_type or "").lower()
    if "pdf" in content:
        return "pdf"
    if "word" in content or "document" in content:
        return "docx"
    if "rtf" in content:
        return "rtf"
    return "txt"


def content_type_for_extension(extension: str) -> str:
    """Map a stored extension to a browser-safe response content type."""
    return _EXTENSION_CONTENT_TYPES.get(extension.lower().lstrip("."), "application/octet-stream")


def make_supabase_key(application_id: str, extension: str) -> str:
    """Build a deterministic private Storage object key for an application."""
    return f"applications/{application_id}.{extension.lstrip('.') or 'pdf'}"


def internal_resume_url(application_id: str, extension: str) -> str:
    """Build the authenticated backend URL used by recruiter dossier links."""
    return f"/api/v1/applications/{application_id}/resume/{extension.lstrip('.') or 'pdf'}"


def upload_to_supabase(supabase: Any, key: str, content: bytes, content_type: str) -> None:
    """Upload bytes to the configured private Supabase Storage bucket."""
    bucket = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    bucket.upload(
        key,
        content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    logger.info("supabase_resume_uploaded", bucket=settings.SUPABASE_STORAGE_BUCKET, key=key)


def download_from_supabase(supabase: Any, key: str) -> bytes:
    """Download a private resume object from Supabase Storage."""
    bucket = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    return bucket.download(key)
