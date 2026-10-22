"""Builds the first spoken line of a call, using only what is actually recorded."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import db
import llm
from config import PATIENT_TZ

log = logging.getLogger("opener")

SYSTEM = """You write the first thing a voice companion says to {name} when a call starts. It will be spoken aloud.
Now is {now}. {situation}

Rules:
- One or two short, warm sentences. Plain words. Use {name}'s name once.
- Use ONLY the facts listed below, and only if one is clearly useful (an unfinished plan, or something that worried them). Otherwise just greet or check in.
- Never claim to see, hear, or sense anything. Never mention music, the room, the weather, the sun, or the house. Never say they are safe or where they are.
- Never ask them to remember or think back. At most one gentle, easy question.
- Never describe the evening, the day, or the quiet as calm, quiet, peaceful, or similar. Do not say it is good to hear from them when they have not spoken yet.
- Never mention any diagnosis or illness.
- Output only the spoken line, nothing else.

Recent facts (last 24 hours, may be empty):
{facts}"""


BANNED = ("quiet", "calm", "peaceful", "safe", "music", "living room", "weather", "sun", "alzheimer", "dementia")


def _acceptable(text: str, proactive: bool) -> bool:
    low = text.lower()
    if any(b in low for b in BANNED):
        return False
    return not (proactive and "hear from you" in low)  # they have not spoken yet


def _fallback(name: str, proactive: bool, hour: int) -> str:
    if proactive:
        return f"Hi {name}, I haven't heard from you for a little while, so I wanted to check in. How are you doing?"
    part = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    return f"{part}, {name}. How are you feeling?"


async def build_opener(patient_id: int, name: str, proactive: bool) -> str:
    local = datetime.now(ZoneInfo(PATIENT_TZ))
    async with db.pool.connection() as conn:
        cur = await conn.execute(
            """SELECT content FROM memories WHERE patient_id = %s AND source = 'person' AND created_at > now() - interval '24 hours'
               ORDER BY created_at DESC LIMIT 8""", (patient_id,))
        facts = [r[0] for r in await cur.fetchall()]
    situation = (
        f"{name} has not spoken to you for a while, so you are reaching out first."
        if proactive else f"{name} just started the call."
    )
    system = SYSTEM.format(
        name=name, now=local.strftime("%A %H:%M"), situation=situation,
        facts="\n".join(f"- {f}" for f in facts) or "(none)",
    )
    try:
        text, _ = await llm.generate(system, [{"role": "user", "content": "Write the opening line."}], max_tokens=80)
        text = text.strip().strip('"')
        if text and len(text) < 300 and _acceptable(text, proactive):
            return text
    except Exception:
        log.exception("opener generation failed")
    return _fallback(name, proactive, local.hour)
