import { chat, health as engineHealth, STATIC, byok, PROVIDERS } from "./engine.js";
import { renderEvidence } from "./evidence.js";
import { createOrb } from "./orb.js";
import { I18N, prefs, romanTerm, addressed, say, localize, story, verse, persona } from "./mozhi.js";

document.documentElement.classList.add("js");
const $ = (s) => document.querySelector(s);
const fillText = (s, f) => s.replace(/\{(\w+)\}/g, (_, k) => f[k] ?? "");
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};
const TOOL_LABEL = { WEATHER: "Weather", SET_REMINDER: "Reminder", SAVE_NOTE: "Note", GENERAL_QA: "Answer", NEWS: "News", STORY: "Story", VERSE: "Verse", UNSUPPORTED: "Not done" };
const ACTED = { WEATHER: "Looked up", SET_REMINDER: "Reminder set", SAVE_NOTE: "Note saved", GENERAL_QA: "Asked the model", NEWS: "Fetched headlines", STORY: "Picked a story", VERSE: "Picked a verse" };
let threshold = 0.85, llm = { connected: false }, supported = null;
const history = [];
const orb = createOrb($("#orb"));

/* ---------- state: one value drives the orb, the aurora and the caption ---------- */
let state = "idle", settleTimer = 0;
function setState(s, then = 0) {
  clearTimeout(settleTimer);
  state = s;
  document.body.dataset.state = s;
  orb.setState(s);
  if (then) settleTimer = setTimeout(() => setState("idle"), then);
}
const caption = (t) => { $("#caption").textContent = t; };
let IDLE_CAPTION = "";

/* ---------- tabs ---------- */
function showTab() {
  const tab = location.hash === "#evidence" ? "evidence" : "talk";
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== tab;
  for (const a of document.querySelectorAll("[data-tab]")) {
    if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  if (tab === "evidence" && !$("#ev-root").dataset.ready) { $("#ev-root").dataset.ready = "1"; renderEvidence($("#ev-root")); }
  window.scrollTo(0, 0);
}
addEventListener("hashchange", showTab);
showTab();

/* ---------- health ---------- */
async function health() {
  const s = $("#status");
  try {
    const h = await engineHealth();
    threshold = h.threshold;
    if (h.tools && h.tools.join() !== supported?.join()) { supported = h.tools; applyLang(); }
    llm = h.llm || llm;
    const where = STATIC ? "Router ready, running in your browser" : "Router ready, running on this machine";
    const om = llm.omniroute || {};
    const model = om.state === "starting" ? "Starting OmniRoute for you" : om.state === "failed" ? `Language model unavailable: ${om.detail}`
      : llm.connected ? "Answers from " + llm.model : "No language model connected";
    s.textContent = `${where}. ${model}`;
    s.className = "status ok";
    if (om.state === "starting") setTimeout(health, 2000);
  } catch {
    s.textContent = STATIC ? "Loading the 23 MB router into your browser" : "Router offline. Check that the Mozhi app is running.";
    s.className = "status bad";
    setTimeout(health, 4000);
  }
}
health();

/* ---------- slips ---------- */
function esc(t) { return t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function markSpans(text, spans) {
  // find each span in the raw text, then escape piece by piece so inserted markup is never searched
  const lower = text.toLowerCase(), hits = [];
  for (const sp of spans || []) {
    const i = lower.indexOf(sp.text.toLowerCase());
    if (i >= 0 && !hits.some((h) => i < h.end && i + sp.text.length > h.start)) hits.push({ start: i, end: i + sp.text.length, kind: sp.kind });
  }
  hits.sort((a, b) => a.start - b.start);
  let out = "", at = 0;
  for (const h of hits) {
    out += esc(text.slice(at, h.start)) + `<mark class="s-${h.kind}">${esc(text.slice(h.start, h.end))}</mark>`;
    at = h.end;
  }
  return out + esc(text.slice(at));
}

const TOOL_ORDER = ["WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "NEWS", "STORY", "VERSE", "UNSUPPORTED"];
function scoreRows() {
  const tools = TOOL_ORDER.filter((t) => !supported || supported.includes(t) || t === "UNSUPPORTED");
  return tools.map((t, i) => `<li data-t="${t}" class="scanning" style="--i:${i}"><span class="nm">${TOOL_LABEL[t]}</span><span class="bar"><i></i></span><span class="pc">&nbsp;</span></li>`).join("");
}

function explain(r) {
  const pct = Math.round(r.confidence * 100), bar = Math.round(threshold * 100), top = TOOL_LABEL[r.tool];
  if (r.path === "abstain") return `Closest match was ${top.toLowerCase()} at ${pct}%, under the ${bar}% bar, so I declined instead of guessing.`;
  if (r.tool === "UNSUPPORTED") return `Heard as "${(r.intent || "unsupported").replace(/_/g, " ")}", which I cannot do. Nothing was done.`;
  if (r.tool === "GENERAL_QA") return r.intent === "general_greet" ? "A greeting, so no tool was needed." : `Not an action request. ${llm.connected ? "Asking the language model." : "No language model is connected, so I will say so."}`;
  if (["NEWS", "STORY", "VERSE"].includes(r.tool)) return `${top} at ${pct}%. This comes from content, not the language model.`;
  return `${top} at ${pct}%, over the ${bar}% bar, so I went ahead.`;
}

function revealMind(li, text, r) {
  const mind = li.querySelector(".mind");
  const words = (r.words && r.words.length ? r.words : text.toLowerCase().split(/\s+/).filter(Boolean));
  const slotOf = (w) => (r.spans || []).find((s) => s.text.split(" ").includes(w))?.kind;
  const heard = mind.querySelector(".heard");
  heard.replaceChildren(...words.slice(0, 24).map((w, i) => {
    const c = document.createElement("span");
    c.textContent = w; c.style.setProperty("--i", i);
    const k = slotOf(w); if (k) c.dataset.slot = k;
    return c;
  }));
  mind.querySelectorAll(".scores li").forEach((row) => {
    const t = row.dataset.t, p = r.scores?.[t] ?? (t === r.tool ? r.confidence : 0);
    row.classList.remove("scanning");
    row.classList.toggle("lead", t === r.tool);
    row.style.setProperty("--p", p.toFixed(3));
    row.querySelector(".pc").textContent = p < 0.005 ? "<1%" : `${Math.round(p * 100)}%`;
    if (["WEATHER", "SET_REMINDER", "SAVE_NOTE"].includes(t)) row.style.setProperty("--th", threshold);
  });
  mind.classList.add("read");
  mind.querySelector(".dots").remove();
  mind.querySelector(".why-t").textContent = explain(r);
}

function newSlip(text) {
  $("#empty").hidden = true;
  $("#clear").hidden = false;
  const feed = $("#feed");
  const before = [...feed.children].map((el) => [el, el.getBoundingClientRect().top]);
  const li = document.createElement("li");
  li.className = "slip enter";
  li.innerHTML = `<p class="said">${esc(text)}</p>
    <ol class="trace" aria-label="Steps">
      <li class="on"><b></b><span>Heard</span></li><li><b></b><span>Routed</span></li>
      <li><b></b><span>Acted</span></li><li><b></b><span>Replied</span></li></ol>
    <div class="mind">
      <div class="heard" aria-hidden="true"></div>
      <ul class="scores" aria-hidden="true">${scoreRows()}</ul>
      <p class="why"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="why-t">Reading your request</span></p>
    </div>
    <div class="verdict" hidden></div>
    <p class="reply"><span class="shimmer"></span></p>
    <p class="meta fine" hidden></p>`;
  feed.prepend(li);
  if (!reduced.matches) { // FLIP: the older slips glide down instead of jumping
    for (const [el, top] of before) {
      const dy = top - el.getBoundingClientRect().top;
      if (dy) el.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 420, easing: "cubic-bezier(.2,.8,.2,1)" });
    }
  }
  return li;
}

function showRoute(li, text, r) {
  const no = r.tool === "UNSUPPORTED", name = r.tool.toLowerCase();
  li.dataset.tool = name;
  li.classList.toggle("is-no", no);
  li.querySelector(".said").innerHTML = markSpans(text, r.spans);
  revealMind(li, text, r);
  const steps = li.querySelectorAll(".trace li");
  steps[1].classList.add("on");
  steps[1].querySelector("span").innerHTML = `Routed<small>${r.ms < 10 ? r.ms.toFixed(1) : Math.round(r.ms)} ms</small>`;
  if (no) {
    steps[2].classList.add("stop");
    steps[2].querySelector("span").textContent = "Did not act";
    steps[3].remove();
  } else {
    const acted = r.tool !== "GENERAL_QA" ? ACTED[r.tool] : r.intent === "general_greet" ? "Answered" : llm.connected ? ACTED.GENERAL_QA : "No model connected";
    steps[2].querySelector("span").textContent = acted;
  }
  const slots = Object.entries(r.args || {}).filter(([, v]) => v).map(([k, v]) => `${k}: ${esc(String(v))}`).join(", ");
  const how = r.path === "abstain" ? "Unsure, so it declined" : r.path === "llm" ? "Asked the language model" : "Fast path";
  const v = li.querySelector(".verdict");
  v.hidden = false;
  v.innerHTML = `<span class="chip">${TOOL_LABEL[r.tool]}</span>
    <span class="meter" style="--v:${r.confidence};--th:${threshold}" role="img" aria-label="Router confidence ${Math.round(r.confidence * 100)} percent, decline threshold ${Math.round(threshold * 100)} percent"></span>
    <span class="meta">${Math.round(r.confidence * 100)}% sure${slots ? ", " + slots : ""}</span>`;
  const m = li.querySelector(".meta.fine");
  m.hidden = false;
  m.textContent = `${how}${r.intent ? ", heard as " + r.intent.replace(/_/g, " ") : ""}`;
  caption(`${TOOL_LABEL[r.tool]}, ${Math.round(r.confidence * 100)}% sure`);
}

/* ---------- actions on this device ---------- */
const timers = new Map();
function schedule(rem) {
  const ms = new Date(rem.at) - Date.now();
  if (ms <= 0 || ms > 2 ** 31 - 1) return;
  timers.set(rem.at + rem.title, setTimeout(() => {
    if ("Notification" in window && Notification.permission === "granted") new Notification("Mozhi reminder", { body: rem.title });
    caption(`Reminder: ${rem.title}`);
    speak(`Reminder: ${rem.title}`);
  }, ms));
}
function renderSaved() {
  const rems = store.get("reminders", []).filter((r) => new Date(r.at) > Date.now());
  const notes = store.get("notes", []);
  $("#saved").innerHTML = [...rems.map((r) => `<div class="item">${esc(r.title)}<small>${new Date(r.at).toLocaleString()}</small></div>`),
    ...notes.map((n) => `<div class="item">${esc(n.text)}<small>note</small></div>`)].join("") || "<p>Nothing saved on this device yet.</p>";
}
function perform(action) {
  if (!action) return;
  if (action.type === "reminder") {
    store.set("reminders", [...store.get("reminders", []), action]);
    schedule(action);
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  } else if (action.type === "note") {
    store.set("notes", [{ text: action.text, at: new Date().toISOString() }, ...store.get("notes", [])]);
  }
  renderSaved();
}
store.get("reminders", []).forEach(schedule);
renderSaved();

/* ---------- speech out ---------- */
// Prefer the natural-sounding voices the browser offers (Edge ships "Online (Natural)" ones), let the person override.
const voiceRank = (v) => (/natural|neural/i.test(v.name) ? 4 : 0) + (/online/i.test(v.name) ? 2 : 0) + (/google/i.test(v.name) ? 1 : 0);
function fillVoices() {
  if (!("speechSynthesis" in window)) return;
  const lang = prefs.native ? prefs.lang : "en";
  const vs = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang)).sort((a, b) => voiceRank(b) - voiceRank(a));
  const want = store.get("voice", "");
  $("#voice").innerHTML = "";
  for (const v of vs) {
    const o = document.createElement("option");
    o.value = v.name; o.textContent = `${v.name} (${v.lang})`;
    $("#voice").append(o);
  }
  if (vs.some((v) => v.name === want)) $("#voice").value = want;
  $("#tts-note").textContent = vs.length || prefs.lang === "en" || !prefs.native ? "" : fillText(I18N.ui[prefs.lang].no_voice, { lang: I18N.langs[prefs.lang].label });
}
function chosenVoice() { return speechSynthesis.getVoices().find((v) => v.name === $("#voice").value) || null; }
function speak(t, force = false) {
  if ((!force && !$("#speak").checked) || !("speechSynthesis" in window)) return;
  if (prefs.lang !== "en" && prefs.native && !chosenVoice()) return; // no Tamil or Malayalam voice here: show the text, never read it with an English voice
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(t);
  const v = chosenVoice();
  if (v) { u.voice = v; u.lang = v.lang; } else u.lang = prefs.native ? I18N.langs[prefs.lang].speech : "en-US";
  u.rate = Number($("#rate").value) || 1;
  u.onstart = () => setState("speaking");
  u.onboundary = () => orb.pulse(0.8); // a pulse on every word the voice reaches, where the voice reports them
  u.onend = u.onerror = () => setState("idle");
  speechSynthesis.speak(u);
}
if ("speechSynthesis" in window) { fillVoices(); speechSynthesis.onvoiceschanged = fillVoices; }
$("#voice").addEventListener("change", (e) => store.set("voice", e.target.value));
$("#rate").value = store.get("rate", 1);
$("#rate").addEventListener("change", (e) => store.set("rate", Number(e.target.value)));
$("#hear").addEventListener("click", () => speak("Hello. This is how I sound.", true));
$("#speak").checked = store.get("speak", false);
$("#speak").addEventListener("change", (e) => store.set("speak", e.target.checked));
$("#city").value = store.get("city", "");
$("#city").addEventListener("change", (e) => store.set("city", e.target.value.trim()));

/* ---------- what to show and say for a result ---------- */

async function present(d) {
  const out = localize(d);
  out.spoken = out.text;
  if (d.action?.type !== "content") {
    if (out.card?.kind === "news") out.spoken = [out.text, ...out.card.items.map((i) => i.title)].join(". ");
    return out;
  }
  const card = d.action.kind === "story" ? await story() : await verse();
  const L = prefs.lang;
  if (!card) { out.text = L === "en" || !prefs.native ? "I do not have one to share yet." : say("decline"); return out; }
  out.card = card;
  const intro = d.action.kind === "story" ? "story_intro" : "verse_intro";
  out.text = L === "en" || !prefs.native ? addressed(d.action.kind === "story" ? "Here is a folk tale." : "Here is a verse.") : say(intro);
  out.spoken = [out.text, card.title, card.body, card.lines?.join(". "), card.meaning, card.moral].filter(Boolean).join(" ");
  return out;
}

function safeLink(text, url) {
  const a = document.createElement("a");
  a.textContent = text; a.href = /^https:\/\//.test(url) ? url : "#"; a.target = "_blank"; a.rel = "noopener noreferrer";
  return a;
}

function renderCard(c) {
  const el = document.createElement("div");
  el.className = `card card-${c.kind}`;
  const add = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; n.textContent = text; el.append(n); return n; };
  if (c.kind === "news") {
    const ul = document.createElement("ul");
    for (const i of c.items) {
      const li = document.createElement("li");
      li.append(safeLink(i.title, i.url));
      if (i.source) { const s = document.createElement("small"); s.textContent = ` ${i.source}`; li.append(s); }
      ul.append(li);
    }
    el.append(ul);
    return el;
  }
  const L = prefs.native ? I18N.langs[prefs.lang] : I18N.langs.en;
  if (c.kind === "story") { add("h3", "", c.title); add("p", "body", c.body); add("p", "moral", `${L.informal?.moral ?? "Moral:"} ${c.moral}`); }
  else { add("p", "lines", c.lines.join("\n")); if (c.meaning) add("p", "body", c.meaning); add("p", "attrib", `${c.author}, ${c.work}${c.ref ? " " + c.ref : ""}`); }
  const src = document.createElement("p");
  src.className = "attrib";
  src.append(`${L.informal?.source ?? "Source"}: `, safeLink(c.source.name, c.source.url));
  if (c.source.licence) src.append(` (${c.source.licence})`);
  el.append(src);
  return el;
}

/* ---------- language and respect ---------- */
function applyLang() {
  const ui = I18N.ui.en, L = I18N.langs.en;  // the page stays English; only the sample requests change
  document.documentElement.lang = "en";
  $("#l-lang").textContent = ui.lang; $("#l-respect").textContent = ui.respect; $("#l-gender").textContent = ui.gender;
  $("#respect-name").textContent = `${prefs.level + 1}/5 ${L.level_names[prefs.level]}${romanTerm() ? ", " + romanTerm().replace(/, $/, "") : ""}`;
  $("#gender").innerHTML = "";
  for (const [v, k] of [["", "neutral"], ["male", "male"], ["female", "female"]]) $("#gender").append(new Option(ui[k], v));
  $("#gender").value = prefs.gender;
  $("#gender").disabled = $("#respect").disabled = prefs.lang === "en";
  $("#text").placeholder = ui.placeholder;
  $("#send-btn").textContent = ui.send;
  IDLE_CAPTION = fillText(ui.caption, { name: I18N.app.name });
  if (state === "idle") caption(IDLE_CAPTION);
  const heads = { do: ui.should_do, no: ui.should_decline, qa: ui.should_answer };
  $("#tries").innerHTML = "";
  for (const g of ["do", "no", "qa"]) {
    const div = document.createElement("div"), h = document.createElement("h2"), ul = document.createElement("ul");
    h.textContent = heads[g]; div.append(h, ul);
    for (const e of I18N.examples[prefs.lang].filter((x) => x.group === g && (!x.tool || !supported || supported.includes(x.tool)))) {
      const li = document.createElement("li"), b = document.createElement("button");
      b.type = "button"; b.textContent = e.label; b.addEventListener("click", () => send(e.say)); li.append(b); ul.append(li);
    }
    $("#tries").append(div);
  }
  if ("speechSynthesis" in window) fillVoices();
}
$("#lang").append(...Object.entries(I18N.langs).map(([k, v]) => new Option(v.menu, k)));
$("#native").checked = prefs.native;
$("#native").addEventListener("change", (e) => { prefs.native = e.target.checked; prefs.save(); applyLang(); });
$("#lang").value = prefs.lang;
$("#respect").value = prefs.level;
$("#lang").addEventListener("change", (e) => { prefs.lang = e.target.value; prefs.save(); applyLang(); });
$("#respect").addEventListener("input", (e) => { prefs.level = Number(e.target.value); prefs.save(); applyLang(); });
$("#gender").addEventListener("change", (e) => { prefs.gender = e.target.value; prefs.save(); applyLang(); });

/* ---------- send ---------- */
let busy = false;
async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  $("#text").value = "";
  $(".send").disabled = true;
  setState("thinking");
  caption("Routing");
  const li = newSlip(text);
  const reply = li.querySelector(".reply");
  let streamed = "";
  try {
    const d = await chat({ text, tz_offset_min: -new Date().getTimezoneOffset(), default_city: $("#city").value.trim(), history,
      lang: prefs.lang, level: prefs.level, gender: prefs.gender, native: prefs.native, persona: persona() }, {
      route: (r) => showRoute(li, text, r),
      token: (piece) => {
        if (!streamed) { reply.textContent = ""; li.querySelectorAll(".trace li")[2]?.classList.add("on"); li.classList.add("answering"); }
        streamed += piece;
        li.dataset.tokens = String((Number(li.dataset.tokens) || 0) + 1);
        reply.textContent = streamed;
        const caret = document.createElement("span");
        caret.className = "caret";
        reply.append(caret);
      },
    });
    const out = await present(d);
    li.classList.remove("answering");
    reply.textContent = out.text;
    if (out.card) li.querySelector(".reply").after(renderCard(out.card));
    const steps = li.querySelectorAll(".trace li");
    if (d.route.tool !== "UNSUPPORTED") steps.forEach((s) => s.classList.add("on"));
    perform(d.action);
    history.push({ role: "user", content: text }, { role: "assistant", content: out.text });
    if (d.route.tool === "UNSUPPORTED") setState("declined", 1600);
    else setState("idle");
    caption(d.route.tool === "UNSUPPORTED" ? "Declined. Nothing was done." : IDLE_CAPTION);
    speak(out.spoken);
  } catch {
    li.removeAttribute("data-tool");
    reply.textContent = "The router did not answer. In the hosted copy the model may still be loading: wait a few seconds and send again.";
    setState("idle");
    caption(IDLE_CAPTION);
  } finally {
    busy = false;
    $(".send").disabled = false;
  }
}
$("#form").addEventListener("submit", (e) => { e.preventDefault(); send($("#text").value); });
applyLang();
$("#clear").addEventListener("click", () => { $("#feed").innerHTML = ""; $("#empty").hidden = false; $("#clear").hidden = true; });
addEventListener("keydown", (e) => { // "/" jumps to the input, Escape stops listening; neither animates
  if (e.key === "/" && !/input|textarea/i.test(document.activeElement?.tagName)) { e.preventDefault(); $("#text").focus(); }
  if (e.key === "Escape") stopListening?.();
});

/* ---------- voice in ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const mic = $("#mic");
let stopListening = null;
if (!SR) {
  mic.disabled = true;
  $("#voice-hint").textContent = "Voice input needs Chrome or Edge. Typing works in any browser.";
} else {
  let rec = null, raf = 0, stream = null, ctx = null;
  const freq = new Uint8Array(256);
  const level = (an, buf) => {
    an.getByteFrequencyData(freq); orb.setSpectrum(freq);
    an.getByteTimeDomainData(buf);
    let s = 0; for (const v of buf) s += Math.abs(v - 128);
    orb.setLevel(Math.min(1, (s / buf.length) / 24));
    raf = requestAnimationFrame(() => level(an, buf));
  };
  const cleanup = () => {
    mic.setAttribute("aria-pressed", "false");
    cancelAnimationFrame(raf); orb.setLevel(0); orb.setSpectrum(null);
    stream?.getTracks().forEach((t) => t.stop()); ctx?.close(); stream = ctx = null;
  };
  stopListening = () => rec?.stop();
  mic.addEventListener("click", async () => {
    if (rec) { rec.stop(); return; }
    if (busy) return;
    rec = new SR(); rec.lang = prefs.native ? I18N.langs[prefs.lang].speech : "en-IN"; // Tanglish and Manglish come out best through English (India) recognition rec.interimResults = true; rec.maxAlternatives = 1;
    let last = "";
    rec.onresult = (e) => { last = [...e.results].map((r) => r[0].transcript).join(" "); $("#text").value = last; caption(last); };
    rec.onerror = (e) => { $("#voice-hint").textContent = e.error === "not-allowed" ? "Microphone access is blocked. Allow it in the address bar, or type instead." : "Could not hear that. Try again or type."; };
    rec.onend = () => { rec = null; cleanup(); if (last) send(last); else { setState("idle"); caption(IDLE_CAPTION); } };
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(an); level(an, new Uint8Array(an.fftSize));
    } catch { /* the level meter is optional */ }
    $("#voice-hint").textContent = "";
    mic.setAttribute("aria-pressed", "true");
    setState("listening"); caption("Listening");
    rec.start();
  });
  $("#voice-hint").textContent = "Click the orb and speak, or type. Speech recognition runs in your browser. Press / to type.";
}

/* ?say=text prefills the input only. Nothing runs until the person presses Send, so a shared link
   cannot save notes, set reminders or spend LLM calls on its own. */
const preset = new URLSearchParams(location.search).get("say");
if (preset) $("#text").value = preset.slice(0, 300);

/* ---------- bring your own key: only on the hosted copy ---------- */
if (STATIC) {
  $("#byok").hidden = false;
  for (const [id, p] of Object.entries(PROVIDERS)) $("#byok-provider").append(new Option(p.label, id));
  const cur = byok.get();
  if (cur) { $("#byok-provider").value = cur.provider; $("#byok-model").value = cur.model; $("#byok-msg").textContent = "A key is set for this tab."; }
  $("#byok-save").addEventListener("click", () => {
    const provider = $("#byok-provider").value, model = $("#byok-model").value.trim(), key = $("#byok-key").value.trim();
    if (!model || !key) { $("#byok-msg").textContent = "Enter a model id and a key."; return; }
    byok.set({ provider, model, key });
    $("#byok-key").value = "";
    $("#byok-msg").textContent = "Saved for this tab only.";
    health();
  });
  $("#byok-forget").addEventListener("click", () => { byok.clear(); $("#byok-model").value = ""; $("#byok-msg").textContent = "Key removed."; health(); });
}
