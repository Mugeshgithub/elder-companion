import { useEffect, useState } from "react";
import PatientView from "./PatientView";
import CaregiverView from "./CaregiverView";
import Deck from "./Deck";
import Demo from "./Demo";
import Inspector from "./Inspector";
import Setup from "./Setup";
import Privacy from "./Privacy";
import Documents from "./Documents";
import { getCode, saveCode } from "./api";

function CodeGate({ retry, onDone }: { retry: boolean; onDone: () => void }) {
  const [code, setCode] = useState("");
  return (
    <main className="min-h-dvh flex items-center justify-center bg-[#0a1d33] px-6 text-[#f5f8fb]">
      <form
        className="w-full max-w-xs space-y-4 text-center"
        onSubmit={(e) => {
          e.preventDefault();
          saveCode(code.trim());
          onDone();
        }}
      >
        <p className="text-xl font-semibold">Enter your access code</p>
        {retry && <p className="text-base text-amber-300">That code did not work.</p>}
        <input
          autoFocus
          type="password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="w-full rounded-xl bg-white/10 px-4 py-3 text-center text-lg outline-none focus:ring-2 focus:ring-emerald-300"
        />
        <button className="min-h-11 w-full rounded-xl bg-emerald-400 font-semibold text-neutral-900">Continue</button>
      </form>
    </main>
  );
}

export default function App() {
  // Local development has no gate. A deployed site asks for the code until the server accepts it.
  const [locked, setLocked] = useState(import.meta.env.PROD && !getCode());
  const [tried, setTried] = useState(false);

  useEffect(() => {
    const lock = () => {
      setTried(true);
      setLocked(true);
    };
    window.addEventListener("ec-locked", lock);
    return () => window.removeEventListener("ec-locked", lock);
  }, []);

  const path = window.location.pathname;
  if (path === "/") return <Deck />; // the slides hold no data, so they need no code
  if (locked) return <CodeGate retry={tried} onDone={() => setLocked(false)} />;
  if (path.startsWith("/caregiver")) return <CaregiverView />;
  if (path.startsWith("/demo")) return <Demo />;
  if (path.startsWith("/inspector")) return <Inspector />;
  if (path.startsWith("/setup")) return <Setup />;
  if (path.startsWith("/privacy")) return <Privacy />;
  if (path.startsWith("/documents")) return <Documents />;
  return <PatientView />; // /app, the companion on its own, is what the installed Mac app opens
}
