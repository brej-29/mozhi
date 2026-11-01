/* Language and respect layer: which words Koottu uses, and what it calls you.
   Tamil and Malayalam replies are composed here from facts (a place, a temperature, a time), so the same
   wording is used whether the facts came from the local server or from the browser-only copy. English
   replies come from the backend unchanged. All Tamil and Malayalam text lives in i18n.json. */

export const I18N = await (await fetch("i18n.json")).json();
export const LEVELS = I18N.levels;

const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};
export const prefs = {
  lang: I18N.langs[store.get("lang", "")] ? store.get("lang", "en") : "en",
  level: Math.min(LEVELS - 1, Math.max(0, Number(store.get("level", 2)) || 0)),
  gender: ["male", "female"].includes(store.get("gender", "")) ? store.get("gender", "") : "",
  save() { store.set("lang", this.lang); store.set("level", this.level); store.set("gender", this.gender); },
};

export const formal = (level = prefs.level) => level >= 2; // from "anna/akka" up, the polite "you" is used
const fill = (s, facts) => s.replace(/\{(\w+)\}/g, (_, k) => facts[k] ?? "");

/** The address term for a level, or "" when the person chose none (neutral below the highest level). */
export function term(lang = prefs.lang, level = prefs.level, gender = prefs.gender) {
  const row = I18N.langs[lang].address?.[level];
  return row ? row[{ male: 0, female: 1 }[gender] ?? 2] : "";
}

/** One message in the chosen language and register. English is not handled here. */
export function say(code, facts = {}, lang = prefs.lang, level = prefs.level, gender = prefs.gender) {
  const L = I18N.langs[lang];
  const a = term(lang, level, gender);
  const text = L[formal(level) ? "formal" : "informal"][code];
  return text ? fill(text, { ...facts, a: a ? `${a}, ` : "" }).trim() : "";
}

const spokenDate = (iso, lang) => new Intl.DateTimeFormat(I18N.langs[lang].locale, {
  weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" }).format(new Date(iso));

/** Turns a backend result into what the person sees and hears: { text, card }. */
export function localize(d, ctx = prefs) {
  const { lang, level, gender } = ctx;
  const act = d.action || {};
  if (lang === "en") return { text: d.reply, card: act.type === "news" ? { kind: "news", items: act.items } : null };
  const m = (code, facts) => say(code, facts, lang, level, gender);
  if (act.type === "say") return { text: m(act.code, act) || d.reply, card: null };
  if (act.type === "weather") return { text: m("weather_ok", { ...act, sky: I18N.langs[lang].sky[act.sky] ?? "" }), card: null };
  if (act.type === "reminder") return { text: m("reminder_ok", { title: act.title, when_spoken: spokenDate(act.at, lang) }), card: null };
  if (act.type === "note") return { text: m("note_ok"), card: null };
  if (act.type === "news") return { text: m("news_intro"), card: { kind: "news", items: act.items } };
  if (d.route.tool === "UNSUPPORTED") return { text: m("decline"), card: null };
  if (d.route.tool === "GENERAL_QA" && d.route.intent === "general_greet") return { text: m("greet"), card: null };
  return { text: d.reply, card: null }; // a model answer, already written in the chosen language
}

/* ---------- stories and verses: bundled, sourced, read from disk ---------- */
const loaded = {};
const load = (name) => (loaded[name] ||= fetch(`content/${name}.json`).then((r) => r.json()).catch(() => ({})));
const pick = (list, seenKey) => {
  const seen = new Set(store.get(seenKey, []));
  const fresh = list.filter((x) => !seen.has(x.id));
  const x = (fresh.length ? fresh : list)[Math.floor(Math.random() * (fresh.length || list.length))];
  store.set(seenKey, [...(fresh.length ? seen : []), x.id].slice(-200));
  return x;
};

export async function story(ctx = prefs) {
  const list = (await load("stories")).stories || [];
  if (!list.length) return null;
  const s = pick(list, "koottu.stories");
  const lang = ctx.lang;
  return { kind: "story", title: s.title[lang], body: s.summary[lang], moral: s.moral[lang], source: s.source, region: s.region };
}

export async function verse(ctx = prefs) {
  const all = (await load("verses")).verses || [];
  // Malayalam gets Malayalam classics. Tamil gets Tamil. English gets Thirukkural, which has an English gloss.
  const list = all.filter((v) => (ctx.lang === "ml" ? v.lang === "ml" : ctx.lang === "ta" ? v.lang === "ta" : v.meaning.en));
  if (!list.length) return null;
  const v = pick(list, `koottu.verses.${ctx.lang}`);
  return { kind: "verse", lines: v.lines, meaning: v.meaning[ctx.lang] || v.meaning.en || "", work: ctx.lang === "en" ? v.work_en : v.work,
    author: ctx.lang === "en" ? v.author_en : v.author, ref: v.ref, source: v.source };
}

/** The system prompt used by the browser-only copy; the local server builds the same text in llm.persona(). */
export function persona(ctx = prefs) {
  const p = I18N.persona, L = I18N.langs[ctx.lang];
  if (ctx.lang === "en") return null;
  const f = formal(ctx.level), a = term(ctx.lang, ctx.level, ctx.gender);
  return [fill(p.name_line, { name: I18N.app.name }), fill(p.lang_line, { language: L.language }),
    fill(p[f ? "formal" : "informal"], { pronoun: L.pronoun[f ? 1 : 0] }),
    a ? fill(p.addr_line, { addr: a }) : p.no_addr_line].join(" ");
}
