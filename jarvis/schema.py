"""Shared types: the tool set and the routing result every router returns."""

from dataclasses import dataclass, field

TOOLS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA", "UNSUPPORTED")
ACTION_TOOLS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE")
# GENERAL_QA and UNSUPPORTED both mean "do not perform a side effect"
NO_ACTION = "NO_ACTION"


@dataclass
class Route:
    tool: str
    args: dict = field(default_factory=dict)  # WEATHER: city; SET_REMINDER: when, title
    confidence: float = 1.0
    valid: bool = True  # False when an LLM router produced output that failed the schema
    ms: float = 0.0  # wall-clock router time
    path: str = ""  # which stage answered (fast, llm, abstain)
    intent: str = ""  # fine-grained intent label when the router has one
    spans: list = field(default_factory=list)  # [{"kind", "text"}] extracted slot spans
    scores: dict = field(default_factory=dict)  # probability of every tool, so the UI can show the whole decision
    words: list = field(default_factory=list)  # the words the router actually read, after normalising


def action_view(tool: str) -> str:
    return tool if tool in ACTION_TOOLS else NO_ACTION
