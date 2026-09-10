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

BACKEND_DIR = Path(__file__).resolve().parent.parent
ECERTIS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ecertis"
ECERTIS_GENERATOR_PATH = BACKEND_DIR / "scripts" / "build_ecertis_cache.py"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client against a freshly built app, so no test inherits another's state."""
    with TestClient(create_app()) as test_client:
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
