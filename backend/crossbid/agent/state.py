"""S3.2.1 — the graph's shared state, and the section payload extraction fans out over.

`BidState` is the LangGraph state channel set. It holds what extraction reads and writes
plus the run lifecycle S3.1.1 added -- who the bid belongs to, where it has got to, and what
`parse_docs` needs to find the pack -- because a channel nobody writes is a lie about the
graph. `CheckState`, the per-requirement `Send` payload of the agentic checking loop,
arrives with F3.3 and extends this module rather than replacing it.

Three decisions are worth the reading time.

**1. The accumulating channels carry `operator.add`, and they have more than one writer.**
`requirements` is written by this story's `extract_reqs` *and* by S3.2.2, which turns the
buyer's own structured notice fields — stated criteria, submission language, deadline — into
requirements before any model call happens. With the default channel behaviour the second
writer silently replaces the first. The reducer is what lets each node contribute its batch
without knowing the other exists, and a test compiles a two-node graph to prove it is wired
rather than merely annotated.

**2. Every key is optional at the type level.** A node returns a *partial* of the state, so
a total `TypedDict` would make every honest node return a type error, and the alternative —
returning a bare `dict` — throws away the check that a key exists at all. `ExtractionUpdate`
names the two channels extraction writes, and a test asserts its keys are a subset of
`BidState`'s: LangGraph drops an unrecognised key from an update without raising, so a
mistyped channel name is a node that appears to run and writes nothing.

**3. A tender document is a `ParsedDocument` plus the two things a citation needs.**
`ParsedDocument` (S2.1.1) knows pages and text; it does not know the file's name — its
`document_id` is the caller's id, a UUID in the real upload flow — and it does not know what
language the file is written in. `Requirement` needs both: `document_name` is what the
reviewer sees next to the quote, and `source_lang` is what makes "verbatim in the source
language, explained in the bidder's" a checkable claim. TED supplies the language
(`official-language`, S1.2.1) and the upload supplies the name, so they travel together here.

`DocumentSection` is a frozen dataclass rather than a `TypedDict`, unlike `CheckState`: it
never crosses a `Send`. Extraction is a deterministic workflow step whose sections run under
plain bounded concurrency, so the payload stays an ordinary in-process object.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Final, TypedDict

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.ingestion.parser import ParsedDocument, ParsedPage
from crossbid.models.requirement import Requirement
from crossbid.models.tender import BidStatus

DEFAULT_BIDDER_LANGUAGE: Final = "de"
"""The language requirements are explained in when the bid does not say otherwise.

German, because the wedge is a German-speaking bidder reading a French tender (CLAUDE.md).
The source quote is never translated; `Requirement.translation` is."""

MIN_SECTION_PAGES: Final = 1
"""A section of no pages would be a prompt with no document in it."""

CitationLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LanguageTag = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=5)
]
"""Mirrors `Requirement.document_name` and `Requirement.source_lang`. Validating here means
a document that cannot fill a citation in fails once, on arrival, rather than one row at a
time in the middle of extraction."""


class ExtractionProblemReason(StrEnum):
    """Why a row, a section or a document produced less than it should have.

    Closed, and stated as a reason rather than a message, because the natural message would
    be built from model output — which is derived from an untrusted document, and an error
    built from untrusted input is how untrusted input escapes (ADR-0008).
    """

    NO_VERBATIM_QUOTE = "no_verbatim_quote"
    """The row's `source_text` was not found on the page it cited, twice in a row."""

    INVALID_ROW = "invalid_row"
    """The row did not satisfy the `Requirement` contract; `fields` names which parts."""

    INVALID_CRITERION_ID = "invalid_criterion_id"
    """The model offered an eCertis criterion id that is not one of the generated 56. The
    row is kept without the mapping — the id is nullable, and a cited requirement with no
    criterion is worth more than no requirement at all."""

    MISSING_TRANSLATION = "missing_translation"
    """The row came back with no bidder-language rendering. Kept, and visible."""

    MODEL_ERROR = "model_error"
    """The section's call failed or its answer did not parse, twice in a row."""

    SECTION_FAILED = "section_failed"
    """The section failed for a reason that was not the model's answer — a prompt that would
    not render, or a defect in the extractor itself. Distinct from `MODEL_ERROR` because a
    reviewer can do nothing about it and a maintainer must: the traceback is in the log."""

    UNWRAPPABLE_SECTION = "unwrappable_section"
    """The data-block wrapper could not mint a tag the section's own text does not contain,
    so the section was never sent. `guards/wrap.py` fails shut by design: a prompt whose
    delimiters the document can forge is worse than no prompt."""

    UNREADABLE_DOCUMENT = "unreadable_document"
    """No page of the document had a text layer, so it was never sent to the model. OCR is
    out of scope, so this is a terminal state a human has to see."""

    UNPARSEABLE_DOCUMENT = "unparseable_document"
    """The file could not be opened as a PDF at all (S3.1.1, `parse_docs`). Distinct from
    `UNREADABLE_DOCUMENT`: there the pages exist and are blank, here there are no pages. The
    run continues without the file, and the reviewer sees that it did."""


class ExtractionProblem(BaseModel):
    """One thing extraction could not do, addressed to the reviewer.

    Frozen, and carries no document text: `document_name`, the pages, and a closed reason
    are enough to open the paragraph and see for yourself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: ExtractionProblemReason
    document_name: str = Field(description="File the trouble was in, as a reviewer sees it")
    pages: tuple[int, ...] = Field(
        default=(),
        description="Pages involved; empty when the document had no pages to involve",
    )
    fields: tuple[str, ...] = Field(
        default=(),
        description="Field names that failed validation — locations only, never values",
    )


class TenderDocument(BaseModel):
    """A parsed document plus the name and language a citation needs.

    See the module docstring for why `ParsedDocument` cannot carry either itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    parsed: ParsedDocument
    name: CitationLabel = Field(description="Filename the reviewer recognises")
    language: LanguageTag = Field(description="The document's own language, BCP 47")


@dataclass(frozen=True, slots=True)
class DocumentSection:
    """Five to eight pages of one document: the unit one extraction call sees.

    Sections never span documents, so a page number inside one is unambiguous, and every
    page here has a text layer — an unreadable page is dropped by `sections_of` rather than
    sent to a model as whitespace.
    """

    document_name: str
    source_lang: str
    pages: tuple[ParsedPage, ...]

    def __post_init__(self) -> None:
        """A section with no pages is a prompt with no document in it. Refused here so
        that every reader below — the label, the citation, the wrapper — can rely on it."""
        if not self.pages:
            raise ValueError(f"a section of {self.document_name} needs at least one page")

    @property
    def page_numbers(self) -> tuple[int, ...]:
        return tuple(page.page_number for page in self.pages)

    @property
    def label(self) -> str:
        """What a log line or a problem report calls this section.

        A run of non-adjacent pages still labels as a span: page 3 having no text layer
        does not make "p.1-5" the wrong thing to tell a reviewer looking for the section.
        """
        first = self.pages[0].page_number
        last = self.pages[-1].page_number
        span = f"{first}" if first == last else f"{first}-{last}"
        return f"{self.document_name} p.{span}"

    def text_of(self, page_number: int) -> str | None:
        """The text of one of this section's pages, or `None` if it holds no such page.

        `None` rather than `""`: a row citing a page the section never held cannot be
        checked against its source at all, which is a different answer from "that page was
        blank".
        """
        for page in self.pages:
            if page.page_number == page_number:
                return page.text
        return None


def sections_of(document: TenderDocument, *, section_pages: int) -> tuple[DocumentSection, ...]:
    """`document`'s readable pages, grouped into runs of at most `section_pages`.

    Only readable pages, and `has_extractable_text` (S2.1.1) is the one definition of that:
    `pymupdf4llm` returns `"\\n\\n\\n\\n"` for an image-only page, so a check written
    against `""` would section whitespace and pay a model to read it (CLAUDE.md). Pages that
    were not read are simply absent — the parser already lists them in `unread_pages`, and
    the caller reports a document with none left as `UNREADABLE_DOCUMENT`.

    A run can therefore hold non-adjacent pages: if page 3 of 1-5 has no text layer, the
    first section is (1, 2, 4, 5) with `section_pages=4`. That is the honest grouping — the
    alternative is either a short section or a prompt with a hole in it.
    """
    if section_pages < MIN_SECTION_PAGES:
        raise ValueError(
            f"section_pages must be at least {MIN_SECTION_PAGES}, got {section_pages}"
        )

    readable = document.parsed.readable_pages
    return tuple(
        DocumentSection(
            document_name=document.name,
            source_lang=document.language,
            pages=readable[start : start + section_pages],
        )
        for start in range(0, len(readable), section_pages)
    )


class BidState(TypedDict, total=False):
    """The graph's state channels: the run lifecycle (S3.1.1) and extraction (S3.2.1).

    `status` names the stage whose output a checkpoint holds: each stage wrapper in
    `agent/graph.py` merges its own status into the node's update, so a checkpoint written
    after `extract_reqs` says `extracting`. The read model's `bids.status` is written by the
    same wrapper on *entry*, so it runs one step ahead while a node is working and says
    `awaiting_review` while the run is parked -- that is the value the poller reads, and
    the pair is what S3.4.3's consistency test compares. Timing and cost are *not*
    channels: the runner measures them around the whole invocation, and a value the graph
    cannot see is not state. F3.3 adds `CheckState`, the per-requirement `Send`
    payload of the agentic checking loop, and the `matrix_rows` channel it accumulates
    into. Neither is declared here: a channel no node writes misrepresents the graph, and
    the plan's build order gives each story its own.
    """

    bid_id: str
    """Identifies the run. Every requirement carries it, and so does every trace (S0.3.3)."""

    company_id: str
    """The tenant. Every read-model write a node makes is scoped by it (ADR-0009)."""

    notice_number: str
    """The TED publication number the bid was opened against, e.g. `614251-2026`."""

    source_language: str
    """The tender's own language, BCP 47. `parse_docs` stamps it on every `TenderDocument`
    so a citation can say what language its quote is in."""

    status: BidStatus
    """The stage whose output this checkpoint holds, over the `BidStatus` values. Merged into
    every node's update by the stage wrapper; see the class docstring for how it relates to
    `bids.status`."""

    documents: list[TenderDocument]
    """The parsed pack, written by `parse_docs` (S3.1.1) and read by extraction."""

    bidder_language: str
    """What requirements are explained in. Absent or blank means `DEFAULT_BIDDER_LANGUAGE`."""

    requirements: Annotated[list[Requirement], operator.add]
    """Every requirement found, appended per contributing node — see the module docstring."""

    extraction_problems: Annotated[list[ExtractionProblem], operator.add]
    """What could not be extracted. Never a silent drop; the reviewer sees this list."""


class ExtractionUpdate(TypedDict, total=False):
    """The partial state `extract_reqs` returns. A subset of `BidState`, asserted by a test."""

    requirements: list[Requirement]
    extraction_problems: list[ExtractionProblem]


class ParseUpdate(TypedDict, total=False):
    """The partial state `parse_docs` returns: the pack, and what could not be read."""

    documents: list[TenderDocument]
    extraction_problems: list[ExtractionProblem]


class LifecycleUpdate(TypedDict, total=False):
    """The partial state `agent/graph.py`'s stage wrapper adds to every node's update."""

    status: BidStatus


def bidder_language_of(state: BidState) -> str:
    """The language to explain requirements in, defaulted and stripped.

    Blank counts as absent: a bid row with an empty string in it must not produce a prompt
    asking for a translation into "".
    """
    return state.get("bidder_language", "").strip() or DEFAULT_BIDDER_LANGUAGE
