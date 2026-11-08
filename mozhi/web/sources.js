/* Free sources the browser can reach directly, no key, no account.
   - Wikipedia in English, Tamil and Malayalam: answers to open questions and "search" (CC BY-SA, link kept)
   - Wikipedia "on this day": history stories (English only)
   - BBC and Google News feeds through rss2json (their free tier), headlines and links only
   An optional search proxy (window.MOZHI_PROXY, see worker/) adds web search with a server-side key and a usage cap.
   Everything returns a card the UI can render, or null. Nothing here ever sees an API key. */

const WIKI = { en: "en", ta: "ta", ml: "ml" };
const FEEDS = {
  en: "https://feeds.bbci.co.uk/news/world/rss.xml",
  ta: "https://feeds.bbci.co.uk/tamil/rss.xml",
  ml: "https://news.google.com/rss?hl=ml&gl=IN&ceid=IN:ml",
};
const TIMEOUT = 8000;

async function getJSON(url, init = {}) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), TIMEOUT);
  try {
    const r = await fetch(url, { ...init, signal: ctl.signal, credentials: "omit", referrerPolicy: "no-referrer" });
    return r.ok ? await r.json() : null;
  } catch { return null; } finally { clearTimeout(t); }
}

const httpsOnly = (u) => (typeof u === "string" && /^https:\/\//.test(u) ? u : "");
const firstSentences = (s, max = 380) => {
  const t = String(s || "").replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max), i = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("। "));
  return i > 120 ? cut.slice(0, i + 1) : cut.replace(/\s+\S*$/, "") + "…";
};
const hasIndic = (s) => /[஀-௿ഀ-ൿ]/.test(s);

/** Words that only ask for a lookup carry no meaning for the search. */
const FILLER = /^(?:(?:please|tell me|what is|what's|who is|who was|who painted|who wrote|who built|search for|search|look up|find|about|the|a|an)\s+)+/i;

export async function search(text, lang = "en") {
  const proxy = window.MOZHI_PROXY && (await proxySearch(text, lang));
  if (proxy) return proxy;
  const order = hasIndic(text) ? [WIKI[lang] && lang !== "en" ? lang : /[஀-௿]/.test(text) ? "ta" : "ml", "en"] : ["en"];
  for (const host of order) {
    const q = hasIndic(text) ? text : text.replace(FILLER, "");
    const hit = await getJSON(`https://${host}.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&srlimit=1&format=json&origin=*`);
    const title = hit?.query?.search?.[0]?.title;
    if (!title) continue;
    const sum = await getJSON(`https://${host}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title.replace(/ /g, "_"))}`);
    if (sum?.extract) {
      return { kind: "search", title: sum.title || title, text: firstSentences(sum.extract), url: httpsOnly(sum.content_urls?.desktop?.page), source: `Wikipedia (${host}), CC BY-SA`, lang: host };
    }
  }
  return null;
}

/** Today in history, from Wikipedia's feed. English only; the feed has no Tamil or Malayalam edition. */
export async function history() {
  const d = new Date();
  const j = await getJSON(`https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/${d.getMonth() + 1}/${d.getDate()}`);
  const ev = (j?.events || []).filter((e) => e.text && e.year);
  if (!ev.length) return null;
  const pick = [...ev].sort(() => Math.random() - 0.5).slice(0, 5).sort((a, b) => a.year - b.year);
  return { kind: "history", items: pick.map((e) => ({ year: e.year, text: firstSentences(e.text, 220), url: httpsOnly(e.pages?.[0]?.content_urls?.desktop?.page) })) };
}

export async function news(lang = "en") {
  const proxy = window.MOZHI_PROXY && (await getJSON(`${window.MOZHI_PROXY}/news?lang=${lang}`));
  if (proxy?.items?.length) return { kind: "news", items: proxy.items.map(cleanItem).filter(Boolean).slice(0, 6) };
  const j = await getJSON(`https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(FEEDS[lang] || FEEDS.en)}`);
  if (j?.status !== "ok" || !j.items?.length) return currentEvents(); // the free converter is rate limited at times
  const source = j.feed?.title || "";
  return { kind: "news", items: j.items.slice(0, 6).map((i) => cleanItem({ title: i.title, url: i.link, source, published: i.pubDate })).filter(Boolean) };
}

const cleanItem = (i) => (i?.title && httpsOnly(i.url) ? { title: String(i.title).slice(0, 220), url: i.url, source: String(i.source || "").slice(0, 80), published: i.published || "" } : null);

async function proxySearch(text, lang) {
  const j = await getJSON(`${window.MOZHI_PROXY}/search?lang=${lang}&q=${encodeURIComponent(text.slice(0, 200))}`);
  return j?.text && j.title ? { kind: "search", title: String(j.title).slice(0, 160), text: firstSentences(j.text), url: httpsOnly(j.url), source: String(j.source || "Web search").slice(0, 80), lang } : null;
}

/** Fallback with no third party and no key: Wikipedia's "Current events" portal, the last two days. English only. */
async function currentEvents() {
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  for (const back of [0, 1]) {
    const d = new Date(Date.now() - back * 86400000);
    const page = `Portal:Current_events/${d.getFullYear()}_${months[d.getMonth()]}_${d.getDate()}`;
    const j = await getJSON(`https://en.wikipedia.org/w/api.php?action=parse&page=${encodeURIComponent(page)}&prop=text&format=json&formatversion=2&origin=*`);
    if (!j?.parse?.text) continue;
    const doc = new DOMParser().parseFromString(j.parse.text, "text/html"); // parsed into an inert document; only text and hrefs are read
    const items = [];
    for (const li of doc.querySelectorAll("li")) {
      if (li.querySelector("ul, li")) continue;
      const text = li.textContent.replace(/\[\d+\]/g, "").replace(/\s+/g, " ").trim();
      const href = li.querySelector('a[href^="/wiki/"]')?.getAttribute("href");
      if (text.length > 60 && href && !/^(edit|history|watch)/i.test(text)) items.push({ title: firstSentences(text, 200), url: "https://en.wikipedia.org" + href, source: "Wikipedia current events, CC BY-SA", published: "" });
      if (items.length === 6) break;
    }
    if (items.length) return { kind: "news", items };
  }
  return null;
}
