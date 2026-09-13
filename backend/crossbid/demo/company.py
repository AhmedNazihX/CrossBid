"""Who the demo GmbH is, and the evidence pack it owns. S2.4.3, reading S6.3's output.

The walkthrough needs one bidder that exists in every environment: the fictional Beispiel IT
Services GmbH of `tests/fixtures/company/`. `scripts/build_demo_company_pack.py` (S6.3)
*renders* that pack — ten German PDFs from `profile.yaml` and `documents.yaml`, byte-identical
on every rebuild. This module *reads* it, and is the one place that says which company id,
which owner and which document ids those files land under.

**The pack lives under `tests/fixtures/` and is not a test fixture.** It is generated,
committed and shipped, and S6.3 put it there when its only consumer was the suite. Moving it
is a rename nobody needs; `PACK_DIR` is the one place that path is written, and `load_pack`
takes a directory so nothing is pinned to it.

**Every id is a `uuid5`, and that is the whole idempotence mechanism.** A second seed must not
create a second copy of anything, and deriving a document's id from its filename is the
cheapest way to recognise one that is already seeded: a single `select` answers before a byte
is uploaded and before an embedding is paid for. The alternatives are worse — probing Storage
for the object key costs a network round trip per document and still cannot tell a
half-finished upload from a complete one, and matching on `name` makes the seed's notion of
identity differ from the database's primary key.

**`DEMO_COMPANY_ID` must never change.** It is already pasted into developers' `.env` files as
`NEXT_PUBLIC_DEV_COMPANY_ID`, which the web app reads at *build* time, so rotating it orphans
every checkout. The derivation is written twice — here and in `scripts/seed_dev_company.py`,
which deliberately imports nothing from `crossbid` so it can run before the package is
importable — and `tests/unit/test_demo_pack.py` pins both against the literal UUID, so a
well-meant edit to either namespace fails a test instead of breaking a build.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from crossbid.models import CompanyProfile

BACKEND_DIR: Final = Path(__file__).resolve().parents[2]
PACK_DIR: Final = BACKEND_DIR / "tests" / "fixtures" / "company"
DOCUMENTS_DIR_NAME: Final = "documents"
PROFILE_FILE_NAME: Final = "profile.yaml"
PDF_GLOB: Final = "*.pdf"

SEED_NAMESPACE: Final = uuid.UUID("7f0b7d0e-4e6a-5a6c-9e1a-2c3d4e5f6a7b")
"""The namespace `scripts/seed_dev_company.py` fixed, restated so both derive the same ids."""

DEMO_COMPANY_NAME: Final = "dev-company"
DEMO_OWNER_NAME: Final = "dev-company-owner"
DOCUMENT_NAME_PREFIX: Final = "demo-document:"
"""Prefixed so a document id can never collide with the company's or the owner's."""

DEMO_COMPANY_ID: Final = uuid.uuid5(SEED_NAMESPACE, DEMO_COMPANY_NAME)
DEMO_OWNER_USER_ID: Final = uuid.uuid5(SEED_NAMESPACE, DEMO_OWNER_NAME)


class PackError(RuntimeError):
    """The pack on disk cannot be read as the demo company. Never carries file contents."""


def document_id(filename: str) -> uuid.UUID:
    """The id this document always has, in every database. See the module docstring."""
    return uuid.uuid5(SEED_NAMESPACE, f"{DOCUMENT_NAME_PREFIX}{filename}")


@dataclass(frozen=True, slots=True)
class PackDocument:
    """One PDF of the pack: what it is called, what it is, and the id it is seeded under."""

    filename: str
    document_id: uuid.UUID
    content: bytes


@dataclass(frozen=True, slots=True)
class DemoPack:
    """Everything the seed writes: the bidder's facts and the papers that evidence them."""

    profile: CompanyProfile
    documents: tuple[PackDocument, ...]


def load_pack(directory: Path = PACK_DIR) -> DemoPack:
    """Read `profile.yaml` and every PDF beside it, or say what is missing.

    Validation is strict and happens before anything is written: the profile has to parse
    into `CompanyProfile` (the same model `PUT /companies/me` accepts) and there has to be at
    least one readable document. A pack that is half there would otherwise be discovered
    document by document, after the company row was already created.
    """
    return DemoPack(
        profile=load_profile(directory / PROFILE_FILE_NAME),
        documents=load_documents(directory / DOCUMENTS_DIR_NAME),
    )


def load_profile(path: Path) -> CompanyProfile:
    """`profile.yaml` as the profile the form would have saved."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PackError(
            f"cannot read the demo company profile at {path}: {error}. The pack is "
            "generated and committed; rebuild it with `make demo-pack`."
        ) from error
    except yaml.YAMLError as error:
        raise PackError(f"{path} is not valid YAML: {error}") from error

    try:
        return CompanyProfile.model_validate(raw)
    except ValueError as error:
        raise PackError(
            f"{path} does not describe a company profile: {error}. It has to parse into "
            "the same CompanyProfile the form saves, or the seeded tenant is not the one "
            "the documents were rendered from."
        ) from error


def load_documents(directory: Path) -> tuple[PackDocument, ...]:
    """Every PDF in `directory`, in filename order, each with the id it is seeded under."""
    paths = sorted(directory.glob(PDF_GLOB)) if directory.is_dir() else []
    if not paths:
        raise PackError(
            f"no PDF found in {directory}, so there is no evidence to seed. Build the pack "
            "with `make demo-pack`."
        )
    return tuple(_document(path) for path in paths)


def _document(path: Path) -> PackDocument:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise PackError(f"cannot read {path.name}: {error}") from error
    if not content:
        raise PackError(
            f"{path.name} is empty, so it would fail the moment it reached Storage. "
            "Rebuild the pack with `make demo-pack`."
        )
    return PackDocument(filename=path.name, document_id=document_id(path.name), content=content)
