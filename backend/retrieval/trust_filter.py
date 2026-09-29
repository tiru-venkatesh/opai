"""Trust policy for retrieved context."""
from __future__ import annotations

TRUSTED_FIRST_PARTY_SOURCES = {
    "resume", "project", "reflection", "academic", "application",
    "outreach", "cover_letter", "memory", "task", "opportunity",
}


def is_trusted(source_type: str) -> bool:
    return source_type in TRUSTED_FIRST_PARTY_SOURCES
