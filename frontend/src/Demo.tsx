import { useState, type FormEvent } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";
import Inspector from "./Inspector";

// ?patient=99 points the demo at the test patient, same as the other screens
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

// The same brain as the voice, reached by typing. It makes the demo independent of the microphone and the room,
// and the live data beneath it shows each message being saved and searched as it happens.
function TypeBox() {
  const [text, setText] = useState("");
  const [log, setLog] = useState<{ you: string; reply: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setFailed(false);
    setText("");
    try {
      const r = await api("/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ patient_id: PID, message }),
      });
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      setLog((l) => [{ you: message, reply: d.reply }, ...l].slice(0, 3));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={send} className="shrink-0 border-b border-white/10 p-3">
      <label htmlFor="type-to-companion" className="text-sm font-semibold text-white/70">
        Type to the companion. Same brain as the voice.
      </label>
      <div className="mt-2 flex gap-2">
        <input
          id="type-to-companion"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="I just put my wallet on the kitchen table."
          className="min-w-0 flex-1 rounded-lg bg-white/10 px-3 py-2 text-base text-white outline-none placeholder:text-white/40 focus:ring-2 focus:ring-emerald-300"
        />
        <button
          disabled={busy || !text.trim()}
          className="min-h-11 rounded-lg bg-emerald-400 px-5 text-base font-semibold text-neutral-900 disabled:opacity-40"
        >
          {busy ? "..." : "Send"}
        </button>
      </div>
      {failed && <p className="mt-2 text-sm font-medium text-amber-300">That did not go through. Try again.</p>}
      {log.length > 0 && (
        <ul className="mt-3 space-y-2">
          {log.map((m, i) => (
            <li key={i} className="text-base leading-snug">
              <p className="text-white/55">You: {m.you}</p>
              <p className="font-medium">Companion: {m.reply}</p>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}

// The companion on the left, running for real. The data it touches, live, on the right.
// The companion is an iframe so it keeps its own voice session and its own small-window layout.
export default function Demo() {
  return (
    <div className="flex h-dvh flex-col bg-[#071626] text-[#f5f8fb]">
      <header className="flex h-10 shrink-0 items-center justify-between px-4 text-sm">
        <span className="font-semibold text-white/70">Live demo</span>
        <span className="flex gap-5 text-white/60">
          <a href="/setup" className="underline-offset-4 hover:underline">Family setup</a>
          <a href="/" className="underline-offset-4 hover:underline">Back to slides</a>
        </span>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-3 pb-3 lg:flex-row">
        <iframe
          title="Companion"
          src="/app"
          allow="microphone; autoplay"
          className="h-[600px] w-full shrink-0 rounded-2xl border border-white/10 lg:h-full lg:w-[400px]"
        />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-white/10">
          <TypeBox />
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Inspector />
          </div>
        </div>
      </div>
    </div>
  );
}
