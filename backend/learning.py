"""Turns what the person says into durable facts and alerts, after the utterance has settled."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import alerts
import episodic_memory
import llm
import textutil
import working_memory
from config import PATIENT_TZ

log = logging.getLogger("learning")

DEBOUNCE_SECONDS = 4  # wait for the transcript to stop changing before learning from it
DUPLICATE_SCORE = 0.93
CATEGORIES = "object_location, medication, meal, plan, person, routine, preference, mood, other"

EXTRACT_SYSTEM = """You maintain the memory of {name}, who sometimes forgets small things.
Now is {now}. You get the companion's last line (context only) and what {name} just said.

Extract only durable facts worth remembering later: where things are, whether they did something (medication, meals), plans and appointments, people, routines, preferences, how they feel.
Rules:
- Each fact is one standalone sentence about {name} that makes sense with no conversation around it.
- Never record diagnoses or medical conditions as facts. They are kept in a separate profile.
- One fact per thing. Never restate the same thing in different words. At most 3 facts.
- Only what {name} actually said. Do not guess. If they sound unsure ("I guess"), write "probably".
- Skip greetings, thanks, small talk, filler, and anything vague. Returning no facts is normal.
- Short answers like "no" or "yes" count only when the companion's line makes the meaning clear (for example it asked if they took the pill).
- concern detail: quote what {name} said. Do not add causes, diagnoses, or links between events.
- concern: "confusion", "distress", or "missed_medication" ONLY when clearly shown (disoriented, frightened, in pain, says they skipped a dose). Otherwise "none".

Reply with JSON only, no other text:
{{"facts":[{{"text":"...","category":"one of: {cats}"}}],"concern":{{"kind":"none","detail":""}}}}"""


async def extract(name: str, prev_assistant: str, message: str) -> dict:
    now = datetime.now(ZoneInfo(PATIENT_TZ)).strftime("%A %d %B %Y, %H:%M")
    system = EXTRACT_SYSTEM.format(name=name, now=now, cats=CATEGORIES)
    user = f"Companion said: {prev_assistant or '(conversation just started)'}\n{name} said: {message}"
    text, _ = await llm.generate(system, [{"role": "user", "content": user}], max_tokens=400)
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


async def commit(patient_id: int, name: str, seq: int, prev_assistant: str, message: str) -> None:
    await asyncio.sleep(DEBOUNCE_SECONDS)
    if await working_memory.current_seq(patient_id) != seq:
        return  # a newer version of this utterance arrived, that one will do the learning
    if textutil.is_filler(message):
        return
    try:
        result = await extract(name, prev_assistant, message)
        for f in result.get("facts", []):
            text, cat = f.get("text", "").strip(), f.get("category", "other")
            if not text:
                continue
            near = await episodic_memory.search_memories(patient_id, text, k=1, include_family=False)
            if near:
                age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(near[0]["when"])).total_seconds() / 60
                same_dose = cat in ("medication", "meal") and near[0]["score"] >= 0.8 and age_min < 90
                if near[0]["score"] >= DUPLICATE_SCORE or same_dose:
                    await working_memory.log_event(
                        patient_id, "skipped", text, category=cat, near=near[0]["content"], score=round(near[0]["score"], 2))
                    continue
            await episodic_memory.save_memory(patient_id, text, cat, "low" if cat == "mood" else None)
            await working_memory.log_event(patient_id, "learned", text, category=cat)
        concern = result.get("concern") or {}
        if concern.get("kind") in ("confusion", "distress", "missed_medication"):
            await alerts.raise_alert(patient_id, concern["kind"], concern.get("detail", ""))
    except Exception:
        log.exception("learning failed for %r", message)
