"""Small deterministic context budgeter; never makes another provider call."""
from __future__ import annotations

import os
from typing import Any, Dict, List


def _chars(message: Dict[str, Any]) -> int:
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        # Base64 images are not useful for character-based token budgeting; preserve them,
        # but count only their text captions.
        return sum(len(str(part.get("text", ""))) for part in content if isinstance(part, dict))
    return len(str(content or ""))


def compact(messages: List[Dict[str, Any]], *, max_chars: int | None = None, recent_turns: int = 10) -> List[Dict[str, Any]]:
    """Keep all system instructions, the newest turns, and a short extract of older text turns."""
    try:
        configured_budget = int(os.getenv("KARNA_CONTEXT_MAX_CHARS", "48000"))
    except ValueError:
        configured_budget = 48000
    budget = max_chars or max(4000, configured_budget)
    copied = [dict(m) for m in (messages or []) if isinstance(m, dict)]
    if sum(_chars(m) for m in copied) <= budget:
        return copied
    fixed = [m for m in copied if m.get("role") in ("system", "developer")]
    turns = [m for m in copied if m.get("role") not in ("system", "developer")]
    selected = turns[-max(2, recent_turns):]
    remaining = max(0, budget - sum(_chars(m) for m in fixed))
    if sum(_chars(m) for m in selected) > remaining:
        # Keep newest first while budgeting, then restore chronological order.
        keep = []
        for message in reversed(selected):
            size = _chars(message)
            if keep and size > remaining:
                continue
            if size > remaining and isinstance(message.get("content"), str):
                message["content"] = message["content"][-remaining:] if remaining else ""
                size = _chars(message)
            keep.append(message)
            remaining = max(0, remaining - size)
        selected = list(reversed(keep))
    omitted = max(0, len(turns) - len(selected))
    if omitted:
        selected.insert(0, {"role": "system", "content": f"[Earlier conversation turns omitted for context length: {omitted}. Use recent turns as the active context.]"})
    return fixed + selected
