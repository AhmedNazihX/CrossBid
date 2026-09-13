"""`scripts/recall.py` end to end, and the honesty of the extraction fixtures it reads.

Two things are under test and they are not the same thing.

The **script** is a thin CLI: it resolves paths, reads the threshold out of the committed
YAML, prints the report and turns the scores into an exit code. The logic it calls lives in
`crossbid/eval/` and is tested there; what is asserted here is the wiring and the three exit
codes, because `make test` cannot see a script that imports nothing.

The **fixtures** are the interesting half. `tests/fixtures/extractions/*.json` are synthetic
— built from the golden labels so the script can run offline — and a synthetic fixture is
one careless edit away from being a fabrication. So the same guarantee the golden files carry
is asserted for them: every quote is really on the page it cites, checked with
`extract_reqs._is_verbatim`, the extractor's own predicate. A recall figure scored against
invented text would be meaningless in a way nothing else would notice, and `meta.source`
being `synthetic` is what keeps the figure from being read as a measurement at all.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

from crossbid.agent.nodes.extract_reqs import _is_verbatim
from crossbid.eval.extraction import ExtractionResult, ExtractionSource, load_extraction
from crossbid.eval.recall import scored_labels
from crossbid.eval.report import CLOSING_S6_4, NOTHING_SCORED
from crossbid.models.golden import load_golden
from crossbid.models.requirement import Requirement, RequirementKind
from tests.conftest import TENDERS_DIR, parsed_fixture_pdf, tender_pack_pdfs

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "recall.py"
EXTRACTIONS_DIR = BACKEND_DIR / "tests" / "fixtures" / "extractions"

DE_MANDATORY_LABELS = 211
DE_DENOMINATOR = 177
"""253/219 until 2026-09-13, when the user ruled the `Kriterienkatalog Leistung` criteria are
scored rather than pass/fail: 35 of them became `optional` and left the scored set. The 11
A-Kriterien in the same catalogue stayed `mandatory` — an offer below their point thresholds is
excluded, so they are pass/fail despite being expressed in points. Recall fell 0.77 -> 0.73.

Then 184 -> 178 on 2026-09-13, when the §4 spot-check found six labels quoting the *recitation
of the law* rather than a duty on the bidder — the offences listed inside one exclusion ground,
and the sub-clause on how the buyer may prove it. Then 178 -> 177 for DE-228, the
notice's eForms "Quellen der Eignungskriterien" field, which points at the procurement
documents rather than stating a requirement of its own. The bidder's duty in those cases is
the Eigenerklärung, labelled separately; counting the statute too made one obligation look
like several.

These numbers are pinned so the denominator may only move on a recorded decision."""
"""The DE answer key's mandatory labels, and the ones the extractor can actually produce.

Pinned because the gap between them is the whole point of ADR-0015: 34 of the mandatory
labels are `contract_performance`, which `extract_reqs` filters out before anything leaves
the node. Score against 253 and recall is permanently 34 rows low, with nothing in the
output to say so. This is the assertion that makes dropping the stage filter fail loudly.

The two figures grew on 2026-09-12 (from 116/105) when the 173 candidate missing labels the
live run produced were adjudicated into the key and the independent sweep added what neither
the key nor the extraction had; the social-sustainability catalogue is most of the widened
gap between them.
"""

EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_BAD_INPUT = 2


@pytest.fixture(scope="module")
def recall() -> Iterator[ModuleType]:
    """The script as a module, loaded by path as `test_seed_dev_company` does."""
    spec = importlib.util.spec_from_file_location("recall_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, SCRIPT_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["recall_script"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("recall_script", None)


def shipped_paths() -> list[Path]:
    return sorted(EXTRACTIONS_DIR.glob("*.json"))


@cache
def shipped(path: Path) -> ExtractionResult:
    return load_extraction(path)


def row_cases() -> list[pytest.ParameterSet]:
    return [
        pytest.param(path, row, id=f"{path.stem}-{index}")
        for path in shipped_paths()
        for index, row in enumerate(shipped(path).requirements)
    ]


def synthetic_paths() -> list[Path]:
    """The hand-built fixtures. A live result is a different artefact — see below."""
    return [
        path
        for path in shipped_paths()
        if shipped(path).meta.source is ExtractionSource.SYNTHETIC
    ]


def live_paths() -> list[Path]:
    return [
        path
        for path in shipped_paths()
        if shipped(path).meta.source is not ExtractionSource.SYNTHETIC
    ]


FILE_CASES = [pytest.param(path, id=path.stem) for path in shipped_paths()]
SYNTHETIC_CASES = [pytest.param(path, id=path.stem) for path in synthetic_paths()]
ROW_CASES = row_cases()


# ------------------------------------------------------------------------- the fixtures


def test_some_extraction_results_are_shipped() -> None:
    """Guards every parametrisation below from passing by being empty."""
    # Act & Assert
    assert shipped_paths()


@pytest.mark.parametrize("path", SYNTHETIC_CASES)
def test_a_synthetic_result_declares_itself_synthetic(path: Path) -> None:
    """A hand-built fixture must say so, because its recall figure measures nothing."""
    # Act & Assert
    assert shipped(path).meta.source is ExtractionSource.SYNTHETIC


def test_every_shipped_result_declares_where_it_came_from() -> None:
    """The distinction that matters is that it is *declared*, not that it is synthetic.

    This assertion used to read "every shipped result is synthetic", which was true until a
    real one was committed (`de.live.json`, 2026-09-12) and then became a rule that would
    have had to be deleted to keep the evidence. A live result is a different artefact: it is
    the measurement S3.2.1 is graded on, and it is allowed to be **red** — recall was 0.75
    against a 0.90 threshold on the day it was taken. What must never happen is a result whose
    provenance is unstated, so that is what is pinned."""
    # Act & Assert
    assert shipped_paths()
    for path in shipped_paths():
        assert shipped(path).meta.source in set(ExtractionSource)


@pytest.mark.parametrize("path", FILE_CASES)
def test_a_shipped_result_names_a_tender_with_an_answer_key(path: Path) -> None:
    # Act & Assert
    assert shipped(path).golden_path(BACKEND_DIR).is_file()


@pytest.mark.parametrize(("path", "row"), ROW_CASES)
def test_a_shipped_row_quotes_the_page_it_cites(path: Path, row: Requirement) -> None:
    """The one check that separates a synthetic fixture from a fabricated one."""
    # Arrange
    fixture_dir = BACKEND_DIR / shipped(path).meta.fixture_dir
    document = parsed_fixture_pdf(tender_pack_pdfs(fixture_dir)[row.document_name])

    # Act & Assert
    assert row.page <= document.page_count
    assert _is_verbatim(row.source_text, document.pages[row.page - 1].text)


# ---------------------------------------------------------------------------- the script


def test_help_describes_the_entry_point(recall: ModuleType) -> None:
    """`uv run scripts/recall.py --help` is what the plan's acceptance list points at."""
    # Act & Assert
    with pytest.raises(SystemExit) as exit_info:
        recall.main(["--help"])
    assert exit_info.value.code == EXIT_OK


@pytest.mark.parametrize("path", SYNTHETIC_CASES)
def test_it_scores_a_synthetic_result_and_reports_success(
    path: Path, recall: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The synthetic fixtures are built to clear the threshold, so scoring one exits 0."""
    # Act
    code = recall.main([str(path)])

    # Assert
    printed = capsys.readouterr().out
    assert code == EXIT_OK
    assert CLOSING_S6_4 in printed
    golden = load_golden(shipped(path).golden_path(BACKEND_DIR))
    assert golden.meta.ted_publication_number in printed


def test_scoring_the_live_result_fails_because_recall_is_below_the_threshold(
    recall: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The measurement is red, and the script's whole job is to say so out loud.

    Pinned deliberately rather than exempted. `de.live.json` is the real DE run of
    2026-09-12 and it scores under `evaluation.recall_threshold`; a green suite here would
    mean the exit code had stopped meaning anything. When extraction improves enough to pass,
    this test fails and is the reminder to record that in an ADR."""
    # Arrange
    live = live_paths()
    if not live:  # pragma: no cover - there is one today; this keeps the intent readable
        pytest.skip("no live result is shipped")

    # Act
    code = recall.main([str(live[0])])

    # Assert
    assert code == EXIT_BELOW_THRESHOLD
    assert CLOSING_S6_4 in capsys.readouterr().out


def test_a_named_result_is_scored_on_its_own(
    recall: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    one = shipped_paths()[0]

    # Act
    code = recall.main([str(one)])

    # Assert -- one headline, so the other shipped fixtures were not scored too
    headlines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("  recall ")
    ]
    assert code == EXIT_OK
    assert len(headlines) == 1


def test_recall_below_the_settings_threshold_exits_non_zero(
    recall: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E3's done-when, mechanised: an extraction that finds almost nothing fails the run."""
    # Arrange
    full = json.loads(shipped_paths()[0].read_text(encoding="utf-8"))
    thin = tmp_path / "thin.json"
    thin.write_text(
        json.dumps({**full, "requirements": full["requirements"][:1]}), encoding="utf-8"
    )

    # Act
    code = recall.main([str(thin)])

    # Assert
    assert code == EXIT_BELOW_THRESHOLD
    assert "FAIL" in capsys.readouterr().out


def test_a_missing_result_file_is_an_input_error(
    recall: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Distinct from a failing threshold: nothing was scored, so nothing is claimed."""
    # Act
    code = recall.main([str(tmp_path / "absent.json")])

    # Assert
    assert code == EXIT_BAD_INPUT
    assert "cannot score" in capsys.readouterr().err


def test_a_malformed_result_file_is_an_input_error(recall: ModuleType, tmp_path: Path) -> None:
    # Arrange
    broken = tmp_path / "broken.json"
    broken.write_text('{"meta": {}, "requirements": []}', encoding="utf-8")

    # Act & Assert
    assert recall.main([str(broken)]) == EXIT_BAD_INPUT


def test_reading_no_results_at_all_is_not_a_pass(
    recall: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty directory must not print a green exit code: nothing was demonstrated."""
    # Arrange
    monkeypatch.setattr(recall, "DEFAULT_EXTRACTIONS_DIR", tmp_path)

    # Act
    code = recall.main([])

    # Assert
    assert code == EXIT_BELOW_THRESHOLD
    assert NOTHING_SCORED in capsys.readouterr().out


def test_the_de_denominator_leaves_out_its_deliberate_post_award_labels() -> None:
    """ADR-0015's filter, scored on the real answer key rather than a synthetic one."""
    # Arrange
    golden = load_golden(TENDERS_DIR / "de" / "golden.yaml")

    # Act
    denominator = scored_labels(golden)

    # Assert
    mandatory = [e for e in golden.requirements if e.kind is RequirementKind.MANDATORY]
    assert len(mandatory) == DE_MANDATORY_LABELS
    assert len(denominator) == DE_DENOMINATOR
