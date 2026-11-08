"""Collect bench/results/*.json into mozhi/web/results.json and bench/results/SUMMARY.md.

    python bench/summarize.py
Every number is read from a result file, never typed by hand.
"""

import json
import statistics as st
from pathlib import Path

from mozhi.bench import data, metrics
from mozhi.schema import Route

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "bench" / "results"
SHIPPED = "j1_asr_seed"  # the model in models/joint is seed 0 of this family, picked on dev


def load(name):
    p = R / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def preds(name):
    p = R / f"{name}.preds.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def row(rid, label, group, res):
    lo, hi = res["ci95_action_macro_f1"]
    return {"id": rid, "label": label, "group": group, "n": res["n"], "f1": res["action_macro_f1"],
            "lo": lo, "hi": hi, "far": res["far"], "miss": res["miss"], "honesty": res["honesty"],
            "city": res["city_acc"], "when": res["when_acc"], "valid": res["valid_rate"],
            "p50": res["p50_ms"], "p95": res["p95_ms"]}


def seeds(prefix, tag):
    runs = [r for r in (load(f"{prefix}{s}_{tag}") for s in range(3)) if r]
    keys = ("action_macro_f1", "far", "honesty", "city_acc", "when_acc", "miss")
    out = {k: [st.mean(r[k] for r in runs), st.pstdev(r[k] for r in runs)] for k in keys} if runs else {}
    out["values"] = [r["action_macro_f1"] for r in runs]
    return out


def routes(rows):
    return [Route(r["pred"]["tool"], r["pred"]["args"]) for r in rows]


SYSTEMS = [
    ("R0", "Keyword rules", "base", "r0_{t}"),
    ("M1", "TF-IDF + logistic regression", "fast", "m1_{t}"),
    ("J1v0", "Joint model, MASSIVE only (pre-registered)", "fast", "j1_joint_seed0_{t}"),
    ("J1", "Joint model, shipped (speech-aware)", "fast", "j1_asr_seed0_{t}"),
    ("C1", "Cascade: joint model, small LLM when unsure", "fast", "c1_asr_seed0_{t}"),
    ("L1-7B", "Constrained JSON prompt, Mistral 7B (GPU)", "llm", "l1_mistral-7b_{t}_gpu"),
    ("L0-7B", "Jarvis V1 prompt, Mistral 7B (GPU)", "llm", "l0_mistral-7b_{t}_gpu"),
    ("L1-1.5B", "Constrained JSON prompt, Qwen2.5 1.5B", "llm", "l1_qwen2.5-1.5b_{t}"),
    ("L0-1.5B", "Jarvis V1 prompt, Qwen2.5 1.5B", "llm", "l0_qwen2.5-1.5b_{t}"),
    ("L0x-1.5B", "V1 prompt without pasted docs, Qwen2.5 1.5B", "llm", "l0x_qwen2.5-1.5b_{t}"),
    ("L1-0.5B", "Constrained JSON prompt, Qwen2.5 0.5B", "llm", "l1_qwen2.5-0.5b_{t}"),
    ("L0-0.5B", "Jarvis V1 prompt, Qwen2.5 0.5B", "llm", "l0_qwen2.5-0.5b_{t}"),
]


def main():
    out = {"rows": {"full": [], "subset": []}}
    for tag in ("full", "subset"):
        for rid, label, group, pat in SYSTEMS:
            res = load(pat.format(t=f"{tag}_test"))
            if res:
                out["rows"][tag].append(row(rid, label, group, res))
    out["seeds"] = {"J1v0": seeds("j1_joint_seed", "full_test"), "J1aug": seeds("j1_aug_seed", "full_test"),
                    "J1": seeds(SHIPPED, "full_test")}
    out["seeds_asr"] = {"J1": seeds(SHIPPED, "full_test_asr"), "J1aug": seeds("j1_aug_seed", "full_test_asr_numnorm")}
    out["latency"] = load("latency")
    out["bugs"] = load("v1_bugs")

    # paired differences on the shared subset: shipped router minus each LLM
    items = {i.id: i for i in data.load("test")}
    base = preds("j1_asr_seed0_subset_test")
    out["paired"] = []
    for rid, _, group, pat in SYSTEMS:
        if group != "llm":
            continue
        other = preds(pat.format(t="subset_test"))
        if base and len(other) == len(base):
            m, lo, hi = metrics.paired_diff_ci([items[r["id"]] for r in base], routes(base), routes(other))
            out["paired"].append({"vs": rid, "diff": m, "lo": lo, "hi": hi})

    # real speech: same clips, gold text versus Whisper transcripts
    asr = {"rows": []}
    for rid, name in (("R0", "r0"), ("M1", "m1"), ("J1v0", "j1_joint_seed0"), ("J1aug", "j1_aug_seed0"),
                      ("J1", "j1_asr_seed0"), ("L1-1.5B", "l1_qwen2.5-1.5b"), ("L1-7B", "l1_mistral-7b")):
        clean = (load(f"{name}_full_test_asrclean") or load(f"{name}_subset_test_asrclean")
                 or load(f"{name}_test_asrclean"))
        noisy = ((load(f"{name}_full_test_asr_numnorm") if name == "j1_aug_seed0" else None)
                 or load(f"{name}_full_test_asr") or load(f"{name}_subset_test_asr") or load(f"{name}_test_asr"))
        if clean and noisy:
            asr["rows"].append({"id": rid, "clean": clean["action_macro_f1"], "asr": noisy["action_macro_f1"],
                                "far_clean": clean["far"], "far_asr": noisy["far"], "miss_asr": noisy["miss"],
                                "honesty_asr": noisy["honesty"], "n": noisy["n"]})
    try:
        import jiwer

        strip = jiwer.RemovePunctuation()
        sizes = []
        for m in ("tiny.en", "base.en", "small.en", "medium.en"):
            f = data.RAW / "asr" / f"slurp_whisper_{m}.json"
            res = load(f"j1_asr_seed0_full_test_asr_{m.split('.')[0]}")
            if f.exists():
                recs = json.loads(f.read_text(encoding="utf-8"))
                hyp = [strip(o["asr_text"].lower()).strip() or "x" for o in recs]
                wer = jiwer.wer([o["gold_text"] for o in recs], hyp)
                sizes.append({"model": m, "wer": wer, "n": len(recs), "f1": res["action_macro_f1"] if res else None,
                              "far": res["far"] if res else None})
        asr["sizes"] = sizes
    except ImportError:
        asr["sizes"] = []
    out["asr"] = asr

    # abstention threshold sweep (shipped model)
    sweep = []
    for th in ("0.0", "0.5", "0.8", "0.9", "0.95", "0.99"):
        c, a = load(f"j1_asr_seed0_full_test_th{th}"), load(f"j1_asr_seed0_full_test_asr_th{th}")
        if c and a:
            sweep.append({"th": float(th), "clean": {k: c[k] for k in ("action_macro_f1", "far", "miss")},
                          "asr": {k: a[k] for k in ("action_macro_f1", "far", "miss")}})
    out["sweep"] = sweep

    (ROOT / "mozhi" / "web" / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    def f(v):
        return "n/a" if v is None else f"{v:.3f}"

    lines = ["| system | n | action macro-F1 (95% CI) | FAR | miss | honesty | city | when | valid | p50 ms | p95 ms |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for tag in ("full", "subset"):
        lines.append(f"| **{tag} set** | | | | | | | | | | |")
        for r in out["rows"][tag]:
            lines.append(f"| {r['id']} | {r['n']} | {r['f1']:.3f} ({r['lo']:.3f} to {r['hi']:.3f}) | {r['far']:.3f} | "
                         f"{r['miss']:.3f} | {r['honesty']:.3f} | {f(r['city'])} | {f(r['when'])} | {r['valid']:.2f} | "
                         f"{r['p50']:.1f} | {r['p95']:.1f} |")
    (R / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(json.dumps({k: out[k] for k in ("seeds", "paired")}, indent=1)[:1800])


if __name__ == "__main__":
    main()
