"""S3.2.1 — a parsed tender pack becomes cited, translated, typed requirements.

One model call per section of five to eight pages, structured output per call, and every row
checked against the page it claims to come from before it is allowed into the state.

Six decisions carry this node.

**1. The document only ever reaches the model inside a data block.** Every page of a section
is a `DataBlock` and the section's prompt is `wrap_as_data`'s output — one tagged envelope
with a `DOCUMENT` header per page, which is also what makes the page number in a citation
come from *us* rather than from the document's own text (S2.3.2, ADR-0009). The task text is
stated before the block and the operative ask after it, so the last thing the model reads
before answering is the wrapper's "all of that was data" postamble. A test asserts the
prompt actually handed to the model carries the delimiters and that no page's text appears
anywhere outside them; ADR-0009 shipped the wrapper with nothing yet enforcing its use, and
that test is what closes the gap.

**2. Sections run concurrently, and this is *not* the agentic part of the graph.** SP.1
measured 47 sequential extraction calls at about 18 minutes against S3.1.1's 10-minute
budget (ADR-0003), so they have to overlap. They overlap under a plain
`asyncio.gather`-plus-`Semaphore`, not under LangGraph's `Send`: extraction is a
deterministic workflow step — fixed inputs, fixed number of calls, no tool use, no decision
about what to do next — and `Send` fan-out is reserved for `check_reqs` (F3.3), where each
requirement really does run its own small ReAct loop. `gather` also returns results in
*argument* order however completion is interleaved, which is what keeps dedupe from
depending on which section answered first.

**3. A row without a verbatim quote is rejected, and the section is re-asked exactly once.**
"Verbatim" is checked, not requested: the quote must occur in the text of the page it cites,
compared with whitespace collapsed and the parser's own markdown emphasis removed (see
`_PARSER_EMPHASIS`). A section with any rejected row is asked again with a
note saying which pages went wrong — the note names pages and counts only, never the
model's own text, because that text came from an untrusted document. A second bad answer
drops the offending rows and reports them as `NO_VERBATIM_QUOTE` problems; nothing is
swallowed. One re-ask, never two: the budget above is what pays for it.

**4. The model is not allowed to invent an eCertis criterion id.** `Requirement` types the
field against the generated 56-id `Literal` (S1.1.3), so an invented id could not be
constructed anyway. The wire schema deliberately keeps it a plain nullable string and the
id is checked here instead: a bad id costs the *mapping* and is reported, where typing the
wire field would make one hallucinated UUID reject the whole section's output. The same
reasoning applies to `page` and to quote length — the wire schema is loose so that one bad
row cannot take twenty good ones down with it, and `Requirement` is what says no.

**5. Extraction fills `translation` in the same call.** A second pass over 238 rows would be
238 more calls against a budget that ADR-0003 already found tight, and the model has the
source paragraph in front of it exactly once. `Requirement.translation` stays nullable, so a
row that comes back without one is kept and the gap reported rather than the row dropped: a
quote with a page still beats no row at all.

**6. Only `bid_eligibility` rows leave this node.** ADR-0003's central finding: without the
discriminator one German pack yields 579 "mandatory" requirements, because the AGB, EVB-IT,
VOL/B, framework agreement and data-processing agreement are all genuinely phrased as
obligations. They bind the winner after award, not the bidder at qualification time. The
filter cut the set to 238 with no measured recall loss.

Dedupe is by quote similarity *and* page proximity *within one document*: page numbers of
different files are not comparable, and the same obligation cited from two documents is two
citations, not a duplicate.

Two `Requirement` fields are deliberately left unset. `threshold` is what makes a scorer
compare rather than ask a model to judge, and its consumer is F3.4; asking for it here would
be a second structured field to tune before anything reads it. `deadline` belongs to S3.2.2,
which takes it from the notice's own `deadline-receipt-tender-date-lot` field rather than
from prose, because that is the one date a bid may not get wrong.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Optional, Protocol, cast

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crossbid.agent.prompts import render
from crossbid.agent.state import (
    BidState,
    DocumentSection,
    ExtractionProblem,
    ExtractionProblemReason,
    ExtractionUpdate,
    TenderDocument,
    bidder_language_of,
    sections_of,
)
from crossbid.guards.wrap import DataBlock, DataWrapError, wrap_as_data
from crossbid.llm import chat_model, resilient
from crossbid.models.ecertis_criteria import CRITERION_IDS, EcertisCriterionId
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)
from crossbid.settings import ModelRole, Settings

logger = logging.getLogger(__name__)

EXTRACT_PROMPT_NAME: Final = "extract"
BIDDER_LANGUAGE_MARKER: Final = "bidder_language"

DEFAULT_SECTION_PAGES: Final = 6
"""Six pages, the size SP.1 measured recall 1.00/0.95 at. The plan's range is 5-8."""

DEFAULT_CONCURRENCY: Final = 5
"""Sections in flight at once. Bounded because it is OpenRouter's rate limit and this
account's spend that the number protects, and unbounded `gather` over a 47-section pack
would open 47 connections at once."""

RE_ASKS_PER_SECTION: Final = 1
"""One re-ask, so a section costs at most two calls. The story says "re-asked once"; the
latency budget of ADR-0003 is why it is not "until it gets it right"."""

QUOTE_SIMILARITY_THRESHOLD: Final = 0.92
"""How alike two quotes must read to count as the same obligation. High on purpose: SP.1's
false positive was a 0.68 match between two genuinely different requirements (ADR-0003), and
dropping a real requirement costs recall, which is the graded number."""

PAGE_PROXIMITY: Final = 2
"""Pages apart within which two similar quotes are the same clause restated rather than a
duty that recurs deliberately — a signature block repeated per lot, say."""

MATRIX_STAGE: Final = RequirementStage.BID_ELIGIBILITY
"""The only stage that reaches the matrix. See decision 6 in the module docstring."""

REQUIREMENT_ID_NAMESPACE: Final = uuid.UUID("6b4f0a52-3d17-4c0e-9f8a-2e5c7b1d40a9")
"""Namespace for the `uuid5` a requirement's id is. Deterministic rather than random so that
re-running extraction over the same pack produces the same ids: the `requirements` table is
keyed on them, and a retried run should update rows rather than double them."""

VALID_CRITERION_IDS: Final = frozenset(CRITERION_IDS)

_WHITESPACE: Final = re.compile(r"\s+")

_PARSER_LINE_BREAK: Final = re.compile(r"<br\s*/?>", re.IGNORECASE)
_PARSER_INLINE_TAGS: Final = re.compile(r"</?(?:sup|sub|u|b|i|em|strong)\s*>", re.IGNORECASE)
"""The inline *tags* `pymupdf4llm` emits, replaced by a space before the check.

Emphasis below covers `**bold**`; this covers what the parser writes when markdown cannot
express the layout. Inside a table cell a line break arrives as a literal `<br>`, and
footnote markers arrive as `<sup>`.

This one was measured, not guessed. On 2026-09-13 seven rows from the DE pack's
`Eigenerklärung Ausschlussgründe` were thrown away as "not verbatim" while being perfectly
honest quotes: the page holds
`... aufträge gegen geltende<br>umwelt-, sozial- oder arbeitsrechtliche ...` and the model,
reading the clause as a human does, wrote a space where the `<br>` is. The quote matched for
65 characters and then diverged on parser punctuation the buyer never wrote. Those rejections
cost nine labels of recall in one document.

The two patterns are separate because the substitution differs, and getting that backwards
re-breaks the check. `<br>` is a *line break*: it becomes a space, or `geltende<br>umwelt`
fuses into one word that appears in no document. The inline tags are not whitespace and
become nothing, or `EUR<sup>1</sup>` would split into `EUR 1` and reject a quote reading
`EUR1`.
"""

_PARSER_EMPHASIS: Final = re.compile(r"[*_`]+")
"""Inline markdown runs, removed from both sides of the verbatim check.

The default parser is `pymupdf4llm`, which returns markdown: a bold word arrives as
`**Umsatz**` and that is 1.3% of the DE pack's characters (ADR-0008). Those asterisks are
the *parser's* punctuation, not the buyer's, so a model that leaves them out of a quote has
still quoted the document — and under a plain substring check that honest quote would be
rejected, re-asked, and then dropped, which costs recall, the graded number. SP.1 never met
this because it read `page.get_text()` rather than markdown.

Only the inline marks. `#` is left alone: it occurs at the start of a heading line, never in
the middle of a clause, so it cannot split a quote the way an emphasised word can.
"""

CLOSING_ASK: Final = (
    "List every obligation the block above states, one entry each, following the field "
    "rules given before it. Quote verbatim in the document's own language, cite the page "
    "from the DOCUMENT header the quote sat under, and return an empty list if the pages "
    "state no obligation."
)
"""The operative instruction, placed after the block. See `guards/wrap.py` on why."""

RE_ASK_NOTE: Final = (
    "Some entries were discarded: their quote was not found on the page they cited. "
    "Pages affected: {pages}. Answer again for the same block, and this time copy each "
    "quote character for character out of the page it sits on, or leave the entry out."
)
MODEL_ERROR_NOTE: Final = (
    "Your previous answer could not be read as the requested structure. Answer again for "
    "the same block, returning only the fields asked for."
)
"""Both notes name pages and nothing else. A note that quoted the model's own output back
would be feeding text of untrusted origin into the next prompt outside a data block."""


class ExtractedRequirement(BaseModel):
    """One row as the model returns it, before anything is believed.

    Deliberately looser than `Requirement`: no length limit on the quote, no lower bound on
    the page, and the criterion id is a plain string. Every one of those is checked in this
    module, and the looseness is what keeps one bad row from invalidating the whole
    section's structured output (decision 4 in the module docstring).
    """

    model_config = ConfigDict(frozen=True)

    source_text: str = Field(
        description="The obligation, verbatim in the document's own language"
    )
    translation: str = Field(description="The same obligation in the bidder's language")
    page: int = Field(description="Page number from the DOCUMENT header of the quote")
    kind: RequirementKind
    category: RequirementCategory
    stage: RequirementStage
    checkable: Checkability
    ecertis_criterion_id: str | None = Field(
        default=None,
        description="ESPD criterion UUID, only when the section itself prints one",
    )


class SectionExtraction(BaseModel):
    """The structured answer to one section's prompt."""

    model_config = ConfigDict(frozen=True)

    requirements: list[ExtractedRequirement] = Field(default_factory=list)


Prompt = tuple[tuple[str, str], ...]
"""Messages as `(role, content)` pairs, LangChain's tuple form. A tuple so that a re-ask
builds a new prompt instead of appending to the one already sent."""

SectionExtractor = Callable[[Prompt], Awaitable[SectionExtraction]]
"""One structured call. The seam the tests replace: a fake records the prompt it was handed,
which is how the data-block postcondition is asserted without a model."""


class StructuredRunnable(Protocol):
    """The slice of a LangChain runnable this module uses.

    A Protocol so the adapter below can be tested against a fake that returns a dict, which
    is one of the two shapes `with_structured_output` really produces.
    """

    async def ainvoke(self, messages: Any, /) -> Any: ...


def structured_extractor(model: StructuredRunnable) -> SectionExtractor:
    """Adapt a structured-output runnable to the `SectionExtractor` seam.

    The answer is re-validated rather than trusted: `with_structured_output` may hand back a
    dict, and CLAUDE.md's rule is that a model's output is schema-validated before use.
    """

    async def extract(prompt: Prompt) -> SectionExtraction:
        answer = await model.ainvoke(list(prompt))
        return SectionExtraction.model_validate(answer)

    return extract


def build_extract_reqs(settings: Settings) -> RequirementExtractor:
    """The node as the graph wires it (S3.1.1), configured from settings.

    Both slugs are bound to the same schema and handed to `resilient`, so a section whose
    call times out is retried once and then asked of the smaller model (S3.4.4). Binding
    happens before the wrapper rather than inside it: `with_structured_output` is what makes
    either model answer a `SectionExtraction`, and a wrapper that bound its own would have
    to know this node's schema.
    """
    bound = (
        chat_model(role, settings).with_structured_output(SectionExtraction)
        for role in (ModelRole.EXTRACT, ModelRole.FALLBACK)
    )
    primary, fallback = bound
    return RequirementExtractor(
        structured_extractor(resilient(primary, fallback)),
        section_pages=settings.runtime.ingestion.section_pages,
        concurrency=settings.runtime.agent.extract_concurrency,
        system_prompt=settings.runtime.system_prompt,
    )


@dataclass(frozen=True, slots=True)
class _SectionResult:
    """What one section contributed: its rows, and what it could not deliver."""

    rows: tuple[Requirement, ...] = ()
    problems: tuple[ExtractionProblem, ...] = ()


@dataclass(frozen=True, slots=True)
class _Attempt:
    """One call's outcome, plus the note that would be sent if it is asked again.

    `correction is None` means the answer was clean and there is nothing to re-ask.
    """

    result: _SectionResult
    correction: str | None = None


class RequirementExtractor:
    """The `extract_reqs` node: `(state, config) -> partial state`.

    A callable object rather than a bare function because the model seam and the four knobs
    have to come from somewhere, and a node the graph builds once and calls with
    `(state, config)` keeps the convention CLAUDE.md states while staying injectable.
    Holds no per-run state, so one instance serves every concurrent bid.
    """

    def __init__(
        self,
        extractor: SectionExtractor,
        *,
        section_pages: int = DEFAULT_SECTION_PAGES,
        concurrency: int = DEFAULT_CONCURRENCY,
        system_prompt: str | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError(f"concurrency must be at least 1, got {concurrency}")
        self._extractor = extractor
        self._section_pages = section_pages
        self._concurrency = concurrency
        self._system_prompt = system_prompt

    @property
    def section_pages(self) -> int:
        return self._section_pages

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def system_prompt(self) -> str | None:
        return self._system_prompt

    async def __call__(
        self,
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`, and the spelling is load-bearing:
        # this module uses postponed annotations, so LangGraph sees the *string* of the
        # annotation and matches it against a list that holds "RunnableConfig" and
        # "Optional[RunnableConfig]" and not "RunnableConfig | None". Write the modern
        # spelling and every graph build warns and the config is never injected.
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> ExtractionUpdate:
        """Every eligibility requirement in the pack, deduped, plus what went wrong.

        `config` is part of the node contract LangGraph calls with and is unused here:
        extraction needs nothing from the run config, and a node whose signature differed
        could not be swapped for this one.
        """
        bid_id = state.get("bid_id", "").strip()
        if not bid_id:
            raise ValueError("bid_id is required: a requirement without one cannot be stored.")

        sections, problems = self._plan(state.get("documents", []))
        results = await self._run_sections(sections, bid_id, bidder_language_of(state))

        rows = [row for result in results for row in result.rows]
        return {
            "requirements": list(_dedupe(row for row in rows if row.stage is MATRIX_STAGE)),
            "extraction_problems": [
                *problems,
                *(problem for result in results for problem in result.problems),
            ],
        }

    # ------------------------------------------------------------------- planning

    def _plan(
        self, documents: Sequence[TenderDocument]
    ) -> tuple[tuple[DocumentSection, ...], tuple[ExtractionProblem, ...]]:
        """Sections in document order, and a problem per document that could not be read."""
        sections: list[DocumentSection] = []
        problems: list[ExtractionProblem] = []
        for document in documents:
            found = sections_of(document, section_pages=self._section_pages)
            if not found:
                problems.append(
                    ExtractionProblem(
                        reason=ExtractionProblemReason.UNREADABLE_DOCUMENT,
                        document_name=document.name,
                        pages=document.parsed.unread_pages,
                    )
                )
                continue
            sections.extend(found)
        return tuple(sections), tuple(problems)

    async def _run_sections(
        self, sections: Sequence[DocumentSection], bid_id: str, language: str
    ) -> tuple[_SectionResult, ...]:
        """Every section, at most `concurrency` at a time, results in section order.

        `gather` orders by argument, not by completion, so the rows dedupe sees are always
        in document-and-page order no matter how the calls interleave.

        **Nothing raises out of here, and the catch-all is the reason.** `gather` without
        `return_exceptions` re-raises the first exception it sees, which would throw away
        every *other* section's finished rows — the exact failure the story forbids. The
        model call has its own handler one level down; this one is for everything else a
        section does, from a prompt that will not render to a defect in the row reader. It
        is deliberately broad and deliberately loud: the reviewer gets a problem, and the
        log gets the traceback, because an unexpected exception here is a bug and not a
        condition to be quietly absorbed.
        """
        limit = asyncio.Semaphore(self._concurrency)

        async def run(section: DocumentSection) -> _SectionResult:
            async with limit:
                try:
                    return await self._extract_section(section, bid_id, language)
                except Exception:
                    logger.exception("Extraction failed for section %s", section.label)
                    reason = ExtractionProblemReason.SECTION_FAILED
                    return _SectionResult(problems=(_problem(reason, section),))

        return tuple(await asyncio.gather(*(run(section) for section in sections)))

    # -------------------------------------------------------------------- one section

    async def _extract_section(
        self, section: DocumentSection, bid_id: str, language: str
    ) -> _SectionResult:
        """One section's rows, re-asking at most `RE_ASKS_PER_SECTION` times."""
        try:
            prompt = self._prompt(section, language)
        except DataWrapError:
            # Every tag the wrapper offered turned up in the section's own text. Failing
            # shut is wrap.py's decision; losing one section is better than losing the run.
            reason = ExtractionProblemReason.UNWRAPPABLE_SECTION
            return _SectionResult(problems=(_problem(reason, section),))

        asks = 0
        while True:
            asks += 1
            attempt = await self._attempt(prompt, section, bid_id)
            if attempt.correction is None or asks > RE_ASKS_PER_SECTION:
                return attempt.result
            prompt = (*prompt, ("human", attempt.correction))

    async def _attempt(self, prompt: Prompt, section: DocumentSection, bid_id: str) -> _Attempt:
        """One call, and what to say if it has to be made again."""
        try:
            answer = await self._extractor(prompt)
        except Exception as exc:
            # Any provider, transport or validation failure: the section is worth one more
            # ask, and which of them it was changes nothing about what we do next. It is
            # still logged, because "model_error" alone does not tell a developer whether
            # OpenRouter returned a 502 or the answer failed the schema. The exception's
            # *message* is deliberately left out: a `ValidationError` over a structured
            # answer quotes the model's output, which is document-derived text (ADR-0008).
            logger.warning(
                "Extraction call failed for %s: %s", section.label, type(exc).__name__
            )
            return _Attempt(
                result=_SectionResult(
                    problems=(_problem(ExtractionProblemReason.MODEL_ERROR, section),)
                ),
                correction=MODEL_ERROR_NOTE,
            )
        return _read_answer(answer, section, bid_id)

    def _prompt(self, section: DocumentSection, language: str) -> Prompt:
        """The messages one section's call is made with.

        One `DataBlock` per page, so every page carries its own `DOCUMENT` header and a
        citation's page number comes from the header rather than from the text. Built
        directly rather than through `block_from_fragment`, which fits a `Chunk`'s
        `document_id`/`page` shape; a `ParsedPage` names its page differently.
        """
        wrapped = wrap_as_data(
            tuple(
                DataBlock(
                    text=page.text,
                    label=section.document_name,
                    pages=(page.page_number,),
                )
                for page in section.pages
            )
        )
        task = render(EXTRACT_PROMPT_NAME, {BIDDER_LANGUAGE_MARKER: language})
        human = "\n\n".join((task, wrapped.text, CLOSING_ASK))
        system: Prompt = (
            () if self._system_prompt is None else (("system", self._system_prompt),)
        )
        return (*system, ("human", human))


# ---------------------------------------------------------------------- reading an answer


def _read_answer(answer: SectionExtraction, section: DocumentSection, bid_id: str) -> _Attempt:
    """Turn one structured answer into rows, keeping only what the pages support."""
    rows: list[Requirement] = []
    problems: list[ExtractionProblem] = []
    unquoted: list[int] = []

    for extracted in answer.requirements:
        page_text = section.text_of(extracted.page)
        if page_text is None or not _is_verbatim(extracted.source_text, page_text):
            unquoted.append(extracted.page)
            reason = ExtractionProblemReason.NO_VERBATIM_QUOTE
            problems.append(_problem(reason, section, extracted.page))
            continue
        row, row_problems = _to_requirement(extracted, section, bid_id)
        problems.extend(row_problems)
        if row is not None:
            rows.append(row)

    result = _SectionResult(
        # By page, so page proximity means the same thing whatever order the model answered
        # in. Stable, so two rows quoting one page keep the order they were written in.
        rows=tuple(sorted(rows, key=_page_of)),
        problems=tuple(problems),
    )
    if not unquoted:
        return _Attempt(result=result)
    pages = ", ".join(str(page) for page in sorted(set(unquoted)))
    return _Attempt(result=result, correction=RE_ASK_NOTE.format(pages=pages))


def _to_requirement(
    extracted: ExtractedRequirement, section: DocumentSection, bid_id: str
) -> tuple[Requirement | None, tuple[ExtractionProblem, ...]]:
    """One extracted row as a `Requirement`, or `None` plus the reason it is not one."""
    criterion_id, problems = _criterion_of(extracted, section)
    translation = extracted.translation.strip() or None
    try:
        row = Requirement(
            id=_requirement_id(bid_id, section, extracted),
            bid_id=bid_id,
            category=extracted.category,
            kind=extracted.kind,
            stage=extracted.stage,
            checkable=extracted.checkable,
            source_text=extracted.source_text,
            source_lang=section.source_lang,
            document_name=section.document_name,
            page=extracted.page,
            translation=translation,
            ecertis_criterion_id=criterion_id,
        )
    except ValidationError as exc:
        # Locations only. A message built from the value would carry document-derived text
        # into a log line and a UI (ADR-0008).
        return None, (
            _problem(
                ExtractionProblemReason.INVALID_ROW,
                section,
                extracted.page,
                fields=_locations(exc),
            ),
        )

    if translation is None:
        problems = (
            *problems,
            _problem(ExtractionProblemReason.MISSING_TRANSLATION, section, extracted.page),
        )
    return row, problems


def _criterion_of(
    extracted: ExtractedRequirement, section: DocumentSection
) -> tuple[EcertisCriterionId | None, tuple[ExtractionProblem, ...]]:
    """The row's criterion id if it is one of the generated 56, otherwise none of them.

    Case is normalised, because a DUME prints the same UUID in either case; anything else is
    rejected rather than repaired. `cast` is unavoidable: membership in a set built from the
    `Literal` is exactly the check the type wants, and no type checker can see that.
    """
    offered = (extracted.ecertis_criterion_id or "").strip().lower()
    if not offered:
        return None, ()
    if offered not in VALID_CRITERION_IDS:
        reason = ExtractionProblemReason.INVALID_CRITERION_ID
        return None, (_problem(reason, section, extracted.page),)
    return cast(EcertisCriterionId, offered), ()


def _requirement_id(
    bid_id: str, section: DocumentSection, extracted: ExtractedRequirement
) -> str:
    """A `uuid5` over bid, document, page and quote — see `REQUIREMENT_ID_NAMESPACE`."""
    key = "\x1f".join(
        (
            bid_id,
            section.document_name,
            str(extracted.page),
            _comparable(extracted.source_text),
        )
    )
    return str(uuid.uuid5(REQUIREMENT_ID_NAMESPACE, key))


def _locations(exc: ValidationError) -> tuple[str, ...]:
    """The field paths a validation error names, deduplicated, in order."""
    paths = (".".join(str(part) for part in error["loc"]) for error in exc.errors())
    return tuple(dict.fromkeys(path for path in paths if path))


def _problem(
    reason: ExtractionProblemReason,
    section: DocumentSection,
    *pages: int,
    fields: tuple[str, ...] = (),
) -> ExtractionProblem:
    """A problem addressed to the reviewer: where it happened, and nothing quoted."""
    return ExtractionProblem(
        reason=reason,
        document_name=section.document_name,
        pages=pages or section.page_numbers,
        fields=fields,
    )


# ------------------------------------------------------------------- quotes and duplicates


def _is_verbatim(quote: str, page_text: str) -> bool:
    """Whether `quote` really occurs on the page, comparing with whitespace collapsed.

    Whitespace only: a PDF breaks a sentence across lines wherever the column ends, so
    demanding the newlines back would reject honest quotes. Case is *not* folded — a
    verbatim quote of a legal requirement keeps the case the buyer wrote it in.
    """
    needle = _normalised(quote)
    return bool(needle) and needle in _normalised(page_text)


def _dedupe(rows: Iterable[Requirement]) -> tuple[Requirement, ...]:
    """Keep the first of each obligation; drop a later near-repeat of a nearby page.

    O(n^2) over the kept rows, which at ADR-0003's 238-row scale is a few thousand string
    comparisons. Same document only: page 3 of one file and page 3 of another are not
    "two pages apart", and one obligation cited from two documents is two citations.
    """
    kept: list[tuple[Requirement, str]] = []
    for row in rows:
        comparable = _comparable(row.source_text)
        if any(_is_repeat(row, comparable, other, text) for other, text in kept):
            continue
        kept.append((row, comparable))
    return tuple(row for row, _ in kept)


def _is_repeat(row: Requirement, text: str, other: Requirement, other_text: str) -> bool:
    if row.document_name != other.document_name:
        return False
    if abs(_page_of(row) - _page_of(other)) > PAGE_PROXIMITY:
        return False
    # `autojunk=False`: the heuristic it disables treats characters that recur in more than
    # 1% of a long string as junk, which for a 2000-character legal quote means most of the
    # alphabet, and it would report near-identical clauses as unlike.
    ratio = difflib.SequenceMatcher(None, text, other_text, autojunk=False).ratio()
    return ratio >= QUOTE_SIMILARITY_THRESHOLD


def _page_of(row: Requirement) -> int:
    """The row's page. Zero is unreachable here and exists for the type checker.

    `Requirement.page` became nullable when a published ESPD request gained the right to
    produce rows that cite a criterion instead of a page (S2.5.1). Nothing in this module
    can see one: every row here is built from an `ExtractedRequirement`, which carries an
    `int` page that is then checked against the text of that very page.
    """
    return row.page or 0


def _normalised(text: str) -> str:
    """Comparable text: parser markup removed, whitespace collapsed, trimmed, case kept."""
    without_tags = _PARSER_INLINE_TAGS.sub("", _PARSER_LINE_BREAK.sub(" ", text))
    return _WHITESPACE.sub(" ", _PARSER_EMPHASIS.sub("", without_tags)).strip()


def _comparable(text: str) -> str:
    """`_normalised`, case-folded. For judging sameness, never for storing a quote."""
    return _normalised(text).casefold()
