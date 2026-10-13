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
                learn_url=t.learn_url, practice_url=t.practice_url, notes=t.notes or "", sessions_done=t.sessions_done or 0,
                next_review=t.next_review, review_count=t.review_count or 0)


def _res(plan: DsaPlan) -> Dict[str, Any]:
    return R.clean_resources(getattr(plan, "resources", None), None)


def _topics(db: Session, plan: DsaPlan) -> List[Dict[str, Any]]:
    rows = db.query(DsaTopic).filter(DsaTopic.plan_id == plan.id).order_by(DsaTopic.position).all()
    defaults, res, out = R.default_links(plan.language or "Python"), _res(plan), []
    for t in rows:
        d = _tdict(t)
        d["learn_url"], d["practice_url"] = R.effective_links(d, defaults[d["position"]] if d["position"] < len(defaults) else (None, None), res)
        out.append(d)
    return out


def _exam_context(db: Session, uid: str, today: date):
    """Nearest upcoming exam -> (days away, course name). (None, None) when there is none."""
    e = (db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed", Exam.exam_date >= today)
         .order_by(Exam.exam_date).first())
    if not e:
        return None, None
    course = db.query(Course).filter(Course.id == e.course_id).first() if e.course_id else None
    name = getattr(course, "name", None) or getattr(course, "course_name", None) or "exam"
    return (e.exam_date - today).days, name


def _learn_streak(db: Session, plan: DsaPlan, today: date) -> int:
    """Learn sessions in a row (most recent first) since the last revision slot. Skipped days do not count."""
    rows = (db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date < today, DsaSession.status == "done")
            .order_by(DsaSession.plan_date.desc()).limit(6).all())
    n = 0
    for r in rows:
        if r.kind in ("revise", "review"):
            break
        n += 1
    return n


def ensure_session(db: Session, plan: DsaPlan, tdicts: List[Dict[str, Any]], today: date, exam_days: Optional[int]) -> Optional[DsaSession]:
    """The one DSA block for `today`. Re-evaluated while still 'planned' so exam season and topic changes adapt it;
    done/skipped blocks are frozen."""
    mode, _ = R.mode_for(exam_days, plan.mode_override or "auto")
    if mode == "paused":
        return None                              # paused: no DSA block is generated (history and progress are kept)
    due = R.due_reviews(tdicts, today)
    topic, kind = R.pick_topic(tdicts, mode, due, _learn_streak(db, plan, today))
    s = db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date == today).first()
    if topic is None:
        return s
    minutes = R.day_minutes(plan.daily_minutes or 60, mode, exam_days)
    if kind == "revise":
        minutes = R.review_minutes(minutes, topic["confidence"])
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


def _with_notes(blocks: List[Dict[str, Any]], plan: DsaPlan) -> List[Dict[str, Any]]:
    n = _res(plan)["notes"]
    for b in blocks:
        if b["kind"] == "notes" and n["url"]:
            b["url"] = n["url"]
    return blocks


# ---------------------------------------------------------------- state for the DSA page
def options() -> Dict[str, Any]:
    return {"languages": list(R.LANGUAGES), "goals": list(R.GOALS), "levels": list(R.LEVELS), "daily_minutes": [20, 30, 45, 60], "days_per_week": [3, 4, 5, 6, 7],
            "modes": list(R.MODES), "resources": {"learn": list(R.LEARN_SOURCES), "practice": list(R.PRACTICE_SOURCES), "notes": list(R.NOTES_SOURCES)}, "outcomes": list(R.OUTCOMES), "difficulty": list(R.DIFFICULTY),
            "statuses": [{"id": s, "label": R.STATUS_LABEL[s]} for s in R.STATUSES],
            "tracks": [{k: t[k] for k in ("key", "name", "best_for", "goal", "level", "minutes")} for t in R.TRACKS]}


def state(db: Session, uid: str, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    base = {"options": options(), "resources": {"learn": R.LEARN_URL, "gfg": R.GFG_ROADMAP}}
    plan = _plan(db, uid)
    if not plan:
        return {**base, "plan": None}
    td = _topics(db, plan)
    start = plan.start_date or today
    weeks = plan.weeks or R.WEEKS
    week, overrun = R.week_number(start, today, weeks)
    exam_days, exam_name = _exam_context(db, uid, today)
    mode, why = R.mode_for(exam_days, plan.mode_override or "auto")
    act = R.active_topic(td)
    sess = ensure_session(db, plan, td, today, exam_days)
    byid = {t["id"]: t for t in td}

    locks = R.lock_states(td)
    phases = []
    for no, name, _w, _ in R.PHASES:
        a, b = R.phase_weeks(no, weeks)
        ts = [dict(t, is_active=bool(act and act["id"] == t["id"]), status_label=R.STATUS_LABEL.get(t["status"], t["status"]),
                   lock=locks[t["id"]]["state"], lock_why=locks[t["id"]]["why"]) for t in td if t["phase_no"] == no]
        phases.append({"no": no, "name": name, "weeks": [a, b], "topics": ts, "advanced": sum(1 for t in ts if R.is_advanced(t["status"])), "total": len(ts)})

    adv = sum(1 for t in td if R.is_advanced(t["status"]))
    today_block = None
    if sess and byid.get(sess.topic_id):
        topic = byid[sess.topic_id]
        today_block = {"date": today.isoformat(), "session_id": sess.id, "status": sess.status, "minutes": sess.minutes, "mode": sess.mode,
                       "kind": sess.kind, "confidence": sess.confidence,
                       "topic": {"id": topic["id"], "name": topic["name"], "phase": topic["phase"]},
                       "why": R.why_now(topic, sess.kind, sess.mode),
                       "next_up": next((t["name"] for t in td if t["position"] > topic["position"] and not R.is_advanced(t["status"])), None),
                       "blocks": _with_notes(R.day_blocks(topic, sess.mode, sess.kind, sess.minutes), plan)}

    queue = [dict(topic_id=t["id"], name=t["name"], phase=t["phase"], confidence=t["confidence"], minutes=R.review_minutes(plan.daily_minutes or 60, t["confidence"]),
                  due=t["next_review"].isoformat(), overdue_days=(today - t["next_review"]).days,
                  learn_url=t["learn_url"], practice_url=t["practice_url"]) for t in R.due_reviews(td, today)]
    hist = (db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.status.in_(("done", "skipped")))
            .order_by(DsaSession.plan_date.desc(), DsaSession.created_at.desc()).limit(15).all())
    history = [dict(date=h.plan_date.isoformat(), topic=(byid.get(h.topic_id) or {}).get("name", "Topic"), kind=h.kind, status=h.status, outcome=h.outcome,
                    minutes=h.actual_minutes or h.minutes, confidence=h.confidence, difficulty=h.difficulty_tags or []) for h in hist]
    first = start + timedelta(days=7 * (week - 1))
    rows = db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.plan_date >= first, DsaSession.plan_date <= first + timedelta(days=6)).all()
    by_date = {r.plan_date: r.status for r in rows}
    return {**base,
            "plan": {"id": plan.id, "goal": plan.goal, "language": plan.language, "daily_minutes": plan.daily_minutes, "days_per_week": plan.days_per_week,
                     "start_date": start.isoformat(), "target": "90-day roadmap", "mode_override": plan.mode_override or "auto",
                     "level": plan.level, "target_date": plan.target_date.isoformat() if plan.target_date else None,
                     "weeks": weeks, "resources": _res(plan),
                     "track": R.track_summary(plan.goal or "", plan.level or "", plan.daily_minutes or 60)},
            "progress": {"week": week, "weeks": weeks, "overrun": overrun, "advanced": adv, "total": len(td), "percent": round(100 * adv / max(1, len(td))),
                         "current_phase": act["phase"] if act else "Roadmap complete", "current_topic": act["name"] if act else None,
                         "milestone": R.next_milestone(td)},
            "pace": R.pace(td, week),
            "mode": {"mode": mode, "reason": why, "exam_in_days": exam_days, "exam_name": exam_name, "override": plan.mode_override or "auto",
                     "heads_up": (f"{exam_name} exam in {exam_days} days. DSA moves to maintenance within {R.EXAM_WINDOW_DAYS} days; you can override this anytime."
                                  if mode == "normal" and exam_days is not None and R.EXAM_WINDOW_DAYS < exam_days <= 14 and (plan.mode_override or "auto") == "auto" else "")},
            "this_week": R.week_bullets(td, week),
            "week_plan": R.week_plan(plan.days_per_week or 5),
            "revision_queue": queue,
            "history": history,
            "today": today_block,
            "phases": phases,
            "weekly_review": R.weekly_review(td, [dict(topic_id=r.topic_id, status=r.status, outcome=r.outcome, confidence=r.confidence) for r in rows],
                                             plan.days_per_week or 5, week, today),
            "consistency": {"planned": plan.days_per_week, "completed": sum(1 for v in by_date.values() if v == "done"), "days": R.week_days(start, week, by_date, today)}}


# ---------------------------------------------------------------- mutations
def create_plan(db: Session, uid: str, goal: str, language: str, daily_minutes: int, days_per_week: int, today: Optional[date] = None,
                level: str = "Starting from basics", target_date: Optional[date] = None) -> DsaPlan:
    if language not in R.LANGUAGES:
        raise DsaError(422, "Pick one of: " + ", ".join(R.LANGUAGES))
    if goal not in R.GOALS + R.LEGACY_GOALS:
        raise DsaError(422, "Pick one of: " + ", ".join(R.GOALS))
    if level not in R.LEVELS:
        raise DsaError(422, "Pick one of: " + ", ".join(R.LEVELS))
    start = today or date.today()
    if target_date is not None and target_date <= start:
        raise DsaError(422, "Target date must be in the future")
    daily_minutes, days_per_week = max(20, min(int(daily_minutes), 180)), max(1, min(int(days_per_week), 7))
    for model in (DsaSession, DsaTopic, DsaPlan):          # a fresh roadmap replaces the old one
        db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
    weeks = R.weeks_for(daily_minutes)
    plan = DsaPlan(user_id=uid, goal=goal, language=language, daily_minutes=daily_minutes, days_per_week=days_per_week,
                   weeks=weeks, resources=R.clean_resources(None, None), start_date=start, mode_override="auto", status="active", level=level, target_date=target_date)
    db.add(plan)
    db.flush()
    for t in R.build_topics(language, level, start, weeks):
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
            raise DsaError(422, "mode_override must be auto, normal, maintenance or paused")
        plan.mode_override = fields["mode_override"]
    if "target_date" in fields:
        td_ = fields["target_date"]
        if td_ is not None and td_ <= date.today():
            raise DsaError(422, "Target date must be in the future")
        plan.target_date = td_
    if fields.get("daily_minutes") is not None:
        plan.daily_minutes = max(20, min(int(fields["daily_minutes"]), 180))
        new_weeks = R.weeks_for(plan.daily_minutes)
        if new_weeks != (plan.weeks or R.WEEKS):                    # roadmap length follows daily time; topics keep their status
            plan.weeks = new_weeks
            pw = R.planned_weeks(plan.language or "Python", new_weeks)
            for t in db.query(DsaTopic).filter(DsaTopic.plan_id == plan.id).all():
                if t.position is not None and t.position < len(pw):
                    t.planned_week = pw[t.position]
    if fields.get("resources") is not None:
        try:
            plan.resources = R.clean_resources(getattr(plan, "resources", None), fields["resources"])
        except ValueError as e:
            raise DsaError(422, str(e))
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
    plan = db.query(DsaPlan).filter(DsaPlan.id == t.plan_id).first()
    if plan is not None and any(k in fields for k in ("learn_url", "practice_url")):
        dl = R.default_links(plan.language or "Python")
        cur = dict(name=t.name, learn_url=t.learn_url, practice_url=t.practice_url)
        eff = R.effective_links(cur, dl[t.position] if t.position is not None and t.position < len(dl) else (None, None), _res(plan))
    else:
        eff = (None, None)
    for i, k in enumerate(("learn_url", "practice_url")):
        if k in fields:
            try:
                v = R.clean_url(fields[k])
            except ValueError as e:
                raise DsaError(422, str(e))
            if v is not None and v == eff[i]:
                continue                                              # shown value unchanged: keep inheriting, don't pin it
            setattr(t, k, v)
    if "notes" in fields:
        t.notes = (fields["notes"] or "")[:2000]
    t.updated_at = datetime.utcnow()
    db.commit()


def _session(db: Session, uid: str, sid: str) -> DsaSession:
    s = db.query(DsaSession).filter(DsaSession.id == str(sid), DsaSession.user_id == uid).first()
    if not s:
        raise DsaError(404, "DSA session not found")
    return s


def complete_session(db: Session, uid: str, sid: str, actual_minutes: Optional[int] = None, confidence: Optional[int] = None,
                     outcome: str = "completed", difficulty: Optional[List[str]] = None) -> DsaSession:
    """User is back from the external site and logs the outcome. Updates topic status, confidence, time spent and the
    next revision date, so tomorrow's block adapts. outcome: completed | partial | could_not_start."""
    if outcome not in R.OUTCOMES:
        raise DsaError(422, "outcome must be one of: " + ", ".join(R.OUTCOMES))
    try:
        tags = R.clean_tags(difficulty)
    except ValueError as e:
        raise DsaError(422, str(e))
    s = _session(db, uid, sid)
    if s.status == "done":
        return s                                              # idempotent
    t = db.query(DsaTopic).filter(DsaTopic.id == s.topic_id).first()
    s.outcome, s.difficulty_tags = outcome, tags
    if outcome == "could_not_start":                          # nothing is lost: same topic tomorrow, no progress recorded
        if s.status == "planned":
            s.status = "skipped"
        db.commit()
        return s
    s.status, s.completed_at = "done", datetime.utcnow()
    s.actual_minutes = actual_minutes
    s.confidence = confidence
    if t:
        if confidence is not None:
            t.confidence = confidence
        before = t.sessions_done or 0
        if s.mode == "normal" and s.kind == "learn":          # only a normal learn session moves the roadmap
            t.status = R.status_after_session(t.status or "not_started", before, confidence, outcome)
            if outcome == "completed":
                t.sessions_done = before + 1
        elif s.kind in ("revise", "review"):                  # a revision can lift a topic (practicing -> revised -> comfortable)
            if outcome == "completed" and t.status in ("practicing", "revised"):
                t.status = R.status_after_session(t.status, before, confidence)
            t.review_count = (t.review_count or 0) + 1
        t.last_session = s.plan_date
        # partly done = look again tomorrow; otherwise the interval follows the learner's own confidence
        t.next_review = s.plan_date + timedelta(days=1) if outcome == "partial" else R.next_review_date(confidence if confidence is not None else t.confidence, s.plan_date)
        t.updated_at = datetime.utcnow()
    db.commit()
    return s


def review_topic(db: Session, uid: str, topic_id: str, confidence: int, actual_minutes: Optional[int] = None, today: Optional[date] = None) -> None:
    """Log a revision from the Revision Queue (separate from the one daily block). Resets the review date."""
    t = db.query(DsaTopic).filter(DsaTopic.id == str(topic_id), DsaTopic.user_id == uid).first()
    if not t:
        raise DsaError(404, "Topic not found")
    if not (1 <= int(confidence) <= 5):
        raise DsaError(422, "Confidence is 1 to 5")
    today = today or date.today()
    t.confidence = int(confidence)
    t.review_count = (t.review_count or 0) + 1
    t.last_session = today
    t.next_review = R.next_review_date(t.confidence, today)
    if t.status in ("practicing", "revised"):
        t.status = R.status_after_session(t.status, t.sessions_done or 0, t.confidence)
    t.updated_at = datetime.utcnow()
    db.commit()


def shorten_session(db: Session, uid: str, sid: str, minutes: int) -> DsaSession:
    """Make today's block shorter (never longer). Blocks are rebuilt from `minutes`, so the plan stays consistent."""
    s = _session(db, uid, sid)
    if s.status not in ("planned", "in_progress"):
        raise DsaError(409, "Only an open block can be shortened")
    m = int(minutes)
    if m < 5 or m >= (s.minutes or 0):
        raise DsaError(422, "Pick a time between 5 minutes and less than the planned block")
    s.minutes = m
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
    s = ensure_session(db, plan, td, today, exam_days)       # None while paused
    if s is None or s.status == "skipped":
        return []
    topic = next((t for t in td if t["id"] == s.topic_id), None)
    if not topic:
        return []
    week, _ = R.week_number(plan.start_date or today, today, plan.weeks or R.WEEKS)
    last = (db.query(DsaSession).filter(DsaSession.plan_id == plan.id, DsaSession.status == "done", DsaSession.plan_date < today)
            .order_by(DsaSession.plan_date.desc()).first())
    stale = min(14, (today - last.plan_date).days) if last else 0
    maint = s.mode == "maintenance"
    revise = s.kind in ("revise", "review")
    return [dict(kind="dsa", ref_id=s.id,
                 title=(f"DSA maintenance — {topic['name']}" if maint else f"DSA revision — {topic['name']}" if revise else f"DSA Roadmap — {topic['name']}"),
                 subtitle=("Maintenance · review only" + (f" · {exam_name} exam in {exam_days}d" if exam_days is not None else "")) if maint else f"Week {week} of {plan.weeks or R.WEEKS} · {topic['phase']}",
                 minutes=int(s.minutes or 30), days=None, importance=0.3 if (maint or revise) else 0.55, stale=stale, done=s.status == "done",
                 effort=int(s.minutes or 30), link="dsa.html",
                 facts=dict(topic=topic["name"], phase=topic["phase"], week=week, mode=s.mode, minutes=int(s.minutes or 30),
                            exam_in_days=exam_days, exam_name=exam_name, learn_url=topic.get("learn_url"), practice_url=topic.get("practice_url")))]
