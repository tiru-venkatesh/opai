"""One deterministic builder per brief type.

Pipeline for every builder:  load structured data -> rules compute facts/capacity/deadlines -> rank -> create action
candidates -> (optional, later) language layer rewords. A builder never calls a language model and never mutates
user data except where documented (daily: the SEMS planner may lay down today's study blocks, exactly as /v1/today/refresh does).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import dsa_roadmap as R
import today_engine as T
from database import (Reminder, ActionRecord, Application, Contact, Course, DsaPlan, DsaSession, Exam, Milestone, Opportunity,
                      OutboxItem, Project, ResearchBrief, Semester, StudyBlock, Task, Topic)
from .core import BriefError, Ctx, clamp01, urgency_label


# ------------------------------------------------------------------ helpers
def _end_of_day(day: date) -> datetime:
    return T.local_day_start_utc(day + timedelta(days=1)) - timedelta(seconds=1)


def _in(days: int) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


def _hhmm(m: int) -> str:
    m = int(m) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _peak_start(db: Session, uid: str) -> int:
    sem = db.query(Semester).filter(Semester.user_id == uid, Semester.is_current == True).first()  # noqa: E712
    try:
        h, m = (sem.peak_start or "").split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 9 * 60


def _wrap(fn: Callable, *a, **k):
    try:
        return fn(*a, **k)
    except HTTPException as e:
        raise BriefError(e.status_code, e.detail)


def _code(prefix: str, d: Optional[int]) -> Optional[str]:
    if d is None:
        return None
    return f"{prefix}_overdue" if d < 0 else f"{prefix}_today" if d == 0 else f"{prefix}_tomorrow" if d == 1 else f"{prefix}_in_{d}_days"


def _src(title: str, typ: str = "workspace", url: Optional[str] = None, checked_on: Optional[str] = None) -> Dict[str, Any]:
    return {"title": title, "type": typ, "url": url, "checked_on": checked_on}


def _result(title: str, summary: str, confidence: float, *, scope: str, expires: Optional[datetime], context: Dict[str, Any],
            priorities: Optional[List[Dict[str, Any]]] = None, alerts: Optional[List[Dict[str, Any]]] = None,
            sources: Optional[List[Dict[str, Any]]] = None, short: str = "", codes: Optional[List[str]] = None,
            approval_items: Optional[List[Dict[str, Any]]] = None, **extra) -> Dict[str, Any]:
    return {"title": title, "summary": summary, "confidence": round(clamp01(confidence), 2), "context": context,
            "priorities": priorities or [], "alerts": alerts or [], "sources": sources or [], "approval_items": approval_items or [],
            "explanation": {"short": short or summary, "details_available": True, "reason_codes": codes or []},
            "_scope": scope, "_expires": expires, **extra}


# ================================================================== 1. DAILY OPERATING BRIEF
def _daily_codes(it: Dict[str, Any]) -> List[str]:
    k, d, f = it["kind"], it.get("days"), it.get("facts") or {}
    c: List[str] = []
    if k == "study_block":
        c.append(_code("exam", d))
        if (f.get("weightage") or 0) >= 20:
            c.append("high_weight_topic")
        if f.get("confidence") and f["confidence"] <= 2:
            c.append("confidence_low")
        if f.get("mode") in ("revise", "recall"):
            c.append("revision_due")
    elif k == "application":
        c.append(_code("deadline", d))
    elif k == "task":
        c.append(_code("task_due", d))
    elif k == "academic":
        c.append(_code("exam", d))
    elif k == "dsa":
        c.append("dsa_maintenance" if f.get("mode") == "maintenance" else "roadmap_daily_block")
        if f.get("exam_in_days") is not None:
            c.append(_code("exam", f["exam_in_days"]))
    elif k == "outbox":
        c.append("draft_awaiting_review")
    if it.get("split"):
        c.append("time_constrained")
    return [x for x in c if x]


def _item_actions(ctx: Ctx, it: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    k, rid = it["kind"], it["ref_id"]
    if k == "outbox":
        return [ctx.act("open_outbox", "Review draft", link="agent-console.html", entity_id=rid, primary=True)], "open_outbox"
    acts: List[Dict[str, Any]] = []
    if k == "application":
        acts.append(ctx.act("open_application", "Open application", link=it.get("link") or "applications.html", entity_id=rid, primary=True))
    else:
        acts.append(ctx.act("start_focus", f"Start {it['minutes']}-minute session", kind="execute", intent="today_op",
                            payload={"kind": k, "ref_id": rid, "op": "start"}, entity_id=rid, primary=True))
    acts.append(ctx.act("complete", "Mark preparation done" if k == "application" else "Mark done", kind="execute", intent="today_op",
                        payload={"kind": k, "ref_id": rid, "op": "complete"}, entity_id=rid))
    acts.append(ctx.act("reschedule", "Move to tomorrow", kind="execute", intent="today_op",
                        payload={"kind": k, "ref_id": rid, "op": "snooze", "days": 1}, entity_id=rid))
    return acts, acts[0]["type"]


def build_daily(ctx: Ctx) -> Dict[str, Any]:
    db, uid, p = ctx.db, ctx.uid, ctx.params
    day = date.fromisoformat(p["date"]) if p.get("date") else date.today()
    minutes, energy = p.get("capacity_override"), ("low" if p.get("energy") == "low" else "normal")
    plan = T.build(db, uid, today=day, minutes=minutes, energy=energy)
    replanned = False
    if day == date.today() and (minutes or plan["needs_plan"]):
        from agent_service import generate_study_plan          # same planner /v1/today/refresh uses; done blocks are never touched
        generate_study_plan(uid, db, day, available_minutes=T.available_minutes(db, uid, minutes))
        plan, replanned = T.build(db, uid, today=day, minutes=minutes, energy=energy), True
    cap, items = plan["capacity"], plan["items"]

    clock, priorities, shown_ids = _peak_start(db, uid), [], set()
    for i, it in enumerate(items, 1):
        acts, nxt = _item_actions(ctx, it)
        end = clock + int(it["minutes"])
        priorities.append({
            "rank": i, "entity_type": it["kind"], "entity_id": it["ref_id"], "title": it["title"], "subtitle": it["subtitle"],
            "category": it["category"], "duration_min": it["minutes"], "urgency": urgency_label(it["score"]), "score": it["score"],
            "due": it["due"], "state": it["state"], "reason_codes": _daily_codes(it), "reason_text": it["reason"],
            "if_delayed": it["explain"]["if_delayed"], "next_action": nxt, "window": {"start": _hhmm(clock), "end": _hhmm(end)},
            "actions": acts})
        shown_ids.add(it["ref_id"])
        clock = end + 10

    alerts: List[Dict[str, Any]] = []
    pend = [o for o in db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.status == "pending").all() if o.id not in shown_ids]
    for o in pend[:3]:
        soon = bool(o.expires_at and o.expires_at < datetime.utcnow() + timedelta(hours=24))
        alerts.append({"severity": "warning" if soon else "info", "title": "One outreach draft is waiting for review" if len(pend) == 1 else "An outreach draft is waiting for review",
                       "detail": (o.payload or {}).get("subject"), "entity_id": o.id, "action": "open_outbox", "link": "agent-console.html"})
    for l in plan["later"]:
        if l["due"] in ("today", "tomorrow") or "overdue" in l["due"]:
            alerts.append({"severity": "critical" if "overdue" in l["due"] else "warning", "title": f"{l['title']} does not fit today's capacity",
                           "detail": f"Due {l['due']} · {l['minutes']} min", "action": "adjust_capacity"})
    if plan["needs_plan"]:
        alerts.append({"severity": "warning", "title": "An exam has no study plan", "detail": "Add syllabus topics so OPAI can plan study blocks.",
                       "action": "open_plan", "link": "plan.html"})
    if energy == "low":
        alerts.append({"severity": "info", "title": "Low-energy mode", "detail": "Sessions are capped at 25 minutes."})

    if items:
        f = items[0]
        lead = (f"Your {f['facts'].get('course')} exam {f['facts'].get('exam_in')} is the highest-risk commitment."
                if f["kind"] == "study_block" else f"{f['title']} comes first: {f['reason']}")
        summary = f"You have {cap['available_min']} minutes available. {lead}"
    else:
        summary = plan.get("empty_hint") or "You are clear for today."
    conf = 0.9 if items else 0.6
    if plan["needs_plan"]:
        conf = 0.55
    srcs = [_src("Today engine (deterministic scoring)", "rules")]
    kinds = {i["kind"] for i in items}
    for kind, label in (("study_block", "SEMS exam map and study blocks"), ("task", "Tasks"), ("application", "Applications"),
                        ("dsa", "DSA roadmap"), ("outbox", "Outbox drafts")):
        if kind in kinds:
            srcs.append(_src(label))
    top_codes = priorities[0]["reason_codes"] if priorities else []
    return _result("Today's operating brief", summary, conf, scope=day.isoformat(), expires=_end_of_day(day),
                   context={"user_id": uid, "date": day.isoformat(), "capacity_min": cap["available_min"], "planned_min": cap["planned_min"],
                            "buffer_min": cap["buffer_min"], "energy": energy, "capacity_override": minutes, "replanned": replanned,
                            "later_count": plan["later_count"]},
                   priorities=priorities, alerts=alerts, sources=srcs, codes=top_codes,
                   short=(priorities[0]["reason_text"] if priorities else summary),
                   capacity=cap, completed_today=plan["completed_today"], later=plan["later"])


# ================================================================== 2. SEMS EXAM BRIEF
_WEIGHT = lambda w: "high" if (w or 0) >= 20 else "medium" if (w or 0) >= 10 else "low"
_SESSION = {1: ("learn", "Learn + active recall"), 2: ("practice", "Practice questions"), 3: ("revise", "Revise key points")}


def _course_name(db: Session, course_id: Optional[str]) -> str:
    c = db.query(Course).filter(Course.id == course_id).first() if course_id else None
    return getattr(c, "name", None) or "Exam"


def _pick_exam(db: Session, uid: str, exam_id: Optional[str]) -> Exam:
    from agent_service import compute_exam_risk
    today = date.today()
    if exam_id:
        e = db.query(Exam).filter(Exam.id == exam_id, Exam.user_id == uid).first()
        if not e:
            raise BriefError(404, "Exam not found")
        return e
    exams = [e for e in db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed").all() if e.exam_date is None or e.exam_date >= today]
    if not exams:
        raise BriefError(404, "No upcoming exams. Add an exam first.")
    def key(e):
        r = compute_exam_risk(e, db.query(Topic).filter(Topic.course_id == e.course_id).all(), today)
        return (r["risk_score"], -(r["days_until"] if r["days_until"] is not None else 999))
    return max(exams, key=key)


def build_exam(ctx: Ctx) -> Dict[str, Any]:
    from agent_service import compute_exam_risk, _topic_priority
    db, uid, today = ctx.db, ctx.uid, date.today()
    exam = _pick_exam(db, uid, ctx.params.get("exam_id"))
    cname = _course_name(db, exam.course_id)
    topics = db.query(Topic).filter(Topic.course_id == exam.course_id).all()
    risk = compute_exam_risk(exam, topics, today)
    d = risk["days_until"]
    pending = [t for t in topics if t.status != "done"]
    ranked = sorted(pending, key=lambda t: -_topic_priority(t, exam, today))[:3]
    blocks = {b.topic_id: b for b in db.query(StudyBlock).filter(StudyBlock.user_id == uid, StudyBlock.exam_id == exam.id, StudyBlock.plan_date == today,
                                                                 StudyBlock.status == "planned", StudyBlock.mode != "buffer").all()}
    today_min = sum(b.duration_min or 0 for b in db.query(StudyBlock).filter(StudyBlock.user_id == uid, StudyBlock.exam_id == exam.id,
                                                                            StudyBlock.plan_date == today, StudyBlock.mode != "buffer").all())
    remaining = round(sum(max(15, t.estimated_minutes or 60) * (1.0 - 0.1 * ((t.confidence or 1) - 1)) for t in pending))
    reviews_due = sum(1 for t in topics if t.next_review and t.next_review <= today and t.status != "done")

    ptopics, priorities = [], []
    for i, t in enumerate(ranked, 1):
        conf = t.confidence or 1
        mode, label = _SESSION.get(conf, ("recall", "Quick recall"))
        dur = min(60, max(20, t.estimated_minutes or 45))
        codes = [c for c in (_code("exam", d), "high_weight_topic" if _WEIGHT(t.exam_weightage) == "high" else None,
                             "confidence_low" if conf <= 2 else None, "not_started" if t.status == "not_started" else None) if c]
        blk = blocks.get(t.id)
        if blk:
            act = ctx.act("start_study_block", f"Start {t.name}", kind="execute", intent="today_op",
                          payload={"kind": "study_block", "ref_id": blk.id, "op": "start"}, entity_id=blk.id, primary=(i == 1))
        else:
            act = ctx.act("add_study_block", f"Schedule {t.name} today", kind="execute", intent="create_study_block",
                          payload={"exam_id": exam.id, "topic_id": t.id, "date": today.isoformat(), "duration_min": dur, "mode": mode},
                          entity_id=t.id, primary=(i == 1))
        ptopics.append({"topic": t.name, "topic_id": t.id, "confidence": conf, "weightage": _WEIGHT(t.exam_weightage),
                        "weightage_pct": t.exam_weightage, "next_session": label, "duration_min": dur, "status": t.status})
        priorities.append({"rank": i, "entity_type": "topic", "entity_id": t.id, "title": f"{cname} — {t.name}", "duration_min": dur,
                           "urgency": "high" if (d is not None and d <= 7 and conf <= 2) else "medium" if conf <= 3 else "low",
                           "reason_codes": codes, "reason_text": f"Confidence {conf}/5, about {t.exam_weightage}% of the paper" + (f", exam {('in ' + str(d) + ' days') if d and d > 1 else 'tomorrow' if d == 1 else 'today'}." if d is not None else "."),
                           "next_action": act["type"], "actions": [act]})
    ctx.act("generate_study_plan", "Plan today's study blocks", kind="execute", intent="replan_today", payload={})

    alerts: List[Dict[str, Any]] = []
    if d is not None and d <= 3 and risk["risk_level"] in ("high", "critical"):
        alerts.append({"severity": "critical", "title": f"Exam in {d} day(s) with preparation at {risk['preparation_pct']}%", "entity_id": exam.id})
    if not topics:
        alerts.append({"severity": "warning", "title": "No syllabus topics mapped for this course", "detail": "Add topics so OPAI can plan sessions.", "action": "open_plan", "link": "plan.html"})
    if exam.exam_date is None:
        alerts.append({"severity": "warning", "title": "Exam date is not set", "detail": "Risk and urgency cannot be computed without it."})
    if exam.status == "tentative":
        alerts.append({"severity": "info", "title": "Exam date is tentative", "detail": "Confirm it once the timetable is final."})
    when = "date not set" if d is None else "is today" if d == 0 else "is tomorrow" if d == 1 else f"is in {d} days"
    summary = f"Your {cname} exam {when}. Preparation is estimated at {risk['preparation_pct']}%; risk is {risk['risk_level']}."
    conf = 0.9 - (0.25 if len(topics) < 3 else 0) - (0.1 if exam.status == "tentative" else 0) - (0.2 if d is None else 0)
    return _result(f"{cname} exam brief", summary, conf, scope=exam.id, expires=_in(3),
                   context={"user_id": uid, "exam_id": exam.id, "course_id": exam.course_id, "topics_total": len(topics), "topics_pending": len(pending)},
                   priorities=priorities, alerts=alerts, sources=[_src(f"{cname} syllabus map and topic confidence"), _src("Exam risk model (estimate, not a predicted mark)", "rules")],
                   codes=[c for c in (_code("exam", d), f"risk_{risk['risk_level']}") if c], short=f"Preparation is an estimate from completion, confidence and revision, not a predicted mark.",
                   exam={"course": cname, "exam_id": exam.id, "exam_date": exam.exam_date.isoformat() if exam.exam_date else None, "days_remaining": d,
                         "risk_level": risk["risk_level"], "risk_score": risk["risk_score"], "preparation_estimate": risk["preparation_pct"],
                         "weak_topics": risk["weak_topics"]},
                   priority_topics=ptopics, plan={"today_min": today_min, "remaining_estimated_min": remaining, "review_sessions_due": reviews_due})


# ================================================================== 3. DSA ROADMAP BRIEF
def build_dsa(ctx: Ctx) -> Dict[str, Any]:
    import dsa_service as DS
    db, uid, today = ctx.db, ctx.uid, date.today()
    st = DS.state(db, uid, today)
    if not st.get("plan"):
        ctx.act("create_dsa_roadmap", "Create DSA roadmap", link="dsa.html", primary=True)
        return _result("DSA roadmap brief", "No DSA roadmap yet. Create one and OPAI will schedule one small learning block a day.", 0.95,
                       scope="dsa", expires=_in(1), context={"user_id": uid, "date": today.isoformat()}, sources=[_src("DSA roadmap")],
                       roadmap=None, today=None)
    plan, prog, mode, tb = st["plan"], st["progress"], st["mode"], st.get("today")
    topic_row = None
    if tb:
        for ph in st["phases"]:
            for t in ph["topics"]:
                if t["id"] == tb["topic"]["id"]:
                    topic_row = t
    resources: List[Dict[str, Any]] = []
    if tb:
        learn = (topic_row or {}).get("learn_url") or st["resources"]["learn"]
        resources.append({"title": f"Learn: {tb['topic']['name']}", "url": learn, "type": "learning"})
        if (topic_row or {}).get("practice_url") and tb["mode"] != "maintenance":
            resources.append({"title": "Practice one linked external question", "url": topic_row["practice_url"], "type": "external_practice"})
    priorities: List[Dict[str, Any]] = []
    if tb and tb["status"] in ("planned", "in_progress"):
        open_res = ctx.act("open_resource", "Open learning resource", link=resources[0]["url"], entity_id=tb["session_id"], primary=True)
        start = ctx.act("start_focus", f"Start {tb['minutes']}-minute block", kind="execute", intent="today_op",
                        payload={"kind": "dsa", "ref_id": tb["session_id"], "op": "start"}, entity_id=tb["session_id"])
        codes = ["dsa_maintenance" if tb["mode"] == "maintenance" else "roadmap_daily_block"] + ([_code("exam", mode["exam_in_days"])] if mode.get("exam_in_days") is not None else [])
        priorities.append({"rank": 1, "entity_type": "dsa", "entity_id": tb["session_id"], "title": f"DSA — {tb['topic']['name']}", "duration_min": tb["minutes"],
                           "urgency": "low", "reason_codes": [c for c in codes if c], "reason_text": mode["reason"] or "Small daily sessions beat long irregular ones.",
                           "next_action": "open_resource", "actions": [open_res, start]})
    maint = tb and tb["mode"] == "maintenance"
    if mode["override"] != "maintenance":
        ctx.act("pause_dsa", "Keep DSA in maintenance until exams end", kind="execute", risk="medium", intent="set_dsa_mode", payload={"mode": "maintenance"}, confirm=True)
    else:
        ctx.act("resume_dsa", "Return DSA to automatic mode", kind="execute", risk="medium", intent="set_dsa_mode", payload={"mode": "auto"}, confirm=True)
    alerts = []
    if st["pace"]["state"] == "behind":
        alerts.append({"severity": "warning", "title": "DSA pace is behind schedule", "detail": st["pace"]["message"]})
    if mode.get("exam_in_days") is not None and mode["mode"] == "maintenance":
        alerts.append({"severity": "info", "title": "DSA is in maintenance mode", "detail": mode["reason"]})
    phase = prog["current_phase"]
    summary = (f"You are in Week {prog['week']} of {prog['weeks']} ({phase}). " +
               ("DSA is in maintenance mode: review only, no heavy new topics." if maint else "Keep today's block small and steady."))
    return _result("DSA roadmap brief", summary, 0.9, scope="dsa", expires=_end_of_day(today),
                   context={"user_id": uid, "date": today.isoformat(), "week": prog["week"], "percent": prog["percent"]},
                   priorities=priorities, alerts=alerts, sources=[_src("DSA roadmap plan and topic progress"), _src("Exam calendar", "workspace")],
                   codes=priorities[0]["reason_codes"] if priorities else [], short=mode["reason"] or summary,
                   roadmap={"goal": plan["goal"], "language": plan["language"], "current_phase": phase, "current_topic": prog["current_topic"],
                            "status": "active", "mode": mode["mode"], "pace": st["pace"]["state"], "percent": prog["percent"]},
                   today={"duration_min": tb["minutes"] if tb else 0, "learning_target": tb["topic"]["name"] if tb else None,
                          "external_resources": resources, "blocks": tb["blocks"] if tb else []},
                   reason=mode["reason"] or "Consistency beats volume.")


# ================================================================== 4. APPLICATION BRIEF
def _strength(m: int) -> str:
    return "a strong" if m >= 70 else "a moderate" if m >= 40 else "a weak"


def build_application(ctx: Ctx) -> Dict[str, Any]:
    import extras_api as X
    db, uid, today = ctx.db, ctx.uid, date.today()
    eid = ctx.params["entity_id"]
    opp = db.query(Opportunity).filter(Opportunity.id == eid).first()
    app = None
    if opp:
        ev = _wrap(X.evaluate_opportunity, eid, uid, db)
        tracked = ev["duplicates"]["your_applications"]
        app = db.query(Application).filter(Application.id == tracked[0], Application.user_id == uid).first() if tracked else None
        info = {"company": opp.company_or_lab, "role": opp.title, "deadline": ev["deadline"], "match_score": ev["match_percent"],
                "source_url": opp.link, "days_left": ev["days_left"], "urgency": ev["urgency"], "tracked": bool(app)}
        reasons, gaps, match, eff = ev["why_it_matches"], ev["gaps"], ev["match_percent"], ev["effort_minutes"]
        unmet = [c["item"] for c in ev["eligibility_checklist"] if c["status"] == "unmet"]
        stale, low_conf, urgency, days_left = ev["source"]["stale"], ev["match_confidence"] == "low", ev["urgency"], ev["days_left"]
    else:
        app = db.query(Application).filter(Application.id == eid, Application.user_id == uid).first()
        if not app:
            raise BriefError(404, "Opportunity or application not found")
        days_left = (app.deadline - today).days if app.deadline else None
        urgency = ("none" if days_left is None else "overdue" if days_left < 0 else "critical" if days_left <= 3 else "soon" if days_left <= 7 else "ok")
        info = {"company": app.company, "role": app.role, "deadline": app.deadline.isoformat() if app.deadline else None, "match_score": None,
                "source_url": app.link, "days_left": days_left, "urgency": urgency, "tracked": True, "status": app.status}
        reasons, gaps, match, eff, unmet, stale, low_conf = [], [], None, app.effort_minutes or 60, [], False, True

    blockers = _wrap(X.application_blockers, app.id, uid, db)["blockers"] if app else []
    open_status = bool(app) and (app.status or "") in ("To Apply", "Draft", "Not started", "")
    if app and open_status and not app.tailored_at and not app.resume_bullets:
        nba = {"title": "Tailor your resume", "duration_min": 40}
    elif app and open_status:
        nba = {"title": "Review the tailored resume and submit it yourself", "duration_min": 15}
    elif app:
        nba = {"title": "Track the outcome and plan the follow-up", "duration_min": 10}
    else:
        nba = {"title": "Track the application, then tailor your resume", "duration_min": eff}

    if not app:
        a1 = ctx.act("create_application", "Track application", kind="execute", intent="create_application", payload={"opportunity_id": eid},
                     entity_id=eid, primary=True)
    else:
        a1 = ctx.act("open_application", "Open application", link="applications.html", entity_id=app.id, primary=not open_status)
        if open_status:
            a1 = ctx.act("draft_resume_changes", "Create resume suggestions", kind="execute", intent="tailor_resume",
                         payload={"application_id": app.id}, entity_id=app.id, primary=True)
    if info["source_url"]:
        ctx.act("open_source", "Open posting", link=info["source_url"], entity_id=eid)

    alerts: List[Dict[str, Any]] = []
    if urgency == "overdue":
        alerts.append({"severity": "critical", "title": "The deadline has passed", "entity_id": eid})
    elif urgency in ("critical", "soon"):
        alerts.append({"severity": "critical" if urgency == "critical" else "warning", "title": f"Deadline in {days_left} day(s)", "entity_id": eid})
    for b in blockers:
        if b["code"] not in ("deadline_close", "deadline_passed"):
            alerts.append({"severity": "warning", "title": b["text"], "entity_id": app.id if app else eid})
    if unmet:
        alerts.append({"severity": "critical", "title": "Eligibility not met: " + "; ".join(unmet)})
    if stale:
        alerts.append({"severity": "info", "title": "The posting was last verified over 14 days ago. Check it is still open."})
    if opp and ev["duplicates"]["opportunities"]:
        alerts.append({"severity": "info", "title": "A duplicate listing exists"})

    if urgency == "overdue":
        summary = f"The deadline for {info['role']} at {info['company']} has passed. Check whether the posting is still open before spending time on it."
    elif match is None:
        summary = f"{info['role']} at {info['company']} is tracked" + (f" and closes in {days_left} days." if days_left is not None and days_left >= 0 else ".")
    else:
        summary = f"This role is {_strength(match)} profile match ({match}%)" + (f" but closes in {days_left} days." if days_left is not None and 0 <= days_left <= 7 else ".")
    codes = [c for c in (_code("deadline", days_left), f"match_{match}" if match is not None else None, "match_confidence_low" if low_conf else None) if c]
    pri = {"rank": 1, "entity_type": "application" if app else "opportunity", "entity_id": app.id if app else eid, "title": nba["title"], "duration_min": nba["duration_min"],
           "urgency": "high" if urgency in ("critical", "overdue") else "medium" if urgency == "soon" else "low", "reason_codes": codes,
           "reason_text": summary, "next_action": a1["type"], "actions": [a1]}
    conf = (0.55 if low_conf else 0.85) - (0.1 if stale else 0)
    return _result(f"{info['role']} opportunity brief", summary, conf, scope=eid, expires=_in(2),
                   context={"user_id": uid, "opportunity_id": eid if opp else None, "application_id": app.id if app else None},
                   priorities=[pri], alerts=alerts, sources=[_src("Skills overlap (profile, resumes, projects)", "rules"),
                                                          _src(info["company"] + " posting", "web", info["source_url"], opp.last_verified_at.date().isoformat() if opp and opp.last_verified_at else None)],
                   codes=codes, short="Match is a deterministic skills overlap, not a prediction of the outcome.",
                   opportunity=info, match_reasons=reasons, gaps=gaps, next_best_action=nba)


# ================================================================== 5. OUTREACH RESEARCH BRIEF
def build_outreach(ctx: Ctx) -> Dict[str, Any]:
    import extras_api as X
    import outreach_guard as G
    db, uid = ctx.db, ctx.uid
    c = db.query(Contact).filter(Contact.id == ctx.params["entity_id"]).first()
    if not c:
        raise BriefError(404, "Contact not found")
    rb = (db.query(ResearchBrief).filter(ResearchBrief.user_id == uid, ResearchBrief.contact_id == c.id, ResearchBrief.created_at >= _in(-7))
          .order_by(ResearchBrief.created_at.desc()).first())
    content = (X._brief_out(rb) if rb else _wrap(X.research_brief, c.id, X.BriefBody(user_id=uid), db))
    verification = content["verification"]
    rb_id = content["id"]
    suppressed = G.is_suppressed(db, uid, c.email)
    blocked = None
    try:
        G.check_can_draft(db, uid, c)
    except G.Blocked as e:
        blocked = e.detail
    email_ok = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", c.email or ""))
    email_status = "suppressed" if suppressed else "invalid_format" if not email_ok else "source_verified" if verification == "verified" else "needs_verification"
    pending = db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.status == "pending").all()
    pending = [o for o in pending if (o.ref or {}).get("id") == c.id]

    alerts: List[Dict[str, Any]] = []
    if suppressed:
        alerts.append({"severity": "critical", "title": "This contact is on your do-not-contact list", "detail": suppressed.reason})
    elif blocked:
        alerts.append({"severity": "warning", "title": "Drafting is blocked by the outreach safety policy", "detail": blocked})
    for w in content.get("warnings") or []:
        alerts.append({"severity": "warning", "title": w})
    approval_items: List[Dict[str, Any]] = []
    draft = None
    if pending:
        o = pending[0]
        pl = o.payload or {}
        draft = {"outbox_id": o.id, "subject": pl.get("subject"), "status": "pending_review", "steps": ["Review", "Edit", "Approve", "Send"], "current_step": "Review"}
        approval_items.append({"approval_id": o.id, "source": "outbox", "title": f"Email to {pl.get('to')}", "risk": "high",
                               "preview": {"to": pl.get("to"), "subject": pl.get("subject"), "body": (pl.get("body") or "")[:400]},
                               "expires_at": o.expires_at.isoformat() if o.expires_at else None})
        ctx.act("open_outbox", "Review draft in Outbox", link="agent-console.html", entity_id=o.id, primary=True)
    else:
        ctx.act("verify_contact", "Verify email and source", risk="medium", link="agent-console.html#contacts", entity_id=c.id)
        if not suppressed and not blocked and verification != "unverified":
            ctx.act("draft_outreach", "Create email draft", kind="execute", intent="create_outreach_draft",
                    payload={"contact_id": c.id, "brief_id": rb_id}, entity_id=c.id, primary=True)
    areas = content.get("research_focus") or []
    matched = content.get("matched_areas") or []
    summary = (f"This contact is {'relevant' if content['relevance'] >= 40 else 'only weakly relevant'} to your work"
               + (f" on {matched[0]}" if matched else "") + ". "
               + ("A draft is waiting for your review." if pending else "Verify the email and source before drafting." if verification != "verified" else "The source is attached; you can draft now."))
    conf = {"verified": 0.9, "partial": 0.7}.get(verification, 0.45) - (0.1 if not matched else 0)
    codes = [f"verification_{verification}", f"relevance_{content['relevance']}"] + (["suppressed"] if suppressed else [])
    return _result("Professor outreach brief", summary, conf, scope=c.id, expires=_in(3),
                   context={"user_id": uid, "contact_id": c.id, "research_brief_id": rb_id}, alerts=alerts, approval_items=approval_items,
                   sources=content.get("sources") or [], codes=codes, short="Relevance is a deterministic overlap with your profile; no claim about their work is made without a source.",
                   contact={"id": c.id, "name": c.name, "institute": c.institute, "lab": c.lab, "email": c.email, "email_status": email_status, "status": c.status},
                   research_match={"score": content["relevance"], "research_area": (matched[0] if matched else (areas[0] if areas else None)),
                                   "why_relevant": content.get("why_you_fit") or []},
                   recommended_ask=content.get("suggested_ask"), draft=draft)


# ================================================================== 6. PROJECT BRIEF
def build_project(ctx: Ctx) -> Dict[str, Any]:
    import extras_api as X
    db, uid, today = ctx.db, ctx.uid, date.today()
    d = _wrap(X.project_dashboard, ctx.params["entity_id"], uid, db)
    ms = next((m for m in d["milestones"] if m["status"] != "done"), None)
    nt, prog = d["next_task"], d["progress"]
    priorities: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    if d["blocker"]:
        a = ctx.act("open_project", "Open project to resolve blocker", link="projects.html", entity_id=d["id"], primary=True)
        priorities.append({"rank": len(priorities) + 1, "entity_type": "blocker", "entity_id": d["id"], "title": f"Unblock: {d['blocker'][:150]}", "duration_min": 30,
                           "urgency": "high", "reason_codes": ["blocker_present"], "reason_text": "A blocker stops every other task from moving.", "next_action": a["type"], "actions": [a]})
        alerts.append({"severity": "warning", "title": "Project is blocked", "detail": d["blocker"][:200], "entity_id": d["id"]})
    if nt:
        a = ctx.act("start_focus", f"Start {nt['estimated_minutes'] or 45}-minute session", kind="execute", intent="today_op",
                    payload={"kind": "task", "ref_id": nt["id"], "op": "start"}, entity_id=nt["id"], primary=not d["blocker"])
        priorities.append({"rank": len(priorities) + 1, "entity_type": "task", "entity_id": nt["id"], "title": nt["title"], "duration_min": nt["estimated_minutes"] or 45,
                           "urgency": "medium", "reason_codes": ["next_task_in_order"], "reason_text": "Earliest-due open task for this project.", "next_action": a["type"], "actions": [a]})
    elif ms:
        a = ctx.act("break_down_milestone", "Break the milestone into tasks", link="projects.html", entity_id=ms["id"], primary=not d["blocker"])
        priorities.append({"rank": len(priorities) + 1, "entity_type": "milestone", "entity_id": ms["id"], "title": f"Plan tasks for: {ms['title']}", "duration_min": 20,
                           "urgency": "medium", "reason_codes": ["milestone_has_no_tasks"], "reason_text": "A milestone without tasks cannot make progress.", "next_action": a["type"], "actions": [a]})
    if ms and ms["due_date"]:
        left = (date.fromisoformat(ms["due_date"]) - today).days
        if left < 0:
            alerts.append({"severity": "critical", "title": f"Milestone '{ms['title']}' is {-left} day(s) overdue", "entity_id": ms["id"]})
        elif left <= 7 and ms["tasks_total"] and ms["tasks_done"] < ms["tasks_total"]:
            alerts.append({"severity": "warning", "title": f"Milestone '{ms['title']}' is due in {left} day(s) with {ms['tasks_total'] - ms['tasks_done']} task(s) open", "entity_id": ms["id"]})
    summary = (f"{d['title']}: {prog['done']} of {prog['total']} tasks done. " + (f"Next milestone: {ms['title']}. " if ms else "") +
               ("It is currently blocked." if d["blocker"] else (f"Next task: {nt['title']}." if nt else "No open tasks.")))
    return _result(f"{d['title']} project brief", summary.strip(), 0.85 if prog["total"] else 0.6, scope=d["id"], expires=_in(3),
                   context={"user_id": uid, "project_id": d["id"]}, priorities=priorities, alerts=alerts,
                   sources=[_src("Project milestones and tasks")], codes=priorities[0]["reason_codes"] if priorities else [],
                   project={"id": d["id"], "title": d["title"], "status": d["status"], "progress": prog, "deadline": d["deadline"]},
                   milestone=ms, blocker=d["blocker"], next_task=nt)


# ================================================================== 7. WEEKLY REVIEW BRIEF
def build_weekly(ctx: Ctx) -> Dict[str, Any]:
    db, uid, today = ctx.db, ctx.uid, date.today()
    start = today - timedelta(days=6)
    blocks = db.query(StudyBlock).filter(StudyBlock.user_id == uid, StudyBlock.plan_date >= start, StudyBlock.plan_date <= today, StudyBlock.mode != "buffer").all()
    done = [b for b in blocks if b.status == "done"]
    missed = [b for b in blocks if b.status == "missed" or (b.status == "planned" and b.plan_date < today)]
    today_planned = [b for b in blocks if b.status == "planned" and b.plan_date == today]
    total = len(done) + len(missed) + len(today_planned)
    rate = round(len(done) / total, 2) if total else None
    mins_done = sum((b.actual_duration_min or b.duration_min or 0) for b in done)
    ops = (db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.intent == "today_op", ActionRecord.status == "executed",
                                         ActionRecord.created_at >= T.local_day_start_utc(start)).all())
    completed_ops = sum(1 for o in ops if (o.result_json or {}).get("state") == "completed")
    moved_ops = sum(1 for o in ops if (o.result_json or {}).get("state") == "paused")
    dsa = db.query(DsaSession).filter(DsaSession.user_id == uid, DsaSession.plan_date >= start, DsaSession.plan_date <= today).all()
    dsa_done, dsa_skipped = sum(1 for s in dsa if s.status == "done"), sum(1 for s in dsa if s.status == "skipped")
    horizon = today + timedelta(days=7)
    exams = [e for e in db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed").all() if e.exam_date and today < e.exam_date <= horizon]
    apps = [a for a in db.query(Application).filter(Application.user_id == uid).all()
            if a.deadline and today <= a.deadline <= horizon and (a.status or "").lower() not in T.DONE_APP]
    tasks = [t for t in db.query(Task).filter(Task.user_id == uid, Task.status != "done").all() if t.due_date and today <= t.due_date <= horizon]
    cap = T.available_minutes(db, uid, None)
    has_sem = db.query(Semester).filter(Semester.user_id == uid, Semester.is_current == True).first() is not None  # noqa: E712

    priorities: List[Dict[str, Any]] = []
    def add(title, text, codes, urgency, acts):
        priorities.append({"rank": len(priorities) + 1, "entity_type": "adjustment", "entity_id": codes[0], "title": title, "duration_min": None, "urgency": urgency,
                           "reason_codes": codes, "reason_text": text, "next_action": acts[0]["type"] if acts else None, "actions": acts})
    if rate is not None and total >= 3 and rate < 0.5 and has_sem:
        new = max(60, int(round(cap * 0.75 / 15)) * 15)
        a = ctx.act("adjust_capacity", f"Lower daily study time to {new} min", kind="execute", risk="medium", intent="set_daily_capacity", payload={"minutes": new}, confirm=True, primary=True)
        add("Plan a lighter load", f"You finished {len(done)} of {total} planned blocks. A smaller daily target is easier to keep.", ["completion_below_50"], "high", [a])
    if len(missed) >= 2:
        a = ctx.act("open_recovery", "See what to recover", link="briefs.html?type=recovery")
        add("Recover missed work", f"{len(missed)} study blocks were missed.", ["missed_blocks"], "medium", [a])
    if exams:
        acts = []
        if db.query(DsaPlan).filter(DsaPlan.user_id == uid, DsaPlan.status == "active", DsaPlan.mode_override != "maintenance").first():
            acts.append(ctx.act("pause_dsa", "Keep DSA in maintenance", kind="execute", risk="medium", intent="set_dsa_mode", payload={"mode": "maintenance"}, confirm=True))
        add("Exam week ahead", f"{len(exams)} exam(s) in the next 7 days. Protect study time.", ["exam_within_7_days"], "high", acts)
    if apps:
        a = ctx.act("open_applications", "Open applications", link="applications.html")
        add("Application deadlines next week", f"{len(apps)} application deadline(s) in the next 7 days.", ["application_deadlines_7d"], "medium", [a])
    if rate is not None and total >= 4 and rate >= 0.85:
        add("Keep the same load", f"You completed {round(rate * 100)}% of planned study. The current load is sustainable.", ["on_track"], "low", [])
    if rate is None and not completed_ops:
        add("Not enough data yet", "Complete a few sessions this week so OPAI can tune your plan.", ["insufficient_data"], "low", [])

    alerts = []
    if len(missed) >= 3:
        alerts.append({"severity": "warning", "title": f"{len(missed)} study blocks were missed this week"})
    summary = (f"You completed {len(done)} of {total} planned study blocks ({round(rate * 100)}%) and {mins_done} study minutes this week."
               if rate is not None else "There is not enough tracked study activity this week to review.")
    conf = 0.9 if total >= 5 else 0.7 if total >= 2 else 0.5
    return _result("Weekly review", summary, conf, scope=start.isoformat(), expires=_in(7),
                   context={"user_id": uid, "window_start": start.isoformat(), "window_end": today.isoformat(), "capacity_min": cap},
                   priorities=priorities, alerts=alerts, sources=[_src("Study blocks"), _src("Today actions"), _src("DSA sessions")],
                   codes=priorities[0]["reason_codes"] if priorities else [], short=summary,
                   review={"study": {"planned": total, "done": len(done), "missed": len(missed), "minutes_done": mins_done, "completion_rate": rate},
                           "today_actions": {"completed": completed_ops, "moved": moved_ops}, "dsa": {"sessions": len(dsa), "done": dsa_done, "skipped": dsa_skipped}},
                   next_week={"exams": [{"id": e.id, "course": _course_name(db, e.course_id), "date": e.exam_date.isoformat()} for e in exams],
                              "application_deadlines": [{"id": a.id, "title": f"{a.role} at {a.company}", "date": a.deadline.isoformat()} for a in apps],
                              "tasks_due": len(tasks)})


# ================================================================== 8. DECISION BRIEF
def _subject(q: str) -> str:
    s = re.sub(r"^\s*(should i|shall i|can i|do i need to|is it worth(?: it)? (?:to|for me to)|would it be better (?:to|for me to))\s+", "", q.strip(), flags=re.I)
    s = s.strip(" ?.!")
    return (s[:1].upper() + s[1:])[:200] or q[:200]


def _deadline_days(q: str) -> Optional[int]:
    t = q.lower()
    if re.search(r"\b(today|tonight)\b", t):
        return 0
    if re.search(r"\b(tomorrow|tmrw)\b", t):
        return 1
    m = re.search(r"\b(?:in|within)\s+(\d{1,2})\s+days?\b", t)
    return int(m.group(1)) if m else None


def build_decision(ctx: Ctx) -> Dict[str, Any]:
    db, uid, p = ctx.db, ctx.uid, ctx.params
    q = (p.get("question") or "").strip()
    if len(q) < 4:
        raise BriefError(422, "Ask the question you are deciding, e.g. 'Should I take on the freelance request?'")
    est_given = p.get("estimated_minutes") is not None
    est = max(5, min(int(p.get("estimated_minutes") or 45), 480))
    dl = p["deadline_days"] if p.get("deadline_days") is not None else _deadline_days(q)
    plan = T.build(db, uid)
    cap = plan["capacity"]
    buffer_min, fits = cap["buffer_min"], est <= cap["buffer_min"]
    lowest = plan["items"][-1] if plan["items"] else None
    urgent = dl is not None and dl <= 1
    subj = _subject(q)
    today, tomorrow = date.today(), date.today() + timedelta(days=1)

    sa = 45 + (35 if urgent else 0) + (15 if fits else -25) - (10 if est > 90 else 0)
    sb = 50 + (15 if (dl is None or dl >= 2) else -40) + (10 if not fits else 0)
    sc = 20 + (25 if (dl is None and est >= 90 and not fits) else 0) - (30 if urgent else 0)
    opts = [
        ("A", "Do it today", sa, ["fits_in_buffer" if fits else "exceeds_buffer"] + (["deadline_within_1_day"] if urgent else []),
         f"Uses {est} of your {buffer_min} spare minutes." if fits else f"Needs {est} min but only {buffer_min} are spare" + (f"; it would displace '{lowest['title']}'." if lowest else "."),
         ("add_today", "Add to today", today)),
        ("B", "Schedule it for tomorrow", sb, ["protects_today_plan"] + (["no_deadline"] if dl is None else []),
         "Keeps today's plan intact." + (" Safe because there is no deadline before tomorrow." if not urgent else " Risky: the deadline is within a day."),
         ("schedule_tomorrow", "Schedule for tomorrow", tomorrow)),
        ("C", "Skip it for now", sc, ["low_value_or_long"] if sc > 20 else ["deadline_risk"] if urgent else ["keeps_options_open"],
         "Frees time, but nothing is tracked and it may come back later." + (" Not advised with a deadline this close." if urgent else ""), None),
    ]
    opts.sort(key=lambda o: -o[2])
    priorities = []
    for i, (oid, title, score, codes, why, act) in enumerate(opts, 1):
        acts = []
        if act:
            acts.append(ctx.act(act[0], act[1], kind="execute", intent="create_task",
                                payload={"title": subj, "due_date": act[2].isoformat(), "estimated_minutes": est, "type": "general"}, entity_id=oid, primary=(i == 1)))
        priorities.append({"rank": i, "entity_type": "option", "entity_id": oid, "title": title, "duration_min": est if act else 0,
                           "urgency": "high" if (i == 1 and urgent) else "medium" if i == 1 else "low", "reason_codes": codes, "reason_text": why,
                           "next_action": acts[0]["type"] if acts else None, "score": score, "actions": acts})
    best = priorities[0]
    assumptions = ([] if est_given else [f"Assumed it takes about {est} minutes."]) + ([] if dl is not None else ["No deadline given, so urgency was not considered."])
    conf = 0.5 + (0.1 if est_given else 0) + (0.15 if dl is not None else 0)
    return _result("Decision brief", f"Recommended: {best['title']}. {best['reason_text']}", conf, scope=re.sub(r"\W+", "-", q.lower())[:80], expires=_in(1),
                   context={"user_id": uid, "question": q, "subject": subj, "estimated_minutes": est, "estimate_assumed": not est_given, "deadline_days": dl,
                            "spare_min_today": buffer_min},
                   priorities=priorities, sources=[_src("Today capacity and priorities", "rules")], codes=best["reason_codes"],
                   short="Options are scored from your spare time today and any deadline; this is a recommendation, not a command.",
                   options=[{"id": o[0], "title": o[1], "score": o[2], "trade_off": o[4]} for o in opts], assumptions=assumptions)


# ================================================================== 9. RECOVERY BRIEF
def build_recovery(ctx: Ctx) -> Dict[str, Any]:
    db, uid, today = ctx.db, ctx.uid, date.today()
    since = today - timedelta(days=7)
    blocks = db.query(StudyBlock).filter(StudyBlock.user_id == uid, StudyBlock.plan_date >= since, StudyBlock.plan_date < today, StudyBlock.mode != "buffer").all()
    missed = [b for b in blocks if b.status == "missed" or b.status == "planned"]
    skipped = db.query(DsaSession).filter(DsaSession.user_id == uid, DsaSession.plan_date >= since, DsaSession.plan_date < today, DsaSession.status == "skipped").count()
    overdue = [t for t in db.query(Task).filter(Task.user_id == uid, Task.status != "done").all() if t.due_date and t.due_date < today]
    overdue.sort(key=lambda t: t.due_date)
    moved = [o for o in db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.intent == "today_op", ActionRecord.status == "executed",
                                                      ActionRecord.created_at >= T.local_day_start_utc(today - timedelta(days=3))).all()
             if (o.result_json or {}).get("state") == "paused"]
    plan = T.build(db, uid)

    names = []
    for b in missed[:8]:
        tp = db.query(Topic).filter(Topic.id == b.topic_id).first() if b.topic_id else None
        names.append({"block_id": b.id, "title": tp.name if tp else "Study block", "planned_for": b.plan_date.isoformat(), "minutes": b.duration_min})
    priorities: List[Dict[str, Any]] = []
    if missed:
        a = ctx.act("replan_today", "Re-plan today around missed work", kind="execute", intent="replan_today", payload={}, primary=True)
        priorities.append({"rank": 1, "entity_type": "recovery", "entity_id": "replan", "title": "Re-plan today around missed work", "duration_min": None, "urgency": "high",
                           "reason_codes": ["missed_blocks"], "reason_text": f"{len(missed)} study block(s) were not completed. The planner will re-rank those topics by exam urgency.",
                           "next_action": a["type"], "actions": [a]})
    for t in overdue[:3]:
        a = ctx.act("reschedule", f"Move '{t.title[:40]}' to tomorrow", kind="execute", intent="today_op",
                    payload={"kind": "task", "ref_id": t.id, "op": "snooze", "days": 1}, entity_id=t.id, primary=not priorities)
        priorities.append({"rank": len(priorities) + 1, "entity_type": "task", "entity_id": t.id, "title": t.title, "duration_min": t.estimated_minutes, "urgency": "medium",
                           "reason_codes": [f"task_overdue_{(today - t.due_date).days}_days"], "reason_text": f"Overdue since {t.due_date.isoformat()}.", "next_action": a["type"], "actions": [a]})
    dropped = plan["later"]
    alerts = [{"severity": "info", "title": f"{plan['later_count']} item(s) will not fit today", "detail": ", ".join(l["title"] for l in dropped[:3])}] if plan["later_count"] else []
    if not (missed or overdue or skipped):
        summary = "Nothing to recover. You are on track."
    else:
        summary = (f"{len(missed)} study block(s) missed, {len(overdue)} overdue task(s)" + (f", {skipped} DSA session(s) skipped" if skipped else "") +
                   ". Re-planning today puts the highest-risk work back first.")
    return _result("Recovery brief", summary, 0.95 if not (missed or overdue) else 0.85, scope=today.isoformat(), expires=_end_of_day(today),
                   context={"user_id": uid, "window_start": since.isoformat(), "capacity_min": plan["capacity"]["available_min"]},
                   priorities=priorities, alerts=alerts, sources=[_src("Study blocks"), _src("Tasks"), _src("Today actions")],
                   codes=["missed_blocks"] if missed else [], short=summary,
                   changes={"missed_blocks": names, "dsa_skipped": skipped, "overdue_tasks": [{"id": t.id, "title": t.title, "days_overdue": (today - t.due_date).days} for t in overdue[:10]],
                            "moved_recently": len(moved)},
                   recovery_plan={"fits_today": [{"title": i["title"], "minutes": i["minutes"]} for i in plan["items"]], "dropped_or_deferred": dropped})


# ================================================================== 10. APPROVAL BRIEF
def _describe(db: Session, uid: str, r: ActionRecord) -> Tuple[str, Dict[str, Any]]:
    p = r.payload_json or {}
    if r.intent == "send_email":
        return f"Send email to {p.get('to')}", {"to": p.get("to"), "subject": p.get("subject"), "body": (p.get("body") or "")[:400],
                                                "effect": "Creates a pending Outbox item. Nothing is sent until you approve it there."}
    if r.intent == "update_application_status":
        a = db.query(Application).filter(Application.id == p.get("application_id"), Application.user_id == uid).first()
        label = f"{a.role} at {a.company}" if a else "an application"
        return f"Mark {label} as '{p.get('status')}'", {"application": label, "from": a.status if a else None, "to": p.get("status"), "effect": "Changes the tracked status only; nothing is submitted for you."}
    if r.intent == "delete_task":
        t = db.query(Task).filter(Task.id == p.get("task_id"), Task.user_id == uid).first()
        return f"Delete task '{t.title if t else p.get('task_id')}'", {"task": t.title if t else None, "effect": "Permanently deletes the task."}
    return r.intent.replace("_", " ").capitalize(), {"payload": p}


def build_approval(ctx: Ctx) -> Dict[str, Any]:
    import action_service as A
    db, uid = ctx.db, ctx.uid
    only = ctx.params.get("action_id")
    q = db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.status == "pending_approval")
    if only:
        q = q.filter(ActionRecord.id == only)
    records = q.order_by(ActionRecord.created_at).all()
    if only and not records:
        raise BriefError(404, "No pending action with that id")
    items: List[Dict[str, Any]] = []
    priorities: List[Dict[str, Any]] = []
    for r in records:
        title, preview = _describe(db, uid, r)
        h = A.payload_hash(r.payload_json or {})
        ap = ctx.act("approve", "Approve", kind="decision", risk=r.risk or "high", payload={"action_record_id": r.id}, entity_id=r.id, confirm=True, primary=True)
        rj = ctx.act("reject", "Reject", kind="decision", risk="low", payload={"action_record_id": r.id}, entity_id=r.id, primary=True)
        items.append({"approval_id": r.id, "source": "action", "title": title, "risk": r.risk or "high", "preview": preview, "payload_hash": h,
                      "expires_at": None, "reason": r.reason, "proposed_by": r.source, "approve_action_id": ap["action_id"], "reject_action_id": rj["action_id"]})
        priorities.append({"rank": len(priorities) + 1, "entity_type": "approval", "entity_id": r.id, "title": title, "duration_min": None, "urgency": "high" if (r.risk == "high") else "medium",
                           "reason_codes": [f"risk_{r.risk}", "needs_user_approval"], "reason_text": r.reason or "OPAI never runs consequential actions without your approval.",
                           "next_action": "approve", "actions": [ap, rj]})
    if not only:
        for o in db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.status == "pending").all():
            if o.expires_at and o.expires_at < datetime.utcnow():
                continue
            pl = o.payload or {}
            a = ctx.act("open_outbox", "Review in Outbox", link="agent-console.html", entity_id=o.id)
            items.append({"approval_id": o.id, "source": "outbox", "title": f"{(o.channel or 'email').capitalize()} to {pl.get('to')}", "risk": o.risk_level or "high",
                          "preview": {"to": pl.get("to"), "subject": pl.get("subject"), "body": (pl.get("body") or "")[:400], "effect": "Sent only after you approve it in the Outbox."},
                          "expires_at": o.expires_at.isoformat() if o.expires_at else None})
            priorities.append({"rank": len(priorities) + 1, "entity_type": "outbox", "entity_id": o.id, "title": f"Review draft: {pl.get('subject') or 'message'}", "duration_min": 5,
                               "urgency": "medium", "reason_codes": ["draft_awaiting_review"], "reason_text": "Drafted by OPAI. Sending always needs your approval.", "next_action": "open_outbox", "actions": [a]})
    n = len(items)
    summary = f"{n} item(s) need your approval. Nothing runs until you approve." if n else "Nothing is waiting for approval."
    return _result("Approval brief", summary, 1.0, scope=only or "all", expires=_in(1), context={"user_id": uid, "pending": n},
                   priorities=priorities, approval_items=items, sources=[_src("Action approval queue", "rules"), _src("Outbox")],
                   codes=["needs_user_approval"] if n else [], short="Approvals are single-use and bound to the exact payload you reviewed.")


# ================================================================== 11. REMINDER CONFIRMATION BRIEF
def build_reminder(ctx: Ctx) -> Dict[str, Any]:
    import reminders as RM
    db, uid = ctx.db, ctx.uid
    r = db.query(Reminder).filter(Reminder.id == ctx.params["reminder_id"], Reminder.user_id == uid).first()
    if not r or r.kind != "reminder":
        raise BriefError(404, "Reminder not found")
    off = RM.offset_at(db, uid, r.remind_at)
    local, now_local = RM.to_local(r.remind_at, off), RM.to_local(datetime.utcnow(), RM.offset_at(db, uid))
    title = r.title or "Reminder"
    done = ctx.act("complete_reminder", "Done", kind="execute", intent="complete_reminder", payload={"reminder_id": r.id}, entity_id=r.id, primary=True)
    snz = ctx.act("snooze_reminder", "Snooze 10 minutes", kind="execute", intent="snooze_reminder", payload={"reminder_id": r.id, "minutes": 10}, entity_id=r.id)
    ctx.act("open_today", "Open Today", link="today.html", entity_id=r.id)
    pending = r.status == "pending"
    summary = (RM.confirm_text(title, local, now_local) if pending else
               f"Reminder: {title}. " + ("Marked done." if r.status == "done" else "Waiting for you." if r.status == "fired" else f"Status: {r.status}."))
    pri = {"rank": 1, "entity_type": "reminder", "entity_id": r.id, "title": title, "duration_min": None, "urgency": "medium",
           "reason_codes": ["user_requested_reminder"] + (["snoozed"] if r.snooze_count else []), "reason_text": f"You asked to be reminded at {RM.fmt_time(local)}.",
           "next_action": "complete_reminder", "actions": [done, snz]}
    return _result("Reminder", summary, 1.0, scope=f"{r.id}:{r.remind_at.isoformat()}", expires=_in(2), context={"user_id": uid, "reminder_id": r.id, "timezone": r.timezone},
                   priorities=[pri], sources=[_src("Your reminder")], codes=pri["reason_codes"], short="You created this reminder.",
                   reminder=RM.serialize(r, off))


# ================================================================== registry
BUILDERS: Dict[str, Callable[[Ctx], Dict[str, Any]]] = {
    "daily_plan": build_daily, "exam_readiness": build_exam, "dsa_roadmap": build_dsa, "application_opportunity": build_application,
    "outreach_research": build_outreach, "project": build_project, "weekly_review": build_weekly, "decision": build_decision,
    "recovery": build_recovery, "approval": build_approval, "reminder": build_reminder,
}
