"""Fresh J2 and server-dispatch references for the fixed 600-per-language sample."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from mozhi.routers.joint import JointRouter
from mozhi.routers.joint2 import JointRouter2, clean, language

ROOT = Path(__file__).resolve().parents[1]


def main():
    j1, j2 = JointRouter.load(), JointRouter2.load()
    rows = []
    sample = ROOT / "bench/results/j2_parity.jsonl"
    for line in sample.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        text = row["text"]
        row["j2_route"] = asdict(j2.route(text))
        selected = j2 if language(text) != "en" else j1
        row["server_route"] = asdict(selected.route(text))
        row["words"] = clean(text)
        row["python_ids"] = j2.tok.encode(row["words"], is_pretokenized=True).ids
        row["python_tool"] = row["j2_route"]["tool"]
        rows.append(row)
    Path(sys.argv[1]).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} fresh Python references")


if __name__ == "__main__":
    main()
