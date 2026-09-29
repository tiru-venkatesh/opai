"""
Central policy for actions that must not execute without user approval.
"""
from __future__ import annotations

HIGH_IMPACT_INTENTS = {
    "draft_outreach",      # draft itself is safe; sending happens in Outbox
    "update_application",  # submission is never automatic
    "approve_action",
    "delete_record",
}

HIGH_IMPACT_TOOLS = {
    "send_email",
    "submit_application",
    "delete_record",
    "calendar_invite",
    "mark_outbox_sent",
}


def requires_approval(action: str, *, tool_name: str | None = None) -> bool:
    if tool_name and tool_name in HIGH_IMPACT_TOOLS:
        return True
    return action in HIGH_IMPACT_INTENTS


def approval_message(action: str) -> str:
    return (
        f"{action.replace('_', ' ').capitalize()} is ready, but OPA requires your "
        "approval before any external or destructive action."
    )
