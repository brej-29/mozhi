import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const tok = JSON.parse(fs.readFileSync(path.join(root, "models", "joint2", "tokenizer.json"), "utf8"));
const vocab = tok.model.vocab;
const rows = fs.readFileSync(path.join(root, "bench", "results", "j2_parity.jsonl"), "utf8")
  .trim().split("\n").map((line) => JSON.parse(line));

function wordpiece(piece) {
  const chars = [...piece];
  if (chars.length > 100) return [vocab["[UNK]"]];
  const out = [];
  let start = 0;
  while (start < chars.length) {
    let end = chars.length;
    let found = null;
    while (start < end) {
      const candidate = (start ? "##" : "") + chars.slice(start, end).join("");
      if (Object.hasOwn(vocab, candidate)) { found = vocab[candidate]; break; }
      end -= 1;
    }
    if (found === null) return [vocab["[UNK]"]];
    out.push(found);
    start = end;
  }
  return out;
}

function encode(words) {
  const ids = [vocab["[CLS]"]];
  for (const word of words) {
    let current = "";
    for (const c of [...word]) {
      const code = c.codePointAt(0);
      const punct = (code >= 33 && code <= 47) || (code >= 58 && code <= 64) ||
        (code >= 91 && code <= 96) || (code >= 123 && code <= 126) || /\p{P}/u.test(c);
      if (punct) {
        if (current) ids.push(...wordpiece(current));
        ids.push(...wordpiece(c));
        current = "";
      } else current += c;
    }
    if (current) ids.push(...wordpiece(current));
  }
  ids.push(vocab["[SEP]"]);
  return ids;
}

const checked = rows.map((row) => ({ ...row, js_ids: encode(row.words) }));
const mismatches = checked.filter((row) => JSON.stringify(row.js_ids) !== JSON.stringify(row.python_ids));
const result = {
  checked: checked.length,
  mismatches: mismatches.length,
  token_ids_match: mismatches.length === 0,
  browser_tool_agreement: "unverified: onnxruntime-web assets were not available in this checkout",
  by_language: Object.fromEntries(["en", "ta", "ml"].map((lang) => {
    const part = checked.filter((row) => row.lang === lang);
    return [lang, { checked: part.length, mismatches: part.filter((row) => JSON.stringify(row.js_ids) !== JSON.stringify(row.python_ids)).length }];
  })),
};
fs.writeFileSync(path.join(root, "bench", "results", "j2_parity.json"), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));

