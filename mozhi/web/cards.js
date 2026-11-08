/* Every supplied value is text. Links are parsed and limited to HTTPS. */
const text = (v) => (v == null ? "" : String(v));
function node(tag, cls, value) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (value != null) n.textContent = text(value);
  return n;
}
export function safeLink(label, url) {
  let u;
  try {
    u = new URL(text(url));
  } catch {
    /* invalid address */
  }
  if (!u || u.protocol !== "https:" || u.username || u.password)
    return node("span", "item-title", label);
  const a = node("a", "", label);
  a.href = u.href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function spoken(n) {
  n.classList.add("speech-text");
  return n;
}
function source(el, s) {
  if (!s) return;
  const p = node("p", "attrib");
  if (typeof s === "object") {
    p.append("Source: ", safeLink(s.name || "Read source", s.url));
    if (s.licence) p.append(" (" + text(s.licence) + ")");
  } else p.textContent = "Source: " + text(s);
  el.append(p);
}
export function cardSpeech(c) {
  if (!c) return "";
  switch (c.kind) {
    case "news":
      return (c.items || []).map((i) => i.title).join(". ");
    case "history":
      return (c.items || [])
        .map((i) => text(i.year) + ". " + text(i.text))
        .join(". ");
    case "story":
      return [c.title, c.body, c.moral].filter(Boolean).join(" ");
    case "verse":
      return [...(c.lines || []), c.meaning].filter(Boolean).join(" ");
    case "search":
      return [c.title, c.text].filter(Boolean).join(". ");
    default:
      return "";
  }
}
export function renderCard(c) {
  const kinds = ["search", "news", "history", "story", "verse", "weather"];
  const kind = kinds.includes(c.kind) ? c.kind : "search";
  const el = node("section", "card card-" + kind);
  el.setAttribute("aria-label", kind + " result");
  if (/^(en|ta|ml)(-[A-Za-z]+)?$/.test(c.lang || "")) el.lang = c.lang;
  const add = (tag, cls, value, speech = false) => {
    const n = node(tag, cls, value);
    el.append(n);
    return speech ? spoken(n) : n;
  };
  add(
    "p",
    "card-type",
    {
      search: "From the web",
      news: "Headlines",
      history: "Through time",
      story: "A story to sit with",
      verse: "In a few lines",
      weather: "Weather report",
    }[kind],
  );
  if (kind === "search") {
    const h = add("h3", "");
    h.append(spoken(safeLink(c.title || "Search result", c.url)));
    if (c.text) add("p", "body", c.text, true);
    source(el, c.source);
  }
  if (kind === "news" || kind === "history") {
    const ol = add("ol", "card-list");
    for (const [index, item] of (Array.isArray(c.items)
      ? c.items
      : []
    ).entries()) {
      const li = node("li"),
        number = node(
          "span",
          "item-number",
          kind === "history" ? item.year : String(index + 1).padStart(2, "0"),
        ),
        body = node("div");
      if (kind === "history") spoken(number);
      body.append(
        spoken(safeLink(kind === "history" ? item.text : item.title, item.url)),
      );
      const meta = [item.source, item.published]
        .filter((v) => typeof v === "string")
        .join(" · ");
      if (meta) body.append(node("small", "", meta));
      li.append(number, body);
      ol.append(li);
    }
  }
  if (kind === "story") {
    add("h3", "", c.title, true);
    const track = add("div", "reading-track");
    const p = node("progress");
    p.max = 100;
    p.value = 0;
    p.setAttribute("aria-label", "Story spoken progress");
    track.append(p, node("span", "reading-label", "Ready to read"));
    add("p", "body", c.body, true);
    if (c.moral) add("p", "moral", c.moral, true);
    source(el, c.source);
  }
  if (kind === "verse") {
    const lines = add("div", "lines");
    for (const [i, line] of (Array.isArray(c.lines) ? c.lines : []).entries()) {
      const p = spoken(node("p", "verse-line", line));
      p.style.setProperty("--i", Math.min(i, 12));
      lines.append(p);
    }
    if (c.meaning) add("p", "body", c.meaning, true);
    add("p", "attrib", [c.author, c.work, c.ref].filter(Boolean).join(" · "));
    source(el, c.source);
  }
  if (kind === "weather") {
    if (typeof c.skyText === "number") {
      const code = c.skyText;
      c = {
        ...c,
        skyText:
          code === 0
            ? "Clear sky"
            : code === 1
              ? "Mostly clear"
              : code === 2
                ? "Partly cloudy"
                : code === 3
                  ? "Overcast"
                  : code < 50
                    ? "Fog"
                    : code < 60
                      ? "Drizzle"
                      : code < 70
                        ? "Rain"
                        : code < 80
                          ? "Snow"
                          : code < 90
                            ? "Showers"
                            : "Thunderstorms",
      };
    }
    const top = add("div", "weather-top");
    top.append(node("h3", "", c.place || "Current weather"));
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 64 64");
    svg.setAttribute("class", "weather-icon");
    svg.setAttribute("aria-hidden", "true");
    const cloud = /cloud|rain|overcast|snow|fog/i.test(text(c.skyText));
    const shape = document.createElementNS(svg.namespaceURI, "path");
    shape.setAttribute(
      "d",
      cloud
        ? "M16 45h33a10 10 0 0 0 0-20 16 16 0 0 0-31-3 12 12 0 0 0-2 23Z"
        : "M32 6v7m0 38v7M6 32h7m38 0h7M14 14l5 5m26 26 5 5M14 50l5-5m26-26 5-5M45 32a13 13 0 1 1-26 0 13 13 0 0 1 26 0Z",
    );
    svg.append(shape);
    top.append(svg);
    const temp = (v) =>
      typeof v === "number" && Number.isFinite(v)
        ? Math.round(v)
        : text(v) || "?";
    add("p", "temperature", temp(c.temp) + "°");
    add("p", "body", c.skyText || "Current conditions");
    add(
      "p",
      "weather-detail",
      "Low " + temp(c.lo) + "°  /  High " + temp(c.hi) + "°",
    );
  }
  return el;
}
/* Match displayed words to exact UTF-16 offsets reported by speech synthesis.
   Source metadata stays readable but is excluded from the spoken sequence. */
export function prepareSpeech(container, utterance) {
  const words = [];
  let cursor = 0,
    active = null;
  const progress = container.querySelector("progress"),
    label = container.querySelector(".reading-label");
  let reported = false;
  for (const el of container.querySelectorAll(".speech-text")) {
    const value = el.textContent,
      start = utterance.indexOf(value, cursor);
    if (start < 0 || !value) continue;
    cursor = start + value.length;
    const frag = document.createDocumentFragment();
    let at = 0;
    for (const match of value.matchAll(/\S+/gu)) {
      frag.append(value.slice(at, match.index));
      const span = node("span", "speech-word", match[0]);
      frag.append(span);
      words.push({
        el: span,
        start: start + match.index,
        end: start + match.index + match[0].length,
      });
      at = match.index + match[0].length;
    }
    frag.append(value.slice(at));
    el.replaceChildren(frag);
  }
  function clear() {
    active?.classList.remove("current");
    active = null;
  }
  return {
    boundary(index) {
      if (document.hidden) return;
      reported = true;
      clear();
      const hit =
        words.find((w) => index >= w.start && index < w.end) ||
        words.find((w) => w.start >= index);
      if (hit) {
        active = hit.el;
        active.classList.add("current");
      }
      if (progress) {
        const body = container.querySelector(".card-story .body"),
          inBody = words.filter((w) => body?.contains(w.el));
        const first = inBody[0]?.start || 0,
          last = inBody.at(-1)?.end || utterance.length;
        progress.value = Math.max(
          0,
          Math.min(100, ((index - first) / (last - first || 1)) * 100),
        );
        label.textContent = "Reading " + Math.round(progress.value) + "%";
      }
    },
    finish(completed = false) {
      clear();
      if (progress) {
        if (completed) {
          progress.value = 100;
          label.textContent = "Read to the end";
        } else label.textContent = reported ? "Reading paused" : "Text ready";
      }
    },
  };
}
