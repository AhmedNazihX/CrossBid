"""S2.2.3 — `POST /documents`, `GET /documents/{id}`, `GET /documents`.

The HTTP layer is thin on purpose: validate the multipart part, hand it to
`ingestion.pipeline.DocumentPipeline`, answer **202** with the `uploaded` row, and let the
rest run as a `BackgroundTask` while the browser polls `GET /documents/{id}`. The state
machine and the failure reasons live in the pipeline, so a second caller cannot get them
wrong; this module only validates input and translates exceptions into status codes.

What the validation is for. A PDF is the only thing the parser reads (S2.1.1), so anything
else would be accepted at 202 and then fail in the background with a reason the bidder has to
come back for — refusing it here with **415** is the kinder failure. The check is three-fold
(extension, declared content type, the `%PDF-` magic bytes) because each alone is spoofable
or unreliable: browsers send `application/octet-stream` for a genuine PDF often enough that
the content type cannot be trusted on its own, and a `.pdf` suffix on an executable is exactly
the upload a parser should never see. The size cap is a named constant here and should become
a setting (`ingestion.max_upload_bytes`) once `settings.default.yaml` grows an upload section.

Every route depends on `auth.current_company` and scopes by `company.company_id`. A document
that belongs to another company answers **404**, never 403 (S2.2.2's reasoning: a "forbidden"
confirms the id exists). There is no `bid_id` on the upload: the pack is uploaded first and
S3.1.1's `POST /bids` attaches it (see `ingestion.pipeline`).

Response shapes are the frontend's contract — `frontend/lib/api.ts` is generated from this
schema — so they are plain Pydantic models with a description on every field and no
server-side detail (`storage_path`, `company_id`) the browser has no use for.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Final

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import CompanyContext, current_company
from crossbid.db import Database
from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddingsClient
from crossbid.ingestion.pipeline import DocumentPipeline, Upload
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import (
    DEFAULT_CONTENT_TYPE,
    StorageError,
    company_document_store,
)
from crossbid.main import get_app_settings, get_database
from crossbid.models import DocumentKind
from crossbid.readmodel.documents import DocumentRecord, DocumentsReadModel, DocumentStatus
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_MEGABYTES: Final = 50
MAX_UPLOAD_BYTES: Final = MAX_UPLOAD_MEGABYTES * 1024 * 1024
"""The DE fixture's largest single file is under 10 MB and the whole 28-file pack under 60,
so 50 MB per file admits any real tender document and refuses a mistake. Should become
`ingestion.max_upload_bytes` in `settings.default.yaml` (see the module docstring)."""

PDF_SUFFIX: Final = ".pdf"
PDF_MAGIC: Final = b"%PDF-"
"""Every PDF starts with this header (ISO 32000-1 §7.5.2). Checked because neither the
suffix nor the declared content type is something the server can trust."""

PDF_CONTENT_TYPES: Final = frozenset({"application/pdf", "application/x-pdf"})
GENERIC_CONTENT_TYPES: Final = frozenset({"application/octet-stream", ""})
"""What a browser or `curl` sends when it does not know better. Allowed, because the magic
bytes decide; a declared type outside both sets is an honest "this is not a PDF"."""

NO_FILENAME_DETAIL: Final = "The upload needs a filename."
NOT_PDF_SUFFIX_DETAIL: Final = (
    f"Only PDF files are accepted; the filename must end in {PDF_SUFFIX}."
)
NOT_PDF_TYPE_DETAIL: Final = "Only PDF files are accepted; the file was sent as another type."
NOT_PDF_CONTENT_DETAIL: Final = "Only PDF files are accepted; the file's content is not a PDF."
EMPTY_FILE_DETAIL: Final = "The uploaded file is empty."
TOO_LARGE_DETAIL: Final = f"The file is larger than {MAX_UPLOAD_MEGABYTES} MB."
NO_SUCH_DOCUMENT_DETAIL: Final = "No such document."
STORAGE_NOT_CONFIGURED_DETAIL: Final = (
    "Document storage is not configured on this server, so uploads are unavailable."
)


# ------------------------------------------------------------------------ response models


class DocumentResponse(BaseModel):
    """One uploaded document and how far it has got. `GET /documents/{id}` is polled for it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(description="The document id; use it to poll and to start a bid")
    kind: DocumentKind = Field(description="Company evidence, tender document or tender notice")
    name: str = Field(description="The filename as uploaded")
    bid_id: uuid.UUID | None = Field(
        description="The bid this document is attached to; null until a bid is started with it"
    )
    status: DocumentStatus = Field(
        description="uploaded → parsed → embedded → ready, or failed with failure_reason"
    )
    failure_reason: str | None = Field(
        description="Why the document failed, in a sentence to act on; null otherwise"
    )
    pages: int = Field(description="Total pages, known once the document is parsed")
    unread_pages: list[int] = Field(
        description="Pages with no text layer; the agent cannot read them and says so"
    )
    unread_page_count: int = Field(description="len(unread_pages), for a badge")
    created_at: datetime = Field(description="When the upload was accepted")
    updated_at: datetime = Field(description="When the status last changed")

    @classmethod
    def from_record(cls, record: DocumentRecord) -> DocumentResponse:
        return cls(
            id=record.id,
            kind=record.kind,
            name=record.name,
            bid_id=record.bid_id,
            status=record.status,
            failure_reason=record.failure_reason,
            pages=record.pages,
            unread_pages=list(record.unread_pages),
            unread_page_count=len(record.unread_pages),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class DocumentListResponse(BaseModel):
    """Every document of the calling company, newest first."""

    model_config = ConfigDict(frozen=True)

    documents: list[DocumentResponse] = Field(description="Newest first")


# ------------------------------------------------------------------------- dependencies


def get_document_records(db: Database = Depends(get_database)) -> DocumentsReadModel:
    """The `documents` writer on the process pool. Overridden with a fake in tests."""
    return DocumentsReadModel(db)


def get_pipeline(
    settings: Settings = Depends(get_app_settings),
    db: Database = Depends(get_database),
    records: DocumentsReadModel = Depends(get_document_records),
) -> DocumentPipeline:
    """The production wiring: real Storage, parser, chunker, embeddings and vector store.

    Built per request because the embeddings client owns an HTTP pool that the background
    task must be able to close. The chunker's encoder is left to its lazy default, so the
    BPE table is loaded in the background task and never inside a request.
    """
    try:
        store = company_document_store(settings)
    except StorageError as exc:
        # The message names the missing variables; that is for the operator's log, not the
        # bidder's screen.
        logger.error("uploads unavailable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORAGE_NOT_CONFIGURED_DETAIL
        ) from exc

    ingestion = settings.runtime.ingestion
    return DocumentPipeline(
        store=store,
        parser=PyMuPDFParser(),
        chunker=Chunker(
            chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
        ),
        embedder=EmbeddingsClient(settings),
        chunk_writer=ChunkVectorStore(db),
        records=records,
    )


# ------------------------------------------------------------------------------- routes


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
    summary="Upload a PDF",
)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(description=f"The PDF, at most {MAX_UPLOAD_MEGABYTES} MB"),
    kind: DocumentKind = Form(description="What the document is"),
    company: CompanyContext = Depends(current_company),
    pipeline: DocumentPipeline = Depends(get_pipeline),
) -> DocumentResponse:
    """Accept a PDF and answer 202 at once; poll `GET /documents/{id}` until it is done.

    The status moves `uploaded → parsed → embedded → ready`. A failure carries a
    `failure_reason` the bidder can act on.
    """
    upload = await validated_upload(file)
    try:
        record = await pipeline.accept(
            company_id=_company_uuid(company), kind=kind, upload=upload
        )
    except BaseException:
        # The row was not written, so nothing will run in the background to release the
        # embedder's pool; do it here and let the error surface as the 500 it is.
        await pipeline.aclose()
        raise

    background.add_task(_process_in_background, pipeline, record, upload)
    return DocumentResponse.from_record(record)


@router.get("/{document_id}", response_model=DocumentResponse, summary="Poll one document")
async def get_document(
    document_id: uuid.UUID,
    company: CompanyContext = Depends(current_company),
    records: DocumentsReadModel = Depends(get_document_records),
) -> DocumentResponse:
    """One document of the calling company. Another company's id answers 404."""
    record = await records.get(company_id=_company_uuid(company), document_id=document_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_DOCUMENT_DETAIL)
    return DocumentResponse.from_record(record)


@router.get("", response_model=DocumentListResponse, summary="List the company's documents")
async def list_documents(
    company: CompanyContext = Depends(current_company),
    records: DocumentsReadModel = Depends(get_document_records),
) -> DocumentListResponse:
    """Every document of the calling company, newest first."""
    found = await records.list(company_id=_company_uuid(company))
    return DocumentListResponse(documents=[DocumentResponse.from_record(r) for r in found])


# ------------------------------------------------------------------------------ helpers


def _company_uuid(company: CompanyContext) -> uuid.UUID:
    """`CompanyContext.company_id` is a string by contract; the read model binds UUIDs."""
    return uuid.UUID(company.company_id)


async def validated_upload(file: UploadFile) -> Upload:
    """The multipart part as an `Upload`, or the 4xx that names what is wrong with it.

    The body is read with a limit of one byte over the cap, so an oversized upload is
    recognised without being held in memory whole. The stored content type is always
    `application/pdf`: the magic bytes have been checked, so that is what the file *is*,
    whatever the client declared.
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NO_FILENAME_DETAIL)
    if not filename.lower().endswith(PDF_SUFFIX):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_SUFFIX_DETAIL
        )

    declared = (file.content_type or "").split(";", 1)[0].strip().lower()
    if declared not in PDF_CONTENT_TYPES and declared not in GENERIC_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_TYPE_DETAIL)

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=TOO_LARGE_DETAIL)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=EMPTY_FILE_DETAIL)
    if not content.startswith(PDF_MAGIC):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_CONTENT_DETAIL
        )
    return Upload(filename=filename, content_type=DEFAULT_CONTENT_TYPE, content=content)


async def _process_in_background(
    pipeline: DocumentPipeline, record: DocumentRecord, upload: Upload
) -> None:
    """The background task: run the state machine, then release the embedder's pool.

    `process` never raises for a document failure — that becomes the `failed` row. What can
    still propagate is the `mark_failed` write itself failing, which Starlette logs; nothing
    here swallows it.
    """
    try:
        await pipeline.process(record, upload)
    finally:
        await pipeline.aclose()
