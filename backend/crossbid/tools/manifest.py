"""What a tool declares about itself, and what it is handed when it is built.

Two small objects, deliberately in their own module so a tool can import them without
importing its siblings -- the registry (S1.4.1) is the only thing that imports all of them.

`ToolManifest` is the operator-facing half: `GET /dev/settings` lists these so that the
developer panel can show what the agent may reach without reading the code. `external` is
the field that matters there -- it says the tool opens a socket, which is the difference
between "slow and costed" and "offline and free", and between a tool an operator may leave
on and one they may want off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to the type checker
    from crossbid.db import ConnectionSource
    from crossbid.ingestion.embeddings import EmbeddingsClient
    from crossbid.settings import Settings

ToolName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
"""Snake case, because the name is what the model types into a tool call."""


class ToolManifest(BaseModel):
    """One tool's self-description. The registry reads it; the developer panel shows it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: ToolName
    description: str = Field(min_length=1)
    """Written for the model, not for us: this is the text that decides whether it calls."""
    external: bool
    """True when a call leaves the process. Cached reference data is False."""
    default_enabled: bool
    """Whether `settings.default.yaml` lists it in `enabled_tools`.

    A claim about another file, so it is worth nothing unless something compares the two:
    `tests/unit/test_tool_manifests.py` asserts the equality over every module in this
    package, in both directions. The flag is duplicated here rather than read from the
    settings at import time because the panel describes the tool, not this process's
    configuration — an operator who has switched the tool off should still see that it ships
    on by default."""


@dataclass(frozen=True, slots=True)
class ToolContext:
    """The scope a tool is built for. Never a global -- one per run, per company.

    `bid_id` is `None` for tools that do not read tender text (the eCertis lookup, currency
    conversion); a tool that needs it says so by raising when it is absent rather than
    quietly searching every bid. `db` is `None` in the same spirit: a tool that reads
    Postgres cannot be built without a connection source.

    `embedder` is the odd one out: it is not scope but a *resource*, and it is here because
    the scope object is the only thing `registry.build_enabled_tools` hands a tool. Both RAG
    tools embed their query and both take an injectable client (S2.4.2); without this field
    each would build its own and open its own `httpx` pool, closed by garbage collection.
    The alternative -- a parameter on `build_enabled_tools` -- would put one pair of tools'
    resource into the registry's signature for every future tool to ignore. `None` keeps the
    old behaviour, so nothing that builds a context for a single call has to change. The
    consumer that fills it is `check_reqs` (S3.3.1), which opens one client per lane.
    """

    settings: Settings
    company_id: str
    bid_id: str | None = None
    db: ConnectionSource | None = None
    embedder: EmbeddingsClient | None = None
