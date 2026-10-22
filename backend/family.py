"""What the family can do: leave a message for the person, read a daily summary, record consent,
pause monitoring, and erase what the companion has stored."""
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import episodic_memory
import llm
import working_memory
from config import PATIENT_TZ

router = APIRouter(prefix="/family")

KIND_TEXT = {
    "family_notification_request": "asked for their family to be told",
    "distress": "seemed distressed",
    "missed_medication": "may have missed a dose",
    "confusion": "seemed confused",
    "inactivity": "was quiet for a long time and the companion started a check-in",
    "no_response": "did not answer a check-in call",
}

SUMMARY_SYSTEM = """You write a short note for the family of {name}, who uses a voice companion. Now is {now}.
Write 2 to 4 plain sentences using ONLY the notes and alerts below.
- Say what {name} told the companion, and any concern that was raised. If there was an alert, mention it first.
- Never diagnose and never guess. Never say they are fine, safe, or well: the notes only show what was said to the companion.
- Use {name}'s name. Do not use "he" or "she". No lists, no markdown, no dashes.
- Output only the note."""


def _midnight_sql() -> str:
    return "(date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s)"


# ---------- messages ----------

class MessageIn(BaseModel):
    from_name: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=300)


@router.post("/{pid}/message")
async def leave_message(pid: int, body: MessageIn):
    """A note from a family member. The companion says it at the start of the next call, once."""
    who, text = body.from_name.strip(), body.text.strip()
    if not who or not text:
        return JSONResponse({"detail": "empty message"}, status_code=422)
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            """INSERT INTO family_messages (patient_id, from_name, text)
               SELECT id, %s, %s FROM patients WHERE id = %s RETURNING id""", (who, text, pid))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    # also a memory, so they can ask "did Anna leave me a message?" and get a true answer
    await episodic_memory.save_memory(pid, f"{who} left this message for them: {text}", "message", None, "family")
    await working_memory.log_event(pid, "family_message", f"{who}: {text}")
    return {"id": row[0]}


@router.get("/{pid}/messages")
async def list_messages(pid: int):
    async with db.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT id, from_name, text, created_at, delivered_at FROM family_messages
               WHERE patient_id = %s ORDER BY created_at DESC LIMIT 8""", (pid,))).fetchall()
    return {"messages": [
        dict(id=i, from_name=n, text=t, at=c.isoformat(), delivered_at=d.isoformat() if d else None)
        for i, n, t, c, d in rows]}


async def take_messages(pid: int) -> list[tuple[str, str]]:
    """Claims up to three waiting messages in one statement, so two calls starting together cannot both say them."""
    async with db.pool.connection() as conn:
        cur = await conn.execute(
            """UPDATE family_messages SET delivered_at = now() WHERE id IN (
                 SELECT id FROM family_messages WHERE patient_id = %s AND delivered_at IS NULL
                 ORDER BY created_at LIMIT 3) RETURNING from_name, text, created_at""", (pid,))
        rows = sorted(await cur.fetchall(), key=lambda r: r[2])
    return [(n, t) for n, t, _ in rows]


def spoken(messages: list[tuple[str, str]]) -> str:
    parts = []
    for who, text in messages:
        text = text.strip()
        parts.append(f"{who} asked me to tell you: {text}" + ("" if text[-1:] in ".!?" else "."))
    return " ".join(parts)


# ---------- daily summary ----------

@router.get("/{pid}/summary")
async def summary(pid: int):
    cached = await working_memory.r.get(f"patient:{pid}:summary")
    if cached:
        return json.loads(cached)
    async with db.pool.connection() as conn:
        row = await (await conn.execute("SELECT name FROM patients WHERE id = %s", (pid,))).fetchone()
        if not row:
            return JSONResponse({"detail": "not found"}, status_code=404)
        name = row[0]
        notes = await (await conn.execute(
            f"""SELECT content, created_at FROM memories
                WHERE patient_id = %s AND source = 'person' AND content !~ '^[^ ]+ said: '
                  AND created_at >= {_midnight_sql()} ORDER BY created_at LIMIT 40""",
            (pid, PATIENT_TZ, PATIENT_TZ))).fetchall()
        alerts = await (await conn.execute(
            f"""SELECT kind, detail, resolved, created_at FROM alerts
                WHERE patient_id = %s AND created_at >= {_midnight_sql()} ORDER BY created_at""",
            (pid, PATIENT_TZ, PATIENT_TZ))).fetchall()

    if not notes and not alerts:
        text = "Nothing recorded today yet."
    else:
        lines = [f"Notes {name} gave the companion today:"] + [f"- {c}" for c, _ in notes] if notes else []
        if alerts:
            lines += ["Alerts today:"] + [
                f"- {name} {KIND_TEXT.get(k, k)}" + (f" (they said: {d})" if d and k in ("distress", "confusion", "missed_medication", "family_notification_request") else "")
                + (", already handled" if r else "") for k, d, r, _ in alerts]
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(PATIENT_TZ)).strftime("%A %H:%M")
            text, _ = await llm.generate(
                SUMMARY_SYSTEM.format(name=name, now=now), [{"role": "user", "content": "\n".join(lines)}], max_tokens=220)
            text = text.strip()
        except Exception:
            text = " ".join(l.lstrip("- ") for l in lines if not l.endswith(":"))
    out = {"summary": text, "notes": len(notes), "alerts": len(alerts), "at": datetime.now(timezone.utc).isoformat()}
    await working_memory.r.set(f"patient:{pid}:summary", json.dumps(out), ex=120)
    return out


# ---------- consent ----------

class ConsentIn(BaseModel):
    by: str = Field(min_length=1, max_length=60)
    basis: Literal["person_agreed", "legal_authority"]


@router.get("/{pid}/consent")
async def get_consent(pid: int):
    async with db.pool.connection() as conn:
        row = await (await conn.execute("SELECT consent FROM patients WHERE id = %s", (pid,))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return {"consent": row[0]}


@router.post("/{pid}/consent")
async def set_consent(pid: int, body: ConsentIn):
    record = {"by": body.by.strip(), "basis": body.basis, "at": datetime.now(timezone.utc).isoformat()}
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET consent = %s::jsonb WHERE id = %s", (json.dumps(record), pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    await working_memory.log_event(pid, "consent", f"Consent recorded by {record['by']}")
    return {"consent": record}


# ---------- pause and erase ----------

class PauseIn(BaseModel):
    paused: bool


@router.post("/{pid}/pause")
async def pause(pid: int, body: PauseIn):
    """Paused means nothing is saved, no alerts are raised, and the companion starts no check-in calls."""
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET paused = %s WHERE id = %s", (body.paused, pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    if body.paused:
        await working_memory.r.delete(f"patient:{pid}:checkin_pending")
    await working_memory.log_event(pid, "pause", "Monitoring paused" if body.paused else "Monitoring resumed")
    return {"paused": body.paused}


class EraseIn(BaseModel):
    confirm: str


@router.post("/{pid}/erase")
async def erase(pid: int, body: EraseIn):
    """Deletes what the companion learned and recorded. The family's own setup stays."""
    if body.confirm != "DELETE":
        return JSONResponse({"detail": "type DELETE to confirm"}, status_code=422)
    async with db.pool.connection() as conn:
        m = await conn.execute("DELETE FROM memories WHERE patient_id = %s AND (source = 'person' OR category = 'message')", (pid,))
        a = await conn.execute("DELETE FROM alerts WHERE patient_id = %s", (pid,))
        f = await conn.execute("DELETE FROM family_messages WHERE patient_id = %s", (pid,))
    keys = [k async for k in working_memory.r.scan_iter(match=f"patient:{pid}:*", count=200)]
    if keys:
        await working_memory.r.delete(*keys)
    return {"erased": {"memories": m.rowcount, "alerts": a.rowcount, "messages": f.rowcount, "live_keys": len(keys)}}
