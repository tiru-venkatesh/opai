"""Tokenising and chunking. Pure Python, no dependencies."""
from __future__ import annotations

import re
from typing import List

_STOP = set(
    "a an the and or of to in on for with at by from is are was were be been it this that these those "
    "as i my me we our you your they their he she his her its into over under about can could should "
    "would will do does did have has had not no yes so if then than also just more most some any all "
    "what who whom whose when where which why how".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#\-]*")


def _stem(t: str) -> str:
    """Very light suffix stripping ('applications' ~ 'application'). Applied to queries and chunks alike."""
    if not t.isalpha() or len(t) < 5:
        return t
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)] + rep
    return t


def tokenize(text: str) -> List[str]:
    return [_stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def chunk_text(text: str, max_chars: int = 600, overlap: int = 100) -> List[str]:
    """Paragraph-first packing; over-long paragraphs are split on sentences with a small overlap."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[\-\u2022*]\s)", text) if p.strip()]
    units: List[str] = []
    for p in paras:
        if len(p) <= max_chars:
            units.append(p)
            continue
        cur = ""
        for s in re.split(r"(?<=[.!?])\s+", p):
            if len(s) > max_chars:  # no punctuation at all
                if cur:
                    units.append(cur)
                    cur = ""
                units.extend(s[i : i + max_chars] for i in range(0, len(s), max_chars - overlap))
            elif len(cur) + len(s) + 1 > max_chars:
                units.append(cur)
                cur = (cur[-overlap:] + " " + s).strip() if overlap else s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            units.append(cur)
    chunks: List[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + len(u) + 1 > max_chars:
            chunks.append(cur)
            cur = u
        else:
            cur = (cur + "\n" + u).strip()
    if cur:
        chunks.append(cur)
    return chunks
