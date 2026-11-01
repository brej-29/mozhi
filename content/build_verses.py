"""Builds jarvis/web/content/verses.json from public-domain works.

Every work here is out of copyright (Thiruvalluvar, Avvaiyar, Poonthanam, Ezhuthachan, Kumaran Asan).
Texts come from the Thirukkural JSON dataset (Apache-2.0) and from Tamil and Malayalam Wikisource
(transcriptions are CC BY-SA, so each verse carries its source link). Run: python content/build_verses.py
Sources are fetched live; the output is committed so the app never fetches them.
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "jarvis" / "web" / "content" / "verses.json"
UA = {"User-Agent": "mozhi-content-build/0.1 (portfolio project)"}
KURAL_URL = "https://raw.githubusercontent.com/tk120404/thirukkural/master/thirukkural.json"


def fetch(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf8")


def wiki_raw(host: str, title: str) -> str:
    return fetch(f"https://{host}.wikisource.org/w/index.php?action=raw&title=" + urllib.parse.quote(title))


def wiki_url(host: str, title: str) -> str:
    return f"https://{host}.wikisource.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def strip_markup(s: str) -> str:
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"</?(?:poem|div|br|small|ref)[^>]*>", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"\(\d+\)\s*$", "", s)  # repeat markers such as (2)
    return s.strip()


def kurals() -> list[dict]:
    rows = json.loads(fetch(KURAL_URL))["kural"]
    src = {"name": "Thirukkural JSON dataset", "url": "https://github.com/tk120404/thirukkural",
           "licence": "Apache-2.0 (dataset); the work is public domain"}
    return [{"id": f"kural-{r['Number']}", "work": "திருக்குறள்", "work_en": "Thirukkural", "author": "திருவள்ளுவர்",
             "author_en": "Thiruvalluvar", "lang": "ta", "ref": str(r["Number"]),
             "lines": [r["Line1"], r["Line2"]], "meaning": {"ta": r["mv"], "en": r["explanation"]}, "source": src}
            for r in rows]


def aathichoodi() -> list[dict]:
    raw = wiki_raw("ta", "ஆத்திசூடி")
    src = {"name": "Tamil Wikisource", "url": wiki_url("ta", "ஆத்திசூடி"), "licence": "CC BY-SA 4.0 (transcription); the work is public domain"}
    out = []
    for m in re.finditer(r"^(\d+)\.\s*\{\{green\|([^}]+)\}\}\s*<br\s*/?>\s*(.+)$", raw, re.MULTILINE):
        n, line, meaning = m.group(1), strip_markup(m.group(2)), strip_markup(m.group(3))
        out.append({"id": f"aathichoodi-{n}", "work": "ஆத்திசூடி", "work_en": "Aathichoodi", "author": "ஔவையார்",
                    "author_en": "Avvaiyar", "lang": "ta", "ref": n, "lines": [line], "meaning": {"ta": meaning}, "source": src})
    return out


def stanzas(title: str, host: str, work: str, work_en: str, author: str, author_en: str, key: str, per: int, limit: int) -> list[dict]:
    raw = wiki_raw(host, title)
    body = raw.split("<poem>", 1)[1] if "<poem>" in raw else raw.split('<div class="prose">', 1)[1]
    body = body.split("</poem>")[0]
    lines = [strip_markup(x) for x in body.splitlines()]
    lines = [x for x in lines if x and not x.startswith("=") and not x.startswith("__")]
    src = {"name": "Malayalam Wikisource", "url": wiki_url(host, title), "licence": "CC BY-SA 4.0 (transcription); the work is public domain"}
    out = []
    for i in range(0, min(len(lines), per * limit), per):
        chunk = lines[i:i + per]
        if len(chunk) == per:
            out.append({"id": f"{key}-{i // per + 1}", "work": work, "work_en": work_en, "author": author, "author_en": author_en,
                        "lang": "ml", "ref": str(i // per + 1), "lines": chunk, "meaning": {}, "source": src})
    return out


def main():
    verses = (kurals() + aathichoodi()
              + stanzas("ജ്ഞാനപ്പാന", "ml", "ജ്ഞാനപ്പാന", "Jnanappana", "പൂന്താനം", "Poonthanam", "jnanappana", 4, 12)
              + stanzas("ഹരിനാമകീർത്തനം", "ml", "ഹരിനാമകീർത്തനം", "Harinamakeerthanam", "എഴുത്തച്ഛൻ", "Ezhuthachan", "harinama", 4, 12)
              + stanzas("വീണ പൂവ്", "ml", "വീണപൂവ്", "Veena Poovu", "കുമാരനാശാൻ", "Kumaran Asan", "veenapoovu", 4, 12))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"verses": verses}, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    by = {}
    for v in verses:
        by[v["work_en"]] = by.get(v["work_en"], 0) + 1
    print(by, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
