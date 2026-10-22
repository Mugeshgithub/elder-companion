"""Optional, limited location sharing.

What it is: while a page is open on the person's phone and they have pressed Share, the phone sends its position about
once a minute. If they have been outside a safe area around home for five minutes, the family is told, with a map link.
What it is not: background tracking. A web page cannot do that, so when the page is closed the family sees "not sharing",
never a guess. Only the latest position is kept, never a history, and Stop deletes it.
"""
import logging
import math
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import alerts
import db
import family
import working_memory

log = logging.getLogger("location")
router = APIRouter(prefix="/location")

LEAVE_AFTER_SECONDS = 300  # outside the safe area this long before anyone is told
FRESH_SECONDS = 600        # a position older than this counts as "not sharing"
COOLDOWN_SECONDS = 2 * 3600


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def _inside(lat: float, lng: float, accuracy: float | None, home: tuple[float, float, int]) -> bool:
    # a poor fix gets the benefit of the doubt, so a wobbling signal near the edge does not raise an alarm
    return distance_m(lat, lng, home[0], home[1]) - min(accuracy or 0, 200) <= home[2]


class Fix(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100000)


async def record(pid: int, lat: float, lng: float, accuracy: float | None) -> dict | None:
    async with db.pool.connection() as conn:
        row = await (await conn.execute("SELECT home_lat, home_lng, safe_radius_m FROM patients WHERE id = %s", (pid,))).fetchone()
        if not row:
            return None
        await conn.execute(
            """INSERT INTO last_location (patient_id, lat, lng, accuracy, at) VALUES (%s, %s, %s, %s, now())
               ON CONFLICT (patient_id) DO UPDATE SET lat = EXCLUDED.lat, lng = EXCLUDED.lng, accuracy = EXCLUDED.accuracy, at = now()""",
            (pid, lat, lng, accuracy))
    home = (row[0], row[1], row[2]) if row[0] is not None and row[1] is not None else None
    inside = _inside(lat, lng, accuracy, home) if home else None
    r = working_memory.r
    key = f"loc:{pid}:outside_since"
    if inside is False:
        since = await r.get(key)
        if not since:
            await r.set(key, str(time.time()), ex=24 * 3600)
        elif time.time() - float(since) >= LEAVE_AFTER_SECONDS and await r.set(f"loc:{pid}:alerted", "1", nx=True, ex=COOLDOWN_SECONDS):
            await alerts.raise_alert(pid, "left_safe_area", f"https://www.google.com/maps?q={lat:.5f},{lng:.5f}", dedupe_minutes=120)
    elif inside is True:
        await r.delete(key, f"loc:{pid}:alerted")  # back inside: the next outing can alert again
    return {"inside": inside, "home_set": home is not None}


async def status(pid: int) -> dict:
    """What the portal shows. No coordinates, only whether they are sharing and whether they are inside."""
    async with db.pool.connection() as conn:
        p = await (await conn.execute("SELECT home_lat, home_lng, safe_radius_m FROM patients WHERE id = %s", (pid,))).fetchone()
        loc = await (await conn.execute(
            "SELECT lat, lng, accuracy, at, extract(epoch FROM now() - at) FROM last_location WHERE patient_id = %s", (pid,))).fetchone()
    home = (p[0], p[1], p[2]) if p and p[0] is not None and p[1] is not None else None
    sharing = bool(loc and loc[4] < FRESH_SECONDS)
    return {
        "home_set": home is not None, "radius": p[2] if p else None, "sharing": sharing,
        "at": loc[3].isoformat() if loc else None,
        "inside": _inside(loc[0], loc[1], loc[2], home) if (loc and home and sharing) else None,
    }


@router.post("/{pid}")
async def share(pid: int, fix: Fix):
    out = await record(pid, fix.lat, fix.lng, fix.accuracy)
    if out is None:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return out


class Home(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius: int = Field(default=300, ge=50, le=5000)


@router.post("/{pid}/home")
async def set_home(pid: int, body: Home, request: Request):
    async with db.pool.connection() as conn:
        cur = await conn.execute("UPDATE patients SET home_lat = %s, home_lng = %s, safe_radius_m = %s WHERE id = %s",
                                 (body.lat, body.lng, body.radius, pid))
        if cur.rowcount != 1:
            return JSONResponse({"detail": "not found"}, status_code=404)
    await working_memory.r.delete(f"loc:{pid}:outside_since", f"loc:{pid}:alerted")
    await family.audit(pid, family.actor_of(request), "location_home", f"safe area of {body.radius} m")
    return {"home_set": True, "radius": body.radius}


@router.post("/{pid}/stop")
async def stop(pid: int, request: Request):
    """Stop sharing: the last position is deleted, not kept."""
    async with db.pool.connection() as conn:
        await conn.execute("DELETE FROM last_location WHERE patient_id = %s", (pid,))
    await working_memory.r.delete(f"loc:{pid}:outside_since", f"loc:{pid}:alerted")
    await family.audit(pid, family.actor_of(request), "location_stopped", "last position deleted")
    return {"stopped": True}


@router.get("/{pid}")
async def get_status(pid: int):
    return await status(pid)
