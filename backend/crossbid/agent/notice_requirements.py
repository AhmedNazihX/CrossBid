"""S3.2.2 — the buyer's own structured notice fields as `Requirement`s, decided by rule.

The second path in the system from an input to a matrix row with no model in it, and it
exists for the same reason as the first (`espd_requirements.py`): where the buyer has already
*stated* something in a machine-readable field, asking a model to read it out of prose can
only make the answer worse.

**What TED actually gives, and what it does not.** Three fields matter here and each was
measured rather than assumed (CLAUDE.md, *TED Search API v3*):

* `selection-criterion-description-lot` — the buyer's own selection criteria, in prose, in
  the notice's language. **Populated on only 14-17 % of CPV-72 notices**, and 496 of 600
  English ones carried none. That sparsity is not a disappointment to be worked around; it
  is the measurement the whole upload-the-pack design rests on, because it is what proves
  the notice usually does *not* carry the requirements.
* `submission-language` — which languages a tender may be written in. Always present, and a
  real obligation: a bid submitted in the wrong language is rejected unread.
* `deadline-receipt-tender-date-lot` — a date with an offset and no hour (ADR-0043).

**Why these become requirements at all, rather than fields on the bid.** They are things the
bidder must satisfy, so they belong in the matrix where a reviewer sees them beside
everything else and a verdict can count them. The deadline in particular is a requirement a
bid can fail: it is the one whose failure is total.

**The quote is the buyer's own words, untranslated.** `source_text` is what a reviewer is
shown and what the recall scorer compares, and a machine translation of a legal criterion is
not the criterion (`eval/matching.py` compares `source_text` and never `translation`). The
client resolves these fields in the notice's official language for exactly this reason.

**The citation is the notice, not a page.** A TED notice reaches us as structured JSON, not
as a parsed PDF, so `page` is `None` and `source` is `NOTICE` — the same shape the DUME path
uses, and the database constraint refuses to let the two disagree (migration 0008). The
reviewer follows the citation by opening the notice, which the search screen links to.

**Nothing here is `ecertis_criterion_id`.** A notice states criteria in prose, not as ESPD
UUIDs, and ADR-0007 forbids inferring one from wording: a wrong id is worse than none. Only
a published DUME carries ids nobody had to guess.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Final

from pydantic import ValidationError

from crossbid.agent.nodes.extract_reqs import REQUIREMENT_ID_NAMESPACE
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
)
from crossbid.models.ted import TedNotice

logger = logging.getLogger(__name__)

NOTICE_DOCUMENT_TEMPLATE: Final = "TED notice {publication_number}"
"""What `document_name` reads as. Not a filename, because there is no file: the reviewer
opens the notice on TED, and the publication number is what finds it."""

SUBMISSION_LANGUAGE_TEMPLATE: Final = (
    "The tender may be submitted in: {languages}. A tender in another language is rejected "
    "without being read."
)
"""The one requirement here whose text we write rather than quote.

`submission-language` is a list of codes, not prose — there is no buyer sentence to quote —
so this states the obligation the codes encode. It is marked `source: notice` all the same,
because the *fact* is the buyer's and structured; only the sentence around it is ours."""

DEADLINE_KEY: Final = "deadline"
SUBMISSION_LANGUAGE_KEY: Final = "submission_languages"
"""Discriminators for the two rows whose text is ours rather than the buyer's.

A criterion row keys on the buyer's own sentence, which is what makes it unique within a
notice. These two have no sentence to key on -- there is exactly one of each per notice --
so they key on what they are.
"""

DEADLINE_TEMPLATE: Final = (
    "Tenders must be received by {date}. TED publishes the date and the buyer's UTC offset "
    "({offset}) and no time of day; the hour is in the notice itself."
)
"""Says what is known and what is not. A deadline rendered as a timestamp would invent an
hour nobody published (ADR-0043), and this is the row a reviewer reads to decide whether the
bid is worth starting at all."""


def requirements_from_notice(notice: TedNotice, *, bid_id: str) -> tuple[Requirement, ...]:
    """`notice`'s stated facts as requirements of `bid_id`, in the order a bidder meets them.

    Empty is the common answer and not a failure: most notices state no selection criteria,
    and one with no deadline and no submission language is a notice with nothing structured
    to contribute. The caller adds what comes back and carries on to extraction either way.
    """
    document_name = NOTICE_DOCUMENT_TEMPLATE.format(
        publication_number=notice.publication_number
    )
    language = _source_language(notice)
    rows: list[Requirement] = []

    deadline = _deadline_requirement(notice, bid_id, document_name, language)
    if deadline is not None:
        rows.append(deadline)

    languages = _submission_language_requirement(notice, bid_id, document_name, language)
    if languages is not None:
        rows.append(languages)

    rows.extend(
        row
        for row in (
            _criterion_requirement(text, bid_id, document_name, language)
            for text in notice.selection_criteria
        )
        if row is not None
    )
    return tuple(rows)


def _deadline_requirement(
    notice: TedNotice, bid_id: str, document_name: str, language: str
) -> Requirement | None:
    """The submission deadline.

    `FORMAL` and `DOCUMENT_SUBMISSION`: no fact about the company settles it. It is met by
    acting, so the checking loop would spend tool calls to reach `unclear` — the failure
    SP.1 measured (ADR-0003) — and the reviewer is the only one who can say it was met.
    """
    if notice.deadline is None:
        return None
    # Bound before the closure: the factory is called later, and pyright cannot carry the
    # narrowing above through a lambda that reads `notice.deadline` again.
    deadline = notice.deadline
    offset = notice.deadline_utc_offset_minutes
    return _guarded(
        lambda: Requirement(
            id=_requirement_id(bid_id, document_name, DEADLINE_KEY),
            bid_id=bid_id,
            category=RequirementCategory.FORMAL,
            kind=RequirementKind.MANDATORY,
            stage=RequirementStage.BID_ELIGIBILITY,
            checkable=Checkability.DOCUMENT_SUBMISSION,
            source=RequirementSource.NOTICE,
            source_text=DEADLINE_TEMPLATE.format(
                date=deadline.isoformat(), offset=_offset_text(offset)
            ),
            source_lang=language,
            document_name=document_name,
            page=None,
            deadline=deadline,
        )
    )


def _submission_language_requirement(
    notice: TedNotice, bid_id: str, document_name: str, language: str
) -> Requirement | None:
    if not notice.submission_languages:
        return None
    return _guarded(
        lambda: Requirement(
            id=_requirement_id(bid_id, document_name, SUBMISSION_LANGUAGE_KEY),
            bid_id=bid_id,
            category=RequirementCategory.FORMAL,
            kind=RequirementKind.MANDATORY,
            stage=RequirementStage.BID_ELIGIBILITY,
            checkable=Checkability.DOCUMENT_SUBMISSION,
            source=RequirementSource.NOTICE,
            source_text=SUBMISSION_LANGUAGE_TEMPLATE.format(
                languages=", ".join(notice.submission_languages)
            ),
            source_lang=language,
            document_name=document_name,
            page=None,
        )
    )


def _criterion_requirement(
    text: str, bid_id: str, document_name: str, language: str
) -> Requirement | None:
    """One stated selection criterion, quoted, or `None` when it cannot be one.

    `COMPANY_PROPERTY`: a selection criterion is by definition a fact about the bidder that
    their evidence pack can settle, which is the same line `espd_requirements` draws between
    selection criteria and exclusion grounds. The category is `OTHER` because the notice
    states the criterion in prose and nothing here classifies prose — that is `extract_reqs`'
    job on the pack, and guessing a category here would put a wrong label on a row a
    reviewer trusts.
    """
    return _guarded(
        lambda: Requirement(
            id=_requirement_id(bid_id, document_name, text),
            bid_id=bid_id,
            category=RequirementCategory.OTHER,
            kind=RequirementKind.MANDATORY,
            stage=RequirementStage.BID_ELIGIBILITY,
            checkable=Checkability.COMPANY_PROPERTY,
            source=RequirementSource.NOTICE,
            source_text=text,
            source_lang=language,
            document_name=document_name,
            page=None,
        )
    )


def _requirement_id(bid_id: str, document_name: str, discriminator: str) -> str:
    """A `uuid5` over bid, notice and what the row is about -- deterministic, so a re-run
    upserts instead of doubling.

    `readmodel/requirements.py` states the contract these rows have to hold: a requirement's
    id is derived, not minted, so that `parse_docs` running twice -- after a crash, or when a
    resumed run replays the superstep -- writes the same rows again rather than a second set.
    Every other path into that table already did this (`espd_requirements._requirement_id`,
    `extract_reqs`' bid/file/page/quote key) and the notice path was the one exception, so a
    `uuid4` here was a doubled deadline row waiting for the first badly-timed restart.

    The same namespace as the other two, because these rows share one primary key and two id
    spaces would be two id spaces nobody asked for. The key cannot collide with an extracted
    row's, which carries a page number a notice row has no equivalent of.
    """
    key = "\x1f".join((bid_id, document_name, discriminator))
    return str(uuid.uuid5(REQUIREMENT_ID_NAMESPACE, key))


def _guarded(build: Callable[[], Requirement]) -> Requirement | None:
    """`build()`, or `None` when the buyer's own field cannot be a requirement.

    TED does not cap `selection-criterion-description-lot`, and `Requirement.source_text`
    caps a quote at `MAX_QUOTE_CHARS`. Constructing inline, one verbose buyer therefore
    raised a `ValidationError` out of `parse_docs`, which the stage wrapper turned into a
    failed bid: a pack the bidder had already uploaded, lost to somebody else's prose.

    Dropping the row is the right trade. The notice is a bonus source -- most notices state
    no criteria at all (see the module docstring) and extraction still reads the pack -- so
    losing one row costs a row, while raising costs the run. `espd_requirements` draws the
    same line for the same reason, one criterion at a time.

    A factory rather than a mapping of fields, so the constructor call stays where pyright
    can see it: a wrong field name here has to stay a type error, not a run-time surprise.
    Only the failing field names are logged, never the buyer's text, which could be anything.
    """
    try:
        return build()
    except ValidationError as exc:
        named = sorted({".".join(str(part) for part in e["loc"]) for e in exc.errors()})
        logger.warning(
            "Notice requirement dropped: it cannot satisfy the requirement contract (%s)",
            ", ".join(named),
        )
        return None


def _source_language(notice: TedNotice) -> str:
    """ISO 639-1 from TED's 639-3, because `Requirement.source_lang` is two letters.

    Unknown falls back to the first two characters, which is right far more often than it is
    wrong across the 24 EU languages and is never worse than refusing the row.
    """
    first = (notice.official_languages[0] if notice.official_languages else "").lower()
    return THREE_TO_TWO_LETTER.get(first, first[:2] or "en")


def _offset_text(minutes: int | None) -> str:
    if minutes is None:
        return "not stated"
    sign = "-" if minutes < 0 else "+"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


THREE_TO_TWO_LETTER: Final[dict[str, str]] = {
    "bul": "bg",
    "ces": "cs",
    "dan": "da",
    "deu": "de",
    "ell": "el",
    "eng": "en",
    "est": "et",
    "fin": "fi",
    "fra": "fr",
    "gle": "ga",
    "hrv": "hr",
    "hun": "hu",
    "ita": "it",
    "lav": "lv",
    "lit": "lt",
    "mlt": "mt",
    "nld": "nl",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "slk": "sk",
    "slv": "sl",
    "spa": "es",
    "swe": "sv",
}
"""The 24 official EU languages, TED's codes against the two-letter ones the rest of the
app uses. `ell`/`ell` for Greek, not `gre`: TED uses the ISO 639-2/T set."""
