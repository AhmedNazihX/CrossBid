"""S7.1 — the citation check, and proof that it can fail.

A metric that cannot return anything but 1.00 is not evidence, it is a decoration (ADR-0063).
The extractor already drops a row whose quote is not verbatim on its page
(`NO_VERBATIM_QUOTE`), so a live run's faithfulness is expected to be perfect and the
interesting question is entirely whether this check would notice if it were not. Every
failure mode below is therefore driven by mutating a real row from a real pack: a word
changed, a page moved past the end of the file, a document renamed.

The score is deliberately not "how close was the quote". It is the share of rows whose quote
is on the page they cite, which is the promise the workspace makes when it turns a citation
into a link.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crossbid.eval.extraction import (
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
)
from crossbid.eval.faithfulness import (
    CitationVerdict,
    FaithfulnessScore,
    score_faithfulness,
)
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.models.requirement import Requirement, RequirementSource
from tests.conftest import requirement

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DE_PACK = FIXTURES / "tenders" / "de"

DOCUMENT = "Bewerbungsbedingungen.pdf"


def de_document() -> Path:
    """One real pack document, chosen because its first page carries ordinary prose."""
    return next((DE_PACK / "documents").glob("*.pdf"))


def quote_from(path: Path, page: int, *, words: int = 8) -> str:
    """A genuinely verbatim quote: the first words of a real parsed page."""
    parsed = PyMuPDFParser().parse(path.read_bytes(), document_id=path.name)
    return " ".join(parsed.pages[page - 1].text.split()[:words])


def extraction_of(*rows: Requirement) -> ExtractionResult:
    return ExtractionResult(
        meta=ExtractionMeta(
            fixture_dir="tests/fixtures/tenders/de",
            source=ExtractionSource.SYNTHETIC,
            produced_on="2026-09-16",  # type: ignore[arg-type]
            method="built by test_faithfulness.py to exercise the citation check",
        ),
        requirements=rows,
    )


def score_of(*rows: Requirement) -> FaithfulnessScore:
    return score_faithfulness(extraction_of(*rows), pack_dir=DE_PACK)


# ------------------------------------------------------------------------ the passing case


def test_a_quote_really_on_its_page_is_faithful() -> None:
    path = de_document()
    row = requirement(quote_from(path, 1), page=1, document_name=path.name)

    score = score_of(row)

    assert score.score == 1.0
    assert [check.verdict for check in score.checks] == [CitationVerdict.FAITHFUL]


# ------------------------------------------- the three ways a citation fails, each measured


def test_a_quote_that_is_not_on_the_page_is_caught() -> None:
    """The mutation that matters: one word changed in an otherwise real quote."""
    path = de_document()
    honest = quote_from(path, 1)
    tampered = honest.replace(honest.split()[-1], "Schokoladenfabrik")
    assert tampered != honest, "the mutation did not change the quote"

    score = score_of(requirement(tampered, page=1, document_name=path.name))

    assert score.score == 0.0
    assert score.failures[0].verdict is CitationVerdict.NOT_ON_PAGE


def test_a_page_past_the_end_of_the_document_is_caught() -> None:
    """An attribution defect, not an extraction one: the citation opens nothing."""
    path = de_document()

    score = score_of(requirement(quote_from(path, 1), page=9999, document_name=path.name))

    assert score.failures[0].verdict is CitationVerdict.NO_SUCH_PAGE


def test_a_document_the_pack_does_not_contain_is_caught() -> None:
    """The failure that looks most correct on screen: a plausible filename, no such file."""
    path = de_document()

    score = score_of(
        requirement(quote_from(path, 1), page=1, document_name="Vertragsbedingungen_v9.pdf")
    )

    assert score.failures[0].verdict is CitationVerdict.NO_SUCH_DOCUMENT


# ---------------------------------------------------- what is deliberately not in the score


def test_a_row_with_no_page_is_set_aside_rather_than_counted_as_a_pass() -> None:
    """The FR pack is 30 of 144 rows this way. Counting them faithful would have inflated
    the score by a fifth of the tender on evidence this metric never looked at."""
    path = de_document()
    espd = requirement(
        "Chiffre d'affaires annuel général",
        page=None,
        source=RequirementSource.ESPD_REQUEST,
        document_name="DUME_acheteur.xml",
    )

    score = score_of(requirement(quote_from(path, 1), page=1, document_name=path.name), espd)

    assert len(score.checks) == 1, "the unpaginated row must not be checked"
    assert score.unpaginated == (espd,)
    assert score.score == 1.0


def test_a_tender_with_nothing_checkable_scores_zero_and_not_one() -> None:
    """An empty numerator over an empty denominator is the most misleading 1.00 available."""
    espd = requirement(
        "Effectifs moyens annuels",
        page=None,
        source=RequirementSource.ESPD_REQUEST,
        document_name="DUME_acheteur.xml",
    )

    score = score_of(espd)

    assert score.checks == ()
    assert score.score == 0.0


# ------------------------------------------------------------------- against the real packs


@pytest.mark.parametrize("fixture", ["de", "fr", "en"])
def test_every_golden_label_quotes_the_page_it_cites(fixture: str) -> None:
    """The control for the metric above: the answer keys, scored by the same predicate.

    `test_golden_labels.py` already proves this row by row. Scoring it here as well is what
    makes the number in `REPORT.md` trustworthy — it shows the check returns 1.00 on text a
    human verified, so a 1.00 on extraction is the same statement and not a broken metric.
    """
    from crossbid.models.golden import load_golden

    golden = load_golden(FIXTURES / "tenders" / fixture / "golden.yaml")
    rows = tuple(
        requirement(entry.quote, page=entry.page, document_name=entry.doc)
        for entry in golden.requirements
        if entry.page is not None
    )
    score = score_faithfulness(extraction_of(*rows), pack_dir=FIXTURES / "tenders" / fixture)

    assert score.score == 1.0, [
        (check.verdict.value, check.requirement.document_name, check.requirement.page)
        for check in score.failures
    ][:5]


def test_a_document_that_will_not_parse_is_named_rather_than_scored(tmp_path: Path) -> None:
    """A pack where a file is corrupt must not report a silent 0.00 with no cause: the
    filename is carried out so the report can say *why* nothing was checkable."""
    documents = tmp_path / "documents"
    documents.mkdir(parents=True)
    broken = documents / "Bewerbungsbedingungen.pdf"
    broken.write_bytes(b"%PDF-1.7\nthis is not a readable PDF body\n")

    score = score_faithfulness(
        extraction_of(requirement("irgendein Zitat", page=1, document_name=broken.name)),
        pack_dir=tmp_path,
    )

    assert score.unreadable == (broken.name,)
    assert score.failures[0].verdict is CitationVerdict.NO_SUCH_DOCUMENT
    assert score.score == 0.0
