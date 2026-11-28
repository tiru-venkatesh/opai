"""Small OpenAI-compatible HTTP adapter for Gemini and OpenRouter."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator


class ProviderError(RuntimeError):
    def __init__(self, provider: str, status: int, message: str, retryable: bool):
        super().__init__(message)
        self.provider, self.status, self.retryable = provider, status, retryable


_CONFIG = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "GEMINI_TIMEOUT"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "OPENROUTER_TIMEOUT"),
}
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def _safe_error_message(status: int) -> str:
    if status == 429:
        return "Provider rate limit or quota exceeded"
    if status in (401, 403):
        return "Provider rejected its server-side credentials"
    if status in (408, 409) or status >= 500:
        return "Provider is temporarily unavailable"
    return "Provider request failed"


def _stream_error(provider: str, data: Dict[str, Any]) -> None:
    error = data.get("error")
    if not error:
        return
    raw_status = error.get("status", error.get("status_code", error.get("code"))) if isinstance(error, dict) else None
    try:
        status = int(raw_status)
    except (TypeError, ValueError):
        status = 502
    raise ProviderError(provider, status, _safe_error_message(status), status in _RETRYABLE_STATUS)


def _body(model: str, messages, *, max_tokens=2048, temperature=0.2, tools=None, response_format=None):
    body: Dict[str, Any] = {"model": model, "messages": messages, "max_tokens": int(max_tokens), "temperature": float(temperature)}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format:
        body["response_format"] = response_format
    if model == "openrouter/free":
        body["provider"] = {"data_collection": "deny", "allow_fallbacks": True}
    return body


def _request(provider: str, model: str, messages, *, max_tokens=2048, temperature=0.2, tools=None, response_format=None, stream=False):
    url, key_env, timeout_env = _CONFIG[provider]
    key = os.getenv(key_env, "").strip()
    if not key:
        raise ProviderError(provider, 503, f"{key_env} is not configured", False)
    body = _body(model, messages, max_tokens=max_tokens, temperature=temperature, tools=tools, response_format=response_format)
    if stream:
        body["stream"] = True
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = os.getenv("OPAI_PUBLIC_URL", "https://opai.live")
        headers["X-Title"] = "OPAI KARNA"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        retries = min(2, max(0, int(os.getenv("KARNA_PROVIDER_MAX_RETRIES", "1"))))
    except ValueError:
        retries = 1
    timeout = float(os.getenv(timeout_env, "45"))
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in _RETRYABLE_STATUS
            if exc.code in (408, 500, 502, 503, 504) and attempt < retries:
                time.sleep(0.25 * (2 ** attempt))
                continue
            raise ProviderError(provider, exc.code, _safe_error_message(exc.code), retryable) from None
        except (TimeoutError, OSError) as exc:
            if attempt < retries:
                time.sleep(0.25 * (2 ** attempt))
                continue
            raise ProviderError(provider, 503, type(exc).__name__, True) from None
    raise ProviderError(provider, 503, "Provider request failed", True)


def complete(provider: str, model: str, messages, *, max_tokens=2048, temperature=0.2, tools=None, response_format=None) -> Dict[str, Any]:
    with _request(provider, model, messages, max_tokens=max_tokens, temperature=temperature, tools=tools, response_format=response_format) as response:
        try:
            data = json.loads(response.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ProviderError(provider, 502, "Provider returned invalid JSON", True) from None
    if not isinstance(data, dict) or not data.get("choices"):
        raise ProviderError(provider, 502, "Provider returned an invalid completion", True)
    usage = data.get("usage")
    if isinstance(usage, dict):
        usage["prompt_tokens"] = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        usage["completion_tokens"] = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        data["usage"] = usage
    return data


def stream(provider: str, model: str, messages, *, max_tokens=2048, temperature=0.2) -> Iterator[str]:
    yielded = False
    with _request(provider, model, messages, max_tokens=max_tokens, temperature=temperature, stream=True) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
                _stream_error(provider, data)
                delta = (((data.get("choices") or [{}])[0]).get("delta") or {}).get("content")
                if isinstance(delta, str) and delta:
                    yielded = True
                    yield delta
            except (ValueError, TypeError, AttributeError):
                continue
    if not yielded:
        raise ProviderError(provider, 502, "Provider returned an empty stream", True)


def stream_completion(provider: str, model: str, messages, *, max_tokens=2048, temperature=0.2,
                      tools=None, response_format=None, on_delta=None) -> Dict[str, Any]:
    """Stream an OpenAI-compatible completion, forwarding visible text and collecting tool-call deltas."""
    content = []
    tool_calls: Dict[int, Dict[str, str]] = {}
    completion_id, served_model, finish_reason, usage = "", model, None, None
    with _request(provider, model, messages, max_tokens=max_tokens, temperature=temperature,
                  tools=tools, response_format=response_format, stream=True) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except (ValueError, TypeError):
                continue
            _stream_error(provider, data)
            completion_id = data.get("id") or completion_id
            served_model = data.get("model") or served_model
            usage = data.get("usage") or usage
            for choice in data.get("choices") or []:
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    content.append(text)
                    if on_delta:
                        on_delta(text)
                for part in delta.get("tool_calls") or []:
                    index = int(part.get("index", 0))
                    call = tool_calls.setdefault(index, {"id": "", "type": "function", "name": "", "arguments": ""})
                    call["id"] += part.get("id") or ""
                    fn = part.get("function") or {}
                    call["name"] += fn.get("name") or ""
                    call["arguments"] += fn.get("arguments") or ""
    if not content and not tool_calls:
        raise ProviderError(provider, 502, "Provider returned an empty stream", True)
    normalized_calls = [
        {"id": value["id"] or f"call_{index}", "type": "function",
         "function": {"name": value["name"], "arguments": value["arguments"]}}
        for index, value in sorted(tool_calls.items())
    ]
    message = {"role": "assistant", "content": "".join(content) or None,
               "tool_calls": normalized_calls or None}
    if not isinstance(usage, dict) or not (usage.get("prompt_tokens") or usage.get("input_tokens")
                                            or usage.get("completion_tokens") or usage.get("output_tokens")):
        prompt_estimate = 0
        for message_item in messages or []:
            value = message_item.get("content")
            prompt_estimate += len(value) if isinstance(value, str) else sum(
                len(str(part.get("text", ""))) for part in (value or []) if isinstance(part, dict))
        output_estimate = sum(map(len, content)) + sum(len(c["name"]) + len(c["arguments"]) for c in tool_calls.values())
        usage = {"prompt_tokens": (prompt_estimate + 3) // 4,
                 "completion_tokens": (output_estimate + 3) // 4}
    else:
        usage["prompt_tokens"] = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        usage["completion_tokens"] = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return {"id": completion_id, "model": served_model,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": finish_reason or ("tool_calls" if normalized_calls else "stop")}],
            "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0}}
