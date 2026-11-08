"""R0: keyword rules. The floor that every learned router has to beat."""

import re

from mozhi.schema import Route

WEATHER = re.compile(
    r"\b(weather|forecast|rain|raining|rainy|snow|snowing|temperature|sunny|cloudy|windy|"
    r"humid|humidity|storm|stormy|umbrella|degrees)\b")
REMIND = re.compile(
    r"\b(remind|reminder|alarm|wake me|schedule|appointment|meeting|calendar|set a timer)\b")
NOTE = re.compile(r"\b(note|notes|jot|write down|list)\b")
QA = re.compile(r"^(what|who|when|where|how|why|which|define|tell me|is|are|does|do|can)\b")
CITY = re.compile(r"\b(?:in|for|at)\s+([a-z][a-z .'-]*?)(?:\s+(?:today|tomorrow|tonight|now|this|next|on)\b|$)")
WHEN = re.compile(
    r"\b((?:tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next \w+|this \w+)(?: (?:morning|afternoon|evening|night))?"
    r"|(?:at )?\d{1,2}(?::\d\d)? ?(?:am|pm)|(?:at )?\w+ (?:am|pm)|in \w+ (?:minutes?|hours?|days?))\b")
STOP_CITY = {"the", "my", "this", "that", "it", "me", "a"}


class RuleRouter:
    name = "R0"

    def route(self, text: str) -> Route:
        t = text.lower().strip()
        if WEATHER.search(t):
            m = CITY.search(t)
            city = m.group(1).strip() if m and m.group(1).split()[0] not in STOP_CITY else ""
            return Route("WEATHER", {"city": city}, path="rules")
        if REMIND.search(t):
            return Route("SET_REMINDER", {"when": " ".join(m for m in WHEN.findall(t))}, path="rules")
        if NOTE.search(t):
            return Route("SAVE_NOTE", path="rules")
        if QA.search(t):
            return Route("GENERAL_QA", path="rules")
        return Route("UNSUPPORTED", path="rules")
