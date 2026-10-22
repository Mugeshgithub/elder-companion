import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Consent = { by: string; basis: string; at: string } | null;
type Member = { id: number; name: string; created_at: string; last_seen: string | null };
type Entry = { actor: string; action: string; detail: string; at: string };
type Notify = { enabled: boolean; bot: string | null; include_words: boolean; targets: { id: number; name: string; created_at: string }[] };
type Info = {
  patient: string;
  consent: Consent;
  paused: boolean;
  retention_days: number | null;
  members: Member[];
  audit: Entry[];
};

// ?patient=99 points the page at the test patient, same as the family portal
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

const input = "w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-lg text-neutral-900";
const button = "min-h-11 rounded-lg px-5 text-base font-semibold disabled:opacity-40";
const BASIS: Record<string, string> = {
  person_agreed: "They agreed to this",
  legal_authority: "Recorded by someone with legal authority to act for them",
};
const KEEP: { value: string; label: string }[] = [
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "1 year" },
  { value: "forever", label: "Until you delete it" },
];
const ACTION: Record<string, string> = {
  message: "left a message",
  consent: "recorded consent",
  pause: "paused monitoring",
  resume: "resumed monitoring",
  erase: "deleted what was recorded",
  setup: "changed the setup",
  retention: "changed how long data is kept",
  export: "downloaded a copy of the data",
  member_added: "added a family member",
  notify_link: "made a Telegram link",
  notify_connected: "connected a phone for alerts",
  notify_words: "changed whether messages include their words",
  notify_test: "sent a test message",
  notify_removed: "removed a phone from alerts",
  member_removed: "removed a family member",
  alert_handled: "marked an alert as handled",
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
  const [role, setRole] = useState<"owner" | "member" | null>(null);
  const [error, setError] = useState(false);
  const [by, setBy] = useState("");
  const [basis, setBasis] = useState("person_agreed");
  const [typed, setTyped] = useState("");
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState<{ name: string; code: string } | null>(null);
  const [notify, setNotify] = useState<Notify | null>(null);
  const [phoneName, setPhoneName] = useState("");
  const [link, setLink] = useState<{ name: string; url: string } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      // the deployed site says who is signed in; a local dev screen has no such route and is the owner
      const who = await api("/whoami");
      const role = who.ok ? (await who.json()).role : "owner";
      setRole(role);
      if (role !== "owner") return;
      const r = await api(`/family/${PID}/privacy`);
      if (!r.ok) throw new Error(String(r.status));
      setInfo(await r.json());
      const n = await api(`/family/${PID}/notify`);
      if (n.ok) setNotify(await n.json());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);
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
      const out = await r.json();
      await load();
      return out;
    } catch {
      setNote("That did not work. Try again.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setBusy(true);
    setNote("");
    try {
      const r = await api(`/family/${PID}/export`);
      if (!r.ok) throw new Error(String(r.status));
      const link = document.createElement("a");
      link.href = URL.createObjectURL(await r.blob());
      link.download = `memory-lane-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      await load();
    } catch {
      setNote("Could not download. Try again.");
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

        {role === "member" && (
          <div className="mt-4">
            <Card title="Your access">
              <p>
                You can read the portal, mark alerts as handled, and leave messages. Only the owner can change privacy settings,
                download the data, or delete it.
              </p>
            </Card>
          </div>
        )}

        {info && role === "owner" && (
          <div className="mt-4 space-y-4">
            <Card title="What is stored">
              <p>
                What {name} says to the companion, short notes taken from it, alerts, messages, and the setup you entered. The database
                and our servers are in the EU. Nothing is sold.
              </p>
              <p>
                To work, the words are processed by other services: ElevenLabs for speech, Anthropic for the replies, OpenAI for
                searching notes, and Telegram for phone alerts. They are outside our control and may process data outside the EU. ElevenLabs also keeps its own call
                transcripts.
              </p>
              <p>The companion tells people it is an AI. It never gives medical advice, and it does not diagnose.</p>
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
                className={`${button} bg-neutral-900 text-white`}
              >
                {info.consent ? "Record again" : "Record consent"}
              </button>
            </Card>

            <Card title="How long to keep it">
              <p>What {name} says, the alerts, and the messages are deleted automatically after this long.</p>
              <select
                aria-label="How long to keep data"
                className={input}
                disabled={busy}
                value={info.retention_days ? String(info.retention_days) : "forever"}
                onChange={(e) => post("retention", { days: e.target.value === "forever" ? null : Number(e.target.value) })}
              >
                {KEEP.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </Card>

            <Card title="Download a copy">
              <p>Everything stored about {name}, as a file you keep. Call transcripts held by ElevenLabs are not in it.</p>
              <button onClick={download} disabled={busy} className={`${button} border border-neutral-900`}>
                Download a copy
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
                className={`${button} border border-neutral-900`}
              >
                {info.paused ? "Resume monitoring" : "Pause monitoring"}
              </button>
            </Card>

            <Card title="Family members">
              <p>
                Each person gets their own code. They can read the portal, mark alerts as handled, and leave messages. They cannot change
                settings or delete anything. Remove a code and it stops working within a minute.
              </p>
              <ul className="space-y-2">
                {info.members.length === 0 && <li>No one else has access yet.</li>}
                {info.members.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 rounded-lg border border-neutral-200 p-3">
                    <span>
                      <span className="font-semibold text-neutral-900">{m.name}</span>
                      <span className="block text-sm">{m.last_seen ? `Last used ${when(m.last_seen)}` : "Never used"}</span>
                    </span>
                    <button
                      onClick={() => post("members/" + m.id + "/revoke", {})}
                      disabled={busy}
                      className={`${button} border border-neutral-400`}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
              {newCode && (
                <p className="rounded-lg bg-yellow-100 px-3 py-2 text-neutral-900">
                  Give {newCode.name} this code. It is shown once and cannot be looked up again:{" "}
                  <span className="font-mono text-lg font-bold">{newCode.code}</span>
                </p>
              )}
              <div className="flex gap-2">
                <input
                  aria-label="Name of the family member"
                  className={`${input} min-w-0 flex-1`}
                  placeholder="Name"
                  value={newName}
                  maxLength={40}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button
                  onClick={async () => {
                    const out = await post("members", { name: newName.trim() });
                    if (out) {
                      setNewCode({ name: out.name, code: out.code });
                      setNewName("");
                    }
                  }}
                  disabled={busy || !newName.trim()}
                  className={`${button} bg-neutral-900 text-white`}
                >
                  Add
                </button>
              </div>
            </Card>

            <Card title="Phone alerts (Telegram)">
              {!notify?.enabled && <p>Not set up on the server yet.</p>}
              {notify?.enabled && (
                <>
                  <p>
                    Important alerts reach each connected phone as a message. To keep phones calm: alerts in the same moment become one
                    message, the same kind does not repeat for 30 minutes, there are at most 4 messages an hour, and a serious alert still
                    open after 20 minutes gets one reminder. The portal always shows everything. Anyone can send /stop to the bot to stop.
                  </p>
                  <ul className="space-y-2">
                    {notify.targets.length === 0 && <li>No phone is connected yet.</li>}
                    {notify.targets.map((t) => (
                      <li key={t.id} className="flex items-center justify-between gap-3 rounded-lg border border-neutral-200 p-3">
                        <span className="font-semibold text-neutral-900">{t.name}</span>
                        <button onClick={() => post(`notify/${t.id}/remove`, {})} disabled={busy} className={`${button} border border-neutral-400`}>
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                  {link && (
                    <p className="rounded-lg bg-yellow-100 px-3 py-2 text-neutral-900">
                      Send this to {link.name}. They open it on their phone and press Start. It works once, for 24 hours:{" "}
                      <a href={link.url} className="break-all font-mono font-bold underline">{link.url}</a>
                    </p>
                  )}
                  <div className="flex gap-2">
                    <input
                      aria-label="Name of the person to connect"
                      className={`${input} min-w-0 flex-1`}
                      placeholder="Name"
                      value={phoneName}
                      maxLength={40}
                      onChange={(e) => setPhoneName(e.target.value)}
                    />
                    <button
                      onClick={async () => {
                        const out = await post("notify/link", { name: phoneName.trim() });
                        if (out) {
                          setLink({ name: out.name, url: out.link });
                          setPhoneName("");
                        }
                      }}
                      disabled={busy || !phoneName.trim()}
                      className={`${button} bg-neutral-900 text-white`}
                    >
                      Get a link
                    </button>
                  </div>
                  <label className="flex min-h-11 items-center gap-3 font-medium">
                    <input
                      type="checkbox"
                      className="h-5 w-5"
                      checked={notify.include_words}
                      disabled={busy}
                      onChange={(e) => post("notify/words", { include: e.target.checked })}
                    />
                    Include {name}&rsquo;s own words in messages
                  </label>
                  <p className="text-sm">Off by default. A message on a phone is health information leaving this system, so by default it says what kind of alert it is, and the words stay on the portal.</p>
                  <button
                    onClick={async () => {
                      const out = await post("notify/test", {});
                      if (out) setNote(`Test message delivered to ${out.sent} of ${out.connected} phones.`);
                    }}
                    disabled={busy || notify.targets.length === 0}
                    className={`${button} border border-neutral-900`}
                  >
                    Send a test message
                  </button>
                </>
              )}
            </Card>

            <Card title="Activity log">
              <ul className="space-y-2">
                {info.audit.length === 0 && <li>Nothing yet.</li>}
                {info.audit.map((a, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-semibold text-neutral-900">{a.actor}</span> {ACTION[a.action] ?? a.action}
                    {a.detail ? `, ${a.detail}` : ""}. {when(a.at)}
                  </li>
                ))}
              </ul>
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
                className={`${button} bg-red-700 text-white`}
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
