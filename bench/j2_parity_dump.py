"""Dump the Python J2 decisions and token IDs for the browser parity sample."""

from __future__ import annotations

import json
from pathlib import Path

from mozhi.routers.joint2 import JointRouter2, clean
from training.train_joint2 import massive_rows

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bench" / "results" / "j2_parity.jsonl"


def main():
    router = JointRouter2.load()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as stream:
        for lang in ("en", "ta", "ml"):
            for index, row in enumerate(massive_rows(lang, "test")[:600]):
                words = clean(" ".join(row[0]), lang)
                enc = router.tok.encode(words, is_pretokenized=True)
                stream.write(json.dumps({
                    "lang": lang,
                    "index": index,
                    "text": " ".join(row[0]),
                    "words": words,
                    "python_ids": enc.ids,
                    "python_tool": router.route(" ".join(row[0])).tool,
                }, ensure_ascii=False) + "\n")
    print(OUT, 1800)


if __name__ == "__main__":
    main()

