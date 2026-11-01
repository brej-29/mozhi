from datetime import datetime

from jarvis import tools


def test_reminder_parses_future_time():
    reply, action = tools.reminder("tomorrow at 3 pm", "dentist", tz_offset_min=330,
                                   now=datetime(2026, 1, 5, 9, 0))
    assert action["type"] == "reminder"
    assert action["at"].startswith("2026-01-06T15:00:00")
    assert action["at"].endswith("+05:30")


def test_reminder_without_time_asks():
    reply, action = tools.reminder("", "dentist")
    assert action == {"type": "say", "code": "need_when"} and "When" in reply


def test_unsupported_names_what_it_heard():
    assert "play music" in tools.unsupported("play_music")
    assert "weather" in tools.unsupported("something_unknown")


def test_weather_needs_a_city():
    import asyncio

    reply, action = asyncio.run(tools.weather(""))
    assert action["code"] == "need_city" and "Which city" in reply


def test_clean_spells_out_recogniser_digits():
    from jarvis.routers.joint import clean

    assert clean("Block 1 hour from 10 tomorrow.") == ["block", "one", "hour", "from", "ten", "tomorrow"]
    assert clean("Wake me at 5:30 p.m.") == ["wake", "me", "at", "five", "thirty", "p", "m"]
    assert clean("the 7-day forecast") == ["the", "seven", "day", "forecast"]
    assert clean("What's the weather?") == ["what's", "the", "weather"]


def test_reminder_title_fallback():
    assert tools.reminder_title("remind me to call mum tomorrow at 5 pm", "tomorrow five pm") == "call mum"
    assert tools.reminder_title("remind me to take the bins out tonight", "tonight") == "take the bins out"


def test_spoken_times_parse():
    now = datetime(2026, 1, 5, 9, 0)
    cases = {"tonight": "20:00", "tomorrow morning": "09:00", "five thirty p m": "17:30",
             "next monday": "09:00", "this evening": "18:00", "half past two pm": "14:30", "friday": "09:00"}
    for when, hhmm in cases.items():
        _reply, action = tools.reminder(when, "x", tz_offset_min=0, now=now)
        assert action and action["at"][11:16] == hhmm, (when, action)


def test_static_hints_match_python():
    import json
    from pathlib import Path

    hints = json.loads((Path(__file__).parents[1] / "jarvis" / "web" / "hints.json").read_text(encoding="utf-8"))
    assert hints == tools.UNSUPPORTED_HINT
