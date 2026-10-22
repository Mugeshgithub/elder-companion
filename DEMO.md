# Rehearsal script

## Before you start
- **ElevenLabs credits**: the account was on the free tier with all 10,000 credits used on 2026-10-21 (resets 21 Nov). Redeem the sponsor credits or upgrade before any voice call, or calls fail instantly.
- Close the patient tab (Tab A) when you are not rehearsing. It starts calls by itself after silence, and each call costs credits.
- Tunnel terminal is running (`cloudflared tunnel --url http://localhost:8000`). If you restarted it, give Claude the new URL.
- Tab A, the patient screen: http://localhost:4340/
- Tab B, the family portal: http://localhost:4340/caregiver (should be green)
- Silence timer is 30 seconds for the demo (`INACTIVITY_SECONDS` in `.env`; use 14400 for real use)

## Beat 1: it learns (about 1 minute)
1. Tab A: touch the screen once. The agent greets you.
2. Say: "I just put my wallet on the kitchen table."
3. Say: "I just took my blue pill."
4. Touch the screen to end the call. Wait 10 seconds (it learns after you stop talking).
5. Tab B, "Today": two facts appear.

## Beat 2: it remembers (about 1 minute)
1. Touch the screen to start a new call.
2. Ask: "Where did I put my wallet?" It should say the kitchen table.
3. Ask: "Did I take my pill today?" It should confirm, because you told it.
4. Ask something it can't know: "Where is my passport?" It should say it has nothing written down, and not guess.

## Beat 3: it reaches out (about 1 minute)
1. Touch the screen to end the call. Then do nothing.
2. After about 30 seconds Tab B turns yellow, "Check-in pending".
3. A few seconds later the screen starts the call by itself and the agent speaks first.

## Beat 4: it tells the family (about 1 minute)
1. In that call, say: "I can't find my key and I'm worried."
2. The agent offers to leave a note for the family. Say: "Yes please."
3. Tab B turns red within about 5 seconds, with your exact words in the alert.
4. Click "Mark handled". Tab B turns green.

## Things not to expect
- It cannot phone or message anyone. "Notify" puts a note on the family portal.
- It will not give medical advice.
- Pauses longer than 30 seconds, even in a call, can raise a silence alert.
- If nobody answers a check-in, it hangs up after about a minute and puts one 'Check-in call was not answered' alert on the portal. It does not keep calling.
- Say 'good night' and it stays quiet for 8 hours (no calls, no silence alerts). Touching the screen wakes it.
- After an auto-call ends, it will not call again for 2 minutes.
