"""
KARNA LLM gateway: Claude first, Groq as automatic fallback.

Every model call in the backend goes through `get_client()`, which returns an object shaped like the
OpenAI/Groq SDK client (`client.chat.completions.create(...)`, `.choices[0].message.content`, `.tool_calls`).
That lets all existing call sites (RAG answers, general chat, router, tool loop, vision, JSON extraction)
run on Claude without being rewritten.

Provider selection (env):
  KARNA_PROVIDER     auto (default) | anthropic | groq
                     auto = Claude when ANTHROPIC_API_KEY is set, otherwise Groq when GROQ_API_KEY is set.
  ANTHROPIC_API_KEY  enables Claude.
  CLAUDE_FAST_MODEL  routing, JSON extraction, query rewrite     (default claude-haiku-5-5)
  CLAUDE_MODEL       user-visible answers, RAG, general chat      (default claude-sonnet-5-5)
  CLAUDE_AGENT_MODEL tool-calling agent loop                      (default = CLAUDE_MODEL)
  CLAUDE_DEEP_MODEL  hardest requests, opt-in via tier="deep"      (default claude-opus-5-5)
  KARNA_FALLBACK     on (default) | off: if Claude fails, retry the same call on Groq when a Groq key exists.
  ANTHROPIC_TIMEOUT  seconds (default 60)
  HUGGINGFACE_API_KEY optional: enables Hugging Face models in the chat model picker (see agent/model_catalog.py).

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
    """'anthropic', 'groq' or None (no key configured)."""
    pref = (_key("KARNA_PROVIDER") or "auto").lower()
    if pref in ("anthropic", "claude"):
        return "anthropic" if _key("ANTHROPIC_API_KEY") else None
    if pref == "groq":
        return "groq" if _key("GROQ_API_KEY") else None
    if _key("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _key("GROQ_API_KEY"):
        return "groq"
    return None


def enabled() -> bool:
    return provider() is not None


def status() -> Dict[str, Any]:
    """Safe to expose on /v1/health: no secrets."""
    p = provider()
    return {
        "provider": p,
        "anthropic_key_set": bool(_key("ANTHROPIC_API_KEY")),
        "groq_key_set": bool(_key("GROQ_API_KEY")),
        "huggingface_key_set": bool(_key("HUGGINGFACE_API_KEY")),
        "fallback": _fallback_allowed(),
        "models": {"fast": _model_for("fast"), "balanced": _model_for("balanced"),
                   "agent": _model_for("agent"), "deep": _model_for("deep")} if p == "anthropic" else None,
    }


def _fallback_allowed() -> bool:
    return os.getenv("KARNA_FALLBACK", "on").strip().lower() not in ("off", "0", "false", "no") and bool(_key("GROQ_API_KEY"))


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


def _create(**kw):
    p = provider()
    if p is None:
        raise RuntimeError("No LLM key configured. Set ANTHROPIC_API_KEY (recommended) or GROQ_API_KEY on the backend.")
    if p == "groq":
        return _groq_create(**kw)
    try:
        return _claude_create(**kw)
    except Exception as e:
        if _fallback_allowed() and type(e).__name__ not in ("BadRequestError",):
            log.warning("Claude call failed (%s: %s); falling back to Groq", type(e).__name__, str(e)[:200])
            _fell.set(True)
            return _groq_create(**kw)
        raise


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
        raise RuntimeError("No LLM key configured. Set ANTHROPIC_API_KEY (recommended) or GROQ_API_KEY on the backend.")
    return _client


# ----------------------------------------------------------------------------- streaming
def stream_chat(messages: List[Dict[str, Any]], *, tier: str = "balanced", max_tokens: int = 2000,
                temperature: Optional[float] = 0.3) -> Iterator[str]:
    """Yield text deltas. Claude streams natively; Groq/other providers yield the whole reply once."""
    if provider() != "anthropic":
        yield _create(messages=messages, max_tokens=max_tokens, temperature=temperature or 0.3,
                      model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")).choices[0].message.content or ""
        return
    args, _, model = _build_kwargs({"messages": messages, "tier": tier, "max_tokens": max_tokens, "temperature": temperature})
    with _anthropic_client().messages.stream(**args) as s:
        for delta in s.text_stream:
            yield delta


# ----------------------------------------------------------------------------- user-selected model (final answers only)
_fell: "contextvars.ContextVar[bool]" = contextvars.ContextVar("karna_fell_back", default=False)
_sel: "contextvars.ContextVar[Any]" = contextvars.ContextVar("karna_selected", default=None)    # (entry, who) | None
_meta: "contextvars.ContextVar[Optional[Dict[str, Any]]]" = contextvars.ContextVar("karna_meta", default=None)

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
    if entry is None:
        out = _create(messages=messages, model=default_model, max_tokens=max_tokens, temperature=temperature)
        p = provider()
        fb = _fell.get()
        _meta.set({"key": "auto", "label": "Auto", "provider": "groq" if (fb or p == "groq") else p,
                   "model": getattr(out, "model", "") or default_model, "fallback": bool(fb)})
        return out.choices[0].message.content or ""
    fb = False
    try:
        out = _call_entry(entry, messages, max_tokens, temperature)
    except Exception as e:
        log.warning("selected model %s failed (%s: %s); using default routing", entry.key, type(e).__name__, str(e)[:200])
        _fell.set(False)
        out = _create(messages=messages, model=default_model, max_tokens=max_tokens, temperature=temperature)
        fb = True
    prov = ("groq" if _fell.get() else provider()) if fb else entry.provider
    _meta.set({"key": entry.key, "label": entry.label, "provider": prov,
               "model": getattr(out, "model", "") or entry.model_id, "fallback": fb or _fell.get()})
    return out.choices[0].message.content or ""


def stream_meta(entry: Any = None) -> Dict[str, Any]:
    """Label for a reply produced by stream_chat (Claude tier, or Groq when Claude isn't the active provider)."""
    p = provider()
    if entry is not None and entry.provider == "anthropic" and p == "anthropic":
        return {"key": entry.key, "label": entry.label, "provider": "anthropic", "model": _model_for(entry.claude_tier), "fallback": False}
    if p == "anthropic":
        return {"key": "auto", "label": "Auto", "provider": "anthropic", "model": _model_for("balanced"), "fallback": False}
    return {"key": "auto" if entry is None else entry.key, "label": "Auto" if entry is None else entry.label, "provider": "groq",
            "model": os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), "fallback": entry is not None}
