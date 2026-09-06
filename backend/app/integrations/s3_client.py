"""AWS S3 client for resume and report file storage."""

from __future__ import annotations

import uuid
from typing import BinaryIO

import aioboto3
import structlog

from app.core.config import settings

logger = structlog.stdlib.get_logger("intra_ai.s3")

_session = aioboto3.Session()


async def upload_file(file: BinaryIO, key: str, content_type: str = "application/pdf") -> str:
    """Upload *file* to S3 under *key*. Returns the public URL."""
    async with _session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    ) as s3:
        await s3.upload_fileobj(
            file,
            settings.AWS_S3_BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    if settings.AWS_CLOUDFRONT_DOMAIN:
        url = f"https://{settings.AWS_CLOUDFRONT_DOMAIN}/{key}"
    else:
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"

    logger.info("s3_upload", key=key, url=url)
    return url


async def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed download URL for *key*."""
    async with _session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    ) as s3:
        url: str = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        return url


async def delete_file(key: str) -> None:
    """Delete an object from S3."""
    async with _session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    ) as s3:
        await s3.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
    logger.info("s3_delete", key=key)


def make_resume_key(job_id: str, filename: str) -> str:
    """Build a unique S3 key for a resume upload."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "pdf"
    return f"resumes/{job_id}/{uuid.uuid4()}.{ext}"


def make_report_key(interview_id: str) -> str:
    """Build an S3 key for a generated PDF report."""
    return f"reports/{interview_id}/{uuid.uuid4()}.pdf"
