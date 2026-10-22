"""Alerts to the family's phones, through Telegram.

A family member is connected with a one-time link: they open it on their phone and press Start. From then on a new
important alert reaches them as a message. By default the message carries no health words, only what kind of alert it
is, when, and a link to the portal; the owner can choose to include the person's own words.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import family
import working_memory
from config import AGENT_SHARED_SECRET, PATIENT_TZ

# The Telegram bot token is part of every request URL, so the HTTP client's own request log must never be written.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("notify")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
PORTAL = os.getenv("PORTAL_URL", "").rstrip("/")

router = APIRouter(prefix="/family")  # the owner's controls, behind the proxy and the shared secret
hook = APIRouter()  # Telegram's own call, protected by its secret header instead

# Plain "quiet for a while" notices do not ping anyone. These do.
PUSH_KINDS = {"family_notification_request", "distress", "missed_medication", "confusion", "no_response"}
WORDS_KINDS = {"family_notification_request", "distress", "missed_medication", "confusion"}
KIND_TEXT = {
    "family_notification_request": "asked for their family to be told",
    "distress": "seemed distressed",
    "missed_medication": "may have missed a dose",
    "confusion": "seemed confused",
    "no_response": "did not answer a check-in call",
}

# Pacing, so the family's phones are not flooded. The portal always shows everything.
BATCH_SECONDS = 20       # alerts within this window become one message
COOLDOWN_SECONDS = 1800  # the same kind of alert does not message again for this long
HOURLY_MAX = 4           # messages per person per hour
REMIND_AFTER_MINUTES = 20  # one reminder if a serious alert is still open

_bot_name: str | None = None
_tasks: set[asyncio.Task] = set()


async def _api(method: str, **payload) -> tuple[int, dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


async def bot_username() -> str | None:
    global _bot_name
    if not _bot_name and TOKEN:
        _, d = await _api("getMe")
        _bot_name = (d.get("result") or {}).get("username")
    return _bot_name


async def send(chat_id: int, text: str) -> str:
    """'ok', 'gone' (the person blocked the bot or deleted the chat), or 'error'."""
    try:
        status, d = await _api("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
    except Exception:
        log.warning("telegram send failed (network)")
        return "error"
    if d.get("ok"):
        return "ok"
    return "gone" if status in (400, 403) else "error"


def _hash(token: str) -> str:
    return hmac.new(AGENT_SHARED_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


async def _targets(pid: int) -> tuple[str, bool, list[tuple[int, int]]] | None:
    async with db.pool.connection() as conn:
        p = await (await conn.execute("SELECT name, notify_words FROM patients WHERE id = %s", (pid,))).fetchone()
        targets = await (await conn.execute("SELECT id, chat_id FROM notify_targets WHERE patient_id = %s", (pid,))).fetchall()
    return (p[0], p[1], targets) if p and targets else None


async def _deliver(targets: list[tuple[int, int]], text: str) -> None:
    for tid, chat in targets:
        if await send(chat, text) == "gone":  # blocked the bot or deleted the chat
            async with db.pool.connection() as conn:
                await conn.execute("DELETE FROM notify_targets WHERE id = %s", (tid,))


async def alert(pid: int, kind: str, detail: str) -> None:
    """Called when a new alert was written. Never raises: a failed message must not break a conversation."""
    if not TOKEN or kind not in PUSH_KINDS:
        return
    try:
        r = working_memory.r
        if not await r.set(f"notify:{pid}:cool:{kind}", "1", nx=True, ex=COOLDOWN_SECONDS):
            return  # the family was told about this kind a moment ago
        pending = f"notify:{pid}:pending"
        await r.rpush(pending, json.dumps({"kind": kind, "detail": detail}))
        await r.expire(pending, 120)
        if not await r.set(f"notify:{pid}:batch", "1", nx=True, ex=BATCH_SECONDS + 5):
            return  # another alert in this burst is already waiting, and will carry this one
        await asyncio.sleep(BATCH_SECONDS)
        items = [json.loads(x) for x in await r.lrange(pending, 0, -1)]
        await r.delete(pending, f"notify:{pid}:batch")
        if not items:
            return
        used = await r.incr(f"notify:{pid}:hour")
        if used == 1:
            await r.expire(f"notify:{pid}:hour", 3600)
        if used > HOURLY_MAX:
            log.info("message for patient %s held back: hourly limit", pid)
            return
        found = await _targets(pid)
        if not found:
            return
        name, words, targets = found
        when = datetime.now(ZoneInfo(PATIENT_TZ)).strftime("%H:%M")
        if len(items) == 1:
            lines = [f"Memory Lane: {name} {KIND_TEXT.get(items[0]['kind'], items[0]['kind'])} at {when}."]
        else:
            lines = [f"Memory Lane: {len(items)} things for {name}, around {when}:"] + [
                f"- {KIND_TEXT.get(i['kind'], i['kind'])}" for i in items]
        quotes = [i["detail"] for i in items if words and i["detail"] and i["kind"] in WORDS_KINDS]
        if quotes:
            lines.append(f"They said: \u201c{quotes[0][:300]}\u201d")
        if PORTAL:
            lines.append(f"Open the portal: {PORTAL}/caregiver")
        await _deliver(targets, "\n".join(lines))
    except Exception:
        log.exception("alert notification failed")


async def handled(pid: int, actor: str, kind: str) -> None:
    """Tells everyone else that an alert was taken care of, so nobody acts twice."""
    if not TOKEN or kind not in PUSH_KINDS:
        return
    try:
        found = await _targets(pid)
        if found:
            await _deliver(found[2], f"Memory Lane: {actor} marked the alert for {found[0]} as handled.")
    except Exception:
        log.exception("handled notification failed")


async def remind_once() -> None:
    """One reminder for a serious alert that is still open after a while. Each alert is reminded once, never again."""
    async with db.pool.connection() as conn:
        rows = await (await conn.execute(
            """UPDATE alerts SET reminded_at = now() WHERE id IN (
                 SELECT id FROM alerts WHERE NOT resolved AND severity = 'high' AND reminded_at IS NULL
                   AND created_at < now() - make_interval(mins => %s) AND created_at > now() - interval '6 hours')
               RETURNING patient_id, kind""", (REMIND_AFTER_MINUTES,))).fetchall()
    for pid, kind in rows:
        if kind not in PUSH_KINDS:
            continue
        found = await _targets(pid)
        if found:
            name, _, targets = found
            await _deliver(targets, f"Memory Lane: still open for {name}, {KIND_TEXT.get(kind, kind)}. "
                                    f"Please check, or mark it handled. {PORTAL}/caregiver".strip())


async def reminder_loop() -> None:
    await asyncio.sleep(90)
    while True:
        try:
            await remind_once()
        except Exception:
            log.exception("reminder pass failed")
        await asyncio.sleep(60)


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def fire(pid: int, kind: str, detail: str) -> None:
    _spawn(alert(pid, kind, detail))


def fire_handled(pid: int, actor: str, kind: str) -> None:
    _spawn(handled(pid, actor, kind))


# ---------- owner controls ----------

@router.get("/{pid}/notify")
async def overview(pid: int):
    async with db.pool.connection() as conn:
        p = await (await conn.execute("SELECT notify_words FROM patients WHERE id = %s", (pid,))).fetchone()
        if not p:
            return JSONResponse({"detail": "not found"}, status_code=404)
        rows = await (await conn.execute(
            "SELECT id, name, created_at FROM notify_targets WHERE patient_id = %s ORDER BY created_at", (pid,))).fetchall()
    return {
        "enabled": bool(TOKEN), "bot": await bot_username(), "include_words": p[0],
        "targets": [dict(id=i, name=n, created_at=c.isoformat()) for i, n, c in rows],
    }


class LinkIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@router.post("/{pid}/notify/link")
async def make_link(pid: int, body: LinkIn, request: Request):
    """A one-time link for one person. It works once, for 24 hours."""
    bot = await bot_username()
    name = body.name.strip()
    if not bot or not name:
        return JSONResponse({"detail": "telegram is not set up"}, status_code=503)
    token = secrets.token_urlsafe(12)
    async with db.pool.connection() as conn:
        if not await (await conn.execute("SELECT 1 FROM patients WHERE id = %s", (pid,))).fetchone():
            return JSONResponse({"detail": "not found"}, status_code=404)
        await conn.execute("DELETE FROM notify_links WHERE expires_at < now()")
        await conn.execute(
            "INSERT INTO notify_links (token_hash, patient_id, name, expires_at) VALUES (%s, %s, %s, %s)",
            (_hash(token), pid, name, datetime.now(timezone.utc) + timedelta(hours=24)))
    await family.audit(pid, family.actor_of(request), "notify_link", f"for {name}")
    return {"link": f"https://t.me/{bot}?start={token}", "name": name, "expires_in_hours": 24}


class WordsIn(BaseModel):
    include: bool


@router.post("/{pid}/notify/words")
async def set_words(pid: int, body: WordsIn, request: Request):
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET notify_words = %s WHERE id = %s", (body.include, pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    await family.audit(pid, family.actor_of(request), "notify_words", "included" if body.include else "left out")
    return {"include_words": body.include}


@router.post("/{pid}/notify/test")
async def test(pid: int, request: Request):
    async with db.pool.connection() as conn:
        p = await (await conn.execute("SELECT name FROM patients WHERE id = %s", (pid,))).fetchone()
        targets = await (await conn.execute("SELECT chat_id FROM notify_targets WHERE patient_id = %s", (pid,))).fetchall()
    if not p:
        return JSONResponse({"detail": "not found"}, status_code=404)
    sent = 0
    for (chat,) in targets:
        if await send(chat, f"Memory Lane test for {p[0]}. Alerts will arrive in this chat.") == "ok":
            sent += 1
    await family.audit(pid, family.actor_of(request), "notify_test", f"{sent} of {len(targets)} delivered")
    return {"sent": sent, "connected": len(targets)}


@router.post("/{pid}/notify/{tid}/remove")
async def remove(pid: int, tid: int, request: Request):
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "DELETE FROM notify_targets WHERE id = %s AND patient_id = %s RETURNING name", (tid, pid))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    await family.audit(pid, family.actor_of(request), "notify_removed", row[0])
    return {"removed": True}


# ---------- Telegram's call ----------

@hook.post("/telegram/webhook")
async def webhook(request: Request):
    if not WEBHOOK_SECRET or not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), WEBHOOK_SECRET):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    try:
        msg = (await request.json()).get("message") or {}
    except ValueError:
        return {"ok": True}
    chat, text = msg.get("chat") or {}, (msg.get("text") or "").strip()
    chat_id = chat.get("id")
    if not chat_id or chat.get("type") != "private":
        return {"ok": True}

    if text.startswith("/stop"):
        async with db.pool.connection() as conn:
            await conn.execute("DELETE FROM notify_targets WHERE chat_id = %s", (chat_id,))
        await send(chat_id, "Stopped. You will not get alerts here any more. Ask the family owner for a new link to start again.")
    elif text.startswith("/start") and text[6:].strip():
        async with db.pool.connection() as conn:
            link = await (await conn.execute(
                "DELETE FROM notify_links WHERE token_hash = %s AND expires_at > now() RETURNING patient_id, name",
                (_hash(text[6:].strip()),))).fetchone()
            if link:
                pid, name = link
                await conn.execute(
                    """INSERT INTO notify_targets (patient_id, name, chat_id) VALUES (%s, %s, %s)
                       ON CONFLICT (patient_id, chat_id) DO UPDATE SET name = EXCLUDED.name""", (pid, name, chat_id))
                patient = (await (await conn.execute("SELECT name FROM patients WHERE id = %s", (pid,))).fetchone())[0]
        if link:
            await family.audit(pid, name, "notify_connected", "telegram")
            await send(chat_id, f"Connected, {name}. You will get alerts about {patient} here. Send /stop to stop them.")
        else:
            await send(chat_id, "That link has expired or was already used. Ask the family owner for a new one.")
    elif text.startswith("/start"):
        await send(chat_id, "Hello. To get Memory Lane alerts here, ask the family owner for a link from the Privacy page, and open it.")
    else:
        await send(chat_id, "I only send alerts. Send /stop to stop them.")
    return {"ok": True}
