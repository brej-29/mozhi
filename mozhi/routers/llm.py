"""LLM routers on llama.cpp (local GGUF) or any OpenAI-compatible endpoint.

L0 reproduces Jarvis V1: project-doc prompt, JSON by instruction only, default sampling,
one repair retry (V1 sent the exception text, not the model output, to the repair call; kept as is).
L1 is the fair baseline: short prompt, few-shot, JSON-schema constrained decoding, temperature 0.
"""

import json
import re

from jarvis.legacy.v1_prompt import V1_CONTRACT, V1_ROUTER_SYSTEM
from jarvis.schema import TOOLS, Route

V1_TOOLS = ("WEATHER", "SET_REMINDER", "SAVE_NOTE", "GENERAL_QA")

MIN_SYSTEM = """You route one spoken request for a voice assistant to exactly one tool.
Tools:
- WEATHER: weather or forecast. city = place named in the request, or "" if none.
- SET_REMINDER: set an alarm or reminder or calendar event. when = the date and time words as spoken, or "".
- SAVE_NOTE: save a note or add to a list.
- GENERAL_QA: a factual question, definition, maths, joke or greeting.
- UNSUPPORTED: anything else the assistant has no tool for (music, smart home, email, news, transport, reading the calendar, and so on).
Answer with JSON only: {"tool": ..., "city": ..., "when": ...}. Use "" for fields that do not apply."""

SHOTS = [
    ("will it rain in paris tomorrow", {"tool": "WEATHER", "city": "paris", "when": ""}),
    ("wake me up at six am", {"tool": "SET_REMINDER", "city": "", "when": "six am"}),
    ("save a note about the budget meeting", {"tool": "SAVE_NOTE", "city": "", "when": ""}),
    ("who painted the mona lisa", {"tool": "GENERAL_QA", "city": "", "when": ""}),
    ("play some jazz in the kitchen", {"tool": "UNSUPPORTED", "city": "", "when": ""}),
    ("what is on my calendar friday", {"tool": "UNSUPPORTED", "city": "", "when": ""}),
]
SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"enum": list(TOOLS)},
        "city": {"type": "string"},
        "when": {"type": "string"},
    },
    "required": ["tool", "city", "when"],
}


def _json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(m.group(0) if m else raw)


def parse_v1(raw: str) -> Route:
    d = _json(raw)["tool_call"]
    name = d["name"]
    if name not in V1_TOOLS:
        raise ValueError(f"unknown tool {name}")
    a = d.get("args") or {}
    return Route(
        name,
        {"city": str(a.get("city") or ""), "when": str(a.get("datetime_text") or ""),
         "title": str(a.get("title") or "")},
        float(d.get("confidence") or 0.0),
    )


def parse_min(raw: str) -> Route:
    d = _json(raw)
    if d["tool"] not in TOOLS:
        raise ValueError(f"unknown tool {d['tool']}")
    return Route(d["tool"], {"city": d.get("city", ""), "when": d.get("when", "")})


class LlamaRouter:
    """mode 'v1' = L0, 'min' = L1."""

    def __init__(self, model_path: str, mode: str = "min", n_gpu_layers: int = 0, n_ctx: int = 2048,
                 n_threads: int | None = None):
        import os

        for d in filter(None, os.environ.get("JARVIS_DLL_DIRS", "").split(os.pathsep)):
            os.add_dll_directory(d)  # Windows: CUDA runtime DLLs for the GPU build of llama.cpp
        from llama_cpp import Llama

        self.mode, self.name = mode, {"v1": "L0", "v1x": "L0x"}.get(mode, "L1")
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
                         n_threads=n_threads, verbose=False, seed=0)

    def _chat(self, messages, **kw) -> str:
        out = self.llm.create_chat_completion(messages=messages, **kw)
        return out["choices"][0]["message"]["content"] or ""

    def route(self, text: str) -> Route:
        if self.mode in ("v1", "v1x"):
            return self._route_v1(text)
        msgs = [{"role": "system", "content": MIN_SYSTEM}]
        for u, a in SHOTS:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": json.dumps(a)}]
        msgs.append({"role": "user", "content": text})
        raw = self._chat(msgs, temperature=0.0, max_tokens=60,
                         response_format={"type": "json_object", "schema": SCHEMA})
        try:
            return parse_min(raw)
        except Exception:
            return Route("GENERAL_QA", valid=False)

    def _route_v1(self, text: str) -> Route:
        # v1x: the V1 contract without the pasted project-doc excerpts (ablation H3)
        base = [{"role": "system", "content": V1_ROUTER_SYSTEM if self.mode == "v1" else V1_CONTRACT}]
        raw = self._chat(base + [{"role": "user", "content": text}], temperature=0.8, max_tokens=256)
        try:
            return parse_v1(raw)
        except Exception as exc:
            fix = ("You previously returned invalid JSON for a tool routing decision. "
                   f"Here is your response:\n\n{exc}\n\nPlease return ONLY valid JSON that matches "
                   'this schema:{"tool_call":{"name":"WEATHER"|"SET_REMINDER"|"SAVE_NOTE"|"GENERAL_QA",'
                   '"args":{},"confidence":0.0},"assistant_message":"string or null"}')
            try:
                r = parse_v1(self._chat(base + [{"role": "user", "content": fix}],
                                        temperature=0.8, max_tokens=256))
                r.valid = False  # first output was invalid even though the retry recovered
                return r
            except Exception:
                # V1 then answered as plain Q&A
                return Route("GENERAL_QA", valid=False)
