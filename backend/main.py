import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import alerts
import db
import documents
import episodic_memory
import family
import location
import notify
import reminders
import intents
import learning
import opener
import textutil
import llm
import memory
import triggers
import working_memory
from config import AGENT_SHARED_SECRET, INACTIVITY_SECONDS, PATIENT_TZ
from prompt import CAREGIVER_SYSTEM, CHECKIN_OPENER


async def _patient(patient_id: int) -> tuple[str, str, int | None, bool]:
    """name, profile, this person's own check-in window in seconds (None means the server default), and
    whether the family has paused monitoring."""
    async with db.pool.connection() as conn:
        cur = await conn.execute(
            "SELECT name, COALESCE(profile, ''), checkin_seconds, paused FROM patients WHERE id = %s", (patient_id,))
        row = await cur.fetchone()
    return (row[0], row[1], row[2], row[3]) if row else ("friend", "", None, False)


async def _patient_name(patient_id: int) -> str:
    async with db.pool.connection() as conn:
        cur = await conn.execute("SELECT name FROM patients WHERE id = %s", (patient_id,))
        row = await cur.fetchone()
    return row[0] if row else "friend"


async def _on_inactive(patient_id: int) -> None:
    if await db.is_paused(patient_id):
        return  # monitoring is paused: no alert and no check-in call
    if await working_memory.r.get(f"patient:{patient_id}:dnd"):
        return  # they said goodnight, so silence is expected
    await working_memory.log_event(patient_id, "trigger", "Silence timer expired (Valkey key-expiry event)")
    await alerts.raise_alert(patient_id, "inactivity", "No activity within the check-in window", dedupe_minutes=1)
    await working_memory.r.set(f"patient:{patient_id}:checkin_pending", "1", ex=3600, nx=True)  # never replaces a waiting message


async def _on_reminder(patient_id: int, kind: str, compact: str) -> None:
    await (reminders.fire if kind == "remind" else reminders.check)(patient_id, compact)


_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.pool.open(wait=True, timeout=30)  # connections are ready before the first request
    try:
        await reminders.schedule_all()  # make sure every medicine time has its timer
    except Exception:
        logging.getLogger("main").exception("could not schedule reminders at start")
    task = asyncio.create_task(triggers.listen_for_inactivity(_on_inactive, _on_reminder))
    digest = asyncio.create_task(notify.digest_loop())
    purge = asyncio.create_task(family.purge_loop())
    remind = asyncio.create_task(notify.reminder_loop())
    resume = asyncio.create_task(documents.resume_stuck())
    yield
    task.cancel()
    purge.cancel()
    remind.cancel()
    resume.cancel()
    digest.cancel()
    await db.pool.close()


app = FastAPI(title="Elder Companion", lifespan=lifespan)
app.include_router(family.router)
app.include_router(documents.router)
app.include_router(notify.router)
app.include_router(notify.hook)
app.include_router(location.router)


@app.middleware("http")
async def require_secret(request: Request, call_next):
    """The server is reachable through a public tunnel, so every route needs the shared secret."""
    # Telegram cannot send our key, so its webhook is checked by its own secret header inside the route
    if request.url.path != "/telegram/webhook" and request.headers.get("x-api-key") != AGENT_SHARED_SECRET:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


class ChatIn(BaseModel):
    patient_id: int = 1
    message: str | None = None  # None means the agent is opening a proactive check-in


async def _on_silence_message(pid: int) -> dict:
    """ElevenLabs sends "..." when the person is silent. Never spend a model call or say anything alarming for that."""
    key = f"patient:{pid}:fillers"
    streak = await working_memory.r.incr(key)
    await working_memory.r.expire(key, 300)
    if streak >= 2 and not await working_memory.r.get(f"patient:{pid}:dnd"):
        await alerts.raise_alert(pid, "no_response", "The check-in call was not answered.", dedupe_minutes=30)
        await working_memory.r.delete(f"patient:{pid}:checkin_pending")  # do not call an empty room again
    # the first silence gets one gentle line; after that the companion waits quietly, until the person speaks again
    return {"reply": "Take your time. I'm here." if streak == 1 else "", "model": "silence", "memories_used": 0}


async def respond(pid: int, message: str | None) -> dict:
    opener = message is None
    if not opener and textutil.is_filler(message):
        return await _on_silence_message(pid)

    if opener:
        name, profile, window, paused = await _patient(pid)
        text = CHECKIN_OPENER.format(name=name)
        ctx = await memory.build_context(pid, text)
    else:
        cached = await working_memory.cached_reply(pid, message)
        if cached:  # ElevenLabs often repeats the same request
            return {"reply": cached, "model": "cache", "memories_used": 0}
        await working_memory.drop_superseded(pid, message)
        text = message
        (name, profile, window, paused), ctx = await asyncio.gather(_patient(pid), memory.build_context(pid, text))
    if not opener:
        await working_memory.log_event(pid, "recall", message, hits=[
            {"content": m["content"], "category": m["category"], "score": round(m["score"], 2)} for m in ctx["memories"][:4]])
    prev = next((t["text"] for t in reversed(ctx["turns"]) if t["role"] == "assistant"), "")
    context = memory.format_for_prompt(ctx)
    notify_confirmed = not opener and not paused and intents.wants_family_notified(message, prev)
    if notify_confirmed:
        await alerts.raise_alert(pid, "family_notification_request", intents.snippet(message, prev), dedupe_minutes=5)
        context += (
            "\n\nThe person just asked you to let their family know. A note for their family has been recorded "
            "and they will see it on their dashboard. Say so in one short, calm sentence. Do not say you will call or visit."
        )
    quiet = not opener and intents.wants_quiet(message)
    if quiet:
        await working_memory.r.set(f"patient:{pid}:dnd", "1", ex=8 * 3600)
        context += "\n\nThey are going to sleep or want quiet. Reply with one short goodnight and nothing else. Ask nothing and offer nothing."
    elif not opener:
        await working_memory.r.delete(f"patient:{pid}:dnd")
    if paused:
        context += "\n\nNotes for their family are switched off right now. Never offer to leave a note or let their family know."
    system = CAREGIVER_SYSTEM.format(
        name=name, profile=f"Always keep in mind: {profile}\n" if profile else "", context=context)
    history = [{"role": t["role"], "content": t["text"]} for t in ctx["turns"]]
    reply, model_used = await llm.generate(system, history + [{"role": "user", "content": text}])

    if not opener and intents.asks_dose_advice(message):
        reply = intents.DOSE_ADVICE_REPLY_PAUSED if paused else intents.DOSE_ADVICE_REPLY  # never the model's to improvise
    elif not opener and not notify_confirmed and intents.reply_commits_to_note(reply):
        # a promise nobody asked for would be unkept, and recording it would be a false alarm: ask instead
        reply = "I'm here with you." if paused else "I'm here with you. Would you like me to leave a note for your family so they know?"

    await asyncio.gather(
        working_memory.log_event(pid, "reply", reply, model=model_used),
        working_memory.touch_activity(pid, window or INACTIVITY_SECONDS),
        working_memory.clear_checkin(pid),
    )
    if not opener:
        await working_memory.add_turn(pid, "user", message)
    await working_memory.add_turn(pid, "assistant", reply)
    if not opener:
        await working_memory.r.delete(f"patient:{pid}:fillers")
        seq = await working_memory.next_seq(pid)
        await working_memory.cache_reply(pid, message, reply, seq)
        if not paused:
            _spawn(learning.commit(pid, name, seq, prev, message))
    return {"reply": reply, "model": model_used, "memories_used": len(ctx["memories"])}


@app.post("/chat")
async def chat(body: ChatIn):
    return await respond(body.patient_id, body.message)


async def _first_call(patient_id: int) -> bool:
    """True exactly once per setup: flips the flag in the same statement, so two requests cannot both win."""
    async with db.pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE patients SET intro_done = true WHERE id = %s AND NOT intro_done RETURNING id", (patient_id,))
        return await cur.fetchone() is not None


@app.get("/opener/{patient_id}")
async def get_opener(patient_id: int, proactive: bool = False, reason: str = ""):
    name = await _patient_name(patient_id)
    if proactive and reason == "reminder":
        line = await reminders.opener_line(patient_id, name)
        if line:
            return {"opener": line}
        proactive = False  # the reminder was already taken care of, so just greet
    if proactive and reason == "message":
        # the companion reached out to pass on a message, not because it was quiet, so it does not say it was
        waiting = await family.take_messages(patient_id)
        if waiting:
            return {"opener": f"Hello {name}. {family.spoken(waiting)}"}
        proactive = False  # someone already said it, so just greet
    if not proactive and await _first_call(patient_id):
        line = (f"Hello {name}. I'm Memory Lane, an AI voice companion. Your family asked me to keep you company. "
                "Tell me things you want to remember, and ask me where anything is. I'll check in on you too.")
    else:
        line = await opener.build_opener(patient_id, name, proactive)
    waiting = await family.take_messages(patient_id)
    if waiting:
        line = f"{line} {family.spoken(waiting)}"
    return {"opener": line}


@app.post("/activity/{patient_id}")
async def activity(patient_id: int):
    await working_memory.r.delete(f"patient:{patient_id}:dnd")  # a manual start means they are awake
    _, _, window, _ = await _patient(patient_id)
    await working_memory.touch_activity(patient_id, window or INACTIVITY_SECONDS)
    return {"ok": True}


@app.get("/checkin/{patient_id}")
async def checkin_pending(patient_id: int):
    flag = await working_memory.r.get(f"patient:{patient_id}:checkin_pending")
    return {"pending": bool(flag), "reason": flag if flag in ("message", "reminder") else "silence"}


def _status(alerts_out: list[dict], pending: bool) -> dict:
    open_ = [a for a in alerts_out if not a["resolved"]]
    high = [a for a in open_ if a["severity"] == "high"]
    if high:
        high.sort(key=lambda a: a["kind"] != "family_notification_request")
        return {"level": "red", "title": "Needs attention", "note": "A high priority alert is open.", "kind": high[0]["kind"]}
    recent = [a for a in open_ if (datetime.now(timezone.utc) - datetime.fromisoformat(a["at"])).total_seconds() < 7200]
    if pending or recent:
        return {"level": "amber", "title": "Check-in pending" if pending else "Worth a look",
                "note": "The companion is reaching out now." if pending else "An alert from the last two hours is open.", "kind": None}
    return {"level": "green", "title": "All secure", "note": "No open alerts.", "kind": None}


@app.get("/dashboard/{patient_id}")
async def dashboard(patient_id: int):
    name = await _patient_name(patient_id)
    pending = bool(await working_memory.r.get(f"patient:{patient_id}:checkin_pending"))
    async with db.pool.connection() as conn:
        mem = await (await conn.execute(
            """SELECT content, category, created_at FROM memories
               WHERE patient_id = %s AND source = 'person' AND content !~ '^[^ ]+ said: '
                 AND created_at >= (date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s)
               ORDER BY created_at DESC LIMIT 50""", (patient_id, PATIENT_TZ, PATIENT_TZ))).fetchall()
        al = await (await conn.execute(
            """SELECT id, kind, severity, detail, resolved, created_at FROM alerts
               WHERE patient_id = %s AND (NOT resolved OR created_at > now() - interval '24 hours')
               ORDER BY resolved, created_at DESC LIMIT 30""", (patient_id,))).fetchall()
        meta = await (await conn.execute("SELECT consent, paused FROM patients WHERE id = %s", (patient_id,))).fetchone()
        msgs = await (await conn.execute(
            """SELECT id, from_name, text, created_at, delivered_at FROM family_messages
               WHERE patient_id = %s ORDER BY created_at DESC LIMIT 5""", (patient_id,))).fetchall()
    alerts_out = [dict(id=i, kind=k, severity=s, detail=d, resolved=r, at=t.isoformat()) for i, k, s, d, r, t in al]
    return {
        "patient": name,
        "pending_checkin": pending,
        "status": _status(alerts_out, pending),
        "memories": [dict(content=c, category=k, at=t.isoformat()) for c, k, t in mem],
        "alerts": alerts_out,
        "consent": meta[0] if meta else None,
        "paused": bool(meta and meta[1]),
        "location": await location.status(patient_id),
        "messages": [dict(id=i, from_name=n, text=t, at=c.isoformat(), delivered_at=d.isoformat() if d else None)
                     for i, n, t, c, d in msgs],
    }


class Med(BaseModel):
    name: str = Field(max_length=80)
    time: str = Field(default="", max_length=5)  # "09:00"


class Person(BaseModel):
    name: str = Field(max_length=60)
    relation: str = Field(max_length=40)


class Place(BaseModel):
    item: str = Field(max_length=60)
    place: str = Field(max_length=80)


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=400)  # kept as the private profile, never a searchable memory
    meds: list[Med] = Field(default=[], max_length=10)
    routines: list[str] = Field(default=[], max_length=10)
    people: list[Person] = Field(default=[], max_length=10)
    places: list[Place] = Field(default=[], max_length=10)
    checkin_minutes: int | None = Field(default=None, ge=1, le=1440)


def _family_facts(s: SetupIn) -> list[tuple[str, str]]:
    """The form as sentences. A medication schedule is a routine, never a medication event:
    only the person saying so today confirms a dose."""
    out = []
    for m in s.meds:
        if m.name.strip():
            when = f" at {m.time}" if m.time.strip() else ""
            out.append((f"{s.name} takes {m.name.strip()}{when} each day.", "routine"))
    out += [(r.strip(), "routine") for r in s.routines if r.strip()]
    out += [(f"{p.name.strip()} is {s.name}'s {p.relation.strip()}.", "person") for p in s.people if p.name.strip()]
    out += [(f"Usual place for {s.name}'s {pl.item.strip()}: {pl.place.strip()}.", "object_location")
            for pl in s.places if pl.item.strip() and pl.place.strip()]
    return out


@app.get("/setup/{patient_id}")
async def get_setup(patient_id: int):
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT name, COALESCE(profile, ''), setup, checkin_seconds FROM patients WHERE id = %s", (patient_id,))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    name, profile, setup, secs = row
    base = {"name": name, "note": profile, "meds": [], "routines": [], "people": [], "places": [],
            "checkin_minutes": round(secs / 60) if secs else None}
    return {**base, **(setup or {}), "name": name, "note": profile}


@app.post("/setup/{patient_id}")
async def save_setup(patient_id: int, body: SetupIn, request: Request):
    """Replaces everything the family previously entered. The companion introduces itself again on the next call."""
    secs = body.checkin_minutes * 60 if body.checkin_minutes else None
    async with db.pool.connection() as conn:
        cur = await conn.execute(
            """UPDATE patients SET name = %s, profile = %s, setup = %s::jsonb, checkin_seconds = %s, intro_done = false
               WHERE id = %s""",
            (body.name.strip(), body.note.strip(), body.model_dump_json(), secs, patient_id))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
        await conn.execute("DELETE FROM memories WHERE patient_id = %s AND source = 'family' AND category <> 'message'", (patient_id,))
    facts = _family_facts(body)
    await asyncio.gather(*[
        episodic_memory.save_memory(patient_id, text, cat, None, "family") for text, cat in facts])
    await working_memory.log_event(patient_id, "setup", f"Family setup saved: {len(facts)} facts for the companion")
    await family.audit(patient_id, family.actor_of(request), "setup", f"{len(facts)} notes for the companion")
    await reminders.schedule(patient_id, reset=True)  # medicine times may have changed
    return {"saved": True, "facts": len(facts)}


@app.get("/inspect/{patient_id}")
async def inspect(patient_id: int):
    """Everything the memory layers hold right now, for the live inspector on the demo page."""
    pid, r = patient_id, working_memory.r
    keys = sorted([k async for k in r.scan_iter(match=f"patient:{pid}:*", count=100)])
    keys = [k for k in keys if ":reply:" not in k]  # the 8 second reply cache is noise
    ttls = await asyncio.gather(*[r.ttl(k) for k in keys])
    alive, dnd, pending, mood, turns, events = await asyncio.gather(
        r.ttl(f"patient:{pid}:alive"), r.ttl(f"patient:{pid}:dnd"), r.get(f"patient:{pid}:checkin_pending"),
        working_memory.get_mood(pid), working_memory.recent_turns(pid, 8), working_memory.recent_events(pid, 30))
    async with db.pool.connection() as conn:
        total = (await (await conn.execute("SELECT count(*) FROM memories WHERE patient_id = %s", (pid,))).fetchone())[0]
        rows = await (await conn.execute(
            """SELECT content, category, created_at, source FROM memories
               WHERE patient_id = %s AND content !~ '^[^ ]+ said: '
               ORDER BY created_at DESC LIMIT 12""", (pid,))).fetchall()
    return {
        "working": {
            "silence_ttl": alive, "silence_limit": INACTIVITY_SECONDS, "dnd_ttl": dnd,
            "checkin_pending": bool(pending), "mood": mood, "turns": turns,
            "keys": [{"key": k.split(":", 2)[2], "ttl": t} for k, t in zip(keys, ttls)],
        },
        "episodic": {
            "total": total,
            "recent": [dict(content=c, category=k, at=t.isoformat(), source=src) for c, k, t, src in rows],
        },
        "events": events,
    }


@app.post("/alerts/{patient_id}/{alert_id}/resolve")
async def resolve_alert(patient_id: int, alert_id: int, request: Request):
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            "UPDATE alerts SET resolved = true WHERE id = %s AND patient_id = %s RETURNING kind", (alert_id, patient_id))).fetchone()
        done = row is not None
    if done:
        await family.audit(patient_id, family.actor_of(request), "alert_handled", f"alert {alert_id}")
        notify.fire_handled(patient_id, family.actor_of(request), row[0])  # so the others do not act twice
    return {"resolved": done}


@app.post("/v1/chat/completions")
async def openai_compatible(request: Request):
    """OpenAI-compatible route so ElevenLabs can use us as its custom LLM.
    ElevenLabs sends the whole transcript; we only take the latest user turn
    because our own memory layer supplies the history and context."""
    body = await request.json()
    pid = int(request.headers.get("x-patient-id", 1))
    last_user = next((m["content"] for m in reversed(body.get("messages", [])) if m["role"] == "user"), None)
    if isinstance(last_user, list):  # content-parts format
        last_user = " ".join(p.get("text", "") for p in last_user)
    result = await respond(pid, last_user)
    reply, cid, created = result["reply"], f"chatcmpl-{int(time.time()*1000)}", int(time.time())

    def chunk(delta: dict, finish=None) -> str:
        return "data: " + json.dumps({
            "id": cid, "object": "chat.completion.chunk", "created": created, "model": body.get("model", "caregiver"),
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }) + "\n\n"

    if not body.get("stream"):
        return {"id": cid, "object": "chat.completion", "created": created, "model": body.get("model", "caregiver"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]}

    async def gen():
        yield chunk({"role": "assistant", "content": ""})
        for word in (reply.split(" ") if reply else []):  # an empty reply is a quiet turn: nothing to say
            yield chunk({"content": word + " "})
        yield chunk({}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
