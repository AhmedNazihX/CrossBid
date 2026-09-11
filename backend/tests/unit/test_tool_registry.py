"""S1.4.1 — the registry: exactly the configured tools, built once, offline.

The story's first criterion is "given `enabled_tools`, when the graph builds, then only
those tools are bound", and this file is where that is proved. It is proved on the *list*
rather than on a model bound to it: `check_reqs` (S3.3.1) is the consumer and does not
exist, and `model.bind_tools(...)` is a langchain call whose result would tell us about
langchain, not about us. The thing S3.3.1 will pass to `bind_tools` is
`build_enabled_tools`'s return value, so that is what is asserted here — by name, in both
directions, because "the disabled tool is absent" is the half that actually constrains
what the agent may reach.

The three tools are built for real, not faked. Building them opens no socket
(`EmbeddingsClient` connects lazily, the eCertis cache is committed JSON) and the database
is `conftest`'s recording source, so the registry's contract with each module — the
`build_tool(context)` shape — is exercised rather than described.

Two policies are pinned here because a later reader will otherwise assume the opposite:

* A **configured name with no module** is skipped and logged, never raised. The settings
  file is allowed to run ahead of the code (`search_ted` and `currency_convert` are
  Increment 4) and a run must not die because an operator's YAML names next month's tool.
* A **tool that cannot be built for its context** propagates. `tender_rag_search` with no
  `bid_id` is the case, and it is a programming error in the caller, not a configuration:
  swallowing it would hand `check_reqs` a shorter tool list and a confident answer about a
  tender nobody read.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

import pytest
from langchain_core.tools import BaseTool

from crossbid.settings import AppSettingsRow, Settings, apply_app_settings_row
from crossbid.tools.manifest import ToolContext, ToolManifest
from crossbid.tools.rag import RagToolError
from crossbid.tools.registry import (
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
NOT_BUILT_YET = "search_ted"
"""In `settings.default.yaml`'s `enabled_tools`, with no module until Increment 4."""


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


# ------------------------------------------------------------------------- discovery


def test_discovery_finds_every_module_that_exports_a_manifest() -> None:
    """The shared sweep: `manifest.py` and `rag.py` carry none and must drop out."""
    # Act
    found = {entry.manifest.name for entry in tool_entries()}

    # Assert
    assert found == {COMPANY_RAG, TENDER_RAG, ECERTIS}


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
    built = [names_of(build_enabled_tools(context(s), s)) for s in (forwards, backwards)]

    # Assert
    assert built[0] == built[1] == (COMPANY_RAG, ECERTIS)


# ---------------------------------------------------------- only the configured tools


def test_only_the_configured_tools_are_built(offline_settings: Settings) -> None:
    """The story's first criterion, stated positively."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, TENDER_RAG)

    # Act
    tools = build_enabled_tools(context(settings), settings)

    # Assert
    assert names_of(tools) == (ECERTIS, TENDER_RAG)


def test_a_tool_left_out_of_enabled_tools_is_not_built(offline_settings: Settings) -> None:
    """The same criterion stated negatively, which is the half that constrains the agent."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act
    tools = build_enabled_tools(context(settings), settings)

    # Assert
    assert COMPANY_RAG not in names_of(tools)
    assert TENDER_RAG not in names_of(tools)


def test_no_enabled_tools_means_no_tools(offline_settings: Settings) -> None:
    """An operator may switch everything off; that is a configuration, not a failure."""
    # Arrange
    settings = with_tools(offline_settings)

    # Act & Assert
    assert build_enabled_tools(context(settings), settings) == ()


def test_a_name_listed_twice_is_built_once(offline_settings: Settings) -> None:
    """`enabled_tools` is a set of permissions; a repeat is a typo, not two tools."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, ECERTIS)

    # Act
    tools = build_enabled_tools(context(settings), settings)

    # Assert
    assert names_of(tools) == (ECERTIS,)


def test_the_built_tools_are_the_real_ones(offline_settings: Settings) -> None:
    """Not a name check: the descriptions the model is bound with come from the manifests."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS)

    # Act
    tool = build_enabled_tools(context(settings), settings)[0]

    # Assert
    by_name = {manifest.name: manifest for manifest in manifests()}
    assert tool.description == by_name[ECERTIS].description


# ------------------------------------------------------- configured but not built yet


def test_a_configured_name_with_no_module_is_skipped(offline_settings: Settings) -> None:
    """`settings.default.yaml` ships with two of these; neither may take a run down."""
    # Arrange
    settings = with_tools(offline_settings, ECERTIS, NOT_BUILT_YET)

    # Act
    tools = build_enabled_tools(context(settings), settings)

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
        build_enabled_tools(context(settings), settings)

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
        build_enabled_tools(context(settings), settings)

    # Assert
    assert [record for record in caplog.records if record.msg == UNBUILT_TOOLS_MESSAGE] == []


def test_unbuilt_names_are_the_configured_ones_no_module_provides(
    offline_settings: Settings,
) -> None:
    """What the panel prints as "configured, not built" — the settings file as shipped."""
    # Act
    unbuilt = unbuilt_tool_names(offline_settings)

    # Assert
    assert unbuilt == ("currency_convert", "search_ted")


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
        build_enabled_tools(context(settings, bid_id=None), settings)


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
        build_enabled_tools(context(settings, bid_id=None), settings)
