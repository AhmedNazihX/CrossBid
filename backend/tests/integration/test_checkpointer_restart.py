"""S0.2.2's acceptance criterion: a graph's state survives an API restart.

Marked `live` because it needs Postgres. The DSN is resolved exactly as the API resolves
it -- `load_settings()`: the process environment first (CI's backend job exports the
pgvector service), the repository-root `.env` second (`make test-live` on a developer's
machine, against the Supabase project). With no `DATABASE_URL` either way the test skips
rather than fail on a machine without one.

A "restart" here is the whole `Database` being closed and a fresh one opened, which is
exactly what the lifespan does: no object survives, only rows. Both memories are checked --
the checkpointer (a thread's graph state) and the Store (a company's long-term facts).
"""

from __future__ import annotations

import uuid
from typing import Annotated, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from crossbid.db import Database
from crossbid.settings import SettingsError, bid_run_config, load_settings

pytestmark = pytest.mark.live


def resolve_dsn() -> str | None:
    try:
        url = load_settings().env.database_url
    except SettingsError:
        return None
    return None if url is None else url.get_secret_value()


DSN = resolve_dsn()
skip_without_database = pytest.mark.skipif(DSN is None, reason="DATABASE_URL is not set")


def _append(left: list[str], right: list[str]) -> list[str]:
    return left + right


class TinyState(TypedDict):
    steps: Annotated[list[str], _append]


def build_graph(db: Database):
    """The smallest graph that writes a checkpoint: one node, one appended step."""

    def record(_state: TinyState) -> dict[str, list[str]]:
        return {"steps": ["ran"]}

    graph = StateGraph(TinyState)
    graph.add_node("record", record)
    graph.add_edge(START, "record")
    graph.add_edge("record", END)
    return graph.compile(checkpointer=db.checkpointer)


async def open_database() -> Database:
    assert DSN is not None
    db = await Database.connect(DSN, min_size=0, max_size=2)
    await db.setup()
    return db


@skip_without_database
@pytest.mark.anyio
async def test_a_checkpoint_and_a_store_item_survive_a_restart() -> None:
    bid_id = uuid.uuid4()
    thread_id = f"bid:{bid_id}"
    config = bid_run_config(bid_id, thread_id=thread_id)
    namespace = ("profile", f"test-{bid_id}")

    # Arrange -- first process: run the graph and remember one long-term fact
    first = await open_database()
    try:
        result = await build_graph(first).ainvoke({"steps": []}, config)
        assert result["steps"] == ["ran"]
        await first.store.aput(namespace, "country", {"value": "DE"})
    finally:
        await first.close()

    # Act -- the "restart": nothing in memory survives, only what Postgres holds
    second = await open_database()
    try:
        state = await build_graph(second).aget_state(config)
        item = await second.store.aget(namespace, "country")

        # Assert
        assert state.values["steps"] == ["ran"]
        assert state.next == ()
        assert state.metadata is not None
        assert item is not None
        assert item.value == {"value": "DE"}
    finally:
        # Clean up so the shared project does not accumulate test threads.
        await second.checkpointer.adelete_thread(thread_id)
        await second.store.adelete(namespace, "country")
        await second.close()


@skip_without_database
@pytest.mark.anyio
async def test_setup_is_idempotent_and_the_vector_type_is_registered() -> None:
    """Two starts in a row apply nothing twice, and a borrowed connection understands
    `vector` -- which is what `_register_types` exists for."""
    db = await open_database()
    try:
        await db.setup()  # second call on the same tables
        async with db.connection() as conn:
            row = await (
                await conn.execute("select '[1,2,3]'::vector as v, 1 as one")
            ).fetchone()
        assert row is not None
        assert row["one"] == 1
        # A `Vector`, not a string: proof the adapter ran on this pooled connection.
        assert type(row["v"]).__name__ == "Vector"
        assert row["v"].to_list() == [1.0, 2.0, 3.0]
    finally:
        await db.close()
