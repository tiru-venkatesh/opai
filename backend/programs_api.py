"""Programs & Challenges: open-source programs, hackathons, startup competitions, fellowships, company and research
programs, government internships and online challenges, tracked as dated CYCLES.

Rules enforced in code:
  * Status (Open / Opens soon / Active / Closed ...) is shown only for dates confirmed against the organizer's own domain
    and re-checked within 14 days. Otherwise: 'Verify current cycle' or 'Not announced'.
  * Third-party pages can help discover a program but never make its dates trusted.
  * Editing confirmed dates without re-confirming drops the trust (a stale edit cannot look official).
  * OPAI never registers or submits for the user. 'Submitted' needs the user's explicit confirmation.
  * Planning creates at most 3 real tasks per cycle, idempotently, so Today is never flooded."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import programs_logic as L
from audit.logger import record as audit
from database import Program, ProgramCycle, Task, User, get_db

router = APIRouter(prefix="/v1/opp/programs", tags=["programs"])

PARTICIPATION = ["Interested", "Planned", "Preparing", "Submitted", "Participating", "Selected", "Not selected", "Completed", "Withdrawn"]
LIVE = ("Open", "Opens soon", "Active", "Upcoming")


def _user(db: Session, uid: str) -> User:
    u = db.query(User).filter(User.id == str(uid)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _prog(db: Session, uid: str, pid: str) -> Program:
    p = db.query(Program).filter(Program.id == pid, Program.user_id == uid).first()
    if not p:
        raise HTTPException(404, "Program not found")
    return p


def _cyc(db: Session, uid: str, cid: str):
    c = db.query(ProgramCycle).filter(ProgramCycle.id == cid, ProgramCycle.user_id == uid).first()
    if not c:
        raise HTTPException(404, "Cycle not found")
    return c, db.query(Program).filter(Program.id == c.program_id).first()


def _skills(u: User) -> List[str]:
    try:
        from opportunities_api import _profile_view
        return [str(s) for s in (_profile_view(u)["profile"].get("skills") or [])]
    except Exception:
        return [s.strip() for s in (u.skills or "").split(",") if s.strip()]


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _next_step(p: Program, c: ProgramCycle, st: Dict[str, Any], today: date) -> str:
    s = st["status"]
    if s == "Not announced":
        return "Prepare your profile and explore past projects while you wait for the announcement."
    if s == "Verify current cycle":
        return {"startup_competition": "Check rules, student eligibility, team requirements, and the deadline on the official page.",
                "open_source_event": "Choose a challenge and review its requirements on the official page.",
                "open_source_program": "Check this year's timeline and eligibility on the official page, then shortlist organizations.",
                "fellowship": "Check the current cohort, eligibility and deadline on the official page."}.get(p.program_type,
                "Open the official page and confirm the dates and eligibility.")
    if s in ("Closed", "Ended"):
        return "This cycle is over. Watch the official page for the next one."
    dl = L.days_to(c, today)
    if s == "Open":
        return (f"Closes in {c.deadline and (c.deadline - today).days} day(s). Finish preparing, then submit on the official site yourself."
                if c.deadline and (c.deadline - today).days <= 7 else "Add preparation tasks, then apply on the official site yourself.")
    if s in ("Opens soon", "Upcoming"):
        return f"Prepare your materials before it opens{(' on ' + _iso(c.applications_open or c.event_start)) if (c.applications_open or c.event_start) else ''}."
    if s == "Active":
        return "Take part and log your progress here."
    return "Open the official page."


def cycle_view(db: Session, p: Program, c: ProgramCycle, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    st = L.cycle_status(c, today)
    open_tasks = db.query(Task).filter(Task.user_id == c.user_id, Task.status != "done", Task.source_ref.like(f"program_cycle:{c.id}:%")).count()
    return {"id": c.id, "label": c.label, "year": c.year, "status": st["status"], "status_why": st["why"], "confirmed": st["confirmed"],
            "needs_reverify": st["needs_reverify"], "days_to_next_date": L.days_to(c, today) if st["confirmed"] else None,
            "applications_open": _iso(c.applications_open), "deadline": _iso(c.deadline), "event_start": _iso(c.event_start), "event_end": _iso(c.event_end),
            "eligibility": c.eligibility or "Check official rules", "eligibility_known": bool(c.eligibility),
            "stages": c.stages or [], "requirements": c.requirements or [], "team_min": c.team_min, "team_max": c.team_max,
            "time_commitment": c.time_commitment, "reward": c.reward,
            "source": {"url": c.source_url, "checked_at": _iso(c.source_checked_at), "verification": c.verification,
                       "last_checked": c.source_checked_at.date().isoformat() if c.source_checked_at else "Not checked yet"},
            "needs_review": c.needs_review or [], "participation": c.participation, "history": c.history or [], "open_prep_tasks": open_tasks}


def _current_cycle(db: Session, p: Program) -> Optional[ProgramCycle]:
    """The most recent edition by year (a cycle with no year sorts last)."""
    rows = db.query(ProgramCycle).filter(ProgramCycle.program_id == p.id).all()
    return sorted(rows, key=lambda r: (r.year if r.year is not None else 9999, r.created_at or datetime.min))[-1] if rows else None


def program_view(db: Session, p: Program, skills: List[str], today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    c = _current_cycle(db, p)
    cv = cycle_view(db, p, c, today) if c else None
    st = L.cycle_status(c, today) if c else {"status": "Verify current cycle", "confirmed": False, "needs_reverify": False, "why": ""}
    fit = L.fit_for(p, skills)
    nxt = None
    if c and cv["status"] in ("Closed", "Ended"):          # never show an old edition as current: pair it with the next cycle
        nxt = {"label": "Next announced cycle", "status": "Not announced", "next_step": "Prepare your profile and explore past projects while you wait.",
               "can_add": True}
    return {"id": p.id, "name": p.name, "organizer": p.organizer, "type": p.program_type, "type_label": L.TYPES.get(p.program_type, {}).get("label", p.program_type),
            "group": L.TYPES.get(p.program_type, {}).get("group"), "recurrence": p.recurrence, "official_url": p.official_url, "from_catalog": bool(p.catalog_id),
            "cycle": cv, "next_cycle": nxt, "fit": fit, "next_step": _next_step(p, c, st, today) if c else "Add a cycle.", "dismissed": p.status == "dismissed",
            "notes": p.notes}


# ---------------------------------------------------------------- catalog
@router.get("/types")
def types():
    return {"types": [{"key": k, **v} for k, v in L.TYPES.items()], "participation": PARTICIPATION}


@router.get("/catalog")
def catalog(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    have = {p.catalog_id for p in db.query(Program).filter(Program.user_id == u.id).all() if p.catalog_id}
    skills = _skills(u)
    items = []
    for c in L.CATALOG:
        fake = type("P", (), {"focus_tags": c["focus_tags"]})()
        items.append({"id": c["id"], "name": c["name"], "organizer": c["organizer"], "type": c["program_type"], "type_label": L.TYPES[c["program_type"]]["label"],
                      "official_url": c["official_url"], "blurb": c["blurb"], "already_added": c["id"] in have, "fit": L.fit_for(fake, skills),
                      "status": "Verify current cycle"})
    return {"items": items, "note": "Starter list for discovery only. It contains no dates. Add a program, then confirm its current cycle on the organizer's official page."}


class AddProgram(BaseModel):
    user_id: str
    catalog_id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=120)
    organizer: Optional[str] = Field(default=None, max_length=120)
    program_type: Optional[str] = None
    official_url: Optional[str] = Field(default=None, max_length=500)
    recurrence: str = "annual"
    focus_tags: List[str] = []
    notes: Optional[str] = Field(default=None, max_length=1000)


@router.post("")
def add_program(p: AddProgram, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if p.catalog_id:
        cat = L.CATALOG_BY_ID.get(p.catalog_id)
        if not cat:
            raise HTTPException(404, "Unknown catalog entry")
        vals = dict(name=cat["name"], organizer=cat["organizer"], program_type=cat["program_type"], official_url=cat["official_url"],
                    recurrence=cat["recurrence"], focus_tags=cat["focus_tags"], catalog_id=cat["id"])
    else:
        if not p.name or not p.program_type:
            raise HTTPException(422, "name and program_type are required")
        if p.program_type not in L.TYPES:
            raise HTTPException(422, "Unknown program type")
        if not p.official_url or not p.official_url.lower().startswith("https://") or not L.host_of(p.official_url):
            raise HTTPException(422, "Give the organizer's official https:// page. Without it nothing about this program can be verified.")
        vals = dict(name=p.name.strip(), organizer=p.organizer, program_type=p.program_type, official_url=p.official_url.strip(),
                    recurrence=p.recurrence if p.recurrence in ("annual", "recurring", "one_off") else "annual",
                    focus_tags=[t.strip().lower() for t in p.focus_tags if t.strip()][:12])
    existing = db.query(Program).filter(Program.user_id == u.id, Program.name == vals["name"]).first()
    if existing:
        if existing.status == "dismissed":
            existing.status = "tracking"; db.commit()
        out = program_view(db, existing, _skills(u)); out["duplicate"] = True
        return out
    pr = Program(user_id=u.id, notes=p.notes, **vals)
    db.add(pr); db.flush()
    db.add(ProgramCycle(user_id=u.id, program_id=pr.id, label=str(date.today().year), year=date.today().year, announced=None))
    db.commit(); db.refresh(pr)
    audit(db, u.id, "programs.add", {"program_id": pr.id, "catalog_id": pr.catalog_id}, {"name": pr.name}, "low")
    return program_view(db, pr, _skills(u))


@router.get("")
def list_programs(user_id: str, type: Optional[str] = None, group: Optional[str] = None, relevant_only: bool = False, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    skills = _skills(u)
    rows = db.query(Program).filter(Program.user_id == u.id).order_by(Program.created_at.desc()).all()
    out = []
    for p in rows:
        if p.status == "dismissed" and relevant_only:
            continue
        v = program_view(db, p, skills)
        if type and v["type"] != type:
            continue
        if group and v["group"] != group:
            continue
        if relevant_only and (v["dismissed"] or v["cycle"]["status"] in ("Closed", "Ended")):
            continue
        out.append(v)
    order = {"Open": 0, "Active": 1, "Opens soon": 2, "Upcoming": 3, "Verify current cycle": 4, "Not announced": 5, "Closed": 6, "Ended": 6}
    out.sort(key=lambda v: (v["dismissed"], order.get(v["cycle"]["status"], 9), v["cycle"]["days_to_next_date"] if v["cycle"]["days_to_next_date"] is not None else 999))
    return {"items": out, "groups": sorted({v["group"] for v in out if v["group"]}),
            "note": "Status appears only for dates confirmed on the organizer's own page. Everything else says Verify or Not announced."}


# ---------------------------------------------------------------- parse / confirm
class ParseBody(BaseModel):
    user_id: str
    text: str = Field(min_length=10, max_length=20000)


@router.post("/parse")
def parse(p: ParseBody, db: Session = Depends(get_db)):
    _user(db, p.user_id)
    return L.parse_program_text(p.text)


class CycleUpdate(BaseModel):
    user_id: str
    label: Optional[str] = Field(default=None, max_length=60)
    announced: Optional[bool] = None
    applications_open: Optional[date] = None
    deadline: Optional[date] = None
    event_start: Optional[date] = None
    event_end: Optional[date] = None
    eligibility: Optional[str] = Field(default=None, max_length=1500)
    stages: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    team_min: Optional[int] = Field(default=None, ge=1, le=100)
    team_max: Optional[int] = Field(default=None, ge=1, le=100)
    time_commitment: Optional[str] = Field(default=None, max_length=120)
    reward: Optional[str] = Field(default=None, max_length=200)
    source_url: Optional[str] = Field(default=None, max_length=500)
    checked_official_page: bool = False        # the user attests they read these details on the organizer's page
    notes: Optional[str] = Field(default=None, max_length=1000)


FACT_FIELDS = ("applications_open", "deadline", "event_start", "event_end", "eligibility", "stages", "requirements", "team_min", "team_max", "time_commitment", "reward")


@router.put("/cycles/{cycle_id}")
def update_cycle(cycle_id: str, p: CycleUpdate, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    c, prog = _cyc(db, u.id, cycle_id)
    data = p.model_dump(exclude_unset=True)
    new = {k: data[k] for k in FACT_FIELDS if k in data}
    ao, dl = new.get("applications_open", c.applications_open), new.get("deadline", c.deadline)
    es, ee = new.get("event_start", c.event_start), new.get("event_end", c.event_end)
    if ao and dl and dl < ao:
        raise HTTPException(422, "The deadline is before the opening date.")
    if es and ee and ee < es:
        raise HTTPException(422, "The event ends before it starts.")
    tmin, tmax = new.get("team_min", c.team_min), new.get("team_max", c.team_max)
    if tmin and tmax and tmax < tmin:
        raise HTTPException(422, "Maximum team size is below the minimum.")
    changed = any(getattr(c, k) != v for k, v in new.items())
    for k, v in new.items():
        setattr(c, k, v)
    for k in ("label", "notes"):
        if k in data and data[k] is not None:
            setattr(c, k, data[k])
    if "label" in data and data["label"]:
        import re
        m = re.search(r"20\d\d", data["label"])
        c.year = int(m[0]) if m else c.year
    if "announced" in data:
        c.announced = data["announced"]
    note = None
    if p.source_url:
        official = L.is_official_source(prog, p.source_url)
        if p.checked_official_page and official:
            c.verification, c.source_url, c.source_checked_at = "official", p.source_url.strip(), datetime.utcnow()
            c.needs_review = []
            if c.announced is False:
                c.announced = True
        elif p.checked_official_page and not official:
            c.verification, c.source_url, c.source_checked_at = "third_party", p.source_url.strip(), None
            note = "That page is not on the organizer's own domain, so these dates are NOT trusted. Open the official page and confirm there."
        else:
            c.source_url = p.source_url.strip()
    elif changed and c.verification == "official":
        c.verification, c.source_checked_at = "unverified", None       # an unconfirmed edit must not keep an 'official' badge
        note = "You changed confirmed details without re-confirming them on the official page, so the status went back to 'Verify current cycle'."
    elif changed and c.verification != "official":
        c.verification = "unverified"
    db.commit(); db.refresh(c)
    audit(db, u.id, "programs.cycle_update", {"cycle_id": c.id}, {"verification": c.verification}, "low")
    out = cycle_view(db, prog, c)
    if note:
        out["note"] = note
    return out


class NewCycle(BaseModel):
    user_id: str
    label: str = Field(min_length=1, max_length=60)
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    announced: Optional[bool] = None


@router.post("/{program_id}/cycles")
def add_cycle(program_id: str, p: NewCycle, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    prog = _prog(db, u.id, program_id)
    c = ProgramCycle(user_id=u.id, program_id=prog.id, label=p.label.strip(), year=p.year, announced=p.announced)
    if c.year is None:
        import re
        m = re.search(r"20\d\d", p.label)
        c.year = int(m[0]) if m else (date.today().year + 1)
    db.add(c); db.commit(); db.refresh(c)
    return cycle_view(db, prog, c)


# ---------------------------------------------------------------- plan / participation
@router.post("/cycles/{cycle_id}/plan")
def plan(cycle_id: str, user_id: str, db: Session = Depends(get_db)):
    """Add to my plan: a few real, dated preparation tasks (they appear in Today). Idempotent."""
    u = _user(db, user_id)
    c, prog = _cyc(db, u.id, cycle_id)
    st = L.cycle_status(c)
    if st["status"] in ("Closed", "Ended"):
        raise HTTPException(409, "This cycle is over. Add the next cycle when the organizer announces it.")
    created, existing = [], []
    for t in L.plan_tasks(prog, c, st):
        ref = f"program_cycle:{c.id}:{t['key']}"
        row = db.query(Task).filter(Task.user_id == u.id, Task.source_ref == ref).first()
        if row:
            existing.append({"id": row.id, "title": row.title, "status": row.status})
            continue
        row = Task(user_id=u.id, title=t["title"], type="program", due_date=t["due"], estimated_minutes=t["minutes"], status="todo", source_ref=ref)
        db.add(row); db.flush()
        created.append({"id": row.id, "title": row.title, "minutes": t["minutes"], "due": t["due"].isoformat()})
    if c.participation == "Interested":
        _log(c, "Interested", "Planned", "Added preparation tasks")
        c.participation = "Planned"
    db.commit()
    audit(db, u.id, "programs.plan", {"cycle_id": c.id}, {"created": len(created)}, "low")
    return {"created": created, "already_planned": existing, "status": st["status"],
            "note": "Tasks are in your Today list. OPAI never registers or submits for you."}


def _log(c: ProgramCycle, frm: str, to: str, note: str = ""):
    c.history = list(c.history or []) + [{"at": datetime.utcnow().isoformat(), "from": frm, "to": to, "note": note or None}]


class Participation(BaseModel):
    user_id: str
    status: str
    note: Optional[str] = Field(default=None, max_length=500)
    user_confirms_submitted: bool = False


@router.post("/cycles/{cycle_id}/participation")
def participation(cycle_id: str, p: Participation, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    c, prog = _cyc(db, u.id, cycle_id)
    if p.status not in PARTICIPATION:
        raise HTTPException(422, "Unknown participation status")
    if p.status in ("Submitted", "Participating") and not p.user_confirms_submitted:
        raise HTTPException(409, "Only you can confirm you registered or submitted on the official site. Set user_confirms_submitted once you have.")
    if p.status == c.participation:
        return cycle_view(db, prog, c)
    _log(c, c.participation, p.status, p.note or "")
    c.participation = p.status
    db.commit(); db.refresh(c)
    audit(db, u.id, "programs.participation", {"cycle_id": c.id}, {"to": p.status}, "low")
    return cycle_view(db, prog, c)


@router.post("/{program_id}/dismiss")
def dismiss(program_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    pr = _prog(db, u.id, program_id)
    pr.status = "dismissed"; db.commit()
    return {"id": pr.id, "status": "dismissed"}


@router.delete("/{program_id}")
def delete_program(program_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    pr = _prog(db, u.id, program_id)
    ids = [c.id for c in db.query(ProgramCycle).filter(ProgramCycle.program_id == pr.id).all()]
    for cid in ids:      # their unfinished prep tasks go with them; completed ones stay as history
        db.query(Task).filter(Task.user_id == u.id, Task.status != "done", Task.source_ref.like(f"program_cycle:{cid}:%")).delete(synchronize_session=False)
    db.delete(pr); db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------- summary (hub + Today)
def programs_summary(db: Session, u: User) -> Dict[str, Any]:
    skills = _skills(u)
    live, verify, nxt = 0, 0, None
    for p in db.query(Program).filter(Program.user_id == u.id, Program.status != "dismissed").all():
        v = program_view(db, p, skills)
        s = v["cycle"]["status"]
        if s in ("Open", "Opens soon", "Active"):
            live += 1
            if nxt is None or (v["cycle"]["days_to_next_date"] or 999) < (nxt["days"] or 999):
                nxt = {"text": f"{v['name']} ({s.lower()}): {v['next_step']}", "days": v["cycle"]["days_to_next_date"], "link": "opportunities.html#programs"}
        elif s == "Verify current cycle":
            verify += 1
    return {"programs_live": live, "programs_to_verify": verify, "program_next_action": nxt}
