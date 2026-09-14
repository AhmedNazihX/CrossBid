"""S1.4.1 — `GET /dev/settings`: what an operator may see, and where it disappears.

Two halves, and the second is the security test.

**What it shows.** The story's second criterion is "a tool module exports `MANIFEST` … and
`GET /dev/settings` lists all manifests" — *all*, not the enabled ones, because a panel that
hid the disabled tools could not be used to turn one back on. The `enabled` flag is derived
from `settings.runtime.enabled_tools` on every request rather than from
`MANIFEST.default_enabled`, so the two are asserted apart here: a tool switched off by the
`app_settings` row still ships `default_enabled=True`, and the panel has to say both.

**What it must never show.** The response is assembled from `RuntimeSettings` only, and the
test below reads the raw body looking for the fake secrets `conftest` plants, plus the
system prompt — excluded for a reason of its own: it is the injection defence's standing
text (S2.3.2), and publishing it on an unauthenticated route hands anyone who can get a PDF
into the pipeline the exact wording to write around. Searching the serialised body rather
than the parsed model is deliberate: a field added later is covered without anyone
remembering to extend this test.

The route is gated on `ENV != production` and answers **404** there, not 403 — a 403 is a
route confirming its own existence. That is the whole gate until S4.6.2 brings a real
developer role; `auth.py` is still the `X-Dev-Company` bridge, and a header anybody can
type is not an authorisation to check against.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pytest
from fastapi.testclient import TestClient

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.main import create_app
from crossbid.routers.dev import DEV_SETTINGS_PATH, NOT_FOUND_DETAIL
from crossbid.settings import (
    AppSettingsRow,
    ModelRole,
    Settings,
    apply_app_settings_row,
    load_settings,
)
from tests.conftest import FAKE_ENCRYPTION_KEY, FAKE_OPENROUTER_KEY

COMPANY_RAG = "company_rag_search"
TENDER_RAG = "tender_rag_search"
ECERTIS = "ecertis_evidence_lookup"
PATH = DEV_SETTINGS_PATH
UNKNOWN_PATH = "/dev/no-such-route"


# ------------------------------------------------------------------------------ helpers


def app_client(settings: Settings) -> TestClient:
    """A client over a freshly built app, for the tests that need settings of their own."""
    return TestClient(create_app(settings))


@pytest.fixture
def production_settings(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    """A deployed configuration, through the real loader so its guards run too.

    `AUTH_MODE=supabase` because `settings.py` refuses the dev bridge in production; that
    refusal is exactly why this route needs a gate of its own. `SUPABASE_URL` comes with it
    for the same reason -- the loader refuses supabase auth with no project to verify
    against (S0.3.1).
    """
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    return load_settings(env_file=None)


def fetch(client: TestClient) -> dict[str, Any]:
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def tools_by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool for tool in body["tools"]}


# -------------------------------------------------------------------------- the manifests


def test_it_lists_every_manifest_that_exists(client: TestClient) -> None:
    """All of them: a panel that listed only the enabled ones could not switch one on."""
    # Act
    listed = tools_by_name(fetch(client))

    # Assert
    assert set(listed) == {COMPANY_RAG, TENDER_RAG, ECERTIS, "search_ted"}


def test_each_manifest_carries_what_the_panel_shows(client: TestClient) -> None:
    """Name, description, `external` and `default_enabled` — the manifest, not a summary."""
    # Act
    listed = tools_by_name(fetch(client))

    # Assert
    assert listed[ECERTIS]["external"] is False, "the cache is committed; it opens no socket"
    assert listed[COMPANY_RAG]["external"] is True
    assert listed[ECERTIS]["default_enabled"] is True
    assert "eCertis" in listed[ECERTIS]["description"]


def test_the_enabled_flag_follows_the_settings_not_the_manifest(
    offline_settings: Settings,
) -> None:
    """A tool switched off at run time still ships on by default, and both are reported."""
    # Arrange
    settings = apply_app_settings_row(
        offline_settings, AppSettingsRow(enabled_tools=(ECERTIS,))
    )

    # Act
    with app_client(settings) as client:
        listed = tools_by_name(fetch(client))

    # Assert
    assert listed[ECERTIS]["enabled"] is True
    assert listed[COMPANY_RAG]["enabled"] is False
    assert listed[COMPANY_RAG]["default_enabled"] is True


def test_it_names_the_tools_that_are_configured_but_not_built(client: TestClient) -> None:
    """`settings.default.yaml` enables two Increment 4 stories; dropping them would lie."""
    # Act
    body = fetch(client)

    # Assert
    assert body["unbuilt_tools"] == ["currency_convert"]
    assert set(body["unbuilt_tools"]).isdisjoint(tools_by_name(body))


# ------------------------------------------------------------------- the runtime settings


def test_it_reports_the_model_slug_for_every_role(
    client: TestClient, offline_settings: Settings
) -> None:
    """The picker of S4.6.2 needs the current slug per role, and the verified list."""
    # Act
    body = fetch(client)

    # Assert
    for role in ModelRole:
        assert body["models"][role.value] == offline_settings.runtime.models.for_role(role)
    assert body["available_models"] == list(offline_settings.runtime.available_models)


def test_it_reports_the_knobs_and_the_budgets(
    client: TestClient, offline_settings: Settings
) -> None:
    """Temperature, max tokens, and the two concurrency limits with the run budgets."""
    # Arrange
    runtime = offline_settings.runtime

    # Act
    body = fetch(client)

    # Assert
    assert body["temperature"] == runtime.temperature
    assert body["max_tokens"] == runtime.max_tokens
    assert body["agent"] == runtime.agent.model_dump()


def test_it_says_a_system_prompt_is_configured_without_printing_it(
    client: TestClient, offline_settings: Settings
) -> None:
    """The operator needs to know an override is in effect; the text itself is not shown."""
    # Arrange
    assert offline_settings.runtime.system_prompt is not None

    # Act
    body = fetch(client)

    # Assert
    assert body["system_prompt_set"] is True
    assert "system_prompt" not in body


# --------------------------------------------------------------------------- no secrets


def test_the_response_carries_no_secret_and_no_prompt(
    client: TestClient, offline_settings: Settings
) -> None:
    """Read as text, so a field somebody adds later is covered without editing this test."""
    # Arrange
    prompt = offline_settings.runtime.system_prompt
    assert prompt is not None

    # Act
    body = client.get(PATH).text

    # Assert
    assert FAKE_OPENROUTER_KEY not in body
    assert FAKE_ENCRYPTION_KEY not in body
    assert prompt.splitlines()[0] not in body


# ------------------------------------------------------------------------------ the gate


def test_it_is_not_reachable_in_production(production_settings: Settings) -> None:
    """404, never 403: a "forbidden" would confirm the route is there to be reached."""
    # Act
    with app_client(production_settings) as client:
        response = client.get(PATH)

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_the_refusal_is_indistinguishable_from_an_unknown_path(
    production_settings: Settings,
) -> None:
    """Same status and same body as a path that was never registered."""
    # Act
    with app_client(production_settings) as client:
        refused = client.get(PATH)
        missing = client.get(UNKNOWN_PATH)

    # Assert
    assert (refused.status_code, refused.json()) == (missing.status_code, missing.json())


def test_it_needs_no_tenant_header(client: TestClient) -> None:
    """Deliberate: the answer holds no tenant data, and `X-Dev-Company` is self-asserted —
    requiring it would turn the 404 above into a 401 that confirms the route exists."""
    # Act & Assert
    assert client.get(PATH).status_code == 200
    assert client.get(PATH, headers={DEV_COMPANY_HEADER: "not-a-uuid"}).status_code == 200


# ------------------------------------------------- what the route is allowed to publish

PUBLISHED_SHAPE: Final[Mapping[str, frozenset[str]]] = {
    "": frozenset(
        {
            "models",
            "available_models",
            "temperature",
            "max_tokens",
            "system_prompt_set",
            "agent",
            "tools",
            "unbuilt_tools",
        }
    ),
    "models": frozenset({"extract", "cheap", "embed", "judge", "fallback"}),
    "agent": frozenset(
        {
            "extract_concurrency",
            "check_concurrency",
            "max_tool_calls_per_requirement",
            "run_budget_seconds",
            "run_budget_usd",
            "llm_timeout_seconds",
        }
    ),
    "tools[]": frozenset({"name", "description", "external", "default_enabled", "enabled"}),
}
"""Every key this route may put on the wire, pinned so growth is a decision and not a drift.

`DevSettingsResponse` names its eight fields one by one, so nothing reaches a caller by
accident today. Two of those eight are a different matter: `models` and `agent` embed
`ModelSlugs` and `AgentSettings` *whole*, and a field added to either would be published the
moment it was added, reviewed by nobody. `test_the_response_carries_no_secret_and_no_prompt`
would not catch it either — that test can only look for secrets whose value it already knows.

So the contract is pinned by shape instead. Adding a knob to `AgentSettings` fails this test
until someone writes it down here, which is the point at which they have to ask whether an
unauthenticated route should carry it.
"""


def _key_paths(body: Mapping[str, object]) -> dict[str, frozenset[str]]:
    """The response's own shape, in the same form as `PUBLISHED_SHAPE`."""
    found = {"": frozenset(body)}
    for key, value in body.items():
        if isinstance(value, dict):
            found[key] = frozenset(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            found[f"{key}[]"] = frozenset().union(*(frozenset(row) for row in value))
    return found


def test_the_route_publishes_exactly_the_pinned_shape(client: TestClient) -> None:
    """A field added to an embedded settings model must not reach the wire unreviewed."""
    # Act
    body = client.get(PATH).json()

    # Assert
    assert _key_paths(body) == dict(PUBLISHED_SHAPE)
