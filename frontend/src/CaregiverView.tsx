import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Memory = { content: string; category: string; at: string };
type Alert = { id: number; kind: string; severity: string; detail: string; resolved: boolean; at: string };
type Status = { level: "green" | "amber" | "red"; title: string; note: string; kind: string | null };
type Data = { patient: string; status: Status; memories: Memory[]; alerts: Alert[] };

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
            <span className="text-base font-medium text-neutral-600 truncate">{data?.patient ?? ""}</span>
          </span>
        </header>

        {offline && <p className="mt-3 text-base font-medium text-neutral-700">Cannot reach the server. Retrying.</p>}

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
        </div>
      </div>
    </div>
  );
}
