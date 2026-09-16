"""The dev-mode auth bridge: `X-Dev-Company` is believed, and only in dev mode.

Offline. A throwaway route wired to `current_company` stands in for every router. Supabase
token verification is S0.3.1 proper and lives in `test_supabase_auth.py`; what is left here
is the bridge that let Increments 1-3 run before it, and the two guards that keep the bridge
from ever being the thing a deployment runs on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from crossbid.auth import DEV_COMPANY_HEADER, CompanyContext, current_company
from crossbid.deps import get_app_settings
from crossbid.main import create_app
from crossbid.settings import AuthMode, Settings, SettingsError, load_settings

COMPANY_ID = str(uuid.uuid4())


def app_for(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/whoami")
    async def whoami(company: CompanyContext = Depends(current_company)) -> CompanyContext:
        return company

    @app.get("/settings-env")
    async def settings_env(settings: Settings = Depends(get_app_settings)) -> str:
        return settings.env.environment.value

    return app


@pytest.fixture
def dev_client(offline_settings: Settings) -> Iterator[TestClient]:
    with TestClient(app_for(offline_settings)) as client:
        yield client


def test_the_dev_header_names_the_company(dev_client: TestClient) -> None:
    response = dev_client.get("/whoami", headers={DEV_COMPANY_HEADER: COMPANY_ID})
    assert response.status_code == 200
    assert response.json() == {"company_id": COMPANY_ID}


def test_the_header_is_normalised_to_canonical_uuid_form(dev_client: TestClient) -> None:
    """Braces, upper case and padding name the same company; the row key must be one form."""
    response = dev_client.get(
        "/whoami", headers={DEV_COMPANY_HEADER: f"  {{{COMPANY_ID.upper()}}} "}
    )
    assert response.json() == {"company_id": COMPANY_ID}


@pytest.mark.parametrize("headers", [{}, {DEV_COMPANY_HEADER: ""}, {DEV_COMPANY_HEADER: "  "}])
def test_a_missing_dev_header_is_401_and_names_the_header(
    dev_client: TestClient, headers: dict[str, str]
) -> None:
    response = dev_client.get("/whoami", headers=headers)
    assert response.status_code == 401
    assert DEV_COMPANY_HEADER in response.json()["detail"]


@pytest.mark.parametrize("value", ["acme", "1", "not-a-uuid-at-all", "'; drop table bids;--"])
def test_a_malformed_dev_header_is_401(dev_client: TestClient, value: str) -> None:
    response = dev_client.get("/whoami", headers={DEV_COMPANY_HEADER: value})
    assert response.status_code == 401
    assert "UUID" in response.json()["detail"]
    assert value not in response.json()["detail"]


def test_dev_auth_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """A header is not a credential, so the mode that trusts one may never be deployed."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "0" * 44)
    monkeypatch.setenv("AUTH_MODE", AuthMode.DEV.value)
    monkeypatch.setenv("ENV", "production")

    with pytest.raises(SettingsError, match="AUTH_MODE=dev is refused"):
        load_settings(env_file=None)


def test_supabase_auth_without_a_project_url_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The signing keys are read from SUPABASE_URL; without it there is nothing to verify
    against, and the failure belongs at startup rather than on the first request."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "0" * 44)
    monkeypatch.setenv("AUTH_MODE", AuthMode.SUPABASE.value)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    with pytest.raises(SettingsError, match="AUTH_MODE=supabase needs SUPABASE_URL"):
        load_settings(env_file=None)


def test_get_app_settings_returns_the_injected_settings(offline_settings: Settings) -> None:
    env = offline_settings.env.model_copy(update={"langsmith_project": "injected"})
    settings = Settings(env=env, runtime=offline_settings.runtime)
    with TestClient(app_for(settings)) as client:
        assert client.get("/settings-env").json() == settings.env.environment.value
        assert client.app.state.settings is settings  # type: ignore[attr-defined]


def test_company_context_is_frozen() -> None:
    context = CompanyContext(company_id=COMPANY_ID)
    with pytest.raises(Exception, match="frozen"):
        context.company_id = "other"  # type: ignore[misc]
    assert SecretStr is not None  # keeps the import honest for the model_copy tests above
