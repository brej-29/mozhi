"""FastAPI app: the router, the tools and the static UI in one process."""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jarvis import llm, news, tools
from jarvis.omniroute import manager
from jarvis.routers.joint import JointRouter

llm.load_dotenv()
WEB = Path(__file__).resolve().parent / "web"
state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["router"] = JointRouter()
    manager.ensure_in_background(llm.settings()["endpoint"])  # starts OmniRoute only if it is local and not running
    yield
    manager.stop()  # stops it only if this run started it


app = FastAPI(title="Jarvis", version="2.0.0", lifespan=lifespan)
# Reject foreign Host headers so a web page cannot reach the local API through DNS rebinding.
# A hosted deployment lists its public hostname in JARVIS_ALLOWED_HOSTS (comma separated).
_hosts = ["localhost", "127.0.0.1", "[::1]", "testserver"]
_hosts += [h.strip() for h in os.getenv("JARVIS_ALLOWED_HOSTS", "").split(",") if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)


@app.middleware("http")
async def revalidate(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Cache-Control", "no-cache")  # always revalidate, so a new build is picked up
    return resp


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    tz_offset_min: int = 0
    default_city: str = ""
    history: list[dict] = Field(default=[], max_length=20)
    lang: str = Field(default="en", pattern="^(en|ta|ml)$")
    level: int = Field(default=2, ge=0, le=4)  # respect meter, 0 casual to 4 deferential
    gender: str = Field(default="", pattern="^(male|female|)$")


def route_json(r) -> dict:
    return {"tool": r.tool, "confidence": round(r.confidence, 3), "intent": r.intent, "path": r.path,
            "args": r.args, "spans": r.spans, "ms": round(r.ms, 2)}


def run_router(text: str):
    t0 = time.perf_counter()
    r = state["router"].route(text)
    r.ms = (time.perf_counter() - t0) * 1000
    return r


@app.get("/api/health")
def health():
    return {"status": "ok", "router": "joint-int8", "threshold": state["router"].threshold, "llm": {**llm.status(), "omniroute": {"state": manager.state, "detail": manager.detail}}}


@app.post("/api/route")
def route(body: ChatIn):
    """Router only, no side effects. Used by the evidence panel and for debugging."""
    return route_json(run_router(body.text))


async def act(r, body: ChatIn):
    """Run the tool the router chose. Returns (spoken reply, client action)."""
    if r.tool == "WEATHER":
        return await tools.weather(r.args.get("city") or body.default_city, lang=body.lang)
    if r.tool == "SET_REMINDER":
        when = r.args.get("when", "")
        title = r.args.get("title", "")
        derived = tools.reminder_title(body.text, when)
        if derived and (not title or title in derived):  # the tagger often stops a word early ("call" for "call mum")
            title = derived
        return tools.reminder(when, title, body.tz_offset_min)
    if r.tool == "SAVE_NOTE":
        return tools.note(body.text)
    if r.tool == "GENERAL_QA":
        return (tools.GREETING if r.intent == "general_greet" else await llm.answer(body.text, body.history, llm.persona(body.lang, body.level, body.gender))), None
    if r.tool == "NEWS":
        items = await news.headlines(body.lang)
        if not items:
            return "I could not get the news just now.", tools.say("news_empty")
        return "Here are the headlines: " + "; ".join(i["title"] for i in items), {"type": "news", "items": items}
    if r.tool in ("STORY", "VERSE"):  # picked in the browser from the bundled, sourced collection
        return "", {"type": "content", "kind": r.tool.lower()}
    return tools.unsupported(r.intent), None


@app.post("/api/chat")
async def chat(body: ChatIn):
    r = run_router(body.text)
    reply, action = await act(r, body)
    return {"reply": reply, "action": action, "route": route_json(r)}


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(body: ChatIn):
    """Server-sent events: `route` first (so the UI can show the decision), then `token`s, then `done`."""
    r = run_router(body.text)

    async def events():
        yield sse("route", route_json(r))
        if r.tool == "GENERAL_QA" and r.intent != "general_greet":
            parts = []
            async for piece in llm.stream_answer(body.text, body.history, system=llm.persona(body.lang, body.level, body.gender)):
                parts.append(piece)
                yield sse("token", piece)
            yield sse("done", {"reply": "".join(parts).strip(), "action": None})
            return
        reply, action = await act(r, body)
        yield sse("done", {"reply": reply, "action": action})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
