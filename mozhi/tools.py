"""The things Mozhi can actually do. Each returns (spoken reply, optional client action)."""

import re
from datetime import datetime, timedelta, timezone

import dateparser
import httpx

from jarvis.routers.joint import clean

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
# WMO weather interpretation codes (Open-Meteo docs)
WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
       81: "rain showers", 82: "violent showers", 95: "a thunderstorm", 96: "thunderstorm and hail",
       99: "thunderstorm and hail"}

# friendly names for the fine intents Mozhi hears but cannot act on
UNSUPPORTED_HINT = {
    "play_music": "play music", "play_radio": "play the radio", "play_podcasts": "play podcasts",
    "play_audiobook": "play audiobooks", "play_game": "play games", "music_query": "answer music questions",
    "music_likeness": "manage music taste", "music_dislikeness": "manage music taste",
    "music_settings": "change music settings", "email_query": "read email",
    "email_sendemail": "send email", "email_querycontact": "look up contacts",
    "email_addcontact": "add contacts", "calendar_query": "read your calendar",
    "calendar_remove": "edit your calendar", "alarm_query": "list your alarms",
    "alarm_remove": "cancel alarms", "lists_query": "read your lists", "lists_remove": "edit lists",
    "iot_hue_lightchange": "control lights", "iot_hue_lightoff": "control lights",
    "iot_hue_lighton": "control lights", "iot_hue_lightdim": "control lights",
    "iot_hue_lightup": "control lights", "iot_coffee": "control appliances",
    "iot_cleaning": "control appliances", "iot_wemo_on": "control smart plugs",
    "iot_wemo_off": "control smart plugs", "audio_volume_up": "change the volume",
    "audio_volume_down": "change the volume", "audio_volume_mute": "change the volume",
    "audio_volume_other": "change the volume", "news_query": "read the news",
    "takeaway_order": "order food", "takeaway_query": "check on food orders",
    "transport_query": "check transport", "transport_taxi": "book taxis",
    "transport_ticket": "book tickets", "transport_traffic": "check traffic",
    "recommendation_events": "recommend events", "recommendation_locations": "recommend places",
    "recommendation_movies": "recommend movies", "social_post": "post to social media",
    "social_query": "read social media", "datetime_query": "tell the time", "datetime_convert": "convert time zones",
    "cooking_recipe": "find recipes", "qa_stock": "look up stock prices",
}


def say(code: str, **facts) -> dict:
    """An action that only names which message was sent, so a client can say it in another language."""
    return {"type": "say", "code": code, **facts}


async def weather(city: str, client: httpx.AsyncClient | None = None, lang: str = "en") -> tuple[str, dict | None]:
    try:
        return await _weather(city, client, lang)
    except (httpx.HTTPError, KeyError, ValueError):
        return "I could not reach the weather service. Try again in a moment.", say("weather_down")


async def _weather(city: str, client: httpx.AsyncClient | None, lang: str = "en") -> tuple[str, dict | None]:
    if not city:
        return "Which city should I check the weather for?", say("need_city")
    async with (client or httpx.AsyncClient(timeout=8)) as c:
        g = (await c.get(GEO, params={"name": city, "count": 1, "format": "json", "language": lang})).json()
        hit = (g.get("results") or [None])[0]
        if not hit:
            return f"I could not find a place called {city}.", say("city_not_found", city=city)
        f = (await c.get(FORECAST, params={
            "latitude": hit["latitude"], "longitude": hit["longitude"],
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": 1,
            "timezone": "auto"})).json()
    cur, day = f["current"], f["daily"]
    sky = WMO.get(int(cur["weather_code"]), "mixed conditions")
    place = hit["name"] + (f", {hit['country']}" if hit.get("country") else "")
    return (f"In {place} it is {round(cur['temperature_2m'])} degrees and {sky}. "
            f"Today's range is {round(day['temperature_2m_min'][0])} to "
            f"{round(day['temperature_2m_max'][0])}."), {
        "type": "weather", "place": place, "temp": round(cur["temperature_2m"]), "sky": int(cur["weather_code"]),
        "lo": round(day["temperature_2m_min"][0]), "hi": round(day["temperature_2m_max"][0])}


_WORD_NUM = {w: str(i) for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"])}
_DAYPART = {"morning": "9 am", "afternoon": "3 pm", "evening": "6 pm", "night": "8 pm"}
_HAS_TIME = re.compile(r"\d|noon|midnight|\bam\b|\bpm\b|\bin \w+ (?:minutes?|hours?)\b")
_MINUTES = {"fifteen": "15", "thirty": "30", "forty five": "45"}


def normalize_when(text: str) -> str:
    """Spoken time phrases to something dateparser understands ("tonight", "five thirty p m")."""
    t = text.lower().replace(".", " ")
    t = re.sub(r"\b([ap]) m\b", r"\1m", t)
    t = re.sub(r"\bnext (\w+day)\b", r"\1", t)
    t = re.sub(r"\bhalf past (\w+)\b", lambda m: f"{_WORD_NUM.get(m.group(1), m.group(1))}:30", t)
    t = re.sub(r"\btonight\b", "today night", t)
    t = re.sub(r"\bthis (morning|afternoon|evening)\b", r"today \1", t)
    if not re.search(r"\d|\b[ap]m\b", t):
        for part, clock in _DAYPART.items():
            t = re.sub(rf"\b{part}\b", clock, t)
    t = " ".join(_WORD_NUM.get(w, w) for w in t.split())
    t = re.sub(r"\b(\d{1,2}) (\d{2}) ([ap]m)\b", r"\1:\2 \3", t)
    t = re.sub(r"\b(\d{1,2}) (fifteen|thirty|forty five) ([ap]m)\b",
               lambda m: f"{m.group(1)}:{_MINUTES[m.group(2)]} {m.group(3)}", t)
    return t.strip()


def reminder(when: str, title: str, tz_offset_min: int = 0, now: datetime | None = None):
    """tz_offset_min is minutes east of UTC (the browser reports the negative of getTimezoneOffset)."""
    tz = timezone(timedelta(minutes=tz_offset_min))
    now = now or datetime.now(tz)
    if not when:
        return "When should I remind you?", say("need_when")
    norm = normalize_when(when)
    at = dateparser.parse(norm, settings={"RELATIVE_BASE": now.replace(tzinfo=None),
                                          "PREFER_DATES_FROM": "future"})
    if at is None:
        return f"I did not understand the time '{when}'. Try something like tomorrow at 3 pm.", say("bad_time", when=when)
    if not _HAS_TIME.search(norm):
        at = at.replace(hour=9, minute=0)  # a date with no time of day: remind at 9 am
    at = at.replace(tzinfo=tz)
    label = title or "Reminder"
    spoken = at.strftime("%A %d %B at %I:%M %p").replace(" 0", " ")
    return f"Okay, I will remind you: {label}, on {spoken}.", {
        "type": "reminder", "title": label, "at": at.isoformat()}


_LEAD = re.compile(r"^(?:(?:hey |ok |okay )?jarvis,? )?(?:please )?(?:remind me|set (?:a |an )?reminder|reminder)(?: to| about| that| for)? ?")


def reminder_title(text: str, when: str) -> str:
    """Fallback title when the router found no event span: the request minus the trigger and the time."""
    t = _LEAD.sub("", " ".join(clean(text)))  # same normalisation as the router, so "5 pm" and "five pm" line up
    for w in when.split():
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t, count=1)
    words = t.replace(",", " ").split()
    while words and words[-1] in {"at", "on", "for", "by", "in", "from", "till", "until", "to", "and"}:
        words.pop()
    return " ".join(words)


def note(text: str):
    return "Saved your note.", {"type": "note", "text": text}


def unsupported(intent: str) -> str:
    hint = UNSUPPORTED_HINT.get(intent)
    heard = f"That sounds like a request to {hint}, which I cannot do. " if hint else "I cannot do that. "
    return heard + "I can check the weather, set reminders and save notes."


GREETING = "Hello. I can check the weather, set reminders and save notes. What do you need?"


from jarvis.llm import answer, stream_answer  # noqa: F401  (general questions live in jarvis/llm.py)
