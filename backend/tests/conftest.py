"""Shared fixtures.

Fakes live here rather than in individual tests so that one definition of "a fake LLM" or
"a fake TED client" serves the whole suite (see docs/project-plan.md, Verification).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from crossbid.main import create_app
from crossbid.reference import ecertis_client
from crossbid.settings import Settings, load_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
ECERTIS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ecertis"
ECERTIS_GENERATOR_PATH = BACKEND_DIR / "scripts" / "build_ecertis_cache.py"


# Distinctive so that a leak into a repr, a dump or an exception is unmistakable.
FAKE_OPENROUTER_KEY = "sk-or-v1-LEAKED-OPENROUTER-KEY"
FAKE_ENCRYPTION_KEY = "LEAKED-FERNET-ENCRYPTION-KEY="

STARTUP_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "APP_ENCRYPTION_KEY",
    "DATABASE_URL",
    "AUTH_MODE",
    "ENV",
    "LANGSMITH_API_KEY",
    "VERIFY_MODEL_SLUGS",
)


@pytest.fixture
def anyio_backend() -> str:
    """Run `@pytest.mark.anyio` tests on asyncio only; trio is not installed."""
    return "asyncio"


@pytest.fixture
def offline_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings the API starts with and that touch nothing outside the process.

    No `DATABASE_URL`, so `create_app` opens no pool -- CI's backend job exports one for
    the live tests, and a `TestClient` picking it up would make every route test hit
    Postgres. No dotenv layer, so a developer's real `.env` is never read.
    """
    for name in STARTUP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)
    return load_settings(env_file=None)


@pytest.fixture
def client(offline_settings: Settings) -> Iterator[TestClient]:
    """A client against a freshly built app, so no test inherits another's state.

    Entering the `with` runs the lifespan, so a route test also proves startup works.
    """
    with TestClient(create_app(offline_settings)) as test_client:
        yield test_client


# ------------------------------------------------------------------------------- eCertis


@pytest.fixture(autouse=True)
def _reset_ecertis_caches() -> Iterator[None]:
    """The cache loaders are `lru_cache`d, so one test's `DATA_DIR` must not leak.

    Autouse and on both sides of the test: a test that repoints `DATA_DIR` at a `tmp_path`
    would otherwise hand its temporary cache to whatever ran next.
    """
    ecertis_client.clear_caches()
    yield
    ecertis_client.clear_caches()


@pytest.fixture(scope="session")
def ecertis_generator() -> ModuleType:
    """`scripts/build_ecertis_cache.py` as an importable module.

    `scripts/` is not a package (and is omitted from coverage as an entry point), but the
    generator's rendering and write logic is exactly what the S1.1.1/S1.1.3 acceptance
    criteria are about, so it is loaded by path rather than left untested.
    """
    name = "build_ecertis_cache"
    spec = importlib.util.spec_from_file_location(name, ECERTIS_GENERATOR_PATH)
    assert spec is not None and spec.loader is not None, ECERTIS_GENERATOR_PATH
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module defines a `@dataclass`, and dataclasses
    # resolve annotations through `sys.modules[cls.__module__]`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EcertisFixtureLoader:
    """Tiny reader so tests say `ecertis_fixture("criteria_list")`, not a path dance."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def __call__(self, name: str) -> dict[str, Any]:
        path = self._directory / f"{name}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path
        return payload


@pytest.fixture(scope="session")
def ecertis_fixture() -> EcertisFixtureLoader:
    """Reads the recorded payloads in `tests/fixtures/ecertis/`. See its SOURCES.md."""
    return EcertisFixtureLoader(ECERTIS_FIXTURE_DIR)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retry backoff instant via the seam `EcertisRestClient._sleep` exists for."""
    monkeypatch.setattr(
        ecertis_client.EcertisRestClient, "_sleep", staticmethod(lambda _seconds: None)
    )
