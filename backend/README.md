# backend_patch: drop-in files (paths relative to backend/)

    agent/orchestrator.py            (replaces agent/orchestrator.py)
    agent/noise.py                   (was sitting at backend/noise.py; agent/orchestrator imports `from . import noise`)
    tests/test_noise_guard.py        (was at backend/test_noise_guard.py; it loads agent/noise.py)
    tests/test_orchestrator_hardening.py   (new, 5 tests)
    agent/conversation.py            (NEW: greetings / thanks / "what can you do" / help, English + Tenglish, no LLM)
    tests/test_conversation.py, tests/test_conversation_e2e.py   (NEW)
    main.py.diff                     (apply with `patch -p0 main.py < main.py.diff`: adds the same fast path to /v1/chat/general)
    orchestrator.diff                (diff vs the agent/orchestrator.py in your zip)

Then delete the stray backend/orchestrator.py, backend/noise.py, backend/test_noise_guard.py.

## What changed in agent/orchestrator.py
- Base is your newer top-level orchestrator.py (noise guard + plain-language clarify, no reason_code leak).
- `_try()`: every optional step (identity, reminder, brief, direct_db, capture) now logs the traceback
  and rolls the session back. Before, identity/direct_db/capture swallowed errors with no rollback and no log.
- `_grounded_chat`: general_answer failure is logged + rolled back instead of `pass`.
- Dates: "today/tomorrow" use Asia/Kolkata, not the server clock (UTC host was off by one day for IST evenings).
- `estimated_minutes` parsed to int (handles "30 min"), clamped 5..600.
- reschedule_session no longer replies "I generated the study plan".
- Removed unused imports/constants; one `import re` instead of three.

- Conversation fast path: "hi", "thanks", "bye", "what can you", "help", "nee features enti" are answered locally BEFORE
  any DB lookup or LLM call (greeting no longer waits on identity/reminder/brief/direct_db/capture). Uses the first name
  only if the profile has one. Edit ENABLED_CAPABILITIES in agent/conversation.py when features change.
- Unclear-message reply is now natural ("I'm not sure what you need yet. Could you say a little more?...").
- `_try()` logs per-step timing: grep your logs for `step=` and `handler=conversation`.

## Verified
Full suite before: 473 passed, 12 failed, 16 errors. After: 507 passed, same 28 failures, 0 new.
The 28 are pre-existing and unrelated: frontend/*.html/js files not in the zip, and test_opportunities_api KeyError.

## Deliberately NOT applied
- pending.py / pending_actions table: your backend already has confirm-first profile memory (agent/learn.py,
  MemoryItem unconfirmed -> active, history-based "yes") and an ActionRecord approval system (action_service.py).
  A second pending table would duplicate both.
