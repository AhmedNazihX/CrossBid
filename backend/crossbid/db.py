"""The one psycopg pool, and the LangGraph checkpointer and Store that borrow from it. S0.2.2.

Everything that talks to Postgres at run time goes through `Database`: the read-model
writers, the pgvector search, `AsyncPostgresSaver` (short-term memory -- the graph's
checkpoints, so a bid paused for days resumes where it stopped) and `AsyncPostgresStore`
(long-term memory -- `profile/{company_id}` and `corrections/{company_id}`). One pool means
the connection budget is one number, which matters here more than usual.

**Why the pool is sized by hand.** The Supabase project has `max_connections = 60`, of
which 3 are reserved for superusers and, measured on 2026-09-10 with the API *not* running,
12 were already held by Supabase's own services (pooler, auth, storage, realtime). That
leaves roughly 45 for everything we start: this API, the migration runner, a developer's
psql, and a second API process when Compose and `make dev-api` run side by side. Ten per
process is the deliberate default, and `MAX_POOL_SIZE_CEILING` refuses a configuration that
could not coexist with a second copy of itself. A pool left at a library default would be
discovered under the `check_reqs` fan-out (F3.3) as "FATAL: too many clients", which says
nothing about pooling.

**What the library actually does with a pool**, verified in langgraph-checkpoint-postgres
3.1.2 rather than assumed, because it decides how much of the budget each client can take:

* `AsyncPostgresSaver._cursor` holds `self.lock` (one `asyncio.Lock` per saver) around
  every operation, pool or not. The checkpointer therefore never uses more than **one**
  connection at a time; concurrent graph branches queue on the lock, not on the pool.
* `AsyncPostgresStore._cursor` skips that lock when handed a pool ("each `_cursor()` call
  checks out its own connection"), so the Store can take up to `max_size`.
* Both create their own tables on `.setup()` -- `checkpoints`, `checkpoint_blobs`,
  `checkpoint_writes`, `checkpoint_migrations`, `store`, `store_migrations` -- and are
  idempotent. `store_vectors` is only created when an `index` config is given; it is not,
  because pgvector search lives in our own `company_chunks` / `tender_chunks` tables with
  the schema `migrations/0001_init.sql` controls.
* `from_conn_string` opens its connections with `prepare_threshold=0`. The pool does the
  same so that a query behaves identically whether the checkpointer or the read model ran
  it -- and it is exactly why the transaction pooler is refused (`check_database_dsn`).

The pool is opened explicitly (`open=False`, then `await pool.open()`): psycopg_pool 3.3
warns that opening an async pool in the constructor is deprecated.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final, Self

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from crossbid.settings import check_database_dsn

SUPABASE_MAX_CONNECTIONS: Final = 60
"""`show max_connections` on the project, 2026-09-10."""
SUPABASE_RESERVED_CONNECTIONS: Final = 3
"""`show superuser_reserved_connections`: slots the `postgres` role cannot count on."""
PLATFORM_BASELINE_SESSIONS: Final = 12
"""`pg_stat_activity` rows with nothing of ours connected: Supabase's own services."""
CONNECTIONS_AVAILABLE_TO_US: Final = (
    SUPABASE_MAX_CONNECTIONS - SUPABASE_RESERVED_CONNECTIONS - PLATFORM_BASELINE_SESSIONS
)
MAX_POOL_SIZE_CEILING: Final = CONNECTIONS_AVAILABLE_TO_US // 2
"""Half the headroom, so two API processes (Compose plus a host run) both fit."""

DEFAULT_MIN_POOL_SIZE: Final = 1
DEFAULT_MAX_POOL_SIZE: Final = 10
POOL_OPEN_TIMEOUT_SECONDS: Final = 15.0
"""How long `open()` waits for the first `min_size` connections before failing startup."""
CONNECT_TIMEOUT_SECONDS: Final = 10

SETUP_ADVISORY_LOCK_KEY: Final = 0x4C414E47_47524148  # "LANGGRAH"
"""Serialises `.setup()` across processes. Deliberately *not* the key `scripts/migrate.py`
uses: the two protect different resources (LangGraph's tables versus our schema), and the
script must stay importable without the package."""

Pool = AsyncConnectionPool[AsyncConnection[DictRow]]
PoolFactory = Callable[..., Pool]
Configure = Callable[[AsyncConnection[DictRow]], Awaitable[None]]


class DatabaseError(RuntimeError):
    """The pool could not be opened or sized. The message never carries the DSN."""


def pool_connection_kwargs() -> dict[str, Any]:
    """The per-connection settings every borrowed connection carries.

    `autocommit=True` because the read model writes single statements and the LangGraph
    clients manage their own transactions; `dict_row` so a row reads as `row["column"]`
    everywhere; `prepare_threshold=0` for parity with `from_conn_string` (see the module
    docstring). A fresh dict each call: psycopg mutates the mapping it is given.
    """
    return {
        "autocommit": True,
        "row_factory": dict_row,
        "prepare_threshold": 0,
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
    }


def check_pool_size(min_size: int, max_size: int) -> None:
    """Refuse a pool that could exhaust the project's connection budget."""
    if min_size < 0 or max_size <= 0 or min_size > max_size:
        raise DatabaseError(
            f"pool size must satisfy 0 <= min_size <= max_size with max_size > 0, "
            f"got min_size={min_size}, max_size={max_size}"
        )
    if max_size > MAX_POOL_SIZE_CEILING:
        raise DatabaseError(
            f"max_size={max_size} exceeds {MAX_POOL_SIZE_CEILING}, the most one API process "
            f"may take of the {CONNECTIONS_AVAILABLE_TO_US} connections left on a "
            f"max_connections={SUPABASE_MAX_CONNECTIONS} Supabase project once "
            f"{SUPABASE_RESERVED_CONNECTIONS} reserved and {PLATFORM_BASELINE_SESSIONS} "
            "platform sessions are subtracted. Two processes must be able to coexist."
        )


async def _register_types(conn: AsyncConnection[DictRow]) -> None:
    """Runs once per pooled connection: teach psycopg the `vector` type (S2.2.1).

    Not in the offline suite: the registration reads `pg_type`, so it needs a live
    connection. The `live` restart test in `tests/integration/` exercises it.
    """
    await register_vector_async(conn)  # pragma: no cover -- live connection only


def _default_pool_factory(conninfo: str, **kwargs: Any) -> Pool:
    """`AsyncConnectionPool` typed for `dict_row`, which `kwargs["row_factory"]` makes true.

    The pool's type parameter defaults to `AsyncConnection[TupleRow]`; naming the connection
    class is how psycopg documents getting a typed pool, and it keeps pyright honest about
    what every borrowed connection returns.
    """
    return AsyncConnectionPool(conninfo, connection_class=AsyncConnection[DictRow], **kwargs)


class Database:
    """Owns the pool and the two LangGraph clients built on it. Create with `connect`."""

    def __init__(
        self,
        pool: Pool,
        *,
        checkpointer: AsyncPostgresSaver,
        store: AsyncPostgresStore,
    ) -> None:
        self._pool = pool
        self._checkpointer = checkpointer
        self._store = store

    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        min_size: int = DEFAULT_MIN_POOL_SIZE,
        max_size: int = DEFAULT_MAX_POOL_SIZE,
        open_timeout: float = POOL_OPEN_TIMEOUT_SECONDS,
        pool_factory: PoolFactory = _default_pool_factory,
        configure: Configure = _register_types,
    ) -> Self:
        """Open the pool, or refuse to start.

        The DSN guard runs here as well as in `load_settings`, because scripts and tests
        reach `connect` with an explicit DSN that never passed through settings.
        `pool_factory` and `configure` are seams for tests, which must not open a socket.
        """
        check_database_dsn(dsn)
        check_pool_size(min_size, max_size)

        pool = pool_factory(
            dsn,
            kwargs=pool_connection_kwargs(),
            min_size=min_size,
            max_size=max_size,
            configure=configure,
            open=False,
        )
        try:
            await pool.open(wait=True, timeout=open_timeout)
        except Exception as exc:
            await pool.close()
            # `exc` may quote the conninfo; the message here names the variable only.
            raise DatabaseError(
                "Could not open the database pool within "
                f"{open_timeout:.0f}s: {type(exc).__name__}. Check DATABASE_URL and that "
                "the Supabase project is not paused."
            ) from exc

        # Built here, inside the running loop: both constructors call
        # `asyncio.get_running_loop()`.
        return cls(
            pool,
            checkpointer=AsyncPostgresSaver(pool),
            store=AsyncPostgresStore(pool),
        )

    @property
    def checkpointer(self) -> AsyncPostgresSaver:
        """Short-term memory: the graph compiles with `checkpointer=db.checkpointer`."""
        return self._checkpointer

    @property
    def store(self) -> AsyncPostgresStore:
        """Long-term memory: `profile/{company_id}` and `corrections/{company_id}`."""
        return self._store

    @property
    def max_size(self) -> int:
        return self._pool.max_size

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]:
        """Borrow a connection for a read-model or vector query; returned on exit.

        This is the signature `ingestion.embeddings.ConnectionSource` and the read-model
        writers depend on, so it is a method returning a context manager rather than an
        `async with db.pool.connection()` reaching into the pool.
        """
        return self._borrow()

    @asynccontextmanager
    async def _borrow(self) -> AsyncIterator[AsyncConnection[DictRow]]:
        async with self._pool.connection() as conn:
            yield conn

    async def setup(self) -> None:
        """Create LangGraph's tables if missing. Idempotent; safe to call on every start.

        Held under an advisory lock so that two API processes starting together do not
        both run the version bookkeeping. `pg_advisory_lock` is session-scoped, so the
        lock and unlock must happen on the *same* borrowed connection.
        """
        async with self.connection() as conn:
            await conn.execute("select pg_advisory_lock(%s)", (SETUP_ADVISORY_LOCK_KEY,))
            try:
                await self._checkpointer.setup()
                await self._store.setup()
            finally:
                await conn.execute("select pg_advisory_unlock(%s)", (SETUP_ADVISORY_LOCK_KEY,))

    async def close(self) -> None:
        """Return every connection. Called from the app's shutdown hook."""
        await self._pool.close()
