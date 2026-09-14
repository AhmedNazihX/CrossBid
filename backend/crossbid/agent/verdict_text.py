"""S3.4.1 — the words a verdict is explained in. Data, not a model call.

The scorer decides by rule (`agent/scoring.py`); this module renders that decision as
prose in the bidder's language and tone. **No model is involved, deliberately.** A verdict
whose wording came from a model would be a model's opinion arriving one field later than
the one the rules engine refused it, and the same sentence would come back differently on
every run — which is exactly what makes a `live` recall measurement so expensive to read
(ADR-0021). Sentences are format strings; the rules engine supplies the numbers.

Three decisions.

**1. The table is keyed by `(language, tone)`, all nine entries written out.** Splitting it
into "language chooses the words, tone chooses which parts are printed" was tried on paper
and does not survive contact with the brief tone: `Kein Angebot.` is not the plain headline
with clauses removed, it is a different sentence. Nine flat entries are greppable, and
`test_verdict_text.py` asserts that every `(language, tone)` pair exists and that every
placeholder in every one of them resolves — which a clever derivation would not make
checkable.

**2. `brief` prints the headline and nothing else.** Every other field defaults to `""`,
and an empty field is skipped rather than rendered blank, so a brief book is six lines.

**3. Thousands are grouped the way the language groups them.** `3,000,000 EUR` rendered
into German prose reads as three point zero: the comma is a decimal separator there. So the
separator is per language — `.` for German, a space for French, `,` for English — and the
grouping happens here rather than in the scorer, because it is a fact about the language
and not about the money.

An unsupported language falls back to English rather than failing: a bid that reached a
verdict must not be lost over a locale nobody wrote a sentence for. `de-AT` matches `de` on
its primary subtag, which is what BCP 47 means by one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from crossbid.models.company import Tone
from crossbid.models.verdict import Decision, Gap, GapSeverity

FALLBACK_LANGUAGE: Final = "en"
"""Used when the bidder's language has no phrasebook. See the module docstring."""

MAX_LISTED_GAPS: Final = 5
"""Gaps named in the prose. `Verdict.gaps` still carries all of them — the workspace lists
the full set, and a rationale that printed 135 bullets would be read by nobody."""

BULLET: Final = "\n\N{EN DASH} "
"""The list marker. Spelled by name so ruff's ambiguous-character rule (RUF001) is
answered rather than silenced: an en dash here is deliberate typography, not a typo for a
hyphen."""

GROUP_SEPARATORS: Final[Mapping[str, str]] = {"de": ".", "en": ",", "fr": " "}
"""Thousands separator per language; see decision 3. Keyed by primary subtag."""


@dataclass(frozen=True, slots=True)
class Phrasebook:
    """One language in one tone. Every field but `headline` may be empty and then skipped."""

    headline: Mapping[Decision, str]
    """Placeholders: `{blocking}`, `{open_items}`, `{supported}`, `{total}`, `{partial}`."""

    counts: str = ""
    blocking_lead: str = ""
    open_lead: str = ""
    more: str = ""
    """`{rest}` — how many gaps were not printed."""

    shortfall: str = ""
    """`{required}` and `{actual}`, appended to a bullet when both are known."""

    required_only: str = ""
    """`{required}` alone, for a gap the company profile cannot answer."""


# ------------------------------------------------------------------------- the phrasebooks

_DE_PLAIN: Final = Phrasebook(
    headline={
        Decision.GO: "Dieses Angebot kann abgegeben werden.",
        Decision.CONDITIONAL: "Dieses Angebot ist mit Auflagen möglich.",
        Decision.NO_GO: "Dieses Angebot wird nicht empfohlen.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "Die Unterlagen reichen für eine Empfehlung nicht aus."
        ),
    },
    counts="{supported} von {total} Pflichtanforderungen sind belegt.",
    blocking_lead="{blocking} Anforderung(en) blockieren das Angebot:",
    open_lead="{open_items} Anforderung(en) sind noch offen:",
    more="… und {rest} weitere.",
    shortfall=" (gefordert {required}, erfasst {actual})",
    required_only=" (gefordert {required})",
)

_DE_FORMAL: Final = Phrasebook(
    headline={
        Decision.GO: "Die Teilnahme an diesem Vergabeverfahren wird empfohlen.",
        Decision.CONDITIONAL: (
            "Die Teilnahme wird vorbehaltlich der nachstehenden Auflagen empfohlen."
        ),
        Decision.NO_GO: "Von einer Teilnahme an diesem Vergabeverfahren wird abgeraten.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "Auf Grundlage der vorliegenden Unterlagen kann keine Empfehlung ausgesprochen "
            "werden."
        ),
    },
    counts="Von {total} Pflichtanforderungen sind {supported} nachgewiesen.",
    blocking_lead="Folgende {blocking} Anforderung(en) stehen einer Teilnahme entgegen:",
    open_lead="Folgende {open_items} Anforderung(en) bedürfen noch eines Nachweises:",
    more="… sowie {rest} weitere.",
    shortfall=" (gefordert: {required}; erfasst: {actual})",
    required_only=" (gefordert: {required})",
)

_DE_BRIEF: Final = Phrasebook(
    headline={
        Decision.GO: "Angebot möglich. {supported}/{total} belegt.",
        Decision.CONDITIONAL: "Angebot mit Auflagen. {open_items} offen.",
        Decision.NO_GO: "Kein Angebot. {blocking} blockierende Lücken.",
        Decision.INSUFFICIENT_EVIDENCE: "Keine Empfehlung. {partial} Anforderungen ungeklärt.",
    }
)

_EN_PLAIN: Final = Phrasebook(
    headline={
        Decision.GO: "This bid can be submitted.",
        Decision.CONDITIONAL: "This bid is possible with open items.",
        Decision.NO_GO: "This bid is not recommended.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "The documents do not settle enough requirements for a recommendation."
        ),
    },
    counts="{supported} of {total} mandatory requirements are supported.",
    blocking_lead="{blocking} requirement(s) block this bid:",
    open_lead="{open_items} requirement(s) still need evidence:",
    more="… and {rest} more.",
    shortfall=" (required {required}, recorded {actual})",
    required_only=" (required {required})",
)

_EN_FORMAL: Final = Phrasebook(
    headline={
        Decision.GO: "Participation in this procurement procedure is recommended.",
        Decision.CONDITIONAL: (
            "Participation is recommended subject to the open items set out below."
        ),
        Decision.NO_GO: "Participation in this procurement procedure is not advised.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "On the evidence available, no recommendation can be made."
        ),
    },
    counts="Of {total} mandatory requirements, {supported} are supported by evidence.",
    blocking_lead="The following {blocking} requirement(s) preclude participation:",
    open_lead="The following {open_items} requirement(s) still require evidence:",
    more="… together with {rest} further requirement(s).",
    shortfall=" (required: {required}; recorded: {actual})",
    required_only=" (required: {required})",
)

_EN_BRIEF: Final = Phrasebook(
    headline={
        Decision.GO: "Go. {supported}/{total} supported.",
        Decision.CONDITIONAL: "Conditional. {open_items} open.",
        Decision.NO_GO: "No go. {blocking} blocking gap(s).",
        Decision.INSUFFICIENT_EVIDENCE: (
            "No recommendation. {partial} requirement(s) unsettled."
        ),
    }
)

_FR_PLAIN: Final = Phrasebook(
    headline={
        Decision.GO: "Cette offre peut être déposée.",
        Decision.CONDITIONAL: "Cette offre est possible sous réserve des points ouverts.",
        Decision.NO_GO: "Cette offre n'est pas recommandée.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "Les pièces disponibles ne permettent pas de formuler une recommandation."
        ),
    },
    counts="{supported} exigences obligatoires sur {total} sont justifiées.",
    blocking_lead="{blocking} exigence(s) bloquent cette offre :",
    open_lead="{open_items} exigence(s) restent à justifier :",
    more="… et {rest} autre(s).",
    shortfall=" (exigé {required}, constaté {actual})",
    required_only=" (exigé {required})",
)

_FR_FORMAL: Final = Phrasebook(
    headline={
        Decision.GO: "La participation à cette procédure est recommandée.",
        Decision.CONDITIONAL: (
            "La participation est recommandée sous réserve des points ci-dessous."
        ),
        Decision.NO_GO: "La participation à cette procédure est déconseillée.",
        Decision.INSUFFICIENT_EVIDENCE: (
            "En l'état des pièces disponibles, aucune recommandation ne peut être formulée."
        ),
    },
    counts="Sur {total} exigences obligatoires, {supported} sont justifiées.",
    blocking_lead="Les {blocking} exigence(s) suivantes font obstacle à la participation :",
    open_lead="Les {open_items} exigence(s) suivantes restent à justifier :",
    more="… ainsi que {rest} autre(s).",
    shortfall=" (exigé : {required} ; constaté : {actual})",
    required_only=" (exigé : {required})",
)

_FR_BRIEF: Final = Phrasebook(
    headline={
        Decision.GO: "Offre possible. {supported}/{total} justifiées.",
        Decision.CONDITIONAL: "Offre sous réserve. {open_items} point(s) ouvert(s).",
        Decision.NO_GO: "Pas d'offre. {blocking} blocage(s).",
        Decision.INSUFFICIENT_EVIDENCE: (
            "Aucune recommandation. {partial} exigence(s) non tranchées."
        ),
    }
)

PHRASEBOOKS: Final[Mapping[tuple[str, Tone], Phrasebook]] = {
    ("de", Tone.PLAIN): _DE_PLAIN,
    ("de", Tone.FORMAL): _DE_FORMAL,
    ("de", Tone.BRIEF): _DE_BRIEF,
    ("en", Tone.PLAIN): _EN_PLAIN,
    ("en", Tone.FORMAL): _EN_FORMAL,
    ("en", Tone.BRIEF): _EN_BRIEF,
    ("fr", Tone.PLAIN): _FR_PLAIN,
    ("fr", Tone.FORMAL): _FR_FORMAL,
    ("fr", Tone.BRIEF): _FR_BRIEF,
}

SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset(
    language for language, _tone in PHRASEBOOKS
)


# ----------------------------------------------------------------------------- rendering


def primary_subtag(language: str) -> str:
    """`de-AT` → `de`. BCP 47's own definition of the language a tag names."""
    return language.strip().lower().partition("-")[0]


def phrasebook_for(language: str, tone: Tone) -> Phrasebook:
    """The book for this language and tone, falling back to English. See the module."""
    subtag = primary_subtag(language)
    if subtag not in SUPPORTED_LANGUAGES:
        subtag = FALLBACK_LANGUAGE
    return PHRASEBOOKS[(subtag, tone)]


def group_digits(value: float, language: str) -> str:
    """`3000000` → `3.000.000` in German, `3 000 000` in French, `3,000,000` in English.

    Whole numbers only: every `Threshold` the golden set produced is one, and a scorer that
    printed `28.5 FTE` against a headcount minimum would be inventing precision the tender
    did not ask for.
    """
    separator = GROUP_SEPARATORS.get(primary_subtag(language), GROUP_SEPARATORS["en"])
    return f"{round(value):,}".replace(",", separator)


def rationale(
    decision: Decision,
    gaps: Sequence[Gap],
    *,
    language: str,
    tone: Tone,
    mandatory_total: int,
    mandatory_supported: int,
    partially_supported_rows: int,
) -> str:
    """The explanation the bidder reads, in their language and tone.

    Built from the decision and the counts the rules engine already computed, so the prose
    cannot disagree with the verdict it explains: there is no second judgement here, only
    a rendering of the first.
    """
    book = phrasebook_for(language, tone)
    blocking = [gap for gap in gaps if gap.severity is GapSeverity.BLOCKING]
    open_items = [gap for gap in gaps if gap.severity is GapSeverity.OPEN_ITEM]
    numbers = {
        "blocking": len(blocking),
        "open_items": len(open_items),
        "supported": mandatory_supported,
        "total": mandatory_total,
        "partial": partially_supported_rows,
    }

    parts = [book.headline[decision].format(**numbers)]
    if book.counts and mandatory_total:
        parts.append(book.counts.format(**numbers))
    parts.extend(_gap_list(book, blocking, book.blocking_lead, numbers))
    parts.extend(_gap_list(book, open_items, book.open_lead, numbers))
    return "\n\n".join(parts)


def _gap_list(
    book: Phrasebook, gaps: Sequence[Gap], lead: str, numbers: Mapping[str, int]
) -> list[str]:
    """One block: the lead sentence, up to `MAX_LISTED_GAPS` bullets, and what was left out.

    Returns an empty list — not a blank paragraph — when this tone prints no list or when
    there is nothing to list, so `"\\n\\n".join` never produces a gap in the prose.
    """
    if not lead or not gaps:
        return []
    shown = gaps[:MAX_LISTED_GAPS]
    lines = [lead.format(**numbers)]
    lines.extend(BULLET + _bullet(book, gap) for gap in shown)
    rest = len(gaps) - len(shown)
    if rest and book.more:
        # A plain newline, not a bullet: "and 35 more" is a note about the list, not a
        # thirty-sixth item in it, and a reader counting bullets should count gaps.
        lines.append("\n" + book.more.format(rest=rest))
    return ["".join(lines)]


def _bullet(book: Phrasebook, gap: Gap) -> str:
    """A gap's own line: what is missing, and the numbers when the scorer knew them.

    `required` and `actual` arrive already grouped for the language (`group_digits`), so
    nothing here has to know which language it is rendering."""
    if gap.required and gap.actual:
        return gap.summary + book.shortfall.format(required=gap.required, actual=gap.actual)
    if gap.required:
        return gap.summary + book.required_only.format(required=gap.required)
    return gap.summary
