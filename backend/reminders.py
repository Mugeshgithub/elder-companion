"""Medicine reminders, on the same Valkey key-expiry trigger that starts a silence check-in.

The family sets a medicine and a time in the setup. For each time there is a Valkey key that expires at the next
occurrence. When it expires, the companion rings and asks, quoting the approved document if there is one. It never
counts a dose as taken unless the person says so. Thirty minutes later a second key expires, and if nothing was
confirmed the family is told "no confirmation", which is not the same as "missed".
"""
import json
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import alerts
import db
import documents
import working_memory
from config import PATIENT_TZ

log = logging.getLogger("reminders")
CHECK_AFTER_SECONDS = 30 * 60
_TIME = re.compile(r"\d{2}:\d{2}")


def _compact(hhmm: str) -> str:
    return hhmm.replace(":", "")


def _seconds_until(hhmm: str) -> int:
    now = datetime.now(ZoneInfo(PATIENT_TZ))
    h, m = (int(x) for x in hhmm.split(":"))
    due = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if due <= now + timedelta(seconds=5):
        due += timedelta(days=1)
    return max(5, int((due - now).total_seconds()))


def _spoken(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    ampm = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12} {ampm}" if m == 0 else f"{h12}:{m:02d} {ampm}"


async def _meds(pid: int) -> list[dict]:
    async with db.pool.connection() as conn:
        row = await (await conn.execute("SELECT setup FROM patients WHERE id = %s", (pid,))).fetchone()
    meds = ((row[0] if row else None) or {}).get("meds") or []
    return [m for m in meds if m.get("name") and _TIME.fullmatch(m.get("time") or "")]


async def schedule(pid: int, reset: bool = False) -> None:
    """One key per distinct time, expiring at its next occurrence. NX, so a key that is already counting is left alone."""
    r = working_memory.r
    if reset:  # the family changed the setup
        old = [k async for k in r.scan_iter(match=f"patient:{pid}:remind:*")]
        if old:
            await r.delete(*old)
    for t in {m["time"] for m in await _meds(pid)}:
        await r.set(f"patient:{pid}:remind:{_compact(t)}", "1", ex=_seconds_until(t), nx=True)


async def schedule_all() -> None:
    async with db.pool.connection() as conn:
        ids = [r[0] for r in await (await conn.execute("SELECT id FROM patients WHERE setup IS NOT NULL")).fetchall()]
    for pid in ids:
        await schedule(pid)


async def fire(pid: int, compact: str) -> None:
    """The reminder time has come."""
    hhmm = f"{compact[:2]}:{compact[2:]}"
    await schedule(pid)  # tomorrow's reminder, now that today's key has expired
    r = working_memory.r
    if await db.is_paused(pid) or await r.get(f"patient:{pid}:dnd"):
        return  # paused, or they said good night
    names = [m["name"] for m in await _meds(pid) if m["time"] == hhmm]
    if not names:
        return
    await r.set(f"patient:{pid}:checkin_pending", "reminder", ex=3600)
    await r.set(f"patient:{pid}:remind_for", json.dumps({"time": hhmm, "names": names}), ex=3600)
    await r.set(f"patient:{pid}:remindcheck:{compact}", "1", ex=CHECK_AFTER_SECONDS)
    await working_memory.log_event(pid, "reminder", f"{_spoken(hhmm)}: {', '.join(names)}")


async def check(pid: int, compact: str) -> None:
    """Half an hour after a reminder: did they say they took it? If not, tell the family there was no confirmation."""
    hhmm = f"{compact[:2]}:{compact[2:]}"
    if await db.is_paused(pid):
        return
    names = [m["name"] for m in await _meds(pid) if m["time"] == hhmm]
    if not names:
        return
    async with db.pool.connection() as conn:
        said = await (await conn.execute(
            """SELECT 1 FROM memories WHERE patient_id = %s AND source = 'person' AND category = 'medication'
                 AND created_at > now() - make_interval(secs => %s) LIMIT 1""", (pid, CHECK_AFTER_SECONDS + 120))).fetchone()
    if said:
        return
    await alerts.raise_alert(pid, "missed_medication", f"No confirmation after the {_spoken(hhmm)} reminder for {', '.join(names)}.", dedupe_minutes=120)


async def opener_line(pid: int, person: str) -> str | None:
    """What the companion says when it rings for a reminder: the time, the medicine, the document's own words if the
    family approved one, and a question. It never says the dose was taken."""
    raw = await working_memory.r.get(f"patient:{pid}:remind_for")
    if not raw:
        return None
    info = json.loads(raw)
    names = info["names"]
    parts = [f"Hello {person}. It's {_spoken(info['time'])}, and your family set a reminder for {' and '.join(names)}."]
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            """SELECT f.summary, d.doc_type, d.author, d.doc_date FROM document_facts f JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = %s AND f.status = 'approved' AND f.kind = 'medication'
                 AND lower(f.detail->'medication'->>'name') LIKE %s LIMIT 1""",
            (pid, f"%{names[0].lower().split()[0]}%"))).fetchone()
    if row:
        summary, dtype, author, ddate = row
        label = documents._label(dtype, author, ddate)
        parts.append(f"{label[0].upper() + label[1:]} says: {summary[0].lower() + summary[1:]}")
    parts.append("Have you taken them yet?" if len(names) > 1 else "Have you taken it yet?")
    if await working_memory.r.get(f"patient:{pid}:checkin_pending") == "reminder":
        await working_memory.r.delete(f"patient:{pid}:checkin_pending")  # the companion is calling now
    return " ".join(parts)
