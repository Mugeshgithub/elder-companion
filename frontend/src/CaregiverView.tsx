import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Memory = { content: string; category: string; at: string };
type Alert = { id: number; kind: string; severity: string; detail: string; resolved: boolean; at: string };
type Status = { level: "green" | "amber" | "red"; title: string; note: string; kind: string | null };
type Msg = { id: number; from_name: string; text: string; at: string; delivered_at: string | null };
type Consent = { by: string; basis: string; at: string } | null;
type Data = {
  patient: string; status: Status; memories: Memory[]; alerts: Alert[];
  consent: Consent; paused: boolean; messages: Msg[];
};
type Summary = { summary: string; notes: number; alerts: number };

const LABEL: Record<string, string> = {
  family_notification_request: "Asked for their family to be told",
  distress: "Seemed distressed",
  missed_medication: "Medication may have been missed",
  confusion: "Seemed confused",
  inactivity: "Quiet for a while, check-in started",
  no_response: "Check-in call was not answered",
};

const BANNER = {
  green: { box: "bg-green-700 text-white", tag: "ALL CLEAR" },
  amber: { box: "bg-yellow-300 text-neutral-900", tag: "CHECK-IN" },
  red: { box: "bg-red-600 text-white", tag: "ACT NOW" },
} as const;

const SEVERITY_EDGE: Record<string, string> = {
  high: "border-l-red-600",
  medium: "border-l-yellow-400",
  normal: "border-l-neutral-400",
};

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// ?patient=99 lets the page be pointed at the test patient without touching real data
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

export default function CaregiverView() {
  const [data, setData] = useState<Data | null>(null);
  const [offline, setOffline] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [from, setFrom] = useState(() => {
    try {
      return localStorage.getItem("ec-from") ?? "";
    } catch {
      return "";
    }
  });
  const [text, setText] = useState("");
  const [sendState, setSendState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const load = useCallback(
    () =>
      api(`/dashboard/${PID}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((d: Data) => { setData(d); setOffline(false); })
        .catch(() => setOffline(true)),
    [],
  );

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const get = () =>
      api(`/family/${PID}/summary`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then(setSummary)
        .catch(() => {});
    get();
    const t = setInterval(get, 120000);
    return () => clearInterval(t);
  }, []);

  const send = async () => {
    setSendState("sending");
    try {
      const r = await api(`/family/${PID}/message`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ from_name: from.trim(), text: text.trim() }),
      });
      if (!r.ok) throw new Error(String(r.status));
      try {
        localStorage.setItem("ec-from", from.trim());
      } catch {
        /* private window: the name is just typed again */
      }
      setText("");
      setSendState("sent");
      load();
    } catch {
      setSendState("error");
    }
  };

  const handle = (id: number) =>
    api(`/alerts/${PID}/${id}/resolve`, { method: "POST" }).then(load);

  const banner = data ? BANNER[data.status.level] : null;
  const open = data?.alerts.filter((a) => !a.resolved) ?? [];
  const done = data?.alerts.filter((a) => a.resolved) ?? [];

  return (
    <div className="min-h-dvh bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-5xl px-4 py-5">
        <header className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-bold">Family portal</h1>
          <span className="flex min-w-0 items-baseline gap-4">
            <a href="/setup" className="shrink-0 text-base font-medium text-neutral-600 underline underline-offset-4">Set up</a>
            <a href="/documents" className="shrink-0 text-base font-medium text-neutral-600 underline underline-offset-4">Documents</a>
            <a href="/privacy" className="shrink-0 text-base font-medium text-neutral-600 underline underline-offset-4">Privacy</a>
            <span className="text-base font-medium text-neutral-600 truncate">{data?.patient ?? ""}</span>
          </span>
        </header>

        {offline && <p className="mt-3 text-base font-medium text-neutral-700">Cannot reach the server. Retrying.</p>}

        {data?.paused && (
          <p className="mt-4 rounded-xl bg-neutral-800 px-4 py-3 text-base font-medium text-white">
            Monitoring is paused. Nothing is being saved, and there are no alerts or check-in calls.{" "}
            <a href="/privacy" className="underline underline-offset-4">Resume in Privacy</a>
          </p>
        )}
        {data && !data.consent && (
          <p className="mt-4 rounded-xl border border-yellow-500 bg-yellow-100 px-4 py-3 text-base font-medium">
            Consent has not been recorded yet.{" "}
            <a href="/privacy" className="underline underline-offset-4">Record it in Privacy</a>
          </p>
        )}

        {data && banner && (
          <section aria-live="polite" className={`mt-4 rounded-2xl px-5 py-6 ${banner.box}`}>
            <p className="text-sm font-bold tracking-widest">{banner.tag}</p>
            <p className="mt-1 text-3xl sm:text-4xl font-extrabold leading-tight">{data.status.title}</p>
            <p className="mt-1 text-lg">
              {data.status.kind ? LABEL[data.status.kind] ?? data.status.note : data.status.note}
            </p>
          </section>
        )}

        <div className="mt-4 grid gap-4 md:grid-cols-2 items-start">
          <section className="rounded-2xl border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-bold uppercase tracking-wide text-neutral-600">Active alerts</h2>
            <ul className="mt-3 space-y-3">
              {open.length === 0 && <li className="text-base text-neutral-600">No open alerts.</li>}
              {open.map((a) => (
                <li key={a.id} className={`rounded-lg border border-neutral-300 border-l-8 ${SEVERITY_EDGE[a.severity] ?? SEVERITY_EDGE.normal} p-3`}>
                  <p className="text-sm font-semibold text-neutral-600">{clock(a.at)}</p>
                  <p className="text-lg font-bold leading-snug">{LABEL[a.kind] ?? a.kind}</p>
                  {a.detail && <p className="mt-1 text-base text-neutral-800 break-words">{a.detail}</p>}
                  <button
                    onClick={() => handle(a.id)}
                    className="mt-3 min-h-11 rounded-lg bg-neutral-900 px-4 text-base font-semibold text-white"
                  >
                    Mark handled
                  </button>
                </li>
              ))}
              {done.map((a) => (
                <li key={a.id} className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-neutral-500">
                  <p className="text-sm">{clock(a.at)}, handled</p>
                  <p className="text-base font-medium">{LABEL[a.kind] ?? a.kind}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-2xl border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-bold uppercase tracking-wide text-neutral-600">Today in short</h2>
            <p className="mt-3 text-lg leading-snug">{summary ? summary.summary : "Loading."}</p>
            {summary && (
              <p className="mt-2 text-sm text-neutral-600">
                Based on {summary.notes} notes and {summary.alerts} alerts from today. It only reflects what was said to the companion.
              </p>
            )}
          </section>

          <section className="rounded-2xl border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-bold uppercase tracking-wide text-neutral-600">Today</h2>
            <ul className="mt-3 space-y-3">
              {data && data.memories.length === 0 && <li className="text-base text-neutral-600">Nothing logged yet today.</li>}
              {data?.memories.map((m, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-16 shrink-0 text-base font-semibold tabular-nums text-neutral-600">{clock(m.at)}</span>
                  <span className="text-lg leading-snug">{m.content}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-2xl border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-bold uppercase tracking-wide text-neutral-600">Message for {data?.patient ?? "them"}</h2>
            <p className="mt-1 text-base text-neutral-600">The companion says it as soon as it is open, or at their next call.</p>
            <label className="mt-3 block text-base font-semibold">
              From
              <input
                className="mt-1 w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-lg font-normal"
                value={from}
                maxLength={40}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="mt-3 block text-base font-semibold">
              Message
              <textarea
                rows={3}
                maxLength={300}
                placeholder="I will visit at four this afternoon."
                className="mt-1 w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-lg font-normal"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  if (sendState !== "idle") setSendState("idle");
                }}
              />
            </label>
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={send}
                disabled={sendState === "sending" || !from.trim() || !text.trim()}
                className="min-h-11 rounded-lg bg-neutral-900 px-5 text-base font-semibold text-white disabled:opacity-40"
              >
                Send
              </button>
              <p role="status" className="text-base font-medium">
                {sendState === "sent" && "Saved. It will be said at the next call."}
                {sendState === "error" && "Could not send. Try again."}
              </p>
            </div>
            <ul className="mt-4 space-y-2">
              {(data?.messages ?? []).slice(0, 3).map((m) => (
                <li key={m.id} className="rounded-lg border border-neutral-200 bg-neutral-50 p-3">
                  <p className="text-sm font-semibold text-neutral-600">
                    {m.from_name}, {clock(m.at)}, {m.delivered_at ? "said to them" : "waiting for the next call"}
                  </p>
                  <p className="text-base break-words">{m.text}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
