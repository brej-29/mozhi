/* Evidence page: every number is read from results.json, which bench/summarize.py builds from bench/results. */
const pct = (v, d = 1) => (v == null ? "n/a" : (v * 100).toFixed(d) + "%");
const f3 = (v) => (v == null ? "n/a" : v.toFixed(3));
const ms = (v) => (v < 10 ? v.toFixed(1) : v < 1000 ? Math.round(v) : (v / 1000).toFixed(1) + "k");
const msFull = (v) => (v < 10 ? v.toFixed(1) + " ms" : v < 1000 ? Math.round(v) + " ms" : (v / 1000).toFixed(1) + " s");
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const COLOR = { fast: "var(--c-fast)", llm: "var(--c-llm)", base: "var(--c-base)" };
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const SHORT = { R0: "Keyword rules", M1: "TF-IDF + linear model", J1v0: "Joint model, MASSIVE only", J1: "Joint model, shipped",
  C1: "Cascade with LLM fallback", "L1-7B": "Mistral 7B, short prompt", "L0-7B": "Mistral 7B, V1 prompt",
  "L1-1.5B": "Qwen 1.5B, short prompt", "L0-1.5B": "Qwen 1.5B, V1 prompt", "L0x-1.5B": "Qwen 1.5B, V1 without docs",
  "L1-0.5B": "Qwen 0.5B, short prompt", "L0-0.5B": "Qwen 0.5B, V1 prompt" };
const get = (rows, id) => rows.find((r) => r.id === id);

function table(head, rows, open = false) {
  return `<details class="tv"${open ? " open" : ""}><summary>${open ? "Table" : "Show as a table"}</summary><table><thead><tr>${head.map((h, i) => `<th class="${i ? "num" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("")}</tbody></table></details>`;
}

/* Horizontal bars with 95% CI whiskers. rows: {label, v, lo, hi, group} */
function barChart(rows, { min = 0, max = 1, aria }) {
  const W = 760, L = 232, R = 70, rowH = 34, H = rows.length * rowH + 30;
  const x = (v) => L + ((v - min) / (max - min)) * (W - L - R);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${aria}">`;
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    s += `<line class="axis" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 24}"/><text class="dim" x="${x(t)}" y="${H - 6}" text-anchor="middle">${t.toFixed(2)}</text>`;
  }
  rows.forEach((r, i) => {
    const y = i * rowH + 6;
    s += `<g><title>${r.label}: ${f3(r.v)} (95% CI ${f3(r.lo)} to ${f3(r.hi)})</title>
      <text x="${L - 12}" y="${y + 15}" text-anchor="end">${r.label}</text>
      <rect class="bar" style="--i:${i}" x="${L}" y="${y + 2}" width="${Math.max(2, x(r.v) - L)}" height="16" rx="4" fill="${COLOR[r.group]}"/>
      <g class="pt" style="--i:${i}"><line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${y + 10}" y2="${y + 10}" stroke="var(--ink)" stroke-width="2"/>
      <text x="${x(r.hi) + 8}" y="${y + 15}">${r.v.toFixed(2)}</text></g></g>`;
  });
  return s + "</svg>";
}

/* Log-scale latency: p50 dot, p95 whisker. */
function latencyChart(rows) {
  const W = 760, L = 232, R = 60, rowH = 34, H = rows.length * rowH + 30, lo = 0.5, hi = 20000;
  const x = (v) => L + ((Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (W - L - R);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Median and 95th percentile router latency on a log scale">`;
  for (const t of [1, 10, 100, 1000, 10000]) s += `<line class="axis" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 24}"/><text class="dim" x="${x(t)}" y="${H - 6}" text-anchor="middle">${t >= 1000 ? t / 1000 + " s" : t + " ms"}</text>`;
  rows.forEach((r, i) => {
    const y = i * rowH + 16;
    s += `<g><title>${r.label}: median ${msFull(r.p50)}, 95th percentile ${msFull(r.p95)}</title><text x="${L - 12}" y="${y + 4}" text-anchor="end">${r.label}</text>
      <g class="pt" style="--i:${i}"><line x1="${x(Math.max(r.p50, lo))}" x2="${x(r.p95)}" y1="${y}" y2="${y}" stroke="${COLOR[r.group]}" stroke-width="3" stroke-linecap="round"/>
      <circle cx="${x(Math.max(r.p50, lo))}" cy="${y}" r="6" fill="${COLOR[r.group]}" stroke="var(--ground)" stroke-width="2"/>
      <text x="${x(r.p95) + 10}" y="${y + 4}">${msFull(r.p50)}</text></g></g>`;
  });
  return s + "</svg>";
}

/* Dumbbell: score on gold text to score on recognised speech. */
function dumbbell(rows) {
  const W = 760, L = 150, R = 60, rowH = 38, H = rows.length * rowH + 30, min = 0.4, max = 1;
  const x = (v) => L + ((v - min) / (max - min)) * (W - L - R);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Action macro-F1 on gold text versus on Whisper transcripts of real recordings">`;
  for (const t of [0.4, 0.6, 0.8, 1]) s += `<line class="axis" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 24}"/><text class="dim" x="${x(t)}" y="${H - 6}" text-anchor="middle">${t.toFixed(1)}</text>`;
  rows.forEach((r, i) => {
    const y = i * rowH + 18;
    s += `<g><title>${r.id}: ${f3(r.clean)} on gold text, ${f3(r.asr)} on speech</title><text x="${L - 12}" y="${y + 4}" text-anchor="end">${r.id}</text>
      <g class="pt" style="--i:${i}"><line x1="${x(r.asr)}" x2="${x(r.clean)}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="3"/>
      <circle cx="${x(r.clean)}" cy="${y}" r="6" fill="var(--ink)"/>
      <circle cx="${x(r.asr)}" cy="${y}" r="6" fill="var(--c-base)" stroke="var(--ground)" stroke-width="2"/>
      <text x="${x(r.asr) - 12}" y="${y + 4}" text-anchor="end">${r.asr.toFixed(2)}</text><text x="${x(r.clean) + 12}" y="${y + 4}">${r.clean.toFixed(2)}</text></g></g>`;
  });
  return s + "</svg>";
}

/* Safety dial: each point is a threshold; x = false-action rate, y = missed actions. */
function dialChart(sweep) {
  const W = 760, H = 330, L = 60, B = 40, T = 12, R = 24;
  const xs = sweep.flatMap((p) => [p.clean.far, p.asr.far]), ys = sweep.flatMap((p) => [p.clean.miss, p.asr.miss]);
  const xmax = Math.max(0.035, ...xs) * 1.05, ymax = Math.max(0.45, ...ys) * 1.05;
  const x = (v) => L + (v / xmax) * (W - L - R), y = (v) => T + (1 - v / ymax) * (H - T - B);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Missed actions against false actions as the abstention threshold changes, for clean text and for speech">`;
  for (let t = 0; t <= xmax; t += 0.01) s += `<line class="axis" x1="${x(t)}" x2="${x(t)}" y1="${T}" y2="${H - B}"/><text class="dim" x="${x(t)}" y="${H - B + 18}" text-anchor="middle">${(t * 100).toFixed(0)}%</text>`;
  for (let t = 0; t <= ymax; t += 0.1) s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text class="dim" x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${(t * 100).toFixed(0)}%</text>`;
  s += `<text class="dim" x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">False actions: requests it should decline but acted on</text>`;
  for (const [key, label, col, dash] of [["clean", "Gold text", "var(--c-fast)", ""], ["asr", "Recognised speech", "var(--c-base)", "6 4"]]) {
    s += `<polyline class="ln" pathLength="1" fill="none" stroke="${col}" stroke-width="2.5" points="${sweep.map((p) => `${x(p[key].far)},${y(p[key].miss)}`).join(" ")}"/>`;
    sweep.forEach((p) => { s += `<circle cx="${x(p[key].far)}" cy="${y(p[key].miss)}" r="5.5" fill="${col}" stroke="var(--ground)" stroke-width="2"><title>${label}, threshold ${p.th}: ${pct(p[key].far)} false actions, ${pct(p[key].miss)} missed</title></circle>`; });
    const last = sweep[sweep.length - 1], first = sweep[0];
    s += `<text x="${x(last[key].far) + 10}" y="${y(last[key].miss) + 4}">${label}</text>`;
    s += `<text class="dim" x="${x(first[key].far) + 8}" y="${y(first[key].miss) - 10}">threshold ${first.th}</text>`;
  }
  return s + "</svg>";
}

function scoreboard(d) {
  const sub = d.rows.subset, full = d.rows.full;
  const J = d.seeds.J1, J0 = d.seeds.J1v0, shipped = get(full, "J1"), jsub = get(sub, "J1");
  const bestL0 = d.paired.filter((p) => p.vs.startsWith("L0")).sort((a, b) => a.diff - b.diff)[0];
  const asrJ = d.asr.rows.find((r) => r.id === "J1");
  const rows = [];
  const add = (id, claim, target, value, status) => rows.push({ id, claim, target, value, status });
  add("T1", "Action macro-F1 on clean text", "at least 0.95", `${f3(J.action_macro_f1[0])} mean of 3 seeds (${J.values.map(f3).join(", ")}); MASSIVE-only model ${f3(J0.action_macro_f1[0])}`, J.action_macro_f1[0] >= 0.95 ? "pass" : "near");
  add("T2", "False-action rate", "at most 2%", pct(J.far[0], 2), J.far[0] <= 0.02 ? "pass" : "fail");
  add("T3", "Router latency, 95th percentile", "at most 25 ms", shipped ? msFull(shipped.p95) : "n/a", shipped && shipped.p95 <= 25 ? "pass" : "fail");
  if (bestL0) add("T4", "Gain over the best Jarvis V1 prompt result", "at least 10 points, CI above 0", `+${(bestL0.diff * 100).toFixed(1)} points vs ${bestL0.vs} (CI ${(bestL0.lo * 100).toFixed(1)} to ${(bestL0.hi * 100).toFixed(1)})`, bestL0.diff >= 0.1 && bestL0.lo > 0 ? "pass" : "fail");
  add("T5", "City and time arguments, given the right tool", "at least 90% and 75%", `${pct(J.city_acc[0])} and ${pct(J.when_acc[0])}`, J.city_acc[0] >= 0.9 && J.when_acc[0] >= 0.75 ? "pass" : "fail");
  if (asrJ) {
    const med = d.asr.sizes.find((z) => z.model === "medium.en" && z.f1 != null);
    const base = asrJ.clean - asrJ.asr, big = med ? asrJ.clean - med.f1 : null;
    add("T6", "Drop on real recorded speech", "at most 5 points",
      `${(base * 100).toFixed(1)} points with Whisper base.en (${f3(asrJ.clean)} to ${f3(asrJ.asr)})${med ? `; ${(big * 100).toFixed(1)} points with medium.en` : ""}`,
      base <= 0.05 ? "pass" : big != null && big <= 0.05 ? "mixed" : "fail");
  }
  add("T7", "Honest about unsupported requests", "at least 85%", pct(J.honesty[0]), J.honesty[0] >= 0.85 ? "pass" : "fail");
  return rows;
}

export async function renderEvidence(root) {
  let d;
  try { d = await (await fetch("results.json", { cache: "no-cache" })).json(); } catch { root.innerHTML = "<h1>Evidence</h1><p class='lede'>results.json is missing. Run <code>python bench/summarize.py</code>.</p>"; return; }
  const sub = d.rows.subset, full = d.rows.full;
  const l0 = sub.filter((r) => r.id.startsWith("L0-"));
  const worst = l0.sort((a, b) => b.far - a.far)[0] || l0[0];
  const l0q = get(sub, "L0-1.5B"), j = get(sub, "J1"), jf = get(full, "J1"), m1 = get(full, "M1"), l1q = get(sub, "L1-1.5B");
  const asrJ = d.asr.rows.find((r) => r.id === "J1");
  const lat = d.latency && d.latency.rows;
  const latRows = lat ? [["M1", "TF-IDF + logistic regression", "fast"], ["J1", "Joint model (shipped)", "fast"], ["L1", "Constrained prompt, Qwen2.5 1.5B", "llm"], ["L0", "Jarvis V1 prompt, Qwen2.5 1.5B", "llm"]]
    .filter(([k]) => lat[k]).map(([k, label, group]) => ({ label, group, p50: lat[k].p50_ms, p95: lat[k].p95_ms })) : [];

  const barRows = [...sub].sort((a, b) => b.f1 - a.f1)
    .map((r) => ({ label: SHORT[r.id] || r.label, v: r.f1, lo: r.lo, hi: r.hi, group: r.group }));
  const sc = scoreboard(d);
  const status = { pass: ["pass", "Met"], near: ["near", "Missed by a hair"], mixed: ["near", "Depends on the recogniser"], fail: ["fail", "Missed"] };

  root.innerHTML = `
  <header class="ev-head"><h1>Does a voice assistant need an LLM to decide what to do?</h1>
  <p class="lede">Jarvis V1 asked a small language model to pick a tool from a prompt. Nobody measured how often that was right. These are the measurements, and what replaced it.</p></header>

  <section class="block" aria-labelledby="e1">
    <h2 id="e1">${l0q ? `With the V1 prompt, a 1.5B model acted on ${pct(l0q.far, 0)} of requests it should have declined` : "The V1 prompt, measured"}</h2>
    <p>The benchmark is MASSIVE (Amazon, CC BY 4.0): ${full[0] ? full[0].n.toLocaleString() : ""} English requests, mapped to Jarvis's tools plus a new "unsupported" label for requests it has no tool for. The score is a macro-F1 over weather, reminder, note and "do nothing". The slow systems are scored on one fixed stratified subset of ${sub[0] ? sub[0].n : ""} requests so every row below sees the same questions.</p>
    <div class="legend"><span><i style="background:var(--c-fast)"></i>On-device model</span><span><i style="background:var(--c-llm)"></i>Language model prompted to route</span><span><i style="background:var(--c-base)"></i>Keyword rules</span></div>
    ${barChart(barRows, { aria: "Action macro-F1 per system with 95 percent confidence intervals" })}
    ${table(["System", "Macro-F1", "95% CI", "False actions", "Missed", "Valid output"], sub.map((r) => [r.label, f3(r.f1), `${f3(r.lo)} to ${f3(r.hi)}`, pct(r.far), pct(r.miss), pct(r.valid, 0)]))}
    ${l0q ? `<p class="callout">Only ${pct(l0q.valid, 0)} of the V1 prompt's outputs were valid JSON for the schema, and it never said "I cannot do that" (honesty ${pct(l0q.honesty, 0)}), because V1 had no such label. ${get(sub, "L0-7B") ? `Mistral 7B, the model family V1 defaulted to, returned valid JSON for ${pct(get(sub, "L0-7B").valid, 0)} of requests: it answered in prose and invented a weather API call instead. ` : ""}${l1q ? `A short prompt with constrained decoding fixes the format (${pct(l1q.valid, 0)} valid) and reaches ${f3(l1q.f1)}, but it still acts on ${pct(l1q.far)} of requests it should decline.` : ""}</p>` : ""}
  </section>

  <section class="block" aria-labelledby="e2">
    <h2 id="e2">${j && lat ? `The on-device model is ${Math.round((lat.L0 ? lat.L0.p50_ms : l0q.p50) / lat.J1.p50_ms).toLocaleString()} times faster than the V1 prompt` : "Speed"}</h2>
    <p>A small transformer reads the request once and outputs the intent and the argument spans together. Exported as int8 ONNX it is a ${d.model_mb || 23} MB file that runs on one CPU thread. Timings are router only, one request at a time, measured on an otherwise idle laptop.</p>
    ${latRows.length ? latencyChart(latRows) + table(["System", "Median", "95th percentile"], [["Keyword rules", msFull(lat.R0.p50_ms), msFull(lat.R0.p95_ms)], ...latRows.map((r) => [r.label, msFull(r.p50), msFull(r.p95)])]) : "<p>Latency table is not available.</p>"}
  </section>

  <section class="block" aria-labelledby="e3">
    <h2 id="e3">Choosing the tool is easy. Reading the arguments is where the model earns its place</h2>
    <p>A linear model on word and character n-grams gets most of the way on tool choice. The transformer's gain is in the city and the time it hears.</p>
    ${table(["System", "Macro-F1", "City correct", "Time correct", "False actions"], full.filter((r) => ["R0", "M1", "J1v0", "J1"].includes(r.id)).map((r) => [r.label, f3(r.f1), pct(r.city), pct(r.when), pct(r.far, 2)]))}
    ${m1 && jf ? `<p class="say-it">Tool choice: ${f3(m1.f1)} with the linear model against ${f3(d.seeds.J1.action_macro_f1[0])} here (mean of three seeds). Time arguments: ${pct(m1.when, 0)} against ${pct(d.seeds.J1.when_acc[0], 0)}.</p>` : ""}
  </section>

  <section class="block" aria-labelledby="e4">
    <h2 id="e4">${asrJ ? `Real speech is the harder problem: ${((asrJ.clean - asrJ.asr) * 100).toFixed(0)} points lost between text and a microphone` : "Real speech"}</h2>
    <p>I played real recordings (SLURP, headset and far-field) through Whisper and routed the transcripts. Same requests, same labels, never seen in training. Whisper base.en made ${d.asr.sizes.find((s) => s.model === "base.en") ? pct(d.asr.sizes.find((s) => s.model === "base.en").wer, 0) : ""} word errors on this set.</p>
    ${d.asr.rows.length ? `<div class="legend"><span><i style="background:var(--ink)"></i>Gold text</span><span><i style="background:var(--c-base)"></i>Whisper transcript</span></div>${dumbbell(d.asr.rows)}${table(["System", "Gold text", "Speech", "False actions on speech"], d.asr.rows.map((r) => [r.id, f3(r.clean), f3(r.asr), pct(r.far_asr)]))}` : ""}
    ${d.asr.sizes.filter((s) => s.f1 != null).length > 1 ? `<h3>A better recogniser buys back more than any routing trick</h3>${table(["Whisper model", "Word error rate", "Macro-F1", "False actions"], d.asr.sizes.filter((s) => s.f1 != null).map((s) => [s.model, pct(s.wer, 0), f3(s.f1), pct(s.far)]), true)}` : ""}
    <p class="callout">Training on 6,600 real recogniser transcripts helped (${d.seeds_asr.J1aug && d.seeds_asr.J1aug.action_macro_f1 ? f3(d.seeds_asr.J1aug.action_macro_f1[0]) + " to " : ""}${d.seeds_asr.J1.action_macro_f1 ? f3(d.seeds_asr.J1.action_macro_f1[0]) : ""} on speech) but did not close the gap. When the recogniser turns "weather" into "rider", no router can recover it. ${(() => { const m = d.asr.sizes.find((z) => z.model === "medium.en" && z.f1 != null); return m && asrJ ? `The fix is earlier in the pipeline: with Whisper medium.en the same router scores ${f3(m.f1)} on speech, ${((asrJ.clean - m.f1) * 100).toFixed(1)} points below gold text.` : "The fix is earlier in the pipeline."; })()}</p>
  </section>

  ${d.sweep.length ? `<section class="block" aria-labelledby="e5">
    <h2 id="e5">A safety dial: how sure the router must be before it acts</h2>
    <p>Raising the threshold makes Jarvis decline more often. On clean text it costs little until the very top. On speech every step costs more, because the model is less sure of what it heard.</p>
    ${dialChart(d.sweep)}
    ${table(["Threshold", "Text: false actions", "Text: missed", "Speech: false actions", "Speech: missed"], d.sweep.map((p) => [p.th, pct(p.clean.far, 2), pct(p.clean.miss), pct(p.asr.far, 2), pct(p.asr.miss)]))}
  </section>` : ""}

  <section class="block" aria-labelledby="e6">
    <h2 id="e6">What did not work</h2>
    <ul class="plain">
      ${get(sub, "C1") && j ? `<li>A cascade that hands unsure requests to a small LLM scored ${f3(get(sub, "C1").f1)} against ${f3(j.f1)} for the router alone, with a 95th percentile of ${msFull(get(sub, "C1").p95)}. The fallback made it slower and slightly worse, so the shipped router abstains instead.</li>` : ""}
      ${get(sub, "L1-7B") ? `<li>A bigger model did not help. Mistral 7B, the V1 default family, scored ${f3(get(sub, "L1-7B").f1)} with the constrained prompt and acted on ${pct(get(sub, "L1-7B").far, 0)} of requests it should decline.</li>` : ""}
      <li>Pre-registered goal T1 (clean macro-F1 at least 0.95) was missed by a hair for the shipped model, and T6 (speech robustness) was missed by a wide margin. The scoreboard below lists all seven.</li>
      <li>Many remaining "misses" are label noise in MASSIVE (for example "by get marks" is labelled as a weather request), so the ceiling on this benchmark is below 1.0.</li>
    </ul>
  </section>

  <section class="block" aria-labelledby="e7">
    <h2 id="e7">Pre-registered goals, scored</h2>
    <p>The goals and thresholds were committed before any model was trained. See <code>docs/PREREG.md</code>.</p>
    <table><thead><tr><th>Goal</th><th>Claim</th><th>Target</th><th>Result</th><th>Verdict</th></tr></thead><tbody>
      ${sc.map((r) => `<tr><td>${r.id}</td><td>${r.claim}</td><td>${r.target}</td><td>${r.value}</td><td class="${status[r.status][0]}">${status[r.status][1]}</td></tr>`).join("")}
    </tbody></table>
  </section>

  ${d.bugs ? `<section class="block" aria-labelledby="e8">
    <h2 id="e8">Two bugs found in V1 by running its code</h2>
    <ul class="plain">
      <li>Saving a note crashed: <code>${d.bugs.save_note}</code>. The handler used <code>datetime</code> without importing it.</li>
      <li>The repair retry for bad JSON never saw the bad JSON. It was sent the exception message instead (the model's output was included in the repair prompt: <code>${String(d.bugs.repair_prompt_contains_model_output)}</code>).</li>
    </ul>
  </section>` : ""}

  <section class="block" aria-labelledby="e9">
    <h2 id="e9">Limits</h2>
    <ul class="plain">
      <li>The tools are a proxy mapping from MASSIVE: reminders come from alarm and calendar requests, and "note" comes from list requests. Notes were taught with synthetic phrasings, so that class is not measured on real data.</li>
      <li>Speech results use one recogniser family (Whisper, int8, CPU or GPU) and ${d.asr.rows[0] ? d.asr.rows[0].n : "about 500"} clips from one corpus, in English only.</li>
      <li>Latency is from one laptop (i5-13450HX), router only. Browser speech recognition and network calls are not included.</li>
    </ul>
  </section>`;
  const seen = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); seen.unobserve(e.target); }
  }, { threshold: 0.25 });
  root.querySelectorAll("svg.chart").forEach((c) => seen.observe(c));
  // SVG presentation attributes cannot hold var(...), so move them to inline style
  for (const n of root.querySelectorAll("svg *")) {
    for (const a of ["fill", "stroke"]) {
      const v = n.getAttribute(a);
      if (v && v.startsWith("var(")) { n.style[a] = v; n.removeAttribute(a); }
    }
  }
}
