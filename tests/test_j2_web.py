"""Compare the production browser tokenizer with the Python J2 implementation."""

import json
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest
from tokenizers import Tokenizer

from mozhi.routers.joint2 import clean, language, spans

ROOT = Path(__file__).resolve().parents[1]


def test_browser_j2_preprocessing_and_slots():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for browser tokenizer parity")
    tokenizer = Tokenizer.from_file(str(ROOT / "models/joint2/tokenizer.json"))
    tokenizer.no_padding()
    tokenizer.enable_truncation(max_length=64)
    texts = [
        "சென்னையில் வானிலை எப்படி இருக்கிறது",
        "കൊച്ചിയിലെ കാലാവസ്ഥ എന്താണ്",
        unicodedata.normalize("NFD", "கோயம்புத்தூர் കൊച്ചി café"),
        "நாளை ௫:௩௦ மணிக்கு Meeting நினைவூட்டு",
        "നാളെ ൫:൩൦ മണിക്ക് Meeting ഓർമ്മിപ്പിക്കൂ",
        "  'hello' can't foo__bar a''b --- ",
        "Café 5:30 7-day 105",
        "at ٥:٣٠ on day १२",
        "English CAPS தமிழ் മലയാളം",
        "മലയാളം தமிழ்",
        " \u200b \u200d \ufeff ",
        "a\u0301 a\u093e \u093e",
        "a" * 101,
        " ".join(["நாளை", "കൊച്ചി", "can't"] * 80),
        "",
    ]
    rows = [{"text": text, "language": language(text), "words": clean(text)} for text in texts]
    for row in rows:
        row["ids"] = tokenizer.encode(row["words"], is_pretokenized=True).ids
    words = ["சென்னை", "மதுரை", "நாளை", "காலை", "Meeting", "with", "team"]
    tags = ["I-CITY", "B-CITY", "B-WHEN", "I-WHEN", "B-TITLE", "I-TITLE", "B-TITLE"]
    expected_spans = {kind: spans(words, tags, kind) for kind in ("CITY", "WHEN", "TITLE")}
    script = r'''
import fs from "node:fs";
import assert from "node:assert/strict";
import { clean, encode, language, spans } from "./mozhi/web/router2.js";
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const tokenizer = JSON.parse(fs.readFileSync("models/joint2/tokenizer.json", "utf8"));
for (const row of input.rows) {
  assert.equal(language(row.text), row.language);
  assert.deepEqual(clean(row.text), row.words);
  assert.deepEqual(encode(clean(row.text), tokenizer).ids, row.ids);
}
for (const kind of ["CITY", "WHEN", "TITLE"]) {
  assert.deepEqual(spans(input.words, input.tags, kind), input.spans[kind]);
}
'''
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps({"rows": rows, "words": words, "tags": tags, "spans": expected_spans}),
        text=True, capture_output=True, cwd=ROOT, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
