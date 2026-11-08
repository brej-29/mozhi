# J2 report

The report uses the saved JSON files in this directory. MASSIVE results use the
tools that have support in that language split. STORY and VERSE are absent from
MASSIVE, so they are evaluated in the separate synthetic section.

| Threshold id | Target | Measured value with 95% CI | Status |
|---|---|---|---|
| T8 | Tamil and Malayalam MASSIVE tool macro-F1 at least 0.85 each | Tamil 0.8177 [0.7916, 0.8402]; Malayalam 0.8090 [0.7792, 0.8331] | Missed |
| T9 | English action macro-F1 at least 0.911 | 0.9197 [0.8947, 0.9421] | Met by point estimate |
| T10 | int8 file at most 60 MB, p50 at most 15 ms, p95 at most 15 ms | 917706 bytes; worst p50 0.2159 ms [0.2119, 0.2192]; worst p95 0.4630 ms [0.4418, 0.4773] | Met |
| T11 | False action rate at most 0.02 per language | English 0.0119 [0.0082, 0.0171]; Tamil 0.0161 [0.0118, 0.0220]; Malayalam 0.0127 [0.0089, 0.0181] | Met by point estimates |
| T12 | Browser and Python tool decisions agree on at least 99% of 600 per language | Playwright msedge 156.0.4314.42: English 600/600 (100%), Tamil 600/600 (100%), Malayalam 600/600 (100%) against saved Python J2 decisions; no disagreeing utterances | Saved-reference browser agreement met; fresh Python Pages build unverified |
| T13 | Synthetic held-out NEWS, STORY, VERSE macro-F1 at least 0.90 per language | Unverified after the synthetic template expansion | Unverified |
| T14 | Probe tool accuracy at least 0.80 per language | English 0.8000 [0.6269, 0.9049]; Tamil 0.8000 [0.6269, 0.9049]; Malayalam 0.7333 [0.5555, 0.8582] | English and Tamil met by point estimate; Malayalam missed |

The synthetic rows are hand-written and marked synthetic in the result files.
The final model was selected from three seeds. The saved model metadata reports
seed 1, threshold 0.68, and dev action macro-F1 0.8614. Training wall time was
not captured by a single timed wrapper, so it is unverified.

J1 comparison and NEWS mapping

NEWS was moved from UNSUPPORTED to NEWS in the J2 training and benchmark
mapping. With that mapping, the saved J1 English result has action macro-F1 0.9414 [0.9164,
0.9619] and 5-way accuracy 0.9287. The earlier saved J1 seed 0 result had
action macro-F1 0.9520 and 5-way accuracy 0.9690 under the old mapping. The
action metric is not materially changed by moving NEWS, while the 5-way score
is lower because NEWS is now scored as its own tool.

Deviations and extra runs

- The available multilingual MiniLM candidate used SentencePiece, not WordPiece. The full DistilBERT and BERT candidates were not trained to completion because the final shipped encoder needed the 60 MB limit. The shipped artifact therefore uses a compact WordPiece encoder with the DistilBERT cased tokenizer vocabulary as its source. This is a planned fallback deviation.
- The first ONNX export used an attention block and failed at runtime on a longer sequence because of a static reshape. It was replaced with a dynamic-shape-safe token encoder, then retrained.
- The synthetic training repetition count was increased from 3 to 40. Dev and test templates stayed disjoint from train. The extra training and benchmark passes are reflected in the final saved result files.
- Browser follow-up: `engine.js` now selects J2 for Tamil and Malayalam script and retains J1 for English. The production J2 tokenizer matched all 1,800 saved Python token-ID cases. Real Edge WASM inference matched all 1,800 saved Python J2 tool decisions. The benchmark loads J2 directly for the English T12 comparison; production English still uses J1. All 1,200 native-script production routes matched direct J2 decisions, arguments and spans.
- The shared schema tool tuple was not changed because that file was outside the permitted edit paths. J2 carries the eight-tool mapping in its model metadata and benchmark code.
- Follow-up candidate (a) implementation is present in `training/train_joint2.py`, including pruned cased WordPiece embeddings, fp16 CUDA training, layer-size preflight, fixed threshold 0.68, and dev-only promotion. The training and export run is unverified because the managed Python executable returned access denied before starting under `uv`; the existing compact model and saved numbers above were left unchanged.
- The requested varied Tamil and Malayalam NEWS, STORY, VERSE, and note templates were added with disjoint train, dev, and test groups. Their new benchmark scores are unverified because the follow-up model was not trained.
- The saved synthetic JSON results cover the earlier 24-row-per-language synthetic set and are not used to claim a result for the expanded templates.
- Browser follow-up limitation: the requested `.venv/Scripts/python.exe` cannot start its runtime because access to its uv Python home is denied. The Pages build, fresh Python reference generation, pytest and Python-module Ruff commands were attempted and failed before Python started. For the measured saved-reference run, Node staged the static directory with both model sets and SHA-256-verified pinned runtime assets. Execution of `packaging/build_pages.py`, fresh J1/J2 server-dispatch parity, and Python slot parity remain unverified. The native Ruff executable passed.
- Tamil and Malayalam static chat weather requests were checked with mocked geocoding and forecast responses. Native city names and `language=ta` / `language=ml` reached geocoding and returned weather actions. Live weather-service reachability and speech recognition remain unverified. J2 adds 917,706 model bytes and 1,069,025 bytes including tokenizer and metadata. The existing Windows spec already includes `models/joint2`.
- Browser run details and the exact disagreement list (empty) are saved in `bench/results/j2_browser.json`. Rerun `node bench/j2_browser_check.mjs` after Python access is restored to execute the Pages builder and regenerate Python tool, argument and span references.

Commands

```text
PYTHONPATH=. .venv/Scripts/python.exe training/train_joint2.py --seeds 0,1,2 --epochs 8 --out models/joint2
PYTHONPATH=. .venv/Scripts/python.exe bench/bench_j2.py
PYTHONPATH=. .venv/Scripts/python.exe bench/j2_parity_dump.py
node bench/j2_parity_check.mjs
node bench/j2_browser_check.mjs
PYTHONPATH=. .venv/Scripts/python.exe bench/bench_j2_probe.py
PYTHONPATH=. .venv/Scripts/python.exe bench/bench_j1_news.py
PYTHONPATH=. .venv/Scripts/python.exe -m ruff check .
PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q
```

