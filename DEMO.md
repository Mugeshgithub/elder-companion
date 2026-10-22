# Demo script

Three features, about three minutes, with a safety net so nothing depends on the microphone.

## What you are showing
1. **A memory you can watch** (Aiven): a fact is saved, then found by meaning.
2. **Medical documents with sources**: the answer names the clinic letter, and the model never advises.
3. **The family hears, and can reply**: an alert on a phone, and a message the companion says aloud.

## Before you go on
- Open the live demo page (`/demo`), the family portal (`/caregiver`) in a second tab, and Telegram on your phone.
- Upload the sample prescription on `/documents` and leave it unapproved. Approving it is part of the demo. Make your own with `python samples/make_samples.py --name YourName`.
- Start from a clean profile: portal green, no open alerts, no pending call.
- Check your phone is connected under Privacy, Phone alerts, and that the ElevenLabs credits are available.
- **The silence timer is 30 seconds in demo mode.** If you pause, the companion will call you. For real use set `INACTIVITY_SECONDS` to 14400.
- **Do not redeploy anything in the hour before.** A server restart can wait minutes for capacity.
- Do one dry run of any voice step. The typing box on `/demo` uses the same brain, so if voice misbehaves, type instead.

## The three moments

**1. It remembers (the data story)**
- Type: `I just put my wallet on the kitchen table.`
- In the live feed on the right, watch it saved to Postgres as a vector.
- Type: `Where did I leave my wallet?` The feed shows the pgvector search and its similarity score.
- Say: "It found it by meaning, and the data is on Aiven."

**2. It shows where it learned it**
- Open `/documents`, press Review on the prescription, read two cards with their exact quote and page, press **Approve all**.
- Type: `What medicine do I take in the evening?` The answer names the clinic letter.
- Type: `Should I take double tonight?` A fixed reply points to the doctor or pharmacist.
- Say: "Every medical word comes from a document the family approved. It never advises, and that rule is in our code."

**3. The family hears**
- Type: `I'm very frightened and I don't know where I am.`
- About 25 seconds later (the wait that merges bursts) the Telegram alert arrives on your phone and the portal turns red. Show the phone.
- Press **Mark handled** on the portal. A second message tells the others.
- Optional: type a message to the bot from your phone. The companion reaches out and says it.

## Extras, if there is time
- `Where is my passport?` It says it has nothing written down and does not guess.
- Set a medicine time two minutes ahead in Setup, then watch the reminder ring on its own.

## Do not ask
Anything about maps, location or setting reminders by voice. Those are limited or not built, and the honest answer flattens the demo.

## Words to avoid
"Compliant", "certified", "diagnose", "treat", "cures", "clinically proven", "safe for patients". Say "built with EU rules in mind, not certified".

## Things that are not what they seem
- It cannot phone anyone. Notify writes to the portal and Telegram.
- The documents are fictional.
- Hold-to-talk keeps the microphone off until the orb or the space bar is held.
- Telegram messages carry no health words unless the owner turns that on.
