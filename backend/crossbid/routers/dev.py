"""The developer routes: what the agent is configured to do, and what it has spent.

`GET /dev/settings` is S1.4.1 and `GET /dev/costs` is S5.2. They share the router because
they share both gates and the panel that reads them (S4.6.2); they differ in one way that
is worth stating before the rest, because it is the exception to the rule below.

**`/dev/costs` is tenant-scoped and `/dev/settings` is not.** Settings are a property of the
process — the same answer for everyone who may see it — so the route takes no tenant and
deliberately ignores `X-Dev-Company`, which is self-asserted and authorises nothing. Costs
are a property of a *company's* runs, so the costs route adds `current_company` as a
dependency of its own and every statement behind it carries `company_id`
(`readmodel/usage.py`). Being a developer is not a key to another tenant's spend: the
`DEVELOPER_EMAILS` check says who may look at the panel, not whose numbers it shows.

The rule about the settings response — assembled from `RuntimeSettings` alone, so a secret
cannot arrive by accident — has a counterpart rather than an exception on the costs route.
That response is assembled from `llm_usage` rows alone, and the table has no column that
could hold a key, a prompt or a line of a tender: it stores a node name, a provider, a slug,
two token counts and a number of dollars. Nothing is copied onto it from settings or from a
document, which is what keeps the same guarantee without repeating the same argument.

**A bid id is not a capability, and the route must not become an oracle for one.**
`?bid_id=` narrows the answer to one run, and a bid belonging to another company answers
**200 with an empty report**, never 404 — the statements are scoped by company, so there is
nothing to find, and a 404 that appeared only for ids that do not exist anywhere would tell
a caller which ids do. `routers/feedback.py`'s `GET` is shaped the same way for the same
reason.

---

S1.4.1 — `GET /dev/settings`: the tools that exist, and the knobs behind them.

What the developer panel (S4.6.2) reads before it can offer to change anything: every tool
manifest the registry discovered with an `enabled` flag beside it, the configured names no
module provides yet, and the runtime an operator tunes — model slug per role, temperature,
max tokens, the two concurrency limits and the run budgets.

**`switchable_roles` is here for S5.1, and it is not decoration.** `models` carries a slug
for all five roles and `available_models` is a *chat* list, so a panel that rendered one
picker per role from the two together would offer `openai/gpt-5.6-terra` for `embed` — a
switch the loader refuses and which, were it accepted, would leave the corpus half-embedded
by one model and half by another. The backend knows which roles the list applies to, so it
says so rather than leaving the frontend to infer it from a slug's name.

**Why `enabled` is computed here and not read off the manifest.** `MANIFEST.default_enabled`
is a claim about `settings.default.yaml`; `settings.runtime.enabled_tools` is what this
process will actually bind (`tools/registry.py`). They agree until an operator changes the
`app_settings` row, and the moment they disagree is exactly when a panel that showed only
one of them would be lying. Both are in the response.

**What is deliberately not in the response, and why.**

*Everything in `EnvSettings`.* That is one rule rather than a per-field judgement, and it
is the same split the settings module already draws: secrets and deployment wiring live in
the environment (`OPENROUTER_API_KEY`, `APP_ENCRYPTION_KEY`, `DATABASE_URL` with its
password, the Supabase service-role key, the LangSmith key), behaviour lives in
`RuntimeSettings`. So the response is assembled from `RuntimeSettings` alone, and
`ModelSlugs` and `AgentSettings` are reused verbatim rather than re-typed — a field added
to either is behaviour by construction, and cannot be a secret arriving by accident.
`ENV`, `AUTH_MODE` and `WEB_ORIGIN` are non-secret but still deployment facts an operator
cannot change from a panel, so they stay out too.

*`confirm_flagged_chunks`.* S5.3's second opinion, and it stays out for the same reason
`system_prompt` does: it is a defence, and its *state* is worth as much to an attacker as
its wording. A route with no authentication in front of it announcing that the model review
is switched off tells anyone who can put a PDF into the pipeline that the only thing between
them and the corpus is a list of regular expressions. Its value is in the YAML for whoever
deploys it, and in the log line a release writes.

*`system_prompt`.* It is the injection defence's standing text (S2.3.2, ADR-0009): the
rules that tell the model a data block is data. Printing it on a route with no
authentication behind it hands anyone who can get a PDF into the pipeline the exact wording
to write around, and the column is overridable per deployment, so the text may carry
deployment detail the YAML does not. `system_prompt_set` is reported instead — an operator
needs to know an override is in effect; nobody needs to read it over HTTP. S4.6.2 edits it
behind a real role check.

*`evaluation`.* S3.2.3's `recall_threshold` is a gate on how good extraction has to be
before a story counts as delivered, not a knob a panel turns: moving it from a browser
would change the number the course reports without changing anything the agent does. It is
read by `scripts/recall.py` from the YAML and stays off the wire.

**Two gates, and their order is the security-relevant part.** The environment is checked
first and answers **404** with FastAPI's own not-found body, because a 403 is a route
confirming it is there to be reached; then S0.3.1's developer check answers **403** for an
account that is not on `DEVELOPER_EMAILS`. Declared in that order on the router, and FastAPI
resolves a dependency list in order, so in production an unauthenticated request gets the
404 rather than the 401 that would give the route away.

Under `AUTH_MODE=dev` every caller is a developer (`auth.current_user`), which is the same
door the environment gate already opened and needs no tenant header: the answer holds no
tenant data, and `X-Dev-Company` is self-asserted and so authorises nothing.

The route stays in the OpenAPI schema in production — the generated `frontend/lib/api.ts`
must not depend on which environment the API was booted in — and answers 404 there.
"""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import CompanyContext, current_company, require_developer
from crossbid.db import Database
from crossbid.main import get_app_settings, get_database
from crossbid.readmodel.usage import (
    DEFAULT_BID_LIMIT,
    MAX_BID_LIMIT,
    BidUsage,
    NodeUsage,
    UsageTotals,
    fetch_usage_by_bid,
    fetch_usage_by_node,
    totals_of,
)
from crossbid.settings import (
    CHAT_MODEL_ROLES,
    AgentSettings,
    Environment,
    ModelRole,
    ModelSlugs,
    Settings,
)
from crossbid.tools.registry import enabled_tool_names, manifests, unbuilt_tool_names

DEV_SETTINGS_PATH: Final = "/dev/settings"
DEV_COSTS_PATH: Final = "/dev/costs"
"""The full paths, so a test states them once rather than reassembling the prefix."""

NOT_FOUND_DETAIL: Final = "Not Found"
"""Starlette's own 404 body, copied so the refusal reads exactly like an unknown path."""


def refuse_in_production(settings: Settings = Depends(get_app_settings)) -> None:
    """The first gate. Declared before the developer check so production answers 404."""
    if settings.env.environment is Environment.PRODUCTION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


router = APIRouter(
    prefix="/dev",
    tags=["dev"],
    dependencies=[Depends(refuse_in_production), Depends(require_developer)],
)


class ToolDescriptor(BaseModel):
    """One tool as the panel shows it: its manifest, plus whether this process will bind it."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="The name the model calls the tool by")
    description: str = Field(description="The text the model decides on; written for it")
    external: bool = Field(
        description="True when a call leaves the process. Cached reference data is false."
    )
    default_enabled: bool = Field(
        description="Whether the tool ships enabled in settings.default.yaml"
    )
    enabled: bool = Field(
        description="Whether this process will bind it, after any app_settings override"
    )


class DevSettingsResponse(BaseModel):
    """The developer panel's read model. Runtime settings only — never the environment."""

    model_config = ConfigDict(frozen=True)

    models: ModelSlugs = Field(description="The OpenRouter slug in use for each role")
    available_models: tuple[str, ...] = Field(
        description="Slugs the picker may offer: the verified set, not OpenRouter's catalogue"
    )
    switchable_roles: tuple[ModelRole, ...] = Field(
        description=(
            "The roles available_models applies to. Every role but embed, whose slug is "
            "pinned to the stored vectors' width and is not a picker choice."
        )
    )
    temperature: float
    max_tokens: int
    system_prompt_set: bool = Field(
        description=(
            "Whether a system prompt is configured. The text itself is never returned: it "
            "is the prompt-injection defence's standing instructions."
        )
    )
    agent: AgentSettings = Field(
        description="Concurrency limits, the per-requirement tool budget and the run budgets"
    )
    tools: tuple[ToolDescriptor, ...] = Field(
        description="Every tool that exists, enabled or not, sorted by name"
    )
    unbuilt_tools: tuple[str, ...] = Field(
        description=(
            "Names enabled in settings that no module provides yet — a story that has not "
            "landed. Listed rather than dropped, so 'off' and 'not built' stay distinct."
        )
    )


def _describe_tools(settings: Settings) -> tuple[ToolDescriptor, ...]:
    enabled = enabled_tool_names(settings)
    return tuple(
        ToolDescriptor(
            name=manifest.name,
            description=manifest.description,
            external=manifest.external,
            default_enabled=manifest.default_enabled,
            enabled=manifest.name in enabled,
        )
        for manifest in manifests()
    )


@router.get("/settings", response_model=DevSettingsResponse, summary="Developer settings")
async def read_dev_settings(
    settings: Settings = Depends(get_app_settings),
) -> DevSettingsResponse:
    """What the agent may reach and how it is configured. Outside production only."""
    runtime = settings.runtime
    return DevSettingsResponse(
        models=runtime.models,
        available_models=runtime.available_models,
        switchable_roles=CHAT_MODEL_ROLES,
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        system_prompt_set=runtime.system_prompt is not None,
        agent=runtime.agent,
        tools=_describe_tools(settings),
        unbuilt_tools=unbuilt_tool_names(settings),
    )


# ------------------------------------------------------------------------------- costs


class DevCostsResponse(BaseModel):
    """Where the money went: one total, the same rows split two ways.

    Both breakdowns and the total are the same five numbers (`UsageTotals`), so the panel
    adds them up identically wherever it shows them, and `by_node` is what the story asks
    for by name — tokens and cost per node, with the provider used.
    """

    model_config = ConfigDict(frozen=True)

    total: UsageTotals = Field(
        description=(
            "Every chat completion in scope. Embeddings are not counted: they are bought "
            "from the same provider but are not recorded in llm_usage — see crossbid/usage.py"
        )
    )
    by_node: tuple[NodeUsage, ...] = Field(
        description=(
            "Per graph node and per model that answered, dearest first. A node appears "
            "twice when a call fell back to the other vendor mid-run"
        )
    )
    by_bid: tuple[BidUsage, ...] = Field(
        description="Per bid, most recently active first, newest `limit` runs only"
    )


@router.get(
    "/costs", response_model=DevCostsResponse, summary="Tokens and cost per bid and node"
)
async def read_dev_costs(
    bid_id: uuid.UUID | None = Query(
        default=None,
        description="Narrow every figure to one run. Another company's returns nothing",
    ),
    limit: int = Query(
        default=DEFAULT_BID_LIMIT,
        ge=1,
        le=MAX_BID_LIMIT,
        description="How many bids to list in by_bid; by_node and total are never truncated",
    ),
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
) -> DevCostsResponse:
    """What this company's runs have spent, per node and per bid. Outside production only.

    The total is summed from `by_node` rather than asked of the database separately: that
    breakdown is never truncated, so the sum is exact, and a total from its own statement
    could disagree with the lines beneath it if a run wrote a row between the two queries.
    `by_bid` is the one list with a limit, which is why it is not what the total comes from.
    """
    company_id = company.company_id
    scope = None if bid_id is None else str(bid_id)
    by_node = await fetch_usage_by_node(db, company_id=company_id, bid_id=scope)
    by_bid = await fetch_usage_by_bid(db, company_id=company_id, bid_id=scope, limit=limit)
    return DevCostsResponse(total=totals_of(by_node), by_node=by_node, by_bid=by_bid)
