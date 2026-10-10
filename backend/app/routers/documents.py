"""Upload, list, poll, view and re-process documents."""

import hashlib
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import filetype
import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import client_ip, current_user
from app.models import Document, User
from app.services.audit import log_event
from app.services.consent import Access, get_scoped_record, profile_access
from app.services.ingest.pipeline import worker
from app.services.pages import render_page

router = APIRouter(tags=["documents"])

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 20
ALLOWED = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


class DocumentOut(BaseModel):
    id: uuid.UUID
    label: str
    seq: int
    original_filename: str
    mime: str
    page_count: int
    status: str
    stage: str
    error: str | None
    document_type: str | None
    document_date: date | None
    source_org_name: str | None
    result_counts: dict[str, Any] | None
    uploader_role: str
    created_at: datetime
    updated_at: datetime


def doc_out(d: Document) -> DocumentOut:
    counts = dict(d.result_counts or {})
    counts.pop("meta", None)
    return DocumentOut(
        id=d.id,
        label=d.label,
        seq=d.seq,
        original_filename=d.original_filename,
        mime=d.mime,
        page_count=d.page_count,
        status=d.status,
        stage=d.stage,
        error=d.error,
        document_type=d.document_type,
        document_date=d.document_date,
        source_org_name=d.source_org_name,
        result_counts=counts,
        uploader_role=d.uploader_role,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


class UploadResult(BaseModel):
    filename: str
    document: DocumentOut | None = None
    duplicate: bool = False
    error: str | None = None


def sniff(data: bytes) -> str | None:
    kind = filetype.guess(data)
    return kind.mime if kind and kind.mime in ALLOWED else None


def _validate(data: bytes, filename: str) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename} is larger than 15 MB")
    if not data:
        raise ValueError(f"{filename} is empty")
    kind = filetype.guess(data)
    if kind and kind.mime in ("image/heic", "image/heif"):
        raise ValueError("HEIC photos aren't supported yet. Please share the photo as JPG.")
    mime = sniff(data)
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


@router.post("/profiles/{profile_id}/documents", response_model=list[UploadResult])
async def upload_documents(
    profile_id: uuid.UUID,
    request: Request,
    files: list[UploadFile] = File(...),
    access: Access = Depends(profile_access),
    db: AsyncSession = Depends(get_db),
) -> list[UploadResult]:
    access.require_write()
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No files uploaded")
    storage = get_settings().storage_dir
    storage.mkdir(parents=True, exist_ok=True)
    results: list[UploadResult] = []
    next_seq = (await db.scalar(select(func.max(Document.seq)).where(Document.profile_id == profile_id)) or 0) + 1
    for f in files:
        name = Path(f.filename or "document").name[:200]
        data = await f.read(MAX_BYTES + 1)
        try:
            mime = _validate(data, name)
        except ValueError as e:
            results.append(UploadResult(filename=name, error=str(e)))
            continue
        sha = hashlib.sha256(data).hexdigest()
        existing = await db.scalar(
            select(Document).where(
                Document.profile_id == profile_id, Document.sha256 == sha, Document.status != "failed"
            )
        )
        if existing:
            results.append(UploadResult(filename=name, document=doc_out(existing), duplicate=True))
            continue
        path = storage / f"{uuid.uuid4().hex}{ALLOWED[mime]}"
        path.write_bytes(data)
        doc = Document(
            profile_id=profile_id,
            seq=next_seq,
            uploaded_by_user_id=access.user.id,
            uploader_role="owner" if access.is_owner else "doctor",
            original_filename=name,
            mime=mime,
            storage_path=str(path),
            sha256=sha,
            status="queued",
            stage="Uploading",
        )
        next_seq += 1
        db.add(doc)
        await db.flush()
        results.append(UploadResult(filename=name, document=doc_out(doc)))
        await log_event(
            db,
            profile_id=profile_id,
            actor_user_id=access.user.id,
            actor_label=access.actor_label,
            action="upload",
            scopes=["documents"],
            details={"document": doc.label, "filename": name},
            ip=client_ip(request),
        )
    await db.commit()
    for r in results:
        if r.document and not r.duplicate:
            worker.enqueue(r.document.id)
    return results


@router.get("/profiles/{profile_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    profile_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[DocumentOut]:
    access, record = await get_scoped_record(db, profile_id, user)
    visible = {uuid.UUID(d) for d in record.listable_document_ids}
    docs = (
        await db.scalars(select(Document).where(Document.profile_id == profile_id).order_by(Document.seq.desc()))
    ).all()
    return [doc_out(d) for d in docs if access.is_owner or d.id in visible]


async def _doc_for_viewer(db: AsyncSession, doc_id: uuid.UUID, user: User) -> tuple[Document, Access]:
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    access, record = await get_scoped_record(db, doc.profile_id, user)
    if not access.is_owner and str(doc.id) not in {d.id for d in record.documents}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This document is outside your access")
    return doc, access


@router.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> DocumentOut:
    doc, _ = await _doc_for_viewer(db, doc_id, user)
    return doc_out(doc)


@router.get("/documents/{doc_id}/file")
async def document_file(
    doc_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> FileResponse:
    doc, _ = await _doc_for_viewer(db, doc_id, user)
    return FileResponse(
        doc.storage_path,
        media_type=doc.mime,
        filename=doc.original_filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/documents/{doc_id}/pages/{page}.png")
async def document_page(
    doc_id: uuid.UUID,
    page: int,
    highlight: str | None = None,
    crop: bool = False,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    doc, _ = await _doc_for_viewer(db, doc_id, user)
    try:
        png, hit = render_page(Path(doc.storage_path).read_bytes(), doc.mime, page, highlight=highlight, crop=crop)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    return Response(
        png, media_type="image/png", headers={"X-Highlight-Found": "1" if hit else "0", "Cache-Control": "private"}
    )


@router.post("/documents/{doc_id}/retry", response_model=DocumentOut)
async def retry_document(
    doc_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> DocumentOut:
    doc, access = await _doc_for_viewer(db, doc_id, user)
    access.require_write()
    if doc.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed documents can be retried")
    doc.status, doc.stage, doc.error = "queued", "Uploading", None
    await db.commit()
    worker.enqueue(doc.id)
    return doc_out(doc)
