"""Working memory in Valkey: the live conversation loop, mood, and the inactivity timer."""
import json
import time

import redis.asyncio as redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from config import INACTIVITY_SECONDS, VALKEY_URI

# Aiven closes idle connections after 300s, so check the connection before use and retry once on a dropped one
r = redis.from_url(
    VALKEY_URI, decode_responses=True, health_check_interval=20,
    retry=Retry(ExponentialBackoff(), 2), retry_on_error=[RedisConnectionError, RedisTimeoutError],
)

MAX_TURNS = 20


def _k(patient_id: int, name: str) -> str:
    return f"patient:{patient_id}:{name}"


async def add_turn(patient_id: int, role: str, text: str) -> None:
    key = _k(patient_id, "turns")
    await r.rpush(key, json.dumps({"role": role, "text": text, "ts": time.time()}))
    await r.ltrim(key, -MAX_TURNS, -1)
    await r.expire(key, 24 * 3600)


async def recent_turns(patient_id: int, n: int = 10) -> list[dict]:
    raw = await r.lrange(_k(patient_id, "turns"), -n, -1)
    return [json.loads(x) for x in raw]


async def set_mood(patient_id: int, mood: str) -> None:
    await r.set(_k(patient_id, "mood"), mood, ex=6 * 3600)


async def get_mood(patient_id: int) -> str | None:
    return await r.get(_k(patient_id, "mood"))


async def touch_activity(patient_id: int, ttl: int = INACTIVITY_SECONDS) -> None:
    """Reset the inactivity timer. When this key expires, the trigger listener fires."""
    await r.set(_k(patient_id, "alive"), "1", ex=ttl)


# ElevenLabs sends several requests per utterance (partial and repeated transcripts).
# These helpers collapse them into one exchange.
import hashlib

from textutil import norm, similar

SUPERSEDE_WINDOW = 20  # seconds


def _h(message: str) -> str:
    return hashlib.sha1(norm(message).encode()).hexdigest()[:16]


async def cached_reply(patient_id: int, message: str) -> str | None:
    """Only valid while nothing new has been said: the key includes the current sequence number,
    so the same question asked after any other message is answered fresh."""
    seq = await current_seq(patient_id)
    return await r.get(_k(patient_id, f"reply:{seq}:{_h(message)}"))


async def cache_reply(patient_id: int, message: str, reply: str, seq: int) -> None:
    await r.set(_k(patient_id, f"reply:{seq}:{_h(message)}"), reply, ex=8)


async def drop_superseded(patient_id: int, message: str) -> None:
    """If the last exchange was an earlier or partial version of this same utterance, remove it."""
    turns = await recent_turns(patient_id, 2)
    if (
        len(turns) == 2
        and turns[0]["role"] == "user"
        and turns[1]["role"] == "assistant"
        and time.time() - turns[0]["ts"] < SUPERSEDE_WINDOW
        and similar(turns[0]["text"], message)
    ):
        await r.rpop(_k(patient_id, "turns"), 2)


async def next_seq(patient_id: int) -> int:
    return await r.incr(_k(patient_id, "seq"))


async def current_seq(patient_id: int) -> int:
    return int(await r.get(_k(patient_id, "seq")) or 0)


# A short live feed of what the system just did, shown in the memory inspector.
# It is never read back into a reply, and a failure here must never break a conversation.
EVENT_LIMIT = 40


async def log_event(patient_id: int, kind: str, text: str, **extra) -> None:
    try:
        key = _k(patient_id, "events")
        await r.lpush(key, json.dumps({"t": time.time(), "kind": kind, "text": text, **extra}))
        await r.ltrim(key, 0, EVENT_LIMIT - 1)
        await r.expire(key, 24 * 3600)
    except Exception:
        pass


async def recent_events(patient_id: int, n: int = 30) -> list[dict]:
    raw = await r.lrange(_k(patient_id, "events"), 0, n - 1)
    return [json.loads(x) for x in raw]
