"""Local, privacy-aware routing for KARNA's final answer provider."""
from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    reason: str


_lock = threading.Lock()
_health: Dict[str, Dict[str, Any]] = {}
_user_hits = defaultdict(deque)
_COMPLEX = re.compile(r"\b(prove|derive|multi[- ]step|analy[sz]e|research|compare|evaluate|architecture|study (?:plan|workflow)|learning plan|exam plan|syllabus|mathematical|proof|trade[- ]?offs?)\b", re.I)
_CODING = re.compile(r"\b(code|coding|debug|stack trace|exception|function|class|typescript|javascript|python|sql|api|bug)\b", re.I)
_DOCUMENT = re.compile(r"\b(?:uploaded|attached|this)\s+(?:pdf|document|file)|\b(?:pdf|docx?|spreadsheet|slides?)\b|context passages:", re.I)
_SENSITIVE = re.compile(r"\b(resume|cv|medical|diagnosis|address|phone number|email address|account number|social security|ssn|tax id|passport|salary|income|financial|bank|confidential|personal data|private data|uploaded (?:file|document|resume)|"
                        r"(?:my|mine|personal|private|confidential)\s+(?:name|college|branch|skills?|goal|profile|documents?|notes?|plan|schedule|deadlines?|exams?|applications?|projects?|resume|cv|account|address|phone|email|salary|income|budget|grades?|bank details)|"
                        r"i\s+(?:study|am studying|work|live|am from|am at)\s+(?:at\s+|in\s+)?[a-z0-9])\b", re.I)


def _enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _fallback_enabled() -> bool:
    value = os.getenv("KARNA_ENABLE_FALLBACK", os.getenv("KARNA_FALLBACK", "true"))
    return value.strip().lower() not in {"0", "false", "no", "off"}


def model_for(provider: str) -> str:
    return {
        "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
        "openrouter": os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
        "anthropic": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5").strip(),
    }[provider]


def _needs_vision(messages: List[Dict[str, Any]]) -> bool:
    for message in messages or []:
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") in {"image_url", "input_image"}
            for part in content
        ):
            return True
    return False


def _needs_document(messages: List[Dict[str, Any]]) -> bool:
    for message in messages or []:
        content = message.get("content")
        if isinstance(content, str) and _DOCUMENT.search(content[-6000:]):
            return True
        if isinstance(content, list) and any(
            isinstance(part, dict) and _DOCUMENT.search(str(part.get("text", "")))
            for part in content
        ):
            return True
    return False


def available(provider: str) -> bool:
    keys = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY"}
    if not os.getenv(keys[provider], "").strip():
        return False
    if provider == "anthropic" and not _enabled("KARNA_ENABLE_PAID_MODELS", "false"):
        return False
    paid = _enabled("KARNA_ENABLE_PAID_MODELS", "false")
    if provider == "gemini" and not paid and model_for(provider) not in {"gemini-3.8-flash", "gemini-3.5-flash-lite"}:
        return False
    if provider == "openrouter" and not paid and model_for(provider) != "openrouter/free" and not model_for(provider).endswith(":free"):
        return False
    return True


def _healthy(provider: str) -> bool:
    with _lock:
        row = _health.get(provider, {})
        return time.monotonic() >= row.get("open_until", 0)


def record(provider: str, ok: bool, latency_ms: float = 0) -> None:
    with _lock:
        row = _health.setdefault(provider, {"failures": 0, "open_until": 0, "successes": 0, "latency_ms": 0.0})
        if ok:
            row["failures"] = 0
            row["open_until"] = 0
            row["successes"] += 1
            row["latency_ms"] = latency_ms if not row["latency_ms"] else row["latency_ms"] * .8 + latency_ms * .2
        else:
            row["failures"] += 1
            if row["failures"] >= 3:
                row["open_until"] = time.monotonic() + min(120, 15 * (2 ** min(row["failures"] - 3, 3)))


def health() -> Dict[str, Dict[str, Any]]:
    now = time.monotonic()
    with _lock:
        known = {k: dict(v) for k, v in _health.items()}
    providers = ("groq", "gemini", "openrouter", "anthropic")
    out = {}
    for name in providers:
        row = known.get(name, {})
        configured = available(name)
        open_until = row.get("open_until", 0)
        out[name] = {"configured": configured, "healthy": configured and now >= open_until,
                     "cooldown_seconds": max(0, round(open_until - now)),
                     "failures": row.get("failures", 0), "successes": row.get("successes", 0),
                     "average_latency_ms": round(row.get("latency_ms", 0))}
    return out


def check_user_rate_limit(user_id: str) -> None:
    """Best-effort per-process RPM abuse guard; daily/monthly credit limits remain DB-backed in metering.py."""
    from fastapi import HTTPException
    now = time.monotonic()
    limit = max(1, int(os.getenv("KARNA_USER_RPM", "30")))
    key = str(user_id or "anonymous")
    with _lock:
        q = _user_hits[key]
        while q and now - q[0] >= 60:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "KARNA request rate limit reached. Wait a minute and try again.")
        q.append(now)


def classify(messages: List[Dict[str, Any]]) -> str:
    if _needs_vision(messages):
        return "multimodal"
    if _needs_document(messages):
        return "document"
    latest = ""
    for item in reversed(messages or []):
        if item.get("role") == "user":
            content = item.get("content")
            latest = content if isinstance(content, str) else " ".join(str(x.get("text", "")) for x in content or [] if isinstance(x, dict))
            break
    if _CODING.search(latest):
        return "coding"
    if _COMPLEX.search(latest) or len(latest) > 1800:
        return "complex"
    return "chat"


def _workspace_allowed(provider: str) -> bool:
    if provider == "groq":
        return True  # Groq API inference inputs are not retained by default; owner may enable ZDR in provider console.
    if provider == "gemini":
        return _enabled("KARNA_GEMINI_WORKSPACE_ALLOWED", "false") and _enabled("KARNA_ENABLE_PAID_MODELS", "false")
    if provider == "openrouter":
        # OpenRouter may route across downstream providers with different retention policies.
        # Keep private workspace content off this network until per-provider policy pinning exists.
        return False
    return (provider == "anthropic" and _enabled("KARNA_ENABLE_PAID_MODELS", "false")
            and _enabled("KARNA_ANTHROPIC_WORKSPACE_ALLOWED", "false"))


def is_private(messages: List[Dict[str, Any]], *, workspace: bool = False) -> bool:
    """Conservatively identify user-owned or multimodal data before selecting a vendor."""
    if workspace or _needs_vision(messages):
        return True
    text = " ".join(str(m.get("content", "")) for m in messages or [] if m.get("role") == "user")[-5000:]
    return bool(_SENSITIVE.search(text))


def estimated_tokens(messages: List[Dict[str, Any]], max_tokens: int = 0) -> int:
    chars = 0
    for message in messages or []:
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            chars += sum(len(str(part.get("text", ""))) for part in content if isinstance(part, dict))
    return (chars + 3) // 4 + max(0, int(max_tokens or 0))


def routes(messages: List[Dict[str, Any]], *, mode: str = "auto", workspace: bool = False,
           max_tokens: int = 0) -> List[Route]:
    """Choose a primary and privacy-compatible fallbacks using local signals only."""
    mode = (mode or "auto").lower()
    intent = classify(messages)
    multimodal = intent == "multimodal"
    private = is_private(messages, workspace=workspace)
    if intent in {"multimodal", "document"}:
        order = ["gemini", "groq", "openrouter", "anthropic"]
    elif mode == "fast":
        order = ["groq", "gemini", "openrouter", "anthropic"]
    elif mode in ("think", "expert"):
        order = ["gemini", "groq", "openrouter", "anthropic"]
    elif intent == "complex":
        order = ["gemini", "groq", "openrouter", "anthropic"]
    else:  # casual and coding requests use the fast Groq path by default
        order = ["groq", "gemini", "openrouter", "anthropic"]
    if mode == "expert":
        order = ["gemini", "groq", "openrouter", "anthropic"]
    if private:
        order = [p for p in order if _workspace_allowed(p)]
    if not _fallback_enabled():
        order = order[:1]
    result = []
    reason = f"{mode}:{intent}" + (":private" if private else "")
    privacy_candidates = [p for p in order if _workspace_allowed(p)] if private else list(order)
    quota_blocked = []
    from provider_quota import available as quota_available
    reserved_tokens = estimated_tokens(messages, max_tokens)
    for provider in order:
        capable = (not multimodal or provider in {"gemini", "anthropic"}
                   or (provider == "groq" and bool(os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()))
                   or (provider == "openrouter" and _enabled("KARNA_OPENROUTER_VISION_CAPABLE", "false")))
        if capable and available(provider) and _healthy(provider):
            if not quota_available(provider, reserved_tokens=reserved_tokens):
                quota_blocked.append(provider)
                continue
            model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip() if multimodal and provider == "groq" else model_for(provider)
            result.append(Route(provider, model, reason))
    if len(result) > 2:
        # Preserve intent's preferred provider; order remaining fallbacks using
        # observed latency, keeping unseen providers in their configured order.
        with _lock:
            latency = {name: row.get("latency_ms", 0.0) for name, row in _health.items()}
        primary, fallbacks = result[0], result[1:]
        fallbacks.sort(key=lambda route: (latency.get(route.provider, 0.0) <= 0,
                                         latency.get(route.provider, float("inf")) or float("inf")))
        result = [primary, *fallbacks]
    if not result and private:
        if quota_blocked and privacy_candidates:
            raise RuntimeError("All configured privacy-compatible AI providers are at their configured quota. Try again after a quota window resets.")
        if multimodal:
            raise RuntimeError("No configured provider can analyze this private image. Configure Groq vision, or enable Gemini workspace routing only with a paid Gemini API plan and an approved privacy policy.")
        raise RuntimeError("No configured AI provider is approved for private workspace data. Configure Groq, or explicitly enable a provider with a compatible privacy policy.")
    if not result and quota_blocked:
        raise RuntimeError("All configured AI providers are at their configured quota. Try again after a quota window resets.")
    if not result and multimodal:
        raise RuntimeError("No configured AI provider is available for image understanding. Configure Gemini, or enable a verified vision-capable model.")
    if not result:
        raise RuntimeError("No configured AI provider is available. Set GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY.")
    return result
