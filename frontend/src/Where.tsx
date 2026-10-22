import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { PATIENT_ID } from "./config";

type Status = { home_set: boolean; radius: number | null; sharing: boolean; at: string | null; inside: boolean | null };

// ?patient=99 points the page at the test patient, same as the other screens
const PID = Number(new URLSearchParams(window.location.search).get("patient")) || PATIENT_ID;
const SEND_EVERY_MS = 55_000;
const button = "min-h-14 w-full rounded-xl px-5 text-lg font-semibold disabled:opacity-40";
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// Optional and limited, and it says so. A web page cannot track in the background, so this only works while the page
// stays open on the phone. Only the latest position is kept, and Stop deletes it.
export default function Where() {
  const [status, setStatus] = useState<Status | null>(null);
  const [on, setOn] = useState(false);
  const [note, setNote] = useState("");
  const watchId = useRef<number | null>(null);
  const lastSent = useRef(0);
  const lock = useRef<WakeLockSentinel | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api(`/location/${PID}`);
      if (r.ok) setStatus(await r.json());
    } catch {
      /* the next poll will try again */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const stopWatching = () => {
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
    watchId.current = null;
    lock.current?.release().catch(() => {});
    lock.current = null;
  };
  useEffect(() => stopWatching, []);

  const start = async () => {
    setNote("");
    if (!navigator.geolocation) return setNote("This browser cannot share a location.");
    try {
      lock.current = (await navigator.wakeLock?.request("screen")) ?? null; // keep the screen on, or the page is paused
    } catch {
      /* not every phone allows it */
    }
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => {
        if (Date.now() - lastSent.current < SEND_EVERY_MS) return;
        lastSent.current = Date.now();
        api(`/location/${PID}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }),
        })
          .then(load)
          .catch(() => {});
      },
      (err) => {
        setNote(err.code === err.PERMISSION_DENIED ? "Location was blocked. Allow it for this site in the browser settings." : "Could not get a location yet.");
        setOn(false);
        stopWatching();
      },
      { enableHighAccuracy: true, maximumAge: 30_000, timeout: 20_000 },
    );
    setOn(true);
  };

  const stop = async () => {
    stopWatching();
    setOn(false);
    try {
      await api(`/location/${PID}/stop`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      setNote("Stopped. The last position was deleted.");
    } catch {
      setNote("Stopped here, but could not reach the server to delete the last position.");
    }
    load();
  };

  const setHome = () => {
    setNote("");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const r = await api(`/location/${PID}/home`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude, radius: 300 }),
          });
          if (!r.ok) throw new Error(String(r.status));
          setNote("Saved. Home is here, with a safe area of 300 metres.");
          load();
        } catch {
          setNote("Could not save home. Try again.");
        }
      },
      () => setNote("Could not get this phone's location. Allow it in the browser settings."),
      { enableHighAccuracy: true, timeout: 20_000 },
    );
  };

  return (
    <div className="min-h-dvh bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-md px-4 py-5 pb-12">
        <header className="flex items-baseline justify-between gap-3">
          <h1 className="text-xl font-bold">Share my location</h1>
          <a href="/caregiver" className="text-base font-medium text-neutral-600 underline underline-offset-4">Portal</a>
        </header>

        <section className="mt-4 rounded-2xl border border-neutral-300 bg-white p-4 text-base text-neutral-700">
          <p>
            While this page is open on this phone, its location is shared with the family. If the phone stays outside the safe area around
            home for 5 minutes, the family is told, with a map link.
          </p>
          <p className="mt-2 font-semibold text-neutral-900">
            It cannot track in the background yet. Keep this page open with the screen on. If the page is closed, the family sees
            &ldquo;not sharing&rdquo;, never a guess.
          </p>
          <p className="mt-2">Only the latest position is kept, never a history. Stop deletes it.</p>
          {!on ? (
            <button onClick={start} className={`${button} mt-4 bg-neutral-900 text-white`}>
              Start sharing
            </button>
          ) : (
            <button onClick={stop} className={`${button} mt-4 border-2 border-neutral-900`}>
              Stop sharing
            </button>
          )}
          <p className="mt-2 text-sm">By pressing Start you agree to share this phone&rsquo;s location with your family.</p>
        </section>

        <section className="mt-4 rounded-2xl border border-neutral-300 bg-white p-4 text-base text-neutral-700">
          <h2 className="text-lg font-bold text-neutral-900">Safe area</h2>
          <p className="mt-1">
            {status?.home_set ? `Set, with a radius of ${status.radius} metres.` : "Not set yet, so nobody can be told they have left."}
          </p>
          <p className="mt-2">The family owner sets this once, standing at home with this phone.</p>
          <button onClick={setHome} className={`${button} mt-3 border-2 border-neutral-900`}>
            This place is home
          </button>
        </section>

        <section className="mt-4 rounded-2xl border border-neutral-300 bg-white p-4 text-base">
          <h2 className="text-lg font-bold">Right now</h2>
          <p className="mt-1">
            {!status
              ? "Loading."
              : status.sharing
                ? `Sharing. Last position at ${status.at ? clock(status.at) : ""}. ${status.inside === null ? "" : status.inside ? "Inside the safe area." : "Outside the safe area."}`
                : "Not sharing."}
          </p>
        </section>
        <p role="status" className="mt-3 min-h-6 text-base font-medium">{note}</p>
      </div>
    </div>
  );
}
