from types import SimpleNamespace

import pytest

from agent import llm, model_router
from agent.context_manager import compact


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("KARNA_ENABLE_PAID_MODELS", "false")
    monkeypatch.setenv("KARNA_ENABLE_FALLBACK", "true")
    monkeypatch.setenv("KARNA_PROVIDER_LIMITS_JSON", "{}")
    monkeypatch.setenv("KARNA_GEMINI_WORKSPACE_ALLOWED", "false")
    monkeypatch.setenv("KARNA_OPENROUTER_VISION_CAPABLE", "false")
    with model_router._lock:
        model_router._health.clear()
    tokens = (llm._sel.set(None), llm._request_mode.set("auto"), llm._workspace.set(False),
              llm._stream_callback.set(None), llm._user_visible.set(False))
    yield
    llm._user_visible.reset(tokens[4])
    llm._stream_callback.reset(tokens[3])
    llm._workspace.reset(tokens[2])
    llm._request_mode.reset(tokens[1])
    llm._sel.reset(tokens[0])


def test_auto_and_modes_choose_locally_without_calling_a_classifier():
    casual = [{"role": "user", "content": "hey, how are you?"}]
    coding = [{"role": "user", "content": "debug this Python exception"}]
    complex_prompt = [{"role": "user", "content": "Compare these approaches and analyze the trade-offs."}]

    assert model_router.routes(casual)[0].provider == "groq"
    assert model_router.routes(coding)[0].provider == "groq"
    assert model_router.routes(complex_prompt)[0].provider == "gemini"
    assert model_router.routes(complex_prompt, mode="fast")[0].provider == "groq"
    assert model_router.routes(casual, mode="think")[0].provider == "gemini"
    assert model_router.routes(casual, mode="expert")[0].provider == "gemini"
    assert model_router.routes([{"role": "user", "content": "make a study workflow for finals"}])[0].provider == "gemini"


def test_legacy_fallback_switch_is_still_honored(monkeypatch):
    monkeypatch.delenv("KARNA_ENABLE_FALLBACK", raising=False)
    monkeypatch.setenv("KARNA_FALLBACK", "off")
    assert len(model_router.routes([{"role": "user", "content": "hello"}])) == 1


def test_documents_and_vision_prefer_gemini_and_measured_latency_orders_fallbacks():
    document = [{"role": "user", "content": "Summarize this PDF for me."}]
    image = [{"role": "user", "content": [{"type": "text", "text": "What is shown?"},
                                                {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}]}]
    assert model_router.classify(document) == "document"
    assert model_router.routes(document)[0].provider == "gemini"
    assert model_router.classify(image) == "multimodal"
    assert model_router.routes(image)[0].provider == "gemini"

    model_router.record("gemini", True, 80)
    model_router.record("openrouter", True, 20)
    assert model_router.routes([{"role": "user", "content": "hello"}])[1].provider == "openrouter"


def test_circuit_breaker_cools_down_after_repeated_failures():
    for _ in range(3):
        model_router.record("groq", False, 100)
    health = model_router.health()["groq"]
    assert not health["healthy"] and health["cooldown_seconds"] > 0
    assert model_router.routes([{"role": "user", "content": "hello"}])[0].provider == "gemini"


def test_private_workspace_never_falls_back_to_openrouter(monkeypatch):
    msg = [{"role": "user", "content": "Rewrite my resume for this role."}]
    routes = model_router.routes(msg, workspace=True)
    assert [r.provider for r in routes] == ["groq"]

    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="approved for private"):
        model_router.routes(msg, workspace=True)


def test_sensitive_general_chat_is_routed_only_to_approved_providers():
    messages = [{"role": "user", "content": "Please review my salary details and this confidential contract."}]
    assert model_router.is_private(messages)
    assert [route.provider for route in model_router.routes(messages)] == ["groq"]


def test_paid_gemini_workspace_is_explicit_opt_in(monkeypatch):
    msg = [{"role": "user", "content": "Summarize my study schedule."}]
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("KARNA_ENABLE_PAID_MODELS", "true")
    with pytest.raises(RuntimeError, match="approved for private"):
        model_router.routes(msg, workspace=True)
    monkeypatch.setenv("KARNA_GEMINI_WORKSPACE_ALLOWED", "true")
    assert model_router.routes(msg, workspace=True)[0].provider == "gemini"


def test_paid_anthropic_workspace_also_requires_privacy_opt_in(monkeypatch):
    from agent import model_catalog
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    monkeypatch.setenv("KARNA_ENABLE_PAID_MODELS", "true")
    monkeypatch.setenv("KARNA_ANTHROPIC_WORKSPACE_ALLOWED", "false")
    with pytest.raises(model_catalog.ModelChoiceError, match="can't be used in Workspace"):
        model_catalog.resolve("claude-balanced", "workspace")
    monkeypatch.setenv("KARNA_ANTHROPIC_WORKSPACE_ALLOWED", "true")
    assert model_catalog.resolve("claude-balanced", "workspace").provider == "anthropic"


def test_no_private_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="No configured AI provider is approved"):
        model_router.routes([{"role": "user", "content": "my private notes"}], workspace=True)


def test_primary_failure_uses_next_compatible_provider(monkeypatch):
    monkeypatch.setenv("KARNA_GEMINI_WORKSPACE_ALLOWED", "false")
    llm.set_request_mode("auto", workspace=False)
    calls = []

    class RetryableFailure(RuntimeError):
        retryable = True

    def fake_call(route, kwargs):
        calls.append(route.provider)
        if len(calls) == 1:
            raise RetryableFailure("temporarily unavailable")
        msg = SimpleNamespace(content="KARNA reply", tool_calls=None)
        return SimpleNamespace(model=route.model, choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm, "_call_route", fake_call)
    monkeypatch.setattr(llm, "_record_provider_attempt", lambda *args, **kwargs: None)
    out = llm._create_raw(model="ignored", messages=[{"role": "user", "content": "hello"}])

    assert out.choices[0].message.content == "KARNA reply"
    assert calls[:2] == ["groq", "gemini"]


def test_selected_stream_skips_provider_in_circuit_cooldown(monkeypatch):
    llm.set_request_mode("auto", workspace=False)
    llm.select("groq-gpt-oss-120b", "general", "test-user")
    for _ in range(3):
        model_router.record("groq", False, 100)
    from agent.providers import openai_compat
    monkeypatch.setattr(openai_compat, "stream", lambda *args, **kwargs: iter(["Gemini fallback"]))
    monkeypatch.setattr(llm, "_record_provider_attempt", lambda *a, **kw: None)
    try:
        assert "".join(llm.stream_chat([{"role": "user", "content": "hello"}])) == "Gemini fallback"
        assert llm.stream_meta()["provider"] == "gemini"
        assert llm.stream_meta()["fallback"]
    finally:
        llm.select(None, "general", "test-user")


def test_workspace_tool_reply_streams_text_and_reports_actual_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    values = []
    llm.set_request_mode("auto", workspace=False)
    visible_token = llm.set_user_visible(True)
    callback_token = llm.set_stream_callback(values.append)
    from agent.providers import openai_compat

    def stream_completion(*args, on_delta=None, **kwargs):
        on_delta("KARNA is checking.")
        return {"id": "stream-1", "model": "free-model", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "KARNA is checking.", "tool_calls": None},
                "finish_reason": "stop"}], "usage": {"prompt_tokens": 8, "completion_tokens": 4}}

    monkeypatch.setattr(openai_compat, "stream_completion", stream_completion)
    monkeypatch.setattr(llm, "_record_provider_attempt", lambda *a, **kw: None)
    try:
        out = llm._create_raw(model="ignored", messages=[{"role": "user", "content": "hello"}],
                              tools=[{"type": "function", "function": {"name": "show_deadlines", "parameters": {}}}])
        assert out.choices[0].message.content == "KARNA is checking."
        assert values == ["KARNA is checking."]
        assert llm.last_meta()["provider"] == "openrouter"
        assert llm.last_meta()["model"] == "free-model"
    finally:
        llm.reset_stream_callback(callback_token)
        llm.reset_user_visible(visible_token)


def test_groq_tool_stream_collects_function_call_fragments(monkeypatch):
    from types import SimpleNamespace as NS

    fragments = [
        NS(choices=[NS(delta=NS(content="Checking.", tool_calls=None), finish_reason=None)], usage=None),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[NS(index=0, id="call-1",
             function=NS(name="show_deadlines", arguments='{"days":'))]), finish_reason=None)], usage=None),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[NS(index=0, id=None,
             function=NS(name=None, arguments="3}"))]), finish_reason="tool_calls")], usage=None),
    ]
    client = NS(chat=NS(completions=NS(create=lambda **kwargs: iter(fragments))))
    import agent.groq_client as groq_client
    monkeypatch.setattr(groq_client, "groq_raw_client", lambda: client)
    text = []
    route = model_router.Route("groq", "openai/gpt-oss-120b", "test")
    out = llm._stream_tool_completion(route, {"messages": [{"role": "user", "content": "show deadlines"}],
                                             "tools": [{"type": "function"}], "max_tokens": 60}, text.append)
    call = out.choices[0].message.tool_calls[0]
    assert text == ["Checking."]
    assert call.function.name == "show_deadlines"
    assert call.function.arguments == '{"days":3}'
    assert out.usage.prompt_tokens > 0


def test_provider_keys_missing_returns_clear_route_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(RuntimeError, match="No configured AI provider"):
        model_router.routes([{"role": "user", "content": "hello"}])


def test_context_compactor_keeps_system_and_recent_turns(monkeypatch):
    monkeypatch.setenv("KARNA_CONTEXT_MAX_CHARS", "4000")
    messages = [{"role": "system", "content": "Keep the KARNA rules."}]
    messages.extend({"role": "user", "content": ("old turn " + str(i) + " ") * 180} for i in range(8))
    messages.append({"role": "user", "content": "newest question"})
    result = compact(messages, recent_turns=2)
    assert result[0]["content"] == "Keep the KARNA rules."
    assert result[-1]["content"] == "newest question"
    assert any("Earlier conversation turns omitted" in m.get("content", "") for m in result)
