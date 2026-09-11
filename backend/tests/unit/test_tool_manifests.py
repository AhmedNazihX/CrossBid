"""Every tool's manifest against the file it claims to describe (`settings.default.yaml`).

`ToolManifest.default_enabled` is the developer panel's answer to "is the agent allowed to
call this out of the box?", and the only thing that makes it true is `enabled_tools` in the
settings file. Asserting it per tool as `default_enabled is True` restated the literal three
lines above it: a tool could declare itself off, stay listed in `enabled_tools`, and every
test would still pass. What is asserted here is the *relation* instead, over every module in
`crossbid.tools` that exports a manifest, so a new tool is covered the day it is written
rather than the day someone remembers to add a test for it.

The two directions are not symmetric, deliberately:

* A **configured name with no module** is fine. `enabled_tools` already lists `search_ted`
  and `currency_convert`, which are Increment 4 stories — the file is the operator's
  intention, and it is allowed to run ahead of the code. `PENDING_TOOLS` names them, so a
  typo in the settings file is still caught.
* A **module whose flag disagrees with the file** is never fine, in either direction: an
  enabled tool declaring itself off understates what the agent can reach, and a disabled one
  declaring itself on is the panel telling an operator something the runtime will not do.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import pytest

import crossbid.tools
from crossbid.settings import Settings
from crossbid.tools import ToolManifest

PENDING_TOOLS = frozenset({"search_ted", "currency_convert"})
"""Listed in `enabled_tools` with no module yet; Increment 4 (S4 TED, currency)."""

BUILT_TOOLS = frozenset({"company_rag_search", "tender_rag_search", "ecertis_evidence_lookup"})
"""What discovery must find at minimum, so a sweep that finds nothing cannot pass silently."""


def _tool_modules() -> list[ModuleType]:
    """Every `crossbid.tools` submodule that exports a `MANIFEST`.

    Import-by-walk rather than a hand-kept list: the point of this file is to cover tools
    nobody remembered to list. `manifest.py` and `rag.py` are shared machinery and export
    none, so they drop out without being named.
    """
    modules = [
        importlib.import_module(f"{crossbid.tools.__name__}.{info.name}")
        for info in pkgutil.iter_modules(crossbid.tools.__path__)
    ]
    return [module for module in modules if hasattr(module, "MANIFEST")]


TOOL_MODULES = _tool_modules()


@pytest.fixture
def enabled_tools(offline_settings: Settings) -> tuple[str, ...]:
    return offline_settings.runtime.enabled_tools


@pytest.mark.parametrize("module", TOOL_MODULES, ids=lambda module: module.__name__)
def test_default_enabled_says_exactly_what_the_settings_file_says(
    module: ModuleType, enabled_tools: tuple[str, ...]
) -> None:
    """The flag is a claim about `enabled_tools`, so it is compared with `enabled_tools`."""
    # Arrange
    manifest = module.MANIFEST
    assert isinstance(manifest, ToolManifest)

    # Assert
    assert manifest.default_enabled == (manifest.name in enabled_tools), (
        f"{module.__name__} declares default_enabled={manifest.default_enabled} but "
        f"settings.default.yaml {'lists' if manifest.name in enabled_tools else 'omits'} "
        f"{manifest.name!r}"
    )


def test_the_sweep_covers_every_tool_that_exists() -> None:
    """Guards the guard: a discovery that silently found nothing would pass every test above."""
    # Act
    found = {module.MANIFEST.name for module in TOOL_MODULES}

    # Assert
    assert found >= BUILT_TOOLS, f"discovery missed {sorted(BUILT_TOOLS - found)}"
    assert len(found) == len(TOOL_MODULES), "two modules export the same tool name"


def test_every_configured_name_is_either_built_or_a_named_pending_story(
    enabled_tools: tuple[str, ...],
) -> None:
    """`enabled_tools` may run ahead of the code, but only on purpose — a typo is not ahead."""
    # Act
    unbuilt = set(enabled_tools) - {module.MANIFEST.name for module in TOOL_MODULES}

    # Assert
    assert unbuilt == set(PENDING_TOOLS) & set(enabled_tools), (
        "settings.default.yaml enables a tool no module provides and PENDING_TOOLS does not "
        f"name: {sorted(unbuilt - PENDING_TOOLS)}"
    )
