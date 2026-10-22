import { useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Turn = { role: string; text: string; ts: number };
type Hit = { content: string; category: string; score: number };
type Ev = { t: number; kind: string; text: string; hits?: Hit[]; category?: string; model?: string; near?: string; score?: number; alert?: string; severity?: string };
type Data = {
  working: {
    silence_ttl: number;
    silence_limit: number;
    dnd_ttl: number;
    checkin_pending: boolean;
    mood: string | null;
    turns: Turn[];
    keys: { key: string; ttl: number }[];
  };
  episodic: { total: number; recent: { content: string; category: string; at: string; source?: string }[] };
  events: Ev[];
};

// ?patient=99 points the inspector at the test patient, same as the family portal
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

const KIND: Record<string, { tag: string; tone: string }> = {
  recall: { tag: "SEARCH pgvector", tone: "bg-sky-400/20 text-sky-200" },
  reply: { tag: "REPLY", tone: "bg-white/10 text-white/80" },
  learned: { tag: "SAVED to Postgres", tone: "bg-emerald-400/20 text-emerald-200" },
  skipped: { tag: "SKIPPED duplicate", tone: "bg-white/10 text-white/60" },
  alert: { tag: "ALERT", tone: "bg-red-400/25 text-red-200" },
  trigger: { tag: "VALKEY TRIGGER", tone: "bg-amber-400/25 text-amber-200" },
  setup: { tag: "FAMILY SETUP", tone: "bg-sky-400/20 text-sky-200" },
  reminder: { tag: "MEDICINE REMINDER", tone: "bg-amber-400/25 text-amber-200" },
};

const clock = (secs: number) =>
  new Date(secs * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });

function ttlText(t: number) {
  if (t === -1) return "no expiry";
  if (t < 0) return "gone";
  if (t < 90) return `${t}s`;
  if (t < 5400) return `${Math.round(t / 60)}m`;
  return `${Math.round(t / 3600)}h`;
}

function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-sm text-white/55">{sub}</p>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Silence({ w }: { w: Data["working"] }) {
  const running = w.silence_ttl >= 0;
  const pct = running ? Math.max(0, Math.min(1, w.silence_ttl / w.silence_limit)) : 0;
  const m = Math.floor(Math.max(0, w.silence_ttl) / 60);
  const s = Math.max(0, w.silence_ttl) % 60;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-white/60">Silence timer</span>
        <span className="text-3xl font-semibold tabular-nums">{running ? `${m}:${String(s).padStart(2, "0")}` : "idle"}</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-emerald-400 transition-[width] duration-1000 ease-linear" style={{ width: `${pct * 100}%` }} />
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
        {w.checkin_pending && <span className="rounded-full bg-amber-400/25 px-2 py-1 text-amber-200">CHECK-IN PENDING</span>}
        {w.dnd_ttl > 0 && <span className="rounded-full bg-sky-400/20 px-2 py-1 text-sky-200">DO NOT DISTURB {ttlText(w.dnd_ttl)}</span>}
        {!running && <span className="rounded-full bg-white/10 px-2 py-1 text-white/60">NO ACTIVITY YET</span>}
      </div>
    </div>
  );
}

function Event({ e, fresh }: { e: Ev; fresh: boolean }) {
  const k = KIND[e.kind] ?? { tag: e.kind.toUpperCase(), tone: "bg-white/10 text-white/70" };
  return (
    <li className={`rounded-xl border border-white/10 p-3 ${fresh ? "flash" : ""}`}>
      <div className="flex items-center gap-2 text-xs">
        <span className="tabular-nums text-white/45">{clock(e.t)}</span>
        <span className={`rounded-full px-2 py-0.5 font-bold ${k.tone}`}>{k.tag}</span>
        {e.category && <span className="text-white/55">{e.category}</span>}
        {e.alert && <span className="text-white/55">{e.alert}</span>}
        {e.model && <span className="text-white/40">{e.model}</span>}
      </div>
      <p className="mt-1 text-base leading-snug break-words">{e.kind === "recall" ? `“${e.text}”` : e.text}</p>
      {e.kind === "recall" && (
        <ul className="mt-2 space-y-1">
          {(e.hits ?? []).length === 0 && <li className="text-sm text-white/50">No memories matched yet.</li>}
          {(e.hits ?? []).map((h, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="w-10 shrink-0 rounded bg-sky-400/15 text-center font-semibold tabular-nums text-sky-200">{h.score.toFixed(2)}</span>
              <span className="text-white/80">{h.content}</span>
            </li>
          ))}
        </ul>
      )}
      {e.kind === "skipped" && (
        <p className="mt-1 text-sm text-white/50">
          Matches “{e.near}” at {e.score?.toFixed(2)}
        </p>
      )}
    </li>
  );
}

export default function Inspector() {
  const [d, setD] = useState<Data | null>(null);
  const [offline, setOffline] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const load = () =>
      api(`/inspect/${PID}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((x: Data) => {
          setD(x);
          setOffline(false);
          setNow(Date.now());
        })
        .catch(() => setOffline(true));
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);

  const w = d?.working;
  return (
    <div className="h-full min-h-dvh bg-[#0a1d33] px-4 py-4 text-[#f5f8fb]">
      <header className="flex items-baseline justify-between gap-3">
        <h1 className="text-xl font-bold">Memory inspector</h1>
        <span className="flex items-center gap-2 text-sm text-white/60">
          <span className={`h-2.5 w-2.5 rounded-full ${offline ? "bg-red-400" : "bg-emerald-400"}`} />
          {offline ? "Cannot reach the server" : "Live"}
        </span>
      </header>

      {d && w && (
        <div className="mt-4 grid items-start gap-4 xl:grid-cols-2">
          <div className="space-y-4">
            <Card title="Working memory" sub="Aiven for Valkey. Fast, expires on its own.">
              <Silence w={w} />
              <div className="mt-4">
                <p className="text-sm font-semibold text-white/60">Keys</p>
                <ul className="mt-1 space-y-1 font-mono text-sm">
                  {w.keys.length === 0 && <li className="text-white/50">No keys yet.</li>}
                  {w.keys.map((k) => (
                    <li key={k.key} className="flex justify-between gap-3">
                      <span className="truncate">patient:{PID}:{k.key}</span>
                      <span className="shrink-0 text-white/55">{ttlText(k.ttl)}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-4">
                <p className="text-sm font-semibold text-white/60">Recent turns{w.mood ? `, mood: ${w.mood}` : ""}</p>
                <ul className="mt-1 space-y-1 text-sm">
                  {w.turns.length === 0 && <li className="text-white/50">Nothing said yet.</li>}
                  {w.turns.slice(-4).map((t, i) => (
                    <li key={i} className="break-words">
                      <span className="font-semibold text-white/60">{t.role === "user" ? "Said" : "Companion"}: </span>
                      {t.text}
                    </li>
                  ))}
                </ul>
              </div>
            </Card>

            <Card title="Long-term memory" sub="Aiven for PostgreSQL + pgvector. 1024-number vectors, HNSW cosine index.">
              <p className="text-3xl font-semibold tabular-nums">
                {d.episodic.total} <span className="text-base font-normal text-white/55">memories stored</span>
              </p>
              <ul className="mt-3 space-y-2">
                {d.episodic.recent.length === 0 && <li className="text-sm text-white/50">Nothing saved yet.</li>}
                {d.episodic.recent.map((m, i) => (
                  <li key={i} className={`rounded-lg border border-white/10 p-2 ${now - new Date(m.at).getTime() < 8000 ? "flash" : ""}`}>
                    <p className="text-xs text-white/50">
                      {new Date(m.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · {m.category}{m.source && m.source !== "person" ? ` · from ${m.source}` : ""}
                    </p>
                    <p className="text-base leading-snug">{m.content}</p>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card title="Live feed" sub="What the system just did, newest first.">
            <ul className="space-y-2">
              {d.events.length === 0 && <li className="text-sm text-white/50">Waiting for the first message.</li>}
              {d.events.map((e, i) => (
                <Event key={`${e.t}-${i}`} e={e} fresh={now / 1000 - e.t < 6} />
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
