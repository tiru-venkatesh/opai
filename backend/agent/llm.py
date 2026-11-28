"""
KARNA LLM gateway: local privacy-aware routing across Groq, Gemini, OpenRouter and optional legacy providers.

Every model call in the backend goes through `get_client()`, which returns an object shaped like the
OpenAI/Groq SDK client (`client.chat.completions.create(...)`, `.choices[0].message.content`, `.tool_calls`).
That lets all existing call sites (RAG answers, general chat, router, tool loop, vision, JSON extraction)
run on Claude without being rewritten.

Provider selection (env):
  KARNA_DEFAULT_MODE auto | fast | think | expert (default auto); user request mode may override it.
  GROQ_API_KEY / GROQ_MODEL, GEMINI_API_KEY / GEMINI_MODEL, OPENROUTER_API_KEY / OPENROUTER_MODEL.
  Paid models are disabled unless KARNA_ENABLE_PAID_MODELS=true. Gemini workspace routing also requires
  KARNA_GEMINI_WORKSPACE_ALLOWED=true; OpenRouter is never used for private workspace data.
  HUGGINGFACE_API_KEY enables the existing optional Hugging Face chat-picker entries.

User-selectable models: only the FINAL answer in chat / General / RAG uses `final_answer()`. Routing, memory extraction,
JSON-mode and tool-calling calls keep using get_client() and never see the picker.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import contextvars
import urllib.request
import urllib.error
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple

log = logging.getLogger("opa.llm")

DEFAULT_FAST = "claude-haiku-5-5"
DEFAULT_BALANCED = "claude-sonnet-5-5"
DEFAULT_DEEP = "claude-opus-5-5"


# ----------------------------------------------------------------------------- provider selection
def _key(name: str) -> str:
    return os.getenv(name, "").strip()


def provider() -> Optional[str]:
    """Configured default provider; per-request selection is handled by model_router."""
    pref = (_key("KARNA_PROVIDER") or "auto").lower()
    if pref in ("anthropic", "claude"):
        if _key("ANTHROPIC_API_KEY") and os.getenv("KARNA_ENABLE_PAID_MODELS", "false").lower() in ("1", "true", "yes", "on"):
            return "anthropic"
    if pref == "groq":
        if _key("GROQ_API_KEY"):
            return "groq"
    if _key("GROQ_API_KEY"):
        return "groq"
    if _key("GEMINI_API_KEY"):
        return "gemini"
    if _key("OPENROUTER_API_KEY"):
        return "openrouter"
    if _key("ANTHROPIC_API_KEY") and os.getenv("KARNA_ENABLE_PAID_MODELS", "false").lower() in ("1", "true", "yes", "on"):
        return "anthropic"
    return None


def enabled() -> bool:
    return provider() is not None


def status() -> Dict[str, Any]:
    """Safe to expose on /v1/health: no secrets."""
    p = provider()
    return {
        "provider": p,
        "ai_available": p is not None,
        "anthropic_key_set": bool(_key("ANTHROPIC_API_KEY")) and os.getenv("KARNA_ENABLE_PAID_MODELS", "false").lower() in ("1", "true", "yes", "on"),
        "groq_key_set": bool(_key("GROQ_API_KEY")),
        "gemini_key_set": bool(_key("GEMINI_API_KEY")),
        "openrouter_key_set": bool(_key("OPENROUTER_API_KEY")),
        "huggingface_key_set": bool(_key("HUGGINGFACE_API_KEY")),
        "fallback": _fallback_allowed(),
        "models": {"fast": _model_for("fast"), "balanced": _model_for("balanced"),
                   "agent": _model_for("agent"), "deep": _model_for("deep")} if p == "anthropic" else None,
    }


def _fallback_allowed() -> bool:
    return os.getenv("KARNA_ENABLE_FALLBACK", os.getenv("KARNA_FALLBACK", "true")).strip().lower() not in ("off", "0", "false", "no")


# ----------------------------------------------------------------------------- model tiers
def _model_for(tier: str) -> str:
    balanced = _key("CLAUDE_MODEL") or DEFAULT_BALANCED
    return {
        "fast": _key("CLAUDE_FAST_MODEL") or DEFAULT_FAST,
        "balanced": balanced,
        "agent": _key("CLAUDE_AGENT_MODEL") or balanced,
        "deep": _key("CLAUDE_DEEP_MODEL") or DEFAULT_DEEP,
    }.get(tier, balanced)


def infer_tier(model: Optional[str], *, json_mode: bool, max_tokens: Optional[int], has_tools: bool, has_images: bool) -> str:
    """Old call sites pass Groq model names. Map them to a Claude tier by what the call is doing."""
    if has_images:
        return "balanced"
    if has_tools:
        return "agent"
    m = (model or "").lower()
    if m.startswith("claude"):
        return "custom"
    if (max_tokens is not None and max_tokens <= 150) or (json_mode and "20b" in m):
        return "fast"          # query rewrite, intent routing, field extraction
    return "balanced"


# ----------------------------------------------------------------------------- OpenAI -> Anthropic conversion
def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return str(content)


def _convert_user_content(content: Any) -> Any:
    """str stays str; OpenAI content parts (text / image_url data URIs or https URLs) become Anthropic blocks."""
    if not isinstance(content, list):
        return content if content else "(empty)"
    blocks: List[Dict[str, Any]] = []
    for p in content:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            if (p.get("text") or "").strip():
                blocks.append({"type": "text", "text": p["text"]})
        elif p.get("type") == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            m = re.match(r"data:([\w/+.-]+);base64,(.*)", url, re.S)
            if m:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2)}})
            elif url.startswith("http"):
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
    return blocks or "(empty)"


def _as_blocks(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)


def convert_messages(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """-> (system_text, anthropic_messages). Merges same-role neighbours and tool results; first turn is always 'user'."""
    system_parts: List[str] = []
    out: List[Dict[str, Any]] = []

    def push(role: str, blocks: List[Dict[str, Any]]):
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        if role in ("system", "developer"):
            t = _text_of(m.get("content"))
            if t.strip():
                system_parts.append(t)
        elif role == "user":
            push("user", _as_blocks(_convert_user_content(m.get("content"))))
        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []
            t = _text_of(m.get("content"))
            if t.strip():
                blocks.append({"type": "text", "text": t})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc["id"], "name": fn.get("name"), "input": args if isinstance(args, dict) else {}})
            push("assistant", blocks)
        elif role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id"), "content": _text_of(m.get("content")) or "(no output)"}])
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(start)"}]})
    # A tool_result block must come first inside its user message.
    for msg in out:
        if msg["role"] == "user":
            msg["content"].sort(key=lambda b: 0 if b.get("type") == "tool_result" else 1)
    return "\n\n".join(system_parts), out


def convert_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", t)
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    if out:
        out[-1] = {**out[-1], "cache_control": {"type": "ephemeral"}}      # tool list is identical every turn: cache it
    return out


_JSON_RULE = ("\n\nOUTPUT FORMAT: respond with exactly one valid JSON object and nothing else: "
              "no prose before or after, no markdown code fences.")


def extract_json(text: str) -> str:
    """Pull the first JSON object out of a model reply (handles fences / stray prose). Returns '{}' if none."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        json.loads(text)
        return text
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return json.dumps(obj)
            except ValueError:
                continue
    return "{}"


_STOP = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "tool_use": "tool_calls", "refusal": "stop"}


def _to_openai_shape(resp: Any, json_mode: bool, model: str) -> SimpleNamespace:
    text_parts, calls = [], []
    for b in getattr(resp, "content", None) or []:
        bt = getattr(b, "type", None)
        if bt == "text":
            text_parts.append(b.text)
        elif bt == "tool_use":
            calls.append(SimpleNamespace(id=b.id, type="function",
                                         function=SimpleNamespace(name=b.name, arguments=json.dumps(b.input or {}))))
    text = "".join(text_parts)
    if json_mode:
        text = extract_json(text)
    msg = SimpleNamespace(role="assistant", content=text, tool_calls=calls or None)
    u = getattr(resp, "usage", None)
    usage = SimpleNamespace(prompt_tokens=getattr(u, "input_tokens", 0) or 0, completion_tokens=getattr(u, "output_tokens", 0) or 0,
                            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0)
    return SimpleNamespace(
        id=getattr(resp, "id", ""), model=model,
        choices=[SimpleNamespace(index=0, message=msg, finish_reason=_STOP.get(getattr(resp, "stop_reason", None), "stop"))],
        usage=usage,
    )


# ----------------------------------------------------------------------------- Anthropic client
_anthropic = None


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        import anthropic
        _anthropic = anthropic.Anthropic(
            api_key=_key("ANTHROPIC_API_KEY"),
            timeout=float(os.getenv("ANTHROPIC_TIMEOUT", "60")),
            max_retries=int(os.getenv("ANTHROPIC_MAX_RETRIES", "2")),
        )
    return _anthropic


def _build_kwargs(kw: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
    messages = kw.get("messages") or []
    tools = kw.get("tools")
    json_mode = (kw.get("response_format") or {}).get("type") == "json_object"
    has_images = any(isinstance(m.get("content"), list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"])
                     for m in messages)
    tier = kw.get("tier") or infer_tier(kw.get("model"), json_mode=json_mode, max_tokens=kw.get("max_tokens"),
                                        has_tools=bool(tools), has_images=has_images)
    model = (kw.get("model") if tier == "custom" else _model_for(tier))
    system, msgs = convert_messages(messages)
    if json_mode:
        system += _JSON_RULE
    args: Dict[str, Any] = {"model": model, "messages": msgs, "max_tokens": int(kw.get("max_tokens") or (4096 if tier in ("balanced", "agent", "deep") else 1024))}
    if system.strip():
        args["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]   # stable prefix: cached
    if kw.get("temperature") is not None:
        args["temperature"] = max(0.0, min(1.0, float(kw["temperature"])))
    ct = convert_tools(tools)
    if ct:
        args["tools"] = ct
        tc = kw.get("tool_choice")
        args["tool_choice"] = {"type": "any"} if tc == "required" else {"type": "auto"}
    return args, json_mode, model


def _is_param_rejection(exc: Exception) -> bool:
    return type(exc).__name__ == "BadRequestError" and any(w in str(exc).lower() for w in ("temperature", "top_p", "deprecated"))


def _claude_create(**kw) -> SimpleNamespace:
    args, json_mode, model = _build_kwargs(kw)
    t0 = time.perf_counter()
    try:
        resp = _anthropic_client().messages.create(**args)
    except Exception as e:
        if "temperature" in args and _is_param_rejection(e):     # some models fix their own sampling: retry without it
            args.pop("temperature", None)
            resp = _anthropic_client().messages.create(**args)
        else:
            raise
    out = _to_openai_shape(resp, json_mode, model)
    log.info("llm provider=anthropic model=%s in=%s out=%s cache_read=%s ms=%.0f", model, out.usage.prompt_tokens,
             out.usage.completion_tokens, out.usage.cache_read_tokens, (time.perf_counter() - t0) * 1000)
    return out


def _groq_create(**kw):
    from .groq_client import groq_raw_client
    kw = {k: v for k, v in kw.items() if k != "tier"}
    return groq_raw_client().chat.completions.create(**kw)


def _compat_create(which: str, model: str, kw: Dict[str, Any]) -> SimpleNamespace:
    from .providers.openai_compat import complete
    data = complete(which, model, kw.get("messages") or [], max_tokens=kw.get("max_tokens") or 2048,
                    temperature=kw.get("temperature", 0.2), tools=kw.get("tools"), response_format=kw.get("response_format"))
    result = _namespace(data)
    result.model = model
    return result


def _namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_namespace(v) for v in value]
    return value


def _call_route(route: Any, kw: Dict[str, Any]) -> SimpleNamespace:
    args = dict(kw)
    if _user_visible.get():
        args["messages"] = _user_messages(kw.get("messages") or [], route.provider, route.model)
    if route.provider == "groq":
        args["model"] = route.model; args.pop("tier", None)
        return _groq_create(**args)
    if route.provider in ("gemini", "openrouter"):
        return _compat_create(route.provider, route.model, args)
    if route.provider == "anthropic":
        args["tier"] = "balanced"
        return _claude_create(**args)
    raise RuntimeError("Unsupported AI provider")


def _stream_tool_completion(route: Any, kw: Dict[str, Any], on_delta) -> SimpleNamespace:
    """Stream one tool-capable chat completion and normalize the final message."""
    from .context_manager import compact
    from . import model_router
    args = dict(kw)
    args["messages"] = compact(args.get("messages") or [])
    args["model"] = route.model
    if _user_visible.get():
        args["messages"] = _user_messages(args["messages"], route.provider, route.model)
    if route.provider == "groq":
        from .groq_client import groq_raw_client
        args.pop("tier", None)
        args["stream"] = True
        response = groq_raw_client().chat.completions.create(**args)
        content, calls, finish_reason, usage = [], {}, None, None
        for chunk in response:
            usage = getattr(chunk, "usage", None) or usage
            for choice in getattr(chunk, "choices", None) or []:
                finish_reason = getattr(choice, "finish_reason", None) or finish_reason
                delta = getattr(choice, "delta", None)
                text = getattr(delta, "content", None)
                if isinstance(text, str) and text:
                    content.append(text)
                    on_delta(text)
                for part in getattr(delta, "tool_calls", None) or []:
                    index = int(getattr(part, "index", 0) or 0)
                    call = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    call["id"] += getattr(part, "id", None) or ""
                    fn = getattr(part, "function", None)
                    call["name"] += getattr(fn, "name", None) or ""
                    call["arguments"] += getattr(fn, "arguments", None) or ""
        normalized = [SimpleNamespace(id=value["id"] or f"call_{i}", type="function",
                                      function=SimpleNamespace(name=value["name"], arguments=value["arguments"]))
                      for i, value in sorted(calls.items())]
        if not content and not normalized:
            raise RuntimeError("Provider returned an empty stream")
        if not usage or not (getattr(usage, "prompt_tokens", 0) or getattr(usage, "completion_tokens", 0)):
            input_tokens = model_router.estimated_tokens(args.get("messages") or [])
            output_chars = sum(map(len, content)) + sum(len(c.function.name) + len(c.function.arguments) for c in normalized)
            usage = SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=(output_chars + 3) // 4)
        message = SimpleNamespace(role="assistant", content="".join(content) or None, tool_calls=normalized or None)
        return SimpleNamespace(id="", model=route.model,
                               choices=[SimpleNamespace(index=0, message=message,
                                                        finish_reason=finish_reason or ("tool_calls" if normalized else "stop"))],
                               usage=usage or SimpleNamespace(prompt_tokens=0, completion_tokens=0))
    if route.provider in ("gemini", "openrouter"):
        from .providers.openai_compat import stream_completion
        args.pop("tier", None)
        data = stream_completion(route.provider, route.model, args.get("messages") or [],
                                 max_tokens=args.get("max_tokens") or 2048,
                                 temperature=args.get("temperature", 0.2),
                                 tools=args.get("tools"), response_format=args.get("response_format"),
                                 on_delta=on_delta)
        result = _namespace(data)
        result.model = getattr(result, "model", None) or route.model
        return result
    # The legacy paid Anthropic path streams text through stream_chat. Keep its
    # tool-call contract intact here and forward its completed text once.
    result = _call_route(route, args)
    text = result.choices[0].message.content or ""
    if text:
        on_delta(text)
    return result


def _create_raw(**kw):
    from . import model_router
    from provider_quota import available as provider_quota_available
    messages = kw.get("messages") or []
    excluded_providers = set(kw.pop("_exclude_providers", set()) or ())
    routes = model_router.routes(messages, mode=_request_mode.get(), workspace=_workspace.get(),
                                 max_tokens=kw.get("max_tokens") or 0)
    if excluded_providers:
        routes = [route for route in routes if route.provider not in excluded_providers]
        if not routes:
            raise RuntimeError("No configured AI provider is available after excluding a failed provider.")
    selected = _sel.get()
    requested_entry = selected[0] if selected else None
    selected_entry = requested_entry if requested_entry and requested_entry.provider in {"groq", "gemini", "openrouter", "anthropic"} else None
    selected_route_added = False
    if selected_entry and selected_entry.provider in {"groq", "gemini", "openrouter", "anthropic"}:
        selected_model = selected_entry.model_id or _model_for(selected_entry.claude_tier or "balanced")
        private = model_router.is_private(messages, workspace=_workspace.get())
        approved = not private or model_router._workspace_allowed(selected_entry.provider)
        reserved = model_router.estimated_tokens(messages, kw.get("max_tokens") or 0)
        if (approved and model_router.available(selected_entry.provider) and model_router._healthy(selected_entry.provider)
                and provider_quota_available(selected_entry.provider, reserved_tokens=reserved)):
            from .model_router import Route
            selected_route = Route(selected_entry.provider, selected_model, "selected")
            routes = [selected_route] + [r for r in routes if r.provider != selected_entry.provider]
            selected_route_added = True
    _fell.set(False)
    _last_provider.set(None)
    _last_model.set(None)
    if _user_visible.get():
        _meta.set(None)
    streamed_text = []
    last_error = None
    for i, route in enumerate(routes):
        started = time.perf_counter()
        try:
            fallback_used = i > 0 or bool(selected_entry and (
                not selected_route_added or route.provider != selected_entry.provider))
            if _stream_callback.get() and _user_visible.get() and kw.get("tools"):
                def on_delta(piece):
                    streamed_text.append(piece)
                    _stream_callback.get()(piece)
                out = _stream_tool_completion(route, kw, on_delta)
            else:
                out = _call_route(route, kw)
            elapsed_ms = (time.perf_counter() - started) * 1000
            model_router.record(route.provider, True, elapsed_ms)
            _last_provider.set(route.provider)
            _last_model.set(getattr(out, "model", "") or route.model)
            _fell.set(fallback_used)
            if _user_visible.get():
                _meta.set({"key": selected_entry.key if selected_entry else "auto",
                           "label": selected_entry.label if selected_entry else "Auto",
                           "provider": route.provider, "model": _last_model.get(),
                           "fallback": fallback_used, "route": _request_mode.get()})
            _record_provider_attempt(route.provider, route.model, error=False, latency_ms=elapsed_ms,
                                     tokens_in=getattr(getattr(out, "usage", None), "prompt_tokens", 0),
                                     tokens_out=getattr(getattr(out, "usage", None), "completion_tokens", 0), fallback=fallback_used)
            return out
        except Exception as exc:
            last_error = exc
            elapsed_ms = (time.perf_counter() - started) * 1000
            model_router.record(route.provider, False, elapsed_ms)
            failed_fallback = i > 0 or bool(selected_entry and not selected_route_added)
            _record_provider_attempt(route.provider, route.model, error=True, latency_ms=elapsed_ms, fallback=failed_fallback)
            log.warning("provider=%s failed retryable=%s type=%s", route.provider, getattr(exc, "retryable", True), type(exc).__name__)
            if streamed_text or not getattr(exc, "retryable", True) or i + 1 >= len(routes):
                raise
    raise last_error or RuntimeError("No compatible AI provider available")


def _create(**kw):
    """Metered entry point: quota check before the call, ledger row after it (see metering.py)."""
    import metering
    started = time.perf_counter()
    tok = metering.begin(kw.get("model"), kw.get("tier"))
    try:
        resp = _create_raw(**kw)
    except Exception:
        metering.finish(tok, None, error=True)
        raise
    metering.finish(tok, resp, provider=_last_provider.get() or provider(), latency_ms=(time.perf_counter() - started) * 1000, fallback=_fell.get())
    return resp


class _Completions:
    def create(self, **kw):
        return _create(**kw)


class _Chat:
    completions = _Completions()


class Client:
    """Drop-in for the Groq/OpenAI client: client.chat.completions.create(model=..., messages=[...], ...)."""
    chat = _Chat()


_client = Client()


def get_client() -> Client:
    if provider() is None:
        raise RuntimeError("No AI provider key is configured. Set GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY on the backend.")
    return _client


# ----------------------------------------------------------------------------- streaming
def stream_chat(messages: List[Dict[str, Any]], *, tier: str = "balanced", max_tokens: int = 2000,
                temperature: Optional[float] = 0.3) -> Iterator[str]:
    """Stream live text. Fallback is attempted only before the first emitted token."""
    from . import model_router
    selected = _sel.get()
    force_fallback = False
    if selected and selected[0] is not None:
        entry = selected[0]
        selected_model = entry.model_id or _model_for(entry.claude_tier or tier)
        if model_router.classify(messages) == "multimodal" and entry.provider == "groq":
            selected_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
        selected_route = model_router.Route(entry.provider, selected_model, "selected")
        from provider_quota import available as provider_quota_available
        private = model_router.is_private(messages, workspace=_workspace.get())
        quota_ok = provider_quota_available(entry.provider, reserved_tokens=model_router.estimated_tokens(messages, max_tokens))
        provider_ok = model_router.available(entry.provider) and model_router._healthy(entry.provider)
        if (private and not model_router._workspace_allowed(entry.provider)) or not quota_ok or not provider_ok:
            force_fallback = True
            routes = model_router.routes(messages, mode=_request_mode.get(), workspace=_workspace.get(), max_tokens=max_tokens)
        else:
            try:
                fallbacks = model_router.routes(messages, mode=_request_mode.get(), workspace=_workspace.get(), max_tokens=max_tokens)
            except RuntimeError:
                fallbacks = []
            routes = [selected_route] + [r for r in fallbacks if r.provider != selected_route.provider]
    else:
        routes = model_router.routes(messages, mode=_request_mode.get(), workspace=_workspace.get(), max_tokens=max_tokens)
    import metering
    chars_in = sum(len(str(m.get("content", ""))) for m in messages)
    tok = metering.begin(routes[0].model, tier)
    chars_out = 0
    _fell.set(force_fallback)
    _last_provider.set(None)
    _last_model.set(None)
    visible_token = _user_visible.set(True)
    metering_closed = False
    try:
        from .context_manager import compact
        messages = compact(messages)
        for index, route in enumerate(routes):
            started = time.perf_counter()
            try:
                routed_messages = _user_messages(messages, route.provider, route.model)
                if route.provider == "anthropic":
                    args, _, _ = _build_kwargs({"messages": routed_messages, "tier": tier, "max_tokens": max_tokens, "temperature": temperature})
                    with _anthropic_client().messages.stream(**args) as response:
                        iterator = iter(response.text_stream)
                        first = next(iterator, "")
                        if first:
                            chars_out += len(first)
                            yield first
                        for delta in iterator:
                            chars_out += len(delta)
                            yield delta
                elif route.provider == "groq":
                    from .groq_client import groq_raw_client
                    chunks = iter(groq_raw_client().chat.completions.create(
                        model=route.model, messages=routed_messages, max_tokens=max_tokens,
                        temperature=temperature or .3, stream=True))
                    first_chunk = next(chunks, None)
                    first = ((first_chunk.choices[0].delta.content if first_chunk and first_chunk.choices else "") or "")
                    if first:
                        chars_out += len(first)
                        yield first
                    for chunk in chunks:
                        delta = ((chunk.choices[0].delta.content if chunk.choices else "") or "")
                        if delta:
                            chars_out += len(delta)
                            yield delta
                else:
                    from .providers.openai_compat import stream as compat_stream
                    chunks = iter(compat_stream(route.provider, route.model, routed_messages,
                                                max_tokens=max_tokens, temperature=temperature or .3))
                    first = next(chunks, "")
                    if first:
                        chars_out += len(first)
                        yield first
                    for delta in chunks:
                        chars_out += len(delta)
                        yield delta
                elapsed_ms = (time.perf_counter() - started) * 1000
                model_router.record(route.provider, True, elapsed_ms)
                fallback_used = force_fallback or index > 0
                _last_provider.set(route.provider)
                _last_model.set(route.model)
                _fell.set(fallback_used)
                _record_provider_attempt(route.provider, route.model, error=False, latency_ms=elapsed_ms,
                                         tokens_in=chars_in // 4, tokens_out=chars_out // 4,
                                         fallback=fallback_used)
                metering.finish(tok, None, provider=route.provider, kind="llm_stream", tokens_in=chars_in // 4,
                                tokens_out=chars_out // 4, latency_ms=elapsed_ms, fallback=fallback_used)
                metering_closed = True
                return
            except GeneratorExit:
                elapsed_ms = (time.perf_counter() - started) * 1000
                _record_provider_attempt(route.provider, route.model, error=False, latency_ms=elapsed_ms,
                                         tokens_in=chars_in // 4, tokens_out=chars_out // 4,
                                         fallback=force_fallback or index > 0)
                metering.finish(tok, None, provider=route.provider, kind="llm_stream", error=True,
                                tokens_in=chars_in // 4, tokens_out=chars_out // 4, latency_ms=elapsed_ms,
                                fallback=force_fallback or index > 0)
                metering_closed = True
                raise
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                model_router.record(route.provider, False, elapsed_ms)
                _record_provider_attempt(route.provider, route.model, error=True, latency_ms=elapsed_ms,
                                         fallback=force_fallback or index > 0)
                if chars_out or not getattr(exc, "retryable", True) or index + 1 >= len(routes):
                    metering.finish(tok, None, provider=route.provider, kind="llm_stream", error=True,
                                    tokens_in=chars_in // 4, tokens_out=chars_out // 4, latency_ms=elapsed_ms,
                                    fallback=force_fallback or index > 0)
                    metering_closed = True
                    raise
                force_fallback = True
    except GeneratorExit:
        raise
    except Exception:
        if not metering_closed:
            metering.finish(tok, None, provider=_last_provider.get(), kind="llm_stream", error=True,
                            tokens_in=chars_in // 4, tokens_out=chars_out // 4)
        raise
    finally:
        _user_visible.reset(visible_token)


# ----------------------------------------------------------------------------- user-selected model (final answers only)
_fell: "contextvars.ContextVar[bool]" = contextvars.ContextVar("karna_fell_back", default=False)
_sel: "contextvars.ContextVar[Any]" = contextvars.ContextVar("karna_selected", default=None)    # (entry, who) | None
_meta: "contextvars.ContextVar[Optional[Dict[str, Any]]]" = contextvars.ContextVar("karna_meta", default=None)
_request_mode: "contextvars.ContextVar[str]" = contextvars.ContextVar("karna_ai_mode", default="auto")
_workspace: "contextvars.ContextVar[bool]" = contextvars.ContextVar("karna_workspace_private", default=True)
_last_provider: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("karna_last_provider", default=None)
_last_model: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("karna_last_model", default=None)
_user_visible: "contextvars.ContextVar[bool]" = contextvars.ContextVar("karna_user_visible_answer", default=False)
_stream_callback: "contextvars.ContextVar[Any]" = contextvars.ContextVar("karna_stream_callback", default=None)


def _user_messages(messages: List[Dict[str, Any]], provider_name: str, model: str) -> List[Dict[str, Any]]:
    from .karna_prompt import KARNA_CHAT_SYSTEM
    out = [dict(m) for m in messages]
    return [
        {"role": "system", "content": KARNA_CHAT_SYSTEM},
        {"role": "system", "content": f"Runtime model metadata for disclosure if asked: provider={provider_name}; model={model}."},
        *out,
    ]


def _record_provider_attempt(provider_name: str, model: str, **kwargs) -> None:
    try:
        import metering
        metering.record_provider_attempt(provider_name, model, **kwargs)
    except Exception as exc:
        log.warning("provider attempt telemetry skipped for %s (%s)", provider_name, type(exc).__name__)


def set_stream_callback(callback):
    """Install a request-scoped callback for streaming user-visible final answers."""
    return _stream_callback.set(callback)


def reset_stream_callback(token) -> None:
    _stream_callback.reset(token)


class StreamCancelled(RuntimeError):
    """Raised when a caller closes an in-progress answer stream."""
    retryable = False


def set_user_visible(enabled: bool = True):
    """Mark provider calls in this request as part of a user-visible answer."""
    return _user_visible.set(bool(enabled))


def reset_user_visible(token) -> None:
    _user_visible.reset(token)


def set_request_mode(mode: Optional[str] = None, *, workspace: Optional[bool] = None) -> None:
    value = (mode or _request_mode.get() or "auto").strip().lower()
    configured = os.getenv("KARNA_DEFAULT_MODE", "auto").strip().lower()
    if value == "auto" and configured in {"fast", "think", "expert"}:
        value = configured
    if value not in {"auto", "fast", "think", "expert"}:
        raise ValueError("ai_mode must be auto, fast, think, or expert")
    _request_mode.set(value)
    if workspace is not None:
        _workspace.set(bool(workspace))

HF_URL = "https://router.huggingface.co/v1/chat/completions"


def select(model_key: Optional[str], mode: str, who: str = "") -> Any:
    """Validate the client's model_key against the server catalog and remember it for this request.
    Raises agent.model_catalog.ModelChoiceError (400 unknown / not allowed in this mode). Returns the entry or None (= Auto)."""
    from . import model_catalog
    entry = model_catalog.resolve(model_key, mode)
    _sel.set((entry, who) if entry else None)
    _meta.set(None)
    _fell.set(False)
    return entry


def last_meta() -> Optional[Dict[str, Any]]:
    """{'key','label','provider','model','fallback'} for the last model-written answer in this request, else None."""
    return _meta.get()


def _hf_create(entry: Any, messages: List[Dict[str, Any]], max_tokens: int, temperature: Optional[float]) -> SimpleNamespace:
    key = _key("HUGGINGFACE_API_KEY")
    if not key:
        raise RuntimeError("HUGGINGFACE_API_KEY is not configured")
    plain = [{"role": m.get("role"), "content": _text_of(m.get("content"))} for m in messages
             if m.get("role") in ("system", "user", "assistant")]
    body = {"model": entry.model_id, "messages": plain, "max_tokens": int(max_tokens)}
    if temperature is not None:
        body["temperature"] = max(0.0, min(1.5, float(temperature)))
    req = urllib.request.Request(HF_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("HF_TIMEOUT", "60"))) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HuggingFace HTTP {e.code}") from None
    text = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    log.info("llm provider=hf model=%s ms=%.0f", entry.model_id, (time.perf_counter() - t0) * 1000)
    msg = SimpleNamespace(role="assistant", content=text, tool_calls=None)
    return SimpleNamespace(id=data.get("id", ""), model=entry.model_id, choices=[SimpleNamespace(index=0, message=msg, finish_reason="stop")],
                           usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0))


def _call_entry(entry: Any, messages, max_tokens, temperature) -> SimpleNamespace:
    if entry.provider == "anthropic":
        return _claude_create(messages=messages, tier=entry.claude_tier, max_tokens=max_tokens, temperature=temperature)
    if entry.provider == "groq":
        return _groq_create(model=entry.model_id, messages=messages, max_tokens=max_tokens, temperature=temperature)
    if entry.provider in ("gemini", "openrouter"):
        return _compat_create(entry.provider, entry.model_id, {"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
    return _hf_create(entry, messages, max_tokens, temperature)


def charge(entry: Any, who: str) -> None:
    from . import model_catalog
    model_catalog.charge(entry, who)


def final_answer(messages: List[Dict[str, Any]], *, default_model: str, max_tokens: int, temperature: Optional[float] = 0.2,
                 entry: Any = None, who: Optional[str] = None) -> str:
    """The user-visible answer. Honors the model chosen with select() (or an explicit entry); otherwise the existing default
    routing. If the chosen model fails, falls back to the default routing and records fallback=True so the UI can say so."""
    if entry is None:
        cur = _sel.get()
        entry, who = (cur if cur else (None, who))
    _fell.set(False)
    callback = _stream_callback.get()
    if callback and (entry is None or entry.provider != "hf"):
        from .context_manager import compact
        messages = compact(messages)
        tier = entry.claude_tier if entry is not None and entry.claude_tier else "balanced"
        pieces = []
        iterator = stream_chat(messages, tier=tier, max_tokens=max_tokens, temperature=temperature)
        try:
            for piece in iterator:
                pieces.append(piece)
                callback(piece)
        finally:
            iterator.close()
        reply = "".join(pieces)
        _meta.set(stream_meta(entry))
        return reply
    if entry is None:
        from .context_manager import compact
        messages = compact(messages)
        visible_token = _user_visible.set(True)
        try:
            out = _create(messages=messages, model=default_model, max_tokens=max_tokens, temperature=temperature)
        finally:
            _user_visible.reset(visible_token)
        p = _last_provider.get() or provider()
        fb = _fell.get()
        _meta.set({"key": "auto", "label": "Auto", "provider": p,
                   "model": getattr(out, "model", "") or default_model, "fallback": bool(fb), "route": _request_mode.get()})
        return out.choices[0].message.content or ""
    fb = False
    metering_token = None
    started = time.perf_counter()
    provider_started = False
    try:
        from . import model_router
        private = model_router.is_private(messages, workspace=_workspace.get())
        from provider_quota import available as provider_quota_available
        quota_ok = provider_quota_available(entry.provider, reserved_tokens=model_router.estimated_tokens(messages, max_tokens))
        if (private and not model_router._workspace_allowed(entry.provider)) or not quota_ok:
            raise RuntimeError("Selected provider is not approved for private content")
        from .context_manager import compact
        messages = compact(messages)
        import metering
        metering_token = metering.begin(entry.model_id or entry.key, entry.tier)
        visible_token = _user_visible.set(True)
        try:
            provider_started = True
            out = _call_entry(entry, _user_messages(messages, entry.provider, entry.model_id or _model_for(entry.claude_tier or "balanced")), max_tokens, temperature)
        finally:
            _user_visible.reset(visible_token)
        elapsed_ms = (time.perf_counter() - started) * 1000
        from . import model_router
        model_router.record(entry.provider, True, elapsed_ms)
        _last_provider.set(entry.provider)
        _last_model.set(getattr(out, "model", "") or entry.model_id)
        u = getattr(out, "usage", None)
        _record_provider_attempt(entry.provider, _last_model.get() or entry.model_id or "", error=False,
                                 latency_ms=elapsed_ms, tokens_in=getattr(u, "prompt_tokens", 0),
                                 tokens_out=getattr(u, "completion_tokens", 0))
        metering.finish(metering_token, out, provider=entry.provider, latency_ms=elapsed_ms)
    except Exception as e:
        if entry is not None and provider_started:
            from . import model_router
            elapsed_ms = (time.perf_counter() - started) * 1000
            model_router.record(entry.provider, False, elapsed_ms)
            _record_provider_attempt(entry.provider, entry.model_id or entry.key, error=True,
                                     latency_ms=elapsed_ms)
        if getattr(e, "status_code", None) == 429 or type(e).__name__ == "QuotaExceeded":
            raise
        log.warning("selected model %s failed (%s); using default routing", entry.key, type(e).__name__)
        _fell.set(False)
        out = _create(messages=messages, model=default_model, max_tokens=max_tokens, temperature=temperature,
                      _exclude_providers={entry.provider} if provider_started else set())
        fb = True
    prov = (_last_provider.get() or provider()) if fb else entry.provider
    _meta.set({"key": entry.key, "label": entry.label, "provider": prov,
               "model": getattr(out, "model", "") or entry.model_id, "fallback": fb or _fell.get()})
    return out.choices[0].message.content or ""


def stream_meta(entry: Any = None) -> Dict[str, Any]:
    """Label for a reply produced by stream_chat (Claude tier, or Groq when Claude isn't the active provider)."""
    p = _last_provider.get() or provider()
    model = _last_model.get()
    if _meta.get() and _last_provider.get():
        return {**_meta.get(), "provider": p, "model": model or _meta.get().get("model"), "fallback": _fell.get()}
    if p and model:
        return {"key": "auto" if entry is None else entry.key, "label": "Auto" if entry is None else entry.label,
                "provider": p, "model": model, "fallback": _fell.get()}
    if entry is not None and entry.provider == "anthropic" and p == "anthropic":
        return {"key": entry.key, "label": entry.label, "provider": "anthropic", "model": _model_for(entry.claude_tier), "fallback": False}
    if p == "anthropic":
        return {"key": "auto", "label": "Auto", "provider": "anthropic", "model": _model_for("balanced"), "fallback": False}
    return {"key": "auto" if entry is None else entry.key, "label": "Auto" if entry is None else entry.label, "provider": "groq",
            "model": os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), "fallback": entry is not None}
