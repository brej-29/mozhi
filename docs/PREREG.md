# Pre-registration: Jarvis routing benchmark

Written and committed before any router was trained or scored. Git history is the timestamp.
Anything that deviates later is listed under "Deviations" at the bottom, with the reason.

## Problem

A local voice assistant turns speech into text and must then decide, quickly and on a laptop,
which tool to call (weather, reminder, note), with which arguments, or whether to do nothing.
Two things make this harder than it sounds:

1. Acting on the wrong request has side effects (a reminder is created, a note is saved, a city
   is looked up) and a spoken assistant that bluffs ("Okay, playing music") breaks trust.
2. The text comes from speech recognition, not from a keyboard, so it carries recognition errors.

Jarvis V1 routed with a prompted small LLM that returns JSON. Its router prompt also embeds
excerpts of the project's own docs. Nothing measured how often that router is right, how often it
acts when it should not, or how long it takes.

## Tool set

`WEATHER`, `SET_REMINDER`, `SAVE_NOTE`, `GENERAL_QA`, `UNSUPPORTED`.
`UNSUPPORTED` is new: a request Jarvis has no tool for (music, smart home, email, calendar
queries and so on). V1 had no such label, so everything unsupported fell into `GENERAL_QA`.

## Data

MASSIVE 1.0, `en-US` (FitzGerald et al., 2022), licence CC BY 4.0. Official `train` / `dev` /
`test` partitions are used as given. Real speech: the SLURP test recordings (Bastianelli et al.,
2020; MASSIVE's English text is derived from SLURP), used for evaluation only and never
redistributed.

Mapping from MASSIVE intents (applied identically to every system):

| Jarvis tool | MASSIVE intents |
|---|---|
| WEATHER | weather_query |
| SET_REMINDER | alarm_set, calendar_set |
| SAVE_NOTE | lists_createoradd |
| GENERAL_QA | qa_factoid, qa_definition, qa_maths, qa_currency, general_joke, general_greet |
| UNSUPPORTED | every other intent except the excluded one below |
| excluded | general_quirky (label is a dataset catch-all, ambiguous by design) |

Sensitivity analysis (reported, not headline): `general_quirky` included as UNSUPPORTED.
Known weakness of the mapping: `lists_createoradd` is mostly "create a list" and "add X to my
list", a proxy for "save a note". `SAVE_NOTE` arguments are therefore not scored.

Argument gold (from MASSIVE slot annotations):

- WEATHER `city`: the `place_name` span, or none.
- SET_REMINDER `when`: `date`, `time`, `timeofday`, `general_frequency` spans in utterance order.
  Correct if the normalised text matches, or both parse to the same datetime with `dateparser`
  at a fixed reference time.

## Metrics

All on the `test` partition unless stated. Confidence intervals: 95% percentile bootstrap, 2000
resamples, seed 0.

- **Action macro-F1** (primary): macro-F1 over {WEATHER, SET_REMINDER, SAVE_NOTE, NO_ACTION},
  where NO_ACTION merges GENERAL_QA and UNSUPPORTED (so V1, which cannot say UNSUPPORTED, is
  scored fairly).
- **False-action rate (FAR)**: of utterances whose gold is GENERAL_QA or UNSUPPORTED, the share
  routed to an action tool.
- **Miss rate**: of gold action utterances, the share routed to NO_ACTION or to the wrong tool.
- **Honesty**: of gold UNSUPPORTED utterances, the share routed to UNSUPPORTED (not bluffed as
  GENERAL_QA).
- **Slot accuracy**: `city` exact match (case-insensitive) and `when` match, among utterances
  whose tool was routed correctly.
- **Valid-output rate**: output parses and fits the schema (LLM routers only).
- **Latency**: router only, wall-clock per request, batch size 1, after warm-up, single process,
  on the development laptop (i5-13450HX, 24 GB RAM, RTX 3050 6 GB). Reported as p50 and p95.
- **ASR robustness**: the same utterances scored on gold text and on Whisper transcripts of real
  SLURP recordings. Reported as the macro-F1 drop.

## Systems

| Id | System |
|---|---|
| R0 | Keyword rules (the floor: does this need ML at all?) |
| M1 | TF-IDF + logistic regression, intent only |
| L0 | Jarvis V1 as shipped: prompt with project-doc excerpts, JSON by prompt, one repair retry |
| L1 | Same model, minimal prompt, JSON-schema constrained decoding |
| J1 | Proposed: small joint intent+slot transformer, int8 ONNX, confidence threshold to UNSUPPORTED |
| C1 | Proposed cascade: J1, falling back to L1 when confidence is low |

LLM sizes tried: as many of Qwen2.5 0.5B / 1.5B / 3B (GGUF Q4_K_M) as fit in the time budget,
chosen before looking at results. The V1 default (Mistral 7B) is run on a smaller subset if the
GPU path works.

LLM systems are scored on a fixed stratified subset: seed 0, up to 100 test utterances per
non-UNSUPPORTED tool and 200 UNSUPPORTED. All systems are also scored on that same subset so
comparisons are like for like. Non-LLM systems are additionally scored on the full test set.

## Success thresholds for the proposed system (J1 / C1)

| Id | Claim | Threshold |
|---|---|---|
| T1 | Action macro-F1, full test, clean text | >= 0.95 |
| T2 | FAR | <= 2% |
| T3 | Router latency p95, fast path | <= 25 ms |
| T4 | Action macro-F1 minus best L0 model, LLM subset | >= +10 points, bootstrap CI of the difference excludes 0 |
| T5 | City match and when match given correct tool | >= 90% and >= 75% |
| T6 | ASR robustness drop on real SLURP audio | <= 5 points |
| T7 | Honesty (UNSUPPORTED recall) | >= 85% |

## Hypotheses about the baseline (could be wrong; reported either way)

- H1: L0 with models of 1.5B or smaller returns output that fails schema validation in >= 5% of
  requests.
- H2: L0 p50 latency is >= 10x the J1 p50.
- H3: Removing the project-doc excerpts from the L0 prompt changes macro-F1 by less than 2 points
  and cuts latency (so the excerpts are pure cost).
- H4: A TF-IDF linear model (M1) is already within 5 points of J1 on tool choice, and the gain
  of J1 is mostly slots and abstention.

## Planned ablations

- J1 without the abstention threshold.
- Threshold sweep for abstention (coverage vs FAR curve).
- C1 with LLM fallback vs C1 with plain abstention (does the LLM fallback help at all?).
- J1 trained on clean text vs with simulated recognition noise (only if T6 fails).

## Deviations

Listed in the order they happened. None changed a threshold.

1. **Commit order.** This file was written before any router was trained, but it was committed after the
   first rule-based, linear and joint runs existed locally. It has not been edited since, apart from
   appending this section and the outcomes below.
2. **Subset size.** The stratified LLM subset has 539 requests, not 600, because the test set has only 39
   note requests.
3. **Notes and wake word.** MASSIVE has no "save a note" intent, so a model trained on it alone could not
   take a note. Synthetic note phrasings (`training/synth.py`, split by content between train and dev) and a
   wake-word augmentation ("hey mozhi") were added to training. The test set is untouched. The
   MASSIVE-only model is kept and reported as `J1v0`, so the pre-registered setup is still measured.
4. **Speech.** T6 failed with a MASSIVE-only model. The planned fallback was simulated recognition noise;
   instead I used real recogniser output: 6,600 Whisper base.en transcripts of SLURP *train* recordings
   (sentences that also occur in MASSIVE dev or test are excluded), with slot tags carried over by word
   alignment. Recogniser digits are now spelled out before routing ("10" to "ten").
5. **Shipped model.** The shipped model is the speech-aware one (`J1`), seed 0 of three, chosen by dev
   macro-F1 (not test). Reported seeds: all three.
6. **Extra ablations** not in the plan: Whisper size sweep (tiny, base, small, medium), V1 prompt without the
   pasted docs (H3), a Mistral 7B run through llama.cpp on GPU (the V1 default family, but a GGUF Q4_K_M build
   rather than Ollama's tag).
7. **Latency.** Latency in the accuracy runs was measured while other jobs shared the CPU. The numbers
   reported as latency come from `mozhi.bench.latency`, run alone on an idle machine.

## Outcomes

Filled in after the runs, from `bench/results`. The Evidence page shows the same table.

| Id | Result |
|---|---|
| T1 | Met by the MASSIVE-only model (0.951 mean of 3 seeds), missed by a hair by the shipped model (0.948 mean). |
| T2 | Met (0.6% false actions). |
| T3 | Met (p95 3.4 ms). |
| T4 | Met against the V1 prompt (+46 points, CI 41 to 51). Against the fair constrained-prompt baseline the gain is +7.4 points (CI 3.8 to 11.2), under the +10 target. |
| T5 | Met (city 97.5%, time 85.5%). |
| T6 | Missed with Whisper base.en (10 points). Met with Whisper medium.en (1.7 points). |
| T7 | Met (98.6%). |
| H1 | Supported. V1 prompt output was valid for 55% (Qwen 1.5B) and 80% (Qwen 0.5B) of requests. |
| H2 | Supported. About 1,500 times slower at the median (3.3 s against 2.2 ms). |
| H3 | Refuted. Removing the pasted docs raised macro-F1 from 0.49 to 0.67 and valid output from 55% to 91%. Latency did not fall. |
| H4 | Supported. The linear model is 1.1 points behind on tool choice (0.930 against 0.941). The joint model's gain is in arguments (city 85% to 97%, time 47% to 86%). |
