"""Claude gateway: OpenAI-shaped calls are converted to Anthropic Messages calls and back. No network."""
import json
from types import SimpleNamespace as NS

import pytest

from agent import llm


class FakeMessages:
    def __init__(self, blocks, stop="end_turn", raises=None):
        self.calls, self.blocks, self.stop, self.raises = [], blocks, stop, raises

    def create(self, **kw):
        self.calls.append(kw)
        if self.raises:
            raise self.raises
        return NS(id="msg_1", content=self.blocks, stop_reason=self.stop,
                  usage=NS(input_tokens=11, output_tokens=7, cache_read_input_tokens=5, cache_creation_input_tokens=0))


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.delenv("KARNA_PROVIDER", raising=False)
    holder = {}

    def install(blocks, **kw):
        fm = FakeMessages(blocks, **kw)
        monkeypatch.setattr(llm, "_anthropic_client", lambda: NS(messages=fm))
        holder["fm"] = fm
        return fm
    return install


def text(t):
    return NS(type="text", text=t)


def test_provider_selection(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", ""); monkeypatch.setenv("GROQ_API_KEY", ""); monkeypatch.delenv("KARNA_PROVIDER", raising=False)
    assert llm.provider() is None and not llm.enabled()
    monkeypatch.setenv("GROQ_API_KEY", "g"); assert llm.provider() == "groq"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a"); assert llm.provider() == "anthropic"
    monkeypatch.setenv("KARNA_PROVIDER", "groq"); assert llm.provider() == "groq"
    with pytest.raises(RuntimeError):
        monkeypatch.setenv("ANTHROPIC_API_KEY", ""); monkeypatch.setenv("GROQ_API_KEY", ""); llm.get_client()


def test_plain_chat_roundtrip_and_tiers(claude):
    fm = claude([text("Hello there")])
    c = llm.get_client()
    out = c.chat.completions.create(model="openai/gpt-oss-20b", messages=[
        {"role": "system", "content": "You are KARNA."}, {"role": "user", "content": "hi"}], temperature=0.2, max_tokens=900)
    assert out.choices[0].message.content == "Hello there" and out.choices[0].message.tool_calls is None
    kw = fm.calls[0]
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["system"][0]["text"] == "You are KARNA." and kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    # tiny rewrite call -> fast model; json routing on the small model -> fast model
    c.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role": "user", "content": "x"}], max_tokens=80)
    assert fm.calls[1]["model"] == "claude-haiku-5-5"
    fm.blocks = [text("```json\n{\"a\": 1}\n```")]
    out = c.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role": "user", "content": "x"}], response_format={"type": "json_object"})
    assert json.loads(out.choices[0].message.content) == {"a": 1} and fm.calls[2]["model"] == "claude-haiku-5-5"
    assert "valid JSON" in fm.calls[2]["system"][0]["text"]


def test_tool_loop_conversion(claude):
    fm = claude([text("Let me check."), NS(type="tool_use", id="tu_1", name="show_deadlines", input={"days": 3})], stop="tool_use")
    tools = [{"type": "function", "function": {"name": "show_deadlines", "description": "d", "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}}}]
    out = llm.get_client().chat.completions.create(model="openai/gpt-oss-120b", messages=[
        {"role": "system", "content": "s"}, {"role": "user", "content": "deadlines?"}], tools=tools, tool_choice="auto", temperature=0.2)
    msg = out.choices[0].message
    assert out.choices[0].finish_reason == "tool_calls" and msg.content == "Let me check."
    tc = msg.tool_calls[0]
    assert tc.id == "tu_1" and tc.function.name == "show_deadlines" and json.loads(tc.function.arguments) == {"days": 3}
    sent = fm.calls[0]
    assert sent["tools"][0]["input_schema"]["properties"]["days"] == {"type": "integer"} and sent["tool_choice"] == {"type": "auto"}
    # second turn: assistant tool call + two tool results must collapse into valid alternating roles
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "t1", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "t2", "arguments": "{\"x\":1}"}}]},
            {"role": "tool", "tool_call_id": "a", "name": "t1", "content": "{\"ok\":true}"},
            {"role": "tool", "tool_call_id": "b", "name": "t2", "content": "{\"ok\":false}"}]
    _, conv = llm.convert_messages(msgs)
    assert [m["role"] for m in conv] == ["user", "assistant", "user"]
    assert [b["type"] for b in conv[1]["content"]] == ["tool_use", "tool_use"] and conv[1]["content"][1]["input"] == {"x": 1}
    assert [b["tool_use_id"] for b in conv[2]["content"]] == ["a", "b"]


def test_images_become_anthropic_blocks(claude):
    fm = claude([text("a cat")])
    llm.get_client().chat.completions.create(model="qwen/x", messages=[{"role": "user", "content": [
        {"type": "text", "text": "what is this"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}]}])
    blocks = fm.calls[0]["messages"][0]["content"]
    assert blocks[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}}


def test_leading_assistant_turn_gets_user_opener():
    _, conv = llm.convert_messages([{"role": "assistant", "content": "hi"}, {"role": "user", "content": "yo"}])
    assert conv[0]["role"] == "user"


def test_extract_json_variants():
    assert json.loads(llm.extract_json('Sure! {"a": {"b": 2}} done')) == {"a": {"b": 2}}
    assert llm.extract_json("no json here") == "{}"


def test_temperature_rejected_is_retried_without_it(claude):
    class BadRequestError(Exception):
        pass
    fm = claude([text("ok")])
    real = fm.create
    state = {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if "temperature" in kw:
            raise BadRequestError("temperature is deprecated for this model")
        return real(**kw)
    fm.create = flaky
    out = llm.get_client().chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}], temperature=0.3)
    assert out.choices[0].message.content == "ok" and state["n"] == 2


def test_falls_back_to_groq_when_claude_is_down(claude, monkeypatch):
    claude([], raises=RuntimeError("overloaded"))
    monkeypatch.setenv("GROQ_API_KEY", "g")
    seen = {}
    monkeypatch.setattr(llm, "_groq_create", lambda **kw: seen.update(kw) or "GROQ")
    assert llm.get_client().chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role": "user", "content": "x"}]) == "GROQ"
    assert seen["model"] == "openai/gpt-oss-20b"
    monkeypatch.setenv("KARNA_FALLBACK", "off")
    with pytest.raises(RuntimeError):
        llm.get_client().chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])


def test_stream_chat_yields_deltas(claude, monkeypatch):
    class Stream:
        text_stream = iter(["Hel", "lo"])
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(llm, "_anthropic_client", lambda: NS(messages=NS(stream=lambda **kw: Stream())))
    assert "".join(llm.stream_chat([{"role": "user", "content": "x"}])) == "Hello"


def test_general_stream_endpoint_local_and_llm(monkeypatch):
    import os
    os.environ.setdefault("OPAI_LOCAL_AUTH_BYPASS", "1")
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "stream_chat", lambda msgs, **kw: iter(["Pa", "ging is ", "memory mapping."]))
    c = TestClient(main.app)
    r = c.post("/v1/chat/general/stream", json={"messages": [{"role": "user", "content": "what is paging"}]})
    events = [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert "".join(e.get("delta", "") for e in events) == "Paging is memory mapping."
    assert events[-1]["done"] and events[-1]["reply"] == "Paging is memory mapping."
    r = c.post("/v1/chat/general/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    events = [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert events[-1]["source"] == "conversation"


def test_groq_only_setup_passes_calls_straight_through(monkeypatch):
    """No Anthropic key (the user's real setup): behaviour is exactly the old Groq client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", ""); monkeypatch.setenv("GROQ_API_KEY", "gsk_test"); monkeypatch.delenv("KARNA_PROVIDER", raising=False)
    seen = {}
    fake = NS(chat=NS(completions=NS(create=lambda **kw: seen.update(kw) or NS(choices=[NS(message=NS(content="ok", tool_calls=None))]))))
    import agent.groq_client as gc
    monkeypatch.setattr(gc, "groq_raw_client", lambda: fake)
    assert llm.provider() == "groq" and gc.groq_enabled()
    out = gc.get_client().chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role": "user", "content": "x"}], temperature=0.2, max_tokens=50)
    assert out.choices[0].message.content == "ok"
    assert seen["model"] == "openai/gpt-oss-20b" and "tier" not in seen and seen["max_tokens"] == 50
