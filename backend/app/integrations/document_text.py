"""Bounded PDF/DOCX extraction shared by uploads; never decode binary as text."""

import io
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree

from app.core.exceptions import ValidationError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 100_000


def extract_document(content: bytes, filename: str, content_type: str | None = None) -> tuple[str, str]:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValidationError("Upload a non-empty file of at most 8 MB")
    extension = PurePath(filename.lower()).suffix
    expected = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if extension not in expected or content_type not in {None, "", "application/octet-stream", expected.get(extension)}:
        raise ValidationError("Only PDF and DOCX documents are supported")
    try:
        if extension == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise ValueError("PDF signature")
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if len(pdf.pages) > 100:
                    raise ValueError("Page limit")
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 500 or sum(e.file_size for e in entries) > 24 * 1024 * 1024:
                    raise ValueError("Archive limit")
                if any(e.flag_bits & 1 or e.file_size > max(1, e.compress_size) * 200 for e in entries):
                    raise ValueError("Unsafe archive")
                if "[Content_Types].xml" not in archive.namelist():
                    raise ValueError("DOCX container")
                raw = archive.read("word/document.xml")
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise ValueError("XML declarations")
                root = ElementTree.fromstring(raw)
                text = "\n".join("".join(p.itertext()) for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"))
    except Exception:
        raise ValidationError("The document could not be read. Use a valid, unencrypted PDF or DOCX") from None
    text = text.replace("\x00", "").strip()
    if len(text) < 30:
        raise ValidationError("No usable document text found. Scanned PDFs require OCR before upload")
    if len(text) > MAX_TEXT_CHARS:
        raise ValidationError("Document exceeds the 100,000 character extraction limit")
    return text, extension[1:]
