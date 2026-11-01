"""Optional language model for general questions, through any OpenAI-compatible endpoint.

Settings come from the environment or a `.env` file (never committed, never sent to the browser):
    LLM_ENDPOINT         chat completions URL (or a base URL ending in /v1)
    LLM_API_KEY          bearer token, if the endpoint needs one
    LLM_MODEL            model or combo id (falls back to DEFAULT_MODEL when unset or a placeholder)
    LLM_PRICE_IN_PER_M   USD per million input tokens (optional, 0 for free models)
    LLM_PRICE_OUT_PER_M  USD per million output tokens (optional)
    MONTHLY_BUDGET_USD   stop calling the model once this much has been spent (optional)
    LLM_MAX_CALLS_PER_DAY   hard cap on calls per day, default 300
    JARVIS_SPEND_FILE    where the spend ledger lives (default .jarvis_spend.json)
    JARVIS_ENV_FILE      an explicit .env path
The older JARVIS_LLM_BASE_URL / JARVIS_LLM_MODEL / JARVIS_LLM_API_KEY names still work.

The spend guard fails closed: a call is counted and persisted before it is made, the ledger is written
atomically, and an unreadable or unwritable ledger blocks calls instead of letting them through.
"""

import json
import os
import sys
import tempfile
import threading
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import httpx

DEFAULT_MODEL = "auto/best-free"  # a free OmniRoute combo, see D:/Project/models.md
SYSTEM = ("You are Jarvis, a voice assistant. Answer in one or two short spoken sentences. "
          "No markdown, no lists, no emoji.")
MAX_TOKENS = 200
I18N = json.loads((Path(__file__).resolve().parent / "web" / "i18n.json").read_text(encoding="utf-8"))


def persona(lang: str = "en", level: int = 2, gender: str = "") -> str:
    """System prompt for the chosen language and respect level. English keeps the original Jarvis prompt."""
    cfg = I18N["langs"].get(lang)
    if lang == "en" or not cfg:
        return SYSTEM
    p, level = I18N["persona"], max(0, min(int(level), I18N["levels"] - 1))
    formal = level >= 2
    addr = cfg["address"][level][{"male": 0, "female": 1}.get(gender, 2)]
    return " ".join([
        p["name_line"].format(name=I18N["app"]["name"]), p["lang_line"].format(language=cfg["language"]),
        p["formal" if formal else "informal"].format(pronoun=cfg["pronoun"][1 if formal else 0]),
        p["addr_line"].format(addr=addr) if addr else p["no_addr_line"]])


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader: KEY=VALUE lines, existing environment variables win.

    Only files that belong to the application are read (an explicit path, JARVIS_ENV_FILE, the folder
    holding jarvis.exe, or the repository root). The working directory is deliberately not searched, so a
    stray .env in whatever folder you launch from cannot redirect the endpoint or the API key."""
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    candidates = [path] if path else [Path(os.environ["JARVIS_ENV_FILE"])] if os.getenv("JARVIS_ENV_FILE") else [here / ".env"]
    for p in candidates:
        if p and p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _num(name: str) -> float:
    try:
        return max(0.0, float(os.getenv(name, "")))
    except ValueError:  # unset or a "<placeholder>"
        return 0.0


def settings() -> dict:
    endpoint = os.getenv("LLM_ENDPOINT") or os.getenv("JARVIS_LLM_BASE_URL") or ""
    if endpoint and not endpoint.rstrip("/").endswith("/chat/completions"):
        endpoint = endpoint.rstrip("/") + "/chat/completions"
    model = os.getenv("LLM_MODEL") or os.getenv("JARVIS_LLM_MODEL") or ""
    if not model or model.startswith("<"):
        model = DEFAULT_MODEL
    key = os.getenv("LLM_API_KEY") or os.getenv("JARVIS_LLM_API_KEY") or ""
    return {"endpoint": endpoint if not endpoint.startswith("<") else "", "model": model,
            "key": "" if key.startswith("<") else key, "price_in": _num("LLM_PRICE_IN_PER_M"),
            "price_out": _num("LLM_PRICE_OUT_PER_M"), "budget": _num("MONTHLY_BUDGET_USD"),
            "max_calls": int(_num("LLM_MAX_CALLS_PER_DAY") or 300)}


# ---------- spend ledger ----------
class LedgerError(Exception):
    """The ledger cannot be trusted (unreadable or unwritable), so calls must stop."""


_LOCK = threading.Lock()
_MEM: dict = {}  # in-process floor: what this process has counted, whatever the disk says


def spend_file() -> Path:  # resolved on every use, after .env has been loaded
    return Path(os.getenv("JARVIS_SPEND_FILE") or ".jarvis_spend.json")


def _read() -> dict:
    p = spend_file()
    d: dict = {}
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise TypeError("ledger is not an object")
        except (OSError, ValueError, TypeError) as exc:
            raise LedgerError(f"cannot read {p}") from exc
    month, today = date.today().strftime("%Y-%m"), date.today().isoformat()
    if d.get("month") != month:
        d["month"], d["usd"] = month, 0.0
    if d.get("day") != today:
        d["day"], d["calls"] = today, 0
    if _MEM.get("month") == month:
        d["usd"] = max(d.get("usd", 0.0), _MEM.get("usd", 0.0))
    if _MEM.get("day") == today:
        d["calls"] = max(d.get("calls", 0), _MEM.get("calls", 0))
    return d


def _write(d: dict) -> None:
    _MEM.update(d)
    p = spend_file()
    try:
        fd, tmp = tempfile.mkstemp(dir=p.parent if str(p.parent) else ".", prefix=".spend-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, p)  # atomic, so a crash never leaves a half-written ledger
    except OSError as exc:
        raise LedgerError(f"cannot write {p}") from exc


def status() -> dict:
    s = settings()
    try:
        d, ok = _read(), True
    except LedgerError:
        d, ok = {}, False
    return {"connected": bool(s["endpoint"]), "model": s["model"], "spent_usd": round(d.get("usd", 0.0), 4),
            "budget_usd": s["budget"] or None, "calls_today": d.get("calls", 0), "ledger_ok": ok}


def _blocked(s: dict, d: dict) -> str:
    if s["budget"] and d.get("usd", 0.0) >= s["budget"]:
        return "My language model budget for this month is used up, so I cannot answer general questions until it resets."
    if d.get("calls", 0) >= s["max_calls"]:
        return "I have reached today's limit of language model calls. Try again tomorrow."
    return ""


LEDGER_BLOCK = "I cannot track my language model spend right now, so I will not call it. Check the ledger file."


def _cost(s: dict, tokens_in: float, tokens_out: float) -> float:
    return (tokens_in * s["price_in"] + tokens_out * s["price_out"]) / 1e6


def reserve(s: dict, prompt_chars: int) -> tuple[str, float]:
    """Check the caps and count the call in one step, before anything is sent. Returns (block message, reserved USD).

    There is no await between the check and the write, and a lock covers threads, so two requests cannot both
    pass the same remaining budget."""
    with _LOCK:
        try:
            d = _read()
            if msg := _blocked(s, d):
                return msg, 0.0
            reserved = _cost(s, prompt_chars / 4, MAX_TOKENS)  # worst case: a full-length answer
            d["calls"] = d.get("calls", 0) + 1
            d["usd"] = d.get("usd", 0.0) + reserved
            _write(d)
            return "", reserved
        except LedgerError:
            return LEDGER_BLOCK, 0.0


def settle(s: dict, reserved: float, tokens_in: float, tokens_out: float) -> None:
    """Replace the reservation with the real cost. Runs on every exit path, including cancellation."""
    with _LOCK:
        try:
            d = _read()
            d["usd"] = max(0.0, d.get("usd", 0.0) - reserved + _cost(s, tokens_in, tokens_out))
            _write(d)
        except LedgerError:
            _MEM["usd"] = max(0.0, _MEM.get("usd", 0.0) - reserved + _cost(s, tokens_in, tokens_out))


def _messages(text: str, history: list[dict] | None, system: str = SYSTEM) -> list[dict]:
    # the browser supplies the history, so keep only plain user/assistant turns of bounded size
    past = [{"role": h["role"], "content": str(h.get("content", ""))[:500]} for h in (history or [])[-6:]
            if isinstance(h, dict) and h.get("role") in ("user", "assistant")]
    return [{"role": "system", "content": system}, *past, {"role": "user", "content": text}]


NOT_CONNECTED = ("General questions need a language model and none is connected. Set LLM_ENDPOINT and "
                 "LLM_API_KEY in a .env file. Weather, reminders and notes work without one.")
FAILED = "My language model did not answer. Try again in a moment."


async def stream_answer(text: str, history: list[dict] | None = None,
                        client: httpx.AsyncClient | None = None, system: str = SYSTEM) -> AsyncIterator[str]:
    """Yield the reply in pieces. Never raises: failures become a spoken message."""
    s = settings()
    if not s["endpoint"]:
        yield NOT_CONNECTED
        return
    messages = _messages(text, history, system)
    prompt_chars = sum(len(m["content"]) for m in messages)
    msg, reserved = reserve(s, prompt_chars)
    if msg:
        yield msg
        return
    body = {"model": s["model"], "messages": messages, "max_tokens": MAX_TOKENS,
            "temperature": 0.3, "stream": True, "stream_options": {"include_usage": True}}
    headers = {"Authorization": f"Bearer {s['key']}"} if s["key"] else {}
    out_chars, usage = 0, None
    try:
        async with (client or httpx.AsyncClient(timeout=httpx.Timeout(45, connect=5))) as c, \
                c.stream("POST", s["endpoint"], headers=headers, json=body) as r:
            if r.status_code != 200:
                yield FAILED
                return
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                usage = chunk.get("usage") or usage
                for ch in chunk.get("choices") or []:
                    piece = ((ch.get("delta") or {}).get("content") or "").replace(chr(0x202f), " ")
                    if piece:
                        out_chars += len(piece)
                        yield piece
    except (httpx.HTTPError, ValueError, KeyError):
        yield FAILED
    finally:  # also reached on cancellation or when the consumer stops early
        settle(s, reserved, (usage or {}).get("prompt_tokens") or prompt_chars / 4,
               (usage or {}).get("completion_tokens") or out_chars / 4)


async def answer(text: str, history: list[dict] | None = None, system: str = SYSTEM) -> str:
    return "".join([p async for p in stream_answer(text, history, system=system)]).strip()
