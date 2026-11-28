"""
LLM adapter used by the agent layer.

The module keeps its historical name so existing imports (`from agent import groq_client`) still work.
Calls go through `agent.llm`, which routes across the configured providers. `groq_enabled()` retains its old
name but means that at least one supported AI provider is configured.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import llm

_groq = None


def groq_enabled() -> bool:
    return llm.enabled()


def groq_raw_client():
    """The real Groq SDK client (only imported/constructed when Groq is actually used)."""
    global _groq
    if _groq is None:
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        from groq import Groq
        try:
            retries = min(2, max(0, int(os.getenv("KARNA_PROVIDER_MAX_RETRIES", "1"))))
        except ValueError:
            retries = 1
        _groq = Groq(api_key=key, timeout=float(os.getenv("GROQ_TIMEOUT", "45")), max_retries=retries)
    return _groq


def get_client():
    return llm.get_client()


def generate_json(system_prompt: str, user_prompt: str, *, model: Optional[str] = None, temperature: float = 0.0) -> Dict[str, Any]:
    completion = get_client().chat.completions.create(
        model=model or os.getenv("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b"),
        messages=[
            {"role": "system", "content": f"{system_prompt}\nReturn only valid JSON."},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    return json.loads(completion.choices[0].message.content or "{}")


def generate_text(system_prompt: str, user_prompt: str, *, model: Optional[str] = None, temperature: float = 0.2) -> str:
    completion = get_client().chat.completions.create(
        model=model or os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=temperature,
    )
    return completion.choices[0].message.content or ""


def chat_with_tools(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], *, model: Optional[str] = None, temperature: float = 0.2):
    return get_client().chat.completions.create(
        model=model or os.getenv("GROQ_AGENT_MODEL", "openai/gpt-oss-120b"),
        messages=messages, tools=tools, tool_choice="auto", temperature=temperature,
    )
