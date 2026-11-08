"""Real recognition noise for training: SLURP *train* recordings -> Whisper -> transcripts.

Only recordings whose sentence is a MASSIVE train utterance are used, and any sentence that also
occurs in MASSIVE dev/test is dropped, so the transcripts cannot leak the evaluation text.
The label comes from the MASSIVE train item, the words from the recogniser.

    python -m mozhi.bench.asr_train --model base.en --device cuda --limit 8000
"""

import argparse
import io
import json
import random

from mozhi.bench import data
from mozhi.bench.asr import whisper

TRAIN_SHARDS = sorted((data.RAW / "slurp").glob("train*.parquet"))


def main():
    import pyarrow.parquet as pq
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--limit", type=int, default=8000)
    a = ap.parse_args()
    train = {}
    for i in data.load("train"):
        train.setdefault(i.text, i)
    held_out = {i.text for s in ("dev", "test") for i in data.load(s, include_quirky=True)}
    wm = whisper(a.model, a.device)
    out, seen = [], set()
    for shard in TRAIN_SHARDS:
        f = pq.ParquetFile(shard)
        for g in range(f.num_row_groups):
            for r in f.read_row_group(g, columns=["sentence", "audio"]).to_pylist():
                s = r["sentence"].strip().lower()
                if s not in train or s in held_out or len(out) >= a.limit:
                    continue
                key = (s, len([1 for o in out if o["gold_text"] == s]))
                if key[1] >= 2 or key in seen:  # at most two recordings per sentence
                    continue
                seen.add(key)
                audio, _ = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
                segs, _ = wm.transcribe(audio, language="en", beam_size=1, vad_filter=False)
                hyp = " ".join(x.text.strip() for x in segs).strip()
                it = train[s]
                out.append({"id": it.id, "gold_text": s, "asr_text": hyp, "tool": it.tool, "intent": it.intent})
                if len(out) % 500 == 0:
                    print(len(out), s, "->", hyp, flush=True)
    random.Random(0).shuffle(out)
    dest = data.RAW / "asr" / f"slurp_train_whisper_{a.model}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", len(out), "->", dest)


if __name__ == "__main__":
    main()
