"""S1.4.1 — the registry: exactly the configured tools, built once, offline.

The story's first criterion is "given `enabled_tools`, when the graph builds, then only
those tools are bound", and this file is where that is proved. It is proved on the *list*
rather than on a model bound to it: `check_reqs` (S3.3.1) is the consumer and does not
exist, and `model.bind_tools(...)` is a langchain call whose result would tell us about
langchain, not about us. The thing S3.3.1 will pass to `bind_tools` is
`build_enabled_tools`'s return value, so that is what is asserted here — by name, in both
directions, because "the disabled tool is absent" is the half that actually constrains
what the agent may reach.

The tools are built for real, not faked. Building them opens no socket (`EmbeddingsClient`
connects lazily, the eCertis cache is committed JSON, and the two external tools construct
their HTTP client inside the call rather than in `build_tool`) and the database is
`conftest`'s recording source, so the registry's contract with each module — the
`build_tool(context)` shape — is exercised rather than described.

Two policies are pinned here because a later reader will otherwise assume the opposite:

* A **configured name with no module** is skipped and logged, never raised. The settings
  file is allowed to run ahead of the code -- `search_ted` and `currency_convert` both sat in
  it before they were written -- and a run must not die because an operator's YAML names next
  month's tool.
* A **tool that cannot be built for its context** propagates. `tender_rag_search` with no
  `bid_id` is the case, and it is a programming error in the caller, not a configuration:
  swallowing it would hand `check_reqs` a shorter tool list and a confident answer about a
  tender nobody read.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection, Sequence
from typing import Final

import pytest
from langchain_core.tools import BaseTool

from crossbid.settings import AppSettingsRow, Settings, apply_app_settings_row
from crossbid.tools.manifest import ToolContext, ToolManifest
from crossbid.tools.rag import RagToolError
from crossbid.tools.registry import (
    DISABLED_NEEDED_MESSAGE,
    UNBUILT_TOOLS_MESSAGE,
    build_enabled_tools,
    manifests,
    tool_entries,
    unbuilt_tool_names,
)
from tests.conftest import FakeConnectionSource

COMPANY_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
BID_ID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))

COMPANY_RAG = "company_rag_search"
TENDER_RAG = "tender_rag_search"
ECERTIS = "ecertis_evidence_lookup"
SEARCH_TED = "search_ted"
CURRENCY = "currency_convert"
GET_MATRIX = "get_matrix"

NOT_BUILT_YET = "haruspex_lookup"
"""A name no module provides — and, as of S1.3.1, an invented one.

This constant used to be a real story: `search_ted` played the part until S1.2.2 built it and
`currency_convert` until S1.3.1, and each time the name moved the tests below went on proving
the same thing. There is now nothing left in `enabled_tools` that is not built, so the next
substitution would be a lie of a different kind — a name that exists.

The policy, though, still has to be pinned: `build_enabled_tools` must skip a configured name
it cannot provide rather than raise, because the settings file is the operator's intention and
is allowed to run ahead of the code. So the name here is plainly fictional, and the tests that
use it put it into `enabled_tools` themselves (`with_tools`) instead of leaning on the shipped
file. That makes the coverage independent of what the settings happen to enable this month,
which is what let this constant go stale twice.
"""


def context(settings: Settings, *, bid_id: str | None = BID_ID) -> ToolContext:
    """A context every tool can be built for: a tenant, a bid, and a recording database."""
    return ToolContext(
        settings=settings, company_id=COMPANY_ID, bid_id=bid_id, db=FakeConnectionSource()
    )


def with_tools(settings: Settings, *names: str) -> Settings:
    """`settings` with `enabled_tools` replaced, through the same path the panel uses."""
    return apply_app_settings_row(settings, AppSettingsRow(enabled_tools=names))


def names_of(tools: Sequence[BaseTool]) -> tuple[str, ...]:
    return tuple(tool.name for tool in tools)


ANY_NODE: Final = "test_node"


def build_for(
    ctx: ToolContext, settings: Settings, *, needed: Collection[str] | None = None
) -> tuple[BaseTool, ...]:
    """`build_enabled_tools` with the node's key held wide open unless a test narrows it.

    Two keys decide whether a tool is built: `enabled_tools` (the operator's) and `needed`
    (the node's). Most tests in this file are about the operator's, so passing every tool
    that exists keeps them measuring one dimension; the tests under "the node's key" pass
    `needed` themselves.
    """
    every = {manifest.name for manifest in manifests()}
    return build_enabled_tools(
        ctx, settings, needed=every if needed is None else needed, caller=ANY_NODE
    )


# ------------------------------------------------------------------------- discovery


def test_discovery_finds_every_module_that_exports_a_manifest() -> None:
    """The shared sweep: `manifest.py` and `rag.py` carry none and must drop out."""
    # Act
    found = {entry.manifest.name for entry in tool_entries()}

    # Assert
    assert found == {COMPANY_RAG, TENDER_RAG, ECERTIS, SEARCH_TED, CURRENCY, GET_MATRIX}


def test_manifests_lists_the_tools_that_exist_not_the_ones_that_are_on() -> None:
    """The panel shows what could be reached, so a disabled tool is still in the list."""
    # Act
    listed = manifests()

    # Assert
    assert all(isinstance(manifest, ToolManifest) for manifest in listed)
    assert [manifest.name for manifest in listed] == sorted(
        manifest.name for manifest in listed
    ), "the catalogue order is ours, not the filesystem's"


def test_the_order_does_not_follow_the_settings_file(offline_settings: Settings) -> None:
    """Reordering `enabled_tools` must not change what the model is shown, only what it is."""
    # Arrange
    forwards = with_tools(offline_settings, COMPANY_RAG, ECERTIS)
    backwards = with_tools(offline_settings, ECERTIS, COMPANY_RAG)

    # Act
    built = [names_of(build_for(context(s), s)) for s in (forwards, backwards)]

    # Assert
    assert built[0] == built[1] == (COMPANY_RAG, ECERTIS)


# ---------------------------------------------------------- only the configured tools


def test_only_the_configured_tools_are_built(offline_settings: Settings) -> None:
    """The story's first criterion, stated positively."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, TENDER_RAG)

    # Act
    tools = build_for(context(settings), settings)

    # Assert
    assert names_of(tools) == (ECERTIS, TENDER_RAG)


def test_a_tool_left_out_of_enabled_tools_is_not_built(offline_settings: Settings) -> None:
    """The same criterion stated negatively, which is the half that constrains the agent."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act
    tools = build_for(context(settings), settings)

    # Assert
    assert COMPANY_RAG not in names_of(tools)
    assert TENDER_RAG not in names_of(tools)


def test_no_enabled_tools_means_no_tools(offline_settings: Settings) -> None:
    """An operator may switch everything off; that is a configuration, not a failure."""
    # Arrange
    settings = with_tools(offline_settings)

    # Act & Assert
    assert build_for(context(settings), settings) == ()


def test_a_name_listed_twice_is_built_once(offline_settings: Settings) -> None:
    """`enabled_tools` is a set of permissions; a repeat is a typo, not two tools."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, ECERTIS)

    # Act
    tools = build_for(context(settings), settings)

    # Assert
    assert names_of(tools) == (ECERTIS,)


def test_the_built_tools_are_the_real_ones(offline_settings: Settings) -> None:
    """Not a name check: the descriptions the model is bound with come from the manifests."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act
    tool = build_for(context(settings), settings)[0]

    # Assert
    by_name = {manifest.name: manifest for manifest in manifests()}
    assert tool.description == by_name[ECERTIS].description


# ------------------------------------------------------- configured but not built yet


def test_a_configured_name_with_no_module_is_skipped(offline_settings: Settings) -> None:
    """The shipped file has none of these today; the policy is what must not take a run down."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, NOT_BUILT_YET)

    # Act
    tools = build_for(context(settings), settings)

    # Assert
    assert names_of(tools) == (ECERTIS,)


def test_the_skipped_name_is_logged_once_at_info(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Disabled and not-built-yet look identical in the panel unless the log says which."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, NOT_BUILT_YET)

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.tools.registry"):
        build_for(context(settings), settings)

    # Assert
    records = [record for record in caplog.records if record.msg == UNBUILT_TOOLS_MESSAGE]
    assert len(records) == 1
    assert NOT_BUILT_YET in records[0].getMessage()


def test_nothing_is_logged_when_every_configured_tool_exists(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """A clean configuration is silent: a line per run is noise a reader learns to skip."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.tools.registry"):
        build_for(context(settings), settings)

    # Assert
    assert [record for record in caplog.records if record.msg == UNBUILT_TOOLS_MESSAGE] == []


def test_unbuilt_names_are_the_configured_ones_no_module_provides(
    offline_settings: Settings,
) -> None:
    """What the panel prints as "configured, not built".

    Empty against the settings file as shipped, which is S1.3.1's doing: every name in
    `enabled_tools` is now a module. Both halves are asserted, because "nothing is missing"
    and "the function found nothing" are the same tuple and only the second is a bug.
    """
    # Arrange
    with_a_gap = with_tools(offline_settings, ECERTIS, NOT_BUILT_YET)

    # Act & Assert
    assert unbuilt_tool_names(offline_settings) == ()
    assert unbuilt_tool_names(with_a_gap) == (NOT_BUILT_YET,)


def test_a_built_tool_that_is_switched_off_is_not_called_unbuilt(
    offline_settings: Settings,
) -> None:
    """Disabled and missing are different answers and the panel must not merge them."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act & Assert
    assert unbuilt_tool_names(settings) == ()


# ------------------------------------------------------- a tool that cannot be built


def test_a_tool_that_cannot_be_built_for_its_context_is_not_swallowed(
    offline_settings: Settings,
) -> None:
    """A tender search with no bid would read every bid's pack, so the run stops here."""
    # Arrange
    settings = with_tools(offline_settings, TENDER_RAG)

    # Act & Assert
    with pytest.raises(RagToolError, match="bid_id"):
        build_for(context(settings, bid_id=None), settings)


def test_the_tools_are_built_eagerly_so_the_failure_lands_here(
    offline_settings: Settings,
) -> None:
    """A lazily built list would raise inside the ReAct loop instead, hundreds of
    requirements in and with a tender's name in the traceback. One healthy tool ahead of
    the broken one must not defer it."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, TENDER_RAG)

    # Act & Assert
    with pytest.raises(RagToolError):
        build_for(context(settings, bid_id=None), settings)


# --------------------------------------------------------------- the node's key (ADR-0052)


def test_a_tool_the_node_does_not_need_is_not_built_though_it_is_enabled(
    offline_settings: Settings,
) -> None:
    """The failure ADR-0052 exists to stop: `search_ted` was enabled, so the check loop
    bound it, so a live network search sat inside a loop that runs once per requirement."""
    # Arrange
    settings = with_tools(offline_settings, COMPANY_RAG, ECERTIS, SEARCH_TED)

    # Act
    tools = build_for(context(settings), settings, needed={COMPANY_RAG, ECERTIS})

    # Assert
    assert names_of(tools) == (COMPANY_RAG, ECERTIS)


def test_the_operator_still_wins_over_a_node_that_asks_for_a_disabled_tool(
    offline_settings: Settings,
) -> None:
    """Both keys must turn. A node may not re-enable what a deployment switched off —
    `enabled_tools` is the operator's intention and code does not overrule it (ADR-0045)."""
    # Arrange
    settings = with_tools(offline_settings, COMPANY_RAG)

    # Act
    tools = build_for(context(settings), settings, needed={COMPANY_RAG, ECERTIS})

    # Assert
    assert names_of(tools) == (COMPANY_RAG,)


def test_asking_for_a_disabled_tool_says_so_in_the_log(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """ "Found no evidence" and "could not look" read alike in a matrix; not in a log."""
    # Arrange
    settings = with_tools(offline_settings, COMPANY_RAG)

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.tools.registry"):
        build_for(context(settings), settings, needed={COMPANY_RAG, ECERTIS})

    # Assert
    records = [r for r in caplog.records if r.msg == DISABLED_NEEDED_MESSAGE]
    assert len(records) == 1
    assert records[0].args == (ANY_NODE, ECERTIS)


def test_a_node_asking_for_a_tool_that_does_not_exist_raises(
    offline_settings: Settings,
) -> None:
    """The opposite of how an unknown name in `enabled_tools` is treated, on purpose.

    That file is the operator's and may name next month's tool; `needed` is written in this
    repository, so a name matching nothing is a typo no deployment can fix.
    """
    # Act & Assert
    with pytest.raises(ValueError, match="compayn_rag_search"):
        build_for(context(offline_settings), offline_settings, needed={"compayn_rag_search"})


def test_the_check_node_asks_for_tools_that_all_exist(offline_settings: Settings) -> None:
    """`CHECK_TOOLS` is a set of strings; nothing but a test connects it to real modules."""
    # Arrange
    from crossbid.agent.nodes.check_reqs import CHECK_TOOLS

    # Act & Assert
    assert {manifest.name for manifest in manifests()} >= CHECK_TOOLS


def test_the_check_node_does_not_ask_for_the_tender_search(offline_settings: Settings) -> None:
    """Stated as its own test because it is the whole point of the constant, and a future
    edit that adds it back should fail here rather than in a slow live run."""
    # Arrange
    from crossbid.agent.nodes.check_reqs import CHECK_TOOLS

    # Act & Assert
    assert SEARCH_TED not in CHECK_TOOLS
