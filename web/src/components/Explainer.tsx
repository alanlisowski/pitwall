const F1_FONT  = "'Chakra Petch', ui-monospace, monospace";
const DATA_FONT = "'Saira', ui-monospace, monospace";

interface ExplainerProps {
  onEnterMode: (mode: "race" | "strategy") => void;
}

export function Explainer({ onEnterMode }: ExplainerProps) {
  return (
    <div className="space-y-8 py-2" style={{ fontFamily: F1_FONT }}>

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="text-center">
        <p style={{
          fontSize: 9, fontWeight: 700, letterSpacing: "0.35em",
          color: "#E10600", textTransform: "uppercase", marginBottom: 14,
        }}>
          F1 Race Strategy Simulator
        </p>
        <h2
          className="max-w-xl mx-auto"
          style={{
            fontSize: 22, fontWeight: 700, letterSpacing: "0.02em",
            lineHeight: 1.35, color: "#ECE7DA",
          }}
        >
          Take the pit wall — two ways to play a real Grand Prix
        </h2>
        <p
          className="mt-3 max-w-md mx-auto"
          style={{
            fontSize: 12, color: "#6b7280", lineHeight: 1.65,
            fontFamily: DATA_FONT,
          }}
        >
          Both modes run on the same lap-by-lap engine built from real FastF1
          timing data.
        </p>
      </div>

      {/* ── Mode cards ────────────────────────────────────────────────────── */}
      <div className="grid sm:grid-cols-2 gap-4 max-w-3xl mx-auto">

        {/* RACE ENGINEER — featured */}
        <div
          className="relative flex flex-col"
          style={{
            background: "#17171f",
            border: "2px solid #E10600",
            borderRadius: 6,
            padding: "22px 20px 20px",
          }}
        >
          {/* "LIVE · START HERE" badge — sits on the top border */}
          <div style={{
            position: "absolute", top: -1, right: 14,
            background: "#E10600",
            padding: "3px 10px",
            fontSize: 7, fontWeight: 700, letterSpacing: "0.22em",
            color: "#fff", textTransform: "uppercase",
          }}>
            LIVE · START HERE
          </div>

          <div className="flex-1">
            <p style={{
              fontSize: 9, fontWeight: 700, letterSpacing: "0.28em",
              color: "#E10600", textTransform: "uppercase", marginBottom: 7,
            }}>
              RACE ENGINEER
            </p>
            <p style={{
              fontSize: 14, fontWeight: 700, color: "#ECE7DA",
              lineHeight: 1.3, marginBottom: 10,
            }}>
              Race it live. Call every pit stop in the moment.
            </p>
            <p style={{
              fontSize: 11, color: "#71717a", fontFamily: DATA_FONT,
              lineHeight: 1.65, marginBottom: 16,
            }}>
              Pick a driver and race live against a reactive AI field. Call
              the pit stops, work the push/conserve dial, survive the safety
              cars — and live with every decision. A post-race debrief
              tells you what won or lost it.
            </p>
            <div className="flex flex-wrap gap-1.5 mb-5">
              {["live pit calls", "push/conserve dial", "reactive AI"].map((tag) => (
                <span
                  key={tag}
                  style={{
                    fontSize: 8, fontWeight: 700, letterSpacing: "0.14em",
                    textTransform: "uppercase", borderRadius: 3,
                    padding: "3px 8px", color: "#E10600",
                    background: "#E1060010", border: "1px solid #E1060030",
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <button
            onClick={() => onEnterMode("race")}
            style={{
              width: "100%", padding: "10px 0",
              background: "#E10600", border: "none",
              color: "#fff", fontFamily: F1_FONT,
              fontSize: 10, fontWeight: 700, letterSpacing: "0.22em",
              textTransform: "uppercase", cursor: "pointer", borderRadius: 3,
            }}
          >
            START A RACE →
          </button>
        </div>

        {/* STRATEGY LAB — neutral */}
        <div
          className="relative flex flex-col"
          style={{
            background: "#17171f",
            border: "1px solid #2a2a38",
            borderRadius: 6,
            padding: "22px 20px 20px",
          }}
        >
          <div className="flex-1">
            <p style={{
              fontSize: 9, fontWeight: 700, letterSpacing: "0.28em",
              color: "#52525b", textTransform: "uppercase", marginBottom: 7,
            }}>
              STRATEGY LAB
            </p>
            <p style={{
              fontSize: 14, fontWeight: 700, color: "#ECE7DA",
              lineHeight: 1.3, marginBottom: 10,
            }}>
              Edit a strategy. Re-simulate. See who gains.
            </p>
            <p style={{
              fontSize: 11, color: "#71717a", fontFamily: DATA_FONT,
              lineHeight: 1.65, marginBottom: 16,
            }}>
              Edit a real race's pit strategy and re-simulate the full field.
              Move a stop, change a compound, then compare against the baseline
              to see who gains and loses — second by second.
            </p>
            <div className="flex flex-wrap gap-1.5 mb-5">
              {["edit stops", "A/B compare", "deltas"].map((tag) => (
                <span
                  key={tag}
                  style={{
                    fontSize: 8, fontWeight: 700, letterSpacing: "0.14em",
                    textTransform: "uppercase", borderRadius: 3,
                    padding: "3px 8px", color: "#52525b",
                    background: "#1a1a24", border: "1px solid #2a2a38",
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <button
            onClick={() => onEnterMode("strategy")}
            style={{
              width: "100%", padding: "10px 0",
              background: "#1e1e28", border: "1px solid #2a2a38",
              color: "#a0a0b0", fontFamily: F1_FONT,
              fontSize: 10, fontWeight: 700, letterSpacing: "0.22em",
              textTransform: "uppercase", cursor: "pointer", borderRadius: 3,
            }}
          >
            OPEN THE LAB →
          </button>
        </div>
      </div>

      {/* ── Race-picker nudge ─────────────────────────────────────────────── */}
      <p
        className="text-center pb-2"
        style={{
          fontSize: 9, color: "#3f3f46", letterSpacing: "0.2em",
          textTransform: "uppercase", fontFamily: DATA_FONT,
        }}
      >
        ← Select a Grand Prix above to begin
      </p>
    </div>
  );
}
