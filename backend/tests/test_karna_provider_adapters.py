import io
import json
import urllib.error

import pytest

from agent.providers import openai_compat


@pytest.mark.parametrize(
    "provider,key_name,url",
    [
        ("gemini", "GEMINI_API_KEY", "generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
        ("openrouter", "OPENROUTER_API_KEY", "openrouter.ai/api/v1/chat/completions"),
    ],
)
def test_provider_request_uses_server_key_and_expected_endpoint(monkeypatch, provider, key_name, url):
    monkeypatch.setenv(key_name, "secret-test-key")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = json.loads(request.data.decode())
        seen["timeout"] = timeout
        return io.BytesIO(b'{"choices":[{"message":{"content":"hello"}}]}')

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", fake_urlopen)
    data = openai_compat.complete(provider, "test-model", [{"role": "user", "content": "hi"}])

    assert url in seen["url"]
    assert seen["headers"]["authorization"] == "Bearer secret-test-key"
    assert data["choices"][0]["message"]["content"] == "hello"
    if provider == "openrouter":
        assert seen["headers"]["http-referer"]
        assert seen["headers"]["x-title"] == "OPAI KARNA"


def test_openrouter_free_requests_provider_data_collection_denied():
    body = openai_compat._body("openrouter/free", [])
    assert body["provider"] == {"data_collection": "deny", "allow_fallbacks": True}


def test_sse_stream_yields_deltas_and_rejects_empty_stream(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    payload = (
        b'data: {"choices":[{"delta":{"content":"KAR"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"NA"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    monkeypatch.setattr(openai_compat, "_request", lambda *a, **kw: io.BytesIO(payload))
    assert list(openai_compat.stream("gemini", "test", [])) == ["KAR", "NA"]

    monkeypatch.setattr(openai_compat, "_request", lambda *a, **kw: io.BytesIO(b"data: [DONE]\n\n"))
    with pytest.raises(openai_compat.ProviderError, match="empty stream"):
        list(openai_compat.stream("gemini", "test", []))


def test_sse_error_event_preserves_rate_limit_for_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    payload = b'data: {"error":{"code":429,"message":"quota exhausted"}}\n\n'
    monkeypatch.setattr(openai_compat, "_request", lambda *a, **kw: io.BytesIO(payload))
    with pytest.raises(openai_compat.ProviderError) as caught:
        list(openai_compat.stream("gemini", "test", []))
    assert caught.value.status == 429 and caught.value.retryable
    assert "quota exhausted" not in str(caught.value)


def test_sse_tool_call_stream_is_normalized_and_text_is_forwarded(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    events = [
        {"id": "chat-1", "model": "free-model", "choices": [{"delta": {"content": "Checking."}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "type": "function",
                                                     "function": {"name": "show_deadlines", "arguments": '{"days":'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0,
                                                     "function": {"arguments": "3}"}}]}, "finish_reason": "tool_calls"}]},
    ]
    payload = b"".join(("data: " + json.dumps(e) + "\n\n").encode() for e in events) + b"data: [DONE]\n\n"
    monkeypatch.setattr(openai_compat, "_request", lambda *a, **kw: io.BytesIO(payload))
    forwarded = []
    result = openai_compat.stream_completion("openrouter", "openrouter/free", [], tools=[{"type": "function"}], on_delta=forwarded.append)

    assert forwarded == ["Checking."]
    call = result["choices"][0]["message"]["tool_calls"][0]
    assert call["id"] == "call-1"
    assert call["function"] == {"name": "show_deadlines", "arguments": '{"days":3}'}


def test_http_rate_limit_is_retryable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    response = io.BytesIO(b'{"error":{"message":"quota exhausted"}}')

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://provider.invalid", 429, "rate limited", {}, response)

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", fail)
    with pytest.raises(openai_compat.ProviderError) as caught:
        openai_compat.complete("gemini", "test", [])
    assert caught.value.status == 429 and caught.value.retryable


def test_transient_network_failure_gets_bounded_exponential_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("KARNA_PROVIDER_MAX_RETRIES", "2")
    calls, sleeps = [], []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError("temporary")
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(openai_compat.time, "sleep", sleeps.append)
    result = openai_compat.complete("gemini", "test", [])
    assert len(calls) == 3 and sleeps == [0.25, 0.5]
    assert result["choices"][0]["message"]["content"] == "ok"


def test_missing_key_fails_without_network(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(openai_compat.ProviderError) as caught:
        openai_compat.complete("openrouter", "openrouter/free", [])
    assert caught.value.status == 503 and not caught.value.retryable
