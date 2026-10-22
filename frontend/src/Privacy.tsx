import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Consent = { by: string; basis: string; at: string } | null;
type Info = { patient: string; consent: Consent; paused: boolean };

// ?patient=99 points the page at the test patient, same as the family portal
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

const input = "w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-lg text-neutral-900";
const BASIS: Record<string, string> = {
  person_agreed: "They agreed to this",
  legal_authority: "Recorded by someone with legal authority to act for them",
};
const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-neutral-300 bg-white p-4">
      <h2 className="text-lg font-bold">{title}</h2>
      <div className="mt-2 space-y-3 text-base text-neutral-700">{children}</div>
    </section>
  );
}

export default function Privacy() {
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState(false);
  const [by, setBy] = useState("");
  const [basis, setBasis] = useState("person_agreed");
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      api(`/dashboard/${PID}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((d: Info) => {
          setInfo(d);
          setError(false);
        })
        .catch(() => setError(true)),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  const post = async (path: string, body: unknown) => {
    setBusy(true);
    setNote("");
    try {
      const r = await api(`/family/${PID}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(String(r.status));
      await load();
      return await r.json();
    } catch {
      setNote("That did not work. Try again.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const name = info?.patient ?? "them";

  return (
    <div className="min-h-dvh bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-2xl px-4 py-5 pb-12">
        <header className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-bold">Privacy and data</h1>
          <a href="/caregiver" className="text-base font-medium text-neutral-600 underline underline-offset-4">
            Back to portal
          </a>
        </header>
        {error && !info && <p className="mt-4 text-base font-medium">Cannot reach the server.</p>}

        {info && (
          <div className="mt-4 space-y-4">
            <Card title="What is stored">
              <p>
                What {name} says to the companion, short notes taken from it, alerts, and the setup you entered. It is stored in a
                database hosted by Aiven in Frankfurt. Nothing is sold.
              </p>
              <p>
                To work, the words are processed by other services: ElevenLabs for speech, Anthropic for the replies, and OpenAI for
                searching notes. ElevenLabs also keeps its own call transcripts.
              </p>
              <p>The companion never gives medical advice, and it does not diagnose. The private note you wrote is never repeated to them.</p>
            </Card>

            <Card title="Consent">
              {info.consent ? (
                <p className="rounded-lg bg-green-100 px-3 py-2 font-medium text-neutral-900">
                  Recorded by {info.consent.by}. {BASIS[info.consent.basis] ?? info.consent.basis}. {when(info.consent.at)}.
                </p>
              ) : (
                <p className="rounded-lg bg-yellow-100 px-3 py-2 font-medium text-neutral-900">Not recorded yet.</p>
              )}
              <p>
                Confirm that {name} knows about the companion and agrees, or that you have the legal authority to set it up for them.
              </p>
              <label className="block font-semibold">
                Your name
                <input className={`${input} mt-1`} value={by} maxLength={60} onChange={(e) => setBy(e.target.value)} />
              </label>
              <fieldset className="space-y-2">
                {Object.entries(BASIS).map(([value, label]) => (
                  <label key={value} className="flex min-h-11 items-center gap-3 font-medium">
                    <input type="radio" name="basis" checked={basis === value} onChange={() => setBasis(value)} className="h-5 w-5" />
                    {label}
                  </label>
                ))}
              </fieldset>
              <button
                onClick={() => post("consent", { by: by.trim(), basis })}
                disabled={busy || !by.trim()}
                className="min-h-11 rounded-lg bg-neutral-900 px-5 text-base font-semibold text-white disabled:opacity-40"
              >
                {info.consent ? "Record again" : "Record consent"}
              </button>
            </Card>

            <Card title="Pause monitoring">
              <p>
                While paused, nothing is saved, no alerts are raised, and the companion starts no check-in calls. {name} can still talk to
                it, and it will say it cannot pass anything on.
              </p>
              <p className="font-semibold text-neutral-900">{info.paused ? "Monitoring is paused." : "Monitoring is on."}</p>
              <button
                onClick={() => post("pause", { paused: !info.paused })}
                disabled={busy}
                className="min-h-11 rounded-lg border border-neutral-900 px-5 text-base font-semibold disabled:opacity-40"
              >
                {info.paused ? "Resume monitoring" : "Pause monitoring"}
              </button>
            </Card>

            <Card title="Delete what was recorded">
              <p>
                This deletes what the companion learned from {name}&rsquo;s conversations, every alert, and every message. It cannot be
                undone. The setup you entered stays. Call transcripts kept by ElevenLabs are not deleted here: delete those in the
                ElevenLabs account.
              </p>
              <label className="block font-semibold">
                Type DELETE to confirm
                <input className={`${input} mt-1`} value={typed} onChange={(e) => setTyped(e.target.value)} />
              </label>
              <button
                onClick={async () => {
                  const out = await post("erase", { confirm: typed });
                  if (out) {
                    setTyped("");
                    setNote(`Deleted ${out.erased.memories} notes, ${out.erased.alerts} alerts and ${out.erased.messages} messages.`);
                  }
                }}
                disabled={busy || typed !== "DELETE"}
                className="min-h-11 rounded-lg bg-red-700 px-5 text-base font-semibold text-white disabled:opacity-40"
              >
                Delete everything recorded
              </button>
            </Card>

            <p role="status" className="min-h-6 text-base font-medium">
              {note}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
