"""J1: joint intent + slot router. Small transformer exported to int8 ONNX.

Runtime needs only onnxruntime, tokenizers and numpy. Training lives in training/train_joint.py.
"""

import json
import re
from pathlib import Path

import numpy as np

from mozhi.schema import Route

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "joint"
SLOT_TAGS = ("O", "B-CITY", "I-CITY", "B-WHEN", "I-WHEN", "B-TITLE", "I-TITLE")
_PUNCT = re.compile(r"[^\w\s']")
_SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["x", "x", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_CLOCK = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
_NUM = re.compile(r"(?<![\d.])\d{1,3}(?![\d.])")


def num_words(n: int) -> str:
    if n < 20:
        return _SMALL[n]
    if n < 100:
        return _TENS[n // 10] + (" " + _SMALL[n % 10] if n % 10 else "")
    return _SMALL[n // 100] + " hundred" + (" " + num_words(n % 100) if n % 100 else "")


def _clock(m: re.Match) -> str:
    h, mm = int(m.group(1)), int(m.group(2))
    return num_words(h) + ("" if mm == 0 else " oh " + num_words(mm) if mm < 10 else " " + num_words(mm))


def clean(text: str) -> list[str]:
    """Lowercase, spell small numbers out and strip punctuation, so recogniser output (which writes
    "5:30 p.m." and "7-day") looks like the training text ("five thirty p m", "seven day")."""
    t = _CLOCK.sub(_clock, text.lower().replace("-", " "))
    t = _NUM.sub(lambda m: num_words(int(m.group(0))), t)
    return _PUNCT.sub(" ", t).split()


def spans(words: list[str], tags: list[str], kind: str) -> list[str]:
    out, cur = [], []
    for w, t in zip(words, tags):
        if t == f"B-{kind}":
            if cur:
                out.append(" ".join(cur))
            cur = [w]
        elif t == f"I-{kind}" and cur:
            cur.append(w)
        else:
            if cur:
                out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


class JointRouter:
    name = "J1"

    def __init__(self, model_dir: Path = MODEL_DIR, threshold: float | None = None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
        self.intents = meta["intents"]
        self.tool_of = meta["tool_of_intent"]
        self.threshold = meta["threshold"] if threshold is None else threshold
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tok.no_padding()
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1  # single request at a time; threads only add latency here
        self.sess = ort.InferenceSession(str(model_dir / "model.int8.onnx"), so,
                                         providers=["CPUExecutionProvider"])
        self.tools = sorted(set(self.tool_of.values()))
        self.M = np.zeros((len(self.intents), len(self.tools)), dtype=np.float32)
        for i, n in enumerate(self.intents):
            self.M[i, self.tools.index(self.tool_of[n])] = 1.0

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
        first, tags, seen = enc.word_ids, ["O"] * len(words), set()
        for pos, w in enumerate(first):
            if w is not None and w not in seen:
                seen.add(w)
                tags[w] = SLOT_TAGS[tag_ids[pos]]
        return p @ self.M, tags, p

    def route(self, text: str) -> Route:
        words = clean(text)
        if not words:
            return Route("UNSUPPORTED", confidence=1.0, path="empty")
        tp, tags, fine = self.probs(words)
        intent = self.intents[int(fine.argmax())]
        k = int(tp.argmax())
        tool, conf = self.tools[k], float(tp[k])
        scores = {t: round(float(tp[i]), 4) for i, t in enumerate(self.tools)}
        if tool in ("WEATHER", "SET_REMINDER", "SAVE_NOTE") and conf < self.threshold:
            return Route("UNSUPPORTED", confidence=conf, path="abstain", intent=intent, scores=scores, words=words)
        args = {}
        if tool == "WEATHER":
            args["city"] = (spans(words, tags, "CITY") or [""])[0]
        elif tool == "SET_REMINDER":
            args["when"] = " ".join(spans(words, tags, "WHEN"))
            args["title"] = (spans(words, tags, "TITLE") or [""])[0]
        found = [{"kind": k.lower(), "text": t} for k in ("CITY", "WHEN", "TITLE") for t in spans(words, tags, k)]
        return Route(tool, args, conf, path="fast", intent=intent, spans=found, scores=scores, words=words)
