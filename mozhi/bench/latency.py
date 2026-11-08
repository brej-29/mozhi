"""Clean latency measurement: run with the machine otherwise idle.

    python -m jarvis.bench.latency --llm data/raw/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
Router only, batch size 1, 5 warm-up calls, 150 stratified test utterances, single process.
"""

import argparse
import json
import platform

from jarvis.bench import data
from jarvis.bench.run import RESULTS, build, run_items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm")
    ap.add_argument("--joint", default="models/aug_seed0")
    ap.add_argument("--n", type=int, default=150)
    a = ap.parse_args()
    items = data.llm_subset(data.load("test"))
    items = items[:: max(1, len(items) // a.n)][: a.n]
    out = {"n": len(items), "machine": platform.processor(), "rows": {}}
    systems = [("R0", "r0", None), ("M1", "m1", None), ("J1", "j1", a.joint)]
    if a.llm:
        systems += [("L1", "l1", a.llm), ("L0", "l0", a.llm)]
    for label, sysid, model in systems:
        routes = run_items(build(sysid, model, 0), items)
        ms = sorted(r.ms for r in routes)
        out["rows"][label] = {"p50_ms": ms[len(ms) // 2], "p95_ms": ms[int(len(ms) * 0.95)],
                              "mean_ms": sum(ms) / len(ms)}
        print(label, {k: round(v, 2) for k, v in out["rows"][label].items()}, flush=True)
    (RESULTS / "latency.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
