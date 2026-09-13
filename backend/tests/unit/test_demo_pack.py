"""S2.4.3 — the demo company's identity and the pack on disk, read offline.

Two things are proved here and nowhere else.

**The ids may never move.** `DEMO_COMPANY_ID` is pasted into developers' `.env` files as
`NEXT_PUBLIC_DEV_COMPANY_ID`, which the web app reads at *build* time, and it is derived twice
— in `crossbid/demo/company.py` and in `scripts/seed_dev_company.py`, which imports nothing
from `crossbid` on purpose. So the literal is pinned here and the script is loaded by path to
check that the two agree. A well-meant edit to either namespace fails a test instead of
orphaning every checkout.

**The committed pack is loadable.** `load_pack` is what stands between S6.3's generator and a
seed run, so its refusals are asserted one by one against temporary directories: a missing
profile, a profile that is not a profile, no documents, an empty file. Every one of them has
to fail *before* the seed writes a company row, not halfway through ten uploads.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from crossbid.demo.company import (
    DEMO_COMPANY_ID,
    DEMO_OWNER_USER_ID,
    DOCUMENT_NAME_PREFIX,
    PACK_DIR,
    SEED_NAMESPACE,
    PackError,
    document_id,
    load_documents,
    load_pack,
    load_profile,
)
from crossbid.models import LegalForm

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
DEV_SEED_PATH = SCRIPTS_DIR / "seed_dev_company.py"

EXPECTED_DEV_COMPANY_ID = uuid.UUID("91d42546-c9ba-5815-bbb7-8831a728271d")
"""The literal in `.env` files everywhere. `test_seed_dev_company.py` pins the same one."""

EXPECTED_DOCUMENT_COUNT = 10
"""S6.3 renders ten PDFs. Asserted here rather than enforced by `load_pack`: a run-time count
check would refuse an eleventh document somebody deliberately added, while a test says the
committed pack changed and asks whether that was meant."""

PDF_MAGIC = b"%PDF-"


@pytest.fixture(scope="module")
def dev_seed() -> Iterator[ModuleType]:
    """`scripts/seed_dev_company.py` as a module, loaded the way its own test loads it."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("seed_dev_company", DEV_SEED_PATH)
        assert spec is not None and spec.loader is not None, DEV_SEED_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["seed_dev_company"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop("seed_dev_company", None)


# ------------------------------------------------------------------------------- identity


def test_the_demo_company_id_is_the_one_already_in_everybodys_env_file() -> None:
    """Change this and `NEXT_PUBLIC_DEV_COMPANY_ID` names a tenant that does not exist."""
    assert DEMO_COMPANY_ID == EXPECTED_DEV_COMPANY_ID
    assert DEMO_COMPANY_ID.version == 5


def test_the_two_seeds_derive_the_same_company_and_owner(dev_seed: ModuleType) -> None:
    """The older script cannot import this module, so the derivation is written twice."""
    assert dev_seed.SEED_NAMESPACE == SEED_NAMESPACE
    assert dev_seed.DEV_COMPANY_ID == DEMO_COMPANY_ID
    assert dev_seed.DEV_OWNER_USER_ID == DEMO_OWNER_USER_ID


def test_the_owner_is_deterministic_and_is_not_the_company() -> None:
    """`companies_owner_user_id_key` is unique, so the owner id has to be stable too."""
    assert DEMO_OWNER_USER_ID.version == 5
    assert DEMO_OWNER_USER_ID != DEMO_COMPANY_ID


def test_a_document_id_is_the_same_in_every_database() -> None:
    """The whole idempotence mechanism: the id is a function of the filename."""
    assert document_id("Handelsregisterauszug.pdf") == document_id("Handelsregisterauszug.pdf")
    assert document_id("a.pdf") != document_id("b.pdf")
    assert document_id("a.pdf").version == 5


def test_a_document_id_can_never_collide_with_the_company_or_its_owner() -> None:
    """The prefix is what keeps the three derivations in disjoint name spaces."""
    assert DOCUMENT_NAME_PREFIX not in ("dev-company", "dev-company-owner")
    assert document_id("dev-company") not in (DEMO_COMPANY_ID, DEMO_OWNER_USER_ID)


# --------------------------------------------------------------------- the committed pack


def test_the_committed_pack_loads_as_the_demo_gmbh() -> None:
    # Act
    pack = load_pack()

    # Assert
    assert pack.profile.name == "Beispiel IT Services GmbH"
    assert pack.profile.legal_form is LegalForm.GMBH
    assert pack.profile.country == "de"
    assert len(pack.documents) == EXPECTED_DOCUMENT_COUNT


def test_every_document_is_a_readable_pdf_under_its_own_id() -> None:
    """What the seed hands to Storage and the parser, checked before either is involved."""
    # Act
    documents = load_pack().documents

    # Assert
    assert [document.filename for document in documents] == sorted(
        document.filename for document in documents
    )
    for document in documents:
        assert document.content.startswith(PDF_MAGIC), document.filename
        assert document.document_id == document_id(document.filename)
    assert len({document.document_id for document in documents}) == len(documents)


def test_the_pack_directory_is_the_one_s6_3_writes() -> None:
    """One path, written once: `build_demo_company_pack.py` renders into exactly this."""
    assert PACK_DIR == BACKEND_DIR / "tests" / "fixtures" / "company"
    assert (PACK_DIR / "profile.yaml").is_file()


# ------------------------------------------------------------------------------- refusals


def test_a_missing_profile_names_the_command_that_rebuilds_it(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="make demo-pack"):
        load_profile(tmp_path / "profile.yaml")


def test_a_profile_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text("name: [unclosed\n", encoding="utf-8")

    with pytest.raises(PackError, match="not valid YAML"):
        load_profile(path)


def test_a_profile_the_model_refuses_is_refused_here(tmp_path: Path) -> None:
    """The seeded tenant has to be the company the documents were rendered from."""
    path = tmp_path / "profile.yaml"
    path.write_text("name: Nur ein Name\n", encoding="utf-8")

    with pytest.raises(PackError, match="does not describe a company profile"):
        load_profile(path)


def test_a_missing_documents_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="no PDF found"):
        load_documents(tmp_path / "documents")


def test_a_documents_directory_with_no_pdf_is_refused(tmp_path: Path) -> None:
    """An empty pack would seed a company with nothing for the agent to retrieve."""
    directory = tmp_path / "documents"
    directory.mkdir()
    (directory / "README.md").write_text("not a document", encoding="utf-8")

    with pytest.raises(PackError, match="no PDF found"):
        load_documents(directory)


def test_an_empty_pdf_is_refused_before_it_reaches_storage(tmp_path: Path) -> None:
    """`CompanyDocumentStore.upload` refuses empty content; failing here says why."""
    directory = tmp_path / "documents"
    directory.mkdir()
    (directory / "leer.pdf").write_bytes(b"")

    with pytest.raises(PackError, match="is empty"):
        load_documents(directory)


def test_an_unreadable_document_names_the_file_and_not_the_traceback(tmp_path: Path) -> None:
    """A directory ending in `.pdf` is the cheap way to make `read_bytes` fail like an I/O
    error would; what matters is that the refusal names the file and stops the run."""
    directory = tmp_path / "documents"
    directory.mkdir()
    (directory / "kaputt.pdf").mkdir()

    with pytest.raises(PackError, match=r"cannot read kaputt\.pdf"):
        load_documents(directory)


def test_load_pack_reads_the_profile_and_the_documents_of_one_directory(
    tmp_path: Path,
) -> None:
    """The two halves come from one place, so a half-rebuilt pack cannot be seeded."""
    # Arrange
    (tmp_path / "profile.yaml").write_text(
        "name: Testfirma GmbH\ncountry: de\nlegal_form: gmbh\n", encoding="utf-8"
    )
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "eins.pdf").write_bytes(PDF_MAGIC + b"1")

    # Act
    pack = load_pack(tmp_path)

    # Assert
    assert pack.profile.name == "Testfirma GmbH"
    assert [document.filename for document in pack.documents] == ["eins.pdf"]
