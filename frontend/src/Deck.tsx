import { useEffect, useState, type ReactNode } from "react";

function Title({ kicker, children }: { kicker?: string; children: ReactNode }) {
  return (
    <>
      {kicker && <p className="text-sm font-bold uppercase tracking-[0.2em] text-emerald-300 sm:text-base">{kicker}</p>}
      <h1 className="mt-2 text-[clamp(2rem,5vw,4rem)] font-semibold leading-tight">{children}</h1>
    </>
  );
}

function Box({ name, note, tone = "" }: { name: string; note: string; tone?: string }) {
  return (
    <div className={`rounded-xl border border-white/15 bg-white/[0.06] px-4 py-3 ${tone}`}>
      <p className="text-lg font-semibold">{name}</p>
      <p className="text-sm text-white/65">{note}</p>
    </div>
  );
}

const Down = () => (
  <p aria-hidden className="text-center text-2xl leading-none text-white/40">
    ↓
  </p>
);

const SLIDES: ReactNode[] = [
  // 1
  <>
    <Title kicker="Proactive memory companion">Companion</Title>
    <p className="mt-4 max-w-3xl text-[clamp(1.1rem,2.2vw,1.75rem)] text-white/80">
      A voice companion for people who forget. It remembers for them, and it reaches out first.
    </p>
    <p className="mt-10 text-base text-white/55 sm:text-lg">
      Built on Aiven for Valkey and Aiven for PostgreSQL with pgvector
    </p>
  </>,
  // 2
  <>
    <Title kicker="The problem">Help arrives only if someone asks</Title>
    <div className="mt-8 grid gap-6 sm:grid-cols-2">
      <div>
        <p className="text-[clamp(2.5rem,6vw,5rem)] font-bold leading-none text-emerald-300">55 million</p>
        <p className="mt-2 text-lg text-white/75">people live with dementia worldwide (WHO, 2021)</p>
      </div>
      <div>
        <p className="text-[clamp(2.5rem,6vw,5rem)] font-bold leading-none text-emerald-300">5 hours</p>
        <p className="mt-2 text-lg text-white/75">a day of unpaid care from family and friends, on average (WHO, 2019)</p>
      </div>
    </div>
    <p className="mt-10 max-w-3xl text-xl text-white/80">
      Most assistants wait to be asked. A person who forgets cannot ask for the thing they forgot.
    </p>
  </>,
  // 3
  <>
    <Title kicker="What it does">Four things, and nothing else</Title>
    <ul className="mt-8 grid gap-4 sm:grid-cols-2">
      {[
        ["It remembers", "Facts are saved as they speak: where things are, whether a pill was taken."],
        ["It never guesses", "Nothing in memory means it says so. No invented places, no assumed doses."],
        ["It reaches out first", "After a quiet spell it starts the call itself, with a first line built from real facts."],
        ["It tells the family", "Distress, a missed dose, or a request puts an alert on the family portal, in the person's own words."],
      ].map(([h, p]) => (
        <li key={h} className="rounded-2xl border border-white/15 bg-white/[0.06] p-5">
          <p className="text-xl font-semibold">{h}</p>
          <p className="mt-1 text-base text-white/70">{p}</p>
        </li>
      ))}
    </ul>
  </>,
  // 4
  <>
    <Title kicker="How the data flows">What happens when you speak</Title>
    <div className="mt-6 grid max-w-2xl gap-2">
      <Box name="Voice, ElevenLabs" note="Speech in, speech out, interruptions handled" />
      <Down />
      <Box name="FastAPI server" note="Builds the context for every reply" />
      <Down />
      <div className="grid gap-3 sm:grid-cols-2">
        <Box tone="border-emerald-300/40" name="Aiven for Valkey" note="Recent turns, mood, silence timer" />
        <Box tone="border-sky-300/40" name="Aiven for Postgres + pgvector" note="Facts, found by meaning" />
      </div>
      <Down />
      <Box name="Claude writes the reply" note="Four seconds after you stop talking, it also extracts new facts and saves them" />
    </div>
  </>,
  // 5
  <>
    <Title kicker="Why two memories">Fast and short, slow and lasting</Title>
    <div className="mt-8 grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-emerald-300/40 bg-white/[0.06] p-5">
        <p className="text-2xl font-semibold">Aiven for Valkey</p>
        <p className="text-emerald-300">Working memory</p>
        <ul className="mt-3 space-y-2 text-lg text-white/80">
          <li>What was just said, and the mood.</li>
          <li>A silence timer that expires on its own.</li>
          <li>When the timer key expires, Valkey tells us. That starts the proactive call.</li>
        </ul>
      </div>
      <div className="rounded-2xl border border-sky-300/40 bg-white/[0.06] p-5">
        <p className="text-2xl font-semibold">Aiven for PostgreSQL + pgvector</p>
        <p className="text-sky-300">Long-term memory</p>
        <ul className="mt-3 space-y-2 text-lg text-white/80">
          <li>Every fact is stored with a 1024-number vector.</li>
          <li>A question finds the right fact even when the words differ.</li>
          <li>The same store answers what happened today, and tells the family.</li>
        </ul>
      </div>
    </div>
  </>,
  // 6
  <>
    <Title kicker="Safety is in the code">Rules the model cannot talk its way past</Title>
    <ul className="mt-8 max-w-3xl space-y-4 text-xl text-white/85">
      <li>A dose is confirmed only if the person said so today. Otherwise it asks.</li>
      <li>It never asks them to remember or think back.</li>
      <li>It cannot phone anyone, so it leaves a note for the family only after they agree.</li>
      <li>Silence never reaches the model and never produces alarming speech.</li>
    </ul>
  </>,
  // medical documents
  <>
    <Title kicker="Medical documents, with sources">It only says what a document says, and shows where</Title>
    <div className="mt-8 grid gap-5 lg:grid-cols-3">
      {[
        ["1. Read", "A forced tool call turns a clinic letter or prescription into structured findings: medicines, appointments, instructions."],
        ["2. Check", "Every finding must quote the document. Code checks the quote on the page, so a quote that is not there cannot be approved."],
        ["3. Approve", "The family approves each finding. The companion names its source. Diagnoses and test scores stay a family record."],
      ].map(([h, p]) => (
        <div key={h} className="rounded-2xl border border-white/15 bg-white/[0.06] p-5">
          <p className="text-xl font-semibold text-emerald-300">{h}</p>
          <p className="mt-2 text-lg text-white/80">{p}</p>
        </div>
      ))}
    </div>
    <p className="mt-6 max-w-4xl text-lg text-white/75">
      It never advises on doses. A question like &ldquo;should I take double?&rdquo; gets a fixed answer that points to the doctor or pharmacist,
      and it never confirms a dose was taken.
    </p>
  </>,
  // EU rules
  <>
    <Title kicker="Responsible by design">Built with EU rules in mind. Not certified.</Title>
    <div className="mt-8 grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-emerald-300/40 bg-white/[0.06] p-5">
        <p className="text-xl font-semibold text-emerald-300">In place</p>
        <ul className="mt-3 space-y-2 text-lg text-white/80">
          <li>Database and servers in the EU.</li>
          <li>Consent recorded: the person agreed, or someone with legal authority did.</li>
          <li>It says it is an AI, and it never gives medical advice.</li>
          <li>Pause, download a copy, delete, and automatic expiry.</li>
          <li>Each family member has their own code, and an activity log shows who did what.</li>
        </ul>
      </div>
      <div className="rounded-2xl border border-amber-300/40 bg-white/[0.06] p-5">
        <p className="text-xl font-semibold text-amber-300">Still to do</p>
        <ul className="mt-3 space-y-2 text-lg text-white/80">
          <li>A data protection impact assessment (GDPR Article 35).</li>
          <li>Processor agreements with every service we use.</li>
          <li>Legal review: the basis for health data, capacity to consent, and France&rsquo;s health data hosting rule.</li>
          <li>Keep the purpose to companionship, so it is not a medical device.</li>
        </ul>
      </div>
    </div>
    <p className="mt-6 text-base text-white/60 sm:text-lg">
      GDPR, the EU AI Act and medical device rules all touch this product. This is not legal advice, and nothing here is certified or audited.
    </p>
  </>,
  // 7
  <>
    <Title kicker="Where it stands">What is real, and what comes next</Title>
    <div className="mt-8 grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-white/15 bg-white/[0.06] p-5">
        <p className="text-xl font-semibold">Honest limits</p>
        <ul className="mt-3 space-y-2 text-lg text-white/75">
          <li>Notify family writes to the portal. It does not text anyone yet.</li>
          <li>Silence means not talking to the companion. There are no sensors.</li>
          <li>Alerts rely on model judgment, so a false alarm or a miss can happen.</li>
        </ul>
      </div>
      <div className="rounded-2xl border border-white/15 bg-white/[0.06] p-5">
        <p className="text-xl font-semibold">Next</p>
        <ul className="mt-3 space-y-2 text-lg text-white/75">
          <li>Real notifications to the family, by message.</li>
          <li>Location and camera as extra sources of memory.</li>
          <li>One engine for anyone who drifts, such as solo developers.</li>
        </ul>
      </div>
    </div>
  </>,
];

export default function Deck() {
  const [i, setI] = useState(0);
  const last = SLIDES.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") setI((n) => Math.min(last, n + 1));
      if (e.key === "ArrowLeft" || e.key === "PageUp") setI((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [last]);

  return (
    <div className="flex min-h-dvh flex-col bg-gradient-to-b from-[#0a1d33] via-[#0b2a3f] to-[#0b3a35] text-[#f5f8fb]">
      <main className="flex flex-1 flex-col justify-center px-6 py-8 sm:px-12 lg:px-20">
        <div key={i} className="slide mx-auto w-full max-w-5xl">
          {SLIDES[i]}
        </div>
      </main>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-6 py-3 sm:px-12">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setI((n) => Math.max(0, n - 1))}
            disabled={i === 0}
            aria-label="Previous slide"
            className="min-h-11 min-w-11 rounded-lg border border-white/20 text-xl disabled:opacity-30"
          >
            ←
          </button>
          <button
            onClick={() => setI((n) => Math.min(last, n + 1))}
            disabled={i === last}
            aria-label="Next slide"
            className="min-h-11 min-w-11 rounded-lg border border-white/20 text-xl disabled:opacity-30"
          >
            →
          </button>
          <span className="text-sm tabular-nums text-white/60">
            {i + 1} / {SLIDES.length}
          </span>
        </div>
        <a
          href="/demo"
          className="inline-flex min-h-11 items-center rounded-xl bg-emerald-400 px-6 text-lg font-semibold text-neutral-900 hover:bg-emerald-300"
        >
          Open app
        </a>
      </footer>
    </div>
  );
}
