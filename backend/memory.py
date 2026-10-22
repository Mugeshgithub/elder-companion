"""Dual-memory search: working (Valkey) and episodic (pgvector) are queried in parallel."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import episodic_memory
import working_memory
from config import PATIENT_TZ


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(PATIENT_TZ))


async def build_context(patient_id: int, utterance: str) -> dict:
    turns, mood, memories, today = await asyncio.gather(
        working_memory.recent_turns(patient_id),
        working_memory.get_mood(patient_id),
        episodic_memory.search_memories(patient_id, utterance),
        episodic_memory.today_facts(patient_id, PATIENT_TZ),
    )
    return {"turns": turns, "mood": mood, "memories": memories, "today": today}


def format_for_prompt(ctx: dict) -> str:
    lines = []
    if ctx["mood"]:
        lines.append(f"Current mood: {ctx['mood']}")
    if ctx["today"]:
        lines.append("Confirmed today (things they told us):")
        lines += [f"- {_local(t['at']):%H:%M} {t['content']}" for t in ctx["today"]]
    else:
        lines.append("Confirmed today: nothing yet beyond what the person says in this conversation.")
    if ctx["memories"]:
        lines.append("Relevant past memories:")
        lines += [
            f"- (from family, background only) {m['content']}" if m.get("source") == "family"
            else f"- ({_local(m['when']):%a %d %b %H:%M}) {m['content']}"
            for m in ctx["memories"]
        ]
    return "\n".join(lines)
