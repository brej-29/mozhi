"""The language layer: strings, persona prompt, news parsing, bundled content."""

import json
import re
from pathlib import Path

from jarvis import llm, news

WEB = Path(__file__).resolve().parents[1] / "jarvis" / "web"
I18N = json.loads((WEB / "i18n.json").read_text(encoding="utf-8"))
SCRIPT = {"ta": re.compile(r"[஀-௿]"), "ml": re.compile(r"[ഀ-ൿ]")}
PLACEHOLDERS = re.compile(r"\{(\w+)\}")


def test_every_message_exists_in_both_registers_with_the_same_placeholders():
    for lang in ("ta", "ml"):
        inf, frm = I18N["langs"][lang]["informal"], I18N["langs"][lang]["formal"]
        assert inf.keys() == frm.keys()
        for code in inf:
            assert set(PLACEHOLDERS.findall(inf[code])) == set(PLACEHOLDERS.findall(frm[code])), (lang, code)


def test_text_is_written_in_the_right_script_and_has_no_em_dash():
    for lang, rx in SCRIPT.items():
        for reg in ("informal", "formal"):
            for code, text in I18N["langs"][lang][reg].items():
                assert rx.search(text), (lang, reg, code)
    assert chr(0x2014) not in json.dumps(I18N, ensure_ascii=False)


def test_five_levels_each_with_name_and_address_row():
    for lang in ("ta", "ml"):
        L = I18N["langs"][lang]
        assert len(L["level_names"]) == len(L["address"]) == I18N["levels"] == 5
        assert all(len(row) == 3 for row in L["address"])  # male, female, neutral


def test_sky_words_cover_every_weather_code_the_app_can_say():
    from jarvis.tools import WMO
    for lang in ("ta", "ml"):
        assert {str(k) for k in WMO} <= set(I18N["langs"][lang]["sky"])


def test_persona_changes_with_language_level_and_gender():
    assert llm.persona("en") == llm.SYSTEM
    casual = llm.persona("ta", 0, "male")
    polite = llm.persona("ta", 3, "female")
    assert "Tamil" in casual and casual != polite
    assert I18N["langs"]["ta"]["address"][0][0] in casual and I18N["langs"]["ta"]["address"][3][1] in polite
    assert "informal" in casual and "respectful" in polite
    assert "Do not use" in llm.persona("ml", 1, "")  # neutral below the top level: no address term


def test_news_parse_keeps_only_https_links_and_the_limit():
    xml = (b"<rss><channel>" + b"".join(
        b"<item><title>T%d</title><link>https://example.com/%d</link><source>S</source></item>" % (i, i) for i in range(8))
        + b"<item><title>bad</title><link>javascript:alert(1)</link></item></channel></rss>")
    items = news.parse(xml, limit=5)
    assert len(items) == 5 and items[0] == {"title": "T0", "source": "S", "url": "https://example.com/0"}
    assert news.parse(b"<rss><channel><item><title>x</title><link>http://a</link></item></channel></rss>") == []


def test_bundled_content_is_sourced():
    verses = json.loads((WEB / "content" / "verses.json").read_text(encoding="utf-8"))["verses"]
    assert len(verses) > 1000 and all(v["source"]["url"].startswith("https://") and v["lines"] for v in verses)
    stories = WEB / "content" / "stories.json"
    if stories.exists():
        for s in json.loads(stories.read_text(encoding="utf-8"))["stories"]:
            assert s["source"]["url"].startswith("https://") and set(s["summary"]) == {"en", "ta", "ml"}
            assert chr(0x2014) not in json.dumps(s, ensure_ascii=False)


def test_chat_accepts_language_fields_and_rejects_bad_ones():
    from fastapi.testclient import TestClient

    from jarvis.server import app
    with TestClient(app) as c:
        ok = c.post("/api/chat", json={"text": "hello", "lang": "ta", "level": 4, "gender": "female"})
        assert ok.status_code == 200
        assert c.post("/api/chat", json={"text": "hello", "lang": "fr"}).status_code == 422
        assert c.post("/api/chat", json={"text": "hello", "level": 9}).status_code == 422
