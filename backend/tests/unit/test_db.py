"""The pool and the LangGraph clients built on it (S0.2.2).

Every test is offline. `Database.connect` takes a `pool_factory`, so a recording fake stands
in for `AsyncConnectionPool` and nothing opens a socket; the checkpointer and Store are real
objects handed that fake pool, and `setup()` is exercised against a recording connection.
The acceptance criterion that needs Postgres -- state surviving a restart -- is the `live`
test in `tests/integration/test_checkpointer_restart.py`.

Fixtures are module-local: `conftest.py` is shared ground.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from crossbid import db as db_module
from crossbid.db import (
    CONNECTIONS_AVAILABLE_TO_US,
    DEFAULT_MAX_POOL_SIZE,
    DEFAULT_MIN_POOL_SIZE,
    MAX_POOL_SIZE_CEILING,
    PLATFORM_BASELINE_SESSIONS,
    SETUP_ADVISORY_LOCK_KEY,
    SUPABASE_MAX_CONNECTIONS,
    SUPABASE_RESERVED_CONNECTIONS,
    Database,
    DatabaseError,
    check_pool_size,
    pool_connection_kwargs,
)
from crossbid.settings import SettingsError

# Distinctive, so a leak into an exception message is unmistakable.
FAKE_PASSWORD = "LEAKED-DATABASE-PASSWORD"
GOOD_DSN = f"postgresql://crossbid:{FAKE_PASSWORD}@localhost:5432/crossbid"
TRANSACTION_POOLER_DSN = (
    f"postgresql://postgres.ref:{FAKE_PASSWORD}@aws-0-eu-central-1.pooler.supabase.com:6543/db"
)

SIGNED_64_BIT_MAX = 2**63 - 1


# -------------------------------------------------------------------------- fakes


@dataclass
class RecordingConnection:
    """Records every `execute` so a test can assert order and parameters."""

    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, query: str, params: Any = None) -> RecordingConnection:
        self.executed.append((query, params))
        return self


@dataclass
class FakePool:
    """Stands in for `AsyncConnectionPool`: records how it was built and driven."""

    conninfo: str
    kwargs: dict[str, Any]
    min_size: int
    max_size: int
    configure: Any
    open_flag: bool | None
    opened_with: dict[str, Any] | None = None
    closed: bool = False
    fail_open_with: Exception | None = None
    lent: RecordingConnection = field(default_factory=RecordingConnection)

    # `timeout` mirrors `AsyncConnectionPool.open`, which is the signature under test.
    async def open(self, *, wait: bool, timeout: float) -> None:  # noqa: ASYNC109
        if self.fail_open_with is not None:
            raise self.fail_open_with
        self.opened_with = {"wait": wait, "timeout": timeout}

    async def close(self) -> None:
        self.closed = True

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[RecordingConnection]:
        yield self.lent


class FakePoolFactory:
    """`pool_factory` seam: builds `FakePool`s and keeps the last one for assertions."""

    def __init__(self, *, fail_open_with: Exception | None = None) -> None:
        self.fail_open_with = fail_open_with
        self.built: list[FakePool] = []

    def __call__(self, conninfo: str, **kwargs: Any) -> Any:
        pool = FakePool(
            conninfo=conninfo,
            kwargs=kwargs["kwargs"],
            min_size=kwargs["min_size"],
            max_size=kwargs["max_size"],
            configure=kwargs["configure"],
            open_flag=kwargs["open"],
            fail_open_with=self.fail_open_with,
        )
        self.built.append(pool)
        return pool

    @property
    def last(self) -> FakePool:
        assert self.built, "no pool was built"
        return self.built[-1]


async def noop_configure(_conn: Any) -> None:
    """Stands in for `register_vector_async`, which needs a live connection."""


async def connect(factory: FakePoolFactory, **overrides: Any) -> Database:
    return await Database.connect(
        GOOD_DSN, pool_factory=factory, configure=noop_configure, **overrides
    )


# -------------------------------------------------------------- sizing the pool


def test_the_budget_is_derived_from_the_measured_project_limits() -> None:
    """The numbers are pinned: if the project changes, the test must be changed knowingly."""
    assert SUPABASE_MAX_CONNECTIONS == 60
    assert SUPABASE_RESERVED_CONNECTIONS == 3
    assert PLATFORM_BASELINE_SESSIONS == 12
    assert CONNECTIONS_AVAILABLE_TO_US == 45
    assert MAX_POOL_SIZE_CEILING == 22


def test_the_default_pool_leaves_room_for_a_second_process() -> None:
    """Compose and `make dev-api` side by side must both fit, plus the migration runner."""
    assert DEFAULT_MIN_POOL_SIZE <= DEFAULT_MAX_POOL_SIZE
    assert DEFAULT_MAX_POOL_SIZE <= MAX_POOL_SIZE_CEILING
    assert 2 * DEFAULT_MAX_POOL_SIZE < CONNECTIONS_AVAILABLE_TO_US


@pytest.mark.parametrize(
    ("min_size", "max_size"),
    [
        pytest.param(0, 1, id="lazy-pool"),
        pytest.param(1, DEFAULT_MAX_POOL_SIZE, id="defaults"),
        pytest.param(MAX_POOL_SIZE_CEILING, MAX_POOL_SIZE_CEILING, id="at-the-ceiling"),
    ],
)
def test_accepted_pool_sizes(min_size: int, max_size: int) -> None:
    check_pool_size(min_size, max_size)


@pytest.mark.parametrize(
    ("min_size", "max_size", "fragment"),
    [
        pytest.param(-1, 5, "min_size", id="negative-min"),
        pytest.param(0, 0, "max_size > 0", id="zero-max"),
        pytest.param(5, 4, "min_size <= max_size", id="min-above-max"),
        pytest.param(1, MAX_POOL_SIZE_CEILING + 1, "coexist", id="over-the-ceiling"),
        pytest.param(1, SUPABASE_MAX_CONNECTIONS, "coexist", id="the-whole-server"),
    ],
)
def test_refused_pool_sizes_name_the_rule(min_size: int, max_size: int, fragment: str) -> None:
    with pytest.raises(DatabaseError) as caught:
        check_pool_size(min_size, max_size)
    assert fragment in str(caught.value)


def test_the_ceiling_message_shows_its_arithmetic() -> None:
    """An operator reading the error should not have to open the source to see why 22."""
    with pytest.raises(DatabaseError) as caught:
        check_pool_size(1, MAX_POOL_SIZE_CEILING + 1)
    message = str(caught.value)
    for number in (
        SUPABASE_MAX_CONNECTIONS,
        SUPABASE_RESERVED_CONNECTIONS,
        PLATFORM_BASELINE_SESSIONS,
        CONNECTIONS_AVAILABLE_TO_US,
        MAX_POOL_SIZE_CEILING,
    ):
        assert str(number) in message


# ------------------------------------------------------- per-connection settings


def test_every_connection_is_autocommit_dict_row_and_prepared() -> None:
    kwargs = pool_connection_kwargs()
    assert kwargs["autocommit"] is True
    assert kwargs["row_factory"] is dict_row
    assert kwargs["prepare_threshold"] == 0
    assert kwargs["connect_timeout"] > 0


def test_connection_kwargs_are_a_fresh_dict_each_time() -> None:
    """psycopg mutates the mapping it is handed; sharing one would leak between pools."""
    first, second = pool_connection_kwargs(), pool_connection_kwargs()
    assert first == second
    assert first is not second


# --------------------------------------------------------- the real pool class


def test_the_default_factory_builds_a_closed_dict_row_pool() -> None:
    """Constructing with `open=False` opens no socket, so the real class can be exercised."""
    # Act
    pool = db_module._default_pool_factory(
        GOOD_DSN, kwargs=pool_connection_kwargs(), min_size=0, max_size=3, open=False
    )

    # Assert
    assert isinstance(pool, AsyncConnectionPool)
    assert pool.closed is True
    assert pool.max_size == 3
    assert pool.connection_class is AsyncConnection[DictRow]
    assert pool.kwargs["row_factory"] is dict_row


# ----------------------------------------------------------------- connecting


@pytest.mark.anyio
async def test_connect_builds_the_pool_with_the_deliberate_settings() -> None:
    # Arrange
    factory = FakePoolFactory()

    # Act
    db = await connect(factory)

    # Assert
    pool = factory.last
    assert pool.conninfo == GOOD_DSN
    assert pool.kwargs == pool_connection_kwargs()
    assert (pool.min_size, pool.max_size) == (DEFAULT_MIN_POOL_SIZE, DEFAULT_MAX_POOL_SIZE)
    assert pool.configure is noop_configure
    assert pool.open_flag is False, "psycopg_pool 3.3 deprecates opening in the constructor"
    assert pool.opened_with == {"wait": True, "timeout": db_module.POOL_OPEN_TIMEOUT_SECONDS}
    assert db.max_size == DEFAULT_MAX_POOL_SIZE


@pytest.mark.anyio
async def test_connect_honours_explicit_sizes_and_timeout() -> None:
    factory = FakePoolFactory()
    await connect(factory, min_size=2, max_size=4, open_timeout=3.0)
    pool = factory.last
    assert (pool.min_size, pool.max_size) == (2, 4)
    assert pool.opened_with == {"wait": True, "timeout": 3.0}


@pytest.mark.anyio
async def test_connect_registers_the_vector_type_by_default() -> None:
    """The default per-connection hook is the pgvector registration, and nothing else."""
    factory = FakePoolFactory()
    await Database.connect(GOOD_DSN, pool_factory=factory)
    assert factory.last.configure is db_module._register_types


@pytest.mark.anyio
async def test_the_checkpointer_and_store_share_the_one_pool() -> None:
    """One pool, one budget: neither client may quietly open connections of its own."""
    factory = FakePoolFactory()
    db = await connect(factory)
    assert isinstance(db.checkpointer, AsyncPostgresSaver)
    assert isinstance(db.store, AsyncPostgresStore)
    assert db.checkpointer.conn is factory.last
    assert db.store.conn is factory.last


@pytest.mark.anyio
async def test_the_store_is_built_without_a_vector_index() -> None:
    """pgvector search lives in our own tables; the Store must not create `store_vectors`."""
    db = await connect(FakePoolFactory())
    assert db.store.index_config is None
    assert db.store.embeddings is None


@pytest.mark.anyio
async def test_connect_refuses_the_transaction_pooler_before_opening_anything() -> None:
    factory = FakePoolFactory()
    with pytest.raises(SettingsError) as caught:
        await Database.connect(TRANSACTION_POOLER_DSN, pool_factory=factory)
    assert "session pooler" in str(caught.value).lower()
    assert FAKE_PASSWORD not in str(caught.value)
    assert factory.built == []


@pytest.mark.anyio
async def test_connect_refuses_an_oversized_pool_before_opening_anything() -> None:
    factory = FakePoolFactory()
    with pytest.raises(DatabaseError, match="coexist"):
        await connect(factory, max_size=MAX_POOL_SIZE_CEILING + 1)
    assert factory.built == []


@pytest.mark.anyio
async def test_a_pool_that_cannot_open_is_closed_and_the_dsn_is_not_echoed() -> None:
    # Arrange -- psycopg's own error would quote the conninfo, password included
    factory = FakePoolFactory(fail_open_with=TimeoutError(f"could not connect to {GOOD_DSN}"))

    # Act
    with pytest.raises(DatabaseError) as caught:
        await connect(factory)

    # Assert
    message = str(caught.value)
    assert "DATABASE_URL" in message
    assert "TimeoutError" in message
    assert FAKE_PASSWORD not in message
    assert factory.last.closed is True, "a half-open pool must not leak its connections"
    assert isinstance(caught.value.__cause__, TimeoutError)


# ---------------------------------------------------------------- borrowing


@pytest.mark.anyio
async def test_connection_lends_from_the_pool_and_matches_the_protocol_shape() -> None:
    factory = FakePoolFactory()
    db = await connect(factory)
    async with db.connection() as conn:
        assert conn is factory.last.lent


# ------------------------------------------------------------------- setup


@pytest.mark.anyio
async def test_setup_runs_both_setups_under_one_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange -- the real setups need Postgres; record that each was awaited instead
    factory = FakePoolFactory()
    db = await connect(factory)
    calls: list[str] = []

    async def fake_saver_setup(_self: Any) -> None:
        calls.append("checkpointer")

    async def fake_store_setup(_self: Any) -> None:
        calls.append("store")

    monkeypatch.setattr(AsyncPostgresSaver, "setup", fake_saver_setup)
    monkeypatch.setattr(AsyncPostgresStore, "setup", fake_store_setup)

    # Act
    await db.setup()

    # Assert -- lock, checkpointer, store, unlock, all on the same borrowed connection
    assert calls == ["checkpointer", "store"]
    executed = factory.last.lent.executed
    assert [q for q, _ in executed] == [
        "select pg_advisory_lock(%s)",
        "select pg_advisory_unlock(%s)",
    ]
    assert all(params == (SETUP_ADVISORY_LOCK_KEY,) for _, params in executed)


@pytest.mark.anyio
async def test_setup_releases_the_lock_when_a_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakePoolFactory()
    db = await connect(factory)

    async def failing_setup(_self: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(AsyncPostgresSaver, "setup", failing_setup)

    with pytest.raises(RuntimeError, match="boom"):
        await db.setup()

    assert factory.last.lent.executed[-1][0] == "select pg_advisory_unlock(%s)"


def test_the_setup_lock_key_is_a_valid_bigint_and_not_the_migration_runners() -> None:
    """`pg_advisory_lock` takes a signed 64-bit key; and the two locks guard different
    resources, so sharing a key would make an API start wait on an unrelated migration."""
    assert -SIGNED_64_BIT_MAX - 1 <= SETUP_ADVISORY_LOCK_KEY <= SIGNED_64_BIT_MAX
    assert SETUP_ADVISORY_LOCK_KEY != 0x43524F53_53424944  # scripts/migrate.py's key


# ------------------------------------------------------------------- closing


@pytest.mark.anyio
async def test_close_returns_every_connection() -> None:
    factory = FakePoolFactory()
    db = await connect(factory)
    await db.close()
    assert factory.last.closed is True
