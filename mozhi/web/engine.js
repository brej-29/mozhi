/* One interface for the UI, two backends.
   Server mode (python -m mozhi): calls /api/health and /api/chat.
   Static mode (GitHub Pages, window.MOZHI_STATIC): runs the same int8 ONNX router in the browser. */
import { language, loadRouter2 } from "./router2.js";

export const STATIC = !!window.MOZHI_STATIC;

// third-party code is vendored (see packaging/build_pages.py), so the page loads nothing from other origins
const ORT = new URL("vendor/ort/", document.baseURI).href;
const CHRONO = "./vendor/chrono.js";
const MODEL = "model/";

export async function health() {
  if (!STATIC) return (await fetch("api/health")).json();
  const [r, meta2] = await Promise.all([router(), router2Meta()]);
  const k = byok.get();
  return { status: "ok", threshold: r.meta.threshold, tools: [...new Set([...Object.values(r.meta.tool_of_intent), ...Object.values(meta2.tool_of_intent)])].sort(), llm: k ? { connected: true, model: `${PROVIDERS[k.provider].label} ${k.model}` } : { connected: false } };
}

/* Streaming chat. `on.route(route)` fires as soon as the router has decided, `on.token(text)` for each
   piece of a streamed answer, and the promise resolves with { reply, action, route }. */
export async function chat(body, on = {}) {
  if (!STATIC) {
    const res = await fetch("api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok || !res.body) throw new Error(res.status);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "", route = null, done = null;
    for (;;) {
      const { value, done: end } = await reader.read();
      if (end) break;
      buf += value;
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        const ev = /^event: (\w+)/m.exec(block)?.[1], data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? "null");
        if (ev === "route") { route = data; on.route?.(route); }
        else if (ev === "token") on.token?.(data);
        else if (ev === "done") done = data;
      }
    }
    if (!route || !done) throw new Error("stream ended early");
    return { reply: done.reply, action: done.action, route };
  }
  const route = await routeOnly(body.text);
  on.route?.(route);
  const { reply, action } = await act(route, body, on);
  return { reply, action, route };
}

/* ---------- text normalisation, a port of mozhi/routers/joint.py ---------- */
const SMALL = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(" ");
const TENS = "x x twenty thirty forty fifty sixty seventy eighty ninety".split(" ");
function numWords(n) {
  if (n < 20) return SMALL[n];
  if (n < 100) return TENS[Math.floor(n / 10)] + (n % 10 ? " " + SMALL[n % 10] : "");
  return SMALL[Math.floor(n / 100)] + " hundred" + (n % 100 ? " " + numWords(n % 100) : "");
}
export function clean(text) {
  let t = text.toLowerCase().replace(/-/g, " ");
  t = t.replace(/(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])/g, (_, h, m) => numWords(+h) + (+m === 0 ? "" : +m < 10 ? " oh " + numWords(+m) : " " + numWords(+m)));
  t = t.replace(/(?<![\d.])\d{1,3}(?![\d.])/g, (m) => numWords(+m));
  return t.replace(/[^\p{L}\p{N}_\s']/gu, " ").split(/\s+/).filter(Boolean);
}

/* ---------- BERT WordPiece, matching the HF tokenizer used in training ---------- */
const isPunct = (c) => { const k = c.codePointAt(0); return (k >= 33 && k <= 47) || (k >= 58 && k <= 64) || (k >= 91 && k <= 96) || (k >= 123 && k <= 126) || /\p{P}/u.test(c); };
function wordpiece(piece, vocab) {
  if ([...piece].length > 100) return [vocab["[UNK]"]];
  const out = []; let start = 0; const chars = [...piece];
  while (start < chars.length) {
    let end = chars.length, found = null;
    while (start < end) {
      const s = (start ? "##" : "") + chars.slice(start, end).join("");
      if (s in vocab) { found = vocab[s]; break; }
      end--;
    }
    if (found === null) return [vocab["[UNK]"]];
    out.push(found); start = end;
  }
  return out;
}
function encode(words, vocab) {
  const ids = [vocab["[CLS]"]], first = []; // first[i] = position of word i's first token
  words.forEach((w, wi) => {
    const norm = w.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase();
    const pieces = []; let cur = "";
    for (const c of norm) { if (isPunct(c)) { if (cur) pieces.push(cur); pieces.push(c); cur = ""; } else cur += c; }
    if (cur) pieces.push(cur);
    pieces.forEach((p, pi) => { const toks = wordpiece(p, vocab); if (pi === 0) first[wi] = ids.length; ids.push(...toks); });
  });
  ids.push(vocab["[SEP]"]);
  return { ids, first };
}

const SLOT_TAGS = ["O", "B-CITY", "I-CITY", "B-WHEN", "I-WHEN", "B-TITLE", "I-TITLE"];
function spans(words, tags, kind) {
  const out = []; let cur = [];
  words.forEach((w, i) => {
    const t = tags[i];
    if (t === `B-${kind}`) { if (cur.length) out.push(cur.join(" ")); cur = [w]; }
    else if (t === `I-${kind}` && cur.length) cur.push(w);
    else { if (cur.length) out.push(cur.join(" ")); cur = []; }
  });
  if (cur.length) out.push(cur.join(" "));
  return out;
}

let routerPromise;
function router() { return (routerPromise ||= loadRouter()); }
let router2Promise, router2MetaPromise;
function router2Meta() { return (router2MetaPromise ||= fetch("model2/meta.json").then((r) => r.json())); }
function router2() { return (router2Promise ||= router().then(() => loadRouter2(window.ort))); }
function loadScript(src) { return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => bad(new Error("could not load " + src)); document.head.append(s); }); }

async function loadRouter() {
  await loadScript(ORT + "ort.min.js");
  window.ort.env.wasm.wasmPaths = ORT;
  window.ort.env.wasm.numThreads = 1;
  const [meta, tok, buf] = await Promise.all([
    fetch(MODEL + "meta.json").then((r) => r.json()),
    fetch(MODEL + "tokenizer.json").then((r) => r.json()),
    fetch(MODEL + "model.int8.onnx").then((r) => r.arrayBuffer()),
  ]);
  const session = await window.ort.InferenceSession.create(new Uint8Array(buf), { executionProviders: ["wasm"] });
  const vocab = tok.model.vocab;
  const tools = [...new Set(Object.values(meta.tool_of_intent))].sort();
  const toolIdx = meta.intents.map((n) => tools.indexOf(meta.tool_of_intent[n]));
  const ACTION = ["WEATHER", "SET_REMINDER", "SAVE_NOTE"];

  async function run(words) {
    const { ids, first } = encode(words, vocab);
    const n = ids.length;
    const out = await session.run({
      input_ids: new window.ort.Tensor("int64", BigInt64Array.from(ids.map(BigInt)), [1, n]),
      attention_mask: new window.ort.Tensor("int64", new BigInt64Array(n).fill(1n), [1, n]),
    });
    const il = out.intent_logits.data, sl = out.slot_logits.data, nt = SLOT_TAGS.length;
    const mx = Math.max(...il); const e = Array.from(il, (v) => Math.exp(v - mx)); const z = e.reduce((a, b) => a + b, 0);
    const tp = new Array(tools.length).fill(0); let best = 0;
    e.forEach((v, i) => { tp[toolIdx[i]] += v / z; if (v > e[best]) best = i; });
    const tags = words.map((_, wi) => { const p = first[wi]; let k = 0; for (let j = 1; j < nt; j++) if (sl[p * nt + j] > sl[p * nt + k]) k = j; return SLOT_TAGS[k]; });
    return { tp, tags, intent: meta.intents[best] };
  }

  const api = { meta };
  // route() starts inference and finish() turns its result into a decision
  api.route = (text) => { const words = clean(text); return { words, pending: words.length ? run(words) : null }; };
  api.finish = async (pending) => {
    const words = pending.words;
    if (!words.length) return { tool: "UNSUPPORTED", confidence: 1, intent: "", path: "empty", args: {}, spans: [], scores: Object.fromEntries(tools.map((tool) => [tool, 0])), words };
    const { tp, tags, intent } = await pending.pending;
    let k = 0; tp.forEach((v, i) => { if (v > tp[k]) k = i; });
    const tool = tools[k], conf = tp[k];
    const scores = Object.fromEntries(tools.map((t, i) => [t, Math.round(tp[i] * 1e4) / 1e4]));
    if (ACTION.includes(tool) && conf < meta.threshold) return { tool: "UNSUPPORTED", confidence: conf, intent, path: "abstain", args: {}, spans: [], scores, words };
    const args = {};
    if (tool === "WEATHER") args.city = spans(words, tags, "CITY")[0] || "";
    if (tool === "SET_REMINDER") { args.when = spans(words, tags, "WHEN").join(" "); args.title = spans(words, tags, "TITLE")[0] || ""; }
    const found = ["CITY", "WHEN", "TITLE"].flatMap((K) => spans(words, tags, K).map((t) => ({ kind: K.toLowerCase(), text: t })));
    return { tool, confidence: conf, intent, path: "fast", scores, words, args: Object.fromEntries(Object.entries(args).map(([a, b]) => [a, b])), spans: found };
  };
  return api;
}

/* ---------- tools (ports of mozhi/tools.py) ---------- */
const WMO = { 0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "violent showers", 95: "a thunderstorm", 96: "thunderstorm and hail", 99: "thunderstorm and hail" };
const WORD_NUM = Object.fromEntries("zero one two three four five six seven eight nine ten eleven twelve".split(" ").map((w, i) => [w, String(i)]));
const DAYPART = { morning: "9 am", afternoon: "3 pm", evening: "6 pm", night: "8 pm" };
const MINUTES = { fifteen: "15", thirty: "30", "forty five": "45" };

export function normalizeWhen(text) {
  let t = text.toLowerCase().replaceAll(".", " ");
  t = t.replace(/\b([ap]) m\b/g, "$1m").replace(/\bnext (\w+day)\b/g, "$1");
  t = t.replace(/\bhalf past (\w+)\b/g, (_, w) => `${WORD_NUM[w] ?? w}:30`);
  t = t.replace(/\btonight\b/g, "today night").replace(/\bthis (morning|afternoon|evening)\b/g, "today $1");
  if (!/\d|\b[ap]m\b/.test(t)) for (const [part, clock] of Object.entries(DAYPART)) t = t.replace(new RegExp(`\\b${part}\\b`, "g"), clock);
  t = t.split(/\s+/).filter(Boolean).map((w) => WORD_NUM[w] ?? w).join(" ");
  t = t.replace(/\b(\d{1,2}) (\d{2}) ([ap]m)\b/g, "$1:$2 $3");
  t = t.replace(/\b(\d{1,2}) (fifteen|thirty|forty five) ([ap]m)\b/g, (_, h, m, ap) => `${h}:${MINUTES[m]} ${ap}`);
  return t.trim();
}
const HAS_TIME = /\d|noon|midnight|\bam\b|\bpm\b|\bin \w+ (?:minutes?|hours?)\b/;
const LEAD = /^(?:(?:hey |ok |okay )?(?:jarvis|mozhi),? )?(?:please )?(?:remind me|set (?:a |an )?reminder|reminder)(?: to| about| that| for)? ?/;
export function reminderTitle(text, when) {
  let t = clean(text).join(" ").replace(LEAD, "");
  for (const w of when.split(/\s+/).filter(Boolean)) t = t.replace(new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`), " ");
  const words = t.replaceAll(",", " ").split(/\s+/).filter(Boolean);
  while (words.length && ["at", "on", "for", "by", "in", "from", "till", "until", "to", "and"].includes(words[words.length - 1])) words.pop();
  return words.join(" ");
}

const say = (code, extra = {}) => ({ type: "say", code, ...extra });
const GREETING = "Hello. I can check the weather, set reminders and save notes. What do you need?";
let chronoP;
async function act(r, body, on = {}) {
  if (r.tool === "WEATHER") {
    const city = r.args.city || body.default_city, detected = language(city || "");
    return weather(city, detected !== "en" ? detected : body.native ? body.lang || "en" : "en");
  }
  if (r.tool === "SET_REMINDER") {
    const when = r.args.when || "";
    const derived = language(body.text) === "en" ? reminderTitle(body.text, when) : "";
    return reminder(when, derived && (!r.args.title || derived.includes(r.args.title)) ? derived : r.args.title || "");
  }
  if (r.tool === "SAVE_NOTE") return { reply: "Saved your note.", action: { type: "note", text: body.text } };
  if (r.tool === "GENERAL_QA" && r.intent === "general_greet") return { reply: GREETING, action: null };
  if (r.tool === "GENERAL_QA") return byokAnswer(body, on);
  if (r.tool === "NEWS") return { reply: "The news needs the desktop app: browsers block the feed on this page.", action: say("news_static") };
  if (r.tool === "STORY" || r.tool === "VERSE") return { reply: "", action: { type: "content", kind: r.tool.toLowerCase() } };
  const hints = await (hintsP ||= fetch("hints.json").then((x) => x.json()).catch(() => ({})));
  const hint = hints[r.intent];
  return { reply: (hint ? `That sounds like a request to ${hint}, which I cannot do. ` : "I cannot do that. ") + "I can check the weather, set reminders and save notes.", action: null };
}
let hintsP;

async function weather(city, lang = "en") {
  if (!city) return { reply: "Which city should I check the weather for?", action: say("need_city") };
  try {
    const g = await (await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1&format=json&language=${lang}`)).json();
    const hit = (g.results || [])[0];
    if (!hit) return { reply: `I could not find a place called ${city}.`, action: say("city_not_found", { city }) };
    const f = await (await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${hit.latitude}&longitude=${hit.longitude}&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&forecast_days=1&timezone=auto`)).json();
    const place = hit.name + (hit.country ? `, ${hit.country}` : "");
    return { reply: `In ${place} it is ${Math.round(f.current.temperature_2m)} degrees and ${WMO[f.current.weather_code] ?? "mixed conditions"}. Today's range is ${Math.round(f.daily.temperature_2m_min[0])} to ${Math.round(f.daily.temperature_2m_max[0])}.`, action: { type: "weather", place, temp: Math.round(f.current.temperature_2m), sky: f.current.weather_code, lo: Math.round(f.daily.temperature_2m_min[0]), hi: Math.round(f.daily.temperature_2m_max[0]) } };
  } catch {
    return { reply: "I could not reach the weather service. Try again in a moment.", action: say("weather_down") };
  }
}

async function reminder(when, title) {
  if (!when) return { reply: "When should I remind you?", action: say("need_when") };
  const norm = normalizeWhen(when);
  const chrono = await (chronoP ||= import(CHRONO));
  let at = chrono.parseDate(norm, new Date(), { forwardDate: true });
  if (!at) return { reply: `I did not understand the time '${when}'. Try something like tomorrow at 3 pm.`, action: say("bad_time", { when }) };
  if (!HAS_TIME.test(norm)) at.setHours(9, 0, 0, 0);
  const label = title || "Reminder";
  const spoken = at.toLocaleString(undefined, { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });
  return { reply: `Okay, I will remind you: ${label}, on ${spoken}.`, action: { type: "reminder", title: label, at: at.toISOString() } };
}

/* router only, no tools: used by the parity check against the Python router */
export async function routeOnly(text) {
  const t0 = performance.now();
  if (language(text) !== "en") return (await router2()).route(text);
  const [r, meta2] = await Promise.all([router(), router2Meta()]);
  const result = await r.finish(r.route(text));
  if (!["WEATHER", "SET_REMINDER", "SAVE_NOTE"].includes(result.tool)) { // J1 knows nothing of news, stories or verses
    const alt = await (await router2()).route(text);
    if (["NEWS", "STORY", "VERSE"].includes(alt.tool) && alt.confidence >= 0.6) return { ...alt, ms: performance.now() - t0 };
  }
  const scores = { ...Object.fromEntries(Object.values(meta2.tool_of_intent).map((tool) => [tool, 0])), ...result.scores };
  return { ...result, scores, ms: performance.now() - t0 };
}

/* ---------- bring your own key (hosted site only) ----------
   The visitor's key stays in this browser and is sent only to the provider they pick. The page's
   Content-Security-Policy allows exactly these origins, all of which accept browser calls (checked
   with a CORS preflight from this site's origin). */
export const PROVIDERS = {
  openrouter: { label: "OpenRouter", url: "https://openrouter.ai/api/v1/chat/completions" },
  groq: { label: "Groq", url: "https://api.groq.com/openai/v1/chat/completions" },
  openai: { label: "OpenAI", url: "https://api.openai.com/v1/chat/completions" },
  gemini: { label: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions" },
  mistral: { label: "Mistral", url: "https://api.mistral.ai/v1/chat/completions" },
  cerebras: { label: "Cerebras", url: "https://api.cerebras.ai/v1/chat/completions" },
};
const DAILY_CAP = 100;
// An earlier version saved the key in localStorage, which other pages on this shared origin can read.
// Remove any such copy as soon as this file loads, before anyone interacts with the page.
try { localStorage.removeItem("jarvis.byok"); localStorage.removeItem("mozhi.byok"); } catch { /* storage blocked */ }
export const byok = {
  // Kept for this tab only (sessionStorage). The site shares its origin (brej-29.github.io) with other pages,
  // so nothing about the key is written to storage that outlives the tab.
  get() {
    try { const v = JSON.parse(sessionStorage.getItem("mozhi.byok")); if (v?.provider in PROVIDERS && v.key && v.model) return v; } catch { /* storage blocked */ }
    return null;
  },
  set(v) {
    this.clear();
    try { sessionStorage.setItem("mozhi.byok", JSON.stringify(v)); } catch { /* storage blocked */ }
  },
  clear() {
    for (const store of [sessionStorage, localStorage]) { try { store.removeItem("mozhi.byok"); store.removeItem("jarvis.byok"); } catch { /* ignore */ } } // also removes a key saved by an older version
  },
};
function underCap() {
  const day = new Date().toISOString().slice(0, 10);
  try {
    const c = JSON.parse(localStorage.getItem("mozhi.calls") || "{}");
    const n = c.day === day ? c.n : 0;
    if (n >= DAILY_CAP) return false;
    localStorage.setItem("mozhi.calls", JSON.stringify({ day, n: n + 1 }));
  } catch { /* storage blocked: the provider's own limits still apply */ }
  return true;
}
async function byokAnswer(body, on) {
  const text = await byokText(body, on);
  return typeof text === "string" ? { reply: text, action: null } : text;
}
async function byokText(body, on) {
  const cfg = byok.get();
  if (!cfg) return { reply: "General questions need a language model. Add your own key under Preferences, or run Mozhi on your computer with OmniRoute. Weather, reminders and notes work without one.", action: say("qa_nokey") };
  if (!underCap()) return { reply: `That is ${DAILY_CAP} answers today on this device, which is the safety limit. Try again tomorrow.`, action: say("qa_cap", { n: DAILY_CAP }) };
  const messages = [
    { role: "system", content: body.persona || "You are Mozhi, a voice assistant. Answer in one or two short spoken sentences. No markdown, no lists, no emoji." },
    ...(body.history || []).slice(-6).filter((h) => h.role === "user" || h.role === "assistant").map((h) => ({ role: h.role, content: String(h.content).slice(0, 500) })),
    { role: "user", content: body.text },
  ];
  let res;
  try {
    res = await fetch(PROVIDERS[cfg.provider].url, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.key}` },
      body: JSON.stringify({ model: cfg.model, messages, max_tokens: 200, temperature: 0.3, stream: true }) });
  } catch { return `I could not reach ${PROVIDERS[cfg.provider].label}. Check your connection.`; }
  if (res.status === 401 || res.status === 403) return `${PROVIDERS[cfg.provider].label} rejected the key. Check it under Preferences.`;
  if (res.status === 404 || res.status === 400) return `${PROVIDERS[cfg.provider].label} did not accept the model "${cfg.model}". Check the model id under Preferences.`;
  if (!res.ok || !res.body) return `${PROVIDERS[cfg.provider].label} did not answer (${res.status}). Try again in a moment.`;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "", out = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith("data:") || line.endsWith("[DONE]")) continue;
      try {
        const piece = JSON.parse(line.slice(5)).choices?.[0]?.delta?.content;
        if (piece) { out += piece; on.token?.(piece); }
      } catch { /* a partial or non-JSON line */ }
    }
  }
  return out.trim() || `${PROVIDERS[cfg.provider].label} sent an empty answer.`;
}
