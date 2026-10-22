# Elder Companion

A voice companion for someone with memory loss, and a family portal that shows what happened.
Built for one person (Mugesh) first. Built 2026-10-21.

## What it does
1. **Talks by voice.** A phone-call style conversation with interruptions handled. ElevenLabs does the audio, our server does the thinking.
2. **Remembers.** After you speak, it pulls out durable facts ("keys are in the blue bag", "took the blue pill") and answers from them later.
3. **Never guesses.** If it has nothing written down, it says so. It does not name places, plans, or doses that are not in memory.
4. **Reaches out first.** After 30 seconds of silence (4 hours in real use) it raises an alert and starts the call itself.
5. **Tells the family.** Distress, confusion, a missed dose, silence, an unanswered check-in, or a request ("tell my family") put an alert on the family portal.
6. **Respects sleep.** "Good night" means no calls and no silence alerts for 8 hours.

## How a conversation flows
```
You speak -> ElevenLabs (voice, interruptions)
          -> our server, through a cloudflared tunnel
               1. recent turns + mood       (Aiven Valkey)
               2. today's confirmed facts   (Aiven Postgres)
               3. past memories by meaning  (Aiven Postgres + pgvector)
               4. Claude writes the reply   (OpenAI is the fallback)
               5. reply goes back to ElevenLabs, which speaks it
          -> 4 seconds after you stop: Claude extracts facts and concerns, saved as memories and alerts
```

## Stack
| Part | Choice |
|---|---|
| Voice | ElevenLabs Conversational AI (custom LLM = our server) |
| Replies | Claude Haiku 5.5, thinking off. OpenAI gpt-4o-mini as fallback |
| Embeddings | OpenAI text-embedding-3-small, 1024 dimensions |
| Working memory | Aiven for Valkey 9.1 |
| Long-term memory | Aiven for PostgreSQL 18 with pgvector |
| Server | FastAPI (Python) |
| Screens | React + Vite + Tailwind |

## Code map
Backend, `backend/`
- `main.py`: the server and every endpoint, plus the shared reply logic (`respond`)
- `prompt.py`: the companion's instructions and safety rules
- `working_memory.py`: Valkey: recent turns, mood, silence timer, duplicate collapsing, reply cache, and a short event log for the inspector
- `episodic_memory.py`: Postgres: save and search memories, today's confirmed facts
- `memory.py`: queries both memories in parallel and builds the prompt context
- `learning.py`: after a pause, extracts facts and concerns from what was said
- `intents.py`: "tell my family" detection, "good night" detection, promise guard
- `alerts.py`: writes alerts with severity, avoids duplicates
- `triggers.py`: listens for Valkey key-expiry events (the silence trigger), reconnects if dropped
- `opener.py`: writes the first spoken line of each call from real facts
- `llm.py`: Claude first, OpenAI fallback
- `embeddings.py`, `textutil.py`, `config.py`, `schema.sql`, `create_agent.py`

Frontend, `frontend/src/`
- `Deck.tsx`: the slides at `/`, with an Open app button to `/demo`. Public, holds no data
- `Demo.tsx`: `/demo`, the companion on the left, the memory inspector on the right
- `Setup.tsx`: `/setup`, the family fills this in once: name, private note, daily medicine times, routine, people, usual places, check-in window
- `Inspector.tsx`: `/inspector`, live Valkey keys and silence timer, a feed of recalls with similarity scores, facts saved, alerts
- `PatientView.tsx`: the companion alone at `/app` (what the installed Mac app opens). A glow that follows the live voice
- `CaregiverView.tsx`: the family portal at `/caregiver`
- `api.ts`: every call goes through `/api`, with an access code when deployed
- `api/[...path].ts`: Vercel function that adds the backend secret server-side (needs ACCESS_CODE, AGENT_SHARED_SECRET, BACKEND_URL)
- A Vite proxy adds the shared secret, so it never reaches the browser

## API (all need the `x-api-key` secret)
- `POST /v1/chat/completions`: what ElevenLabs calls (OpenAI format, streaming)
- `POST /chat`: the same logic for typed tests
- `GET /opener/{id}`: first line of a call (`?proactive=true` for check-ins)
- `GET /checkin/{id}`: is a check-in pending
- `POST /activity/{id}`: a person is here (resets the silence timer, ends do-not-disturb)
- `GET /dashboard/{id}`: status, today's facts, alerts
- `GET /setup/{id}`, `POST /setup/{id}`: the family's setup. Saving replaces the family's notes and makes the companion introduce itself on the next call
- `GET /inspect/{id}`: Valkey keys and silence timer, recent turns, Postgres count and recent facts, the live event feed
- `POST /alerts/{id}/{alert_id}/resolve`: mark handled

## Database
- `patients`: name, timezone, `profile` (the diagnosis, always in the prompt, never a memory)
- `memories`: fact, category, embedding, `source` (`person` or `family`). Family notes are background only, never treated as something said or done today
- `alerts`: kind, severity, the words that caused it, handled or not

## Alerts
| Kind | Severity | When |
|---|---|---|
| family_notification_request | high | asked for the family to be told |
| distress | high | clearly frightened or in pain |
| missed_medication | high | says a dose was skipped |
| confusion | medium | clearly disoriented |
| no_response | medium | a check-in call was not answered |
| inactivity | normal | silent past the timer |

Portal banner: red if any high alert is open, yellow if a check-in is pending or a recent alert is open, green otherwise.

## Safety rules in the code, not just the prompt
- It confirms a dose only if you told it today. Otherwise it asks. A family-entered medicine time means a dose is due, never taken.
- It never asks you to remember or think back.
- It cannot call anyone. It leaves a note on the portal, and only after you agree.
- An unrequested promise to notify is replaced with a question.
- Silence ("...") never reaches the model and never produces alarming speech.

## Known limits
- "Notify family" only writes to the portal. No push, SMS, or email yet.
- The tunnel URL changes each restart, and the agent must be updated.
- No sensors: "silence" means not talking to the companion.
- Alerts and facts come from model judgment, so expect occasional false alarms or misses.
- One patient (id 1). Patient 99 is a test patient. Never test on patient 1 while a person is using it.
- ElevenLabs free tier credits ran out on 2026-10-21. Needs sponsor credits or an upgrade.
- Every key passed through chat during the build. Rotate them after the hackathon.

## Production (24/7)
- Backend: Modal app `elder-companion` (`backend/modal_app.py`), one always-on container in the EU, next to the Aiven databases in Frankfurt. Secrets live in the Modal secret `elder-companion`.
- Frontend: Vercel project `elder-companion`. Settings on Vercel: `ACCESS_CODE`, `AGENT_SHARED_SECRET`, `BACKEND_URL`. The `/api` function adds the secret server-side.
- The ElevenLabs agent's custom LLM URL is the Modal address plus `/v1`.
- Postgres goes through one shared pool (`backend/db.py`). A fresh connection to Aiven cost about a second, and a reply used to open four.
- Do not run the local backend at the same time as Modal: both would listen for silence.

## Mac app (menu bar)
`desktop/` is an Electron app that holds the companion in a small floating window. It loads the live site, so site updates reach it without reinstalling.
- Menu bar icon, no Dock icon. A dot beside the icon shows only while the microphone is open.
- Global shortcut Cmd+Shift+Space from any app: brings up the window without taking keyboard focus, then starts the call or switches the mic on and off.
- When the companion calls after a silence, the window comes up by itself.
- Starts at login the first time (switch in the menu: right-click the icon).
- Build and install: `cd desktop && npm install && npm run build`, then `codesign --force --deep --sign - "dist/mac-arm64/Memory Lane.app"` and copy it to `~/Applications`. Not notarized, so it only runs on the Mac that built it.

## Run it locally
```
backend:   cd backend && ../.venv/bin/uvicorn main:app --port 8000
frontend:  cd frontend && npm run dev            # port 4340
tunnel:    cloudflared tunnel --url http://localhost:8000
agent:     cd backend && ../.venv/bin/python create_agent.py <tunnel-url>   # or update the existing agent
```
Settings live in `.env` (see `.env.example`). `INACTIVITY_SECONDS=30` for demos, `14400` for real use.
Demo script: `DEMO.md`. Conversation transcripts: `transcripts/`.
