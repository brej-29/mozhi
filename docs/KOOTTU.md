# Koottu: Tamil and Malayalam, with a respect meter

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
| **Koottu** (கூட்டு / കൂട്ട്) | company, companionship | Same word and sense in both languages. Chosen. |
| Thunai (துணை / തുണ) | support, a companion | Close second. |
| Vaani (வாணி / വാണി) | speech, voice | Also a person's name; reads as one persona. |

The name lives in one constant (`APP_NAME` in `jarvis/web/i18n.js`), so changing it is one edit. The repository
and live URL keep the old slug so existing links work. Meanings are my reading; a native speaker should confirm.

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
| T14 | On the 90-phrase hand-written probe set (`tests/probes_koottu.json`, written before training, never used for training or tuning) at least 0.80 tool accuracy per language. Small and written by one person; reported with its interval |

Known limits, stated now: MASSIVE Tamil and Malayalam are translations written in native script, not
transcripts of speech; romanised typing ("nalai mazhai varuma") and Tamil-English mixed speech are not in the
data; recogniser output in native script will be noisier than the benchmark.

## Deviations

Appended after the work, if there are any.
