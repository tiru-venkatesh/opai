"""DSA Coach service: database layer around dsa_coach (all rules live there and are unit-tested).

Stores attempt metadata and the revision schedule. Never a problem statement, a solution or code."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import dsa_coach as C
import dsa_roadmap as R
import dsa_service as S
from database import DsaAttempt, DsaMastery, Notification, Reminder, User


class CoachError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


# ---------------------------------------------------------------- helpers
def _mrow(m: DsaMastery) -> Dict[str, Any]:
    return dict(key=m.problem_key, title=m.title, url=m.url, pattern=m.pattern, difficulty=m.difficulty, stage=m.stage or 0, state=m.state or "new",
                attempts=m.attempts or 0, clean_resolves=m.clean_resolves or 0, last_result=m.last_result, last_attempt=m.last_attempt, next_review=m.next_review)


def _arow(a: DsaAttempt) -> Dict[str, Any]:
    return dict(pattern=a.pattern, result=a.result, on=a.attempted_on, is_resolve=bool(a.is_resolve), mistakes=a.mistakes or [])


def _attempts(db: Session, uid: str, today: date) -> List[DsaAttempt]:
    return (db.query(DsaAttempt).filter(DsaAttempt.user_id == uid, DsaAttempt.attempted_on >= today - timedelta(days=C.LOOKBACK_DAYS))
            .order_by(DsaAttempt.attempted_on.desc(), DsaAttempt.created_at.desc()).all())


def _clip(v: Optional[str], n: int) -> Optional[str]:
    v = (v or "").strip()
    return v[:n] or None


# ---------------------------------------------------------------- logging an attempt
def log_attempt(db: Session, uid: str, f: Dict[str, Any], today: date) -> Dict[str, Any]:
    """Record one attempt and move the problem's spaced-revision schedule. `today` is the learner's local date."""
    try:
        url = R.clean_url(f.get("url"))
        mistakes = C.clean_mistakes(f.get("mistakes"))
    except ValueError as e:
        raise CoachError(422, str(e))
    title = _clip(f.get("title"), 200)
    if not title and not url:
        raise CoachError(422, "Give the problem a title or a link.")
    key = C.problem_key(title, url)
    if not key:
        raise CoachError(422, "Could not tell which problem this is. Add a title or a link.")
    bank = C.BANK_BY_KEY.get(key)
    title = title or (bank["title"] if bank else key.replace("-", " ").title())
    url = url or (bank["url"] if bank else None)
    pattern = f.get("pattern") or (bank["pattern"] if bank else None)
    if pattern is not None and pattern not in C.PATTERNS:
        raise CoachError(422, "Pattern must be one of: " + ", ".join(C.PATTERNS))
    difficulty = f.get("difficulty") or (bank["difficulty"] if bank else None)
    if difficulty is not None and difficulty not in C.DIFFICULTIES:
        raise CoachError(422, "Difficulty must be Easy, Medium or Hard")
    platform = f.get("platform") or ("LeetCode" if url and "leetcode.com" in url else "Other")
    if platform not in C.PLATFORMS:
        raise CoachError(422, "Platform must be one of: " + ", ".join(C.PLATFORMS))
    predicted = f.get("predicted_pattern")
    if predicted is not None and predicted not in C.PATTERNS:
        raise CoachError(422, "predicted_pattern must be one of: " + ", ".join(C.PATTERNS))
    hints, saw = max(0, int(f.get("hints_used") or 0)), bool(f.get("saw_solution"))
    try:
        result = C.effective_result(f.get("result") or "", hints, saw)
    except ValueError as e:
        raise CoachError(422, str(e))
    if result == "solved" and mistakes:
        mistakes = []                                      # a clean solve has no mistakes to learn from
    prev = db.query(DsaMastery).filter(DsaMastery.user_id == uid, DsaMastery.problem_key == key).first()
    before = prev.attempts if prev else 0
    nm = C.next_mastery(prev.stage if prev else 0, prev.clean_resolves if prev else 0, before, "failed" if (saw and result != "solved") else result, today)
    a = DsaAttempt(user_id=uid, problem_key=key, title=title, url=url, platform=platform, pattern=pattern, difficulty=difficulty, result=result,
                   hints_used=hints, saw_solution=saw, minutes=f.get("minutes"), mistakes=mistakes, time_complexity=_clip(f.get("time_complexity"), 40),
                   space_complexity=_clip(f.get("space_complexity"), 40), predicted_pattern=predicted,
                   recall_correct=(predicted == pattern) if (predicted and pattern) else None, approach_note=_clip(f.get("approach_note"), 500),
                   slot=f.get("slot") or "manual", is_resolve=before >= 1, attempted_on=today)
    db.add(a)
    if prev is None:
        prev = DsaMastery(user_id=uid, problem_key=key, title=title, url=url, pattern=pattern, difficulty=difficulty)
        db.add(prev)
    prev.title, prev.url = title, url or prev.url
    prev.pattern, prev.difficulty = pattern or prev.pattern, difficulty or prev.difficulty
    prev.stage, prev.state, prev.attempts, prev.clean_resolves = nm["stage"], nm["state"], nm["attempts"], nm["clean_resolves"]
    prev.last_result, prev.last_attempt, prev.next_review, prev.updated_at = result, today, nm["next_review"], datetime.utcnow()
    db.commit()
    db.refresh(a)
    return dict(attempt=attempt_view(a), mastery=mastery_view(_mrow(prev), today))


def attempt_view(a: DsaAttempt) -> Dict[str, Any]:
    return dict(id=a.id, date=a.attempted_on.isoformat(), title=a.title, url=a.url, platform=a.platform, pattern=a.pattern,
                pattern_name=C.PATTERNS.get(a.pattern or "", None), difficulty=a.difficulty, result=a.result, hints_used=a.hints_used or 0,
                saw_solution=bool(a.saw_solution), minutes=a.minutes, mistakes=a.mistakes or [], time_complexity=a.time_complexity,
                space_complexity=a.space_complexity, recall_correct=a.recall_correct, is_resolve=bool(a.is_resolve), slot=a.slot)


def mastery_view(m: Dict[str, Any], today: date) -> Dict[str, Any]:
    nr = m.get("next_review")
    return dict(key=m["key"], title=m["title"], url=m.get("url"), pattern=m.get("pattern"), pattern_name=C.PATTERNS.get(m.get("pattern") or "", None),
                difficulty=m.get("difficulty"), stage=m["stage"], max_stage=C.MAX_STAGE, state=m["state"], attempts=m["attempts"],
                clean_resolves=m["clean_resolves"], last_result=m.get("last_result"), next_review=nr.isoformat() if nr else None,
                due_in_days=(nr - today).days if nr else None)


def delete_attempt(db: Session, uid: str, aid: str, today: date) -> None:
    """Undo a mis-logged attempt, then rebuild that problem's mastery row from what is left."""
    a = db.query(DsaAttempt).filter(DsaAttempt.id == str(aid), DsaAttempt.user_id == uid).first()
    if not a:
        raise CoachError(404, "Attempt not found")
    key = a.problem_key
    db.delete(a)
    db.flush()
    rebuild_mastery(db, uid, key)
    db.commit()


def rebuild_mastery(db: Session, uid: str, key: str) -> None:
    rows = (db.query(DsaAttempt).filter(DsaAttempt.user_id == uid, DsaAttempt.problem_key == key)
            .order_by(DsaAttempt.attempted_on, DsaAttempt.created_at).all())
    m = db.query(DsaMastery).filter(DsaMastery.user_id == uid, DsaMastery.problem_key == key).first()
    if not rows:
        if m:
            db.delete(m)
        return
    stage = clean = 0
    nm: Dict[str, Any] = {}
    for i, r in enumerate(rows):
        res = "failed" if (r.saw_solution and r.result != "solved") else r.result
        nm = C.next_mastery(stage, clean, i, res, r.attempted_on)
        stage, clean = nm["stage"], nm["clean_resolves"]
        r.is_resolve = i >= 1
    last = rows[-1]
    if m is None:
        m = DsaMastery(user_id=uid, problem_key=key, title=last.title)
        db.add(m)
    m.title, m.url, m.pattern, m.difficulty = last.title, last.url, last.pattern, last.difficulty
    m.stage, m.state, m.attempts, m.clean_resolves = nm["stage"], nm["state"], nm["attempts"], nm["clean_resolves"]
    m.last_result, m.last_attempt, m.next_review, m.updated_at = last.result, last.attempted_on, nm["next_review"], datetime.utcnow()


# ---------------------------------------------------------------- the coach view
def _streak(db: Session, uid: str, today: date) -> Dict[str, Any]:
    days = [d for (d,) in db.query(DsaAttempt.attempted_on).filter(DsaAttempt.user_id == uid).distinct().all()]
    return C.practice_streak(days, today)


def _roadmap_pattern(db: Session, uid: str) -> Optional[str]:
    plan = S._plan(db, uid)
    act = R.active_topic(S._topics(db, plan)) if plan else None
    return C.pattern_for_topic(act["name"]) if act else None


def coach(db: Session, uid: str, today: date, when: str = "tomorrow") -> Dict[str, Any]:
    atts = _attempts(db, uid, today)
    stats = C.pattern_stats([_arow(a) for a in atts], today)
    mastery = [_mrow(m) for m in db.query(DsaMastery).filter(DsaMastery.user_id == uid).all()]
    seen = {m["key"] for m in mastery}
    plan_day = today if when == "today" else today + timedelta(days=1)
    plan_minutes = 60
    p = S._plan(db, uid)
    if p and p.daily_minutes:
        plan_minutes = int(p.daily_minutes)
    plan = C.plan_tomorrow(stats, mastery, seen, plan_day, _roadmap_pattern(db, uid), plan_minutes)
    weak = C.weakest_patterns(stats)
    due = C.due_items(mastery, today)
    counts = {s: sum(1 for m in mastery if m["state"] == s) for s in C.STATES}
    mist: Dict[str, int] = {}
    for a in atts:
        for t in a.mistakes or []:
            mist[t] = mist.get(t, 0) + 1
    recall = [a for a in atts if a.recall_correct is not None]
    return dict(
        today=today.isoformat(),
        plan=plan,
        patterns=[stats[p] for p in C.PATTERN_ORDER],
        weakest=[dict(pattern=s["pattern"], name=s["name"], weakness=s["weakness"], top_mistakes=s["top_mistakes"]) for s in weak[:3]],
        due=[mastery_view(m, today) for m in due[:10]],
        due_count=len(due),
        mastery_counts=counts,
        resolve=C.resolve_stats([_arow(a) for a in atts]),
        recall=dict(tried=len(recall), correct=sum(1 for a in recall if a.recall_correct), rate=round(100 * sum(1 for a in recall if a.recall_correct) / len(recall)) if recall else None),
        mistakes=[dict(tag=k, label=C.MISTAKE_LABEL[k], count=v) for k, v in sorted(mist.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
        streak=_streak(db, uid, today),
        recent=[attempt_view(a) for a in atts[:15]],
        reminders=streak_settings(db, uid),
        options=dict(results=list(C.RESULTS), mistakes=[dict(id=m, label=C.MISTAKE_LABEL[m]) for m in C.MISTAKES],
                     patterns=[dict(id=k, label=v) for k, v in C.PATTERNS.items()], platforms=list(C.PLATFORMS), difficulties=list(C.DIFFICULTIES)),
    )


# ---------------------------------------------------------------- opt-in streak reminders
KIND = "dsa_streak"


def _prefs(db: Session, uid: str) -> Dict[str, Any]:
    u = db.query(User).filter(User.id == uid).first()
    return dict(((u.preferences or {}).get("dsa_streak") or {})) if u else {}


def streak_settings(db: Session, uid: str) -> Dict[str, Any]:
    p = _prefs(db, uid)
    return dict(enabled=bool(p.get("enabled")), times=p.get("times") or list(C.DEFAULT_TIMES), quiet_start=p.get("quiet_start") or C.DEFAULT_QUIET[0],
                quiet_end=p.get("quiet_end") or C.DEFAULT_QUIET[1], max_per_day=C.MAX_PER_DAY,
                note="Off by default. Reminders only go out on days you have not logged a problem, never more than 3 a day, never during quiet hours.")


def set_streak_settings(db: Session, uid: str, enabled: Optional[bool], times: Optional[List[str]], quiet_start: Optional[str], quiet_end: Optional[str]) -> Dict[str, Any]:
    import re
    import reminders as RM
    hhmm = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    cur = streak_settings(db, uid)
    if times is not None:
        times = sorted(set(times))
        if not (1 <= len(times) <= C.MAX_PER_DAY) or not all(hhmm.match(t) for t in times):
            raise CoachError(422, f"Give 1 to {C.MAX_PER_DAY} times as HH:MM")
    for q in (quiet_start, quiet_end):
        if q is not None and not hhmm.match(q):
            raise CoachError(422, "Quiet hours must be HH:MM")
    new = dict(enabled=cur["enabled"] if enabled is None else bool(enabled), times=times or cur["times"],
               quiet_start=quiet_start or cur["quiet_start"], quiet_end=quiet_end or cur["quiet_end"])
    u = db.query(User).filter(User.id == uid).first()
    prefs = dict(u.preferences or {})
    prefs["dsa_streak"] = new
    u.preferences = prefs
    for r in db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == KIND, Reminder.status == "pending").all():
        r.status = "cancelled"
    db.commit()
    if new["enabled"]:
        fn, now = RM.offset_fn(db, uid), datetime.utcnow()
        now_local = RM.to_local(now, fn(now))
        for slot, t in enumerate(new["times"]):
            h, m = [int(x) for x in t.split(":")]
            at_local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            if at_local <= now_local:
                at_local += timedelta(days=1)
            RM.create(db, uid, f"{KIND}:{slot}", RM.local_to_utc(at_local, fn, fn(now)), repeat="daily", kind=KIND, source="settings")
    return streak_settings(db, uid)


def streak_nudge(db: Session, uid: str, slot: int, local_old: datetime) -> Optional[Dict[str, Any]]:
    """Called by the scheduler for one due dsa_streak reminder. `local_old` is the scheduled LOCAL time. Returns what to send or None.
    Re-checks the opt-in, so turning reminders off always wins, even for a row that was already due."""
    s = streak_settings(db, uid)
    if not s["enabled"]:
        return None
    day = local_old.date()
    sent = db.query(Notification.id).filter(Notification.user_id == uid, Notification.kind == KIND,
                                            Notification.idempotency_key.like(f"{KIND}:{uid}:{day.isoformat()}:%")).count()
    return C.nudge(streak=_streak(db, uid, day), slot=slot, sent_today=sent, local_hhmm=local_old.strftime("%H:%M"),
                   quiet=(s["quiet_start"], s["quiet_end"]), max_per_day=s["max_per_day"])
