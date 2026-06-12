const STEPS = [
  {
    num: "01",
    title: "Real race data",
    body: "FastF1 pulls live timing from Formula 1 and caches it to SQLite once. The API reads only from the cache — no network calls during simulation.",
  },
  {
    num: "02",
    title: "Five-component lap model",
    body: "Lap time = base pace + tyre degradation + compound offset + fuel burn + pit-lane loss. The undercut/overcut emerge from the model — never hard-coded.",
  },
  {
    num: "03",
    title: "Edit & compare",
    body: "Click any driver's row to edit their pit stops. Drag the white markers or type a lap number. Hit Compare to re-simulate and see who gained, who lost.",
  },
];

export function Explainer() {
  return (
    <div className="border border-zinc-800 rounded-lg p-6 bg-zinc-900/40">
      <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-5">
        How it works
      </p>
      <div className="grid sm:grid-cols-3 gap-6">
        {STEPS.map((step) => (
          <div key={step.num} className="space-y-2">
            <div className="text-3xl font-bold text-zinc-800">{step.num}</div>
            <div className="text-sm text-zinc-200 font-semibold">{step.title}</div>
            <div className="text-xs text-zinc-500 leading-relaxed">{step.body}</div>
          </div>
        ))}
      </div>
      <p className="mt-6 text-xs text-zinc-700">
        ← Select a race above to load the baseline simulation.
      </p>
    </div>
  );
}
