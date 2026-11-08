/* Run from the repo root: node bench/j2_browser_check.mjs
   Builds Pages, refreshes Python references, and compares actual Edge WASM output.
   --prepared --saved checks an already prepared site against the saved J2 snapshot.
   --site DIR selects the build directory. EDGE_EXECUTABLE can select a system install. */
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";

const root = process.cwd(), args = process.argv.slice(2);
const site = path.resolve(args.includes("--site") ? args[args.indexOf("--site") + 1] : ".site_build");
const prepared = args.includes("--prepared"), saved = args.includes("--saved");
function python(argv) {
  const result = spawnSync(path.join(root, ".venv/Scripts/python.exe"), argv, {
    cwd: root, encoding: "utf8", windowsHide: true, env: { ...process.env, PYTHONPATH: root },
  });
  if (result.error || result.status !== 0) throw new Error(result.error?.message || result.stderr || result.stdout);
  console.log(result.stdout.trim());
}
if (!prepared) python(["packaging/build_pages.py", site]);
if (!saved) python(["bench/j2_browser_dump.py", path.join(site, "python_parity.json")]);
const rows = saved
  ? fs.readFileSync(path.join(root, "bench/results/j2_parity.jsonl"), "utf8").trim().split("\n").map(JSON.parse)
  : JSON.parse(fs.readFileSync(path.join(site, "python_parity.json"), "utf8"));
for (const lang of ["en", "ta", "ml"]) assert.equal(rows.filter((r) => r.lang === lang).length, 600);
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(root, ".venv/Lib/site-packages/playwright/driver/package/index.js")); }
const mime = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".wasm": "application/wasm" };
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  if (pathname === "/demo/__parity__.html") {
    response.setHeader("Content-Type", "text/html");
    response.end('<!doctype html><script src="config.js"></script>'); return;
  }
  const file = path.resolve(site, pathname.replace(/^\/demo\//, ""));
  if (!file.startsWith(site + path.sep)) { response.writeHead(403).end(); return; }
  try { response.setHeader("Content-Type", mime[path.extname(file)] || "application/octet-stream"); response.end(fs.readFileSync(file)); }
  catch { response.writeHead(404).end(); }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  const systemEdge = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
  const executablePath = process.env.EDGE_EXECUTABLE || (fs.existsSync(systemEdge) ? systemEdge : undefined);
  browser = await playwright.chromium.launch({ channel: "msedge", executablePath, headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:' + server.address().port + '/demo/__parity__.html');
  const init = await page.evaluate(async () => {
    window.engine = await import("./engine.js");
    const health = await window.engine.health();
    const module = await import("./router2.js");
    window.j2 = await module.loadRouter2(window.ort);
    return { health, static: window.engine.STATIC };
  });
  assert.equal(init.static, true);
  assert.deepEqual(init.health.tools, ["GENERAL_QA", "NEWS", "SAVE_NOTE", "SET_REMINDER", "STORY", "UNSUPPORTED", "VERSE", "WEATHER"]);
  const checked = [];
  for (let start = 0; start < rows.length; start += 100) {
    const part = await page.evaluate(async (batch) => {
      const results = [];
      for (const row of batch) results.push({ ...row, j2_browser: await window.j2.route(row.text), dispatched_browser: await window.engine.routeOnly(row.text) });
      return results;
    }, rows.slice(start, start + 100));
    checked.push(...part);
  }
  const disagreements = checked.filter((r) => r.j2_browser.tool !== r.python_tool)
    .map((r) => ({ lang: r.lang, index: r.index, text: r.text, python: r.python_tool, browser: r.j2_browser.tool }));
  const dispatchDisagreements = checked.filter((r) => r.server_route && r.dispatched_browser.tool !== r.server_route.tool)
    .map((r) => ({ lang: r.lang, index: r.index, text: r.text, python: r.server_route.tool, browser: r.dispatched_browser.tool }));
  const slotDisagreements = checked.filter((r) => r.j2_route && ["args", "spans", "intent", "path"].some((key) => JSON.stringify(r.j2_browser[key]) !== JSON.stringify(r.j2_route[key])))
    .map((r) => ({ lang: r.lang, index: r.index, text: r.text, python: r.j2_route, browser: r.j2_browser }));
  let nativeDispatchChecked = 0;
  for (const row of checked) {
    if (/[\u0b80-\u0bff\u0d00-\u0d7f]/u.test(row.text)) {
      assert.deepEqual(row.dispatched_browser.words, row.j2_browser.words);
      assert.equal(row.dispatched_browser.tool, row.j2_browser.tool);
      assert.deepEqual(row.dispatched_browser.args, row.j2_browser.args);
      assert.deepEqual(row.dispatched_browser.spans, row.j2_browser.spans);
      nativeDispatchChecked++;
    }
    for (const result of [row.j2_browser, row.dispatched_browser]) {
      assert.deepEqual(Object.keys(result.scores).sort(), init.health.tools);
      assert.ok(Number.isFinite(result.ms));
      assert.ok(Object.values(result.scores).every((p) => Number.isFinite(p) && p >= 0 && p <= 1));
      assert.ok(Math.abs(Object.values(result.scores).reduce((a, b) => a + b, 0) - 1) < 0.001);
    }
    assert.deepEqual(row.j2_browser.words, row.words);
  }
  // Exercise chat and native geocoding without depending on a live weather service.
  const weatherChecks = [];
  for (const [lang, city] of [["ta", "சென்னை"], ["ml", "കൊച്ചി"]]) {
    let geoURL;
    await page.route("https://geocoding-api.open-meteo.com/**", async (route) => {
      geoURL = route.request().url();
      await route.fulfill({ json: { results: [{ name: city, latitude: 10, longitude: 76, country: "India" }] } });
    });
    await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: {
      current: { temperature_2m: 28, weather_code: 0 }, daily: { temperature_2m_min: [24], temperature_2m_max: [30] },
    } }));
    const sample = checked.find((r) => r.lang === lang && r.dispatched_browser.tool === "WEATHER");
    assert.ok(sample, "weather sample for " + lang);
    // The city slot may be empty or another location. The default-city path is
    // exercised with a weather request whose extracted city is empty if available.
    const probe = checked.find((r) => r.lang === lang && r.dispatched_browser.tool === "WEATHER" && !r.dispatched_browser.args.city) || sample;
    const response = await page.evaluate(async ({ text, city }) => window.engine.chat({ text, default_city: city, native: false }), { text: probe.text, city });
    assert.equal(response.action.type, "weather");
    const query = new URL(geoURL).searchParams;
    assert.equal(query.get("language"), lang);
    assert.equal(query.get("name"), response.route.args.city || city);
    weatherChecks.push({ lang, query: Object.fromEntries(query), tool: response.route.tool, action: response.action.type });
    await page.unroute("https://geocoding-api.open-meteo.com/**");
    await page.unroute("https://api.open-meteo.com/**");
  }
  assert.deepEqual(errors, []);
  const result = {
    browser: "Playwright msedge " + browser.version(),
    pages_build: prepared ? "unverified: used a prepared directory" : "packaging/build_pages.py executed",
    reference: saved ? "saved Python JointRouter2 decisions in j2_parity.jsonl" : "fresh Python J2 and J1 dispatch",
    by_language: Object.fromEntries(["en", "ta", "ml"].map((lang) => {
      const total = checked.filter((r) => r.lang === lang).length, agree = total - disagreements.filter((r) => r.lang === lang).length;
      return [lang, { agree, total, percent: 100 * agree / total }];
    })),
    disagreements,
    native_dispatch_matches_direct_j2: nativeDispatchChecked,
    dispatch: saved ? "unverified: fresh J1 reference unavailable" : { checked: checked.length, disagreements: dispatchDisagreements },
    slots: saved ? "unverified: saved reference contains tool decisions only" : { checked: checked.length, disagreements: slotDisagreements },
    weather: { mocked: true, checks: weatherChecks, live_service: "unverified" },
    page_errors: errors,
  };
  fs.writeFileSync(path.join(root, "bench/results/j2_browser.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify(result, null, 2));
  if (Object.values(result.by_language).some((v) => v.percent < 99) || dispatchDisagreements.length || slotDisagreements.length) process.exitCode = 1;
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
