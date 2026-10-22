import psycopg

import working_memory
from config import POSTGRES_URI

SEVERITY = {
    "family_notification_request": "high",
    "distress": "high",
    "missed_medication": "high",
    "confusion": "medium",
    "inactivity": "normal",
    "no_response": "medium",
}


async def raise_alert(patient_id: int, kind: str, detail: str, dedupe_minutes: int = 30) -> bool:
    """Writes an alert unless the same kind is already open. Returns True if a new row was written."""
    async with await psycopg.AsyncConnection.connect(POSTGRES_URI) as conn:
        cur = await conn.execute(
            """INSERT INTO alerts (patient_id, kind, detail, severity)
               SELECT %s, %s, %s, %s WHERE NOT EXISTS (
                 SELECT 1 FROM alerts WHERE patient_id = %s AND kind = %s AND NOT resolved
                   AND created_at > now() - make_interval(mins => %s))
               RETURNING id""",
            (patient_id, kind, detail, SEVERITY.get(kind, "normal"), patient_id, kind, dedupe_minutes),
        )
        written = await cur.fetchone() is not None
    if written:
        await working_memory.log_event(patient_id, "alert", detail, alert=kind, severity=SEVERITY.get(kind, "normal"))
    return written
