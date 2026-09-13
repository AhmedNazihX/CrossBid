"""S2.4.3 — put the demo GmbH in a database, and change nothing on the second run.

Three things have to exist before the walkthrough can be recorded, and all three are here
because any one of them missing leaves a tenant that half works:

1. **The `companies` row**, with the pack's real facts rather than placeholders. The
   column/jsonb split is `readmodel/companies.py`'s and is not restated: a second definition
   of where `staff_fte` lives is a second thing to keep in step with the check constraints.
2. **The same profile in the LangGraph Store**, at `profile/{company_id}`. That is what the
   agent reads (S2.4.1 writes it on every save), so a company that exists only in Postgres is
   half-seeded — `check_reqs` would find no memory of the bidder it is checking.
3. **Every document driven to `ready`** through the *production* `DocumentPipeline`. Not a
   shortcut insert: `ready` is a claim that the file is in Storage, parsed, chunked and
   embedded, and `company_rag_search` returning nothing is exactly the failure the
   walkthrough cannot survive. Running the real state machine is also what makes a seeded
   document indistinguishable from an uploaded one.

**How a second run recognises what it already did, and why it spends nothing.** Each unit is
addressed by a deterministic id (`demo/company.py`) and asks the database before it acts:

* the company row is an `insert ... on conflict (id) do nothing`, so a second run inserts
  nothing and then *compares* the stored profile with the pack's, writing only on a real
  difference. Re-saving an identical profile would move `updated_at`, which is a change;
* the Store item is read before it is written, and an identical item is left alone;
* a document whose row exists is skipped **before** `accept`, so nothing is uploaded and
  `embed_texts` is never called. Embeddings are the only thing here that costs money, and
  this is the check that makes "changes nothing" also mean "spends nothing".

**A document whose row exists but is not `ready` is reported, not repaired.** The honest
options were all worse: re-uploading hits `x-upsert: false` and fails, re-embedding would
leave the earlier run's chunks beside the new ones, and deleting rows is not something a seed
should do behind an operator's back. So the run finishes, `SeedReport.unready` names the
documents and `is_complete` is false, which the CLI turns into a non-zero exit and a sentence
saying what to remove. An interrupted seed is rare; a seed that silently doubles a corpus or
quietly deletes evidence is not a trade worth making.

Documents are processed **one at a time**. `EmbeddingsClient` already batches chunks per
request, the pack is ten short PDFs, and a sequential loop keeps the printed progress honest
and the connection pool at one borrower — concurrency here would buy seconds and cost the
ability to say which document failed.

Every collaborator is an argument typed as a `Protocol` (or `BaseStore`), so the unit suite
runs this against the same fakes the pipeline's own tests use and never opens a socket. The
concrete wiring lives in `scripts/seed_demo_company.py`, which is the only place that has
`Settings` and a `Database`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from langgraph.store.base import BaseStore

from crossbid.demo.company import DEMO_COMPANY_ID, DEMO_OWNER_USER_ID, DemoPack, PackDocument
from crossbid.ingestion.pipeline import DocumentPipeline, Upload
from crossbid.ingestion.storage import object_key
from crossbid.memory.profile import PROFILE_STORE_KEY, profile_namespace
from crossbid.models import CompanyProfile, DocumentKind
from crossbid.readmodel.documents import DocumentRecord, DocumentStatus
from crossbid.settings import Environment, Settings

SEEDED_KIND: Final = DocumentKind.COMPANY_EVIDENCE
"""The pack is the bidder's own evidence, which outlives any bid — so it is embedded at
upload (`ingestion.pipeline.EMBEDDED_KINDS`), which is what makes it retrievable at all."""

PDF_CONTENT_TYPE: Final = "application/pdf"


class SeedError(RuntimeError):
    """The seed must not run here, or the database contradicted itself mid-run."""


# ----------------------------------------------------------------------------- outcomes


class CompanyOutcome(StrEnum):
    """What the run did to the `companies` row. `UNCHANGED` is the second run's answer."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class MemoryOutcome(StrEnum):
    """What the run did to `profile/{company_id}` in the Store."""

    WRITTEN = "written"
    UNCHANGED = "unchanged"


class DocumentOutcome(StrEnum):
    """Whether this run ingested the document or found it already there.

    Deliberately not a verdict: a `SEEDED` document can still have ended `failed`, and a
    `PRESENT` one can have been left half-processed by an earlier run. `DocumentResult.status`
    carries that, so "what the run did" and "where the document got to" stay separable.
    """

    SEEDED = "seeded"
    PRESENT = "present"


@dataclass(frozen=True, slots=True)
class DocumentResult:
    """One document after the run: what happened to it, and where it ended up."""

    filename: str
    document_id: uuid.UUID
    outcome: DocumentOutcome
    status: DocumentStatus
    failure_reason: str | None = None

    @property
    def is_ready(self) -> bool:
        """The only status the walkthrough can use: stored, parsed, chunked and embedded."""
        return self.status is DocumentStatus.READY

    @classmethod
    def of(
        cls, record: DocumentRecord, *, filename: str, outcome: DocumentOutcome
    ) -> DocumentResult:
        """Read the outcome off the row the pipeline handed back, never off a guess."""
        return cls(
            filename=filename,
            document_id=record.id,
            outcome=outcome,
            status=record.status,
            failure_reason=record.failure_reason,
        )


@dataclass(frozen=True, slots=True)
class SeedReport:
    """Everything one run did, so the CLI prints it and a test asserts on it."""

    company: CompanyOutcome
    memory: MemoryOutcome
    documents: tuple[DocumentResult, ...]

    @property
    def changed(self) -> bool:
        """False is the acceptance criterion for a second run: nothing was written."""
        return (
            self.company is not CompanyOutcome.UNCHANGED
            or self.memory is not MemoryOutcome.UNCHANGED
            or any(result.outcome is DocumentOutcome.SEEDED for result in self.documents)
        )

    @property
    def unready(self) -> tuple[DocumentResult, ...]:
        """Documents the walkthrough cannot use. Empty on a good run."""
        return tuple(result for result in self.documents if not result.is_ready)

    @property
    def is_complete(self) -> bool:
        """The company, its memory and *every* document are in place."""
        return bool(self.documents) and not self.unready


# ------------------------------------------------------------------------ collaborators


class CompanyRecords(Protocol):
    """`readmodel.companies.CompaniesReadModel`, by shape."""

    async def create(
        self, *, company_id: uuid.UUID, owner_user_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None: ...

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None: ...

    async def save(
        self, *, company_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None: ...


class DocumentLookup(Protocol):
    """The one read the seed makes on `readmodel.documents.DocumentsReadModel`."""

    async def get(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord | None: ...


# ----------------------------------------------------------------------------- guards


def refuse_in_production(settings: Settings) -> None:
    """A fictional GmbH with fabricated certificates must never reach a real deployment.

    The same gate `scripts/seed_dev_company.py` and `settings._refuse_dev_auth_in_production`
    apply, read off the settings the app itself starts from rather than off `os.environ`, so
    `ENV` is resolved once and in one way.
    """
    if settings.env.environment is Environment.PRODUCTION:
        raise SeedError(
            "ENV=production: refusing to seed the demo company. Every document in the pack "
            "is a fabricated certificate and the tenant is owned by nobody. Run this only "
            "against a local or development database."
        )


# ------------------------------------------------------------------------------ seeding


async def seed_demo_company(
    *,
    companies: CompanyRecords,
    memory: BaseStore,
    documents: DocumentLookup,
    pipeline: DocumentPipeline,
    pack: DemoPack,
    company_id: uuid.UUID = DEMO_COMPANY_ID,
    owner_user_id: uuid.UUID = DEMO_OWNER_USER_ID,
) -> SeedReport:
    """The whole seed: row, memory, documents. Safe to run again; see the module docstring.

    The order matters. `documents.company_id` references `companies (id)`, so the row has to
    exist before the first upload; and the memory write is cheap, so it happens while nothing
    expensive has been spent yet.
    """
    company = await seed_company(
        companies, pack.profile, company_id=company_id, owner_user_id=owner_user_id
    )
    remembered = await seed_memory(memory, pack.profile, company_id=company_id)
    results = [
        await seed_document(pipeline, documents, document, company_id=company_id)
        for document in pack.documents
    ]
    return SeedReport(company=company, memory=remembered, documents=tuple(results))


async def seed_company(
    records: CompanyRecords,
    profile: CompanyProfile,
    *,
    company_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> CompanyOutcome:
    """Create the row, or leave an identical one exactly as it is.

    The insert goes first and its `on conflict do nothing` decides: a returned row means this
    run created the tenant, and `None` means somebody already had. Only then is the stored
    profile read and compared — so there is no select-then-insert window for two runs to race
    through, and an unchanged profile never moves `updated_at`.
    """
    created = await records.create(
        company_id=company_id, owner_user_id=owner_user_id, profile=profile
    )
    if created is not None:
        return CompanyOutcome.CREATED

    if await records.get(company_id=company_id) == profile:
        return CompanyOutcome.UNCHANGED

    if await records.save(company_id=company_id, profile=profile) is None:
        raise SeedError(
            f"company {company_id} exists for the insert but not for the update. Something "
            "deleted the row mid-run; re-run the seed against a quiet database."
        )
    return CompanyOutcome.UPDATED


async def seed_memory(
    store: BaseStore, profile: CompanyProfile, *, company_id: uuid.UUID
) -> MemoryOutcome:
    """Write the profile to `profile/{company_id}`, unless it already says exactly this.

    `model_dump(mode="json")` is the shape `routers/companies.py` writes on every save, and
    it has to stay that shape: the agent reads one item and does not care which writer put it
    there.
    """
    namespace = profile_namespace(company_id)
    document = profile.model_dump(mode="json")
    remembered = await store.aget(namespace, PROFILE_STORE_KEY)
    if remembered is not None and remembered.value == document:
        return MemoryOutcome.UNCHANGED
    await store.aput(namespace, PROFILE_STORE_KEY, document)
    return MemoryOutcome.WRITTEN


async def seed_document(
    pipeline: DocumentPipeline,
    lookup: DocumentLookup,
    document: PackDocument,
    *,
    company_id: uuid.UUID,
) -> DocumentResult:
    """Ingest one document, or report the row that is already there without touching it.

    The lookup is the first thing that happens and the reason a second run is free: a
    document already in the table is never stored, parsed or embedded again. What comes back
    is the row itself, so a half-finished earlier run is reported as what it is rather than
    as a success.
    """
    existing = await lookup.get(company_id=company_id, document_id=document.document_id)
    if existing is not None:
        return DocumentResult.of(
            existing, filename=document.filename, outcome=DocumentOutcome.PRESENT
        )

    upload = Upload(
        filename=document.filename,
        content_type=PDF_CONTENT_TYPE,
        content=document.content,
    )
    record = await pipeline.accept(
        company_id=company_id,
        kind=SEEDED_KIND,
        upload=upload,
        document_id=document.document_id,
    )
    # `process` never raises for a document failure: it writes `failed` with a reason and
    # hands the row back, which is exactly what this report wants to carry.
    processed = await pipeline.process(record, upload)
    return DocumentResult.of(
        processed, filename=document.filename, outcome=DocumentOutcome.SEEDED
    )


# --------------------------------------------------------------------------- rendering


def render_plan(pack: DemoPack, *, company_id: uuid.UUID = DEMO_COMPANY_ID) -> list[str]:
    """What `--dry-run` prints: every id the run would write, and nothing it would spend."""
    lines = [
        f"would seed company {company_id} ({pack.profile.name})",
        f"  profile        {len(pack.profile.turnover)} turnover years, "
        f"{len(pack.profile.certificates)} certificates",
        f"  memory         {'/'.join(profile_namespace(company_id))} -> {PROFILE_STORE_KEY}",
        f"  documents      {len(pack.documents)} as {SEEDED_KIND.value}, each to 'ready'",
    ]
    lines.extend(
        f"    {document.document_id}  {document.filename}" for document in pack.documents
    )
    return lines


def render_report(report: SeedReport, *, company_id: uuid.UUID = DEMO_COMPANY_ID) -> list[str]:
    """What a real run prints. Says what changed, so a second run visibly says "nothing"."""
    lines = [
        f"company {report.company.value}: {company_id}",
        f"memory {report.memory.value}: {'/'.join(profile_namespace(company_id))}",
        *_document_lines(report.documents),
    ]
    lines.append(
        "documents: "
        f"{sum(1 for r in report.documents if r.outcome is DocumentOutcome.SEEDED)} seeded, "
        f"{sum(1 for r in report.documents if r.outcome is DocumentOutcome.PRESENT)} already "
        f"present, {len(report.unready)} not ready"
    )
    if not report.changed:
        lines.append("nothing changed: the demo company was already seeded")
    lines.extend(_unready_advice(report.unready, company_id=company_id))
    return lines


def _document_lines(results: Iterable[DocumentResult]) -> list[str]:
    return [
        f"  {result.outcome.value:<8} {result.status.value:<8} {result.filename}"
        + (f" — {result.failure_reason}" if result.failure_reason else "")
        for result in results
    ]


def _unready_advice(unready: tuple[DocumentResult, ...], *, company_id: uuid.UUID) -> list[str]:
    """The one repair the seed will not do for you, spelled out. See the module docstring.

    Both halves are named because deleting only the row is not enough: the Storage key is
    derived from the same deterministic id, and `CompanyDocumentStore` refuses to overwrite
    an object (`x-upsert: false`), so the next run would fail on the file that is still
    there. Deleting the row takes its chunks with it — `company_chunks.document_id`
    cascades — so these two lines are the whole repair.
    """
    if not unready:
        return []
    return [
        "",
        f"{len(unready)} document(s) are not ready, so the walkthrough would find no "
        "evidence for them. This seed never re-ingests a document that already has a row: "
        "re-uploading would collide in Storage and re-embedding would duplicate the chunks. "
        "Delete each documents row below (its chunks cascade) and the object beside it from "
        "the Storage bucket, then seed again:",
        *(
            f"    row {result.document_id}  object "
            f"{_storage_key(result, company_id=company_id)}"
            for result in unready
        ),
    ]


def _storage_key(result: DocumentResult, *, company_id: uuid.UUID) -> str:
    """The object the row points at, built by the one function that builds every key."""
    return object_key(
        company_id=str(company_id),
        document_id=str(result.document_id),
        filename=result.filename,
    )
