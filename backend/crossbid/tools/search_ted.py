"""`search_ted` — the tool that finds published notices (S1.2.2, over S1.2.1's client).

`external=True`, and that flag is doing real work here: this is the only tool in the set
that opens a socket to a service we do not control. TED is free and needs no key, so the
cost is latency and availability rather than money — but an operator who wants a run that
cannot stall on a third party turns this one off, and the panel tells them which it is.

**It is enabled by default because `settings.default.yaml` says so**, and the file is the
operator's intention — a module declaring itself off while the settings enable it would be
the developer panel telling an operator something the runtime does not do. It is also one of
the five tools brief item Medium 6 asks for an enable/disable surface over.

That said, the agent's own job is to read the pack the bidder uploaded, not to go looking for
other tenders, so the description says plainly what this does *not* do — it does not fetch
procurement documents — and the per-requirement loop's `max_tool_calls_per_requirement`
budget is what stops a model wandering into a search mid-check. An operator who wants a run
that cannot stall on a third party turns it off in the panel, which is exactly what
`external=True` is there to tell them.

**The answer is trimmed to what a model can use.** The full `TedNotice` carries link sets
and CPV lists that would spend tokens on nothing; what is returned is the title, buyer,
deadline, languages, publication number and the two URLs — enough to name a notice and to
say where to read it, and no more.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.models.ted import MAX_RESULTS_PER_PAGE, Cpv, TedNotice, TedSearchQuery
from crossbid.reference.ted_client import (
    REQUEST_TIMEOUT_S,
    TedSearchClient,
    TedUnavailableError,
)
from crossbid.tools import ToolContext, ToolManifest

Alpha2 = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")]

DEFAULT_TOOL_LIMIT = 10
"""Fewer than the screen shows: a model summarising twenty notices spends tokens to say
less than it would about five."""

DESCRIPTION = """\
Search the EU's Tenders Electronic Daily (TED) for published contract notices, by CPV \
code, country of performance and an optional keyword.

Use this to find tenders a bidder might compete for, or to look up a notice by what it is \
about. Results carry the title, the buying authority, the submission deadline, the \
languages the notice is written in and may be answered in, the TED publication number, and \
two links: the notice as published, and the buyer's own platform where the procurement \
documents live.

A CPV code must be the full eight digits (72000000, not 72). Titles come back in the \
bidder's language where TED publishes a translation, which it does for all 24 EU languages.

This reaches a live service. It does NOT download the procurement documents — those sit on \
the buyer's platform and the bidder uploads them by hand.\
"""


MANIFEST = ToolManifest(
    name="search_ted",
    description=DESCRIPTION,
    external=True,
    default_enabled=True,
)


class SearchTedArgs(BaseModel):
    """What the model must supply. Every field is constrained, so nothing needs escaping."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cpv: tuple[Cpv, ...] = Field(
        default=(),
        description=(
            "CPV codes, full eight digits (e.g. '72000000' for IT services). Several are a "
            "union: a notice matching any of them is returned."
        ),
    )
    countries: tuple[Alpha2, ...] = Field(
        default=(),
        description="Where the contract is performed, ISO 3166-1 alpha-2 (e.g. 'fr').",
    )
    keyword: str | None = Field(
        default=None,
        description="One phrase searched across the notice. Not a boolean expression.",
    )
    language: Alpha2 | None = Field(
        default=None,
        description="Read titles in this language where TED publishes a translation.",
    )
    limit: int = Field(
        default=DEFAULT_TOOL_LIMIT,
        ge=1,
        le=MAX_RESULTS_PER_PAGE,
        description="How many notices to return, newest first.",
    )


def build_tool(context: ToolContext) -> BaseTool:
    """The bound tool. `context` is unused: TED is public and scoped by nothing."""
    del context

    def run(
        cpv: tuple[str, ...] = (),
        countries: tuple[str, ...] = (),
        keyword: str | None = None,
        language: str | None = None,
        limit: int = DEFAULT_TOOL_LIMIT,
    ) -> dict[str, Any]:
        query = TedSearchQuery(
            cpv=tuple(cpv),
            countries=tuple(code.lower() for code in countries),
            keyword=keyword,
            limit=limit,
        )
        client = TedSearchClient(httpx.Client(timeout=REQUEST_TIMEOUT_S))
        try:
            page = client.search(query, language=language)
        except TedUnavailableError as error:
            # Total, like every tool the ReAct loop calls: a third party being down must not
            # end a run that has already cost money (S3.3.1's rule for `ecertis_evidence`).
            return {"status": "unavailable", "detail": str(error), "notices": []}
        return {
            "status": "ok",
            "total": page.total,
            "notices": [_summarise(notice) for notice in page.notices],
        }

    return StructuredTool.from_function(
        func=run,
        name=MANIFEST.name,
        description=MANIFEST.description,
        args_schema=SearchTedArgs,
    )


def _summarise(notice: TedNotice) -> dict[str, Any]:
    """One notice, trimmed to what a model can act on. See the module docstring."""
    return {
        "publication_number": notice.publication_number,
        "title": notice.title,
        "buyer": notice.buyer,
        "deadline": None if notice.deadline is None else notice.deadline.isoformat(),
        "official_languages": list(notice.official_languages),
        "submission_languages": list(notice.submission_languages),
        "notice_url": notice.notice_pdf_url,
        "documents_url": notice.documents_url,
    }
