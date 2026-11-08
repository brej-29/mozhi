"""Compare J1 after scoring news_query as the new NEWS tool."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from jarvis.bench import data, metrics
from jarvis.bench.run import run_items
from jarvis.routers.joint import JointRouter

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"


def main():
    items = data.load("test")
    for item in items:
        if item.intent == "news_query":
            item.tool = "NEWS"
    router = JointRouter(ROOT / "models" / "joint")
    routes = run_items(router, items)
    result = metrics.score(items, routes)
    result["ci95_action_macro_f1"] = metrics.bootstrap_ci(items, routes)
    result["tool_acc_5way"] = sum(item.tool == route.tool for item, route in zip(items, routes)) / len(items)
    result.update({"system": "j1", "model": "joint", "set": "full", "split": "test"})
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "j1_joint_full_test_movednews.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (RESULTS / "j1_joint_full_test_movednews.preds.jsonl").open("w", encoding="utf-8") as stream:
        for item, route in zip(items, routes):
            stream.write(json.dumps({"id": item.id, "text": item.text, "gold": item.tool,
                                     "pred": asdict(route)}) + "\n")
    print(json.dumps({k: result[k] for k in ("action_macro_f1", "tool_acc_5way", "ci95_action_macro_f1")}))


if __name__ == "__main__":
    main()

