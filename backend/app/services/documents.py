"""Creating documents from uploaded bytes (shared by the upload API and the seed script)."""

import hashlib
import uuid

import filetype
import pymupdf
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 20
ALLOWED = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


def validate_upload(data: bytes, filename: str) -> str:
    """MIME-sniff and check limits. Returns the mime type or raises ValueError (message is user-facing)."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename} is larger than 15 MB")
    if not data:
        raise ValueError(f"{filename} is empty")
    kind = filetype.guess(data)
    if kind and kind.mime in ("image/heic", "image/heif"):
        raise ValueError("HEIC photos aren't supported yet. Please share the photo as JPG.")
    mime = kind.mime if kind and kind.mime in ALLOWED else None
    if not mime:
        raise ValueError(f"{filename} isn't a PDF, JPG or PNG")
    if mime == "application/pdf":
        try:
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise ValueError(f"{filename} is password protected")
                if pdf.page_count > MAX_PAGES:
                    raise ValueError(f"{filename} has more than {MAX_PAGES} pages")
        except (RuntimeError, pymupdf.FileDataError) as e:
            raise ValueError(f"{filename} couldn't be opened as a PDF") from e
    return mime


async def next_seq(db: AsyncSession, profile_id: uuid.UUID) -> int:
    return (await db.scalar(select(func.max(Document.seq)).where(Document.profile_id == profile_id)) or 0) + 1


async def find_duplicate(db: AsyncSession, profile_id: uuid.UUID, data: bytes) -> Document | None:
    sha = hashlib.sha256(data).hexdigest()
    return await db.scalar(
        select(Document).where(Document.profile_id == profile_id, Document.sha256 == sha, Document.status != "failed")
    )


async def store_document(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    user_id: uuid.UUID,
    uploader_role: str,
    filename: str,
    data: bytes,
    mime: str,
    seq: int,
) -> Document:
    storage = get_settings().storage_dir
    storage.mkdir(parents=True, exist_ok=True)
    path = storage / f"{uuid.uuid4().hex}{ALLOWED[mime]}"
    path.write_bytes(data)
    doc = Document(
        profile_id=profile_id,
        seq=seq,
        uploaded_by_user_id=user_id,
        uploader_role=uploader_role,
        original_filename=filename,
        mime=mime,
        storage_path=str(path),
        sha256=hashlib.sha256(data).hexdigest(),
        status="queued",
        stage="Uploading",
    )
    db.add(doc)
    await db.flush()
    return doc
