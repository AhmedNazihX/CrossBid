"""S2.2.3 — `POST /documents`, `GET /documents/{id}`, `GET /documents`; S4.5.1 adds
`GET /documents/{id}/url`.

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

**The accept-list is keyed on `kind`, not on an exception to the PDF rule (S2.5.1).** A
published ESPD request (DUME) is XML, and it is the only kind that is: `XML_KINDS` says which
kinds are read as XML and every other kind stays PDF-only, so admitting a DUME did not widen
what a tender document or a company evidence file may be. The XML branch keeps the same
three-fold shape, with each check's XML equivalent — the `.xml` suffix, a declared type that
is plausibly XML, and a **content sniff that the root element really is an ESPD request**.
That last one is `ingestion/espd.py`, which reads through `ingestion/safe_xml.py`, so a
hostile document (entity expansion, an external entity, a nesting bomb) is refused here at
415 and never reaches a background task. The XML size cap is `safe_xml.MAX_XML_BYTES` rather
than the 50 MB PDF cap: the reader will not parse more than that, so accepting more would
only be a 202 followed by a failure.

Every route depends on `auth.current_company` and scopes by `company.company_id`. A document
that belongs to another company answers **404**, never 403 (S2.2.2's reasoning: a "forbidden"
confirms the id exists). There is no `bid_id` on the upload: the pack is uploaded first and
S3.1.1's `POST /bids` attaches it (see `ingestion.pipeline`).

`POST /documents` also carries S2.3.3's per-company hourly limit, which answers **429** with
a `Retry-After`; `crossbid/rate_limit.py` holds the counters and the caveats.

Response shapes are the frontend's contract — `frontend/lib/api.ts` is generated from this
schema — so they are plain Pydantic models with a description on every field and no
server-side detail (`storage_path`, `company_id`) the browser has no use for.

`GET /documents/{id}/url` (S4.5.1) is what the workspace's source panel calls: the browser's
own PDF viewer needs a URL it can load in an `<iframe>`, and the file sits in a private
bucket. The answer is `CompanyDocumentStore.signed_url` for the record's own key -- the store
re-checks that the key belongs to the calling company and raises `ObjectNotFoundError`
otherwise, which is the same 404 as an unknown id. The response carries `expires_at` so the
panel can refresh the URL before the ten-minute TTL runs out, and never the key itself.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Annotated, Final

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import CompanyContext, current_company
from crossbid.company_keys import get_company_settings
from crossbid.db import Database
from crossbid.deps import get_app_settings, get_database
from crossbid.ingestion.espd import EspdParseError, parse_espd_request
from crossbid.ingestion.pipeline import DocumentPipeline, Upload, build_pipeline
from crossbid.ingestion.safe_xml import MAX_XML_BYTES
from crossbid.ingestion.storage import (
    DEFAULT_CONTENT_TYPE,
    XML_CONTENT_TYPE,
    CompanyDocumentStore,
    ObjectNotFoundError,
    StorageError,
    company_document_store,
)
from crossbid.models import DocumentKind
from crossbid.rate_limit import RATE_LIMITED_RESPONSES, document_upload_limit
from crossbid.readmodel.documents import DocumentRecord, DocumentsReadModel, DocumentStatus
from crossbid.routers.paging import (
    PAGE_CURSOR_DESCRIPTION,
    PAGE_LIMIT_DESCRIPTION,
    page_request,
)
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

XML_KINDS: Final = frozenset({DocumentKind.TENDER_ESPD_REQUEST})
"""The kinds read as XML. Every other kind is PDF-only — see the module docstring."""

XML_SUFFIX: Final = ".xml"
XML_CONTENT_TYPES: Final = frozenset({"application/xml", "text/xml", "application/espd+xml"})
"""Declared types a client may plausibly send an ESPD request as. As with a PDF, this is a
filter and not the decision: the root element is what settles it."""

NO_FILENAME_DETAIL: Final = "The upload needs a filename."
NOT_PDF_SUFFIX_DETAIL: Final = (
    f"Only PDF files are accepted; the filename must end in {PDF_SUFFIX}."
)
NOT_PDF_TYPE_DETAIL: Final = "Only PDF files are accepted; the file was sent as another type."
NOT_PDF_CONTENT_DETAIL: Final = "Only PDF files are accepted; the file's content is not a PDF."
NOT_XML_SUFFIX_DETAIL: Final = (
    f"An ESPD request must be an XML file; the filename must end in {XML_SUFFIX}."
)
NOT_XML_TYPE_DETAIL: Final = (
    "An ESPD request must be sent as XML; the file was sent as another type."
)
NOT_ESPD_CONTENT_DETAIL: Final = (
    "This file is not a readable ESPD request (DUME). Upload the ESPD request XML the buyer "
    "published with the tender."
)
XML_TOO_LARGE_DETAIL: Final = (
    f"An ESPD request larger than {MAX_XML_BYTES} bytes is not read; check the file."
)
EMPTY_FILE_DETAIL: Final = "The uploaded file is empty."
TOO_LARGE_DETAIL: Final = f"The file is larger than {MAX_UPLOAD_MEGABYTES} MB."
NO_SUCH_DOCUMENT_DETAIL: Final = "No such document."
DOCUMENT_IN_USE_DETAIL: Final = (
    "This document is part of a bid that has already been started, and the requirements in "
    "that bid cite its pages. Delete the bid to remove it."
)
NOT_DELETED_DETAIL: Final = "The document could not be deleted right now. Try again."
STORAGE_NOT_CONFIGURED_DETAIL: Final = (
    "Document storage is not configured on this server, so uploads are unavailable."
)
URL_NOT_SIGNED_DETAIL: Final = "The document could not be opened right now. Try again."


# ------------------------------------------------------------------------ response models


class DocumentResponse(BaseModel):
    """One uploaded document and how far it has got. `GET /documents/{id}` is polled for it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(description="The document id; use it to poll and to start a bid")
    kind: DocumentKind = Field(
        description=(
            "Company evidence, tender document, tender notice, or the buyer's published "
            "ESPD request (DUME), which is the one kind that is XML rather than PDF"
        )
    )
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
    flagged_chunks: list[int] = Field(
        description=(
            "Chunk numbers the injection guard withheld from the corpus (S2.3.1). Text in "
            "them reached no prompt and no embedding, so a reviewer is told rather than "
            "left to wonder why a passage they can see on the page was never cited."
        )
    )
    flagged_chunk_count: int = Field(description="len(flagged_chunks), for a badge")
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
            flagged_chunks=list(record.flagged_chunks),
            flagged_chunk_count=len(record.flagged_chunks),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class DocumentListResponse(BaseModel):
    """One page of the calling company's documents, newest first."""

    model_config = ConfigDict(frozen=True)

    documents: list[DocumentResponse] = Field(description="Newest first")
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Pass as `cursor` for the next page. `null` means this is the last page — which "
            "is not the same as a full one, so read this rather than counting rows."
        ),
    )


class DocumentUrlResponse(BaseModel):
    """A short-lived URL the browser's PDF viewer can load; ask again once it has expired."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="Signed download URL; append #page=N to open a page")
    expires_at: datetime = Field(description="When the URL stops working, UTC")


# ------------------------------------------------------------------------- dependencies


def get_document_records(db: Database = Depends(get_database)) -> DocumentsReadModel:
    """The `documents` writer on the process pool. Overridden with a fake in tests."""
    return DocumentsReadModel(db)


def get_document_store(
    settings: Settings = Depends(get_app_settings),
) -> CompanyDocumentStore:
    """The configured Storage bucket behind the company prefix, or 503 when there is none.

    The message from `storage_bucket` names the missing variables; that is for the
    operator's log, not the bidder's screen, hence the fixed detail.
    """
    try:
        return company_document_store(settings)
    except StorageError as exc:
        logger.error("document storage unavailable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORAGE_NOT_CONFIGURED_DETAIL
        ) from exc


def get_pipeline(
    settings: Settings = Depends(get_company_settings),
    db: Database = Depends(get_database),
    records: DocumentsReadModel = Depends(get_document_records),
    store: CompanyDocumentStore = Depends(get_document_store),
) -> DocumentPipeline:
    """The production wiring, which `ingestion.pipeline.build_pipeline` owns.

    **On the company's own key (S5.4).** Embedding an upload is the company's spend like
    any other, so `get_company_settings` supplies the key and a company without one is
    refused with 402 before a single chunk is embedded, rather than quietly billed to the
    application key.

    Built per request because the embeddings client owns an HTTP pool that the background
    task must be able to close. The factory is shared with S2.4.3's demo seed so that a
    seeded document and an uploaded one are chunked and embedded by the same numbers.
    """
    return build_pipeline(settings, source=db, store=store, records=records)


# ------------------------------------------------------------------------------- routes


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
    summary="Upload a document",
    # S2.3.3. A route dependency rather than a parameter, so it is settled before the
    # multipart body is read: a caller over its limit never gets to send 50 MB.
    dependencies=[Depends(document_upload_limit)],
    responses=RATE_LIMITED_RESPONSES,
)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(
        description=(
            f"The PDF, at most {MAX_UPLOAD_MEGABYTES} MB — or, for the kind "
            f"`tender_espd_request`, the buyer's ESPD request XML, at most "
            f"{MAX_XML_BYTES} bytes"
        )
    ),
    kind: DocumentKind = Form(
        description="What the document is; it also decides which file types are accepted"
    ),
    company: CompanyContext = Depends(current_company),
    pipeline: DocumentPipeline = Depends(get_pipeline),
) -> DocumentResponse:
    """Accept the file and answer 202 at once; poll `GET /documents/{id}` until it is done.

    Every kind but `tender_espd_request` must be a PDF; that one must be the buyer's ESPD
    request (DUME) as XML, and nothing else may be (see the module docstring).

    The status moves `uploaded → parsed → embedded → ready`. A failure carries a
    `failure_reason` the bidder can act on.
    """
    upload = await validated_upload(file, kind)
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


@router.get(
    "/{document_id}/url",
    response_model=DocumentUrlResponse,
    summary="A short-lived URL for the document's file",
)
async def get_document_url(
    document_id: uuid.UUID,
    company: CompanyContext = Depends(current_company),
    records: DocumentsReadModel = Depends(get_document_records),
    store: CompanyDocumentStore = Depends(get_document_store),
) -> DocumentUrlResponse:
    """Sign the document's file for the browser's PDF viewer (S4.5.1's source panel).

    The URL lives for the configured TTL, ten minutes at most; `expires_at` says when to
    ask again. Another company's id, an unknown id and a file Storage no longer holds are
    the same 404.
    """
    record = await records.get(company_id=_company_uuid(company), document_id=document_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_DOCUMENT_DETAIL)
    try:
        # The Storage client is synchronous; keep the request loop free while it signs.
        signed = await asyncio.to_thread(
            store.signed_url, company_id=company.company_id, key=record.storage_path
        )
    except ObjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_DOCUMENT_DETAIL) from exc
    except StorageError as exc:
        # The exception never carries the key or a token (storage.py); the log gets the
        # document id, the screen a sentence to act on.
        logger.error("document %s could not be signed: %s", document_id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=URL_NOT_SIGNED_DETAIL) from exc
    return DocumentUrlResponse(url=signed.url, expires_at=signed.expires_at)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded document",
)
async def delete_document(
    document_id: uuid.UUID,
    company: CompanyContext = Depends(current_company),
    records: DocumentsReadModel = Depends(get_document_records),
    store: CompanyDocumentStore = Depends(get_document_store),
) -> Response:
    """Remove a document the bidder uploaded, and the file behind it.

    **Only while no bid has claimed it.** A tender's documents belong to the run that cites
    them, so once `POST /bids` has attached one, deleting it would leave requirements
    pointing at a page nobody can open; that is a 409 naming the bid, not a silent refusal.
    Another company's id and an unknown id are the same 404 the rest of this router answers.

    The file goes first and the row second. A file Storage has already lost is not an error
    -- the row would otherwise be stranded behind a blob that is not there -- but a Storage
    that *refuses* leaves the row in place, because a document still listed can be deleted
    again while a file with no row can be reached by nothing.
    """
    record = await records.get(company_id=_company_uuid(company), document_id=document_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_DOCUMENT_DETAIL)
    if record.bid_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=DOCUMENT_IN_USE_DETAIL)
    try:
        # The Storage client is synchronous; keep the request loop free while it deletes.
        await asyncio.to_thread(
            store.remove, company_id=company.company_id, key=record.storage_path
        )
    except ObjectNotFoundError:
        logger.info("document %s had no file in Storage; deleting the row anyway", document_id)
    except StorageError as exc:
        logger.error("document %s could not be deleted: %s", document_id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=NOT_DELETED_DETAIL) from exc
    await records.delete(company_id=_company_uuid(company), document_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=DocumentListResponse, summary="List the company's documents")
async def list_documents(
    limit: Annotated[int | None, Query(description=PAGE_LIMIT_DESCRIPTION)] = None,
    cursor: Annotated[str | None, Query(description=PAGE_CURSOR_DESCRIPTION)] = None,
    company: CompanyContext = Depends(current_company),
    records: DocumentsReadModel = Depends(get_document_records),
) -> DocumentListResponse:
    """One page of the calling company's documents, newest first (M13).

    The list was unbounded, then bounded and silently truncated. It is now paged: follow
    `next_cursor` for the rest. A cursor this API did not issue is a 422 rather than a page
    from somewhere unintended — see `readmodel/pagination.py`.
    """
    asked = page_request(limit=limit, cursor=cursor)
    page = await records.list(
        company_id=_company_uuid(company), limit=asked.limit, after=asked.after
    )
    return DocumentListResponse(
        documents=[DocumentResponse.from_record(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


# ------------------------------------------------------------------------------ helpers


def _company_uuid(company: CompanyContext) -> uuid.UUID:
    """`CompanyContext.company_id` is a string by contract; the read model binds UUIDs."""
    return uuid.UUID(company.company_id)


async def validated_upload(file: UploadFile, kind: DocumentKind) -> Upload:
    """The multipart part as an `Upload`, or the 4xx that names what is wrong with it.

    `kind` chooses the accept-list: a published ESPD request is read as XML, everything else
    as a PDF (see the module docstring). The filename is the one check both share.
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=NO_FILENAME_DETAIL)
    if kind in XML_KINDS:
        return await _validated_espd_request(file, filename)
    return await _validated_pdf(file, filename)


async def _validated_espd_request(file: UploadFile, filename: str) -> Upload:
    """The XML branch: suffix, declared type, and a root element that is an ESPD request.

    The sniff is a full parse through `ingestion/espd.py`, which is the hardened reader —
    so this is also where a hostile XML is refused, before any background task exists. It is
    synchronous work inside the request, which is acceptable because `MAX_XML_BYTES` bounds
    it at four megabytes and the French fixture's 145 KB form parses in milliseconds.
    """
    if not filename.lower().endswith(XML_SUFFIX):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_XML_SUFFIX_DETAIL
        )
    declared = _declared_type(file)
    if declared not in XML_CONTENT_TYPES and declared not in GENERIC_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_XML_TYPE_DETAIL)

    content = await _body(file, limit=MAX_XML_BYTES, too_large=XML_TOO_LARGE_DETAIL)
    try:
        parse_espd_request(content)
    except EspdParseError as exc:
        # The reason is in the log for an operator; the bidder gets one sentence, and the
        # exception's own message never reaches it (it is derived from the file, ADR-0008).
        logger.info("upload refused: %s is not an ESPD request (%s)", filename, exc)
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_ESPD_CONTENT_DETAIL
        ) from exc
    return Upload(filename=filename, content_type=XML_CONTENT_TYPE, content=content)


async def _validated_pdf(file: UploadFile, filename: str) -> Upload:
    """The PDF branch: suffix, declared type, and the `%PDF-` magic bytes.

    The stored content type is always `application/pdf`: the magic bytes have been checked,
    so that is what the file *is*, whatever the client declared.
    """
    if not filename.lower().endswith(PDF_SUFFIX):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_SUFFIX_DETAIL
        )

    declared = _declared_type(file)
    if declared not in PDF_CONTENT_TYPES and declared not in GENERIC_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_TYPE_DETAIL)

    content = await _body(file, limit=MAX_UPLOAD_BYTES, too_large=TOO_LARGE_DETAIL)
    if not content.startswith(PDF_MAGIC):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=NOT_PDF_CONTENT_DETAIL
        )
    return Upload(filename=filename, content_type=DEFAULT_CONTENT_TYPE, content=content)


def _declared_type(file: UploadFile) -> str:
    """The part's content type without its parameters, lower-cased. Never trusted alone."""
    return (file.content_type or "").split(";", 1)[0].strip().lower()


async def _body(file: UploadFile, *, limit: int, too_large: str) -> bytes:
    """The part's bytes, or the 4xx for empty and oversized.

    Read with a limit of one byte over the cap, so an oversized upload is recognised
    without being held in memory whole.
    """
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=too_large)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=EMPTY_FILE_DETAIL)
    return content


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
