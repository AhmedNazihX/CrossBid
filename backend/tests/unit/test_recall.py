"""S3.2.3 — the matcher, the recall score, and the report a reviewer adjudicates.

Everything here is offline and synthetic: the quotes are short invented clauses, never the
fixture PDFs, because what is under test is the *rule* that decides two quotes describe one
obligation, not whether a particular German sentence is on page four.

The matcher is the part worth arguing about. Quote equality is too strict — the extractor
legitimately quotes a longer or a shorter span of the same clause — and document-and-page is
far too loose, since a page of a Bewerbungsbedingungen carries a dozen separate duties. So
the tests below pin both directions: which honest variations must still match, and which
plausible-looking coincidences must not.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from crossbid.eval.extraction import (
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
    dump_extraction,
    load_extraction,
)
from crossbid.eval.matching import (
    MIN_SHARED_CHARS,
    PAGE_WINDOW,
    match_all,
    quote_overlap,
)
from crossbid.eval.recall import (
    DisagreementField,
    exit_code_for,
    score_tender,
    scored_labels,
)
from crossbid.eval.report import (
    CANDIDATES_HEADING,
    CLOSING_S6_4,
    DISAGREEMENTS_HEADING,
    LEAKS_HEADING,
    MISSES_HEADING,
    NOTHING_SCORED,
    QUOTE_EXCERPT_CHARS,
    SYNTHETIC_WARNING,
    render,
)
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.golden import GoldenFile, GoldenMeta, GoldenRequirement, LabelSource
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)
from crossbid.settings import load_runtime_settings

DOC = "Besondere_Bewerbungsbedingungen_VV2_V1.pdf"
OTHER_DOC = "Kriterienkatalog_Eignung_VV2_V1.pdf"
FIXTURE_DIR = "tests/fixtures/tenders/de"

TURNOVER = "Der Bieter weist einen Jahresumsatz von mindestens 3.000.000 EUR nach."
STAFF = "Der Bieter beschäftigt im Jahresmittel mindestens 29 Vollzeitäquivalente."
CRITERION = CRITERION_IDS[0]
OTHER_CRITERION = CRITERION_IDS[1]

THRESHOLD = 0.9


# ------------------------------------------------------------------------------- builders


def label(
    quote: str = TURNOVER,
    *,
    identifier: str = "DE-001",
    page: int = 4,
    doc: str = DOC,
    kind: RequirementKind = RequirementKind.MANDATORY,
    stage: RequirementStage = RequirementStage.BID_ELIGIBILITY,
    criterion: str | None = None,
) -> GoldenRequirement:
    """One golden label, defaulting to a scored one: mandatory and bid-eligibility."""
    return GoldenRequirement(
        id=identifier,
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=kind,
        stage=stage,
        checkable=Checkability.COMPANY_PROPERTY,
        doc=doc,
        page=page,
        quote=quote,
        summary="Annual turnover of at least EUR 3,000,000",
        ecertis_criterion_id=criterion,  # type: ignore[arg-type]
    )


def extracted(
    source_text: str = TURNOVER,
    *,
    page: int = 4,
    doc: str = DOC,
    kind: RequirementKind = RequirementKind.MANDATORY,
    stage: RequirementStage = RequirementStage.BID_ELIGIBILITY,
    criterion: str | None = None,
) -> Requirement:
    """One row as `extract_reqs` writes it. The id is derived, so two builds agree."""
    return Requirement(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc}:{page}:{source_text}")),
        bid_id="bid-1",
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=kind,
        stage=stage,
        checkable=Checkability.COMPANY_PROPERTY,
        source_text=source_text,
        source_lang="de",
        document_name=doc,
        page=page,
        ecertis_criterion_id=criterion,  # type: ignore[arg-type]
    )


def golden(
    *entries: GoldenRequirement, conditional: tuple[GoldenRequirement, ...] = ()
) -> GoldenFile:
    return GoldenFile(
        meta=GoldenMeta(
            ted_publication_number="614251-2026",
            fixture_dir=FIXTURE_DIR,
            source_language="de",
            labelled_by=LabelSource.LLM_DRAFT,
            verified_by="pending",
            labelled_on=date(2026, 9, 11),
            story="S6.4",
            method="synthetic, for the tests",
            documents_scanned=(DOC, OTHER_DOC),
            documents_excluded={},
        ),
        requirements=entries,
        conditional_not_scored=conditional,
    )


def extraction(*rows: Requirement, source: ExtractionSource = ExtractionSource.LIVE_RUN):
    return ExtractionResult(
        meta=ExtractionMeta(
            fixture_dir=FIXTURE_DIR,
            source=source,
            produced_on=date(2026, 9, 12),
            method="synthetic, for the tests",
        ),
        requirements=rows,
    )


def matched_ids(file: GoldenFile, *rows: Requirement) -> set[str]:
    index = match_all(file.entries, rows)
    return {match.label.id for match in index.matches}


# -------------------------------------------------------------------------- the matcher


def test_an_identical_quote_on_the_cited_page_matches() -> None:
    # Arrange & Act & Assert
    assert matched_ids(golden(label()), extracted()) == {"DE-001"}


def test_a_longer_extracted_span_of_the_same_clause_matches() -> None:
    """The extractor is told to quote the obligation, not to guess where the label cut it."""
    # Arrange
    longer = f"Zum Nachweis der wirtschaftlichen Leistungsfähigkeit gilt: {TURNOVER}"

    # Act & Assert
    assert matched_ids(golden(label()), extracted(longer)) == {"DE-001"}


def test_a_shorter_extracted_span_of_the_same_clause_matches() -> None:
    # Arrange
    shorter = "einen Jahresumsatz von mindestens 3.000.000 EUR nach"

    # Act & Assert
    assert matched_ids(golden(label()), extracted(shorter)) == {"DE-001"}


def test_the_parsers_markdown_emphasis_does_not_stop_a_match() -> None:
    """`pymupdf4llm` returns `**3.000.000**` where the buyer wrote a bold number, and the
    two sides may disagree about whether the asterisks belong in the quote (CLAUDE.md)."""
    # Arrange
    emphasised = TURNOVER.replace("3.000.000", "**3.000.000**")

    # Act & Assert
    assert matched_ids(golden(label()), extracted(emphasised)) == {"DE-001"}


def test_line_breaks_inside_a_quote_do_not_stop_a_match() -> None:
    # Arrange
    wrapped = TURNOVER.replace(" ", "\n   ", 3)

    # Act & Assert
    assert matched_ids(golden(label()), extracted(wrapped)) == {"DE-001"}


def test_a_case_difference_does_not_stop_a_match() -> None:
    """Sameness is judged case-folded, exactly as `extract_reqs` dedupes. Storing a quote
    still preserves case; this comparison is not storage."""
    # Act & Assert
    assert matched_ids(golden(label()), extracted(TURNOVER.upper())) == {"DE-001"}


def test_a_clause_quoted_one_page_later_still_matches() -> None:
    """A clause broken by a page break is cited by whichever page each reader saw it start
    on, so one page of slack is honest."""
    # Act & Assert
    assert matched_ids(golden(label(page=4)), extracted(page=4 + PAGE_WINDOW)) == {"DE-001"}


def test_the_same_words_further_away_in_the_document_do_not_match() -> None:
    """A duty restated in a later annex is a second citation, not this label's evidence."""
    # Act & Assert
    assert matched_ids(golden(label(page=4)), extracted(page=4 + PAGE_WINDOW + 1)) == set()


def test_the_same_clause_quoted_from_another_document_does_not_match() -> None:
    """Page numbers of different files are not comparable, and `extract_reqs._dedupe` draws
    the same line: one obligation cited from two documents is two citations."""
    # Act & Assert
    assert matched_ids(golden(label(doc=DOC)), extracted(doc=OTHER_DOC)) == set()


def test_a_translation_of_the_clause_does_not_match() -> None:
    """Deliberate. A golden quote is verbatim source-language text by schema, and the only
    field compared is `source_text`; a match on the bidder-language `translation` would say
    the extractor found a clause it had merely paraphrased."""
    # Arrange
    english = "The bidder demonstrates an annual turnover of at least EUR 3,000,000."

    # Act & Assert
    assert matched_ids(golden(label()), extracted(english)) == set()


def test_a_short_shared_phrase_does_not_match() -> None:
    """The one false positive the rule is built to refuse: two different duties on one page
    that open with the same boilerplate."""
    # Arrange
    boilerplate = "Der Bieter weist"

    # Act & Assert
    assert len(boilerplate) < MIN_SHARED_CHARS
    assert matched_ids(golden(label()), extracted(boilerplate)) == set()


def test_two_different_duties_on_the_same_page_do_not_match_each_other() -> None:
    # Act & Assert
    assert matched_ids(golden(label(TURNOVER)), extracted(STAFF)) == set()


def test_an_empty_quote_never_matches() -> None:
    """`Requirement` puts no lower bound on `source_text`, so an empty one can arrive."""
    # Act & Assert
    assert matched_ids(golden(label()), extracted("")) == set()


def test_one_extracted_row_may_satisfy_several_labels() -> None:
    """A single quoted enumeration genuinely carries several obligations, and the question
    recall asks is whether extraction surfaced the text at all."""
    # Arrange
    enumeration = f"Mit dem Angebot einzureichen: {TURNOVER} {STAFF}"
    file = golden(label(TURNOVER, identifier="DE-001"), label(STAFF, identifier="DE-002"))

    # Act & Assert
    assert matched_ids(file, extracted(enumeration)) == {"DE-001", "DE-002"}


def test_a_label_is_credited_to_its_best_overlapping_row() -> None:
    """Several rows may quote one clause; only the closest is reported, so a reviewer reads
    one line per label rather than one per coincidence."""
    # Arrange
    exact = extracted(TURNOVER)
    loose = extracted(f"Vorbemerkung. {TURNOVER} Weitere Hinweise folgen in Anlage 3.")

    # Act
    index = match_all(golden(label()).entries, (loose, exact))

    # Assert
    assert [match.requirement.id for match in index.matches] == [exact.id]


def test_a_row_that_matched_a_label_is_not_reported_as_unexplained() -> None:
    # Arrange
    row = extracted()

    # Act
    index = match_all(golden(label()).entries, (row,))

    # Assert
    assert index.unmatched_requirements == ()


def test_a_row_that_matched_nothing_is_reported_as_unexplained() -> None:
    # Arrange
    row = extracted(STAFF)

    # Act
    index = match_all(golden(label(TURNOVER)).entries, (row,))

    # Assert
    assert index.unmatched_requirements == (row,)


def test_overlap_of_two_empty_quotes_is_zero_rather_than_undefined() -> None:
    # Act & Assert
    assert quote_overlap("", "").ratio == 0.0


# ---------------------------------------------------------------------------- the score


def test_only_bid_eligibility_labels_are_scored() -> None:
    """ADR-0015: 13 of the DE file's 143 scored rows are `contract_performance`, kept so the
    stage filter can be scored in both directions. Counting them would read recall low."""
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001"),
        label(STAFF, identifier="DE-002", stage=RequirementStage.CONTRACT_PERFORMANCE),
    )

    # Act & Assert
    assert [entry.id for entry in scored_labels(file)] == ["DE-001"]


def test_only_mandatory_labels_are_scored() -> None:
    """The story's number is recall on *mandatory* requirements."""
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001"),
        label(STAFF, identifier="DE-002", kind=RequirementKind.INFORMATIONAL),
    )

    # Act & Assert
    assert [entry.id for entry in scored_labels(file)] == ["DE-001"]


def test_conditional_entries_are_not_scored() -> None:
    """SP.1's scope decision: the base case is a single bidder submitting alone."""
    # Arrange
    file = golden(label(TURNOVER), conditional=(label(STAFF, identifier="DE-C01"),))

    # Act & Assert
    assert [entry.id for entry in scored_labels(file)] == ["DE-001"]


def test_recall_is_the_share_of_scored_labels_found() -> None:
    # Arrange
    file = golden(label(TURNOVER, identifier="DE-001"), label(STAFF, identifier="DE-002"))

    # Act
    score = score_tender(file, extraction(extracted(TURNOVER)), threshold=THRESHOLD)

    # Assert
    assert (score.recall, [entry.id for entry in score.missed]) == (0.5, ["DE-002"])


def test_a_score_at_the_threshold_passes() -> None:
    # Arrange
    file = golden(label(TURNOVER))

    # Act
    score = score_tender(file, extraction(extracted()), threshold=1.0)

    # Assert
    assert score.passes


def test_a_score_below_the_threshold_fails() -> None:
    # Arrange
    file = golden(label(TURNOVER), label(STAFF, identifier="DE-002"))

    # Act
    score = score_tender(file, extraction(extracted(TURNOVER)), threshold=THRESHOLD)

    # Assert
    assert not score.passes


def test_a_golden_file_with_nothing_to_score_is_refused() -> None:
    """A denominator of zero would print recall 1.00 and pass, which is worse than an error."""
    # Arrange
    file = golden(label(kind=RequirementKind.OPTIONAL))

    # Act & Assert
    with pytest.raises(ValueError, match="no mandatory"):
        score_tender(file, extraction(), threshold=THRESHOLD)


def test_an_unscored_label_still_absorbs_the_row_that_quotes_it() -> None:
    """Matching runs against every entry, scoring against the mandatory ones. Otherwise a
    row quoting an informational label would be offered to the reviewer as a missing one."""
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001"),
        label(STAFF, identifier="DE-002", kind=RequirementKind.INFORMATIONAL),
    )

    # Act
    score = score_tender(
        file, extraction(extracted(TURNOVER), extracted(STAFF)), threshold=THRESHOLD
    )

    # Assert
    assert (score.recall, score.candidates) == (1.0, ())


def test_a_row_no_label_explains_is_offered_as_a_candidate_missing_label() -> None:
    """The one failure a verbatim check is blind to: an obligation nobody labelled."""
    # Arrange
    orphan = extracted(STAFF)

    # Act
    score = score_tender(
        golden(label(TURNOVER)), extraction(extracted(TURNOVER), orphan), threshold=THRESHOLD
    )

    # Assert
    assert [row.id for row in score.candidates] == [orphan.id]


def test_a_matched_contract_performance_label_is_reported_as_a_stage_filter_leak() -> None:
    """The other direction of ADR-0015's test: `extract_reqs` must emit nothing at this
    stage, so a match here means the filter let a post-award duty through."""
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001"),
        label(STAFF, identifier="DE-002", stage=RequirementStage.CONTRACT_PERFORMANCE),
    )

    # Act
    score = score_tender(
        file, extraction(extracted(TURNOVER), extracted(STAFF)), threshold=THRESHOLD
    )

    # Assert
    assert [leak.label.id for leak in score.leaks] == ["DE-002"]
    assert score.disagreements == ()


def test_a_kind_disagreement_on_a_matched_pair_is_reported() -> None:
    # Act
    score = score_tender(
        golden(label(TURNOVER)),
        extraction(extracted(TURNOVER, kind=RequirementKind.OPTIONAL)),
        threshold=THRESHOLD,
    )

    # Assert
    assert [(d.field, d.label_value, d.extracted_value) for d in score.disagreements] == [
        (DisagreementField.KIND, "mandatory", "optional")
    ]


def test_a_criterion_disagreement_is_reported_in_both_directions() -> None:
    """A criterion the label has and the extractor missed, and one it invented, are both
    adjudications the reviewer owes an answer to: S3.3.1 fetches evidence for whichever
    id survives."""
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001", criterion=CRITERION),
        label(STAFF, identifier="DE-002"),
    )
    rows = (extracted(TURNOVER), extracted(STAFF, criterion=OTHER_CRITERION))

    # Act
    score = score_tender(file, extraction(*rows), threshold=THRESHOLD)

    # Assert
    assert [(d.label.id, d.label_value, d.extracted_value) for d in score.disagreements] == [
        ("DE-001", CRITERION, "none"),
        ("DE-002", "none", OTHER_CRITERION),
    ]


def test_an_agreeing_pair_produces_no_disagreement() -> None:
    # Act
    score = score_tender(
        golden(label(TURNOVER, criterion=CRITERION)),
        extraction(extracted(TURNOVER, criterion=CRITERION)),
        threshold=THRESHOLD,
    )

    # Assert
    assert score.disagreements == ()


def test_the_exit_code_is_zero_when_every_tender_clears_the_threshold() -> None:
    # Arrange
    score = score_tender(golden(label()), extraction(extracted()), threshold=THRESHOLD)

    # Act & Assert
    assert exit_code_for((score,)) == 0


def test_the_exit_code_is_non_zero_when_one_tender_is_below_the_threshold() -> None:
    # Arrange
    passing = score_tender(golden(label()), extraction(extracted()), threshold=THRESHOLD)
    failing = score_tender(
        golden(label(TURNOVER), label(STAFF, identifier="DE-002")),
        extraction(extracted(TURNOVER)),
        threshold=THRESHOLD,
    )

    # Act & Assert
    assert exit_code_for((passing, failing)) == 1


def test_no_score_at_all_is_a_failure() -> None:
    """`recall.py` with nothing to read must not report success."""
    # Act & Assert
    assert exit_code_for(()) == 1


# --------------------------------------------------------------------------- the report


def report_of(file: GoldenFile, result: ExtractionResult) -> str:
    return render((score_tender(file, result, threshold=THRESHOLD),))


def test_the_report_states_the_recall_and_the_threshold() -> None:
    # Act
    text = report_of(golden(label()), extraction(extracted()))

    # Assert
    assert "1.00" in text
    assert "0.90" in text


def test_the_report_lists_a_miss_with_its_document_page_and_quote() -> None:
    # Act
    text = report_of(golden(label(TURNOVER, page=7)), extraction())

    # Assert
    assert MISSES_HEADING in text
    assert f"{DOC} p.7" in text
    assert TURNOVER in text


def test_the_report_lists_a_candidate_missing_label() -> None:
    # Act
    text = report_of(golden(label(TURNOVER)), extraction(extracted(TURNOVER), extracted(STAFF)))

    # Assert
    assert CANDIDATES_HEADING in text
    assert STAFF in text


def test_the_report_lists_a_field_disagreement() -> None:
    # Act
    text = report_of(
        golden(label(TURNOVER)), extraction(extracted(TURNOVER, kind=RequirementKind.OPTIONAL))
    )

    # Assert
    assert DISAGREEMENTS_HEADING in text
    assert "mandatory" in text and "optional" in text


def test_the_report_lists_a_stage_filter_leak() -> None:
    # Arrange
    file = golden(
        label(TURNOVER, identifier="DE-001"),
        label(STAFF, identifier="DE-002", stage=RequirementStage.CONTRACT_PERFORMANCE),
    )

    # Act
    text = report_of(file, extraction(extracted(TURNOVER), extracted(STAFF)))

    # Assert
    assert LEAKS_HEADING in text
    assert "DE-002" in text


def test_a_clean_tender_prints_no_empty_sections() -> None:
    """A reviewer's list is only useful if what is on it needs adjudicating."""
    # Act
    text = report_of(golden(label()), extraction(extracted()))

    # Assert
    assert MISSES_HEADING not in text
    assert CANDIDATES_HEADING not in text
    assert LEAKS_HEADING not in text
    assert DISAGREEMENTS_HEADING not in text


def test_the_report_says_how_a_reviewer_closes_s6_4() -> None:
    """The report is the artefact the story hands the reviewer; the instruction goes on it,
    not only in a docstring they would have to know to open."""
    # Act
    text = report_of(golden(label()), extraction(extracted()))

    # Assert
    assert CLOSING_S6_4 in text
    assert "llm_assisted_human_verified" in text


def test_a_synthetic_extraction_is_marked_as_not_a_measurement() -> None:
    """The whole point of the provenance field: a number scored against a hand-built file
    must never be reported as a measured one."""
    # Act
    result = extraction(extracted(), source=ExtractionSource.SYNTHETIC)
    text = report_of(golden(label()), result)

    # Assert
    assert SYNTHETIC_WARNING in text


def test_a_live_extraction_carries_no_synthetic_warning() -> None:
    # Act
    text = report_of(golden(label()), extraction(extracted()))

    # Assert
    assert SYNTHETIC_WARNING not in text


def test_a_long_quote_is_excerpted_rather_than_printed_whole() -> None:
    """A 2000-character clause would bury the list it is an item of."""
    # Arrange
    long_quote = "Der Bieter erklärt hiermit verbindlich, " + ("dass er zuverlässig ist. " * 40)

    # Act
    text = report_of(golden(label(long_quote)), extraction())

    # Assert
    assert long_quote[:QUOTE_EXCERPT_CHARS] in text
    assert long_quote not in text


def test_nothing_scored_prints_a_sentence_rather_than_an_empty_report() -> None:
    # Act & Assert
    assert render(()) == NOTHING_SCORED


def test_the_report_names_every_tender_it_scored() -> None:
    # Arrange
    score = score_tender(golden(label()), extraction(extracted()), threshold=THRESHOLD)

    # Act
    text = render((score, score))

    # Assert
    assert text.count("614251-2026") == 2


# --------------------------------------------------------------- the extraction artefact


def test_a_saved_extraction_result_round_trips(tmp_path: Path) -> None:
    """The file the live bid run writes is the file the script reads; one shape, one loader."""
    # Arrange
    result = extraction(extracted())
    path = tmp_path / "de.json"

    # Act
    dump_extraction(result, path)

    # Assert
    assert load_extraction(path) == result


def test_a_saved_extraction_result_ends_in_one_newline(tmp_path: Path) -> None:
    """Committed as a fixture, so it is diffed like source."""
    # Arrange
    path = tmp_path / "de.json"

    # Act
    dump_extraction(extraction(extracted()), path)

    # Assert
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_the_golden_file_is_resolved_from_the_extractions_own_fixture_dir(
    tmp_path: Path,
) -> None:
    """The result says which tender it is, so the two paths cannot be paired up wrongly."""
    # Act
    resolved = extraction().golden_path(tmp_path)

    # Assert
    assert resolved == tmp_path / FIXTURE_DIR / "golden.yaml"


def test_the_fixture_name_is_the_last_segment_of_the_fixture_dir() -> None:
    # Act & Assert
    assert extraction().fixture_name == "de"


def test_an_unknown_field_in_an_extraction_file_is_refused(tmp_path: Path) -> None:
    """Same reasoning as the golden schema: a misspelled key must fail, not be dropped."""
    # Arrange
    path = tmp_path / "de.json"
    path.write_text('{"meta": {}, "requirements": [], "surprise": 1}', encoding="utf-8")

    # Act & Assert
    with pytest.raises(ValidationError):
        load_extraction(path)


# ------------------------------------------------------------------------- the threshold


def test_the_threshold_is_configuration_and_matches_the_plans_figure() -> None:
    """S3.2.1's criterion is 0.9 and R1 says the threshold lives in settings, so the number
    the script exits on is read from the committed YAML rather than written in a script."""
    # Act & Assert
    assert load_runtime_settings().evaluation.recall_threshold == THRESHOLD
