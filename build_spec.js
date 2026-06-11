const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType,
  TableOfContents, PageNumber, Header, Footer, ExternalHyperlink, PageBreak,
} = require("docx");

const ACCENT = "E10600";   // F1 red
const DARK = "15151E";
const GREY = "555555";
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const CONTENT_W = 9360;

// ---------- helpers ----------
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const P = (t, opts = {}) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, ...opts })] });
const bullet = (t, bold) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 },
  children: Array.isArray(t) ? t : [new TextRun({ text: t, bold: !!bold })],
});
const num = (t) => new Paragraph({
  numbering: { reference: "numbers", level: 0 }, spacing: { after: 60 },
  children: [new TextRun(t)],
});
const labelRun = (label, rest) => [new TextRun({ text: label, bold: true }), new TextRun({ text: rest })];

function table(headers, rows, widths) {
  const headRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders, width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: ACCENT, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, color: "FFFFFF" })] })],
    })),
  });
  const bodyRows = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => new TableCell({
      borders, width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: ri % 2 ? "F4F4F6" : "FFFFFF", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun(c)] })],
    })),
  }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: [headRow, ...bodyRows] });
}

const styles = {
  default: { document: { run: { font: "Arial", size: 21 } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 30, bold: true, font: "Arial", color: ACCENT },
      paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0,
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 4 } } } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 24, bold: true, font: "Arial", color: DARK },
      paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
  ],
};

const numbering = {
  config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
  ],
};

// ---------- title page ----------
const titlePage = [
  new Paragraph({ spacing: { before: 1800, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "PITWALL", bold: true, size: 72, color: ACCENT, font: "Arial" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [new TextRun({ text: "An F1 Race Strategy Simulator", size: 32, color: DARK })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
    children: [new TextRun({ text: "Project Specification — v1 (“Meaty” scope, ~3–4 weeks)", italics: true, size: 22, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 },
    children: [new TextRun({ text: "Prepared for Alan Lisowski  ·  June 2026", size: 20, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Simulate pit stops, tyre wear, and the undercut. Ask “what if we boxed on lap 18?” and watch the race re-order.", italics: true, size: 22, color: DARK })] }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------- TOC ----------
const toc = [
  new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 28, color: DARK })], spacing: { after: 160 } }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------- body ----------
const body = [];
const add = (...els) => els.forEach((e) => body.push(e));

// 1. Overview
add(H1("1. Overview"));
add(P("PitWall is an interactive Formula 1 race strategy simulator. The user picks a real Grand Prix (data pulled from the FastF1 library), sets a starting grid and tyre allocation, then plays strategist: choose when each car pits and onto which compound, and the engine simulates the full race lap-by-lap — modelling tyre degradation, fuel burn, pit-lane time loss, and the undercut/overcut effect — to show how the finishing order changes."));
add(P("The hook is the “what if” loop. Drag a pit stop from lap 18 to lap 22 and the whole race re-orders in front of you, with a delta chart showing exactly where the time was won or lost. It is part data-visualisation showcase, part simulation engine — and it ties directly to a genuine interest in F1 engineering, which makes it memorable in interviews."));

add(H2("Why this project earns interviews"));
add(bullet("It is not another CRUD app. A simulation engine with a real model behind it signals you can reason about systems, not just wire up forms.", false));
add(bullet("It is demoable in 30 seconds. A recruiter can open a live link, drag a slider, and immediately see something happen — engagement beats screenshots.", false));
add(bullet("It shows full-stack range without being generic: a Python modelling/data layer, a typed API, and a polished interactive React front-end.", false));
add(bullet("It is grounded in real data (FastF1, free, no API key), so your numbers are defensible and you can validate the simulation against actual race results.", false));

// 2. Concept & UX
add(H1("2. Concept & User Experience"));
add(P("The core screen is a race timeline. Across the top, a lap axis (1 → N). For each car, a horizontal “stint bar” coloured by tyre compound, with pit stops as draggable markers. Below, a live-updating chart shows the gap to the leader over the course of the race."));
add(P("The primary interaction loop:"));
add(num("Pick a race and session (e.g. 2024 Hungarian GP)."));
add(num("The app seeds a realistic baseline: real starting grid, real pace, real tyre allocation."));
add(num("The user edits a strategy — move a pit window, switch a compound, add or remove a stop."));
add(num("The engine re-simulates instantly and animates the new running order."));
add(num("A summary panel reports finishing positions, total race time, and the net gain/loss vs. the baseline strategy."));
add(P("A secondary “compare” mode lets the user pit two strategies against each other (e.g. one-stop vs. two-stop) and see which wins and by how much — the actual question a race strategist answers on the pit wall."));

// 3. Simulation model
add(H1("3. The Simulation Model"));
add(P("This is the technical heart of the project and the part worth talking about in interviews. The race is simulated as a discrete lap-by-lap loop. Each lap, every car is assigned a lap time built from a small set of additive components, then positions are recomputed from cumulative time."));
add(H2("Lap-time components"));
add(table(
  ["Component", "Model", "Typical value (grounded in research)"],
  [
    ["Base pace", "Per-car constant from real qualifying / race pace in FastF1", "~90–110 s/lap, track dependent"],
    ["Tyre degradation", "Linear (or piecewise-linear) loss that grows with tyre age, per compound", "Soft ~0.10–0.15 s/lap, Medium ~0.06–0.10, Hard ~0.03–0.06"],
    ["Compound offset", "Fixed pace delta between compounds (softer = faster when fresh)", "Soft to Hard gap ~0.6–1.0 s/lap"],
    ["Fuel burn", "Car gets lighter each lap → lap time improves linearly", "~0.03–0.06 s/lap improvement per lap of fuel"],
    ["Pit-lane loss", "One-off time penalty when a stop is taken", "Total ~18–25 s, circuit dependent"],
    ["Traffic / dirty air", "Penalty when a car is within ~1 s of the car ahead and can’t pass", "~0.2–0.5 s/lap (stretch: model DRS overtakes)"],
  ],
  [2400, 3360, 3600],
));
add(P("The undercut and overcut fall out of this model naturally rather than being hard-coded: a car that pits early gets fresh-tyre pace (worth ~1.5–2 s on the out-lap) while rivals are still on worn rubber, so it can leapfrog them through the pit cycle. That emergent behaviour is the satisfying part — and a great thing to explain to an interviewer.", { }));
add(H2("Model parameters & calibration"));
add(P("Degradation rates, compound offsets and pit loss are stored as a per-circuit configuration. v1 ships with hand-tuned defaults; the stretch goal is to fit these parameters automatically from real FastF1 stint data (linear regression of lap time against tyre age per stint), so the model self-calibrates per track. Validating the simulated finishing order against the actual race result is both a correctness check and a compelling portfolio talking point."));

// 4. Architecture & stack
add(H1("4. Architecture & Stack"));
add(P("Three components, deliberately chosen to show range while staying within tools you already know plus one or two worth learning:"));
add(table(
  ["Layer", "Choice", "Why"],
  [
    ["Front-end", "React + TypeScript + Vite, charts via Recharts or D3", "Your core stack; interactive viz is the showcase"],
    ["API", "Python + FastAPI", "Lives next to the simulation/data code; clean typed endpoints"],
    ["Simulation engine", "Pure Python module (NumPy)", "Testable in isolation; the “interesting” core"],
    ["Data ingestion", "FastF1 (cached to local files / SQLite)", "Free, no API key, real timing & tyre data"],
    ["Persistence", "SQLite (or Postgres if you want parity with your other projects)", "Store races, baseline data, saved strategies"],
    ["Deployment", "Front-end on Vercel; API on Render/Fly.io/Railway", "Public live URL — non-negotiable for portfolio"],
  ],
  [2100, 3400, 3860],
));
add(P("Keep the simulation engine completely decoupled from the web layer: it takes a race configuration and a strategy in, and returns a lap-by-lap result out. That separation makes it unit-testable and is exactly the kind of clean boundary interviewers like to see."));

// 5. Data
add(H1("5. Data Sources"));
add(new Paragraph({ spacing: { after: 120 }, children: [
  new TextRun("FastF1 is the backbone. It is a free, open-source Python package (no API key) covering 2018–present, exposing data as pandas DataFrames. Docs: "),
  new ExternalHyperlink({ children: [new TextRun({ text: "docs.fastf1.dev", style: "Hyperlink" })], link: "https://docs.fastf1.dev/" }),
  new TextRun("."),
]}));
add(P("From each session you can pull what the simulator needs:"));
add(bullet("Lap times, sector times, and stint numbers per driver."));
add(bullet("Tyre compound and tyre life (age in laps) for every lap — the raw material for fitting degradation curves."));
add(bullet("Pit in/out times to measure real pit-lane loss per circuit."));
add(bullet("Starting grid and final classification for validating the simulation."));
add(bullet("Weather and full 30 Hz car telemetry (speed/throttle/brake/gear/position) — optional, useful for a richer track-map view."));
add(P("Cache aggressively: FastF1 downloads can be slow, so fetch once into a local cache/SQLite table and serve the simulator from there.", { }));

// 6. Milestones
add(H1("6. Milestones (3–4 weeks)"));
add(P("Sequenced so you always have something demoable. Ship the engine first (correctness), then the interface (polish)."));
add(table(
  ["Week", "Focus", "Deliverable"],
  [
    ["1", "Data + engine core", "FastF1 ingestion into SQLite; pure-Python lap loop with tyre deg, fuel, compound offset, pit loss; unit tests on the engine"],
    ["2", "API + baseline accuracy", "FastAPI endpoints (list races, get baseline, run strategy); calibrate parameters so simulated order roughly matches a real race"],
    ["3", "Front-end interaction", "React timeline with draggable pit stops, compound picker, live gap chart; instant re-simulation"],
    ["4", "Compare mode, polish, deploy", "Strategy A/B compare, summary panel, responsive UI, README/case study, deploy to live URL"],
  ],
  [900, 2860, 5600],
));

// 7. Stretch
add(H1("7. Stretch Goals"));
add(bullet([...labelRun("Auto-calibration: ", "fit degradation and compound offsets from real stint data via regression, per circuit.")]));
add(bullet([...labelRun("Monte Carlo: ", "add randomness (safety cars, pit-stop variance, lap-time noise) and run thousands of simulations to report win probability per strategy.")]));
add(bullet([...labelRun("Safety car / VSC events: ", "model the pit-loss discount during a neutralisation — the single biggest strategic swing in real F1.")]));
add(bullet([...labelRun("Optimal-strategy solver: ", "search the space of pit laps/compounds to recommend the fastest strategy, not just evaluate the user’s.")]));
add(bullet([...labelRun("Track-map replay: ", "animate car positions on the real circuit outline using FastF1 telemetry coordinates.")]));

// 8. Portfolio angle
add(H1("8. Portfolio & Interview Angle"));
add(P("Present it as a case study on your site, in the same problem → built → stack format you already use for Wardrobe AI. Lead with a 30–60 second screen-recorded demo dragging a pit stop and watching the order change."));
add(P("Talking points to prepare:"));
add(bullet("How the undercut emerges from the model instead of being hard-coded — shows you understand the system, not just the sport."));
add(bullet("How you validated the simulation against real race results, and where it diverges and why."));
add(bullet("The decision to decouple the engine from the API, and how that made it unit-testable."));
add(bullet("Trade-offs in the degradation model: linear vs. piecewise, and why you chose what you chose."));
add(P("One sentence for the README / your CV: “A lap-by-lap F1 race strategy simulator built on real timing data, with an interactive React front-end where moving a single pit stop re-orders the whole field.”", { italics: true }));

// 9. Risks
add(H1("9. Risks & Gotchas"));
add(table(
  ["Risk", "Mitigation"],
  [
    ["Scope creep — the model can grow forever", "Freeze v1 model to the six components in §3; everything else is a stretch goal"],
    ["FastF1 downloads are slow / flaky", "Cache to SQLite on first fetch; never hit FastF1 live from the API"],
    ["Simulation feels “off” vs. reality", "Calibrate against one known race early (week 2), not at the end"],
    ["Front-end interaction complexity (drag + live re-sim)", "Start with a simple lap-number input before building drag-and-drop"],
    ["Deployment friction (Python API hosting)", "Pick a host with a free tier and Docker support early; deploy a hello-world in week 2"],
  ],
  [3800, 5560],
));

// 10. Getting started
add(H1("10. First Steps"));
add(num("Install FastF1 (pip install fastf1), pull one race into a notebook, and plot real lap times by stint — this confirms the data shape before you build anything."));
add(num("Write the pure-Python lap loop for a single car with tyre deg + fuel only. Print the lap times. No web, no DB yet."));
add(num("Add multiple cars and pit stops; verify an early pit can undercut a rival."));
add(num("Only then wrap it in FastAPI and start the React timeline."));
add(new Paragraph({ spacing: { before: 200, after: 0 }, border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 6 } },
  children: [new TextRun({ text: "Build the engine until it is correct, then build the interface until it is beautiful. Ship it live, and write the case study. That sequence is what turns this into a job.", italics: true, color: GREY })] }));

// ---------- assemble ----------
const doc = new Document({
  styles, numbering,
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "PitWall — Project Specification   ·   ", color: GREY, size: 16 }),
                 new TextRun({ children: [PageNumber.CURRENT], color: GREY, size: 16 })] })] }) },
    children: [...titlePage, ...toc, ...body],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("PitWall_F1_Strategy_Simulator_Spec.docx", buf);
  console.log("written");
});
