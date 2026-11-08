"""Run one router over the benchmark and write metrics plus per-item predictions.

    python -m mozhi.bench.run r0 --set full
    python -m mozhi.bench.run l1 --model data/raw/models/qwen2.5-1.5b-instruct-q4_k_m.gguf --set subset
"""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from mozhi.bench import data, metrics

RESULTS = data.ROOT / "bench" / "results"


def build(system: str, model: str | None, gpu: int, **kw):
    if system == "r0":
        from mozhi.routers.rules import RuleRouter

        return RuleRouter()
    if system in ("l0", "l0x", "l1"):
        from mozhi.routers.llm import LlamaRouter

        return LlamaRouter(model, mode={"l0": "v1", "l0x": "v1x"}.get(system, "min"), n_gpu_layers=gpu)
    if system == "m1":
        from mozhi.routers.linear import LinearRouter

        return LinearRouter.load()
    if system == "j2":
        from mozhi.routers.joint2 import MODEL_DIR, JointRouter2

        return JointRouter2(Path(model) if model else MODEL_DIR, threshold=kw.get("threshold"))
    if system in ("j1", "c1"):
        from mozhi.routers.joint import MODEL_DIR, JointRouter

        j = JointRouter(Path(model) if model else MODEL_DIR, threshold=kw.get("threshold"))
        if system == "j1":
            return j
        from mozhi.routers.cascade import Cascade
        from mozhi.routers.llm import LlamaRouter

        tau = Cascade.tau_for_rate(j, data.load("dev"), kw["rate"])
        print(f"cascade tau={tau:.3f} for dev fallback rate {kw['rate']}")
        return Cascade(j, LlamaRouter(kw["llm"], mode="min", n_gpu_layers=gpu), tau)
    raise SystemExit(f"unknown system {system}")


def run_items(router, items, warmup: int = 5):
    for it in items[:warmup]:
        router.route(it.text)
    routes = []
    for it in items:
        t0 = time.perf_counter()
        r = router.route(it.text)
        r.ms = (time.perf_counter() - t0) * 1000
        routes.append(r)
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("system")
    ap.add_argument("--model")
    ap.add_argument("--gpu", type=int, default=0, help="llama.cpp GPU layers (0 = CPU)")
    ap.add_argument("--set", default="full", choices=["full", "subset"])
    ap.add_argument("--split", default="test")
    ap.add_argument("--tag", default="")
    ap.add_argument("--quirky", action="store_true", help="sensitivity: include general_quirky")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--asr", help="Whisper transcript JSON from mozhi.bench.asr")
    ap.add_argument("--asr-clean", action="store_true", help="same items, gold text instead of transcripts")
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--llm", help="GGUF path for the cascade fallback")
    ap.add_argument("--rate", type=float, default=0.15, help="target dev fallback rate for c1")
    a = ap.parse_args()

    items = data.load(a.split, include_quirky=a.quirky)
    if a.set == "subset":
        items = data.llm_subset(items)
    if a.asr:
        from dataclasses import replace

        rec = {o["id"]: o for o in json.loads(Path(a.asr).read_text(encoding="utf-8"))}
        by_id = {i.id: i for i in data.load("test")}
        items = [replace(by_id[k], text=o["gold_text" if a.asr_clean else "asr_text"]) for k, o in rec.items()]
        a.tag = a.tag or ("asrclean" if a.asr_clean else "asr")
    if a.limit:
        items = items[: a.limit]
    router = build(a.system, a.model, a.gpu, threshold=a.threshold, llm=a.llm, rate=a.rate)
    routes = run_items(router, items)

    model_tag = Path(a.model).stem.split("-instruct")[0] if a.model else ""
    name = "_".join(x for x in (a.system, model_tag, a.set, a.split, a.tag, "quirky" if a.quirky else "") if x)
    res = metrics.score(items, routes)
    res["ci95_action_macro_f1"] = metrics.bootstrap_ci(items, routes)
    res["system"], res["model"], res["set"], res["split"] = a.system, model_tag, a.set, a.split
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    with (RESULTS / f"{name}.preds.jsonl").open("w", encoding="utf-8") as f:
        for it, r in zip(items, routes):
            f.write(json.dumps({"id": it.id, "text": it.text, "gold": it.tool, "city": it.city,
                                "when": it.when, "pred": asdict(r)}) + "\n")
    print(name, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()
                            if k in ("n", "action_macro_f1", "ci95_action_macro_f1", "far", "miss",
                                     "honesty", "tool_acc_5way", "city_acc", "when_acc",
                                     "p50_ms", "p95_ms", "valid_rate")}))


if __name__ == "__main__":
    main()
