"""J2 multilingual joint intent and slot router.

J2 keeps native-script letters and marks intact.  It is intentionally separate
from J1 so the existing English router and browser path remain unchanged.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import numpy as np

from jarvis.schema import Route

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "joint2"
SLOT_TAGS = ("O", "B-CITY", "I-CITY", "B-WHEN", "I-WHEN", "B-TITLE", "I-TITLE")
ACTION_TOOLS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE")
_SMALL = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS = ["x", "x", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_CLOCK = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
_NUM = re.compile(r"(?<![\d.])\d{1,3}(?![\d.])")
_NATIVE_DIGITS = str.maketrans(
    "௦௧௨௩௪௫௬௭௮௯൦൧൨൩൪൫൬൭൮൯", "01234567890123456789"
)


def num_words(n: int) -> str:
    if n < 20:
        return _SMALL[n]
    if n < 100:
        return _TENS[n // 10] + (" " + _SMALL[n % 10] if n % 10 else "")
    return _SMALL[n // 100] + " hundred" + (" " + num_words(n % 100) if n % 100 else "")


def _clock(m: re.Match) -> str:
    h, mm = int(m.group(1)), int(m.group(2))
    return num_words(h) + ("" if mm == 0 else " oh " + num_words(mm) if mm < 10 else " " + num_words(mm))


def language(text: str) -> str:
    if any("\u0b80" <= c <= "\u0bff" for c in text):
        return "ta"
    if any("\u0d00" <= c <= "\u0d7f" for c in text):
        return "ml"
    return "en"


def clean(text: str, lang: str | None = None) -> list[str]:
    """NFC-normalise without removing Indic marks or lowercasing native scripts."""
    lang = lang or language(text)
    t = unicodedata.normalize("NFC", text).translate(_NATIVE_DIGITS)
    if lang == "en":
        t = _CLOCK.sub(_clock, t.lower().replace("-", " "))
        t = _NUM.sub(lambda m: num_words(int(m.group(0))), t)
    else:
        t = t.replace("-", " ")
    out, cur = [], []
    for c in t:
        cat = unicodedata.category(c)
        if cat[0] in {"L", "M", "N"} or c == "_" or (c == "'" and cur):
            cur.append(c)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out


def spans(words: list[str], tags: list[str], kind: str) -> list[str]:
    out, cur = [], []
    for w, tag in zip(words, tags):
        if tag == f"B-{kind}":
            if cur:
                out.append(" ".join(cur))
            cur = [w]
        elif tag == f"I-{kind}" and cur:
            cur.append(w)
        else:
            if cur:
                out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


class JointRouter2:
    name = "J2"

    def __init__(self, model_dir: Path = MODEL_DIR, threshold: float | None = None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
        self.intents = meta["intents"]
        self.tool_of = meta["tool_of_intent"]
        self.threshold = meta["threshold"] if threshold is None else threshold
        self.max_len = int(meta.get("max_len", 64))
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tok.no_padding()
        self.tok.enable_truncation(max_length=self.max_len)
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        self.sess = ort.InferenceSession(
            str(model_dir / "model.int8.onnx"), so, providers=["CPUExecutionProvider"]
        )
        self.tools = sorted(set(self.tool_of.values()))
        self.M = np.zeros((len(self.intents), len(self.tools)), dtype=np.float32)
        for i, name in enumerate(self.intents):
            self.M[i, self.tools.index(self.tool_of[name])] = 1.0

    @classmethod
    def load(cls, threshold: float | None = None):
        return cls(threshold=threshold)

    def probs(self, words: list[str]):
        enc = self.tok.encode(words, is_pretokenized=True)
        ids = np.array([enc.ids], dtype=np.int64)
        mask = np.array([enc.attention_mask], dtype=np.int64)
        il, sl = self.sess.run(None, {"input_ids": ids, "attention_mask": mask})
        p = np.exp(il[0] - il[0].max())
        p /= p.sum()
        tag_ids = sl[0].argmax(-1)
        tags, seen = ["O"] * len(words), set()
        for pos, word in enumerate(enc.word_ids):
            if word is not None and word not in seen:
                seen.add(word)
                tags[word] = SLOT_TAGS[tag_ids[pos]]
        return p @ self.M, tags, p

    def route(self, text: str) -> Route:
        words = clean(text)
        if not words:
            return Route("UNSUPPORTED", confidence=1.0, path="empty")
        tool_probs, tags, fine = self.probs(words)
        intent = self.intents[int(fine.argmax())]
        k = int(tool_probs.argmax())
        tool, conf = self.tools[k], float(tool_probs[k])
        if tool in ACTION_TOOLS and conf < self.threshold:
            return Route("UNSUPPORTED", confidence=conf, path="abstain", intent=intent)
        args = {}
        if tool == "WEATHER":
            args["city"] = (spans(words, tags, "CITY") or [""])[0]
        elif tool == "SET_REMINDER":
            args["when"] = " ".join(spans(words, tags, "WHEN"))
            args["title"] = (spans(words, tags, "TITLE") or [""])[0]
        found = [{"kind": k.lower(), "text": value}
                 for k in ("CITY", "WHEN", "TITLE") for value in spans(words, tags, k)]
        return Route(tool, args, conf, path="fast", intent=intent, spans=found)

