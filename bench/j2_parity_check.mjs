import fs from "node:fs";
import path from "node:path";
import { clean, encode } from "../mozhi/web/router2.js";

const root = process.cwd();
const tok = JSON.parse(fs.readFileSync(path.join(root, "models/joint2/tokenizer.json"), "utf8"));
const meta = JSON.parse(fs.readFileSync(path.join(root, "models/joint2/meta.json"), "utf8"));
const rows = fs.readFileSync(path.join(root, "bench/results/j2_parity.jsonl"), "utf8")
  .trim().split("\n").map(JSON.parse);
const checked = rows.map((row) => {
  const words = clean(row.text, row.lang), { ids } = encode(words, tok, meta.max_len ?? 64);
  return { lang: row.lang, index: row.index, text: row.text,
    match: JSON.stringify(words) === JSON.stringify(row.words) && JSON.stringify(ids) === JSON.stringify(row.python_ids) };
});
const mismatches = checked.filter((row) => !row.match);
const result = {
  checked: checked.length, mismatches, token_ids_match: mismatches.length === 0,
  by_language: Object.fromEntries(["en", "ta", "ml"].map((lang) => {
    const part = checked.filter((row) => row.lang === lang);
    return [lang, { checked: part.length, mismatches: part.filter((row) => !row.match).length }];
  })),
};
fs.writeFileSync(path.join(root, "bench/results/j2_parity.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
if (mismatches.length) process.exitCode = 1;
