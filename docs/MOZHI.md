# Mozhi: Tamil and Malayalam, with a respect meter

Design note and pre-registration for the third version of the project. Written before any multilingual
model was trained. The thresholds in section 5 are fixed now and are not edited after results exist; anything
that changes goes in the Deviations list at the end.

## 1. Why

The router, the decline behaviour and the evidence all stand. What the project lacked was a reason for a person
to open it: "Jarvis" is a name every assistant demo uses, and the assistant only spoke English. Most people in
Tamil Nadu and Kerala who speak to a phone do it in their own language, with a register that depends on who
they are talking to. A flat "you" is wrong in both languages. That register is the feature.

## 2. Name

| Option | Meaning | Note |
|---|---|---|
| **Mozhi** (மொழி / മൊഴി) | speech, language | Same word in both languages, neutral tone. Chosen. |
| Koottu (கூட்டு / കൂട്ട്) | company, companionship | First choice, dropped: it reads like a dating or social app. |
| Thunai (துணை / തുണ) | support, a companion | Also means a spouse, so not used. |
| Vaani (வாணி / വാണി) | speech, voice | Also a person's name. |

The name lives in one value (`app.name` in `jarvis/web/i18n.json`), so changing it is one edit. The repository
and live URL keep the old slug so existing links work. Meanings are my reading; a native speaker should confirm.
Some file names keep the earlier working name (`tests/probes_koottu.json`, `training/synth_koottu.py`) because the
pre-registration and the training scripts refer to them.

## 3. The respect meter

One dial, five positions. It changes three things together: the address term, the second-person form of the
verb, and the warmth of the wording. The user can also say whether the terms for a man or a woman apply.

| Level | Feel | Tamil | Malayalam | "You" |
|---|---|---|---|---|
| 0 | Close friend | da / di | da / di | nee |
| 1 | Warm, affectionate | thambi / thangachi | mone / mole | nee |
| 2 | Family respect | anna / akka | chetta / chechi | neenga / ningal |
| 3 | Polite, public | sir / madam | saar / madam | neenga / ningal |
| 4 | Deferential | ayya / amma, then muthalali | muthalali | neenga / ningal |

Open points, none of them guessed into the product:

- The brief named "ambra" and "ejama". I could not map "ambra" to a word I can verify, so it is not in the table.
  "Ejamaan" (master, owner) is a real Tamil term of deference and is kept as an alias at level 4.
- "Thambi/thangachi" and "mone/mole" address someone younger, so they assume the assistant is older than the
  user. They are offered as a warm level, not as a claim about anyone's age.
- All Tamil and Malayalam wording in the app is first-draft and has had no native review.

## 4. What it can do

| Tool | New | What it does | Works offline |
|---|---|---|---|
| WEATHER, SET_REMINDER, SAVE_NOTE | no | As before, now with Tamil and Malayalam phrasing | yes |
| GENERAL_QA | extended | Answers in the chosen language and register | needs an LLM |
| NEWS | yes | World headlines (desktop app reads public RSS; the hosted page cannot, browsers block it) | desktop only |
| STORY | yes | A folk tale told from a short sourced summary | yes (summary), richer with an LLM |
| VERSE | yes | A verse with its source: Thirukkural, Aathichoodi, Malayalam classics | yes |
| UNSUPPORTED | no | Still declines | yes |

### Content and rights

| Source | Use | Licence status |
|---|---|---|
| Thirukkural text (tk120404/thirukkural on GitHub) | verses and meanings | Apache-2.0 dataset of a public domain work |
| Aathichoodi, Ta Wikisource | verses | work is public domain; transcription CC BY-SA, credit kept |
| Folk Tales of Tamilnadu (K.A. Seethalakshmi, Sterling 1960), Folk Tales of Kerala (K. Jacob, Sterling 1960) | **plot beats only, written by me, with title and link** | in copyright; no text copied |
| 22 Tamil Folk Tales (Storytelling Institute 85.pdf), SFI podcast ep. 85, Kalampedia | plot beats only, with link | in copyright; no text copied |

Folk tales are retold from my own short summaries, not from the source text. Each story card shows its source
and a link, and the model is told to narrate only what the summary says.

### Voice

| Part | English | Tamil | Malayalam |
|---|---|---|---|
| Listening (browser recognition) | yes | yes (`ta-IN`), unverified here | yes (`ml-IN`), unverified here |
| Speaking, this machine's browser | David, Mark, Zira | **no voice installed** | **no voice installed** |
| Speaking, option | n/a | MMS-TTS `facebook/mms-tts-tam`, CC BY-NC | Piper `ml_IN` (arjun, meera), or MMS-TTS |

Where a browser has no voice, the app shows the text and says so. It does not silently read Tamil with an
English voice.

## 5. Pre-registered thresholds (new model, "J2")

Data: MASSIVE `en-US`, `ta-IN`, `ml-IN`, same train/dev/test splits, same intent-to-tool mapping as J1.
Tool-level macro-F1 on the MASSIVE test split of each language.

| Id | Threshold |
|---|---|
| T8 | Tamil and Malayalam test macro-F1 each at least 0.85 |
| T9 | English test macro-F1 within 0.03 of J1 (0.941), so at least 0.911 |
| T10 | int8 ONNX file at most 60 MB; p50 router latency at most 15 ms on the CPU used for J1 |
| T11 | False action rate (an action tool chosen for a request that should be declined) at most 2% per language |
| T12 | Browser (onnxruntime-web) and Python agree on the tool for at least 99% of 600 test utterances per language |
| T13 | New tools NEWS, STORY, VERSE: F1 at least 0.90 per language on a **template-held-out** split. This is synthetic evidence and is labelled so wherever it is shown |
| T14 | On the 90-phrase hand-written probe set (`tests/probes_mozhi.json`, written before training, never used for training or tuning) at least 0.80 tool accuracy per language. Small and written by one person; reported with its interval |

Known limits, stated now: MASSIVE Tamil and Malayalam are translations written in native script, not
transcripts of speech; romanised typing ("nalai mazhai varuma") and Tamil-English mixed speech are not in the
data; recogniser output in native script will be noisier than the benchmark.

## Deviations

Appended after the work, if there are any.

1. **Encoder.** The planned pruned multilingual DistilBERT was not trained to completion. The shipped J2 is a
   compact WordPiece encoder (0.9 MB int8) trained from scratch, which is the fallback the plan allowed.
2. **Synthetic templates.** The synthetic repetition count was raised from 3 to 40 and the template set expanded
   for NEWS, STORY and VERSE. T13 was not re-measured after that expansion.
3. **Browser parity (T12).** Only token ids were compared (1,800 of 1,800 matched); tool decisions in a real
   browser were not run.

## Outcomes (J2, first model)

| Id | Target | Measured | Status |
|---|---|---|---|
| T8 | Tamil and Malayalam 0.85 each | Tamil 0.818, Malayalam 0.809 | Missed |
| T9 | English at least 0.911 | 0.920 | Met |
| T10 | 60 MB, 15 ms | 0.9 MB, 0.22 ms p50 | Met |
| T11 | False actions at most 2% | 1.2%, 1.6%, 1.3% (en, ta, ml) | Met |
| T12 | 99% browser agreement | token ids only | Unverified |
| T13 | 0.90 synthetic held-out | not re-measured | Unverified |
| T14 | 0.80 probes per language | en 0.80, ta 0.80, ml 0.73 | Malayalam missed |

Full table with intervals: `bench/results/J2_REPORT.md`. The next step is a pretrained multilingual encoder.
