"""S1.4.1 — which tools the agent may reach, decided in settings rather than in a deploy.

One discovery, one build, one catalogue. `crossbid.tools` is walked for modules exporting a
`MANIFEST`, `build_enabled_tools` builds exactly those `settings.runtime.enabled_tools`
names, and `manifests()` lists every tool that exists so the developer panel can show what
is off as well as what is on. `check_reqs` (F3.3) is the consumer: the list this returns is
what it hands to `bind_tools`, and it is the *only* place that turns configuration into a
tool list, so no node gets to re-decide what the agent may call.

**Discovery is a walk, not a list.** A hand-kept registry is the kind of file everyone
forgets: a tool would be written, tested, and silently never bound. Walking the package
means a module is registered by existing. `tests/unit/test_tool_manifests.py` imports
`tool_entries` from here rather than repeating the walk, so the sweep that proves each
manifest against `settings.default.yaml` covers exactly the set this builds from.

**Order is ours, not the settings file's.** Entries are sorted by tool name and the build
follows that order, so reordering `enabled_tools` changes *which* tools the model is bound
with and never in which order it is shown them. An operator's line order is incidental; a
stable tool list keeps one bid's prompt identical to the next's.

**A configured name with no module is skipped, not raised.** `settings.default.yaml`
already enables `search_ted` (S1.2.2) and `currency_convert` (S1.3.1), which land in
Increment 4: the settings file is the operator's intention and is allowed to run ahead of
the code. At run time a typo (`companyrag_search`) and a not-yet-built story are the same
observation — a name nothing provides — so there is nothing here that could tell them
apart, and refusing would mean a run dies because the YAML names next month's tool. Hence a
warning-shaped fact logged at info: "the agent is not reaching these" is worth saying out
loud, and it is what makes "disabled" distinguishable from "not built yet" in the log as
well as in the panel. The typo is caught at *test* time instead, by
`test_every_configured_name_is_either_built_or_a_named_pending_story` in
`test_tool_manifests.py`, which compares `enabled_tools` with the modules that exist and
allows only the two names it lists as pending.

**A tool that cannot be built for its context propagates.** `tender_rag_search` raises
`RagToolError` when its `ToolContext` carries no `bid_id`, and `company_rag_search` when it
carries no database. Skipping those with a log was considered and rejected: the tools the
registry drops silently would be exactly the ones `check_reqs` cannot work without, and the
run would carry on and answer "no evidence found" for every requirement in a tender it never
searched — a wrong answer indistinguishable from a right one, which is the failure mode this
whole codebase is arranged against. All three build failures are programming errors in the
*caller* (no bid, no pool, a malformed UUID), not operator configuration, so they belong
where a developer sees them. The build is eager for the same reason: a generator would
defer the failure into the ReAct loop, hundreds of requirements later.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType
from typing import Final

from langchain_core.tools import BaseTool

import crossbid.tools
from crossbid.settings import Settings
from crossbid.tools.manifest import ToolContext, ToolManifest

logger = logging.getLogger(__name__)

MANIFEST_ATTRIBUTE: Final = "MANIFEST"
BUILDER_ATTRIBUTE: Final = "build_tool"

UNBUILT_TOOLS_MESSAGE: Final = (
    "enabled_tools names %s, which no module in crossbid.tools provides, so the agent will "
    "not reach them. Expected for a story that has not landed yet; otherwise it is a typo in "
    "the settings file."
)
"""Logged once per build, with every missing name in one line. A module constant so the
test can match the record without restating the sentence."""


@dataclass(frozen=True, slots=True)
class ToolEntry:
    """One discovered tool module: what it says about itself, and how to build it.

    The module is kept so that a failure can name the file and so `test_tool_manifests.py`
    can parameterise by it; the builder is pulled out because that is the whole contract —
    `build_tool(context) -> BaseTool`, keyword arguments optional (the RAG tools take an
    injectable embedder the registry never passes).
    """

    manifest: ToolManifest
    build: Callable[[ToolContext], BaseTool]
    module: ModuleType


@lru_cache(maxsize=1)
def tool_entries() -> tuple[ToolEntry, ...]:
    """Every `crossbid.tools` submodule exporting a `MANIFEST`, sorted by tool name.

    Cached: the walk imports each module, which is idempotent, and the answer cannot change
    within a process. A module exporting a manifest but no `build_tool` raises
    `AttributeError` here rather than at the first build — the contract is stated in
    `crossbid/tools/__init__.py` and a half-written tool should fail on the way in.
    """
    entries: list[ToolEntry] = []
    for info in pkgutil.iter_modules(crossbid.tools.__path__):
        module = importlib.import_module(f"{crossbid.tools.__name__}.{info.name}")
        manifest = getattr(module, MANIFEST_ATTRIBUTE, None)
        if not isinstance(manifest, ToolManifest):
            continue  # shared machinery: `manifest.py`, `rag.py`, this module.
        build: Callable[[ToolContext], BaseTool] = getattr(module, BUILDER_ATTRIBUTE)
        entries.append(ToolEntry(manifest=manifest, build=build, module=module))
    return tuple(sorted(entries, key=lambda entry: entry.manifest.name))


def manifests() -> tuple[ToolManifest, ...]:
    """Every manifest, enabled or not — the catalogue `GET /dev/settings` lists.

    Not filtered by `enabled_tools` on purpose: an operator who cannot see a disabled tool
    cannot switch it back on, and cannot tell it apart from one that was never built.
    """
    return tuple(entry.manifest for entry in tool_entries())


def enabled_tool_names(settings: Settings) -> frozenset[str]:
    """`enabled_tools` as a set: the one definition of "the agent may call this".

    Shared with `routers/dev.py`, which reports the same predicate as each manifest's
    `enabled` flag. Two copies of a membership test is one copy too many the day the rule
    grows a second clause -- the panel would then describe a permission the graph does not
    honour, which is the exact failure `default_enabled` already exists to avoid.
    """
    return frozenset(settings.runtime.enabled_tools)


def unbuilt_tool_names(settings: Settings) -> tuple[str, ...]:
    """Configured names no module provides, sorted and deduplicated.

    The panel prints these as "configured, not built" rather than dropping them, so that an
    operator reading the settings file and the panel side by side sees the same five names.
    """
    known = {entry.manifest.name for entry in tool_entries()}
    return tuple(sorted(enabled_tool_names(settings) - known))


def build_enabled_tools(context: ToolContext, settings: Settings) -> tuple[BaseTool, ...]:
    """The tools the agent may call in this run: exactly `enabled_tools`, built for `context`.

    The story's first criterion lives here — "given `enabled_tools`, when the graph builds,
    then only those tools are bound" — and the tuple is what `check_reqs` passes to
    `bind_tools`. Repeats in the configuration collapse (a permission list, not a
    multiset), unknown names are logged and skipped, and a tool that refuses its context
    raises. See the module docstring for why each of those is the way round it is.
    """
    unbuilt = unbuilt_tool_names(settings)
    if unbuilt:
        logger.info(UNBUILT_TOOLS_MESSAGE, ", ".join(unbuilt))
    enabled = enabled_tool_names(settings)
    return tuple(
        entry.build(context) for entry in tool_entries() if entry.manifest.name in enabled
    )
