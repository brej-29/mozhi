"""Final-only evaluation of the pre-registered hand-written probe set."""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.routers.joint2 import JointRouter2

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"


def wilson(success, total):
    z = 1.959963984540054
    p = success / total
    den = 1 + z * z / total
    mid = (p + z * z / (2 * total)) / den
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / den
    return [mid - half, mid + half]


def main():
    rows = json.loads((ROOT / "tests" / "probes_koottu.json").read_text(encoding="utf-8"))["rows"]
    router = JointRouter2.load()
    out = {"system": "j2", "probe_set": "tests/probes_koottu.json", "n": len(rows), "languages": {}}
    for lang in ("en", "ta", "ml"):
        part = [row for row in rows if row["lang"] == lang]
        correct = sum(router.route(row["text"]).tool == row["tool"] for row in part)
        out["languages"][lang] = {
            "n": len(part),
            "correct": correct,
            "accuracy": correct / len(part),
            "wilson95": wilson(correct, len(part)),
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "j2_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

