"""Plot real lap times from the SQLite database, coloured by stint.

Usage (from engine/ with venv active):
    python scripts/plot_laps.py --year 2024 --gp "Hungarian Grand Prix"
    python scripts/plot_laps.py --year 2024 --gp Hungary --drivers VER,NOR,HAM

The --gp argument is matched with SQL LIKE so "Hungary" matches
"Hungarian Grand Prix".

Output: lap_times.png saved to the current directory, and an interactive
window if a display is available.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive by default; override with --show
import matplotlib.pyplot as plt
import numpy as np

_DB_DEFAULT = Path(__file__).parent.parent / "pitwall.db"

# Official F1 compound colours
COMPOUND_COLOUR = {
    "SOFT":         "#E8002D",
    "MEDIUM":       "#FFF200",
    "HARD":         "#FFFFFF",
    "INTERMEDIATE": "#39B54A",
    "WET":          "#0067FF",
    "UNKNOWN":      "#888888",
}

# Fallback colours when the same stint maps to multiple compounds (shouldn't
# happen, but just in case).
_STINT_PALETTE = [
    "#00C6FF", "#FF6B35", "#5EBD3E", "#8A4FFF",
    "#FF2D55", "#FFD700", "#00E5CC",
]


def _compound_for_stint(stint_rows: list[tuple]) -> str:
    """Return the most common compound seen in this stint."""
    counts: dict[str, int] = defaultdict(int)
    for _, _, compound, _ in stint_rows:
        counts[compound] += 1
    return max(counts, key=lambda k: counts[k])


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot lap times by stint")
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--gp",      required=True, help="Partial GP name, e.g. 'Hungary'")
    parser.add_argument("--db",      default=str(_DB_DEFAULT))
    parser.add_argument(
        "--drivers",
        default=None,
        help="Comma-separated 3-letter codes, e.g. VER,NOR  (default: top 10 finishers)",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Open an interactive matplotlib window (default: save PNG only)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    rows = conn.execute(
        """
        SELECT  d.driver_code,
                d.finishing_position,
                l.lap_number,
                l.lap_time_s,
                l.compound,
                l.stint,
                l.is_pit_in_lap
        FROM    laps    l
        JOIN    drivers d ON d.id     = l.driver_id
        JOIN    races   r ON r.id     = d.race_id
        WHERE   r.year    = ?
          AND   (r.gp_name LIKE ? OR r.gp_key LIKE ?)
          AND   l.lap_time_s IS NOT NULL
        ORDER BY d.finishing_position, l.lap_number
        """,
        (args.year, f"%{args.gp}%", f"%{args.gp}%"),
    ).fetchall()
    conn.close()

    if not rows:
        print(
            f"No data found for {args.year} '{args.gp}'. "
            "Run: python -m engine.ingest --year ... --gp ...",
            file=sys.stderr,
        )
        sys.exit(1)

    # Organise: {(finish_pos, code): {stint: [(lap, time, compound, pit_in)]}}
    driver_stints: dict[tuple[int, str], dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for code, pos, lap_num, lap_time, compound, stint, pit_in in rows:
        if args.drivers and code not in args.drivers.upper().split(","):
            continue
        driver_stints[(pos, code)][stint].append((lap_num, lap_time, compound, bool(pit_in)))

    if not driver_stints:
        print("No matching drivers found.", file=sys.stderr)
        sys.exit(1)

    ordered = sorted(driver_stints.keys())[:10]  # cap at 10 for readability
    n = len(ordered)
    ncols = 2
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows), sharex=False)
    fig.patch.set_facecolor("#0d0d1a")
    axes_flat: list = np.array(axes).flatten().tolist() if n > 1 else [axes]

    for ax, (pos, code) in zip(axes_flat, ordered):
        stints = driver_stints[(pos, code)]

        for i, (stint_num, stint_rows) in enumerate(sorted(stints.items())):
            compound = _compound_for_stint(stint_rows)
            colour = COMPOUND_COLOUR.get(compound, _STINT_PALETTE[i % len(_STINT_PALETTE)])

            lap_nums = [r[0] for r in stint_rows]
            lap_times = [r[1] for r in stint_rows]

            ax.plot(lap_nums, lap_times, ".", color=colour, markersize=5, zorder=3)
            ax.plot(lap_nums, lap_times, "-", color=colour, alpha=0.35, linewidth=1, zorder=2)

            # Pit-in lap marker (downward triangle)
            pit_rows = [(r[0], r[1]) for r in stint_rows if r[3]]
            if pit_rows:
                px, py = zip(*pit_rows)
                ax.plot(px, py, "v", color="white", markersize=7, zorder=5,
                        markeredgecolor="#555", markeredgewidth=0.5)

            # Stint label mid-stint
            mid = len(lap_nums) // 2
            ax.annotate(
                f"S{stint_num} {compound}",
                xy=(lap_nums[mid], lap_times[mid]),
                xytext=(0, 8),
                textcoords="offset points",
                fontsize=7,
                color=colour,
                ha="center",
            )

        ax.set_facecolor("#1a1a2e")
        ax.set_title(f"P{pos}  {code}", color="white", fontsize=11, pad=6)
        ax.set_xlabel("Lap", color="#aaa", fontsize=9)
        ax.set_ylabel("Lap time (s)", color="#aaa", fontsize=9)
        ax.tick_params(colors="#aaa", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
        ax.grid(axis="y", color="#2a2a3e", linewidth=0.5, zorder=0)

    # Hide unused subplots
    for ax in axes_flat[len(ordered):]:
        ax.set_visible(False)

    gp_title = rows[0][0] and f"{args.year}  ·  {args.gp}" or f"{args.year} {args.gp}"
    fig.suptitle(
        f"{args.year}  ·  {args.gp}  —  Lap times by stint",
        color="white", fontsize=13, y=1.01,
    )
    plt.tight_layout()

    out = Path("lap_times.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved {out.resolve()}")

    if args.show:
        matplotlib.use("TkAgg")  # switch to interactive backend
        plt.show()


if __name__ == "__main__":
    main()
