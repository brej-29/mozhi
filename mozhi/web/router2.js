/* Browser port of mozhi/routers/joint2.py for the shipped cased WordPiece model. */
export function language(text) {
  if (/[\u0b80-\u0bff]/u.test(text)) return "ta";
  if (/[\u0d00-\u0d7f]/u.test(text)) return "ml";
  return "en";
}
const SMALL = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(" ");
const TENS = "x x twenty thirty forty fifty sixty seventy eighty ninety".split(" ");
function numWords(n) {
  if (n < 20) return SMALL[n];
  if (n < 100) return TENS[Math.floor(n / 10)] + (n % 10 ? " " + SMALL[n % 10] : "");
  return SMALL[Math.floor(n / 100)] + " hundred" + (n % 100 ? " " + numWords(n % 100) : "");
}
function decimal(text) {
  return Number([...text].map((c) => {
    let start = c.codePointAt(0);
    while (/\p{Nd}/u.test(String.fromCodePoint(start - 1))) start--;
    return (c.codePointAt(0) - start) % 10;
  }).join(""));
}
export function clean(text, lang = language(text)) {
  let t = text.normalize("NFC").replace(/[௦-௯൦-൯]/gu, (c) => String(c.codePointAt(0) - (c <= "௯" ? 0x0be6 : 0x0d66))).replace(/-/g, " ");
  if (lang === "en") {
    t = t.toLowerCase().replace(/(?<![\p{Nd}:])(\p{Nd}{1,2}):(\p{Nd}{2})(?![\p{Nd}:])/gu, (_, h, m) => numWords(decimal(h)) + (decimal(m) === 0 ? "" : decimal(m) < 10 ? " oh " + numWords(decimal(m)) : " " + numWords(decimal(m))));
    t = t.replace(/(?<![\p{Nd}.])\p{Nd}{1,3}(?![\p{Nd}.])/gu, (m) => numWords(decimal(m)));
  }
  const words = []; let current = "";
  for (const c of t) {
    if (/[\p{L}\p{M}\p{N}_]/u.test(c) || (c === "'" && current)) current += c;
    else if (current) { words.push(current); current = ""; }
  }
  if (current) words.push(current);
  return words;
}
function wordpiece(piece, model) {
  const vocab = model.vocab, chars = [...piece];
  if (chars.length > model.max_input_chars_per_word) return [vocab[model.unk_token]];
  const ids = []; let start = 0;
  while (start < chars.length) {
    let end = chars.length, found;
    while (start < end) {
      const candidate = (start ? model.continuing_subword_prefix : "") + chars.slice(start, end).join("");
      if (Object.hasOwn(vocab, candidate)) { found = vocab[candidate]; break; }
      end--;
    }
    if (found === undefined) return [vocab[model.unk_token]];
    ids.push(found); start = end;
  }
  return ids;
}
export function encode(words, tokenizer, maxLen = 64) {
  // The shipped tokenizer has no normalizer and uses Rust Unicode Whitespace
  // (word runs and punctuation runs), rather than J1's uncased Bert tokenizer.
  if (tokenizer.normalizer !== null || tokenizer.pre_tokenizer?.type !== "Whitespace") throw new Error("Unsupported J2 tokenizer configuration");
  const vocab = tokenizer.model.vocab, ids = [vocab["[CLS]"]], first = [];
  for (const [wi, word] of words.entries()) {
    const pieces = word.match(/[\p{L}\p{M}\p{N}\p{Pc}\u200c\u200d]+|[^\p{L}\p{M}\p{N}\p{Pc}\u200c\u200d\s]+/gu) || [];
    for (const piece of pieces) {
      if (ids.length >= maxLen - 1) break;
      if (first[wi] === undefined) first[wi] = ids.length;
      ids.push(...wordpiece(piece, tokenizer.model).slice(0, maxLen - 1 - ids.length));
    }
  }
  ids.push(vocab["[SEP]"]);
  return { ids, first };
}
const SLOT_TAGS = ["O", "B-CITY", "I-CITY", "B-WHEN", "I-WHEN", "B-TITLE", "I-TITLE"];
export function spans(words, tags, kind) {
  const out = []; let current = [];
  words.forEach((word, i) => {
    if (tags[i] === "B-" + kind) { if (current.length) out.push(current.join(" ")); current = [word]; }
    else if (tags[i] === "I-" + kind && current.length) current.push(word);
    else { if (current.length) out.push(current.join(" ")); current = []; }
  });
  if (current.length) out.push(current.join(" "));
  return out;
}
export async function loadRouter2(ort, model = "model2/") {
  const [meta, tokenizer, bytes] = await Promise.all([
    fetch(model + "meta.json").then((r) => r.json()),
    fetch(model + "tokenizer.json").then((r) => r.json()),
    fetch(model + "model.int8.onnx").then((r) => r.arrayBuffer()),
  ]);
  const session = await ort.InferenceSession.create(new Uint8Array(bytes), { executionProviders: ["wasm"] });
  const tools = [...new Set(Object.values(meta.tool_of_intent))].sort();
  async function route(text) {
    const start = performance.now(), words = clean(text);
    const scores = Object.fromEntries(tools.map((tool) => [tool, 0]));
    const base = { tool: "UNSUPPORTED", confidence: 1, intent: "", path: "empty", args: {}, spans: [], scores, words };
    if (!words.length) return { ...base, ms: performance.now() - start };
    const { ids, first } = encode(words, tokenizer, meta.max_len ?? 64), n = ids.length;
    const output = await session.run({
      input_ids: new ort.Tensor("int64", BigInt64Array.from(ids, BigInt), [1, n]),
      attention_mask: new ort.Tensor("int64", new BigInt64Array(n).fill(1n), [1, n]),
    });
    const logits = output.intent_logits.data, slots = output.slot_logits.data;
    const max = Math.max(...logits), exp = Array.from(logits, (v) => Math.exp(v - max)), sum = exp.reduce((a, b) => a + b, 0);
    let best = 0;
    exp.forEach((value, i) => { scores[meta.tool_of_intent[meta.intents[i]]] += value / sum; if (value > exp[best]) best = i; });
    const intent = meta.intents[best];
    const tool = tools.reduce((a, b) => scores[b] > scores[a] ? b : a), confidence = scores[tool];
    if (["WEATHER", "SET_REMINDER", "SAVE_NOTE"].includes(tool) && confidence < meta.threshold) return { ...base, confidence, intent, path: "abstain", ms: performance.now() - start };
    const tags = words.map((_, wi) => {
      const position = first[wi];
      if (position === undefined) return "O";
      let k = 0;
      for (let j = 1; j < SLOT_TAGS.length; j++) if (slots[position * SLOT_TAGS.length + j] > slots[position * SLOT_TAGS.length + k]) k = j;
      return SLOT_TAGS[k];
    });
    const args = {};
    if (tool === "WEATHER") args.city = spans(words, tags, "CITY")[0] || "";
    if (tool === "SET_REMINDER") { args.when = spans(words, tags, "WHEN").join(" "); args.title = spans(words, tags, "TITLE")[0] || ""; }
    const found = ["CITY", "WHEN", "TITLE"].flatMap((kind) => spans(words, tags, kind).map((text) => ({ kind: kind.toLowerCase(), text })));
    return { ...base, tool, confidence, intent, path: "fast", args, spans: found, ms: performance.now() - start };
  }
  return { meta, route };
}
