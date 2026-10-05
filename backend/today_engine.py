"""Today engine: turns real records into the 3 next best actions.

Deterministic and testable. Score (0-100) = 100 * (0.45*urgency + 0.30*importance + 0.15*effort_fit + 0.10*staleness).
Study blocks already carry a priority_score from the exam planner (exam urgency, weightage, difficulty,
confidence gap, revision need); it is used as their importance. Jev (intent routing) and Groq (wording)
sit around this engine; they never decide dates, capacity or scores."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database import (ActionRecord, Academic, Application, Exam, OutboxItem, Semester, StudyBlock, Task, Topic, Course)

DEFAULT_MINUTES = 180
BUDGET_RATIO = 0.8                     # keep 20% as catch-up buffer
LOW_ENERGY_CAP = 25                    # minutes per item when tired
DONE_APP = {"applied", "submitted", "rejected", "offer", "accepted", "withdrawn", "closed", "interview"}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def urgency(days: Optional[int]) -> float:
    if days is None:
        return 0.15
    if days < 0:
        return 1.0
    for limit, v in ((1, 1.0), (3, 0.85), (7, 0.6), (14, 0.35), (30, 0.15)):
        if days <= limit:
            return v
    return 0.05


def score(days: Optional[int], importance: float, minutes: int, avail: int, stale_days: int = 0) -> float:
    fit = 1.0 if minutes <= avail else _clamp(avail / max(minutes, 1))
    return round(100 * (0.45 * urgency(days) + 0.30 * _clamp(importance) + 0.15 * fit + 0.10 * _clamp(stale_days / 14)), 1)


def _days(d: Optional[date], today: date) -> Optional[int]:
    return (d - today).days if d else None


def _when(days: Optional[int]) -> str:
    if days is None:
        return "no deadline"
    if days < 0:
        return f"{-days}d overdue"
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def available_minutes(db: Session, uid: str, override: Optional[int]) -> int:
    if override:
        return max(10, min(int(override), 720))
    sem = db.query(Semester).filter(Semester.user_id == uid, Semester.is_current == True).first()  # noqa: E712
    return (sem.daily_study_minutes if sem and sem.daily_study_minutes else DEFAULT_MINUTES)


def _states(db: Session, uid: str, today: date) -> Dict[str, str]:
    """Latest Today state per item, from today's executed today_op actions."""
    start = __import__("datetime").datetime.combine(today, __import__("datetime").time.min)
    out: Dict[str, str] = {}
    rows = (db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.intent == "today_op",
                                          ActionRecord.status == "executed", ActionRecord.created_at >= start)
            .order_by(ActionRecord.created_at).all())
    for r in rows:
        p, res = r.payload_json or {}, r.result_json or {}
        out[f"{p.get('kind')}:{p.get('ref_id')}"] = res.get("state", "ai_suggested")
    return out


def candidates(db: Session, uid: str, today: date, avail: int, energy: str) -> List[Dict[str, Any]]:
    c: List[Dict[str, Any]] = []

    # --- study blocks (planned by the SEMS planner) ---
    blocks = db.query(StudyBlock).filter(StudyBlock.user_id == uid, StudyBlock.plan_date == today,
                                         StudyBlock.status.in_(["planned", "done"]), StudyBlock.mode != "buffer").all()
    for b in blocks:
        ex = db.query(Exam).filter(Exam.id == b.exam_id).first() if b.exam_id else None
        tp = db.query(Topic).filter(Topic.id == b.topic_id).first() if b.topic_id else None
        course = db.query(Course).filter(Course.id == ex.course_id).first() if ex else None
        d = _days(ex.exam_date, today) if ex else None
        cname = getattr(course, "name", None) or getattr(course, "course_name", None) or "Exam"
        title = f"Study {tp.name}" if tp else f"Study {cname}"
        imp = float(b.priority_score or 50) / 100
        c.append(dict(kind="study_block", ref_id=b.id, title=title, subtitle=f"{cname} · {b.mode.replace('_', ' ')}",
                      minutes=int(b.duration_min or 45), days=d, importance=imp, stale=0, done=b.status == "done",
                      effort=int(b.duration_min or 45), link="plan.html",
                      facts=dict(course=cname, mode=b.mode, exam_in=_when(d), confidence=getattr(tp, "confidence", None),
                                 weightage=getattr(tp, "exam_weightage", None), planner_reason=b.generated_reason)))

    # --- tasks ---
    for t in db.query(Task).filter(Task.user_id == uid, Task.status != "done").all():
        d = _days(t.due_date, today)
        if d is not None and d > 14:
            continue
        c.append(dict(kind="task", ref_id=t.id, title=t.title, subtitle=f"Task · {t.type or 'general'}", minutes=int(t.estimated_minutes or 45),
                      days=d, importance=0.5 if (t.type or "") != "general" else 0.4, stale=0, done=False, effort=int(t.estimated_minutes or 45),
                      link="app.html#/today", facts=dict(due=_when(d), type=t.type)))

    # --- applications: deadline or follow-up due, not already submitted ---
    for a in db.query(Application).filter(Application.user_id == uid).all():
        if (a.status or "").lower() in DONE_APP:
            continue
        d = _days(a.deadline, today)
        fu = _days(a.follow_up_date, today)
        if d is None and not (fu is not None and fu <= 0):
            continue
        if d is not None and d > 21:
            continue
        mins = int(a.effort_minutes or 60)
        c.append(dict(kind="application", ref_id=a.id, title=f"Prepare {a.role} at {a.company}", subtitle=f"Application · {a.status or 'To Apply'}",
                      minutes=mins, days=d if d is not None else fu, importance=0.8, stale=0, done=False, effort=mins, link="applications.html",
                      facts=dict(deadline=_when(d), status=a.status, effort=mins, link=a.link)))

    # --- drafts waiting in the Outbox (needs the user's sign-off; sending itself stays in the Outbox flow) ---
    for o in db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.status == "pending").all():
        pl = o.payload or {}
        c.append(dict(kind="outbox", ref_id=o.id, title=pl.get("subject") or "Review drafted message", subtitle=f"Draft to {pl.get('to') or 'recipient'} · waiting in Outbox",
                      minutes=5, days=1, importance=0.75, stale=0, done=False, effort=5, link="agent-console.html",
                      facts=dict(to=pl.get("to"), channel=o.channel)))

    # --- legacy academics (exam dates not yet in SEMS) ---
    sems_covered = bool(blocks)
    if not sems_covered:
        for ac in db.query(Academic).filter(Academic.user_id == uid, Academic.done == False).all():  # noqa: E712
            d = _days(ac.exam_date, today)
            if d is None or d > 21 or d < 0:
                continue
            pr = {"high": 0.9, "med": 0.6, "low": 0.35}.get((ac.priority or "med").lower(), 0.6)
            mins = int(ac.effort_minutes or 60)
            c.append(dict(kind="academic", ref_id=ac.id, title=ac.task or f"Study {ac.subject}", subtitle=f"{ac.subject} · exam", minutes=mins,
                          days=d, importance=pr, stale=0, done=False, effort=mins, link="academics.html",
                          facts=dict(exam_in=_when(d), priority=ac.priority, weak_areas=ac.weak_areas or [])))

    # --- DSA Roadmap: one small learning block per day (never a practice platform; links go to external sites) ---
    try:
        import dsa_service as DS
        c.extend(DS.today_candidates(db, uid, today))
    except Exception:                      # DSA must never break Today
        db.rollback()
    return c


def _category(x) -> str:
    k, f = x["kind"], x["facts"]
    return {"study_block": f"EXAM PREP · {str(f.get('course', '')).upper()}"[:42], "application": "APPLICATION", "task": "TASK",
            "outbox": "OUTREACH · OUTBOX", "academic": "ACADEMICS", "dsa": "DSA ROADMAP"}.get(k, k.upper())


def _check(x) -> str:
    k, f = x["kind"], x["facts"]
    if k == "study_block":
        bits = [f"Mode: {str(f.get('mode', '')).replace('_', ' ')}"]
        if f.get("confidence"):
            bits.append(f"confidence {f['confidence']}/5")
        if f.get("weightage"):
            bits.append(f"weightage {f['weightage']}%")
        return " · ".join(bits)
    if k == "application":
        return f"Status: {f.get('status') or 'To Apply'} · about {f.get('effort')} min of preparation"
    if k == "dsa":
        if f.get("mode") == "maintenance":
            return "Maintenance: review concepts or watch one topic explanation. No new heavy topic."
        return "Learn · practice one linked external question · write short notes"
    if k == "outbox":
        return "Awaiting your final sign-off before it is sent"
    if k == "task":
        return f"Estimated {x['minutes']} min · {f.get('due')}"
    return f"Exam {f.get('exam_in')}"


def explain(it: Dict[str, Any]) -> Dict[str, Any]:
    f, k, w = it["facts"], it["kind"], _when(it["days"])
    if k == "study_block":
        why = f"{f['course']} exam {f['exam_in']}" + (f"; confidence on this topic is {f['confidence']}/5" if f.get("confidence") else "") + (f"; worth about {f['weightage']}% of the paper" if f.get("weightage") else "") + "."
        late = "A missed session pushes this topic to a later day and shrinks your revision time before the exam."
        used = ["exam date", "topic weightage", "topic confidence", "difficulty", "days since last revision"]
    elif k == "application":
        why = f"Deadline {f['deadline']}; about {f['effort']} minutes of preparation are still needed."
        late = "Missing the deadline loses the opportunity, and rushed applications are weaker."
        used = ["application deadline", "status", "estimated effort"]
    elif k == "task":
        why = f"Due {f['due']}."
        late = "It rolls forward and competes with newer items tomorrow."
        used = ["due date", "estimated minutes", "task type"]
    elif k == "dsa":
        if f.get("mode") == "maintenance":
            why = f"{f.get('exam_name') or 'An'} exam is {_when(f.get('exam_in_days'))}, so DSA is in maintenance: review only, about {f.get('minutes')} minutes."
        else:
            why = f"Week {f.get('week')} of 12 target ({f.get('phase')}). Small daily sessions beat long irregular ones."
        late = "Nothing is lost: the roadmap slides, and tomorrow resumes with the same topic."
        used = ["roadmap phase", "your topic progress", "exam calendar", "days since your last DSA session"]
    elif k == "outbox":
        why = "A draft is ready but nothing is sent until you review and approve it."
        late = "Replies and follow-ups cannot start until it is sent."
        used = ["draft status", "approval policy"]
    else:
        why = f"Exam {f['exam_in']}; priority {f.get('priority') or 'med'}."
        late = "Less time left for revision before the exam."
        used = ["exam date", "priority", "weak areas"]
    return {"why_important": why, "if_delayed": late, "used": used,
            "change": ["Move to tomorrow", "Shorten it (set a time limit)", "Skip with a reason", "Say \"I have 30 minutes\" or \"I'm tired\" to replan"]}


def build(db: Session, user_id: str, today: Optional[date] = None, minutes: Optional[int] = None, energy: str = "normal") -> Dict[str, Any]:
    uid, today = str(user_id), today or date.today()
    energy = "low" if energy == "low" else "normal"
    avail = available_minutes(db, uid, minutes)
    states = _states(db, uid, today)
    cands = candidates(db, uid, today, avail, energy)

    done_minutes = sum(x["minutes"] for x in cands if x["done"])
    for x in cands:
        m = x["minutes"]
        if energy == "low":
            m = min(m, LOW_ENERGY_CAP)
        x["plan_minutes"] = m
        x["score"] = score(x["days"], x["importance"], m, avail, x["stale"])
        if energy == "low" and x["effort"] > 45:
            x["score"] = round(x["score"] * 0.85, 1)
    todo = sorted([x for x in cands if not x["done"] and states.get(f"{x['kind']}:{x['ref_id']}") not in ("completed", "paused")], key=lambda x: -x["score"])

    budget = max(0, int(avail * BUDGET_RATIO) - done_minutes)
    picked, used, later = [], 0, []
    for x in todo:
        m = x["plan_minutes"]
        if len(picked) < 3 and used + m <= budget:
            picked.append(x); used += m
        elif len(picked) < 3 and used == 0 and budget > 0:         # nothing fits whole: split the best one
            x["plan_minutes"] = budget; x["split"] = True; picked.append(x); used += budget
        else:
            later.append(x)
    items = []
    for x in picked:
        key = f"{x['kind']}:{x['ref_id']}"
        items.append({"category": _category(x), "check": _check(x), "priority_label": "HIGH PRIORITY" if x["score"] >= 65 else "MEDIUM PRIORITY" if x["score"] >= 40 else "LOWER PRIORITY",
                      "kind": x["kind"], "ref_id": x["ref_id"], "title": x["title"], "subtitle": x["subtitle"], "minutes": x["plan_minutes"],
                      "score": x["score"], "due": "daily block" if x["kind"] == "dsa" else _when(x["days"]), "reason": explain(x)["why_important"], "split": bool(x.get("split")),
                      "state": states.get(key, "ai_suggested"), "link": x["link"], "explain": explain(x)})
    nxt = next((i for i in items if i["state"] != "paused"), None)
    return {"date": today.isoformat(), "energy": energy, "items": items, "later_count": len(later),
            "later": [{"kind": x["kind"], "title": x["title"], "minutes": x["plan_minutes"], "due": _when(x["days"])} for x in later[:6]],
            "capacity": {"available_min": avail, "planned_min": used, "done_min": done_minutes, "buffer_min": max(0, avail - used - done_minutes)},
            "completed_today": [{"kind": x["kind"], "title": x["title"], "minutes": x["minutes"]} for x in cands if x["done"]],
            "needs_plan": not any(x["kind"] == "study_block" for x in cands) and db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed").count() > 0,
            "next_item": nxt["ref_id"] if nxt else None,
            "empty_hint": None if (items or cands) else "Nothing is due. Add an exam, a task or an application and OPAI will plan around it."}


def narrate(plan: Dict[str, Any]) -> str:
    """Friendly 2-3 sentence summary. Groq only rewords structured facts (never user free text); falls back to a template."""
    items = plan["items"]
    if not items:
        return plan.get("empty_hint") or "You are clear for today."
    first = items[0]
    base = f"Start with {first['title']} ({first['minutes']} min): {first['reason']}"
    cap = plan["capacity"]
    base += f" You have {cap['planned_min']} of {cap['available_min']} minutes planned, with {cap['buffer_min']} as buffer."
    try:
        import os
        if not os.getenv("GROQ_API_KEY"):
            return base
        from agent_service import call_groq_json
        import json
        facts = {"items": [{"title": i["title"], "minutes": i["minutes"], "due": i["due"], "reason": i["reason"]} for i in items], "capacity": cap, "energy": plan["energy"]}
        out = call_groq_json("Return JSON {\"summary\": string}. Write 2 short friendly sentences explaining today's plan from the JSON facts only. Do not add facts.",
                             json.dumps(facts))
        s = (json.loads(out).get("summary") or "").strip()
        return s[:400] or base
    except Exception:
        return base
