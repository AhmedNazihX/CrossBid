"""The dev-mode auth bridge (S0.3.1 Notes): `X-Dev-Company` is believed, and only in dev mode.

Offline. A throwaway route wired to `current_company` stands in for every router.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from crossbid.auth import DEV_COMPANY_HEADER, CompanyContext, current_company
from crossbid.main import create_app, get_app_settings
from crossbid.settings import AuthMode, Settings

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


@pytest.fixture
def supabase_client(offline_settings: Settings) -> Iterator[TestClient]:
    env = offline_settings.env.model_copy(update={"auth_mode": AuthMode.SUPABASE})
    with TestClient(app_for(Settings(env=env, runtime=offline_settings.runtime))) as client:
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


def test_supabase_mode_refuses_rather_than_pretends(supabase_client: TestClient) -> None:
    """Until S0.3.1 lands, a deployment configured for real auth must not look authenticated."""
    response = supabase_client.get("/whoami", headers={DEV_COMPANY_HEADER: COMPANY_ID})
    assert response.status_code == 501
    assert "S0.3.1" in response.json()["detail"]


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
