# Memory Lane

**A voice companion for people with Alzheimer's. It remembers for them, speaks first when they go quiet, and keeps their family in the loop.**

> A second memory you can talk to.

Memory Lane is a working prototype built for a hackathon on a data theme. It is not a medical device, it does not diagnose, and it never gives medical advice. One real person has used it. Read [What is real and what is not](#what-is-real-and-what-is-not) before relying on anything here.

---

## Contents
1. [The problem](#the-problem)
2. [What it does](#what-it-does)
3. [What is real and what is not](#what-is-real-and-what-is-not)
4. [How it works](#how-it-works)
5. [Safety and privacy by design](#safety-and-privacy-by-design)
6. [Try it](#try-it)
7. [Run it yourself](#run-it-yourself)
8. [Code map](#code-map)
9. [API at a glance](#api-at-a-glance)
10. [Known limits](#known-limits)
11. [The future](#the-future)
12. [Notes for the next person](#notes-for-the-next-person)

---

## The problem

In mild Alzheimer's, the person loses small daily memories (where the keys are, whether the pill was taken), which brings anxiety and risk. Their family cannot know how they are doing between visits.

- About 55 million people live with dementia worldwide, and family and friends give about 5 hours of unpaid care a day on average (WHO, 2021 and 2019 reports).
- Common, serious problems include wandering (the Alzheimer's Association figure, repeated in the press, is about six in ten people at some point), medicines at home, and strain and loneliness for carers. One small study of 88 carers found 40% had difficulty managing medication and 74% reported high strain ([Carer Strain and Carer Coping with Medications for People with Dementia](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7551266/)).
- Most assistants wait to be asked. A person who forgets cannot ask for the thing they forgot.

**What this project tries to solve, narrowly:** daily memory support and family peace of mind in the early stage. It does not solve wandering, physical safety, late-stage care, or any treatment decision.

## What it does

| | |
|---|---|
| **It remembers** | Facts from conversation are saved as they are said (where things are, whether a pill was taken) and found again by meaning. |
| **It never guesses** | If nothing is written down, it says so. No invented places, plans or doses. |
| **It speaks first** | After a quiet spell it starts the call itself. At a medicine time it rings with a reminder. |
| **Medical documents, with sources** | A family uploads a clinic letter or prescription. A forced tool call turns it into findings, every finding must quote the document, code checks the quote on the page, and the family approves each one. The companion then answers with the source named. |
| **It knows its limits** | It tells people it is an AI. Dosing questions get a fixed reply that points to the doctor or pharmacist. A diagnosis or a test score can be kept as a family record, and the companion never says it. |
| **The family stays in the loop** | A portal with a red, yellow or green status, alerts, and a plain daily summary. Important alerts arrive as Telegram messages, paced so phones are not flooded. A family member can type to the bot and the companion says it aloud. |
| **The family stays in control** | Recorded consent, pause monitoring, download a copy, delete, automatic expiry, individual family codes, and an activity log. |
| **Optional location, limited** | A page open on a phone shares its position. Leaving a safe area for five minutes alerts the family. It cannot track in the background. |

## What is real and what is not

**Working and tested**
- Voice conversations through an ElevenLabs agent whose replies come from our own server.
- Short-term memory (Aiven for Valkey) and long-term memory searched by meaning (Aiven for PostgreSQL with pgvector).
- The silence trigger, driven by a Valkey key-expiry event, and the medicine-reminder trigger on the same mechanism (a reminder set two minutes ahead fired on its own timer).
- Medical documents: extraction, quote verification, family approval, cited answers, the fixed dosing reply.
- Family portal, setup, consent, pause, export, delete, retention, roles, audit log.
- Telegram alerts with pacing, the two-way message flow, and the evening digest.
- An installable Mac menu bar app (runs on the Mac that built it).

**Working but limited**
- Location sharing works only while a page is open on a phone.
- Hold-to-talk was built to keep room noise out of the transcript. It has not been proven in a long live session, and hands-free is probably the better default for real users.
- Reminders and proactive calls need the companion app to be open on a device.

**Not built**
- Scanned documents (text PDFs only), accounts for many families, a native phone app, SMS or email alerts, a "companion is offline" alert, and anything clinical.

**Not done, and not code**
- A data protection impact assessment, processor agreements with every service used, and a legal review. See [Safety and privacy](#safety-and-privacy-by-design).

## How it works

```
 Person speaks ──► ElevenLabs (voice, interruptions)
                        │  custom LLM: every reply comes from our server
                        ▼
              FastAPI server (Modal, EU)
   ┌────────────────────┼─────────────────────┐
   ▼                    ▼                     ▼
 Aiven Valkey       Aiven PostgreSQL       Claude writes the reply
 working memory     + pgvector             (OpenAI is the fallback)
 recent turns,      long-term memory,
 mood, timers       searched by meaning
   │                    ▲
   │ key expiry         │ 4 seconds after they stop:
   ▼                    │ Claude extracts facts and concerns,
 silence check-in,      │ and they are saved
 medicine reminder ─────┘
```

**Two memories, two jobs.**
- **Aiven for Valkey** holds what is happening now: recent turns, mood, a silence timer, and a timer per medicine time. When a timer's key expires, Valkey tells us, and that starts a call. Expiry is the trigger.
- **Aiven for PostgreSQL with pgvector** holds what lasts: every fact as a 1024-number vector, searched by meaning, so "where is my wallet" finds "wallet on the kitchen table". The same database holds alerts, documents, family messages, consent and the audit log.

**The reply path** (about 2 to 3 seconds for a typed reply): the server reads recent turns, today's confirmed facts and relevant memories in parallel, then Claude writes a short reply under rules enforced in code.

**The document path:** PDF text is extracted, Claude is forced to call a `record_findings` tool with a strict schema, each finding's quote is verified against the page, and nothing is spoken until a person approves it. Only medicines, appointments, instructions and contacts can reach the companion.

**Where things run**

| Part | Where |
|---|---|
| Databases | Aiven, Frankfurt |
| Backend | Modal, EU region, one always-on container |
| Website and proxy | Vercel (the proxy function runs in Frankfurt) |
| Voice | ElevenLabs |
| Replies and document reading | Anthropic (Claude), with OpenAI as a fallback and for embeddings |
| Phone alerts | Telegram |

## Safety and privacy by design

Rules that are enforced in code, not only written in a prompt:

- A dose is confirmed only if the person said so today. A time from the family means a dose is due, never taken. A reminder's follow-up says "no confirmation", never "missed".
- It never asks the person to remember or think back.
- It never says where something is unless that exact place is in its memory. It never states how someone is related to the person unless a memory says so.
- It cannot phone anyone, so it offers to leave a note and records it only after the person agrees.
- Dosing questions ("should I take double?") get a fixed reply pointing to the doctor or pharmacist.
- Silence markers never reach the model.
- Documents: a finding whose quote is not on the page cannot be approved. A diagnosis or a test score is never repeated by the companion.
- It tells people it is an AI.

Controls the family has: a consent record (the person agreed, or someone with legal authority recorded it), pause (nothing saved, no alerts, no check-in calls), a download of everything stored, deletion of what was recorded, automatic expiry (default one year), individual family codes with roles, and an activity log.

**Honest status under EU rules.** This is built with GDPR, the EU AI Act and medical-device boundaries in mind. It is **not certified, not audited, and not legal advice.** Still to do: a data protection impact assessment (GDPR Article 35), processor agreements with every service used (Aiven, ElevenLabs, Anthropic, OpenAI, Modal, Vercel, Telegram), a legal review (the basis for health data, capacity to consent, and whether France's health data hosting rule applies), and keeping the stated purpose to companionship and memory support so it is not treated as a medical device. The privacy page in the app lists exactly where data goes. ElevenLabs keeps its own call transcripts, which our delete cannot remove.

The sample medical documents in `samples/` are **fictional**: a made-up clinic, doctor and patient, watermarked on every page.

## Try it

- **Slides and live demo:** the deployed site's home page is the deck. "Open app" goes to `/demo`: the companion on the left, a live memory inspector on the right, and a box to type to the companion without a microphone.
- **The scripted demo** is in [DEMO.md](DEMO.md): three features in about three minutes.
- **Sample documents:** `python samples/make_samples.py --name YourName` writes a fictional clinic letter and prescription.

## Run it yourself

You need Python 3.13, Node, an Aiven account (PostgreSQL with pgvector, and Valkey with key-expiry events enabled by setting `valkey_notify_keyspace_events` to `Ex`), and keys for Anthropic, OpenAI (embeddings) and ElevenLabs. Telegram is optional.

```bash
# settings: copy the template and fill it in. Never commit .env.
cp .env.example .env

# backend
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
psql "$POSTGRES_URI" -f backend/schema.sql
cd backend && ../.venv/bin/uvicorn main:app --port 8000

# frontend (dev server on port 4340; set DEV_BACKEND=https://... to use a deployed backend)
cd frontend && npm install && npm run dev

# the voice agent, once: creates an ElevenLabs agent that calls your backend
cd backend && ../.venv/bin/python create_agent.py https://YOUR-BACKEND-URL
```

**Deploying**
- **Backend on Modal:** create a Modal secret named `elder-companion` from your `.env` (leave out the ElevenLabs key, the server does not need it), then `modal deploy backend/modal_app.py`. It runs one always-on container, because the silence and reminder listener lives inside it. **Do not run a local backend at the same time**, or both will react to every timer. A redeploy can wait minutes for capacity, so do not redeploy right before a demo.
- **Website on Vercel:** from `frontend/`, run `vercel deploy --prod`. Set three variables on the project: `BACKEND_URL`, `AGENT_SHARED_SECRET` and `ACCESS_CODE`. Use a long access code, not a short one.
- **Telegram (optional):** create a bot with BotFather, put `TELEGRAM_BOT_TOKEN` and a random `TELEGRAM_WEBHOOK_SECRET` in the Modal secret, then register the webhook with `setWebhook` and the same secret token. Revoke and replace the bot token when you are done.
- **Mac app (optional):** `cd desktop && npm install && npm run build`, then ad-hoc sign and copy it to `~/Applications`. It is not notarized, so it only runs on the Mac that built it. A global shortcut (Cmd+Shift+Space) starts a call from any app.

**Settings** (names only; see `.env.example`): `POSTGRES_URI`, `VALKEY_URI`, `ANTHROPIC_API_KEY`, `EMBEDDINGS_API_KEY`, `ELEVENLABS_API_KEY`, `AGENT_SHARED_SECRET`, `INACTIVITY_SECONDS` (30 for demos, 14400 for real use), `PATIENT_TZ`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PORTAL_URL`.

## Code map

**Backend** (`backend/`, FastAPI)

| File | What it does |
|---|---|
| `main.py` | The app, the OpenAI-compatible route ElevenLabs calls, the reply logic, startup and background loops |
| `prompt.py` | The companion's instructions and safety rules |
| `working_memory.py` | Valkey: recent turns, mood, timers, the event log for the inspector |
| `episodic_memory.py`, `memory.py`, `embeddings.py` | Postgres and pgvector: save and search memories, build the reply context |
| `learning.py` | After a pause, extracts facts and concerns from what was said |
| `intents.py` | "Tell my family" detection, good night, the promise guard, the dosing-question guard |
| `alerts.py`, `notify.py` | Alerts with severity and de-duplication, Telegram delivery with pacing, the digest, family messages by Telegram |
| `triggers.py`, `reminders.py` | The Valkey key-expiry listener, medicine reminders |
| `documents.py` | Medical documents: forced tool call, quote verification, approval |
| `family.py` | Messages, summary, consent, pause, erase, export, retention, roles, audit |
| `location.py` | Optional location sharing and the safe area |
| `opener.py`, `llm.py`, `db.py`, `textutil.py`, `config.py` | The first line of a call, Claude with an OpenAI fallback, the connection pool, helpers, settings |
| `schema.sql`, `modal_app.py`, `create_agent.py` | Tables, the Modal deployment, the voice agent setup |

**Frontend** (`frontend/`, React, Vite, Tailwind), plus the Vercel proxy in `frontend/api/proxy.ts`. The proxy adds the shared secret on the server, checks the access code and the role, and forwards only the allowed routes.

| Screen | Route |
|---|---|
| Slide deck | `/` |
| Live demo: companion, memory inspector, typing box | `/demo` |
| The companion alone (what the Mac app opens) | `/app` |
| Family portal | `/caregiver` |
| Family setup | `/setup` |
| Medical documents | `/documents` |
| Privacy and data | `/privacy` |
| Location sharing (for a phone) | `/where` |

**Other:** `desktop/` is the Mac menu bar app (Electron), `samples/` holds the fictional sample documents, `DEMO.md` is the demo script, and `BRIEF.md` is the original brief.

## API at a glance

All backend routes need the shared secret header. The website never exposes it: its proxy adds it.

| Group | Routes |
|---|---|
| Voice | `POST /v1/chat/completions` (what ElevenLabs calls), `POST /chat` (typed), `GET /opener/{id}`, `GET /checkin/{id}`, `POST /activity/{id}` |
| Portal | `GET /dashboard/{id}`, `GET /inspect/{id}`, `POST /alerts/{id}/{alert}/resolve`, `GET` and `POST /setup/{id}` |
| Family | `/family/{id}/message`, `/messages`, `/summary`, `/consent`, `/pause`, `/erase`, `/privacy`, `/retention`, `/export`, `/members` |
| Documents | `/family/{id}/documents` and its review, approve and delete routes |
| Phone alerts | `/family/{id}/notify` and its link, words, test and remove routes, and `POST /telegram/webhook` |
| Location | `/location/{id}`, `/location/{id}/home`, `/location/{id}/stop` |

## Known limits

- One real user so far. No clinical validation and no family pilot.
- Voice depends on a device being open. If the Mac sleeps or the page is closed, there is no spoken reply, no reminder call and no check-in call, and a plain "quiet for a while" notice does not buzz a phone.
- The silence timer is 30 seconds in demo mode. Real use needs hours.
- Location is foreground only. Documents must be text PDFs. Telegram messages are text only.
- Alerts and extracted facts come from model judgment, so a false alarm or a miss can happen. The model sometimes uses a pronoun for a named person despite a rule, and sometimes offers to leave a note when it does not need to.
- One shared owner code protects the deployed site until real accounts exist. Use a long one.
- Deleting data here cannot delete ElevenLabs's own call transcripts.
- One always-on container, with no uptime monitoring yet.

## The future

**Next, weeks**
- A **"companion is offline" alert**: the app sends a quiet signal each minute, and the family hears once if it stops. This closes the biggest honest gap.
- **Real accounts** and several families, replacing the shared owner code.
- **A native phone app** with background location, push notifications that can wake the companion, and hands-free voice. This is also the real answer to wandering.
- **Scanned documents** through Claude's PDF reading, and **"questions for the doctor"**, a cited list built from approved documents and recent notes.
- **More ways to reach the family:** SMS or email, and an escalation chain ("if nobody responds in 15 minutes, tell the next person").
- Reminder polish: snooze, per-medicine confirmation, and quiet hours.

**Then, months**
- **A pilot** with a few real families and a clinician or care-home partner, to learn whether people use it, whether it is safe, and what a person-day of voice really costs.
- **Compliance work:** the impact assessment, processor agreements, legal review, and a hosting check.
- A **signed and notarized** desktop app, uptime monitoring, French language support, and an accessibility review.
- **The family's own voice:** a voice note from a relative, played on the person's device. It needs recording consent and storage, so it comes after the legal review.

**Later**
- A version for **care homes and home-care providers**, where the family-alert and documentation side matters most.
- **Clinical partnership and evaluation.** If it ever needs to detect decline or influence treatment, that is a medical device under EU rules (CE marking and clinical evidence), and should only be done with a clinical partner leading it.

**Not planned:** diagnosing, advising on treatment, or claiming a clinical benefit.

## Notes for the next person

- Keys pasted into chats or terminals during the build should be **rotated** before anyone else uses this: the database URIs, the Anthropic, OpenAI and ElevenLabs keys, the Modal token, and the Telegram bot token (BotFather `/revoke`).
- Never test on the real patient (id 1) while someone may be using it. Patient 99 is the test patient. Clean it afterwards.
- Do not redeploy the backend right before a demo.
- Style: plain, short sentences. No lists in spoken replies. No invented facts.
