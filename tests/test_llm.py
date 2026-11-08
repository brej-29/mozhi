import asyncio
import json

import httpx

from mozhi import llm


def sse(*pieces, usage=None):
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}" for p in pieces]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}")
    return ("\n\n".join(lines) + "\n\ndata: [DONE]\n\n").encode()


def run(coro):
    return asyncio.run(coro)


def collect(client):
    async def go():
        return [p async for p in llm.stream_answer("who painted the mona lisa", None, client)]

    return run(go())


def setup(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("MOZHI_SPEND_FILE", str(tmp_path / "spend.json"))
    llm._MEM.clear()
    for k in ("LLM_ENDPOINT", "LLM_API_KEY", "LLM_MODEL", "MONTHLY_BUDGET_USD", "LLM_PRICE_IN_PER_M",
              "LLM_PRICE_OUT_PER_M", "MOZHI_LLM_BASE_URL", "MOZHI_LLM_MODEL", "MOZHI_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_placeholder_model_and_base_url_are_normalised(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1", LLM_MODEL="<cheap model>", LLM_PRICE_IN_PER_M="<USD>")
    s = llm.settings()
    assert s["endpoint"] == "http://x/v1/chat/completions"
    assert s["model"] == llm.DEFAULT_MODEL and s["price_in"] == 0.0


def test_streams_pieces_and_records_spend(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1/chat/completions", LLM_PRICE_IN_PER_M="10",
          LLM_PRICE_OUT_PER_M="20")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse("Leonardo", " da Vinci.", usage={"prompt_tokens": 100, "completion_tokens": 10}))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert "".join(collect(client)) == "Leonardo da Vinci."
    assert seen["body"]["stream"] is True and seen["auth"] is None  # no key configured, no header
    st = llm.status()
    assert st["calls_today"] == 1 and st["spent_usd"] == 0.0012


def test_budget_blocks_the_call(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1", MONTHLY_BUDGET_USD="0.5")
    (tmp_path / "spend.json").write_text(json.dumps({"month": __import__("datetime").date.today().strftime("%Y-%m"), "usd": 0.6}))

    def handler(request):
        raise AssertionError("must not call the model")

    out = collect(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert "budget" in "".join(out)


def test_not_connected_and_http_error(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    assert "none is connected" in "".join(collect(None))
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert "".join(collect(client)) == llm.FAILED


def test_unreadable_ledger_fails_closed(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1")
    (tmp_path / "spend.json").write_text("{not json")

    def handler(request):
        raise AssertionError("must not call the model")

    out = "".join(collect(httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    assert out == llm.LEDGER_BLOCK and llm.status()["ledger_ok"] is False


def test_unwritable_ledger_fails_closed(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1")
    monkeypatch.setenv("MOZHI_SPEND_FILE", str(tmp_path / "missing_dir" / "spend.json"))

    def handler(request):
        raise AssertionError("must not call the model")

    assert "".join(collect(httpx.AsyncClient(transport=httpx.MockTransport(handler)))) == llm.LEDGER_BLOCK


def test_call_is_counted_even_when_upstream_fails_or_stops_early(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, LLM_ENDPOINT="http://x/v1", LLM_MAX_CALLS_PER_DAY="2")
    def fail():
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    collect(fail())
    collect(fail())
    assert llm.status()["calls_today"] == 2
    assert "limit of language model calls" in "".join(collect(fail()))  # third call refused, upstream untouched


def test_dotenv_ignores_the_working_directory(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("LLM_ENDPOINT=http://evil.example/v1\n")
    monkeypatch.chdir(tmp_path)  # a .env in the launch folder is not read ...
    monkeypatch.setenv("MOZHI_ENV_FILE", str(tmp_path / "elsewhere" / ".env"))  # (the app's own file is somewhere else)
    llm.load_dotenv()
    assert llm.settings()["endpoint"] == ""
    monkeypatch.setenv("MOZHI_ENV_FILE", str(tmp_path / ".env"))  # ... unless it is named explicitly
    llm.load_dotenv()
    assert "evil.example" in llm.settings()["endpoint"]
    monkeypatch.delenv("LLM_ENDPOINT")
