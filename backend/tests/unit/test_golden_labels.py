"""S6.4 — what makes a drafted answer key safe to commit.

The golden files are labelled with LLM assistance, so the interesting failure is not a typo
but a *plausible* fabrication: a quote the model composed out of the document's vocabulary
and attached to a page that never carried it. Nothing downstream would notice. S3.2.3 would
score extraction against the invention, recall would move, and the number the course is
graded on would be wrong in a direction nobody can see.

So every claim a golden entry makes is re-derived here from the PDF itself. The document must
exist in the pack, the page must be inside it, and the quote must literally occur on that
page — checked with `extract_reqs._is_verbatim`, the *same* predicate the extractor uses to
accept a model's citation, imported rather than re-implemented. That matters twice over: a
second definition would drift, and if it were stricter than the extractor's the golden file
could demand quotes the extractor is structurally unable to produce. Its normalisation is
whitespace-collapsed, markdown emphasis stripped, case preserved (CLAUDE.md records why the
plain substring check fails on honest quotes: `pymupdf4llm` returns `**Umsatz**` where the
buyer wrote `Umsatz`).

The pages are read through `PyMuPDFParser`, the repo's own default parser, for the same
reason: a page number is only meaningful relative to the reader that produced it, and this is
the reader S3.2.1 will run.

Each file is a separate parametrisation and a missing one is simply absent from the set, so
this suite runs green against the DE file alone while FR and EN are still being written.
"""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from crossbid.agent.nodes.extract_reqs import _is_verbatim
from crossbid.ingestion.parser import ParsedDocument
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.golden import (
    PENDING_VERIFIER,
    GoldenFile,
    GoldenMeta,
    GoldenRequirement,
    LabelSource,
    load_golden,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
TENDERS_DIR = BACKEND_DIR / "tests" / "fixtures" / "tenders"
GOLDEN_FILENAME = "golden.yaml"
FIXTURES = ("de", "fr", "en")


def _golden_paths() -> list[Path]:
    """The golden files that exist today, in fixture order."""
    candidates = (TENDERS_DIR / fixture / GOLDEN_FILENAME for fixture in FIXTURES)
    return [path for path in candidates if path.is_file()]


@cache
def _golden(path: Path) -> GoldenFile:
    return load_golden(path)


@cache
def _parsed(pdf: Path) -> ParsedDocument:
    """One parse per PDF for the whole module; a 21-page pack file is not cheap to read."""
    return PyMuPDFParser().parse(pdf, document_id=pdf.name)


def _pack_pdfs(path: Path) -> dict[str, Path]:
    """Every PDF of the fixture by filename: the pack, plus the notice one level up.

    The notice sits beside `documents/` rather than inside it because it came from TED and
    the rest came from the buyer's platform, but a bidder reads both, so both are in scope
    for labelling and both must be accounted for in the header.
    """
    fixture_dir = path.parent
    pdfs = sorted(fixture_dir.glob("documents/*.pdf")) + sorted(fixture_dir.glob("*.pdf"))
    return {pdf.name: pdf for pdf in pdfs}


def _entry_cases() -> list[pytest.ParameterSet]:
    """(golden file, entry) for every entry of every golden file that exists."""
    return [
        pytest.param(path, entry, id=f"{path.parent.name}-{entry.id}")
        for path in _golden_paths()
        for entry in _golden(path).entries
    ]


def _file_cases() -> list[pytest.ParameterSet]:
    return [pytest.param(path, id=path.parent.name) for path in _golden_paths()]


FILE_CASES = _file_cases()
ENTRY_CASES = _entry_cases()


# --------------------------------------------------------------------------- the header


@pytest.mark.parametrize("path", FILE_CASES)
def test_golden_file_parses_against_the_strict_schema(path: Path) -> None:
    golden = _golden(path)

    assert golden.entries
    assert golden.meta.fixture_dir.endswith(path.parent.name)


@pytest.mark.parametrize("path", FILE_CASES)
def test_pending_file_declares_itself_a_draft(path: Path) -> None:
    """The one claim a reader of the file cannot verify for themselves."""
    meta = _golden(path).meta

    if meta.verified_by == PENDING_VERIFIER:
        assert meta.labelled_by is LabelSource.LLM_DRAFT
        assert meta.verified_on is None


@pytest.mark.parametrize("path", FILE_CASES)
def test_ids_are_unique_across_the_whole_file(path: Path) -> None:
    """Scored and conditional entries share one id space; S3.2.3 keys reports on them."""
    ids = [entry.id for entry in _golden(path).entries]

    assert len(ids) == len(set(ids)), sorted({id_ for id_ in ids if ids.count(id_) > 1})


@pytest.mark.parametrize("path", FILE_CASES)
def test_every_pack_document_is_either_scanned_or_excluded(path: Path) -> None:
    """No document may be passed over in silence -- an unopened file lowers no score.

    An answer key is measured by what it contains, so an obligation the labeller never
    opened costs nothing and shows up nowhere. Partitioning the pack is the only check that
    can see that omission, which is why it is an assertion and not a convention.
    """
    meta = _golden(path).meta
    accounted = set(meta.documents_scanned) | set(meta.documents_excluded)

    assert accounted == set(_pack_pdfs(path))


@pytest.mark.parametrize("path", FILE_CASES)
def test_scanned_and_excluded_do_not_overlap(path: Path) -> None:
    meta = _golden(path).meta

    assert not set(meta.documents_scanned) & set(meta.documents_excluded)


@pytest.mark.parametrize("path", FILE_CASES)
def test_every_cited_document_was_declared_as_scanned(path: Path) -> None:
    """A requirement read out of a file the header calls excluded is a contradiction."""
    golden = _golden(path)
    scanned = set(golden.meta.documents_scanned)

    assert {entry.doc for entry in golden.entries} <= scanned


# --------------------------------------------------------------------------- the entries


@pytest.mark.parametrize(("path", "entry"), ENTRY_CASES)
def test_cited_document_exists_in_the_pack(path: Path, entry: GoldenRequirement) -> None:
    assert entry.doc in _pack_pdfs(path)


@pytest.mark.parametrize(("path", "entry"), ENTRY_CASES)
def test_cited_page_is_inside_the_document(path: Path, entry: GoldenRequirement) -> None:
    document = _parsed(_pack_pdfs(path)[entry.doc])

    assert entry.page <= document.page_count


@pytest.mark.parametrize(("path", "entry"), ENTRY_CASES)
def test_quote_appears_verbatim_on_the_cited_page(path: Path, entry: GoldenRequirement) -> None:
    """The check that makes an LLM-drafted label as trustworthy as a hand-written one."""
    document = _parsed(_pack_pdfs(path)[entry.doc])
    page = document.pages[entry.page - 1]

    assert _is_verbatim(entry.quote, page.text)


@pytest.mark.parametrize(("path", "entry"), ENTRY_CASES)
def test_ecertis_criterion_id_is_a_criterion_ecertis_knows(
    path: Path, entry: GoldenRequirement
) -> None:
    """Belt and braces over the `Literal`: a wrong id makes S3.3.1 fetch wrong evidence."""
    assert entry.ecertis_criterion_id is None or entry.ecertis_criterion_id in CRITERION_IDS


# ------------------------------------------------------------------ the schema's own rules


def _meta(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ted_publication_number": "614251-2026",
        "fixture_dir": "tests/fixtures/tenders/de",
        "source_language": "de",
        "labelled_by": LabelSource.LLM_DRAFT,
        "verified_by": PENDING_VERIFIER,
        "verified_on": None,
        "labelled_on": date(2026, 9, 11),
        "story": "S6.4",
        "method": "read the pack",
        "documents_scanned": ("AGB.pdf",),
        "documents_excluded": {},
    }
    return base | overrides


def test_a_pending_file_may_not_claim_human_verification() -> None:
    with pytest.raises(ValidationError, match="an unverified file is a draft"):
        GoldenMeta.model_validate(_meta(labelled_by=LabelSource.LLM_ASSISTED_HUMAN_VERIFIED))


def test_a_pending_file_may_not_carry_a_verification_date() -> None:
    with pytest.raises(ValidationError, match="verified_on is set"):
        GoldenMeta.model_validate(_meta(verified_on=date(2026, 9, 11)))


def test_a_verified_file_needs_no_draft_declaration() -> None:
    meta = GoldenMeta.model_validate(
        _meta(
            labelled_by=LabelSource.LLM_ASSISTED_HUMAN_VERIFIED,
            verified_by="Ahmed Nazih Ali",
            verified_on=date(2026, 9, 11),
        )
    )

    assert meta.verified_by != PENDING_VERIFIER


def test_an_unknown_field_is_refused(tmp_path: Path) -> None:
    """`extra='forbid'` is what turns a misspelled key into a failure rather than a silent
    loss -- a label whose `page:` was typed `pages:` would otherwise validate with page 1."""
    path = tmp_path / GOLDEN_FILENAME
    path.write_text("meta: {}\nrequirements: []\nsurprise: 1\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_golden(path)
