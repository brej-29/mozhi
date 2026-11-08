"""Fine tune a pruned multilingual DistilBERT J2 router.

The tokenizer is built from the cased multilingual WordPiece tokenizer, then
pruned to pieces observed in the MASSIVE and synthetic train, dev, and test
text plus the five BERT special tokens. The original embedding rows are
copied into the pruned order. The exported ONNX model has the same two inputs
and outputs as the browser router.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import shutil
import tarfile
import time
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer
from tokenizers.models import WordPiece
from tokenizers.normalizers import BertNormalizer
from tokenizers.pre_tokenizers import BertPreTokenizer
from tokenizers.processors import TemplateProcessing
from torch import nn
from transformers import AutoModel, AutoTokenizer, DistilBertModel

from jarvis.bench import data
from jarvis.bench.metrics import action_view, macro_f1
from jarvis.routers.joint2 import SLOT_TAGS, clean
from training import synth_koottu

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "raw" / "massive.tar.gz"
OUT = ROOT / "models" / "joint2"
BACKBONE = "distilbert-base-multilingual-cased"
LANG_FILES = {"en": "en-US", "ta": "ta-IN", "ml": "ml-IN"}
SLOT_KIND = {
    "place_name": "CITY",
    "event_name": "TITLE",
    **{k: "WHEN" for k in data.WHEN_LABELS},
}
J2_THRESHOLD = 0.68
SPECIAL_TOKENS = ("[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]")
LAYER_OPTIONS = (6, 4, 3)


def read_massive(lang: str, split: str):
    member = f"1.0/data/{LANG_FILES[lang]}.jsonl"
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        source = archive.extractfile(member)
        if source is None:
            raise FileNotFoundError(member)
        for raw in source:
            row = json.loads(raw.decode("utf-8"))
            if row["partition"] == split and row["intent"] != data.EXCLUDED_INTENT:
                yield row


def tagged(row, lang: str):
    words, tags = [], []
    cursor = 0
    text = row["annot_utt"]
    while cursor < len(text):
        if text[cursor] == "[":
            end = text.find("]", cursor)
            if end < 0:
                break
            slot = text[cursor + 1:end]
            if " : " not in slot:
                cursor = end + 1
                continue
            label, value = slot.split(" : ", 1)
            words_in_slot = clean(value, lang)
            kind = SLOT_KIND.get(label)
            words.extend(words_in_slot)
            tags.extend(
                "O" if not kind else [f"{'B-' if i == 0 else 'I-'}{kind}"
                                       for i in range(len(words_in_slot))]
            )
            cursor = end + 1
        else:
            end = text.find("[", cursor)
            value = text[cursor:] if end < 0 else text[cursor:end]
            words_in_text = clean(value, lang)
            words.extend(words_in_text)
            tags.extend(["O"] * len(words_in_text))
            cursor = len(text) if end < 0 else end
    if words != clean(row["utt"], lang):
        return None
    return words, tags


def massive_rows(lang: str, split: str):
    rows = []
    for row in read_massive(lang, split):
        result = tagged(row, lang)
        if result:
            words, tags = result
            rows.append((words, tags, row["intent"], lang, False))
    return rows


def tool_map(intents: list[str]) -> dict[str, str]:
    out = {}
    for intent in intents:
        if intent.startswith("synthetic_news"):
            out[intent] = "NEWS"
        elif intent.startswith("synthetic_story"):
            out[intent] = "STORY"
        elif intent.startswith("synthetic_verse"):
            out[intent] = "VERSE"
        elif intent.startswith("synthetic_note") or intent == "note_save":
            out[intent] = "SAVE_NOTE"
        elif intent == "news_query":
            out[intent] = "NEWS"
        else:
            out[intent] = data.TOOL_OF_INTENT.get(intent, "UNSUPPORTED")
    return out


def load_rows(seed: int):
    train, devset, test = [], [], []
    for lang in LANG_FILES:
        train += massive_rows(lang, "train")
        devset += massive_rows(lang, "dev")
        test += massive_rows(lang, "test")
    train += synth_koottu.rows("train", seed)
    devset += synth_koottu.rows("dev", seed)
    test += synth_koottu.rows("test", seed)
    return train, devset, test


def build_tokenizer(rows):
    original = AutoTokenizer.from_pretrained(BACKBONE, use_fast=True)
    original_vocab = original.get_vocab()
    pieces = set(SPECIAL_TOKENS)
    for words, _, _, _, _ in rows:
        for word in words:
            pieces.update(original.tokenize(word, add_special_tokens=False))
    missing = sorted(piece for piece in pieces if piece not in original_vocab)
    if missing:
        raise ValueError(f"backbone tokenizer returned unknown pieces: {missing[:5]}")

    vocab = {piece: index for index, piece in enumerate(SPECIAL_TOKENS)}
    for piece in sorted(pieces.difference(SPECIAL_TOKENS), key=lambda p: original_vocab[p]):
        vocab[piece] = len(vocab)
    old_ids = [original_vocab[piece] for piece in vocab]

    tokenizer = Tokenizer(WordPiece(vocab=vocab, unk_token="[UNK]"))
    tokenizer.normalizer = BertNormalizer(
        clean_text=True,
        handle_chinese_chars=True,
        strip_accents=False,
        lowercase=False,
    )
    tokenizer.pre_tokenizer = BertPreTokenizer()
    tokenizer.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]",
        special_tokens=[("[CLS]", vocab["[CLS]"]), ("[SEP]", vocab["[SEP]"])],
    )
    return tokenizer, old_ids


def encode(tokenizer: Tokenizer, row, max_len: int):
    words, tags, _, _, _ = row
    enc = tokenizer.encode(words, is_pretokenized=True)
    ids = enc.ids[:max_len]
    word_ids = enc.word_ids[:max_len]
    slot = [-100] * len(ids)
    seen = set()
    for position, word_id in enumerate(word_ids):
        if word_id is not None and word_id not in seen and word_id < len(tags):
            slot[position] = SLOT_TAGS.index(tags[word_id])
            seen.add(word_id)
    return ids, slot


class RouterNet(nn.Module):
    """DistilBERT backbone with intent and first-piece slot heads."""

    def __init__(self, backbone: DistilBertModel, n_intents: int):
        super().__init__()
        self.backbone = backbone
        hidden = backbone.config.dim
        self.intent = nn.Linear(hidden, n_intents)
        self.slot = nn.Linear(hidden, len(SLOT_TAGS))

    def forward(self, input_ids, attention_mask):
        hidden = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        return self.intent(hidden[:, 0]), self.slot(hidden)


def make_backbone(pretrained: DistilBertModel, old_ids: list[int], layers: int):
    config = copy.deepcopy(pretrained.config)
    config.n_layers = layers
    config.vocab_size = len(old_ids)
    config.pad_token_id = 0
    backbone = DistilBertModel(config)
    with torch.no_grad():
        backbone.embeddings.word_embeddings.weight.copy_(
            pretrained.embeddings.word_embeddings.weight[old_ids]
        )
        backbone.embeddings.position_embeddings.weight.copy_(
            pretrained.embeddings.position_embeddings.weight
        )
        backbone.embeddings.LayerNorm.load_state_dict(pretrained.embeddings.LayerNorm.state_dict())
        for index in range(layers):
            backbone.transformer.layer[index].load_state_dict(
                pretrained.transformer.layer[index].state_dict()
            )
    return backbone


def batch(rows, tokenizer, intents, start, size, max_len, device):
    part = rows[start:start + size]
    encoded = [encode(tokenizer, row, max_len) for row in part]
    width = max(len(values[0]) for values in encoded)
    ids = torch.zeros((len(part), width), dtype=torch.long, device=device)
    mask = torch.zeros_like(ids)
    slots = torch.full_like(ids, -100)
    for index, (values, labels) in enumerate(encoded):
        length = len(values)
        ids[index, :length] = torch.tensor(values, device=device)
        mask[index, :length] = 1
        slots[index, :length] = torch.tensor(labels, device=device)
    intent_y = torch.tensor([intents.index(row[2]) for row in part], dtype=torch.long, device=device)
    return ids, mask, intent_y, slots


@torch.no_grad()
def predict(model, tokenizer, rows, intents, max_len, device, batch_size=32):
    model.eval()
    result = []
    for start in range(0, len(rows), batch_size):
        ids, mask, _, _ = batch(rows, tokenizer, intents, start, batch_size, max_len, device)
        intent_logits, _ = model(ids, mask)
        result.append(torch.softmax(intent_logits, -1).cpu().numpy())
    return np.concatenate(result)


def decision(probs, rows, intents, tool_of, threshold=J2_THRESHOLD):
    tools = sorted(set(tool_of.values()))
    matrix = np.zeros((len(intents), len(tools)), dtype=np.float32)
    for index, intent in enumerate(intents):
        matrix[index, tools.index(tool_of[intent])] = 1
    tool_probs = probs @ matrix
    output = []
    for row in tool_probs:
        index = int(row.argmax())
        tool = tools[index]
        if tool in ("WEATHER", "SET_REMINDER", "SAVE_NOTE") and row[index] < threshold:
            tool = "UNSUPPORTED"
        output.append(tool)
    return output


def dev_score(probs, rows, intents, tool_of):
    gold = [tool_of[row[2]] for row in rows]
    pred = decision(probs, rows, intents, tool_of)
    return macro_f1([action_view(value) for value in gold], [action_view(value) for value in pred])


def train_one(seed, train, devset, tokenizer, intents, tool_of, pretrained, old_ids, args, layers):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(args.threads)
    model = RouterNet(make_backbone(pretrained, old_ids, layers), len(intents)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
    order = list(range(len(train)))
    started = time.time()
    scaler = torch.cuda.amp.GradScaler(enabled=device.type == "cuda")
    for epoch in range(args.epochs):
        random.shuffle(order)
        model.train()
        total = 0.0
        for position in range(0, len(order), args.bs):
            selected = [train[i] for i in order[position:position + args.bs]]
            ids, mask, intent_y, slots = batch(
                selected, tokenizer, intents, 0, len(selected), args.max_len, device
            )
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.float16,
                                enabled=device.type == "cuda"):
                intent_logits, slot_logits = model(ids, mask)
                loss = loss_fn(intent_logits, intent_y) + loss_fn(
                    slot_logits.reshape(-1, slot_logits.shape[-1]), slots.reshape(-1)
                )
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total += float(loss.detach().cpu())
        print(
            f"seed {seed} layers {layers} epoch {epoch + 1} "
            f"loss {total / max(1, len(train) / args.bs):.4f} "
            f"t={time.time() - started:.0f}s device={device}",
            flush=True,
        )
    dev_probs = predict(model, tokenizer, devset, intents, args.max_len, device, args.eval_bs)
    return model, dev_score(dev_probs, devset, intents, tool_of)


def export_onnx(model, tokenizer, intents, tool_of, seed, dev_f1, out, args, layers,
                dropped_top=0, preflight=False):
    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    device = next(model.parameters()).device
    dummy = torch.ones((1, 8), dtype=torch.long, device=device)
    mask = torch.ones_like(dummy)
    fp32 = out / "model.fp32.onnx"
    torch.onnx.export(
        model,
        (dummy, mask),
        str(fp32),
        input_names=["input_ids", "attention_mask"],
        output_names=["intent_logits", "slot_logits"],
        dynamic_axes={
            "input_ids": {0: "b", 1: "t"},
            "attention_mask": {0: "b", 1: "t"},
            "intent_logits": {0: "b"},
            "slot_logits": {0: "b", 1: "t"},
        },
        opset_version=17,
        dynamo=False,
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic

    int8 = out / "model.int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    fp32.unlink()
    size = int8.stat().st_size
    if preflight:
        return size
    tokenizer.save(str(out / "tokenizer.json"))
    (out / "meta.json").write_text(
        json.dumps(
            {
                "backbone": BACKBONE,
                "encoder": "distilbert_pruned_wordpiece",
                "layers": layers,
                "dropped_top_layers": dropped_top,
                "vocab_size": tokenizer.get_vocab_size(),
                "max_len": args.max_len,
                "seed": seed,
                "epochs": args.epochs,
                "intents": intents,
                "tool_of_intent": tool_of,
                "threshold": J2_THRESHOLD,
                "dev_action_macro_f1": dev_f1,
                "model_bytes": size,
                "train_rows": args.train_rows,
                "dev_rows": args.dev_rows,
                "languages": ["en", "ta", "ml"],
                "synthetic": "training and template-held-out evaluation rows are marked synthetic",
                "preflight_layer_sizes": args.layer_sizes,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return size


def preflight_sizes(pretrained, old_ids, tokenizer, intents, layers, args):
    work = ROOT / "models" / ".j2_preflight"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    sizes = {}
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    for count in layers:
        model = RouterNet(make_backbone(pretrained, old_ids, count), len(intents)).to(device)
        size = export_onnx(
            model,
            tokenizer,
            intents,
            {},
            0,
            0.0,
            work / str(count),
            args,
            count,
            dropped_top=6 - count,
            preflight=True,
        )
        sizes[str(count)] = size
        print(f"preflight layers {count} int8_bytes {size}", flush=True)
    shutil.rmtree(work)
    return sizes


def promote(candidate: Path, out: Path, dev_f1: float, old_dev: float | None):
    if old_dev is not None and dev_f1 <= old_dev:
        return False
    small = out.with_name("joint2_small")
    if out.exists():
        if small.exists():
            raise FileExistsError(f"refusing to overwrite {small}")
        out.rename(small)
    candidate.rename(out)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--eval-bs", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--layers", default="auto")
    args = ap.parse_args()

    train, devset, test = load_rows(0)
    all_rows = train + devset + test
    tokenizer, old_ids = build_tokenizer(all_rows)
    intents = sorted({row[2] for row in all_rows})
    tool_of = tool_map(intents)
    print("rows", len(train), len(devset), len(test), "vocab", tokenizer.get_vocab_size(), flush=True)

    pretrained = AutoModel.from_pretrained(BACKBONE)
    requested = LAYER_OPTIONS if args.layers == "auto" else tuple(
        int(value) for value in args.layers.split(",") if value.strip()
    )
    if not requested or any(value < 1 or value > 6 for value in requested):
        raise ValueError("layers must be a comma-separated subset of 1..6")
    args.train_rows = len(train)
    args.dev_rows = len(devset)
    args.layer_sizes = preflight_sizes(
        pretrained, old_ids, tokenizer, intents, requested, args
    )
    layers = next(
        (value for value in requested if args.layer_sizes[str(value)] <= 60 * 1024 * 1024),
        None,
    )
    if layers is None:
        layers = requested[-1]
        print("no preflight layer count fits 60 MB; using smallest requested count", flush=True)
    elif layers != 6:
        print(f"dropped top layers: {6 - layers}", flush=True)

    candidate = Path(args.out).with_name(Path(args.out).name + "_candidate")
    if candidate.exists():
        shutil.rmtree(candidate)
    best = None
    for seed_text in args.seeds.split(","):
        if not seed_text.strip():
            continue
        seed = int(seed_text)
        model, dev_f1 = train_one(
            seed,
            train,
            devset,
            tokenizer,
            intents,
            tool_of,
            pretrained,
            old_ids,
            args,
            layers,
        )
        print("seed result", seed, dev_f1, flush=True)
        if best is None or dev_f1 > best[2]:
            best = (seed, model, dev_f1)
    if best is None:
        raise ValueError("no seeds supplied")

    seed, model, dev_f1 = best
    args.layer_sizes = {key: int(value) for key, value in args.layer_sizes.items()}
    export_onnx(
        model,
        tokenizer,
        intents,
        tool_of,
        seed,
        dev_f1,
        candidate,
        args,
        layers,
        dropped_top=6 - layers,
    )
    out = Path(args.out)
    old_meta = out / "meta.json"
    old_dev = None
    if old_meta.exists():
        old_dev = json.loads(old_meta.read_text(encoding="utf-8")).get("dev_action_macro_f1")
    promoted = promote(candidate, out, dev_f1, old_dev)
    metadata_path = out / "meta.json" if promoted else candidate / "meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["promoted"] = promoted
    metadata["old_dev_action_macro_f1"] = old_dev
    metadata["seed_count"] = len([x for x in args.seeds.split(",") if x.strip()])
    metadata["seed_selection"] = "best dev action macro-F1"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        "saved", str(out if promoted else candidate), "promoted", promoted,
        "seed", seed, "threshold", J2_THRESHOLD, "dev_f1", dev_f1, flush=True
    )


if __name__ == "__main__":
    main()
