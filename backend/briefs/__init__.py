"""OPAI Brief System.

Chat is an input method. Briefs are the product output. Actions are the execution method.

  briefs.schema    - the universal brief contract (validated before anything is saved)
  briefs.core      - persistence, lifecycle, action execution/approval
  briefs.builders  - one deterministic builder per brief type (rules engine owns the facts)
  briefs.jarvis    - JARVIS as "brief navigator": message -> brief request -> short spoken summary

Groq never decides priorities, dates or actions. It may only reword the finished facts into `explanation.narrative`.
"""
BRIEF_TYPES = (
    "daily_plan", "exam_readiness", "dsa_roadmap", "application_opportunity", "outreach_research",
    "project", "weekly_review", "decision", "recovery", "approval", "reminder",
)
