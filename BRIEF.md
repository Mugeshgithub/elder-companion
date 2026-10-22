# Elder Companion: Hackathon Brief

A proactive voice AI caregiver for elderly people with memory trouble (e.g. "Margaret"), plus a live dashboard for family. One-day build.

## The goal
Stand out from generic "press a button, ask a question, wait" chatbot demos. Three differentiators:

### 1. Proactive, not reactive
The agent starts contact based on data triggers:
- Valkey detects no speech or movement for ~4 hours
- A scheduled time is hit (calendar or medication reminder)

Example: "Hi Margaret, it's 2:00 PM. Remember we agreed you'd take your blue pill right after lunch? Did you manage to grab it?"

### 2. Dual-memory engine (sponsor flex: Aiven)
- **Working memory**: Aiven for Valkey. Fast cache for the current conversation loop, emotional state, immediate context.
- **Episodic memory**: Aiven for PostgreSQL + pgvector (or OpenSearch). Long-term logs over weeks and months.
- On every user utterance, search both pools in parallel and feed the LLM: `Relevant past memories: [X, Y, Z]` before it answers.

### 3. Voice-to-voice streaming, low latency
- Avoid the clumsy STT -> LLM -> TTS chain (4-5 s delay).
- Use ElevenLabs Conversational AI SDK or OpenAI Realtime API: streaming, feels like a phone call.
- Barge-in: if the user interrupts, the agent stops talking immediately and listens.

## Architecture (three parallel tracks)
```
[ Backend & AI Pipeline ] -> n8n + FastAPI / Modal
[ Data & Memory Layer   ] -> Valkey + pgvector / OpenSearch
[ Frontend & UI         ] -> Lovable / Vercel + ElevenLabs widget
```

## Roadmap
| Hours | Track | Work |
|---|---|---|
| 1-3 | Core pipeline | n8n workflow or Modal backend: capture audio -> Claude (empathetic prompt) -> ElevenLabs |
| 3-6 | Memory injector | Connect DBs. Script that vectorizes and stores past conversations. Prompt always includes "Relevant past memories: [...]" |
| 6-9 | Front-end polish | High-contrast UI for elderly eyes (large buttons, simple text). Family dashboard: log in, see live log of what the patient remembered or struggled with today |

## Offered next steps (not yet done)
- System prompt for the empathetic caregiver AI
- Python for dual-memory search (Valkey + pgvector)

## Open decisions
- Voice layer: ElevenLabs Conversational AI vs OpenAI Realtime
- Episodic store: pgvector vs OpenSearch
- Orchestration: n8n vs FastAPI/Modal
- Proactive trigger scheduler (cron / Valkey keyspace events)
