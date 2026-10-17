"""
KARNA model catalog: the only place that decides which models a user may pick for the final chat answer.

The browser sends a `model_key`; the server validates it here. Nothing the client sends is ever used as a model id.

Providers
  anthropic  Claude tiers (fast / balanced / deep), mapped to CLAUDE_*_MODEL by agent.llm
  groq       Groq-hosted open models
  hf         Hugging Face Inference Providers (OpenAI-compatible router). Optional: needs HUGGINGFACE_API_KEY.

Env
  KARNA_HF_MODELS       JSON list overriding the Hugging Face entries:
                        [{"key":"hf-llama","label":"Llama 3.3 70B","model_id":"meta-llama/Llama-3.3-70B-Instruct"}]
                        Provider availability changes: check each id on its Hugging Face page before enabling it.
  KARNA_HF_WORKSPACE    "on" lets Hugging Face models see Workspace data (documents, profile). Default off.
  KARNA_DAILY_CAPS      per user per day, e.g. "fast:300,balanced:150,deep:20,open:80"
  KARNA_GROQ_MODELS     JSON list overriding the Groq entries (same shape as KARNA_HF_MODELS)

Structured-output work (intent routing, memory extraction, JSON mode, tool calling) never uses this catalog.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


class ModelChoiceError(Exception):
    """Carries an HTTP status so routes can turn it into a clean 400 / 429."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class ModelEntry:
    key: str
    label: str
    provider: str          # anthropic | groq | hf
    tier: str              # cost tier used for daily caps: fast | balanced | deep | open
    model_id: str = ""     # provider model id; empty for Claude (agent.llm maps the tier)
    claude_tier: str = ""  # fast | balanced | deep for provider == anthropic
    workspace_ok: bool = True
    note: str = ""


def _claude_entries() -> List[ModelEntry]:
    return [
        ModelEntry("claude-fast", "Claude Fast", "anthropic", "fast", claude_tier="fast", note="Quickest, cheapest"),
        ModelEntry("claude-balanced", "Claude Balanced", "anthropic", "balanced", claude_tier="balanced", note="Default quality"),
        ModelEntry("claude-deep", "Claude Deep", "anthropic", "deep", claude_tier="deep", note="Hardest questions, slowest, capped"),
    ]


_DEFAULT_GROQ = [
    {"key": "groq-gpt-oss-20b", "label": "GPT-OSS 20B (Groq)", "model_id": "openai/gpt-oss-20b"},
    {"key": "groq-gpt-oss-120b", "label": "GPT-OSS 120B (Groq)", "model_id": "openai/gpt-oss-120b"},
]
# Unverified starting points. Replace via KARNA_HF_MODELS after checking availability on huggingface.co.
_DEFAULT_HF = [
    {"key": "hf-llama-3-3-70b", "label": "Llama 3.3 70B (Hugging Face)", "model_id": "meta-llama/Llama-3.3-70B-Instruct"},
    {"key": "hf-qwen-2-5-72b", "label": "Qwen 2.5 72B (Hugging Face)", "model_id": "Qwen/Qwen2.5-72B-Instruct"},
]


def _load_list(env: str, default: List[Dict[str, str]]) -> List[Dict[str, str]]:
    raw = os.getenv(env, "").strip()
    if not raw:
        return default
    try:
        data = json.loads(raw)
        ok = [d for d in data if isinstance(d, dict) and d.get("key") and d.get("model_id")]
        return ok
    except (ValueError, TypeError):
        return default


def _hf_workspace_ok() -> bool:
    return os.getenv("KARNA_HF_WORKSPACE", "off").strip().lower() in ("on", "1", "true", "yes")


def catalog() -> List[ModelEntry]:
    out = _claude_entries()
    for d in _load_list("KARNA_GROQ_MODELS", _DEFAULT_GROQ):
        out.append(ModelEntry(str(d["key"]), str(d.get("label") or d["model_id"]), "groq", "open", model_id=str(d["model_id"]), workspace_ok=True))
    for d in _load_list("KARNA_HF_MODELS", _DEFAULT_HF):
        out.append(ModelEntry(str(d["key"]), str(d.get("label") or d["model_id"]), "hf", "open", model_id=str(d["model_id"]),
                              workspace_ok=_hf_workspace_ok(), note="Third-party providers; General mode only by default"))
    return out


def _provider_ready(provider: str) -> bool:
    key = {"anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY", "hf": "HUGGINGFACE_API_KEY"}[provider]
    return bool(os.getenv(key, "").strip())


def get(key: str) -> Optional[ModelEntry]:
    return next((e for e in catalog() if e.key == key), None)


def resolve(model_key: Optional[str], mode: str) -> Optional[ModelEntry]:
    """None / '' / 'auto' -> None (use the existing default routing). Unknown or disallowed keys raise ModelChoiceError."""
    k = (model_key or "").strip()
    if not k or k == "auto":
        return None
    e = get(k)
    if e is None:
        raise ModelChoiceError(400, "Unknown model.")
    if not _provider_ready(e.provider):
        raise ModelChoiceError(400, f"{e.label} isn't enabled on this server.")
    if mode == "workspace" and not e.workspace_ok:
        raise ModelChoiceError(400, f"{e.label} can't be used in Workspace mode, because it would send your documents to a third-party provider. Use General mode or pick Claude/Groq.")
    return e


def public_list(mode: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = []
    for e in catalog():
        d = asdict(e)
        d.pop("claude_tier", None)
        d.pop("model_id", None)           # never expose provider ids needlessly
        d["ready"] = _provider_ready(e.provider)
        d["available"] = d["ready"] and (mode != "workspace" or e.workspace_ok)
        rows.append(d)
    return rows


# ----------------------------------------------------------------------------- per-user daily caps
_DEFAULT_CAPS = {"fast": 300, "balanced": 150, "deep": 20, "open": 80}
_USAGE: Dict[str, Dict[str, int]] = {}
_LOCK = threading.Lock()


def caps() -> Dict[str, int]:
    out = dict(_DEFAULT_CAPS)
    for part in os.getenv("KARNA_DAILY_CAPS", "").split(","):
        if ":" in part:
            t, n = part.split(":", 1)
            try:
                out[t.strip()] = int(n)
            except ValueError:
                pass
    return out


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def charge(entry: ModelEntry, who: str) -> None:
    """Count one use against the tier's daily cap. Raises ModelChoiceError(429) when exhausted."""
    cap = caps().get(entry.tier)
    ident = f"{_day()}|{who or 'anon'}"
    with _LOCK:
        for k in [k for k in _USAGE if not k.startswith(_day())]:
            _USAGE.pop(k, None)           # drop yesterday's counters
        row = _USAGE.setdefault(ident, {})
        used = row.get(entry.tier, 0)
        if cap is not None and used >= cap:
            raise ModelChoiceError(429, f"Daily limit for {entry.tier} models reached ({cap}). Try Auto or a lighter model, or come back tomorrow.")
        row[entry.tier] = used + 1


def remaining(who: str) -> Dict[str, int]:
    ident = f"{_day()}|{who or 'anon'}"
    with _LOCK:
        row = _USAGE.get(ident, {})
    return {t: max(0, c - row.get(t, 0)) for t, c in caps().items()}
