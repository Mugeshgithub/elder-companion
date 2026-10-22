"""What the family can do: leave a message for the person, read a daily summary, record consent,
pause monitoring, and erase what the companion has stored."""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import episodic_memory
import llm
import working_memory
from config import AGENT_SHARED_SECRET, PATIENT_TZ

log = logging.getLogger("family")
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
async def leave_message(pid: int, body: MessageIn, request: Request):
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
    await audit(pid, actor_of(request), "message", f"to be said at the next call, from {who}")
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
async def set_consent(pid: int, body: ConsentIn, request: Request):
    record = {"by": body.by.strip(), "basis": body.basis, "at": datetime.now(timezone.utc).isoformat()}
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET consent = %s::jsonb WHERE id = %s", (json.dumps(record), pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    await working_memory.log_event(pid, "consent", f"Consent recorded by {record['by']}")
    await audit(pid, actor_of(request), "consent", f"{record['basis']}, confirmed by {record['by']}")
    return {"consent": record}


# ---------- pause and erase ----------

class PauseIn(BaseModel):
    paused: bool


@router.post("/{pid}/pause")
async def pause(pid: int, body: PauseIn, request: Request):
    """Paused means nothing is saved, no alerts are raised, and the companion starts no check-in calls."""
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET paused = %s WHERE id = %s", (body.paused, pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    if body.paused:
        await working_memory.r.delete(f"patient:{pid}:checkin_pending")
    await working_memory.log_event(pid, "pause", "Monitoring paused" if body.paused else "Monitoring resumed")
    await audit(pid, actor_of(request), "pause" if body.paused else "resume")
    return {"paused": body.paused}


class EraseIn(BaseModel):
    confirm: str


@router.post("/{pid}/erase")
async def erase(pid: int, body: EraseIn, request: Request):
    """Deletes what the companion learned and recorded. The family's own setup stays."""
    if body.confirm != "DELETE":
        return JSONResponse({"detail": "type DELETE to confirm"}, status_code=422)
    async with db.pool.connection() as conn:
        m = await conn.execute(
            "DELETE FROM memories WHERE patient_id = %s AND (source IN ('person', 'document') OR category = 'message')", (pid,))
        await conn.execute("DELETE FROM documents WHERE patient_id = %s", (pid,))  # their findings go with them
        a = await conn.execute("DELETE FROM alerts WHERE patient_id = %s", (pid,))
        f = await conn.execute("DELETE FROM family_messages WHERE patient_id = %s", (pid,))
    keys = [k async for k in working_memory.r.scan_iter(match=f"patient:{pid}:*", count=200)]
    if keys:
        await working_memory.r.delete(*keys)
    await audit(pid, actor_of(request), "erase", f"{m.rowcount} notes, {a.rowcount} alerts, {f.rowcount} messages")
    return {"erased": {"memories": m.rowcount, "alerts": a.rowcount, "messages": f.rowcount, "live_keys": len(keys)}}


# ---------- who did what, and who may sign in ----------

def actor_of(request: Request) -> str:
    """The website's proxy sets this to the signed-in person's name. Only the proxy holds the shared secret."""
    return request.headers.get("x-actor", "unknown")[:60]


async def audit(pid: int | None, actor: str, action: str, detail: str = "") -> None:
    try:
        async with db.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO audit_log (patient_id, actor, action, detail) VALUES (%s, %s, %s, %s)",
                (pid, actor, action, detail[:200]))
    except Exception:
        log.exception("audit write failed")  # an audit problem must never break what the person was doing


def _hash(code: str) -> str:
    return hmac.new(AGENT_SHARED_SECRET.encode(), code.encode(), hashlib.sha256).hexdigest()


class VerifyIn(BaseModel):
    code: str = Field(max_length=100)
    client: str = Field(default="", max_length=80)
    master: bool = False  # the proxy says the code matched the owner code it holds


MAX_FAILS = 10  # wrong codes per client address in 15 minutes


@router.post("/verify")
async def verify(body: VerifyIn):
    key = f"auth:fail:{body.client or 'unknown'}"
    if int(await working_memory.r.get(key) or 0) >= MAX_FAILS:
        return JSONResponse({"detail": "too many attempts"}, status_code=429)
    if body.master:
        return {"role": "owner", "name": "owner"}
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "UPDATE family_members SET last_seen = now() WHERE code_hash = %s RETURNING name, patient_id",
            (_hash(body.code),))).fetchone()
    if row:
        return {"role": "member", "name": row[0], "patient_id": row[1]}
    await working_memory.r.incr(key)
    await working_memory.r.expire(key, 900)
    return JSONResponse({"detail": "invalid"}, status_code=401)


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@router.post("/{pid}/members")
async def add_member(pid: int, body: MemberIn, request: Request):
    """Gives one family member their own code. It is shown once here and only a hash is kept."""
    code = secrets.token_urlsafe(9)
    name = body.name.strip()
    if not name:
        return JSONResponse({"detail": "empty name"}, status_code=422)
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO family_members (patient_id, name, code_hash) SELECT id, %s, %s FROM patients WHERE id = %s RETURNING id",
            (name, _hash(code), pid))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    await audit(pid, actor_of(request), "member_added", name)
    return {"id": row[0], "name": name, "code": code}


@router.post("/{pid}/members/{mid}/revoke")
async def revoke_member(pid: int, mid: int, request: Request):
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "DELETE FROM family_members WHERE id = %s AND patient_id = %s RETURNING name", (mid, pid))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    await audit(pid, actor_of(request), "member_removed", row[0])
    return {"revoked": True}


# ---------- privacy overview, retention, export ----------

@router.get("/{pid}/privacy")
async def privacy(pid: int):
    async with db.pool.connection() as conn:
        p = await (await conn.execute(
            "SELECT name, consent, paused, retention_days FROM patients WHERE id = %s", (pid,))).fetchone()
        if not p:
            return JSONResponse({"detail": "not found"}, status_code=404)
        members = await (await conn.execute(
            "SELECT id, name, created_at, last_seen FROM family_members WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        trail = await (await conn.execute(
            "SELECT actor, action, detail, at FROM audit_log WHERE patient_id = %s ORDER BY at DESC LIMIT 15", (pid,))).fetchall()
    return {
        "patient": p[0], "consent": p[1], "paused": p[2], "retention_days": p[3],
        "members": [dict(id=i, name=n, created_at=c.isoformat(), last_seen=s.isoformat() if s else None) for i, n, c, s in members],
        "audit": [dict(actor=a, action=ac, detail=d, at=t.isoformat()) for a, ac, d, t in trail],
    }


class RetentionIn(BaseModel):
    days: int | None = Field(default=None, ge=7, le=3650)  # null keeps everything until the family deletes it


@router.post("/{pid}/retention")
async def set_retention(pid: int, body: RetentionIn, request: Request):
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET retention_days = %s WHERE id = %s", (body.days, pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    await audit(pid, actor_of(request), "retention", f"{body.days} days" if body.days else "keep until deleted")
    return {"retention_days": body.days}


@router.get("/{pid}/export")
async def export(pid: int, request: Request):
    """A copy of everything stored about this person, as the family can download it. No embeddings, no code hashes."""
    async with db.pool.connection() as conn:
        p = await (await conn.execute(
            "SELECT name, profile, setup, consent, paused, retention_days, created_at FROM patients WHERE id = %s", (pid,))).fetchone()
        if not p:
            return JSONResponse({"detail": "not found"}, status_code=404)
        mem = await (await conn.execute(
            "SELECT content, category, source, mood, created_at FROM memories WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        al = await (await conn.execute(
            "SELECT kind, severity, detail, resolved, created_at FROM alerts WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        msgs = await (await conn.execute(
            "SELECT from_name, text, created_at, delivered_at FROM family_messages WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        members = await (await conn.execute(
            "SELECT name, created_at, last_seen FROM family_members WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        trail = await (await conn.execute(
            "SELECT actor, action, detail, at FROM audit_log WHERE patient_id = %s ORDER BY at", (pid,))).fetchall()
        targets = await (await conn.execute(
            "SELECT name, created_at FROM notify_targets WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
        docs = await (await conn.execute(
            "SELECT id, filename, doc_type, doc_date, author, named_patient, uploaded_by, uploaded_at, pages FROM documents WHERE patient_id = %s ORDER BY uploaded_at", (pid,))).fetchall()
        dfacts = await (await conn.execute(
            "SELECT document_id, kind, summary, page, quote, verified, status, reviewed_by, reviewed_at FROM document_facts WHERE patient_id = %s ORDER BY document_id, id", (pid,))).fetchall()
    iso = lambda t: t.isoformat() if t else None
    await audit(pid, actor_of(request), "export", f"{len(mem)} notes")
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "note": "Call transcripts kept by ElevenLabs are not part of this file.",
        "person": {"name": p[0], "private_note": p[1], "setup": p[2], "consent": p[3], "paused": p[4],
                   "retention_days": p[5], "created_at": iso(p[6])},
        "notes": [dict(content=c, category=k, source=s, mood=m, at=iso(t)) for c, k, s, m, t in mem],
        "alerts": [dict(kind=k, severity=s, detail=d, resolved=r, at=iso(t)) for k, s, d, r, t in al],
        "messages": [dict(from_name=n, text=t, at=iso(c), said_at=iso(d)) for n, t, c, d in msgs],
        "family_members": [dict(name=n, added=iso(c), last_seen=iso(s)) for n, c, s in members],
        "phone_alerts": [dict(name=n, connected=iso(c)) for n, c in targets],
        "audit": [dict(actor=a, action=ac, detail=d, at=iso(t)) for a, ac, d, t in trail],
        "documents": [dict(
            filename=fn, type=ty, date=iso(dd), author=au, about=nm, uploaded_by=ub, uploaded_at=iso(ua), text_by_page=pg,
            findings=[dict(kind=k, summary=s, page=p, quote=q, quote_found_on_page=v, status=st, reviewed_by=rb, reviewed_at=iso(ra))
                      for (xid, k, s, p, q, v, st, rb, ra) in dfacts if xid == i])
            for i, fn, ty, dd, au, nm, ub, ua, pg in docs],
    }


# ---------- retention: delete what has outlived the family's chosen limit ----------

async def purge_once() -> dict:
    async with db.pool.connection() as conn:
        m = await conn.execute(
            """DELETE FROM memories m USING patients p WHERE m.patient_id = p.id AND p.retention_days IS NOT NULL
               AND m.source = 'person' AND m.created_at < now() - make_interval(days => p.retention_days)""")
        a = await conn.execute(
            """DELETE FROM alerts a USING patients p WHERE a.patient_id = p.id AND p.retention_days IS NOT NULL
               AND a.created_at < now() - make_interval(days => p.retention_days)""")
        f = await conn.execute(
            """DELETE FROM family_messages f USING patients p WHERE f.patient_id = p.id AND p.retention_days IS NOT NULL
               AND f.created_at < now() - make_interval(days => p.retention_days)""")
        await conn.execute("DELETE FROM audit_log WHERE at < now() - interval '2 years'")
    return {"memories": m.rowcount, "alerts": a.rowcount, "messages": f.rowcount}


async def purge_loop() -> None:
    await asyncio.sleep(60)
    while True:
        try:
            gone = await purge_once()
            if any(gone.values()):
                log.info("retention purge removed %s", gone)
        except Exception:
            log.exception("retention purge failed")
        await asyncio.sleep(3600)
