"""
Groq adapter used by the agent layer.

All Groq calls live here so routing/workflow code does not depend directly on
the provider SDK. The rest of OPA can therefore continue with deterministic
fallbacks when GROQ_API_KEY is missing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from groq import Groq


_client: Optional[Groq] = None


def groq_enabled() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        _client = Groq(api_key=api_key)
    return _client


def generate_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    completion = get_client().chat.completions.create(
        model=model or os.getenv("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b"),
        messages=[
            {"role": "system", "content": f"{system_prompt}\nReturn only valid JSON."},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    raw = completion.choices[0].message.content or "{}"
    return json.loads(raw)


def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> str:
    completion = get_client().chat.completions.create(
        model=model or os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return completion.choices[0].message.content or ""


def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
):
    return get_client().chat.completions.create(
        model=model or os.getenv("GROQ_AGENT_MODEL", "openai/gpt-oss-120b"),
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
    )
