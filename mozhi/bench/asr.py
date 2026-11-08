"""Real-speech robustness set: SLURP test recordings -> Whisper -> transcripts.

SLURP (Bastianelli et al. 2020) is the source of MASSIVE's English text. We keep only recordings
whose sentence is a MASSIVE *test* utterance and appears in neither train nor dev, so no router has
seen the text. One recording per sentence, stratified like the LLM subset. Audio is never copied
into the repo; only WER and transcripts' effect on routing are reported.

    python -m jarvis.bench.asr --model base.en
"""

import argparse
import io
import json
import random
from pathlib import Path

from jarvis.bench import data

SLURP = data.RAW / "slurp" / "test0.parquet"


def whisper(model: str, device: str = "cpu"):
    """faster-whisper model. On Windows the CUDA DLLs shipped inside torch are reused for the GPU."""
    import os
    import sys

    if device == "cuda":
        lib = Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
        os.add_dll_directory(str(lib))
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ["PATH"]

    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    # a plain local copy avoids the symlink privilege that Windows hub caches need
    local = snapshot_download(f"Systran/faster-whisper-{model}", local_dir=str(data.RAW / "whisper" / model))
    return WhisperModel(local, device=device, compute_type="float16" if device == "cuda" else "int8")


def pick(seed: int = 0, per_tool: int = 100, unsupported: int = 200):
    train_dev = {i.text for s in ("train", "dev") for i in data.load(s)}
    test = {}
    for i in data.load("test"):
        if i.text not in train_dev:
            test.setdefault(i.text, []).append(i)
    # drop sentences whose MASSIVE copies disagree on the tool
    test = {t: v[0] for t, v in test.items() if len({x.tool for x in v}) == 1}
    return test, random.Random(seed), per_tool, unsupported


def main():
    import jiwer
    import pyarrow.parquet as pq
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()
    by_text, rng, per_tool, unsup = pick()
    f = pq.ParquetFile(SLURP)
    rows = {}
    for g in range(f.num_row_groups):
        t = f.read_row_group(g, columns=["sentence", "audio"]).to_pylist()
        for r in t:
            s = r["sentence"].strip().lower()
            if s in by_text and s not in rows:
                rows[s] = r["audio"]["bytes"]
    chosen = []
    for tool in ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "UNSUPPORTED"):
        pool = sorted(s for s in rows if by_text[s].tool == tool)
        chosen += rng.sample(pool, min(unsup if tool == "UNSUPPORTED" else per_tool, len(pool)))
    if a.limit:
        chosen = chosen[: a.limit]
    print(len(rows), "usable sentences;", len(chosen), "chosen")
    wm = whisper(a.model, a.device)
    out = []
    for n, s in enumerate(chosen):
        audio, sr = sf.read(io.BytesIO(rows[s]), dtype="float32")
        segs, _ = wm.transcribe(audio, language="en", beam_size=1, vad_filter=False)
        hyp = " ".join(x.text.strip() for x in segs).strip()
        out.append({"id": by_text[s].id, "gold_text": s, "asr_text": hyp, "tool": by_text[s].tool,
                    "wer": jiwer.wer(s, jiwer.RemovePunctuation()(hyp.lower()) or "x")})
        if n % 50 == 0:
            print(n, s, "->", hyp, flush=True)
    dest = data.RAW / "asr"
    dest.mkdir(exist_ok=True)
    (dest / f"slurp_whisper_{a.model}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    wer = jiwer.wer([o["gold_text"] for o in out],
                    [jiwer.RemovePunctuation()(o["asr_text"].lower()) for o in out])
    print("corpus WER", round(wer, 4), "n", len(out))


if __name__ == "__main__":
    main()
