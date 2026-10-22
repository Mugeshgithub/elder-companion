"""One shared Postgres connection pool.

Opening a fresh TLS connection to Aiven costs about a second, and a reply used to open four of them.
A pool keeps a few connections open, so a query costs milliseconds. It is opened when the server starts.
"""
from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool

from config import POSTGRES_URI


async def _configure(conn) -> None:
    await register_vector_async(conn)
    await conn.commit()  # the pool needs the connection idle after set-up


pool = AsyncConnectionPool(
    POSTGRES_URI,
    min_size=2,
    max_size=6,  # Aiven plans cap total connections, and the laptop and Modal may both run
    open=False,
    configure=_configure,
    check=AsyncConnectionPool.check_connection,  # drops a connection Aiven closed while it sat idle
    max_idle=120,
    max_lifetime=1800,
)


async def is_paused(patient_id: int) -> bool:
    """True while the family has paused monitoring: nothing is saved, no alerts, no check-in calls."""
    async with pool.connection() as conn:
        row = await (await conn.execute("SELECT paused FROM patients WHERE id = %s", (patient_id,))).fetchone()
    return bool(row and row[0])
