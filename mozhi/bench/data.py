"""MASSIVE en-US -> Jarvis tool benchmark. Mapping and gold are fixed in docs/PREREG.md."""

import json
import random
import re
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MASSIVE_URL = "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.0.tar.gz"
MASSIVE_FILE = RAW / "1.0" / "data" / "en-US.jsonl"

TOOL_OF_INTENT = {
    "weather_query": "WEATHER",
    "alarm_set": "SET_REMINDER",
    "calendar_set": "SET_REMINDER",
    "lists_createoradd": "SAVE_NOTE",
    "qa_factoid": "GENERAL_QA",
    "qa_definition": "GENERAL_QA",
    "qa_maths": "GENERAL_QA",
    "qa_currency": "GENERAL_QA",
    "general_joke": "GENERAL_QA",
    "general_greet": "GENERAL_QA",
}
EXCLUDED_INTENT = "general_quirky"
WHEN_LABELS = ("date", "time", "timeofday", "general_frequency")
SLOT = re.compile(r"\[(\w+) : ([^\]]+)\]")


@dataclass
class Item:
    id: str
    text: str
    intent: str
    tool: str
    split: str
    city: str = ""
    when: str = ""
    title: str = ""


def ensure_massive() -> Path:
    if not MASSIVE_FILE.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        tgz = RAW / "massive.tar.gz"
        urllib.request.urlretrieve(MASSIVE_URL, tgz)
        with tarfile.open(tgz) as t:
            t.extractall(RAW, members=[m for m in t.getmembers() if m.name.endswith("en-US.jsonl")])
    return MASSIVE_FILE


def load(split: str | None = None, include_quirky: bool = False) -> list[Item]:
    items = []
    for line in ensure_massive().read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if split and r["partition"] != split:
            continue
        intent = r["intent"]
        if intent == EXCLUDED_INTENT and not include_quirky:
            continue
        tool = TOOL_OF_INTENT.get(intent, "UNSUPPORTED")
        slots = SLOT.findall(r["annot_utt"])
        city = next((v for k, v in slots if k == "place_name"), "") if tool == "WEATHER" else ""
        when = " ".join(v for k, v in slots if k in WHEN_LABELS) if tool == "SET_REMINDER" else ""
        title = next((v for k, v in slots if k == "event_name"), "")
        items.append(Item(r["id"], r["utt"], intent, tool, r["partition"], city, when, title))
    return items


def llm_subset(items: list[Item], per_tool: int = 100, unsupported: int = 200, seed: int = 0):
    """Fixed stratified subset for the slow (LLM) systems. Deterministic for a given seed."""
    rng = random.Random(seed)
    out = []
    for tool in ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "UNSUPPORTED"):
        pool = sorted((i for i in items if i.tool == tool), key=lambda i: int(i.id))
        k = unsupported if tool == "UNSUPPORTED" else per_tool
        out += rng.sample(pool, min(k, len(pool)))
    return sorted(out, key=lambda i: int(i.id))
