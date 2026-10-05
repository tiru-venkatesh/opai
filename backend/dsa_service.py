"""DSA Roadmap service: thin database layer around dsa_roadmap (all rules live there and are unit-tested).

OPAI only plans, tracks, reminds and adapts. Practice happens on external platforms; we store links only."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import dsa_roadmap as R
from database import Course, DsaPlan, DsaSession, DsaTopic, Exam


class DsaError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


def _plan(db: Session, uid: str) -> Optional[DsaPlan]:
    return db.query(DsaPlan).filter(DsaPlan.user_id == uid, DsaPlan.status == "active").first()


def _tdict(t: DsaTopic) -> Dict[str, Any]:
    return dict(id=t.id, position=t.position or 0, phase_no=t.phase_no or 1, phase=t.phase or "", name=t.name,
                planned_week=t.planned_week or 1, status=t.status or "not_started", confidence=t.confidence,
                learn_url=t.learn_url, practice_url=t.practice_url, notes=t.notes or "", sessions_done=t.sessions_done or 0)


def _topics(db: Session, plan: DsaPlan) -> List[Dict[str, Any]]:
    rows = db.query(DsaTopic).filter(DsaTopic.plan_id == plan.id).order_by(DsaTopic.position).all()
    return [_tdict(t) for t in rows]


def _exam_context(db: Session, uid: str, today: date):
    """Nearest upcoming exam -> (days away, course name). (None, None) when there is none."""
    e = (db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed", Exam.exam_date >= today)
         .order_by(Exam.exam_date).first())
    if not e:
        return None, None
    course = db.query(Course).filter(Course.id == e.course_id).first() if e.course_id else None
    name = getattr(course, "name", None) or getattr(course, "course_name", None) or "exam"
    return (e.exam_date - today).days, name


def ensure_session(db: Session, plan: DsaPlan, tdicts: List[Dict[str, Any]], today: date, exam_days: Optional[int]) -> Optional[DsaSession]:
    """The one DSA block for `today`. Re-evaluated while still 'planned' so exam season and topic changes adapt it;
    done/skipped blocks are frozen."""
    mode, _ = R.mode_for(exam_days, plan.mode_override or "auto")
    topic, kind = R.pick_topic(tdicts, mode)
    s = db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date == today).first()
    if topic is None:
        return s
    minutes = R.day_minutes(plan.daily_minutes or 60, mode)
    if s is None:
        s = DsaSession(user_id=plan.user_id, plan_id=plan.id, topic_id=topic["id"], plan_date=today, minutes=minutes,
                       mode=mode, kind=kind, status="planned")
        db.add(s)
        try:
            db.commit()
        except Exception:                      # a concurrent request created today's row first
            db.rollback()
            s = db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date == today).first()
        else:
            db.refresh(s)
    elif s.status == "planned" and (s.topic_id != topic["id"] or s.mode != mode or s.minutes != minutes or s.kind != kind):
        s.topic_id, s.mode, s.minutes, s.kind = topic["id"], mode, minutes, kind
        db.commit()
    return s


# ---------------------------------------------------------------- state for the DSA page
def options() -> Dict[str, Any]:
    return {"languages": list(R.LANGUAGES), "goals": list(R.GOALS), "daily_minutes": [30, 45, 60, 90], "days_per_week": [3, 4, 5, 6, 7],
            "statuses": [{"id": s, "label": R.STATUS_LABEL[s]} for s in R.STATUSES]}


def state(db: Session, uid: str, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    base = {"options": options(), "resources": {"learn": R.LEARN_URL, "gfg": R.GFG_ROADMAP}}
    plan = _plan(db, uid)
    if not plan:
        return {**base, "plan": None}
    td = _topics(db, plan)
    start = plan.start_date or today
    week, overrun = R.week_number(start, today)
    exam_days, exam_name = _exam_context(db, uid, today)
    mode, why = R.mode_for(exam_days, plan.mode_override or "auto")
    act = R.active_topic(td)
    sess = ensure_session(db, plan, td, today, exam_days)
    byid = {t["id"]: t for t in td}

    phases = []
    for no, name, (a, b), _ in R.PHASES:
        ts = [dict(t, is_active=bool(act and act["id"] == t["id"]), status_label=R.STATUS_LABEL.get(t["status"], t["status"])) for t in td if t["phase_no"] == no]
        phases.append({"no": no, "name": name, "weeks": [a, b], "topics": ts, "advanced": sum(1 for t in ts if R.is_advanced(t["status"])), "total": len(ts)})

    adv = sum(1 for t in td if R.is_advanced(t["status"]))
    today_block = None
    if sess and byid.get(sess.topic_id):
        topic = byid[sess.topic_id]
        today_block = {"date": today.isoformat(), "session_id": sess.id, "status": sess.status, "minutes": sess.minutes, "mode": sess.mode,
                       "kind": sess.kind, "confidence": sess.confidence,
                       "topic": {"id": topic["id"], "name": topic["name"], "phase": topic["phase"]},
                       "blocks": R.day_blocks(topic, sess.mode, sess.kind, sess.minutes)}

    first = start + timedelta(days=7 * (week - 1))
    rows = db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date >= first, DsaSession.plan_date <= first + timedelta(days=6)).all()
    by_date = {r.plan_date: r.status for r in rows}
    return {**base,
            "plan": {"id": plan.id, "goal": plan.goal, "language": plan.language, "daily_minutes": plan.daily_minutes, "days_per_week": plan.days_per_week,
                     "start_date": start.isoformat(), "target": "90-day roadmap", "mode_override": plan.mode_override or "auto"},
            "progress": {"week": week, "weeks": R.WEEKS, "overrun": overrun, "advanced": adv, "total": len(td), "percent": round(100 * adv / max(1, len(td))),
                         "current_phase": act["phase"] if act else "Roadmap complete", "current_topic": act["name"] if act else None},
            "pace": R.pace(td, week),
            "mode": {"mode": mode, "reason": why, "exam_in_days": exam_days, "exam_name": exam_name, "override": plan.mode_override or "auto"},
            "this_week": R.week_bullets(td, week),
            "today": today_block,
            "phases": phases,
            "consistency": {"planned": plan.days_per_week, "completed": sum(1 for v in by_date.values() if v == "done"), "days": R.week_days(start, week, by_date, today)}}


# ---------------------------------------------------------------- mutations
def create_plan(db: Session, uid: str, goal: str, language: str, daily_minutes: int, days_per_week: int, today: Optional[date] = None) -> DsaPlan:
    if language not in R.LANGUAGES:
        raise DsaError(422, "Pick one of: " + ", ".join(R.LANGUAGES))
    if goal not in R.GOALS:
        raise DsaError(422, "Pick one of: " + ", ".join(R.GOALS))
    daily_minutes, days_per_week = max(20, min(int(daily_minutes), 180)), max(1, min(int(days_per_week), 7))
    for model in (DsaSession, DsaTopic, DsaPlan):          # a fresh roadmap replaces the old one
        db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
    plan = DsaPlan(user_id=uid, goal=goal, language=language, daily_minutes=daily_minutes, days_per_week=days_per_week,
                   weeks=R.WEEKS, start_date=today or date.today(), mode_override="auto", status="active")
    db.add(plan)
    db.flush()
    for t in R.build_topics(language):
        db.add(DsaTopic(plan_id=plan.id, user_id=uid, **t))
    db.commit()
    db.refresh(plan)
    return plan


def delete_plan(db: Session, uid: str) -> None:
    for model in (DsaSession, DsaTopic, DsaPlan):
        db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
    db.commit()


def update_settings(db: Session, uid: str, fields: Dict[str, Any]) -> None:
    plan = _plan(db, uid)
    if not plan:
        raise DsaError(404, "No DSA roadmap yet")
    if "mode_override" in fields and fields["mode_override"] is not None:
        if fields["mode_override"] not in R.MODES:
            raise DsaError(422, "mode_override must be auto, normal or maintenance")
        plan.mode_override = fields["mode_override"]
    if fields.get("daily_minutes") is not None:
        plan.daily_minutes = max(20, min(int(fields["daily_minutes"]), 180))
    if fields.get("days_per_week") is not None:
        plan.days_per_week = max(1, min(int(fields["days_per_week"]), 7))
    db.commit()


def update_topic(db: Session, uid: str, topic_id: str, fields: Dict[str, Any]) -> None:
    t = db.query(DsaTopic).filter(DsaTopic.id == str(topic_id), DsaTopic.user_id == uid).first()
    if not t:
        raise DsaError(404, "Topic not found")
    if "status" in fields and fields["status"] is not None:
        if fields["status"] not in R.STATUSES:
            raise DsaError(422, "Unknown status")
        t.status = fields["status"]
    if "confidence" in fields:
        c = fields["confidence"]
        if c is not None and not (1 <= int(c) <= 5):
            raise DsaError(422, "Confidence is 1 to 5")
        t.confidence = c
    for k in ("learn_url", "practice_url"):
        if k in fields:
            try:
                setattr(t, k, R.clean_url(fields[k]))
            except ValueError as e:
                raise DsaError(422, str(e))
    if "notes" in fields:
        t.notes = (fields["notes"] or "")[:2000]
    t.updated_at = datetime.utcnow()
    db.commit()


def _session(db: Session, uid: str, sid: str) -> DsaSession:
    s = db.query(DsaSession).filter(DsaSession.id == str(sid), DsaSession.user_id == uid).first()
    if not s:
        raise DsaError(404, "DSA session not found")
    return s


def complete_session(db: Session, uid: str, sid: str, actual_minutes: Optional[int] = None, confidence: Optional[int] = None) -> DsaSession:
    """User is back from the external site and marks progress. Updates the topic, so tomorrow's block adapts."""
    s = _session(db, uid, sid)
    if s.status == "done":
        return s                                              # idempotent
    t = db.query(DsaTopic).filter(DsaTopic.id == s.topic_id).first()
    s.status, s.completed_at = "done", datetime.utcnow()
    s.actual_minutes = actual_minutes
    s.confidence = confidence
    if t:
        if confidence is not None:
            t.confidence = confidence
        if s.mode == "normal":                               # maintenance reviews never advance the roadmap
            before = t.sessions_done or 0
            t.status = R.status_after_session(t.status or "not_started", before, confidence)
            t.sessions_done = before + 1
        t.last_session = s.plan_date
        t.updated_at = datetime.utcnow()
    db.commit()
    return s


def skip_session(db: Session, uid: str, sid: str) -> DsaSession:
    """Skip/move: nothing is lost. Tomorrow resumes with the same topic."""
    s = _session(db, uid, sid)
    if s.status == "planned":
        s.status = "skipped"
        db.commit()
    return s


# ---------------------------------------------------------------- Today integration
def today_candidates(db: Session, uid: str, today: date) -> List[Dict[str, Any]]:
    plan = _plan(db, uid)
    if not plan:
        return []
    td = _topics(db, plan)
    exam_days, exam_name = _exam_context(db, uid, today)
    s = ensure_session(db, plan, td, today, exam_days)
    if s is None or s.status == "skipped":
        return []
    topic = next((t for t in td if t["id"] == s.topic_id), None)
    if not topic:
        return []
    week, _ = R.week_number(plan.start_date or today, today)
    last = (db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.status == "done", DsaSession.plan_date < today)
            .order_by(DsaSession.plan_date.desc()).first())
    stale = min(14, (today - last.plan_date).days) if last else 0
    maint = s.mode == "maintenance"
    return [dict(kind="dsa", ref_id=s.id,
                 title=(f"DSA maintenance — {topic['name']}" if maint else f"DSA Roadmap — {topic['name']}"),
                 subtitle=("Maintenance · review only" + (f" · {exam_name} exam in {exam_days}d" if exam_days is not None else "")) if maint else f"Week {week} of {R.WEEKS} · {topic['phase']}",
                 minutes=int(s.minutes or 30), days=None, importance=0.3 if maint else 0.55, stale=stale, done=s.status == "done",
                 effort=int(s.minutes or 30), link="dsa.html",
                 facts=dict(topic=topic["name"], phase=topic["phase"], week=week, mode=s.mode, minutes=int(s.minutes or 30),
                            exam_in_days=exam_days, exam_name=exam_name, learn_url=topic.get("learn_url"), practice_url=topic.get("practice_url")))]
