"""S1.4.1 — `GET /dev/settings`: the tools that exist, and the knobs behind them.

What the developer panel (S4.6.2) reads before it can offer to change anything: every tool
manifest the registry discovered with an `enabled` flag beside it, the configured names no
module provides yet, and the runtime an operator tunes — model slug per role, temperature,
max tokens, the two concurrency limits and the run budgets.

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

*`system_prompt`.* It is the injection defence's standing text (S2.3.2, ADR-0009): the
rules that tell the model a data block is data. Printing it on a route with no
authentication behind it hands anyone who can get a PDF into the pipeline the exact wording
to write around, and the column is overridable per deployment, so the text may carry
deployment detail the YAML does not. `system_prompt_set` is reported instead — an operator
needs to know an override is in effect; nobody needs to read it over HTTP. S4.6.2 edits it
behind a real role check.

**The gate is `ENV != production`, and the refusal is a 404.** S4.6.2's criterion is "given
a non-developer account, the route is not reachable", but there is no developer role to
check: authentication is still the `X-Dev-Company` bridge of S0.3.1's notes, and the plan
lists the role mechanism (an env-var email list) as open. Inventing one here would be a
security control nobody reviewed. So the route is gated on what exists and what
`seed_dev_company.py` and `settings._refuse_dev_auth_in_production` already gate on: the
environment. **S4.6.2 tightens this to a real role check** and the environment gate stays
underneath it. The refusal is 404 with FastAPI's own not-found body, because a 403 is a
route confirming it is there to be reached. No tenant header is required: the answer holds
no tenant data, `X-Dev-Company` is self-asserted and so authorises nothing, and demanding
it would turn that 404 into a 401 that gives the route away.

The route stays in the OpenAPI schema in production — the generated `frontend/lib/api.ts`
must not depend on which environment the API was booted in — and answers 404 there.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from crossbid.main import get_app_settings
from crossbid.settings import AgentSettings, Environment, ModelSlugs, Settings
from crossbid.tools.registry import enabled_tool_names, manifests, unbuilt_tool_names

router = APIRouter(prefix="/dev", tags=["dev"])

DEV_SETTINGS_PATH: Final = "/dev/settings"
"""The full path, so a test states it once rather than reassembling the prefix."""

NOT_FOUND_DETAIL: Final = "Not Found"
"""Starlette's own 404 body, copied so the refusal reads exactly like an unknown path."""


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


def _refuse_in_production(settings: Settings) -> None:
    """The gate. See the module docstring: environment now, developer role at S4.6.2."""
    if settings.env.environment is Environment.PRODUCTION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


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
    _refuse_in_production(settings)
    runtime = settings.runtime
    return DevSettingsResponse(
        models=runtime.models,
        available_models=runtime.available_models,
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        system_prompt_set=runtime.system_prompt is not None,
        agent=runtime.agent,
        tools=_describe_tools(settings),
        unbuilt_tools=unbuilt_tool_names(settings),
    )
