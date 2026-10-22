import Inspector from "./Inspector";

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
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-2xl border border-white/10">
          <Inspector />
        </div>
      </div>
    </div>
  );
}
