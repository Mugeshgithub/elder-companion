import { useEffect, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Med = { name: string; time: string };
type Person = { name: string; relation: string };
type Place = { item: string; place: string };
type Form = {
  name: string;
  note: string;
  meds: Med[];
  routines: string[];
  people: Person[];
  places: Place[];
  checkin: string;
};

const EMPTY: Form = { name: "", note: "", meds: [], routines: [], people: [], places: [], checkin: "" };

// ?patient=99 points the form at the test patient, same as the family portal
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;

const input = "rounded-lg border border-neutral-300 bg-white px-3 py-2 text-lg text-neutral-900";
const full = `${input} w-full`;
const grow = `${input} min-w-0 flex-1`; // inputs sharing a row split the space and never overflow it
const small = "min-h-11 rounded-lg border border-neutral-300 bg-white px-4 text-base font-semibold text-neutral-800";

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-neutral-300 bg-white p-4">
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="text-base text-neutral-600">{hint}</p>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Remove({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} className="min-h-11 min-w-11 shrink-0 rounded-lg border border-neutral-300 text-xl text-neutral-700">
      ×
    </button>
  );
}

export default function Setup() {
  const [f, setF] = useState<Form>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [count, setCount] = useState(0);

  useEffect(() => {
    api(`/setup/${PID}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        setF({
          name: d.name ?? "",
          note: d.note ?? "",
          meds: d.meds ?? [],
          routines: d.routines ?? [],
          people: d.people ?? [],
          places: d.places ?? [],
          checkin: d.checkin_minutes ? String(d.checkin_minutes) : "",
        });
        setLoaded(true);
      })
      .catch(() => setState("error"));
  }, []);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => {
    setF((p) => ({ ...p, [k]: v }));
    if (state === "saved") setState("idle");
  };
  const edit = <T,>(list: T[], i: number, patch: Partial<T>) => list.map((x, j) => (j === i ? { ...x, ...patch } : x));
  const drop = <T,>(list: T[], i: number) => list.filter((_, j) => j !== i);

  const save = async () => {
    setState("saving");
    try {
      const res = await api(`/setup/${PID}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: f.name,
          note: f.note,
          meds: f.meds.filter((m) => m.name.trim()),
          routines: f.routines.filter((r) => r.trim()),
          people: f.people.filter((p) => p.name.trim()),
          places: f.places.filter((p) => p.item.trim() && p.place.trim()),
          checkin_minutes: f.checkin.trim() ? Number(f.checkin) : null,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setCount((await res.json()).facts ?? 0);
      setState("saved");
    } catch {
      setState("error");
    }
  };

  return (
    <div className="min-h-dvh bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-2xl px-4 py-5 pb-28">
        <header className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-bold">Set up the companion</h1>
          <a href="/caregiver" className="text-base font-medium text-neutral-600 underline underline-offset-4">
            Back to portal
          </a>
        </header>
        <p className="mt-2 text-base text-neutral-700">
          Fill this in once. They will not be asked to set anything up. The companion introduces itself the next time it opens.
        </p>

        {!loaded && state !== "error" && <p className="mt-4 text-base text-neutral-600">Loading.</p>}
        {state === "error" && !loaded && <p className="mt-4 text-base font-medium">Cannot reach the server.</p>}

        {loaded && (
          <div className="mt-4 space-y-4">
            <Section title="About them" hint="The note stays private. The companion keeps it in mind and never repeats it to them.">
              <label className="block text-base font-semibold">
                First name
                <input className={`${full} mt-1`} value={f.name} onChange={(e) => set("name", e.target.value)} />
              </label>
              <label className="block text-base font-semibold">
                Private note
                <textarea
                  rows={3}
                  className={`${full} mt-1`}
                  value={f.note}
                  placeholder="For example: has early memory loss, can get anxious in the evening."
                  onChange={(e) => set("note", e.target.value)}
                />
              </label>
            </Section>

            <Section title="Daily medicine" hint="A time here means a dose is due. It is never treated as taken. Only they can say they took it.">
              {f.meds.map((m, i) => (
                <div key={i} className="flex gap-2">
                  <input aria-label="Medicine" className={grow} placeholder="The blue pill" value={m.name} onChange={(e) => set("meds", edit(f.meds, i, { name: e.target.value }))} />
                  <input aria-label="Time" type="time" className={`${input} w-36 shrink-0`} value={m.time} onChange={(e) => set("meds", edit(f.meds, i, { time: e.target.value }))} />
                  <Remove label="Remove medicine" onClick={() => set("meds", drop(f.meds, i))} />
                </div>
              ))}
              <button type="button" className={small} onClick={() => set("meds", [...f.meds, { name: "", time: "" }])}>
                Add medicine
              </button>
            </Section>

            <Section title="Daily routine" hint="Meals, walks, anything that happens most days.">
              {f.routines.map((r, i) => (
                <div key={i} className="flex gap-2">
                  <input aria-label="Routine" className={grow} placeholder="Has breakfast around 8" value={r} onChange={(e) => set("routines", f.routines.map((x, j) => (j === i ? e.target.value : x)))} />
                  <Remove label="Remove routine" onClick={() => set("routines", drop(f.routines, i))} />
                </div>
              ))}
              <button type="button" className={small} onClick={() => set("routines", [...f.routines, ""])}>
                Add routine
              </button>
            </Section>

            <Section title="People who matter" hint="So it can answer who someone is.">
              {f.people.map((p, i) => (
                <div key={i} className="flex gap-2">
                  <input aria-label="Name" className={grow} placeholder="Anna" value={p.name} onChange={(e) => set("people", edit(f.people, i, { name: e.target.value }))} />
                  <input aria-label="Relation" className={grow} placeholder="Daughter" value={p.relation} onChange={(e) => set("people", edit(f.people, i, { relation: e.target.value }))} />
                  <Remove label="Remove person" onClick={() => set("people", drop(f.people, i))} />
                </div>
              ))}
              <button type="button" className={small} onClick={() => set("people", [...f.people, { name: "", relation: "" }])}>
                Add person
              </button>
            </Section>

            <Section title="Where things usually are" hint="It will say these are usual places. Anything they tell it later wins.">
              {f.places.map((p, i) => (
                <div key={i} className="flex gap-2">
                  <input aria-label="Item" className={grow} placeholder="Keys" value={p.item} onChange={(e) => set("places", edit(f.places, i, { item: e.target.value }))} />
                  <input aria-label="Usual place" className={grow} placeholder="In the blue bag" value={p.place} onChange={(e) => set("places", edit(f.places, i, { place: e.target.value }))} />
                  <Remove label="Remove place" onClick={() => set("places", drop(f.places, i))} />
                </div>
              ))}
              <button type="button" className={small} onClick={() => set("places", [...f.places, { item: "", place: "" }])}>
                Add place
              </button>
            </Section>

            <Section title="Check-ins" hint="How long they can be quiet before the companion calls. Leave empty for the default.">
              <label className="flex items-center gap-3 text-base font-semibold">
                <input
                  inputMode="numeric"
                  className={`${input} w-28`}
                  placeholder="240"
                  value={f.checkin}
                  onChange={(e) => set("checkin", e.target.value.replace(/\D/g, ""))}
                />
                minutes
              </label>
            </Section>
          </div>
        )}
      </div>

      {loaded && (
        <div className="fixed inset-x-0 bottom-0 border-t border-neutral-300 bg-white/95 px-4 py-3">
          <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
            <p role="status" className="text-base font-medium">
              {state === "saving" && "Saving."}
              {state === "saved" && `Saved. ${count} notes for the companion.`}
              {state === "error" && "Could not save. Try again."}
            </p>
            <button
              type="button"
              onClick={save}
              disabled={state === "saving" || !f.name.trim()}
              className="min-h-11 rounded-xl bg-neutral-900 px-6 text-lg font-semibold text-white disabled:opacity-40"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
