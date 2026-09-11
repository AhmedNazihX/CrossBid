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

The sweep is `registry.tool_entries()`, not a walk of its own (S1.4.1). The registry already
has to discover every tool in order to build the enabled ones, and a second discovery here
could drift from it -- this file would then prove something true of a set of modules nobody
binds. Importing the registry's makes the relation exact: what is asserted below is asserted
about precisely the modules the agent can reach.
"""

from __future__ import annotations

import pytest

from crossbid.settings import Settings
from crossbid.tools.registry import ToolEntry, tool_entries

PENDING_TOOLS = frozenset({"search_ted", "currency_convert"})
"""Listed in `enabled_tools` with no module yet; Increment 4 (S4 TED, currency)."""

BUILT_TOOLS = frozenset({"company_rag_search", "tender_rag_search", "ecertis_evidence_lookup"})
"""What discovery must find at minimum, so a sweep that finds nothing cannot pass silently."""


TOOL_ENTRIES = tool_entries()
"""The registry's own discovery: every `crossbid.tools` module exporting a `MANIFEST`.

Import-by-walk rather than a hand-kept list, because the point of this file is to cover
tools nobody remembered to list. `manifest.py`, `rag.py` and `registry.py` are shared
machinery and export no manifest, so they drop out without being named.
"""


@pytest.fixture
def enabled_tools(offline_settings: Settings) -> tuple[str, ...]:
    return offline_settings.runtime.enabled_tools


@pytest.mark.parametrize("entry", TOOL_ENTRIES, ids=lambda entry: entry.module.__name__)
def test_default_enabled_says_exactly_what_the_settings_file_says(
    entry: ToolEntry, enabled_tools: tuple[str, ...]
) -> None:
    """The flag is a claim about `enabled_tools`, so it is compared with `enabled_tools`."""
    # Arrange
    manifest = entry.manifest

    # Assert
    assert manifest.default_enabled == (manifest.name in enabled_tools), (
        f"{entry.module.__name__} declares default_enabled={manifest.default_enabled} but "
        f"settings.default.yaml {'lists' if manifest.name in enabled_tools else 'omits'} "
        f"{manifest.name!r}"
    )


def test_the_sweep_covers_every_tool_that_exists() -> None:
    """Guards the guard: a discovery that silently found nothing would pass every test above."""
    # Act
    found = {entry.manifest.name for entry in TOOL_ENTRIES}

    # Assert
    assert found >= BUILT_TOOLS, f"discovery missed {sorted(BUILT_TOOLS - found)}"
    assert len(found) == len(TOOL_ENTRIES), "two modules export the same tool name"


def test_every_configured_name_is_either_built_or_a_named_pending_story(
    enabled_tools: tuple[str, ...],
) -> None:
    """`enabled_tools` may run ahead of the code, but only on purpose — a typo is not ahead."""
    # Act
    unbuilt = set(enabled_tools) - {entry.manifest.name for entry in TOOL_ENTRIES}

    # Assert
    assert unbuilt == set(PENDING_TOOLS) & set(enabled_tools), (
        "settings.default.yaml enables a tool no module provides and PENDING_TOOLS does not "
        f"name: {sorted(unbuilt - PENDING_TOOLS)}"
    )
