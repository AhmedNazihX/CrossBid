"""S1.2.1 — searching TED, and turning its answer into something a screen can render.

`POST https://api.ted.europa.eu/v3/notices/search`, documented, public, no key. The expert
query syntax is the part worth reading twice, because most of what this module does is
refuse to build a query TED would reject.

**Every rule here was probed live, not read.** The findings are in `CLAUDE.md` under *TED
Search API v3*; what follows is what they mean for the code.

* **A CPV value is eight digits or nothing.** `IN (72)` is HTTP 400
  `QUERY_UNSUPPORTED_FIELD_VALUE`. The model's pattern refuses it here instead.
* **`IN (...)` takes values separated by spaces and never `OR`** — that is the story's own
  criterion, and `_values` is the single place a list becomes a clause, so there is nowhere
  else for an `OR` to get in. The one value that does not pass through it -- the publication
  number `search_by_publication_number` interpolates -- is shape-checked by `_checked_number`
  instead, because a promise with one exception in it is not a promise.
* **Sorting lives inside the query string**, appended as `SORT BY publication-date DESC`. A
  JSON `"sort"` field is rejected outright (`Unrecognized field "sort"`), and `ASC` is 400 —
  so newest-first is not a preference here, it is the only order TED will serve.
* **Pagination stops at 600.** `limit=100, page=7` is 400 even when `totalNoticeCount` is
  160 000, so the page reports `reachable_total` rather than letting a screen offer a page
  that cannot be fetched.

**Resolving the language-keyed fields is the other half of the job.** TED returns
`notice-title` as a mapping of all 24 EU languages, `buyer-name` as a mapping of language to
a *list*, and `title-proc`/`description-proc` in the source language only. `_in_language`
prefers the bidder's own language, then the notice's official language, then English, then
whatever there is — so a German bidder reads a French tender's title in German **without a
single model call**, which is the cross-border wedge arriving for free.

**A deadline is a date, never a time.** `deadline-receipt-tender-date-lot` is a list with one
entry per lot, each a date with a UTC offset and no hour: across 58 sampled lot deadlines,
zero carried one. The earliest is taken, because that is the one a bidder has to act on, and
the offset is kept beside it as the buyer's wall clock (migration 0007). Inventing midnight
here would put a false deadline on a dashboard countdown.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final

import httpx

from crossbid.http_retry import is_retryable
from crossbid.models.ted import (
    CONTRACT_NOTICE_TYPE,
    MAX_REACHABLE_RESULTS,
    TedNotice,
    TedSearchPage,
    TedSearchQuery,
)

logger = logging.getLogger(__name__)

TED_SEARCH_URL: Final = "https://api.ted.europa.eu/v3/notices/search"
TED_REQUEST_TIMEOUT_S: Final = 20.0
TED_MAX_ATTEMPTS: Final = 2
"""One retry, as the story asks: TED is occasionally slow, never usefully hammered."""

SORT_CLAUSE: Final = "SORT BY publication-date DESC"

_PUBLICATION_NUMBER: Final = re.compile(r"\d{1,9}-\d{4}")
"""A TED publication number: digits, a hyphen, a year. `618320-2026`."""

_DATE_WITH_OFFSET: Final = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})(?P<offset>Z|[+-]\d{2}:\d{2})?$"
)
"""The shape TED publishes a deadline in. See `_date_and_offset` for why it is not
`datetime.fromisoformat`."""

FIELDS: Final[tuple[str, ...]] = (
    "publication-number",
    "notice-title",
    "title-proc",
    "description-proc",
    "buyer-name",
    "deadline-receipt-tender-date-lot",
    "selection-criterion-description-lot",
    "official-language",
    "submission-language",
    "classification-cpv",
    "document-url-lot",
    "links",
    "publication-date",
)

ENGLISH: Final = "eng"

ALPHA2_TO_ALPHA3: Final[Mapping[str, str]] = {
    "at": "AUT",
    "be": "BEL",
    "bg": "BGR",
    "hr": "HRV",
    "cy": "CYP",
    "cz": "CZE",
    "dk": "DNK",
    "ee": "EST",
    "fi": "FIN",
    "fr": "FRA",
    "de": "DEU",
    "gr": "GRC",
    "hu": "HUN",
    "ie": "IRL",
    "it": "ITA",
    "lv": "LVA",
    "lt": "LTU",
    "lu": "LUX",
    "mt": "MLT",
    "nl": "NLD",
    "pl": "POL",
    "pt": "PRT",
    "ro": "ROU",
    "sk": "SVK",
    "si": "SVN",
    "es": "ESP",
    "se": "SWE",
}
"""`place-of-performance` speaks alpha-3; the company profile and every screen speak alpha-2
(`companies.country`). One mapping, at the boundary, rather than two vocabularies inside."""

ALPHA2_TO_ALPHA3_LANGUAGE: Final[Mapping[str, str]] = {
    "de": "deu",
    "en": ENGLISH,
    "fr": "fra",
    "nl": "nld",
    "pl": "pol",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "sv": "swe",
    "da": "dan",
    "fi": "fin",
    "cs": "ces",
    "el": "ell",
    "hu": "hun",
    "ro": "ron",
    "bg": "bul",
    "hr": "hrv",
    "sk": "slk",
    "sl": "slv",
    "et": "est",
    "lv": "lav",
    "lt": "lit",
    "mt": "mlt",
    "ga": "gle",
}
"""The bidder's BCP 47 language against TED's ISO 639-3 keys. Missing is not an error: the
fallback chain below is what an unmapped language falls through to."""


class TedUnavailableError(RuntimeError):
    """TED could not be reached, or answered with something unusable. The typed error the
    story asks for — a router turns it into 503, never into an empty result set, because
    "no tenders match" and "TED is down" are different answers to a bidder."""


class TedSearchClient:
    """Searches TED. Construct with an `httpx.Client`; a test passes a `MockTransport`."""

    def __init__(self, http: httpx.Client, *, max_attempts: int = TED_MAX_ATTEMPTS) -> None:
        self._http = http
        self._max_attempts = max_attempts

    def search(
        self,
        query: TedSearchQuery,
        *,
        language: str | None = None,
        query_override: str | None = None,
    ) -> TedSearchPage:
        """One page of notices, with every language-keyed field resolved for `language`.

        `query_override` replaces the built expert query outright, for the one caller that
        needs a clause `TedSearchQuery` cannot express — a lookup by publication number.
        It is a seam and not a general escape hatch: everything else goes through
        `build_query`, which is where the rules about `OR`, sorting and CPV length live.
        """
        payload = {
            "query": build_query(query) if query_override is None else query_override,
            "fields": list(FIELDS),
            "limit": query.limit,
            "page": query.page,
        }
        body = self._post(payload)
        preferred = ALPHA2_TO_ALPHA3_LANGUAGE.get((language or "").lower())
        raw_notices = body.get("notices")
        notices = tuple(
            _notice(entry, preferred)
            for entry in (raw_notices if isinstance(raw_notices, list) else ())
            if isinstance(entry, Mapping)
        )
        total = int(body.get("totalNoticeCount") or 0)
        return TedSearchPage(
            notices=notices,
            total=total,
            page=query.page,
            limit=query.limit,
            reachable_total=min(total, MAX_REACHABLE_RESULTS),
        )

    def search_by_publication_number(
        self, publication_number: str, *, language: str | None = None
    ) -> TedNotice | None:
        """One notice by its TED publication number, or `None` if TED has no such notice.

        A search rather than a fetch, because the v3 API has no by-id endpoint —
        `publication-number IN (629621-2026)` answers with exactly one match (probed
        2026-09-14). The notice-type filter is lifted: the caller already has a specific
        notice and filtering it out because it is an award notice would be a confusing
        nothing.
        """
        page = self.search(
            TedSearchQuery(
                contract_notices_only=False, limit=1, keyword=None, cpv=(), countries=()
            ),
            language=language,
            query_override=f"publication-number IN ({_checked_number(publication_number)})",
        )
        return page.notices[0] if page.notices else None

    def _post(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._http.post(TED_SEARCH_URL, json=dict(payload))
                response.raise_for_status()
                decoded = response.json()
            except httpx.HTTPError as error:
                if not is_retryable(error):
                    # M21: this used to be retried like any other failure. A 400 is TED
                    # saying the *query* is wrong — `IN (72)` rather than `IN (72000000)`,
                    # or an expert-syntax slip — and sending it again only makes the bidder
                    # wait twice as long to be told the same thing.
                    raise TedUnavailableError(
                        f"TED refused the search and will refuse it again: {error}"
                    ) from error
                last_error = error
                logger.warning("TED search attempt %s failed: %s", attempt, error)
            except ValueError as error:  # not JSON at all
                raise TedUnavailableError(
                    "TED answered with something that is not JSON"
                ) from error
            else:
                if isinstance(decoded, Mapping):
                    return decoded
                raise TedUnavailableError("TED answered with a body that is not an object")
        raise TedUnavailableError(
            f"TED search failed after {self._max_attempts} attempts: {last_error}"
        ) from last_error


# ------------------------------------------------------------------------- query building


def build_query(query: TedSearchQuery) -> str:
    """The expert-query string. Every clause is an `IN (...)` or an `FT ~ (...)`, joined by
    `AND`, and sorted — the only order TED serves."""
    clauses: list[str] = []
    if query.cpv:
        clauses.append(f"classification-cpv IN ({_values(query.cpv)})")
    if query.countries:
        countries = tuple(
            ALPHA2_TO_ALPHA3[code] for code in query.countries if code in ALPHA2_TO_ALPHA3
        )
        if countries:
            clauses.append(f"place-of-performance IN ({_values(countries)})")
    if query.contract_notices_only:
        clauses.append(f"notice-type IN ({CONTRACT_NOTICE_TYPE})")
    keyword = (query.keyword or "").strip()
    if keyword:
        clauses.append(f'FT ~ ("{_escaped(keyword)}")')
    # The sort is appended with a space, never joined with `AND`: `... AND SORT BY ...` is
    # `QUERY_SYNTAX_ERROR ... mismatched input 'SORT'`. It is not a clause, it is a suffix.
    return f"{' AND '.join(clauses)} {SORT_CLAUSE}".strip() if clauses else SORT_CLAUSE


def _checked_number(publication_number: str) -> str:
    """The number, or a refusal. The one guard on the one call that builds its own clause.

    `search_by_publication_number` is the only caller that passes `query_override`, so it is
    the only place a value skips `_values` -- this module's promise that there is nowhere
    else for an `OR` to get in. The value reaching it began life in a request body, and a
    public method may not assume its caller was careful: unvalidated, a crafted number could
    close the predicate and open another, and the notice whose deadline `parse_docs` then
    writes onto the bid would not be the notice the bidder chose.

    `TedUnavailableError` rather than a new type: every caller already handles it, and to a
    caller "TED will not answer this" and "this was never a question TED could answer" lead
    to the same place. The message says which it was.
    """
    if _PUBLICATION_NUMBER.fullmatch(publication_number) is None:
        raise TedUnavailableError(
            f"{publication_number!r} is not a TED publication number; no query was sent"
        )
    return publication_number


def _values(values: Iterable[str]) -> str:
    """Values inside `IN (...)`, separated by spaces.

    **This is the one place a list becomes a clause, and it never emits `OR`** — the story's
    second criterion. TED rejects `OR` inside the parentheses outright, so the failure would
    be a 400 on a query a bidder had no way to see.
    """
    return " ".join(values)


def _escaped(keyword: str) -> str:
    """A quoted phrase, with the quote that would end it removed rather than escaped.

    TED's expert syntax has no documented escape, so a `"` in a keyword cannot be passed
    through safely. Dropping it changes the search slightly; passing it through would either
    400 or, worse, change the meaning of the query around it.
    """
    return keyword.replace('"', " ").strip()


# ---------------------------------------------------------------------- response mapping


def _notice(raw: Mapping[str, Any], preferred: str | None) -> TedNotice:
    official = _codes(raw.get("official-language"))
    fallbacks = (preferred, *(code.lower() for code in official), ENGLISH)
    deadline, offset = _earliest_deadline(raw.get("deadline-receipt-tender-date-lot"))
    raw_links = raw.get("links")
    links: Mapping[str, Any] = raw_links if isinstance(raw_links, Mapping) else {}
    return TedNotice(
        publication_number=str(raw.get("publication-number") or ""),
        title=_in_language(raw.get("notice-title"), fallbacks)
        or _in_language(raw.get("title-proc"), fallbacks)
        or "Untitled notice",
        buyer=_in_language(raw.get("buyer-name"), fallbacks),
        description=_in_language(raw.get("description-proc"), fallbacks),
        deadline=deadline,
        deadline_utc_offset_minutes=offset,
        official_languages=official,
        submission_languages=_codes(raw.get("submission-language")),
        cpv=_unique(raw.get("classification-cpv")),
        # In the notice's own language and never the bidder's: these become requirement
        # *quotes*, and a quote is evidence. `notice-title` may be translated because it is
        # read; a criterion the bidder will be held to must be the buyer's own words.
        selection_criteria=_all_in_language(
            raw.get("selection-criterion-description-lot"),
            tuple(code.lower() for code in official),
        ),
        notice_pdf_url=_notice_pdf(links, official),
        documents_url=_first(raw.get("document-url-lot")),
        published_on=_date_only(_first(raw.get("publication-date"))),
    )


def _in_language(field: object, fallbacks: Sequence[str | None]) -> str | None:
    """One string out of TED's language-keyed mapping, in the first language it has.

    The values are strings for a title and *lists* for a buyer, so both are accepted. A
    plain string is passed through: not every field is keyed, and a caller should not have
    to know which.
    """
    if isinstance(field, str):
        return field.strip() or None
    if not isinstance(field, Mapping):
        return None
    for code in (*fallbacks, *sorted(field)):
        if code is None:
            continue
        value = field.get(code)
        text = value[0] if isinstance(value, list) and value else value
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _all_in_language(field: object, official: Sequence[str]) -> tuple[str, ...]:
    """Every entry of a language-keyed list field, in the source language.

    Unlike `_in_language`, which wants one string a human will read, this wants the whole
    list and wants it untranslated: `selection-criterion-description-lot` maps a language to
    a *list* of criteria, and each becomes a requirement the bidder is measured against.
    English is the last resort rather than the second, because a machine translation of a
    legal criterion is not the criterion.
    """
    if not isinstance(field, Mapping):
        return ()
    for code in (*official, ENGLISH, *sorted(field)):
        value = field.get(code)
        if isinstance(value, list):
            found = tuple(
                text.strip() for text in value if isinstance(text, str) and text.strip()
            )
            if found:
                return found
    return ()


def _earliest_deadline(field: object) -> tuple[date | None, int | None]:
    """The soonest lot deadline, and the offset TED published it with.

    One entry per lot, so a notice with four lots has four dates and the bidder is held to
    the first of them. The offset is carried separately because a `timestamptz` would keep
    the instant and lose the wall clock the buyer wrote (ADR-0030).
    """
    best: tuple[date, int | None] | None = None
    for raw in field if isinstance(field, list) else []:
        parsed = _date_and_offset(raw)
        if parsed is not None and (best is None or parsed[0] < best[0]):
            best = parsed
    return (None, None) if best is None else best


def _date_and_offset(raw: object) -> tuple[date, int | None] | None:
    """`'2026-10-07+02:00'` into a date and 120. `Z` is a real value and means zero.

    **Parsed by hand, because `datetime.fromisoformat` gets this exact shape wrong and does
    it silently.** Given `2026-10-07+02:00` — a date with an offset and no time, which is
    what TED publishes — it returns `datetime(2026, 10, 7, 2, 0)` with **no tzinfo**: the
    offset has been read as a time of day. The date survives by luck and the offset vanishes,
    so `utcoffset()` answers `None` and a buyer's wall clock is lost without any error. The
    regex below is the whole fix; a value that *does* carry a time is news worth having, so
    it falls through to the stdlib rather than being refused.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    match = _DATE_WITH_OFFSET.match(text)
    if match is not None:
        return date.fromisoformat(match["date"]), _offset_minutes(match["offset"])
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("TED sent a deadline this client cannot read: %r", text)
        return None
    logger.info("TED sent a deadline carrying a time of day, which it has not before: %r", text)
    offset = moment.utcoffset()
    return moment.date(), None if offset is None else int(offset.total_seconds() // 60)


def _offset_minutes(offset: str | None) -> int | None:
    """`None` when TED published no offset, `0` for `Z`, and signed minutes otherwise."""
    if offset is None:
        return None
    if offset == "Z":
        return 0
    sign = -1 if offset[0] == "-" else 1
    hours, minutes = (int(part) for part in offset[1:].split(":"))
    return sign * (hours * 60 + minutes)


def _date_only(raw: object) -> date | None:
    parsed = _date_and_offset(raw)
    return None if parsed is None else parsed[0]


def _notice_pdf(links: Mapping[str, Any], official: Sequence[str]) -> str | None:
    """The notice PDF in its own language, which is what S1.2.2 opens.

    `links.pdf` is keyed by the same three-letter codes as `official-language`, and carries
    all 24 — the source language is the one the buyer actually wrote, so a translation is
    not offered where the original exists.
    """
    pdfs = links.get("pdf")
    if not isinstance(pdfs, Mapping):
        return None
    for code in (*official, "ENG"):
        url = pdfs.get(code.upper())
        if isinstance(url, str) and url:
            return url
    return next((url for url in pdfs.values() if isinstance(url, str) and url), None)


def _codes(field: object) -> tuple[str, ...]:
    return (
        tuple(str(code) for code in field if isinstance(code, str))
        if isinstance(field, list)
        else ()
    )


def _unique(field: object) -> tuple[str, ...]:
    """`classification-cpv` repeats a code once per lot; a screen wants it once."""
    seen: dict[str, None] = {}
    for code in field if isinstance(field, list) else []:
        if isinstance(code, str) and code:
            seen.setdefault(code, None)
    return tuple(seen)


def _first(field: object) -> str | None:
    if isinstance(field, str):
        return field or None
    for value in field if isinstance(field, list) else []:
        if isinstance(value, str) and value:
            return value
    return None
