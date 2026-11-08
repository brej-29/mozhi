"""Train the joint intent+slot router on MASSIVE train, tune on dev, export int8 ONNX.

    python training/train_joint.py --seed 0 --out models/joint
Test data is never read here. The abstention threshold is chosen on dev.
"""

import argparse
import difflib
import json
import random
import re
import time
import zlib
from pathlib import Path

import numpy as np
import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from mozhi.bench import data
from mozhi.routers.joint import SLOT_TAGS, clean
from training import synth

BACKBONE = "nreimers/MiniLM-L6-H384-uncased"
SLOT_KIND = {"place_name": "CITY", "event_name": "TITLE",
             **{k: "WHEN" for k in data.WHEN_LABELS}}
SEG = re.compile(r"(\[\w+ : [^\]]+\])")


def tagged(row_annot: str, utt: str):
    """Word list and BIO tags from a MASSIVE annotated utterance (None if misaligned)."""
    words, tags = [], []
    for seg in SEG.split(row_annot):
        m = data.SLOT.fullmatch(seg)
        label, text = (m.group(1), m.group(2)) if m else (None, seg)
        w = clean(text)
        kind = SLOT_KIND.get(label)
        for i, x in enumerate(w):
            words.append(x)
            tags.append("O" if not kind else ("B-" if i == 0 else "I-") + kind)
    return (words, tags) if words == clean(utt) else (None, None)


def load_split(split):
    rows = []
    for line in data.ensure_massive().read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["partition"] != split or r["intent"] == data.EXCLUDED_INTENT:
            continue
        w, t = tagged(r["annot_utt"], r["utt"])
        if w:
            rows.append((w, t, r["intent"]))
    return rows


def asr_rows(path: str, train_rows):
    """Transcribed recordings with tags carried over from the clean annotation by word alignment."""
    by_text = {}
    for w, t, i in train_rows:
        by_text.setdefault(" ".join(w), (w, t, i))
    rows, dev = [], []
    for o in json.loads(Path(path).read_text(encoding="utf-8")):
        src = by_text.get(" ".join(clean(o["gold_text"])))
        hyp = clean(o["asr_text"])
        if not src or not hyp:
            continue
        w, t, intent = src
        tags = ["O"] * len(hyp)
        for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, w, hyp, autojunk=False).get_opcodes():
            if op == "equal" or (op == "replace" and a1 - a0 == b1 - b0):
                tags[b0:b1] = t[a0:a1]
        # an I- tag must follow a tag of the same kind
        for k, x in enumerate(tags):
            if x.startswith("I-") and (k == 0 or tags[k - 1][2:] != x[2:]):
                tags[k] = "B-" + x[2:]
        # split by sentence so both recordings of a sentence land on the same side
        (dev if zlib.crc32(o["gold_text"].encode()) % 10 == 0 else rows).append((hyp, tags, intent))
    return rows, dev


class Net(nn.Module):
    def __init__(self, n_intents):
        super().__init__()
        self.enc = AutoModel.from_pretrained(BACKBONE)
        h = self.enc.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.intent = nn.Linear(h, n_intents)
        self.slot = nn.Linear(h, len(SLOT_TAGS))

    def forward(self, input_ids, attention_mask):
        x = self.enc(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        x = self.drop(x)
        return self.intent(x[:, 0]), self.slot(x)


def encode(tok, batch, intents, maxlen=40):
    enc = tok([b[0] for b in batch], is_split_into_words=True, truncation=True, max_length=maxlen,
              padding=True, return_tensors="pt")
    slot_y = torch.full(enc["input_ids"].shape, -100)
    for i, (words, tags, _) in enumerate(batch):
        prev = None
        for pos, w in enumerate(enc.word_ids(i)):
            if w is not None and w != prev:
                slot_y[i, pos] = SLOT_TAGS.index(tags[w])
            prev = w
    intent_y = torch.tensor([intents.index(b[2]) for b in batch])
    return enc, intent_y, slot_y


@torch.no_grad()
def predict(model, tok, rows, intents, dev, bs=256):
    model.eval()
    out = []
    for i in range(0, len(rows), bs):
        enc, _, _ = encode(tok, rows[i:i + bs], intents)
        il, _ = model(enc["input_ids"].to(dev), enc["attention_mask"].to(dev))
        out.append(torch.softmax(il, -1).cpu().numpy())
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--out", default="models/joint")
    ap.add_argument("--asr-train", help="Whisper transcripts of SLURP train recordings (see mozhi.bench.asr_train)")
    ap.add_argument("--no-augment", action="store_true", help="MASSIVE only (the pre-registered J1 setup)")
    a = ap.parse_args()
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    train, devset = load_split("train"), load_split("dev")
    if not a.no_augment:
        n_tr, n_dev = synth.notes(a.seed)
        train = synth.wake_word(train, random.Random(a.seed)) + n_tr + synth.greetings()
        devset = devset + n_dev
    if a.asr_train:
        noisy, noisy_dev = asr_rows(a.asr_train, train)  # dev part only tunes the abstention threshold
        devset = devset + noisy_dev
        train = train + noisy
        print("asr rows train", len(noisy), "dev", len(noisy_dev))
    intents = sorted({r[2] for r in train})
    tool_of = {i: ("SAVE_NOTE" if i == "note_save" else data.TOOL_OF_INTENT.get(i, "UNSUPPORTED")) for i in intents}
    tok = AutoTokenizer.from_pretrained(BACKBONE)
    model = Net(len(intents)).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = a.epochs * ((len(train) + a.bs - 1) // a.bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.1)
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    t0 = time.time()
    for ep in range(a.epochs):
        model.train()
        random.shuffle(train)
        tot = 0.0
        for i in range(0, len(train), a.bs):
            enc, iy, sy = encode(tok, train[i:i + a.bs], intents)
            il, sl = model(enc["input_ids"].to(dev), enc["attention_mask"].to(dev))
            loss = ce(il, iy.to(dev)) + ce(sl.reshape(-1, sl.shape[-1]), sy.to(dev).reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += loss.item()
        print(f"epoch {ep + 1} loss {tot / (len(train) / a.bs):.4f} t={time.time() - t0:.0f}s", flush=True)

    # threshold on dev: the highest-F1 value among those with false-action rate <= 1.5%
    from mozhi.bench.metrics import macro_f1, rates
    P = predict(model, tok, devset, intents, dev)
    tools = sorted(set(tool_of.values()))
    M = np.zeros((len(intents), len(tools)))
    for i, n in enumerate(intents):
        M[i, tools.index(tool_of[n])] = 1
    TP = P @ M
    gold = [tool_of[r[2]] for r in devset]
    best = (None, -1.0)
    for th in np.arange(0.3, 0.99, 0.01):
        pred = []
        for row in TP:
            k = int(row.argmax()); t = tools[k]
            pred.append("UNSUPPORTED" if t in ("WEATHER", "SET_REMINDER", "SAVE_NOTE") and row[k] < th else t)
        from mozhi.schema import action_view
        g = [action_view(x) for x in gold]; p = [action_view(x) for x in pred]
        f, far = macro_f1(g, p), rates(gold, pred)["far"]
        if far <= 0.015 and f > best[1]:
            best = (round(float(th), 2), f)
    th = best[0] if best[0] is not None else 0.5
    print("dev threshold", th, "dev action macro-F1", round(best[1], 4))

    # export
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    model.eval().cpu()
    dummy = tok([["what", "is", "the", "weather"]], is_split_into_words=True, return_tensors="pt")
    fp32 = out / "model.fp32.onnx"
    torch.onnx.export(model, (dummy["input_ids"], dummy["attention_mask"]), str(fp32),
                      input_names=["input_ids", "attention_mask"],
                      output_names=["intent_logits", "slot_logits"],
                      dynamic_axes={"input_ids": {0: "b", 1: "t"}, "attention_mask": {0: "b", 1: "t"},
                                    "intent_logits": {0: "b"}, "slot_logits": {0: "b", 1: "t"}},
                      opset_version=17, dynamo=False)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(str(fp32), str(out / "model.int8.onnx"), weight_type=QuantType.QInt8)
    fp32.unlink()
    tok.backend_tokenizer.save(str(out / "tokenizer.json"))
    (out / "meta.json").write_text(json.dumps({
        "backbone": BACKBONE, "seed": a.seed, "epochs": a.epochs, "intents": intents,
        "tool_of_intent": tool_of, "threshold": th, "dev_action_macro_f1": best[1],
        "train_rows": len(train), "dev_rows": len(devset)}, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
