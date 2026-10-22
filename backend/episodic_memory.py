"""Episodic memory in Postgres + pgvector: long-term history, searched by meaning."""
import psycopg
from pgvector.psycopg import register_vector_async

from config import POSTGRES_URI
from embeddings import embed


async def _conn():
    conn = await psycopg.AsyncConnection.connect(POSTGRES_URI)
    await register_vector_async(conn)
    return conn


async def save_memory(
    patient_id: int, content: str, category: str = "conversation", mood: str | None = None, source: str = "person"
) -> None:
    vec = await embed(content)
    async with await _conn() as conn:
        await conn.execute(
            "INSERT INTO memories (patient_id, content, category, mood, embedding, source) VALUES (%s,%s,%s,%s,%s,%s)",
            (patient_id, content, category, mood, vec, source),
        )


async def search_memories(patient_id: int, query: str, k: int = 5, include_family: bool = True) -> list[dict]:
    vec = await embed(query)
    async with await _conn() as conn:
        cur = await conn.execute(
            """SELECT content, category, mood, created_at, 1 - (embedding <=> %s::vector) AS score, source
               FROM memories WHERE patient_id = %s AND (%s OR source = 'person')
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (vec, patient_id, include_family, vec, k),
        )
        rows = await cur.fetchall()
    return [
        {"content": c, "category": cat, "mood": m, "when": t.isoformat(), "score": float(s), "source": src}
        for c, cat, m, t, s, src in rows
    ]


async def today_facts(patient_id: int, tz: str, categories=("medication", "meal")) -> list[dict]:
    """Facts recorded since local midnight, used to confirm what actually happened today."""
    async with await _conn() as conn:
        cur = await conn.execute(
            """SELECT content, created_at FROM memories
               WHERE patient_id = %s AND source = 'person' AND category = ANY(%s)
                 AND created_at >= (date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s)
               ORDER BY created_at""",
            (patient_id, list(categories), tz, tz),
        )
        rows = await cur.fetchall()
    return [{"content": c, "at": t.isoformat()} for c, t in rows]
