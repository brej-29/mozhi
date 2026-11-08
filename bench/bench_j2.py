"""MASSIVE, synthetic, latency, and probe evaluation for J2.

The probe set is intentionally a separate command and is not read here.  Run
bench_j2.py first, then run bench_j2_probe.py once as the final evaluation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from mozhi.routers.joint2 import ACTION_TOOLS, JointRouter2
from training import synth_koottu
from training.train_joint2 import LANG_FILES, massive_rows, tool_map

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"
LABELS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "NEWS", "STORY", "VERSE", "UNSUPPORTED")
ACTION_LABELS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "NO_ACTION")


def macro_f1(gold, pred, labels=None):
    labels = tuple(labels or sorted(set(gold)))
    vals = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        vals.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return float(np.mean(vals))


def per_label(gold, pred):
    return {label: macro_f1(gold, pred, (label,)) for label in LABELS}


def bootstrap(gold, pred, labels, seed=0, n=2000):
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        idx = rng.integers(0, len(gold), len(gold))
        values.append(macro_f1([gold[i] for i in idx], [pred[i] for i in idx], labels))
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def wilson(success, total):
    if not total:
        return [None, None]
    z = 1.959963984540054
    p = success / total
    den = 1 + z * z / total
    mid = (p + z * z / (2 * total)) / den
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / den
    return [float(mid - half), float(mid + half)]


def latency_ci(values, percentile, seed=0, n=2000):
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        idx = rng.integers(0, len(values), len(values))
        samples.append(float(np.percentile([values[i] for i in idx], percentile)))
    return [float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))]


def score(router, rows, lang, synthetic=False):
    rows = [row for row in rows if row[3] == lang]
    gold = [tool_map([row[2]])[row[2]] for row in rows]
    predicted, times = [], []
    for row in rows:
        text = " ".join(row[0])
        start = time.perf_counter()
        route = router.route(text)
        times.append((time.perf_counter() - start) * 1000)
        predicted.append(route.tool)
    far_gold = [g for g in gold if g not in ACTION_TOOLS]
    far_pred = [p for g, p in zip(gold, predicted) if g not in ACTION_TOOLS]
    far_n = sum(p in ACTION_TOOLS for p in far_pred)
    observed_labels = tuple(sorted(set(gold)))
    result = {
        "system": "j2",
        "language": lang,
        "synthetic": synthetic,
        "n": len(rows),
        "labels_with_support": list(observed_labels),
        "tool_macro_f1": macro_f1(gold, predicted, observed_labels),
        "tool_macro_f1_ci95": bootstrap(gold, predicted, observed_labels),
        "action_macro_f1": macro_f1(
            [g if g in ACTION_TOOLS else "NO_ACTION" for g in gold],
            [p if p in ACTION_TOOLS else "NO_ACTION" for p in predicted],
            ACTION_LABELS,
        ),
        "action_macro_f1_ci95": bootstrap(
            [g if g in ACTION_TOOLS else "NO_ACTION" for g in gold],
            [p if p in ACTION_TOOLS else "NO_ACTION" for p in predicted],
            ACTION_LABELS,
        ),
        "f1_per_tool": per_label(gold, predicted),
        "false_action_rate": far_n / len(far_gold) if far_gold else 0.0,
        "false_action_rate_ci95": wilson(far_n, len(far_gold)),
        "p50_ms": float(np.percentile(times, 50)),
        "p95_ms": float(np.percentile(times, 95)),
        "p50_ms_ci95": latency_ci(times, 50),
        "p95_ms_ci95": latency_ci(times, 95),
        "model_bytes": (ROOT / "models" / "joint2" / "model.int8.onnx").stat().st_size,
    }
    target_labels = ("NEWS", "STORY", "VERSE")
    target = [(g, p) for g, p in zip(gold, predicted) if g in target_labels]
    tg, tp = [x[0] for x in target], [x[1] for x in target]
    result["new_tools"] = {
        "synthetic": synthetic,
        "labels": list(target_labels),
        "n": len(tg),
        "macro_f1": macro_f1(tg, tp, target_labels) if tg else None,
        "macro_f1_ci95": bootstrap(tg, tp, target_labels) if tg else [None, None],
        "f1_per_tool": {label: macro_f1(tg, tp, (label,)) if tg else None for label in target_labels},
    }
    name = f"j2_{lang}_{'synthetic' if synthetic else 'massive'}_test.json"
    (RESULTS / name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    router = JointRouter2.load()
    meta = json.loads((ROOT / "models" / "joint2" / "meta.json").read_text(encoding="utf-8"))
    results = []
    for lang in LANG_FILES:
        results.append(score(router, massive_rows(lang, "test"), lang))
        results.append(score(router, synth_koottu.rows("test"), lang, synthetic=True))
    summary = {
        "system": "j2",
        "threshold": router.threshold,
        "selected_seed": meta["seed"],
        "dev_action_macro_f1": meta["dev_action_macro_f1"],
        "epochs": meta["epochs"],
        "train_rows": meta["train_rows"],
        "dev_rows": meta["dev_rows"],
        "model_bytes": (ROOT / "models" / "joint2" / "model.int8.onnx").stat().st_size,
        "languages": list(LANG_FILES),
        "results": [f"j2_{r['language']}_{'synthetic' if r['synthetic'] else 'massive'}_test.json" for r in results],
        "massive": [r for r in results if not r["synthetic"]],
        "synthetic": [r for r in results if r["synthetic"]],
    }
    (RESULTS / "j2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for result in results:
        print(result["language"], "synthetic" if result["synthetic"] else "massive",
              round(result["tool_macro_f1"], 4), result["tool_macro_f1_ci95"],
              "far", round(result["false_action_rate"], 4),
              "p50", round(result["p50_ms"], 3), "p95", round(result["p95_ms"], 3))


if __name__ == "__main__":
    main()

