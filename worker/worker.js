/* Mozhi search proxy for Cloudflare Workers (free plan).
   Why it exists: a web-search API key must never sit in a web page. This Worker holds the key as a secret,
   answers only requests from the Mozhi site, and stops by itself when half of the monthly allowance is used.

   Routes (GET):
     /search?q=...&lang=en|ta|ml   one web result via Tavily: {title, text, url, source}
     /news?lang=en|ta|ml           headlines from public RSS feeds, no key needed: {items:[{title, url, source, published}]}
   Responses are 503 {"disabled": true} when a cap is reached, and the page then falls back to Wikipedia.

   Secrets and settings: see worker/README.md. Nothing in this file is secret. */

const NEWS_FEEDS = {
  en: "https://feeds.bbci.co.uk/news/world/rss.xml",
  ta: "https://feeds.bbci.co.uk/tamil/rss.xml",
  ml: "https://news.google.com/rss?hl=ml&gl=IN&ceid=IN:ml",
};

const json = (body, status, origin, extra = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "access-control-allow-origin": origin || "null", vary: "origin", ...extra },
  });

const month = () => new Date().toISOString().slice(0, 7);
const day = () => new Date().toISOString().slice(0, 10);

async function bump(kv, key, ttl) {
  const n = Number((await kv.get(key)) || 0) + 1;
  await kv.put(key, String(n), { expirationTtl: ttl });
  return n;
}

function parseRss(xml, source) {
  const items = [];
  for (const m of xml.matchAll(/<item\b[\s\S]*?<\/item>/g)) {
    const block = m[0];
    const pick = (tag) => (block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`)) || [])[1] || "";
    const clean = (s) => s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();
    const title = clean(pick("title")), url = clean(pick("link"));
    if (title && url.startsWith("https://")) items.push({ title: title.slice(0, 220), url, source, published: clean(pick("pubDate")) });
    if (items.length === 6) break;
  }
  return items;
}

export default {
  async fetch(request, env) {
    const allowed = (env.ALLOWED_ORIGINS || "https://brej-29.github.io").split(",").map((s) => s.trim());
    const origin = request.headers.get("origin") || "";
    const ok = allowed.includes(origin);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: { "access-control-allow-origin": ok ? origin : "null", "access-control-allow-methods": "GET", "access-control-max-age": "86400", vary: "origin" } });
    if (request.method !== "GET" || !ok) return json({ error: "not allowed" }, 403, ok ? origin : "");

    const url = new URL(request.url);
    const lang = ["en", "ta", "ml"].includes(url.searchParams.get("lang")) ? url.searchParams.get("lang") : "en";

    if (url.pathname === "/news") {
      const cache = caches.default, key = new Request(`https://cache.invalid/news/${lang}`);
      const hit = await cache.match(key);
      if (hit) return json(await hit.json(), 200, origin);
      const r = await fetch(NEWS_FEEDS[lang], { headers: { "user-agent": "mozhi-news/1.0" }, cf: { cacheTtl: 600 } });
      if (!r.ok) return json({ items: [] }, 502, origin);
      const body = { items: parseRss((await r.text()).slice(0, 400000), lang === "en" ? "BBC News" : lang === "ta" ? "BBC Tamil" : "Google News") };
      await cache.put(key, new Response(JSON.stringify(body), { headers: { "cache-control": "max-age=600" } }));
      return json(body, 200, origin);
    }

    if (url.pathname === "/search") {
      const q = (url.searchParams.get("q") || "").trim().slice(0, 200);
      if (!q) return json({ error: "empty query" }, 400, origin);
      if (!env.TAVILY_API_KEY || !env.USAGE) return json({ disabled: true, reason: "not configured" }, 503, origin);

      const limit = Number(env.TAVILY_MONTHLY_LIMIT || 1000), cap = Math.floor(limit * Number(env.CAP_FRACTION || 0.5));
      const used = Number((await env.USAGE.get(`tavily:${month()}`)) || 0);
      if (used >= cap) return json({ disabled: true, reason: "monthly cap reached" }, 503, origin);

      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      const perIp = await bump(env.USAGE, `ip:${day()}:${ip}`, 90000);
      if (perIp > Number(env.PER_IP_DAILY || 15)) return json({ disabled: true, reason: "daily limit for this visitor" }, 429, origin);

      await bump(env.USAGE, `tavily:${month()}`, 3 * 31 * 86400); // count before the call, so a failure cannot push usage past the cap
      const r = await fetch("https://api.tavily.com/search", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.TAVILY_API_KEY}` },
        body: JSON.stringify({ query: q, max_results: 3, search_depth: "basic", include_answer: true }),
      });
      if (!r.ok) return json({ disabled: true, reason: "search unavailable" }, 502, origin);
      const d = await r.json();
      const top = (d.results || [])[0];
      const text = String(d.answer || top?.content || "").slice(0, 600);
      if (!text || !top?.url?.startsWith("https://")) return json({ title: "", text: "" }, 200, origin);
      return json({ title: String(top.title || q).slice(0, 160), text, url: top.url, source: "Web search (Tavily)" }, 200, origin);
    }

    return json({ error: "not found" }, 404, origin);
  },
};
