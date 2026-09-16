"""S3.2.3 — build the synthetic extraction fixtures `scripts/recall.py` is exercised against.

    uv run python scripts/build_extraction_fixtures.py           # render and write
    uv run python scripts/build_extraction_fixtures.py --check   # verify only, write nothing

`tests/fixtures/extractions/{de,fr,en}.json` are **not** extractions. They are built here from
the committed answer keys so that the recall script, its report and its exit codes can be run
end to end with no model, no key and no money. The figure they yield is a property of this
script; it measures nothing about the extractor, and `meta.source` is `synthetic` so that
`recall.py` prints that in capitals above the number.

**Why this script exists at all** (audit finding H23). These three files used to carry a
`meta.method` describing a generator that had never been committed, quoting counts that had
since moved — 219 where the denominator is 177, 16 dropped labels where the file missed 11.
The one artefact in the repository whose entire value is honest provenance could not be
reproduced and misstated its own method. Everything else generated here — the demo pack, the
adversarial pack, the eCertis cache, the question sets — is regenerable and has a test that
rebuilds it and compares. Now so is this.

**`meta.method` is written from the build, never typed.** Every number in it is counted off
the rows this run actually produced, so the description cannot go stale again the way it did:
the only way to change it is to change the code that produces it.

## What the fixture is made of, and why each part is there

The base is `eval.recall.scored_labels` — the recall denominator itself, imported rather than
re-derived, so the generator and the scorer cannot disagree about what counts. Every one of
those labels becomes a row, except:

* **every `DROP_EVERY`-th one, which is dropped.** Without this recall is trivially 1.00 and
  the miss report is never rendered, so the branch a reviewer most needs to read would be the
  one branch the offline run never reaches.
* **every `WIDEN_EVERY`-th kept row, whose quote is widened** to neighbouring text on the real
  page, and **every `NARROW_EVERY`-th, whose quote is trimmed**. `eval/matching.py` credits a
  row whose quote shares an unbroken run of at least `MIN_SHARED_CHARS` covering
  `MIN_SHARED_SPAN` of the shorter of the two, and a fixture quoting every label back
  byte-for-byte would exercise none of that tolerance. Both edits stay inside it on purpose:
  what is under test here is the script, not the matcher's limits, which
  `tests/unit/test_matching.py` owns.

On top of the base, three deliberate imperfections, because a fixture that only ever produces
clean output leaves the reviewer's lists permanently empty:

* one **`contract_performance` row**, so ADR-0015's stage filter is scored in both directions
  rather than only in the direction that passes;
* `UNEXPLAINED_ROWS` sentences taken from a document the key does not label, so the
  candidate-missing-label list has something in it;
* `DISAGREEMENT_ROWS` rows with one judgement field changed, so the disagreement list does.

**Every quote is a real span of the parsed page it cites**, widened and narrowed ones
included, and the build refuses rather than writes if one is not: `_is_verbatim` is the
extractor's own predicate, and `tests/unit/test_recall_script.py` asserts the same property
against the committed files from the other side. A synthetic fixture is one careless edit away
from being a fabrication, and that is the check that stands between the two.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Final

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:  # pragma: no cover -- import bootstrap
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.agent.nodes.extract_reqs import (  # noqa: E402
    REQUIREMENT_ID_NAMESPACE,
    _comparable,
    _is_verbatim,
)
from crossbid.eval.extraction import (  # noqa: E402
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
)
from crossbid.eval.recall import scored_labels  # noqa: E402
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser  # noqa: E402
from crossbid.models.golden import GoldenFile, GoldenRequirement, load_golden  # noqa: E402
from crossbid.models.requirement import (  # noqa: E402
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)

TENDERS_DIR: Final = BACKEND_DIR / "tests" / "fixtures" / "tenders"
EXTRACTIONS_DIR: Final = BACKEND_DIR / "tests" / "fixtures" / "extractions"
PACKS: Final = ("de", "fr", "en")

BID_ID_NAMESPACE: Final = uuid.UUID("2f3c5f4e-9a10-4f2b-8c77-1de5b0a6c4f1")
"""Namespace for each pack's synthetic `bid_id`. Fixed so two builds agree; distinct from
`REQUIREMENT_ID_NAMESPACE` so a bid id can never collide with a requirement id."""

PRODUCED_ON: Final = date(2026, 9, 16)
"""Stamped rather than `date.today()`: a generated file whose bytes change daily could not be
compared with the committed one, and `--check` would fail every night."""

DROP_EVERY: Final = 13
"""Drop every 13th scored label, so recall is short of 1.00 and the miss list renders."""

WIDEN_EVERY: Final = 7
NARROW_EVERY: Final = 5
"""Widen or trim a kept quote against the real page, so the matcher's tolerance is used."""

WIDEN_BY: Final = 40
"""Characters of real page text to take from each side of a widened quote."""

NARROW_TO: Final = 40
MIN_NARROWABLE: Final = 80
"""Trim to 40 characters, and only quotes at least 80 long. `MIN_SHARED_CHARS` is 20, so 40
keeps a trimmed row comfortably matchable — the tolerance is exercised, not tested to
destruction."""

UNEXPLAINED_ROWS: Final = 2
DISAGREEMENT_ROWS: Final = 2
"""Rows nothing can explain, and rows a judgement field disagrees on. Both lists would
otherwise be permanently empty and their rendering never reached offline."""

UNEXPLAINED_MIN_CHARS: Final = 60
"""A sentence short enough to be boilerplate would collide with a labelled clause under the
matcher, and land in the matched list instead of the unexplained one."""


class BuildError(Exception):
    """The build refuses rather than writing a fixture that says something untrue."""


@dataclass(frozen=True)
class PackBuild:
    """One pack's rows and the counts `meta.method` is written from."""

    name: str
    rows: tuple[Requirement, ...]
    scored: int
    dropped: int
    widened: int
    narrowed: int
    post_award: int
    unexplained: int
    disagreements: int


# ------------------------------------------------------------------------- the parsed pack


@cache
def pack_pages(fixture_dir: Path) -> dict[str, dict[int, str]]:
    """Every page of every PDF in the pack, by filename and page number.

    Cached for the life of the process: the build reads every page twice — once to reshape a
    quote, once to verify it — and the DE pack is 191 pages, which is twenty seconds a repeat.

    The same set `tests/conftest.tender_pack_pdfs` reads — `documents/*.pdf` plus the notice
    one level up — through `PyMuPDFParser`, which is the reader S3.2.1 runs. A page number
    only means something relative to the reader that produced it.
    """
    pdfs = sorted(fixture_dir.glob("documents/*.pdf")) + sorted(fixture_dir.glob("*.pdf"))
    if not pdfs:
        raise BuildError(f"{fixture_dir}: no PDFs to build from")
    parser = PyMuPDFParser()
    pages: dict[str, dict[int, str]] = {}
    for pdf in pdfs:
        parsed = parser.parse(pdf, document_id=pdf.name)
        pages[pdf.name] = {page.page_number: page.text for page in parsed.pages}
    return pages


def _page_text(pages: Mapping[str, Mapping[int, str]], label: GoldenRequirement) -> str:
    text = pages.get(label.doc, {}).get(label.page)
    if text is None:
        raise BuildError(f"{label.id}: {label.doc} has no page {label.page}")
    return text


# ----------------------------------------------------------------------- reshaping a quote


def widen(quote: str, page: str) -> str:
    """`quote` plus up to `WIDEN_BY` characters of real page text on each side.

    Returns the quote untouched when it cannot be located on the page — the verbatim check at
    the end of the build is what refuses that case, with the label's id in the message.
    """
    start = page.find(quote)
    if start < 0:
        return quote
    return page[max(0, start - WIDEN_BY) : start + len(quote) + WIDEN_BY].strip()


def narrow(quote: str) -> str:
    """The first `NARROW_TO` characters, cut at a word boundary so the run stays readable."""
    if len(quote) < MIN_NARROWABLE:
        return quote
    head = quote[:NARROW_TO]
    cut = head.rfind(" ")
    return (head[:cut] if cut > NARROW_TO // 2 else head).strip()


# --------------------------------------------------------------------------- building rows


def requirement_id(bid_id: str, document_name: str, page: int | None, quote: str) -> str:
    """The id `extract_reqs._requirement_id` would derive for this row. One definition."""
    key = "\x1f".join((bid_id, document_name, str(page), _comparable(quote)))
    return str(uuid.uuid5(REQUIREMENT_ID_NAMESPACE, key))


def bid_id_for(pack: str) -> str:
    return str(uuid.uuid5(BID_ID_NAMESPACE, f"synthetic:{pack}"))


def row_from(
    label: GoldenRequirement, *, bid_id: str, source_lang: str, quote: str
) -> Requirement:
    """One extracted row as the label describes it, quoting `quote` rather than the label's."""
    return Requirement(
        id=requirement_id(bid_id, label.doc, label.page, quote),
        bid_id=bid_id,
        category=label.category,
        kind=label.kind,
        stage=label.stage,
        checkable=label.checkable,
        source_text=quote,
        source_lang=source_lang,
        document_name=label.doc,
        page=label.page,
        ecertis_criterion_id=label.ecertis_criterion_id,
        threshold=label.threshold,
    )


def _other_kind(kind: RequirementKind) -> RequirementKind:
    if kind is RequirementKind.MANDATORY:
        return RequirementKind.OPTIONAL
    return RequirementKind.MANDATORY


def _post_award(golden: GoldenFile) -> GoldenRequirement | None:
    """The first label the stage filter says must *not* be extracted, or `None`."""
    return next(
        (
            entry
            for entry in golden.requirements
            if entry.stage is RequirementStage.CONTRACT_PERFORMANCE
        ),
        None,
    )


def _unlabelled_sentences(
    golden: GoldenFile, pages: Mapping[str, Mapping[int, str]], *, wanted: int
) -> tuple[tuple[str, int, str], ...]:
    """`wanted` sentences from documents no label cites, as `(document, page, sentence)`.

    A document the key excludes is the honest source for a row nothing can explain: text from
    a labelled page would risk overlapping a label and being credited instead of listed.
    """
    labelled = {entry.doc for entry in golden.entries}
    found: list[tuple[str, int, str]] = []
    for document in sorted(set(pages) - labelled):
        for page in sorted(pages[document]):
            for sentence in pages[document][page].split("."):
                cleaned = " ".join(sentence.split())
                if len(cleaned) >= UNEXPLAINED_MIN_CHARS and cleaned in pages[document][page]:
                    found.append((document, page, cleaned))
                if len(found) == wanted:
                    return tuple(found)
    return tuple(found)


def build_pack(name: str) -> PackBuild:
    """Every row of one pack's fixture, and the counts its `meta.method` will state."""
    fixture_dir = TENDERS_DIR / name
    golden = load_golden(fixture_dir / "golden.yaml")
    pages = pack_pages(fixture_dir)
    bid_id = bid_id_for(name)
    language = golden.meta.source_language

    scored = scored_labels(golden)
    rows: list[Requirement] = []
    dropped = widened = narrowed = 0

    for position, label in enumerate(scored, start=1):
        if position % DROP_EVERY == 0:
            dropped += 1
            continue
        kept = len(rows) + 1
        quote = label.quote
        if kept % WIDEN_EVERY == 0:
            quote = widen(quote, _page_text(pages, label))
            widened += 1
        elif kept % NARROW_EVERY == 0:
            trimmed = narrow(quote)
            if trimmed != quote:
                quote = trimmed
                narrowed += 1
        rows.append(row_from(label, bid_id=bid_id, source_lang=language, quote=quote))

    post_award = _post_award(golden)
    if post_award is not None:
        rows.append(
            row_from(post_award, bid_id=bid_id, source_lang=language, quote=post_award.quote)
        )

    unexplained = _unlabelled_sentences(golden, pages, wanted=UNEXPLAINED_ROWS)
    for document, page, sentence in unexplained:
        rows.append(
            Requirement(
                id=requirement_id(bid_id, document, page, sentence),
                bid_id=bid_id,
                category=RequirementCategory.FORMAL,
                kind=RequirementKind.MANDATORY,
                stage=RequirementStage.BID_ELIGIBILITY,
                checkable=Checkability.DOCUMENT_SUBMISSION,
                source_text=sentence,
                source_lang=language,
                document_name=document,
                page=page,
            )
        )

    disagreements = _disagree(rows, wanted=DISAGREEMENT_ROWS)
    return PackBuild(
        name=name,
        rows=tuple(rows),
        scored=len(scored),
        dropped=dropped,
        widened=widened,
        narrowed=narrowed,
        post_award=0 if post_award is None else 1,
        unexplained=len(unexplained),
        disagreements=disagreements,
    )


def _disagree(rows: list[Requirement], *, wanted: int) -> int:
    """Change one judgement field on `wanted` evenly spaced rows, in place in the list.

    **Only the two fields `eval.recall.DisagreementField` names**, `kind` and
    `ecertis_criterion_id`. Changing anything else would move a row without the report saying
    so, and `meta.method` would then claim disagreements the reviewer's list does not show —
    exactly the kind of quiet drift between a file and its own description that H23 was.

    Evenly spaced rather than the first few: the opening rows of a pack are one document's
    first page, and every disagreement in one place reads as a broken document rather than as
    the scattered judgement calls a real run produces.
    """
    if not rows or wanted < 1:
        return 0
    step = max(1, len(rows) // (wanted + 1))
    changed = 0
    for position in range(step, len(rows), step):
        if changed == wanted:
            break
        row = rows[position]
        update = (
            {"ecertis_criterion_id": None}
            if changed % 2 and row.ecertis_criterion_id is not None
            else {"kind": _other_kind(row.kind)}
        )
        rows[position] = row.model_copy(update=update)
        changed += 1
    return changed


# --------------------------------------------------------------- what it says of itself


def method_text(build: PackBuild) -> str:
    """`meta.method`, counted off the rows this run produced. Never typed by hand — H23."""
    return (
        f"Built by scripts/build_extraction_fixtures.py from {build.name}/golden.yaml, not "
        f"extracted by a model. Every quote is a real span of the parsed page its label "
        f"cites, checked with the extractor's own _is_verbatim before this file was written.\n"
        f"Base: the {build.scored} mandatory bid-eligibility labels recall is scored over "
        f"(eval.recall.scored_labels), less every {DROP_EVERY}th ({build.dropped} dropped), "
        f"so recall is not trivially 1.00.\n"
        f"Of the rows kept, {build.widened} quote(s) were widened and {build.narrowed} "
        f"narrowed against the real page, so eval/matching.py's tolerance is exercised in "
        f"both directions rather than only on exact quotes.\n"
        f"Added on top: {build.post_award} contract-performance label(s), so ADR-0015's stage "
        f"filter is scored in both directions; {build.unexplained} sentence(s) from documents "
        f"the answer key does not label, which no label can explain; and "
        f"{build.disagreements} judgement field(s) changed, so the disagreement list is not "
        f"empty.\n"
        f"It exists so scripts/recall.py can be run end to end offline. The recall it yields "
        f"is a property of this file. It measures nothing about the extractor."
    )


def result_of(build: PackBuild) -> ExtractionResult:
    return ExtractionResult(
        meta=ExtractionMeta(
            fixture_dir=f"tests/fixtures/tenders/{build.name}",
            source=ExtractionSource.SYNTHETIC,
            produced_on=PRODUCED_ON,
            method=method_text(build),
            models={},
            cost_usd=None,
            elapsed_seconds=None,
        ),
        requirements=build.rows,
        problems=(),
    )


def fixture_text(build: PackBuild) -> str:
    """The committed bytes: `model_dump_json`, indented, with a trailing newline."""
    return result_of(build).model_dump_json(indent=2, exclude_none=False) + "\n"


# -------------------------------------------------------------------------------- the build


def verify(build: PackBuild, pages: Mapping[str, Mapping[int, str]]) -> None:
    """Refuse a row whose quote is not really on the page it cites. See the module docstring."""
    for row in build.rows:
        page = pages.get(row.document_name, {}).get(row.page or 0)
        if page is None:
            raise BuildError(f"{row.id}: {row.document_name} has no page {row.page}")
        if not _is_verbatim(row.source_text, page):
            raise BuildError(
                f"{row.id}: the quote is not a verbatim span of "
                f"{row.document_name} p.{row.page} — refusing to write a fabricated fixture"
            )


def build_all() -> dict[str, str]:
    """Every pack's fixture text by filename, verified against its own pages."""
    built: dict[str, str] = {}
    for name in PACKS:
        build = build_pack(name)
        verify(build, pack_pages(TENDERS_DIR / name))
        built[f"{name}.json"] = fixture_text(build)
    return built


def stale_files(built: Mapping[str, str]) -> tuple[str, ...]:
    """The filenames whose committed bytes differ from a fresh build."""
    stale: list[str] = []
    for name, text in sorted(built.items()):
        path = EXTRACTIONS_DIR / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    return tuple(stale)


def write_all(built: Mapping[str, str]) -> tuple[Path, ...]:
    written: list[Path] = []
    for name, text in sorted(built.items()):
        path = EXTRACTIONS_DIR / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return tuple(written)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the synthetic extraction fixtures (S3.2.3)."
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the committed fixtures, write nothing"
    )
    args = parser.parse_args(argv)

    try:
        built = build_all()
    except (BuildError, OSError, ValueError) as error:
        print(f"build error: {error}", file=sys.stderr)
        return 1

    if args.check:
        stale = stale_files(built)
        if stale:
            print(
                "extraction fixtures are stale, rebuild with "
                f"`make extraction-fixtures`: {', '.join(stale)}",
                file=sys.stderr,
            )
            return 1
        print(f"extraction fixtures are current: {len(built)} files in {EXTRACTIONS_DIR}")
        return 0

    written = write_all(built)
    rows = sum(len(json.loads(path.read_text())["requirements"]) for path in written)
    print(f"wrote {len(written)} files ({rows} rows) to {EXTRACTIONS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
