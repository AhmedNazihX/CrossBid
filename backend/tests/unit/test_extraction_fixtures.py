"""S3.2.3 — the generator behind the synthetic extraction fixtures, and what it guarantees.

`tests/unit/test_recall_script.py` already asserts the committed files are honest: every
quote really occurs on the page it cites, and `meta.source` says `synthetic` so the figure is
never read as a measurement. What it could not assert, until
`scripts/build_extraction_fixtures.py` existed, is that the files are **reproducible** — the
whole of audit finding H23. A fixture whose method is a paragraph somebody typed drifts from
what the file contains the moment the answer key moves, and that is precisely what happened:
a `meta.method` quoting 219 labels and 16 drops against a file of 177 and 11.

So the claim under test here is narrow and it is the one that rotted: **a fresh build equals
what is committed, and the description each file carries is counted off its own rows.**

Everything is offline; the generator is loaded by path, as `scripts/` is not a package.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType

import pytest

from crossbid.eval.extraction import ExtractionSource, load_extraction
from crossbid.eval.recall import scored_labels
from crossbid.ingestion.parser import DocumentSource, ParsedDocument
from crossbid.models.golden import load_golden
from tests.conftest import parsed_fixture_pdf

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "build_extraction_fixtures.py"
EXTRACTIONS_DIR = BACKEND_DIR / "tests" / "fixtures" / "extractions"
TENDERS_DIR = BACKEND_DIR / "tests" / "fixtures" / "tenders"

PACKS = ("de", "fr", "en")
PACK_CASES = [pytest.param(name, id=name) for name in PACKS]


class CachedParser:
    """`PyMuPDFParser` through the session-wide parse `tests/conftest` already holds.

    `parsed_fixture_pdf` *is* `PyMuPDFParser`, so nothing about what gets built changes — but
    the generator parses all three packs and `test_golden_labels` parses the same PDFs, and
    the DE pack is 191 pages. Reading it twice per `make test` cost forty seconds and proved
    nothing. Swapped in here rather than in the script: production has one caller and no
    reason to carry a seam for this.
    """

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        assert isinstance(source, Path), source
        return parsed_fixture_pdf(source)


@pytest.fixture(scope="module")
def generator() -> Iterator[ModuleType]:
    """`scripts/build_extraction_fixtures.py` as a module, imported by path."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("build_extraction_fixtures", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None, SCRIPT_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["build_extraction_fixtures"] = module
        spec.loader.exec_module(module)
        module.PyMuPDFParser = CachedParser
        yield module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop("build_extraction_fixtures", None)


@pytest.fixture(scope="module")
def built(generator: ModuleType) -> Mapping[str, str]:
    """One build, shared: parsing 200-odd fixture pages per test would be needless seconds."""
    return generator.build_all()


# ------------------------------------------------------------------- the reproducibility claim


@pytest.mark.parametrize("name", PACK_CASES)
def test_the_committed_fixture_is_what_a_fresh_build_produces(
    name: str, built: Mapping[str, str]
) -> None:
    """H23. The one property the missing generator made impossible to state."""
    committed = (EXTRACTIONS_DIR / f"{name}.json").read_text(encoding="utf-8")

    assert committed == built[f"{name}.json"]


def test_two_builds_agree(generator: ModuleType, built: Mapping[str, str]) -> None:
    """Nothing in the build may read the clock or a random source. `PRODUCED_ON` is stamped."""
    assert generator.build_all() == dict(built)


def test_check_mode_passes_on_the_committed_fixtures(generator: ModuleType) -> None:
    assert generator.main(["--check"]) == 0


def test_check_mode_reports_a_file_that_drifted(
    generator: ModuleType, built: Mapping[str, str]
) -> None:
    tampered = dict(built) | {"de.json": '{"not": "the committed bytes"}'}

    assert generator.stale_files(tampered) == ("de.json",)


# ------------------------------------------------ the description is counted, not typed


@pytest.mark.parametrize("name", PACK_CASES)
def test_the_method_states_the_denominator_the_scorer_actually_uses(name: str) -> None:
    """The half of H23 that was a wrong number: 219 printed where the key scored 177."""
    golden = load_golden(TENDERS_DIR / name / "golden.yaml")
    method = load_extraction(EXTRACTIONS_DIR / f"{name}.json").meta.method

    assert f"the {len(scored_labels(golden))} mandatory bid-eligibility labels" in method


@pytest.mark.parametrize("name", PACK_CASES)
def test_the_method_states_the_number_of_labels_the_file_really_drops(
    name: str, generator: ModuleType
) -> None:
    """The other half: 16 claimed where the file missed 11. Recall is the arbiter."""
    golden = load_golden(TENDERS_DIR / name / "golden.yaml")
    extraction = load_extraction(EXTRACTIONS_DIR / f"{name}.json")
    scored = scored_labels(golden)
    quoted = {entry.quote for entry in scored} & {
        row.source_text for row in extraction.requirements
    }
    dropped = len(scored) // generator.DROP_EVERY

    assert f"({dropped} dropped)" in extraction.meta.method
    assert len(quoted) <= len(scored) - dropped, "a dropped label must not be quoted back"


@pytest.mark.parametrize("name", PACK_CASES)
def test_the_method_names_the_script_that_can_rebuild_it(name: str) -> None:
    """A provenance note pointing at a file that does not exist is what H23 was."""
    method = load_extraction(EXTRACTIONS_DIR / f"{name}.json").meta.method

    assert "scripts/build_extraction_fixtures.py" in method
    assert SCRIPT_PATH.exists()


# ---------------------------------------------------------------------- the fixture's own shape


@pytest.mark.parametrize("name", PACK_CASES)
def test_a_built_fixture_declares_itself_synthetic(name: str) -> None:
    """The line that keeps `recall.py` from printing this figure as a measurement."""
    meta = load_extraction(EXTRACTIONS_DIR / f"{name}.json").meta

    assert meta.source is ExtractionSource.SYNTHETIC


@pytest.mark.parametrize("name", PACK_CASES)
def test_every_row_is_bound_to_the_one_synthetic_bid(name: str, generator: ModuleType) -> None:
    """Deterministic ids: a rebuild updates rows rather than doubling them."""
    rows = load_extraction(EXTRACTIONS_DIR / f"{name}.json").requirements

    assert {row.bid_id for row in rows} == {generator.bid_id_for(name)}
    assert len({row.id for row in rows}) == len(rows), "ids collide"


@pytest.mark.parametrize("name", PACK_CASES)
def test_the_reviewers_lists_are_not_all_empty(name: str) -> None:
    """The branches the offline run exists to reach: a miss, a candidate, a disagreement.

    Asserted on the shape of the file rather than on the report, so this stays a statement
    about the generator. `test_recall_script.py` reads the rendered report.
    """
    golden = load_golden(TENDERS_DIR / name / "golden.yaml")
    rows = load_extraction(EXTRACTIONS_DIR / f"{name}.json").requirements
    labelled_docs = {entry.doc for entry in golden.entries}

    assert any(row.document_name not in labelled_docs for row in rows), "nothing unexplained"
    assert any(row.stage is not golden.requirements[0].stage for row in rows) or any(
        row.stage.value == "contract_performance" for row in rows
    ), "the stage filter is only scored in one direction"


def test_a_build_refuses_a_quote_that_is_not_on_its_page(generator: ModuleType) -> None:
    """The check that stands between a synthetic fixture and a fabricated one."""
    # Arrange
    build = generator.build_pack("fr")
    pages = generator.pack_pages(TENDERS_DIR / "fr")
    invented = {"source_text": "Diese Zeile steht nirgendwo."}
    fabricated = build.rows[0].model_copy(update=invented)
    tampered = generator.PackBuild(
        name=build.name,
        rows=(fabricated, *build.rows[1:]),
        scored=build.scored,
        dropped=build.dropped,
        widened=build.widened,
        narrowed=build.narrowed,
        post_award=build.post_award,
        unexplained=build.unexplained,
        disagreements=build.disagreements,
    )

    # Act / Assert
    with pytest.raises(generator.BuildError, match="verbatim"):
        generator.verify(tampered, pages)


def test_a_build_refuses_a_row_citing_a_page_the_pack_does_not_have(
    generator: ModuleType,
) -> None:
    build = generator.build_pack("fr")
    pages = generator.pack_pages(TENDERS_DIR / "fr")
    off_the_end = build.rows[0].model_copy(update={"page": 9999})
    tampered = generator.PackBuild(
        name=build.name,
        rows=(off_the_end,),
        scored=build.scored,
        dropped=build.dropped,
        widened=build.widened,
        narrowed=build.narrowed,
        post_award=build.post_award,
        unexplained=build.unexplained,
        disagreements=build.disagreements,
    )

    with pytest.raises(generator.BuildError, match="has no page"):
        generator.verify(tampered, pages)


def test_a_pack_directory_with_no_pdfs_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(generator.BuildError, match="no PDFs"):
        generator.pack_pages(tmp_path)


# ------------------------------------------------------------------------------- the two edits


def test_widening_takes_real_text_from_both_sides(generator: ModuleType) -> None:
    page = "Vorbemerkung zum Verfahren. Der Bieter hat das Formular einzureichen. Ende."

    widened = generator.widen("Der Bieter hat das Formular einzureichen.", page)

    assert widened in page
    assert widened.startswith("Vorbemerkung")


def test_widening_a_quote_the_page_does_not_carry_changes_nothing(
    generator: ModuleType,
) -> None:
    """`verify` is what refuses this case, by id. Silently inventing text here would not."""
    assert generator.widen("nowhere", "a page about something else") == "nowhere"


def test_narrowing_leaves_a_short_quote_alone(generator: ModuleType) -> None:
    """Below `MIN_NARROWABLE` there is nothing to trim that the matcher would still credit."""
    short = "Der Bieter hat das Formular einzureichen."

    assert generator.narrow(short) == short


def test_narrowing_cuts_at_a_word_boundary(generator: ModuleType) -> None:
    quote = (
        "Der Bieter hat mit dem Angebot die vollständig ausgefüllte Eigenerklärung zur "
        "Eignung sowie sämtliche darin benannten Nachweise einzureichen."
    )

    narrowed = generator.narrow(quote)

    assert quote.startswith(narrowed)
    assert not narrowed.endswith(" ")
    assert " " in narrowed and len(narrowed) <= generator.NARROW_TO


# --------------------------------------------------------------------------------- the CLI


def test_writing_produces_exactly_what_is_committed(
    generator: ModuleType,
    built: Mapping[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The write path, aimed somewhere else.

    Deliberately **not** run against the real directory: a build that had drifted would then
    rewrite the committed files as a side effect of the test that is supposed to catch the
    drift, and the tree would come out dirty with nothing failing.
    """
    monkeypatch.setattr(generator, "EXTRACTIONS_DIR", tmp_path)

    assert generator.main([]) == 0
    assert {path.name: path.read_text(encoding="utf-8") for path in tmp_path.iterdir()} == dict(
        built
    )
    assert "wrote 3 files" in capsys.readouterr().out


def test_a_build_error_is_reported_and_exits_one(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse() -> dict[str, str]:
        raise generator.BuildError("the pack moved")

    monkeypatch.setattr(generator, "build_all", refuse)

    assert generator.main([]) == 1
    assert "build error: the pack moved" in capsys.readouterr().err


def test_check_mode_exits_one_and_names_the_stale_file(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(generator, "build_all", lambda: {"de.json": "{}"})

    assert generator.main(["--check"]) == 1
    assert "de.json" in capsys.readouterr().err


def test_the_committed_files_are_valid_json_with_no_problems(built: Mapping[str, str]) -> None:
    """A synthetic run reports no extraction problems: there was no model to have any."""
    for name in built:
        assert json.loads((EXTRACTIONS_DIR / name).read_text())["problems"] == []
