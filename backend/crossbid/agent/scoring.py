"""S3.4.1 — the scorer: requirements plus matrix rows become a go/no-go, by rule only.

Pure. No model, no database, no clock, no I/O — `score` is a function of four arguments and
`tests/unit/test_scoring.py` is its specification. That is the story's whole point: the
recommendation a bidder acts on must be re-derivable from the matrix they can see, and a
decision that came from a model could not be. `agent/verdict_text.py` renders the result as
prose; it makes no judgements of its own.

Five rules, and each exists because the plan or a fixture forced it.

**1. Only `bid_eligibility` counts.** SP.1 extracted 579 "mandatory" requirements from one
tender because the AGB, EVB-IT and the framework agreement are all phrased as obligations
(ADR-0003). A `contract_performance` row is a real obligation and has nothing to do with
whether you may bid, so it is not scored at all — not as a gap, not in a denominator. The
DE golden key deliberately keeps `contract_performance` rows in `requirements` so the
filter can be scored in both directions; anything that scores must apply it.

**2. `unsupported` on a mandatory row is fatal, and so is `unsupported` on any exclusion
ground.** An exclusion ground is inverted — the row is `supported` when the bidder can
prove they are *not* caught by it — so `unsupported` there means the evidence is against
them. Its `kind` is not consulted: an exclusion ground marked `optional` by an extractor
is an extraction defect, and reading it as a softer requirement would let that defect
decide a bid.

**3. A mandatory requirement with no row is an open item, never a pass.** Checking is
total (`check_loop.check_requirement` never raises), so a missing row means a lane never
ran — a resumed run, a cancelled shutdown. Treating "not checked" as "fine" is the one
failure mode a go/no-go must not have.

**4. `insufficient_evidence` is the agent declining to judge, and the test for it is that
it can point at nothing.** Not a proportion: a threshold like "fewer than half the rows"
would be a number nobody in the plan chose. If not one mandatory requirement came back
`supported`, there is nothing to build a recommendation on — and that one sentence covers
every shape of it: an empty matrix, a matrix nobody checked, a matrix of nothing but
`partially_supported`, and a matrix whose mandatory rows the model all read as
`not_applicable`. Each of those was a different wrong answer before it was written this way.

**5. A gap names the numbers when the profile can answer them, and stays silent when it
cannot.** `required` comes off the requirement's own `Threshold`; `actual` comes off the
bidder's typed profile facts, and only where the comparison is honest — an `at_least` FTE
minimum against the recorded FTE, an `at_least` turnover against the most recent year *in
the same currency*. Converting currencies is `currency_convert`'s job and a scorer that
guessed at one would be inventing the bidder's answer. No weighted score is produced: a
buyer's points scale is published in the tender and nothing in `Requirement` carries it, so
`Verdict.score` stays `None` until a story extracts one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from crossbid.agent.verdict_text import group_digits, rationale
from crossbid.models.company import CompanyProfile, Tone
from crossbid.models.matrix import MatrixRow, RowStatus
from crossbid.models.requirement import (
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.verdict import Decision, Gap, GapSeverity, Verdict

MAX_GAP_SUMMARY_CHARS: Final = 180
"""How much of a requirement a gap quotes. A gap is a prompt to act, not the clause itself —
the workspace links the row, which carries the whole quote and its page."""

ELLIPSIS: Final = "…"

BLOCKING_STATUS: Final = RowStatus.UNSUPPORTED
"""The one row status that can block a bid. `partially_supported` is the honest "ask the
reviewer" and never decides against the bidder on its own."""

SETTLED_STATUSES: Final[frozenset[RowStatus]] = frozenset(
    {RowStatus.SUPPORTED, RowStatus.NOT_APPLICABLE}
)
"""Statuses that need nothing further from anyone. `not_applicable` settles a row without
supporting it, so it closes a gap but never counts towards `mandatory_supported`."""

COMPARABLE_COMPARATORS: Final[frozenset[ThresholdComparator]] = frozenset(
    {ThresholdComparator.AT_LEAST}
)
"""Comparators for which a profile fact is a shortfall the bidder can read. An `at_most` or
a `max_age` bound is about something the profile does not record, so naming a number beside
it would invite the wrong comparison (rule 5)."""

FTE_UNITS: Final[frozenset[ThresholdUnit]] = frozenset({ThresholdUnit.FTE})


def score(
    requirements: Sequence[Requirement],
    rows: Sequence[MatrixRow],
    *,
    language: str,
    tone: Tone = Tone.PLAIN,
    profile: CompanyProfile | None = None,
) -> Verdict:
    """The go/no-go for one bid, with every reason behind it. See the module for the rules.

    `profile` is optional and its absence costs only the `actual` half of a threshold gap:
    a company row that cannot be read must not lose the bidder their verdict, the same
    choice `plan_checks` makes about the bidder's country.
    """
    scored = [req for req in requirements if req.stage is RequirementStage.BID_ELIGIBILITY]
    by_requirement = {row.requirement_id: row for row in rows}

    gaps = _gaps(scored, by_requirement, language=language, profile=profile)
    mandatory = [req for req in scored if req.kind is RequirementKind.MANDATORY]
    supported = sum(
        1 for req in mandatory if _status_of(by_requirement, req) is RowStatus.SUPPORTED
    )
    partial = sum(
        1 for req in scored if _status_of(by_requirement, req) is RowStatus.PARTIALLY_SUPPORTED
    )
    decision = _decide(gaps, partially_supported=partial, supported_mandatory=supported)
    return Verdict(
        decision=decision,
        gaps=tuple(gaps),
        rationale=rationale(
            decision,
            gaps,
            language=language,
            tone=tone,
            mandatory_total=len(mandatory),
            mandatory_supported=supported,
            partially_supported_rows=partial,
        ),
        mandatory_total=len(mandatory),
        mandatory_supported=supported,
        partially_supported_rows=partial,
    )


# ------------------------------------------------------------------------------ the rules


def _decide(
    gaps: Sequence[Gap], *, partially_supported: int, supported_mandatory: int
) -> Decision:
    """The decision, in the order the criteria are written. Nothing else decides.

    The order is the point. A blocking gap outranks everything: it is a definite answer, and
    a bid with one is `no_go` however little else was established. Below that, **the agent
    needs something of its own to stand on** — one mandatory requirement it can say is
    supported — or it declines. Only then do the open items decide between `go` and
    `conditional`.

    `supported_mandatory` and not "settled": counting `not_applicable` towards the gate let
    three mandatory rows the model read as inapplicable produce a `go` whose own rationale
    said `0 of 3 supported`, and let five mandatory requirements *nobody had checked* produce
    `conditional` — the encouraging answer for the worse state, because an empty matrix
    declined and a never-checked one did not. `not_applicable` still closes a gap; it just
    cannot open a recommendation.
    """
    if any(gap.severity is GapSeverity.BLOCKING for gap in gaps):
        return Decision.NO_GO
    if not supported_mandatory:
        return Decision.INSUFFICIENT_EVIDENCE
    if not gaps and not partially_supported:
        return Decision.GO
    return Decision.CONDITIONAL


def _gaps(
    requirements: Iterable[Requirement],
    rows: Mapping[str, MatrixRow],
    *,
    language: str,
    profile: CompanyProfile | None,
) -> list[Gap]:
    """Every reason the bidder does not yet qualify, blocking ones first.

    Requirement order is preserved inside each severity — but that is the order of the
    `requirements` channel, which is the order the nodes appended in: a published DUME's
    criteria first (`parse_docs`), then extraction's, section by section. The matrix the
    workspace shows is sorted by document and page (`SELECT_MATRIX_ROWS`), so on a pack with
    a DUME the two orders differ and the gaps named in the rationale are not the first rows
    of the list beside it. Stated rather than fixed: sorting here would need the read model's
    ordering rule in a module that has no database, and the gap carries its requirement id.
    """
    found = [
        gap
        for gap in (
            _gap_for(req, rows.get(req.id), language=language, profile=profile)
            for req in requirements
        )
        if gap is not None
    ]
    blocking = [gap for gap in found if gap.severity is GapSeverity.BLOCKING]
    return blocking + [gap for gap in found if gap.severity is GapSeverity.OPEN_ITEM]


def _gap_for(
    requirement: Requirement,
    row: MatrixRow | None,
    *,
    language: str,
    profile: CompanyProfile | None,
) -> Gap | None:
    """This requirement's gap, or `None` when nothing is owed on it."""
    severity = _severity_of(requirement, row)
    if severity is None:
        return None
    required = _required(requirement.threshold, language)
    return Gap(
        requirement_id=requirement.id,
        severity=severity,
        summary=_summary(requirement),
        required=required,
        actual=_actual(requirement.threshold, profile, language) if required else None,
    )


def _severity_of(requirement: Requirement, row: MatrixRow | None) -> GapSeverity | None:
    """How badly this requirement is open, or `None` when it is not. Rules 2 and 3.

    The order of the first two tests is the whole of rule 2 and was wrong once. An exclusion
    ground is read *before* `kind` is consulted, because `kind` is assigned by the extraction
    model and an exclusion ground it labelled `informational` is an extraction defect — one
    that would otherwise let a bidder with evidence against them on an unspent conviction
    score `go` with no gap naming it. Only a requirement that is not an exclusion ground may
    be softened by its kind.
    """
    is_exclusion_ground = requirement.category is RequirementCategory.EXCLUSION_GROUND
    if requirement.kind is RequirementKind.INFORMATIONAL and not is_exclusion_ground:
        return None
    if row is None:
        # Never checked. Rule 3: that is an open item, never a silent pass.
        return GapSeverity.OPEN_ITEM
    if row.status in SETTLED_STATUSES:
        return None
    is_fatal = requirement.kind is RequirementKind.MANDATORY or is_exclusion_ground
    if row.status is BLOCKING_STATUS and is_fatal:
        return GapSeverity.BLOCKING
    return GapSeverity.OPEN_ITEM


def _status_of(rows: Mapping[str, MatrixRow], requirement: Requirement) -> RowStatus | None:
    row = rows.get(requirement.id)
    return None if row is None else row.status


# -------------------------------------------------------------------------- what a gap says


def _summary(requirement: Requirement) -> str:
    """What is missing, in the bidder's language where a translation exists.

    `translation` is the bidder-language rendering extraction produced (S3.2.1); the
    verbatim source quote is the honest fallback, because a gap in the wrong language is
    still actionable and an invented one is not.
    """
    text = (requirement.translation or requirement.source_text).strip()
    if len(text) <= MAX_GAP_SUMMARY_CHARS:
        return text
    return text[: MAX_GAP_SUMMARY_CHARS - 1].rstrip() + ELLIPSIS


def _required(threshold: Threshold | None, language: str) -> str | None:
    """The buyer's number, grouped for the language: `3.000.000 EUR`, `29 FTE`."""
    if threshold is None:
        return None
    amount = group_digits(threshold.value, language)
    if threshold.unit is ThresholdUnit.CURRENCY and threshold.currency:
        return f"{amount} {threshold.currency}"
    unit = "FTE" if threshold.unit in FTE_UNITS else threshold.unit.value
    return f"{amount} {unit}"


def _actual(
    threshold: Threshold | None, profile: CompanyProfile | None, language: str
) -> str | None:
    """The bidder's own figure, or `None` when the profile cannot honestly answer. Rule 5."""
    if threshold is None or profile is None:
        return None
    if threshold.comparator not in COMPARABLE_COMPARATORS:
        return None
    if threshold.unit in FTE_UNITS:
        # The field-of-contract figure first: that is the one tenders ask about, and a
        # company that records both is answering a narrower question with the narrower
        # number. Total FTE is the fallback, not the preference.
        recorded = (
            profile.staff_fte_relevant
            if profile.staff_fte_relevant is not None
            else profile.staff_fte
        )
        return None if recorded is None else f"{group_digits(recorded, language)} FTE"
    if threshold.unit is ThresholdUnit.CURRENCY and threshold.currency:
        return _turnover(profile, threshold.currency, language)
    return None


def _turnover(profile: CompanyProfile, currency: str, language: str) -> str | None:
    """The most recent year recorded in `currency`, or `None`.

    The most recent rather than the lowest of the last three: "actual" in a gap list means
    "what you have", and a bidder reading their newest figure beside the buyer's minimum
    can see the distance. Which years a tender actually asks about is in the requirement's
    own quote, one line above.
    """
    matching = [year for year in profile.turnover if year.currency == currency]
    if not matching:
        return None
    latest = max(matching, key=lambda year: year.year)
    return f"{group_digits(latest.amount, language)} {currency}"
