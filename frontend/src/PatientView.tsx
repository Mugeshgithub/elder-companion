import { useEffect, useRef, useState } from "react";
import { useConversationControls, useConversationMode, useConversationStatus } from "@elevenlabs/react";
import { api } from "./api";
import { AGENT_ID, CHECKIN_COOLDOWN_MS, PATIENT_ID } from "./config";

function greeting(d: Date) {
  const h = d.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function PatientView() {
  const { startSession, endSession, getInputVolume, getOutputVolume } = useConversationControls();
  const { status } = useConversationStatus();
  const { isSpeaking } = useConversationMode();

  const [now, setNow] = useState(new Date());
  const [name, setName] = useState("");
  const [armed, setArmed] = useState(false); // browsers need one touch before audio and mic work
  const lastEnded = useRef(0);
  const wasConnected = useRef(false);
  const swell = useRef<HTMLDivElement>(null);

  const connected = status === "connected";
  const connecting = status === "connecting";

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000 * 15);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    api(`/dashboard/${PATIENT_ID}`).then((r) => r.json()).then((d) => setName(d.patient ?? "")).catch(() => {});
  }, []);

  useEffect(() => {
    if (wasConnected.current && !connected && !connecting) lastEnded.current = Date.now();
    wasConnected.current = connected;
  }, [connected, connecting]);

  // The orb follows the live voice: yours while you talk, the companion's while it talks.
  // It writes a CSS variable straight to the element, so it never re-renders React 60 times a second.
  useEffect(() => {
    let raf = 0;
    let level = 0;
    const tick = () => {
      const target = connected ? (isSpeaking ? getOutputVolume() : getInputVolume()) : 0;
      level += (target - level) * 0.15;
      swell.current?.style.setProperty("--level", level.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [connected, isSpeaking, getInputVolume, getOutputVolume]);

  const starting = useRef(false);
  const begin = async (proactive = false) => {
    if (starting.current) return;
    starting.current = true;
    // only a person starting the call counts as activity; an unanswered check-in must not re-arm the timer
    if (!proactive) api(`/activity/${PATIENT_ID}`, { method: "POST" }).catch(() => {});
    let line = "";
    try {
      line = (await (await api(`/opener/${PATIENT_ID}?proactive=${proactive}`)).json()).opener ?? "";
    } catch {
      /* fall back to the plain greeting below */
    }
    startSession({
      agentId: AGENT_ID,
      connectionType: "webrtc",
      dynamicVariables: { opener: line || `Hi ${name || "there"}, how are you feeling today?` },
    });
    starting.current = false;
  };

  // Proactive check-in: the backend raises a flag when the person has been quiet too long.
  useEffect(() => {
    if (!armed) return;
    const t = setInterval(async () => {
      if (connected || connecting || Date.now() - lastEnded.current < CHECKIN_COOLDOWN_MS) return;
      try {
        const { pending } = await (await api(`/checkin/${PATIENT_ID}`)).json();
        if (pending) begin(true);
      } catch {
        /* backend briefly unreachable, try again next tick */
      }
    }, 3000);
    return () => clearInterval(t);
  });

  const onTouch = () => {
    if (!armed) setArmed(true);
    if (connected || connecting) endSession();
    else begin();
  };

  const label = connecting
    ? "One moment"
    : connected
      ? isSpeaking
        ? "Speaking"
        : "Listening"
      : armed
        ? "Here with you"
        : "Click to begin";

  const orb = connecting
    ? "from-sky-200 via-sky-400/70 to-indigo-500/10 shadow-[0_0_120px_30px_rgba(125,211,252,0.3)] orb-connecting"
    : connected && isSpeaking
      ? "from-amber-200 via-amber-400/70 to-orange-500/10 shadow-[0_0_140px_40px_rgba(251,191,36,0.35)] orb-speaking"
      : "from-emerald-200 via-emerald-400/70 to-teal-500/10 shadow-[0_0_140px_40px_rgba(52,211,153,0.3)]";

  return (
    <main
      onClick={onTouch}
      className="min-h-dvh select-none cursor-pointer flex flex-col text-[#f5f8fb] bg-gradient-to-b from-[#0a1d33] via-[#0b2a3f] to-[#0b3a35] px-4 py-4"
    >
      <header className="flex items-center justify-between text-lg font-medium">
        <span
          aria-hidden
          className={`h-3 w-3 rounded-full ${connected ? "bg-emerald-300" : "bg-emerald-300/40"}`}
        />
        <time>{now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time>
      </header>

      <section className="flex-1 flex flex-col items-center justify-center text-center gap-6">
        <h1 className="font-semibold leading-tight">
          <span className="block text-[clamp(1.4rem,6vw,3.5rem)]">{greeting(now)},</span>
          <span className="block text-[clamp(2rem,10vw,6rem)] mt-1 min-h-[1.2em]">{name}</span>
        </h1>

        {/* fixed box, so the swell grows the glow without pushing the greeting or the label */}
        <div ref={swell} className="orb-swell grid place-items-center h-[min(55vw,38dvh,20rem)] w-[min(55vw,38dvh,20rem)]">
          <div aria-hidden className={`orb rounded-full bg-radial ${orb} h-full w-full`} />
        </div>

        <p role="status" className="text-[clamp(1.1rem,5vw,2rem)] font-medium">
          {label}
        </p>
      </section>
    </main>
  );
}
