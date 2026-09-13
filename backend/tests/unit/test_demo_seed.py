"""S2.4.3 — the seed: everything exists and is `ready`, and a second run changes nothing.

Offline, and the "second run" half is the point. The pipeline is `conftest`'s `harness()` —
the *real* `DocumentPipeline` and `Chunker` over fakes for Storage, the parser, the embeddings
client and the chunk writer — so a seeded document really does walk `uploaded → parsed →
embedded → ready`, and the fakes are what let the second run be checked for the thing that
actually costs money: `FakeStore.uploads` and `FakeEmbedder.calls` must not grow.

Two fakes are defined here rather than in `conftest.py` because one module needs them:
`InMemoryCompanies` (the `create`/`get`/`save` trio, which no other suite drives) and
`RecordingProfileStore` (`aget` *and* `aput`; `test_companies_router.py`'s store records
`aput` alone, because the router never reads back).

The CLI's own tests monkeypatch `load_settings`: the script deliberately reads the repository
`.env` so that `make seed-demo` works on a developer's machine, and no test may depend on
what that file happens to contain.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from crossbid.demo.company import DemoPack, PackDocument, PackError, document_id
from crossbid.demo.seed import (
    SEEDED_KIND,
    CompanyOutcome,
    DocumentOutcome,
    DocumentResult,
    MemoryOutcome,
    SeedError,
    SeedReport,
    refuse_in_production,
    render_plan,
    render_report,
    seed_company,
    seed_demo_company,
    seed_document,
    seed_memory,
)
from crossbid.memory.profile import PROFILE_STORE_KEY, profile_namespace
from crossbid.models import CompanyProfile, LegalForm, Tone
from crossbid.readmodel.documents import DocumentStatus
from crossbid.settings import AuthMode, Environment, Settings, load_settings
from tests.conftest import (
    COMPANY_PROFILE,
    PDF_BYTES,
    FakeEmbedder,
    Harness,
    harness,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "seed_demo_company.py"

COMPANY_ID = uuid.UUID("91d42546-c9ba-5815-bbb7-8831a728271d")
OWNER_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")

FIRST = "Handelsregisterauszug.pdf"
SECOND = "Zertifikat_ISO_IEC_27001_2022.pdf"

OTHER_PROFILE = CompanyProfile(
    name="Andere IT Services GmbH",
    country="de",
    legal_form=LegalForm.GMBH,
    language="de",
    tone=Tone.PLAIN,
)


def pack(*filenames: str, profile: CompanyProfile = COMPANY_PROFILE) -> DemoPack:
    """A pack with no file behind it: the seed never reads disk, only what it is handed."""
    return DemoPack(
        profile=profile,
        documents=tuple(
            PackDocument(filename=name, document_id=document_id(name), content=PDF_BYTES)
            for name in (filenames or (FIRST,))
        ),
    )


# --------------------------------------------------------------------------------- fakes


@dataclass
class InMemoryCompanies:
    """`CompaniesReadModel` over a dict; `create` behaves like `on conflict do nothing`."""

    profiles: dict[uuid.UUID, CompanyProfile] = field(default_factory=dict)
    owners: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    saves: int = 0
    inserts: int = 0
    vanish_on_save: bool = False

    async def create(
        self, *, company_id: uuid.UUID, owner_user_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        self.inserts += 1
        if company_id in self.profiles:
            return None
        self.profiles[company_id] = profile
        self.owners[company_id] = owner_user_id
        return profile

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        return self.profiles.get(company_id)

    async def save(
        self, *, company_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        self.saves += 1
        if self.vanish_on_save or company_id not in self.profiles:
            return None
        self.profiles[company_id] = profile
        return profile


@dataclass(frozen=True)
class StoredItem:
    """The slice of LangGraph's `Item` the seed reads back."""

    value: dict[str, Any]


@dataclass
class RecordingProfileStore:
    """`BaseStore.aget` / `aput`, recording every write so a second run can be checked."""

    items: dict[tuple[tuple[str, ...], str], dict[str, Any]] = field(default_factory=dict)
    writes: int = 0

    async def aget(self, namespace: tuple[str, ...], key: str) -> StoredItem | None:
        found = self.items.get((namespace, key))
        return None if found is None else StoredItem(found)

    async def aput(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        self.writes += 1
        self.items[(namespace, key)] = value


def offline(**overrides: Any) -> Settings:
    """Settings with no `.env` behind them; `env_file=None` is what keeps this offline."""
    settings = load_settings(env_file=None)
    if not overrides:
        return settings
    return Settings(env=settings.env.model_copy(update=overrides), runtime=settings.runtime)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two secrets `EnvSettings` requires, and nothing a developer's shell might add."""
    for name in ("ENV", "AUTH_MODE", "DATABASE_URL", "WEB_ORIGIN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-not-a-real-key")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "not-a-real-encryption-key=")


# ------------------------------------------------------------------------ the production gate


def test_production_is_refused_naming_what_is_in_the_pack(env: None) -> None:
    """A fictional GmbH with fabricated certificates must never reach a deployment."""
    with pytest.raises(SeedError, match="production"):
        refuse_in_production(
            offline(environment=Environment.PRODUCTION, auth_mode=AuthMode.SUPABASE)
        )


def test_development_is_allowed(env: None) -> None:
    refuse_in_production(offline())


# ------------------------------------------------------------------------------- the row


@pytest.mark.anyio
async def test_an_empty_database_gets_the_company_with_the_packs_real_facts() -> None:
    # Arrange
    records = InMemoryCompanies()

    # Act
    outcome = await seed_company(
        records, COMPANY_PROFILE, company_id=COMPANY_ID, owner_user_id=OWNER_ID
    )

    # Assert
    assert outcome is CompanyOutcome.CREATED
    assert records.profiles[COMPANY_ID] == COMPANY_PROFILE
    assert records.owners[COMPANY_ID] == OWNER_ID
    assert records.saves == 0, "a fresh insert must not follow itself with an update"


@pytest.mark.anyio
async def test_a_second_run_does_not_touch_an_identical_row() -> None:
    """An update would move `updated_at`, which is a change the criterion forbids."""
    # Arrange
    records = InMemoryCompanies(profiles={COMPANY_ID: COMPANY_PROFILE})

    # Act
    outcome = await seed_company(
        records, COMPANY_PROFILE, company_id=COMPANY_ID, owner_user_id=OWNER_ID
    )

    # Assert
    assert outcome is CompanyOutcome.UNCHANGED
    assert records.saves == 0


@pytest.mark.anyio
async def test_a_row_that_drifted_from_the_pack_is_rewritten() -> None:
    """The pack is the authority: a hand-edited demo tenant is put back as it should be."""
    # Arrange
    records = InMemoryCompanies(profiles={COMPANY_ID: OTHER_PROFILE})

    # Act
    outcome = await seed_company(
        records, COMPANY_PROFILE, company_id=COMPANY_ID, owner_user_id=OWNER_ID
    )

    # Assert
    assert outcome is CompanyOutcome.UPDATED
    assert records.profiles[COMPANY_ID] == COMPANY_PROFILE


@pytest.mark.anyio
async def test_a_row_that_disappears_mid_run_is_a_loud_failure() -> None:
    """Never a silent half-seed: the documents that follow would have no company to hang on."""
    records = InMemoryCompanies(profiles={COMPANY_ID: OTHER_PROFILE}, vanish_on_save=True)

    with pytest.raises(SeedError, match="deleted the row mid-run"):
        await seed_company(
            records, COMPANY_PROFILE, company_id=COMPANY_ID, owner_user_id=OWNER_ID
        )


# ---------------------------------------------------------------------------- the memory


@pytest.mark.anyio
async def test_the_profile_is_written_to_the_store_namespace_the_agent_reads() -> None:
    """A company that exists only in Postgres is half-seeded (`check_reqs` reads this)."""
    # Arrange
    store = RecordingProfileStore()

    # Act
    outcome = await seed_memory(store, COMPANY_PROFILE, company_id=COMPANY_ID)

    # Assert
    assert outcome is MemoryOutcome.WRITTEN
    remembered = store.items[(profile_namespace(COMPANY_ID), PROFILE_STORE_KEY)]
    assert remembered == COMPANY_PROFILE.model_dump(mode="json")
    assert remembered["name"] == COMPANY_PROFILE.name, "column fields go in too"


@pytest.mark.anyio
async def test_an_identical_memory_item_is_left_alone() -> None:
    store = RecordingProfileStore()
    await seed_memory(store, COMPANY_PROFILE, company_id=COMPANY_ID)

    outcome = await seed_memory(store, COMPANY_PROFILE, company_id=COMPANY_ID)

    assert outcome is MemoryOutcome.UNCHANGED
    assert store.writes == 1


@pytest.mark.anyio
async def test_a_memory_item_that_drifted_is_rewritten() -> None:
    store = RecordingProfileStore()
    await seed_memory(store, OTHER_PROFILE, company_id=COMPANY_ID)

    outcome = await seed_memory(store, COMPANY_PROFILE, company_id=COMPANY_ID)

    assert outcome is MemoryOutcome.WRITTEN
    assert store.writes == 2


# -------------------------------------------------------------------------- one document


@pytest.mark.anyio
async def test_a_document_is_driven_all_the_way_to_ready() -> None:
    """`ready` is the claim the walkthrough depends on: stored, parsed, chunked, embedded."""
    # Arrange
    h = harness()
    document = pack().documents[0]

    # Act
    result = await seed_document(h.pipeline, h.records, document, company_id=COMPANY_ID)

    # Assert
    assert result.outcome is DocumentOutcome.SEEDED
    assert result.status is DocumentStatus.READY
    assert result.document_id == document.document_id
    assert h.records.statuses_of(document.document_id) == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.READY,
    ]
    assert h.writer.inserts, "no chunks would mean company_rag_search returns nothing"


@pytest.mark.anyio
async def test_a_seeded_document_is_company_evidence_so_it_is_embedded_at_upload() -> None:
    """Only `EMBEDDED_KINDS` get vectors at upload; a tender kind would be `ready` and blind."""
    h = harness()

    await seed_document(h.pipeline, h.records, pack().documents[0], company_id=COMPANY_ID)

    assert h.records.rows[pack().documents[0].document_id].kind is SEEDED_KIND


@pytest.mark.anyio
async def test_a_document_that_is_already_there_costs_nothing() -> None:
    """The check that makes "changes nothing" also mean "spends nothing"."""
    # Arrange
    h = harness()
    document = pack().documents[0]
    await seed_document(h.pipeline, h.records, document, company_id=COMPANY_ID)
    uploads, embeddings = len(h.store.uploads), len(h.embedder.calls)

    # Act
    result = await seed_document(h.pipeline, h.records, document, company_id=COMPANY_ID)

    # Assert
    assert result.outcome is DocumentOutcome.PRESENT
    assert result.status is DocumentStatus.READY
    assert len(h.store.uploads) == uploads
    assert len(h.embedder.calls) == embeddings


@pytest.mark.anyio
async def test_a_document_left_half_processed_is_reported_not_re_ingested() -> None:
    """Re-uploading collides in Storage and re-embedding duplicates chunks; see the module."""
    # Arrange
    h = harness()
    document = pack().documents[0]
    await h.records.insert(
        company_id=COMPANY_ID,
        document_id=document.document_id,
        kind=SEEDED_KIND,
        name=document.filename,
        storage_path="key",
    )
    await h.records.mark_failed(
        company_id=COMPANY_ID, document_id=document.document_id, reason="Try again later."
    )

    # Act
    result = await seed_document(h.pipeline, h.records, document, company_id=COMPANY_ID)

    # Assert
    assert result.outcome is DocumentOutcome.PRESENT
    assert result.status is DocumentStatus.FAILED
    assert result.failure_reason == "Try again later."
    assert result.is_ready is False
    assert h.store.uploads == []


@pytest.mark.anyio
async def test_a_document_that_fails_while_being_seeded_carries_its_reason() -> None:
    """`process` writes `failed` rather than raising, so the run finishes and reports."""
    # Arrange
    h = harness(embedder=FakeEmbedder(error=RuntimeError("no")))
    document = pack().documents[0]

    # Act
    result = await seed_document(h.pipeline, h.records, document, company_id=COMPANY_ID)

    # Assert
    assert result.outcome is DocumentOutcome.SEEDED
    assert result.status is DocumentStatus.FAILED
    assert result.failure_reason is not None


# ------------------------------------------------------------------------- the whole seed


async def run_seed(h: Harness, *, companies: Any, store: Any, demo: DemoPack) -> SeedReport:
    return await seed_demo_company(
        companies=companies,
        memory=store,
        documents=h.records,
        pipeline=h.pipeline,
        pack=demo,
        company_id=COMPANY_ID,
        owner_user_id=OWNER_ID,
    )


@pytest.mark.anyio
async def test_an_empty_database_ends_with_the_company_the_profile_and_every_document() -> None:
    """The acceptance criterion, in one test."""
    # Arrange
    h, companies, store = harness(), InMemoryCompanies(), RecordingProfileStore()
    demo = pack(FIRST, SECOND)

    # Act
    report = await run_seed(h, companies=companies, store=store, demo=demo)

    # Assert
    assert report.company is CompanyOutcome.CREATED
    assert report.memory is MemoryOutcome.WRITTEN
    assert [result.status for result in report.documents] == [DocumentStatus.READY] * 2
    assert report.is_complete
    assert report.changed
    assert companies.profiles[COMPANY_ID] == COMPANY_PROFILE
    assert store.items[(profile_namespace(COMPANY_ID), PROFILE_STORE_KEY)]


@pytest.mark.anyio
async def test_a_second_run_changes_nothing_and_spends_nothing() -> None:
    """The other half of the criterion, including the half that has a bill attached."""
    # Arrange
    h, companies, store = harness(), InMemoryCompanies(), RecordingProfileStore()
    demo = pack(FIRST, SECOND)
    await run_seed(h, companies=companies, store=store, demo=demo)
    before = (len(h.store.uploads), len(h.embedder.calls), companies.saves, store.writes)

    # Act
    report = await run_seed(h, companies=companies, store=store, demo=demo)

    # Assert
    assert report.changed is False
    assert report.is_complete
    assert report.company is CompanyOutcome.UNCHANGED
    assert report.memory is MemoryOutcome.UNCHANGED
    assert all(r.outcome is DocumentOutcome.PRESENT for r in report.documents)
    assert (
        len(h.store.uploads),
        len(h.embedder.calls),
        companies.saves,
        store.writes,
    ) == before


@pytest.mark.anyio
async def test_the_company_exists_before_the_first_document_is_uploaded() -> None:
    """`documents.company_id` references `companies (id)`, so the order is not a preference."""
    # Arrange
    h, companies, store = harness(), InMemoryCompanies(), RecordingProfileStore()

    # Act
    await run_seed(h, companies=companies, store=store, demo=pack())

    # Assert
    assert companies.inserts == 1
    assert len(h.store.uploads) == 1


# -------------------------------------------------------------------------- the report


def result(status: DocumentStatus, *, name: str = FIRST) -> DocumentResult:
    return DocumentResult(
        filename=name,
        document_id=document_id(name),
        outcome=DocumentOutcome.SEEDED,
        status=status,
        failure_reason="Try again later." if status is DocumentStatus.FAILED else None,
    )


def test_a_report_with_no_documents_is_not_complete() -> None:
    """An empty pack would otherwise pass as a good run with nothing in it."""
    report = SeedReport(
        company=CompanyOutcome.CREATED, memory=MemoryOutcome.WRITTEN, documents=()
    )

    assert report.is_complete is False


def test_a_report_naming_an_unready_document_is_not_complete() -> None:
    report = SeedReport(
        company=CompanyOutcome.UNCHANGED,
        memory=MemoryOutcome.UNCHANGED,
        documents=(result(DocumentStatus.READY), result(DocumentStatus.FAILED, name=SECOND)),
    )

    assert report.unready == (result(DocumentStatus.FAILED, name=SECOND),)
    assert report.is_complete is False
    assert report.changed is True


def test_the_plan_names_every_id_the_run_would_write() -> None:
    """`--dry-run` has to be enough to see what a real run will do."""
    lines = "\n".join(render_plan(pack(FIRST, SECOND), company_id=COMPANY_ID))

    assert str(COMPANY_ID) in lines
    assert f"{'/'.join(profile_namespace(COMPANY_ID))} -> {PROFILE_STORE_KEY}" in lines
    for name in (FIRST, SECOND):
        assert name in lines
        assert str(document_id(name)) in lines


def test_a_second_runs_report_says_in_words_that_nothing_changed() -> None:
    report = SeedReport(
        company=CompanyOutcome.UNCHANGED,
        memory=MemoryOutcome.UNCHANGED,
        documents=(
            DocumentResult(
                filename=FIRST,
                document_id=document_id(FIRST),
                outcome=DocumentOutcome.PRESENT,
                status=DocumentStatus.READY,
            ),
        ),
    )

    lines = "\n".join(render_report(report, company_id=COMPANY_ID))

    assert "nothing changed" in lines
    assert "1 already present" in lines


def test_the_report_spells_out_the_repair_for_an_unready_document() -> None:
    """Deleting the row is not enough: the Storage object is keyed by the same id."""
    # Arrange
    report = SeedReport(
        company=CompanyOutcome.UNCHANGED,
        memory=MemoryOutcome.UNCHANGED,
        documents=(result(DocumentStatus.FAILED),),
    )

    # Act
    lines = "\n".join(render_report(report, company_id=COMPANY_ID))

    # Assert
    assert "Try again later." in lines
    assert str(document_id(FIRST)) in lines
    assert f"{COMPANY_ID}/{document_id(FIRST)}/{FIRST}" in lines, "the object to remove"


def test_a_good_run_prints_no_repair_advice() -> None:
    report = SeedReport(
        company=CompanyOutcome.CREATED,
        memory=MemoryOutcome.WRITTEN,
        documents=(result(DocumentStatus.READY),),
    )

    lines = "\n".join(render_report(report, company_id=COMPANY_ID))

    assert "Delete each" not in lines
    assert "nothing changed" not in lines


# ------------------------------------------------------------------------------ the CLI


@pytest.fixture(scope="module")
def script() -> Iterator[ModuleType]:
    """`scripts/seed_demo_company.py` as a module; it is a CLI, so it is driven as one."""
    spec = importlib.util.spec_from_file_location("seed_demo_company", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, SCRIPT_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo_company"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("seed_demo_company", None)


@pytest.fixture
def offline_cli(script: ModuleType, monkeypatch: pytest.MonkeyPatch, env: None) -> None:
    """No repository `.env` reaches the CLI, and nothing it does may open a socket."""
    monkeypatch.setattr(script, "load_settings", lambda: offline())

    async def _refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the CLI connected to something")

    monkeypatch.setattr(script, "seed", _refuse)


def test_dry_run_prints_the_plan_and_connects_to_nothing(
    script: ModuleType, offline_cli: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # Act
    code = script.main(["--dry-run"])

    # Assert
    out = capsys.readouterr().out
    assert code == 0
    assert "would seed company 91d42546-c9ba-5815-bbb7-8831a728271d" in out
    assert "Handelsregisterauszug.pdf" in out


def test_production_exits_one_without_reading_the_pack(
    script: ModuleType,
    offline_cli: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    monkeypatch.setattr(
        script,
        "load_settings",
        lambda: offline(environment=Environment.PRODUCTION, auth_mode=AuthMode.SUPABASE),
    )

    # Act
    code = script.main([])

    # Assert
    assert code == 1
    assert "seed error" in capsys.readouterr().err


def test_a_missing_pack_exits_one_with_the_command_that_builds_it(
    script: ModuleType,
    offline_cli: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    def _missing() -> DemoPack:
        raise PackError("no PDF found. Build the pack with `make demo-pack`.")

    monkeypatch.setattr(script, "load_pack", _missing)

    # Act / Assert
    assert script.main([]) == 1
    assert "make demo-pack" in capsys.readouterr().err


def test_a_complete_run_prints_the_report_and_exits_zero(
    script: ModuleType,
    offline_cli: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    report = SeedReport(
        company=CompanyOutcome.CREATED,
        memory=MemoryOutcome.WRITTEN,
        documents=(result(DocumentStatus.READY),),
    )

    async def _seed(*_args: object, **_kwargs: object) -> SeedReport:
        return report

    monkeypatch.setattr(script, "seed", _seed)

    # Act / Assert
    assert script.main([]) == 0
    assert "company created" in capsys.readouterr().out


def test_an_unready_document_exits_one_so_make_seed_demo_fails_loudly(
    script: ModuleType, offline_cli: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    report = SeedReport(
        company=CompanyOutcome.UNCHANGED,
        memory=MemoryOutcome.UNCHANGED,
        documents=(result(DocumentStatus.FAILED),),
    )

    async def _seed(*_args: object, **_kwargs: object) -> SeedReport:
        return report

    monkeypatch.setattr(script, "seed", _seed)

    # Act / Assert
    assert script.main([]) == 1


@pytest.mark.anyio
async def test_the_cli_refuses_to_run_without_a_database_url(
    script: ModuleType, env: None
) -> None:
    """`load_settings` allows a missing DSN (Compose supplies one); this cannot."""
    with pytest.raises(SeedError, match="DATABASE_URL"):
        await script.seed(offline(), pack())
