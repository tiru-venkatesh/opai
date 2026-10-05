import os
from dotenv import load_dotenv
load_dotenv()  # reads backend/.env if present, before any os.environ.get() calls below
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import (
    init_db, get_db, User, Task, Academic, Contact, DocumentChunk, Resume,
    UserMemory, Application, OutreachHistory, Project, Opportunity, DailyPlan,
    ClientRequest, OutboxItem, MemoryItem, AgentActivityLog,
    Semester, Course, Topic, Exam, StudyBlock,
)
from schemas import (
    DailyPlanResponse, OpportunityMatchList, ProfessorOutreachDraft,
    JarvisChatRequest, JarvisChatResponse,
    ApplicationCreate, ApplicationUpdate, ApplicationOut,
    TaskCreate, TaskUpdate, TaskOut,
    AcademicCreate, AcademicUpdate, AcademicOut,
    ContactCreate, ContactUpdate, ContactOut,
    ResumeCreate, ResumeOut, ResumeReanalyzeRequest, ResumeUpdate, ResumeAskRequest, ResumeAskResponse,
    MemoryOut, MemoryUpdate, MemoryItemCreate, MemoryItemOut, MemoryItemConfirm,
    ReflectionRequest, ReflectionResponse,
    ProjectCreate, ProjectUpdate, ProjectOut,
    OpportunityCreate, OpportunityOut, OpportunityIntelOut,
    HistorySummary, MemorySummarizeResponse,
    ProfileOut, ProfileUpdate,
    ClientRequestCreate, ClientRequestUpdate, ClientRequestOut,
    OutboxCreate, OutboxOut, ActivityLogOut,
    AgentPermissionsOut, AgentPermissionsUpdate,
    SemesterCreate, SemesterOut, CourseCreate, CourseOut,
    TopicCreate, TopicUpdate, TopicOut,
    ExamCreate, ExamOut, ExamRiskOut,
    StudyBlockOut, StudyPlanGenerateRequest, StudyBlockComplete,
    CourseCsvPreviewOut, CourseCsvConfirm,
)
from agent_service import (
    workflow_generate_plan, workflow_match_opportunities,
    workflow_draft_outreach, process_jarvis_message, get_embedding,
    create_resume, reanalyze_resume, update_resume, ask_resume, delete_resume,
    generate_reflection, summarize_recent_activity,
    MAX_TOOL_CALLS_PER_TURN,
    compute_exam_risk, generate_study_plan as sems_generate_study_plan,
    complete_study_block as sems_complete_study_block, parse_course_csv,
)

import rag_service as rag

app = FastAPI(title="OPAI Agent Core API", version="1.1.0")
from pdf_timetable import router as pdf_timetable_router
app.include_router(pdf_timetable_router)
from attach import router as attach_router
app.include_router(attach_router)
from today_api import router as today_router
app.include_router(today_router)
from rag_api import router as rag_router
app.include_router(rag_router)
from dsa_api import router as dsa_router
app.include_router(dsa_router)
from extras_api import router as extras_router
app.include_router(extras_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    init_db()


@app.exception_handler(RuntimeError)
def groq_not_configured_handler(request: Request, exc: RuntimeError):
    # get_groq_client() raises RuntimeError with a clear message when
    # GROQ_API_KEY is missing - surface that as a proper 503 instead of a
    # raw 500 + traceback, since it's a config problem, not a bug.
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _friendly_error(exc: Exception):
    """Map provider/DB failures to (status, message, retry_after); None for genuine bugs.
    Raw Groq/SQLAlchemy text can leak hosts and usernames, so it is never echoed."""
    name, mod = type(exc).__name__, (type(exc).__module__ or "")
    if mod.startswith("groq"):
        if name == "RateLimitError":
            return 429, "The AI service is rate-limited right now. Wait a minute and try again.", 30
        if name in ("AuthenticationError", "PermissionDeniedError"):
            return 502, "The AI service rejected the server's API key. Check GROQ_API_KEY on the backend.", None
        if name in ("APIConnectionError", "APITimeoutError"):
            return 503, "Could not reach the AI service. Try again shortly.", 5
        return 502, "The AI service returned an error. Try again.", 5
    if mod.startswith("sqlalchemy") and name in ("OperationalError", "InterfaceError", "DBAPIError", "TimeoutError"):
        return 503, "The database is temporarily unavailable. Try again shortly.", 5
    return None


@app.exception_handler(Exception)
def unhandled_error_handler(request: Request, exc: Exception):
    # Unhandled errors bypass CORSMiddleware, so add the CORS header here; otherwise the
    # browser reports a misleading "CORS blocked" instead of the real status/detail.
    import logging
    logging.getLogger("opa").exception("Unhandled error on %s %s", request.method, request.url.path)
    headers = {"Access-Control-Allow-Origin": request.headers.get("origin", "*")}
    friendly = _friendly_error(exc)
    if friendly:
        status, message, retry = friendly
        if retry:
            headers["Retry-After"] = str(retry)
        return JSONResponse(status_code=status, content={"detail": message}, headers=headers)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"}, headers=headers)


@app.get("/v1/health")
def health(db: Session = Depends(get_db)):
    """Open this URL in a browser to see why list endpoints 500.
    Returns no row contents and no secrets: dialect, counts, per-table errors."""
    from sqlalchemy import inspect as _inspect
    from database import engine as _engine
    dialect = _engine.dialect.name
    out = {
        "ok": True,
        "db": dialect,
        "db_persistent": dialect != "sqlite",
        "groq_key_set": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "tables": {},
    }
    if dialect == "sqlite":
        out["warning"] = "DATABASE_URL is not set: SQLite on Render is wiped on every deploy/restart. Data and guest users will disappear."
    try:
        cols = {t: [c["name"] for c in _inspect(_engine).get_columns(t)] for t in ("projects", "academics", "users")}
    except Exception as e:
        cols = {}
        out["ok"] = False
        out["inspect_error"] = f"{type(e).__name__}: {e}"
    checks = {"users": (User, None), "projects": (Project, ProjectOut), "academics": (Academic, AcademicOut)}
    for name, (model, schema) in checks.items():
        info = {"columns": cols.get(name)}
        try:
            info["count"] = db.query(model).count()
            if schema is not None:
                rows = db.query(model).limit(50).all()
                bad = 0
                first_err = None
                for r in rows:
                    try:
                        schema.model_validate(r)
                    except Exception as e:
                        bad += 1
                        first_err = first_err or f"{type(e).__name__}: {str(e)[:300]}"
                info["rows_failing_schema"] = bad
                if first_err:
                    info["first_schema_error"] = first_err
                    out["ok"] = False
        except Exception as e:
            db.rollback()
            info["error"] = f"{type(e).__name__}: {str(e)[:400]}"
            out["ok"] = False
        out["tables"][name] = info
    return out


@app.get("/sw.js")
def service_worker():
    # served from the site root so the worker's scope covers the whole app
    if os.path.exists("static/sw.js"):
        return FileResponse("static/sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="sw.js not found")


@app.get("/manifest.json")
def web_manifest():
    if os.path.exists("static/manifest.json"):
        return FileResponse("static/manifest.json", media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="manifest.json not found")



# Pages like /super-chat and /karna load their assets with relative URLs
# (e.g. "opai-shell.js"), which resolve to the site root, not /static/.
# Serve those shared assets from the root so they stop 404-ing.
_ROOT_ASSETS = {
    "opai-shell.js": "application/javascript",
    "guide.js": "application/javascript",
    "attach.js": "application/javascript",
    "fx.js": "application/javascript",
    "opai-shared.css": "text/css",
    "opai-glass.css": "text/css",
    "attach.css": "text/css",
    "fx.css": "text/css",
}


def _register_root_asset(name: str, media: str):
    def _serve():
        path = os.path.join("static", name)
        if os.path.exists(path):
            return FileResponse(path, media_type=media)
        raise HTTPException(status_code=404, detail=name + " not found")
    app.add_api_route("/" + name, _serve, methods=["GET"], include_in_schema=False)


for _n, _m in _ROOT_ASSETS.items():
    _register_root_asset(_n, _m)


@app.get("/super-chat")
def serve_super_chat():
    if os.path.exists("static/super-chat.html"):
        return FileResponse("static/super-chat.html")
    raise HTTPException(status_code=404, detail="super-chat.html not found")


@app.get("/karna")
def serve_karna():
    return serve_super_chat()


@app.get("/")
def serve_ui():
    # The structured frontend uses app.html as the canonical application shell.
    if os.path.exists("static/app.html"):
        return FileResponse("static/app.html")
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "OPAI API is running. Visit /docs for Swagger."}


# ================= AUTH (DEV) =================
@app.post("/v1/auth/dev-login")
def dev_login(email: str = "student@university.edu", name: str = None, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Dev-login must create an empty, owned workspace. Never inject a
        # fictional profile, CGPA, targets, tasks, or academic data.
        user = User(
            email=email,
            name=name or "User",
            branch=None,
            degree=None,
            cgpa=None,
            targets={},
            preferences={},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif name and user.name in {"User", "Guest"}:
        user.name = name
        db.commit()
        db.refresh(user)
    return {"user_id": str(user.id), "name": user.name, "email": user.email}


@app.post("/v1/auth/guest")
def guest_login(db: Session = Depends(get_db)):
    """Every guest gets a brand-new, isolated user record.
    (Previously all guests logged in as the same hardcoded email, so they
    shared one account and saw each other's data.)"""
    import uuid as _uuid
    token = _uuid.uuid4().hex[:12]
    user = User(
        email=f"guest-{token}@opa.local",
        name="Guest",
        branch="",
        degree="",
        targets={},
        preferences={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": str(user.id), "name": user.name, "email": user.email, "guest": True}


# ================= PROFILE =================
@app.get("/v1/profile", response_model=ProfileOut)
def get_profile(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == str(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/v1/profile", response_model=ProfileOut)
def update_profile(user_id: UUID, payload: ProfileUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == str(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    rag.safe(rag.index_profile, db, user)
    return user


# ================= WORKFLOW A: DAILY PLANNING =================
@app.get("/v1/plan/today", response_model=DailyPlanResponse)
def get_today_plan(user_id: UUID, db: Session = Depends(get_db)):
    return workflow_generate_plan(user_id, date.today(), db)


@app.post("/v1/plan/generate", response_model=DailyPlanResponse)
def generate_plan_for_date(user_id: UUID, target_date: date, db: Session = Depends(get_db)):
    return workflow_generate_plan(user_id, target_date, db)


@app.post("/v1/plan/reflect", response_model=ReflectionResponse)
def reflect_on_plan(payload: ReflectionRequest, db: Session = Depends(get_db)):
    try:
        return generate_reflection(payload.user_id, payload.plan_date, payload.actual_completed, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================= APPLICATIONS CRUD =================
@app.get("/v1/applications", response_model=List[ApplicationOut])
def list_applications(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(Application).filter(Application.user_id == str(user_id)).all()


@app.post("/v1/applications", response_model=ApplicationOut)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    row = Application(
        user_id=str(payload.user_id),
        company=payload.company,
        role=payload.role,
        type=payload.type,
        deadline=payload.deadline,
        link=payload.link,
        notes=payload.notes,
        effort_minutes=payload.effort_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_application, db, row)
    return row


@app.patch("/v1/applications/{application_id}", response_model=ApplicationOut)
def update_application(application_id: UUID, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    row = db.query(Application).filter(Application.id == str(application_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_application, db, row)
    return row


@app.delete("/v1/applications/{application_id}")
def delete_application(application_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Application).filter(Application.id == str(application_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    uid = row.user_id
    db.delete(row)
    db.commit()
    rag.safe(rag.delete_source, db, uid, rag.COVER_LETTER, str(application_id))
    return {"status": "deleted"}


@app.post("/v1/applications/{application_id}/mark-applied", response_model=ApplicationOut)
def mark_application_applied(application_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Application).filter(Application.id == str(application_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    row.status = "Applied"
    row.follow_up_date = date.today() + timedelta(days=10)
    db.commit()
    db.refresh(row)
    return row


@app.get("/v1/applications/follow-ups", response_model=List[ApplicationOut])
def list_application_follow_ups(user_id: UUID, db: Session = Depends(get_db)):
    today = date.today()
    return db.query(Application).filter(
        Application.user_id == str(user_id),
        Application.status == "Applied",
        Application.follow_up_date.isnot(None),
        Application.follow_up_date <= today,
    ).all()


# ================= PROJECTS CRUD =================
@app.get("/v1/projects", response_model=List[ProjectOut])
def list_projects(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(Project).filter(Project.user_id == str(user_id)).all()


@app.post("/v1/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    row = Project(
        user_id=str(payload.user_id),
        title=payload.title,
        description=payload.description,
        tech_stack=payload.tech_stack,
        github_link=payload.github_link,
        status=payload.status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_project, db, row)
    return row


@app.patch("/v1/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: UUID, payload: ProjectUpdate, db: Session = Depends(get_db)):
    row = db.query(Project).filter(Project.id == str(project_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_project, db, row)
    return row


@app.delete("/v1/projects/{project_id}")
def delete_project(project_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Project).filter(Project.id == str(project_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    uid = row.user_id
    db.delete(row)
    db.commit()
    rag.safe(rag.delete_source, db, uid, rag.PROJECT, str(project_id))
    return {"status": "deleted"}


@app.post("/v1/projects/{project_id}/tasks", response_model=TaskOut)
def create_project_task(project_id: UUID, payload: TaskCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == str(project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    row = Task(
        user_id=str(payload.user_id),
        project_id=str(project_id),
        title=payload.title,
        type="project",
        due_date=payload.due_date,
        estimated_minutes=payload.estimated_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ================= WORKFLOW B: OPPORTUNITY MATCHING =================
@app.post("/v1/applications/match", response_model=OpportunityMatchList)
def match_applications(user_id: UUID, opportunities: List[dict], db: Session = Depends(get_db)):
    return workflow_match_opportunities(user_id, opportunities, db)


# ================= OPPORTUNITIES CRUD + LIFECYCLE =================
@app.get("/v1/opportunities", response_model=List[OpportunityOut])
def list_opportunities(db: Session = Depends(get_db)):
    return db.query(Opportunity).filter(Opportunity.status == "New").all()


@app.get("/v1/opportunities/intel", response_model=List[OpportunityIntelOut])
def list_opportunities_intel(user_id: UUID, db: Session = Depends(get_db)):
    """Deterministic (no LLM call) scoring layer: skill-tag overlap, deadline
    urgency, a rough effort estimate, and a one-line suggested next action -
    cheap enough to compute on every page load."""
    user = db.query(User).filter(User.id == str(user_id)).first()
    user_skills = {s.strip().lower() for s in (user.skills or "").split(",") if s.strip()} if user else set()
    rows = db.query(Opportunity).filter(Opportunity.status == "New").all()
    out = []
    today = date.today()
    for o in rows:
        tags = {t.strip().lower() for t in (o.tags or []) if t.strip()}
        matched = sorted(tags & user_skills)
        missing = sorted(tags - user_skills)
        score = round(len(matched) / len(tags), 2) if tags else 0.5
        if not o.deadline:
            urgency = "none"
        else:
            days_left = (o.deadline - today).days
            urgency = "critical" if days_left <= 3 else "soon" if days_left <= 10 else "later"
        effort = 45 + 20 * len(missing)
        if score >= 0.8 and urgency in ("critical", "soon"):
            action = "Strong match with a close deadline - apply now."
        elif score >= 0.8:
            action = "Strong match - schedule time to apply."
        elif missing:
            action = f"Fill the gap first: {', '.join(missing[:2])}."
        else:
            action = "Review details before committing time."
        out.append(OpportunityIntelOut(
            id=o.id, title=o.title, company_or_lab=o.company_or_lab, match_score=score,
            matched_skills=matched, missing_skills=missing, deadline=o.deadline,
            deadline_urgency=urgency, estimated_effort_minutes=effort, suggested_next_action=action,
            source=o.source, link=o.link, last_verified_at=o.last_verified_at, eligibility_note=o.eligibility_note,
        ))
    out.sort(key=lambda r: (r.deadline_urgency != "critical", r.deadline_urgency != "soon", -r.match_score))
    return out


@app.post("/v1/opportunities", response_model=OpportunityOut)
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    if not payload.allow_duplicate:
        norm_title = payload.title.strip().lower()
        norm_company = payload.company_or_lab.strip().lower()
        existing = (
            db.query(Opportunity)
            .filter(Opportunity.status == "New")
            .filter(func.lower(func.trim(Opportunity.title)) == norm_title)
            .filter(func.lower(func.trim(Opportunity.company_or_lab)) == norm_company)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Looks like a duplicate of an existing opportunity ({existing.id}) - "
                       f"pass allow_duplicate=true to create it anyway.",
            )
    row = Opportunity(
        title=payload.title,
        company_or_lab=payload.company_or_lab,
        type=payload.type,
        description=payload.description,
        link=payload.link,
        source=payload.source,
        tags=payload.tags,
        deadline=payload.deadline,
        eligibility_note=payload.eligibility_note,
        last_verified_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/v1/opportunities/{opportunity_id}/convert", response_model=ApplicationOut)
def convert_opportunity(opportunity_id: UUID, user_id: UUID, db: Session = Depends(get_db)):
    opp = db.query(Opportunity).filter(Opportunity.id == str(opportunity_id)).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    application = Application(
        user_id=str(user_id),
        company=opp.company_or_lab,
        role=opp.title,
        type=opp.type,
        status="To Apply",
        link=opp.link,
        notes=opp.description,
    )
    opp.status = "Converted"
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@app.post("/v1/opportunities/{opportunity_id}/dismiss")
def dismiss_opportunity(opportunity_id: UUID, db: Session = Depends(get_db)):
    opp = db.query(Opportunity).filter(Opportunity.id == str(opportunity_id)).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp.status = "Dismissed"
    db.commit()
    return {"status": "dismissed"}


# ================= TASKS CRUD =================
@app.get("/v1/tasks", response_model=List[TaskOut])
def list_tasks(user_id: UUID, project_id: UUID = None, db: Session = Depends(get_db)):
    q = db.query(Task).filter(Task.user_id == str(user_id))
    if project_id:
        q = q.filter(Task.project_id == str(project_id))
    return q.all()


@app.post("/v1/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    row = Task(
        user_id=str(payload.user_id),
        title=payload.title,
        type=payload.type,
        due_date=payload.due_date,
        estimated_minutes=payload.estimated_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_task, db, row)
    return row


@app.patch("/v1/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: UUID, payload: TaskUpdate, db: Session = Depends(get_db)):
    row = db.query(Task).filter(Task.id == str(task_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_task, db, row)
    return row


@app.delete("/v1/tasks/{task_id}")
def delete_task(task_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Task).filter(Task.id == str(task_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    uid_t = str(row.user_id)
    db.delete(row)
    db.commit()
    rag.safe(rag.delete_source, db, uid_t, rag.TASK, str(task_id))
    return {"status": "deleted"}


# ================= ACADEMICS CRUD =================
@app.get("/v1/academics", response_model=List[AcademicOut])
def list_academics(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(Academic).filter(Academic.user_id == str(user_id)).all()


@app.post("/v1/academics", response_model=AcademicOut)
def create_academic(payload: AcademicCreate, db: Session = Depends(get_db)):
    row = Academic(
        user_id=str(payload.user_id),
        subject=payload.subject,
        task=payload.task,
        exam_date=payload.exam_date,
        priority=payload.priority,
        weak_areas=payload.weak_areas,
        effort_minutes=payload.effort_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_academic, db, row)
    return row


@app.patch("/v1/academics/{academic_id}", response_model=AcademicOut)
def update_academic(academic_id: UUID, payload: AcademicUpdate, db: Session = Depends(get_db)):
    row = db.query(Academic).filter(Academic.id == str(academic_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Academic entry not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_academic, db, row)
    return row


@app.delete("/v1/academics/{academic_id}")
def delete_academic(academic_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Academic).filter(Academic.id == str(academic_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Academic entry not found")
    uid = row.user_id
    db.delete(row)
    db.commit()
    rag.safe(rag.delete_source, db, uid, rag.ACADEMIC, str(academic_id))
    return {"status": "deleted"}


# ================= CONTACTS (PROFESSORS) =================
@app.get("/v1/contacts", response_model=List[ContactOut])
def list_professors(db: Session = Depends(get_db)):
    return db.query(Contact).all()


@app.post("/v1/contacts", response_model=ContactOut)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    vec = get_embedding(
        f"{payload.institute} {payload.lab or ''} {' '.join(payload.research_areas)} {payload.bio or ''}"
    )
    row = Contact(
        name=payload.name,
        institute=payload.institute,
        lab=payload.lab,
        research_areas=payload.research_areas,
        email=payload.email,
        bio=payload.bio,
        embedding=vec,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.patch("/v1/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: UUID, payload: ContactUpdate, db: Session = Depends(get_db)):
    row = db.query(Contact).filter(Contact.id == str(contact_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.embedding = get_embedding(
        f"{row.institute} {row.lab or ''} {' '.join(row.research_areas or [])} {row.bio or ''}"
    )
    db.commit()
    db.refresh(row)
    return row


@app.delete("/v1/contacts/{contact_id}")
def delete_contact(contact_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Contact).filter(Contact.id == str(contact_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


# ================= WORKFLOW C: OUTREACH =================
@app.get("/v1/outreach")
def list_outreach(user_id: UUID, db: Session = Depends(get_db)):
    rows = db.query(OutreachHistory).filter(OutreachHistory.user_id == str(user_id)).all()
    result = []
    for r in rows:
        contact = db.query(Contact).filter(Contact.id == r.contact_id).first()
        result.append({
            "id": r.id,
            "contact_id": r.contact_id,
            "contact_name": contact.name if contact else "Unknown",
            "subject": r.subject,
            "email_text": r.email_text,
            "status": r.status,
            "follow_up_date": str(r.follow_up_date) if r.follow_up_date else None,
        })
    return result


@app.post("/v1/drafts/outreach", response_model=ProfessorOutreachDraft)
def draft_outreach(user_id: UUID, contact_id: UUID, db: Session = Depends(get_db)):
    try:
        result = workflow_draft_outreach(user_id, contact_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    contact = db.query(Contact).filter(Contact.id == str(contact_id)).first()
    if contact and contact.status == "Not started":
        contact.status = "Drafted"
        db.commit()
    return result


@app.post("/v1/outreach/{outreach_id}/mark-sent")
def mark_outreach_sent(outreach_id: UUID, db: Session = Depends(get_db)):
    row = db.query(OutreachHistory).filter(OutreachHistory.id == str(outreach_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Outreach draft not found")
    row.status = "Sent"
    row.sent_at = datetime.utcnow()
    row.follow_up_date = date.today() + timedelta(days=7)
    contact = db.query(Contact).filter(Contact.id == row.contact_id).first()
    if contact:
        contact.status = "Sent"
        contact.sent_on = date.today()
    db.commit()
    rag.safe(rag.index_outreach, db, row, contact)
    return {"status": "marked sent", "follow_up_date": str(row.follow_up_date)}


@app.post("/v1/outreach/{outreach_id}/reject")
def reject_outreach(outreach_id: UUID, db: Session = Depends(get_db)):
    row = db.query(OutreachHistory).filter(OutreachHistory.id == str(outreach_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Outreach draft not found")
    row.status = "Rejected"
    contact = db.query(Contact).filter(Contact.id == row.contact_id).first()
    if contact and contact.status == "Drafted":
        contact.status = "Not started"
    db.commit()
    return {"status": "rejected"}


@app.get("/v1/outreach/follow-ups")
def list_outreach_follow_ups(user_id: UUID, db: Session = Depends(get_db)):
    today = date.today()
    rows = db.query(OutreachHistory).filter(
        OutreachHistory.user_id == str(user_id),
        OutreachHistory.status == "Sent",
        OutreachHistory.follow_up_date.isnot(None),
        OutreachHistory.follow_up_date <= today,
    ).all()
    return [
        {
            "id": r.id,
            "contact_id": r.contact_id,
            "subject": r.subject,
            "follow_up_date": str(r.follow_up_date),
        }
        for r in rows
    ]


# ================= CLIENT REQUESTS (freelance pipeline) =================
@app.get("/v1/requests", response_model=List[ClientRequestOut])
def list_requests(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(ClientRequest).filter(ClientRequest.user_id == str(user_id)).all()


@app.post("/v1/requests", response_model=ClientRequestOut)
def create_request(payload: ClientRequestCreate, db: Session = Depends(get_db)):
    row = ClientRequest(
        user_id=str(payload.user_id), client=payload.client, ask=payload.ask,
        scope=payload.scope, timeline=payload.timeline, price=payload.price, email=payload.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_request, db, row)
    return row


@app.patch("/v1/requests/{request_id}", response_model=ClientRequestOut)
def update_request(request_id: UUID, payload: ClientRequestUpdate, db: Session = Depends(get_db)):
    row = db.query(ClientRequest).filter(ClientRequest.id == str(request_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_request, db, row)
    return row


@app.delete("/v1/requests/{request_id}")
def delete_request(request_id: UUID, db: Session = Depends(get_db)):
    row = db.query(ClientRequest).filter(ClientRequest.id == str(request_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    uid = row.user_id
    db.delete(row)
    db.commit()
    rag.safe(rag.delete_source, db, uid, rag.REQUEST, str(request_id))
    return {"status": "deleted"}


@app.post("/v1/drafts/proposal", response_model=OutboxOut)
def draft_proposal(user_id: UUID, request_id: UUID, db: Session = Depends(get_db)):
    req = db.query(ClientRequest).filter(ClientRequest.id == str(request_id)).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    subject = f"Proposal for {req.ask or 'your project'}"
    body = (
        f"Hi,\n\nThanks for reaching out about {req.ask or 'your project'}.\n\n"
        f"Scope: {req.scope or 'to be discussed'}\n"
        f"Timeline: {req.timeline or 'TBD'}\n\n"
        f"Happy to walk through details on a quick call.\n\nBest"
    )
    item = OutboxItem(
        user_id=str(user_id), channel="email", status="pending",
        payload={"to": req.email, "subject": subject, "body": body},
        ref={"kind": "request", "id": req.id},
    )
    if req.status == "New":
        req.status = "Scoped"
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ================= OUTBOX (approval queue) =================
# Hard safety limits, enforced in code (not just a prompt): a runaway agent
# loop or a bad actor can propose as many outreach drafts as it wants, but
# only this many can be *approved and sent* per user per day.
MAX_OUTBOX_APPROVALS_PER_DAY = 20


def _classify_outbox_risk(channel: str, ref: dict) -> str:
    kind = (ref or {}).get("kind")
    if channel == "email" or kind in ("contact", "request"):
        return "high"
    return "medium"


@app.get("/v1/outbox", response_model=List[OutboxOut])
def list_outbox(user_id: UUID, db: Session = Depends(get_db)):
    rows = db.query(OutboxItem).filter(OutboxItem.user_id == str(user_id)).all()
    now = datetime.utcnow()
    changed = False
    for row in rows:
        if row.status == "pending" and row.expires_at and row.expires_at < now:
            row.status = "expired"
            changed = True
    if changed:
        db.commit()
    return rows


@app.post("/v1/outbox", response_model=OutboxOut)
def create_outbox(payload: OutboxCreate, db: Session = Depends(get_db)):
    risk = payload.risk_level or _classify_outbox_risk(payload.channel, payload.ref or {})
    row = OutboxItem(
        user_id=str(payload.user_id), channel=payload.channel,
        payload=payload.payload, ref=payload.ref or {}, note=payload.note,
        risk_level=risk, approval_scope="single_use",
        expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/v1/outbox/{outbox_id}/approve", response_model=OutboxOut)
def approve_outbox(outbox_id: UUID, db: Session = Depends(get_db)):
    row = db.query(OutboxItem).filter(OutboxItem.id == str(outbox_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Outbox item not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Item is already '{row.status}', not pending")
    if row.expires_at and row.expires_at < datetime.utcnow():
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="This approval has expired - ask the agent to re-draft it")
    if (row.ref or {}).get("kind") == "contact":
        import outreach_guard as _og
        _c = db.query(Contact).filter(Contact.id == (row.ref or {}).get("id")).first()
        if _c:
            try:
                _og.check_can_send(db, row.user_id, _c)
            except _og.Blocked as _e:
                raise HTTPException(status_code=_e.status, detail=_e.detail)
    since = datetime.utcnow() - timedelta(days=1)
    approved_today = (
        db.query(OutboxItem)
        .filter(OutboxItem.user_id == row.user_id, OutboxItem.status == "approved", OutboxItem.created_at >= since)
        .count()
    )
    if approved_today >= MAX_OUTBOX_APPROVALS_PER_DAY:
        raise HTTPException(status_code=429, detail="Daily outbox approval limit reached - try again tomorrow")
    row.status = "approved"
    ref = row.ref or {}
    if ref.get("kind") == "contact":
        contact = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if contact:
            contact.status = "Sent"
            contact.sent_on = date.today()
            oh = OutreachHistory(
                user_id=row.user_id, contact_id=contact.id,
                subject=row.payload.get("subject", ""), email_text=row.payload.get("body", ""),
                status="Sent", sent_at=datetime.utcnow(), follow_up_date=date.today() + timedelta(days=7),
            )
            db.add(oh)
            rag.safe(rag.index_outreach, db, oh, contact)
    elif ref.get("kind") == "request":
        req = db.query(ClientRequest).filter(ClientRequest.id == ref.get("id")).first()
        if req and req.status in ("New", "Scoped"):
            req.status = "Quoted"
    db.commit()
    db.refresh(row)
    return row


@app.post("/v1/outbox/{outbox_id}/reject", response_model=OutboxOut)
def reject_outbox(outbox_id: UUID, note: str = None, db: Session = Depends(get_db)):
    row = db.query(OutboxItem).filter(OutboxItem.id == str(outbox_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Outbox item not found")
    row.status = "rejected"
    if note:
        row.note = note
    ref = row.ref or {}
    if ref.get("kind") == "contact":
        contact = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if contact and contact.status == "Drafted":
            contact.status = "Not started"
    db.commit()
    db.refresh(row)
    return row


# ================= RESUME (up to ~10 versions, each scored + askable) =================
@app.post("/v1/resumes", response_model=ResumeOut)
def resume_create(payload: ResumeCreate, db: Session = Depends(get_db)):
    return create_resume(payload.user_id, payload.label, payload.target_role, payload.text, db)


@app.get("/v1/resumes", response_model=List[ResumeOut])
def resume_list(user_id: UUID, db: Session = Depends(get_db)):
    return (
        db.query(Resume)
        .filter(Resume.user_id == str(user_id))
        .order_by(Resume.created_at.desc())
        .all()
    )


@app.get("/v1/resumes/{resume_id}", response_model=ResumeOut)
def resume_get(resume_id: str, db: Session = Depends(get_db)):
    row = db.query(Resume).filter(Resume.id == resume_id).first()
    if not row:
        raise HTTPException(404, "Resume not found")
    return row


@app.patch("/v1/resumes/{resume_id}", response_model=ResumeOut)
def resume_update(resume_id: str, payload: ResumeUpdate, db: Session = Depends(get_db)):
    try:
        return update_resume(resume_id, payload.label, payload.target_role, payload.text, db)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(404 if "not found" in msg.lower() else 422, msg)


@app.post("/v1/resumes/{resume_id}/reanalyze", response_model=ResumeOut)
def resume_reanalyze(resume_id: str, payload: ResumeReanalyzeRequest, db: Session = Depends(get_db)):
    try:
        return reanalyze_resume(resume_id, payload.target_role, db)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/v1/resumes/{resume_id}/ask", response_model=ResumeAskResponse)
def resume_ask(resume_id: str, payload: ResumeAskRequest, db: Session = Depends(get_db)):
    return ask_resume(payload.user_id, resume_id, payload.question, db)


@app.delete("/v1/resumes/{resume_id}")
def resume_delete(resume_id: str, db: Session = Depends(get_db)):
    try:
        delete_resume(resume_id, db)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


# ================= MEMORY =================
@app.get("/v1/memory", response_model=MemoryOut)
def get_memory(user_id: UUID, db: Session = Depends(get_db)):
    mem = db.query(UserMemory).filter(UserMemory.user_id == str(user_id)).first()
    if not mem:
        return MemoryOut()
    return mem


@app.patch("/v1/memory", response_model=MemoryOut)
def update_memory(user_id: UUID, payload: MemoryUpdate, db: Session = Depends(get_db)):
    mem = db.query(UserMemory).filter(UserMemory.user_id == str(user_id)).first()
    if not mem:
        mem = UserMemory(user_id=str(user_id))
        db.add(mem)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mem, field, value)
    db.commit()
    db.refresh(mem)
    return mem


# ---- structured memory items (profile / working / learning) ----
@app.get("/v1/memory/items", response_model=List[MemoryItemOut])
def list_memory_items(user_id: UUID, type: str = None, include_unconfirmed: bool = True, db: Session = Depends(get_db)):
    q = db.query(MemoryItem).filter(MemoryItem.user_id == str(user_id), MemoryItem.status != "forgotten")
    if type:
        q = q.filter(MemoryItem.type == type)
    if not include_unconfirmed:
        q = q.filter(MemoryItem.status == "active")
    return q.order_by(MemoryItem.created_at.desc()).all()


@app.post("/v1/memory/items", response_model=MemoryItemOut)
def create_memory_item(payload: MemoryItemCreate, db: Session = Depends(get_db)):
    if payload.type not in ("profile", "working", "learning"):
        raise HTTPException(status_code=400, detail="type must be profile, working, or learning")
    item = MemoryItem(
        user_id=str(payload.user_id), type=payload.type, content=payload.content,
        source=payload.source, confidence=payload.confidence, status=payload.status,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    rag.safe(rag.index_memory_item, db, item)
    return item


@app.post("/v1/memory/items/{item_id}/confirm", response_model=MemoryItemOut)
def confirm_memory_item(item_id: UUID, payload: MemoryItemConfirm, db: Session = Depends(get_db)):
    item = db.query(MemoryItem).filter(MemoryItem.id == str(item_id)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Memory item not found")
    if payload.status not in ("active", "forgotten"):
        raise HTTPException(status_code=400, detail="status must be active or forgotten")
    item.status = payload.status
    if payload.status == "active":
        item.last_verified_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    rag.safe(rag.index_memory_item, db, item)
    return item


@app.delete("/v1/memory/items/{item_id}")
def forget_memory_item(item_id: UUID, db: Session = Depends(get_db)):
    item = db.query(MemoryItem).filter(MemoryItem.id == str(item_id)).first()
    if not item:
        raise HTTPException(status_code=404, detail="Memory item not found")
    item.status = "forgotten"
    db.commit()
    rag.safe(rag.index_memory_item, db, item)
    return {"status": "forgotten"}


# ================= AGENT ACTIVITY LOG (audit trail) =================
@app.get("/v1/activity", response_model=List[ActivityLogOut])
def list_activity(user_id: UUID, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(AgentActivityLog)
        .filter(AgentActivityLog.user_id == str(user_id))
        .order_by(AgentActivityLog.created_at.desc())
        .limit(min(limit, 200)).all()
    )


# ================= AGENT PERMISSIONS (visibility + emergency stop) =================
@app.get("/v1/agent/permissions", response_model=AgentPermissionsOut)
def get_agent_permissions(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == str(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    prefs = user.preferences or {}
    since = datetime.utcnow() - timedelta(days=1)
    used_today = (
        db.query(OutboxItem)
        .filter(OutboxItem.user_id == str(user_id), OutboxItem.status == "approved", OutboxItem.created_at >= since)
        .count()
    )
    return AgentPermissionsOut(
        agent_enabled=prefs.get("agent_enabled", True),
        can_read=["today's plan", "deadlines", "opportunities", "indexed resume/projects/outreach (RAG)"],
        can_create=["tasks", "outreach drafts (Outbox, pending)"],
        can_send=[],  # nothing is ever auto-sent - see draft_outreach tool
        max_tool_calls_per_turn=MAX_TOOL_CALLS_PER_TURN,
        max_outbox_approvals_per_day=MAX_OUTBOX_APPROVALS_PER_DAY,
        outbox_approvals_used_today=used_today,
        connected_integrations=[],  # Gmail/Calendar not wired yet - see README "Build next"
    )


@app.post("/v1/agent/permissions", response_model=AgentPermissionsOut)
def set_agent_permissions(user_id: UUID, payload: AgentPermissionsUpdate, db: Session = Depends(get_db)):
    """Emergency stop: when agent_enabled=false, the KARNA tool loop refuses
    to execute any tool call (see run_jarvis_agent) until re-enabled here."""
    user = db.query(User).filter(User.id == str(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    prefs = dict(user.preferences or {})
    prefs["agent_enabled"] = payload.agent_enabled
    user.preferences = prefs
    db.commit()
    return get_agent_permissions(user_id, db)


# ================= KARNA UNIFIED CHAT =================
@app.post("/v1/jarvis/chat", response_model=JarvisChatResponse)
def jarvis_chat(request: JarvisChatRequest, db: Session = Depends(get_db)):
    return process_jarvis_message(request.user_id, request.message, db, history=request.history, doc_ids=request.doc_ids)


# ================= GENERAL CHAT (no workspace data) =================
class GeneralChatMessage(BaseModel):
    role: str
    content: str


class GeneralChatRequest(BaseModel):
    system: Optional[str] = None
    messages: List[GeneralChatMessage]


_GENERAL_HITS: dict = {}
_GENERAL_LIMIT = int(os.getenv("GENERAL_CHAT_PER_MIN", "20"))


def _general_rate_limit(ip: str):
    import time
    now = time.time()
    hits = [t for t in _GENERAL_HITS.get(ip, []) if now - t < 60]
    if len(hits) >= _GENERAL_LIMIT:
        raise HTTPException(429, "Too many chat requests. Try again in a minute.")
    hits.append(now)
    _GENERAL_HITS[ip] = hits


@app.post("/v1/chat/general")
def general_chat(req: GeneralChatRequest, request: Request):
    from agent import groq_client
    _general_rate_limit(request.client.host if request.client else "unknown")
    if not groq_client.groq_enabled():
        raise HTTPException(503, "GROQ_API_KEY is not configured on the backend")
    msgs = [{"role": "system", "content": (req.system or "You are KARNA, a helpful general-purpose assistant.")[:2000]}]
    for m in req.messages[-12:]:
        if m.role in ("user", "assistant"):
            msgs.append({"role": m.role, "content": m.content[:6000]})
    try:
        out = groq_client.get_client().chat.completions.create(
            model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), messages=msgs, temperature=0.6, max_tokens=1500,
        ).choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(502, f"AI chat failed: {e}")
    return {"reply": out}


# ================= HISTORY (READ-ONLY ROLLUP) =================
@app.get("/v1/history", response_model=HistorySummary)
def get_history(user_id: UUID, db: Session = Depends(get_db)):
    uid = str(user_id)
    cutoff = date.today() - timedelta(days=7)

    applications = db.query(Application).filter(Application.user_id == uid).all()
    outreach = db.query(OutreachHistory).filter(OutreachHistory.user_id == uid).all()
    all_plans = db.query(DailyPlan).filter(DailyPlan.user_id == uid).all()

    apps_by_status = {}
    for a in applications:
        apps_by_status[a.status] = apps_by_status.get(a.status, 0) + 1

    outreach_by_status = {}
    for o in outreach:
        outreach_by_status[o.status] = outreach_by_status.get(o.status, 0) + 1

    tasks_completed = db.query(Task).filter(
        Task.user_id == uid, Task.status == "done", Task.due_date >= cutoff
    ).count()

    recent_reflections = [p.reflection for p in all_plans if p.reflection][-5:]

    return HistorySummary(
        applications_total=len(applications),
        applications_by_status=apps_by_status,
        outreach_total=len(outreach),
        outreach_by_status=outreach_by_status,
        tasks_completed_last_7_days=tasks_completed,
        plans_logged=len(all_plans),
        recent_reflections=recent_reflections,
    )


# ================= BACKGROUND JOBS (manual trigger; wire to cron/APScheduler) =================
@app.post("/v1/jobs/memory-summarize", response_model=MemorySummarizeResponse)
def run_memory_summarize(user_id: UUID, db: Session = Depends(get_db)):
    return summarize_recent_activity(user_id, db)


# ================= SEED DATABASE =================
@app.post("/v1/seed")
def seed_test_data(db: Session = Depends(get_db)):
    # Seed data is a deliberate development-only feature. It is disabled by
    # default so a production request can never recreate demo identities.
    if os.getenv("ENABLE_DEV_SEED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="Development seed is disabled")
    user = db.query(User).filter(User.email == "student@university.edu").first()
    if not user:
        user = User(
            email="student@university.edu",
            name="Aditya Verma",
            branch="Computer Science",
            degree="B.Tech",
            cgpa=8.84
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not db.query(UserMemory).filter(UserMemory.user_id == user.id).first():
        db.add(UserMemory(
            user_id=user.id,
            goals_summary="Targeting IIT Madras/Bombay research internship or Tier-1 ML roles.",
            work_patterns=["Deep work 9-12 AM", "Procrastinates cover letters"],
            recent_outcomes="Completed Distributed KV-Store in Go."
        ))

    projects = [
        "Distributed KV-Store in Go with Raft consensus algorithm and gRPC communication.",
        "RAG Pipeline for Academic Papers using pgvector, FastAPI, and Llama 3 for structured synthesis."
    ]
    for n, p in enumerate(projects):
        rag.index_source(db, user.id, rag.PROJECT, f"seed-{n}", p, title="Project")

    db.add(Task(user_id=user.id, title="Implement Raft leader election heartbeat", type="project", estimated_minutes=90))
    db.add(Academic(
        user_id=user.id, subject="Compiler Design", exam_date=date.today(),
        priority="high", weak_areas=["LR Parsing", "Code Gen"]
    ))
    db.add(Application(
        user_id=user.id, company="Swiggy", role="Backend AI Intern",
        type="internship", status="To Apply", deadline=date.today() + timedelta(days=14)
    ))

    profs = [
        {
            "name": "Balaraman Ravindran",
            "institute": "IIT Madras",
            "lab": "RBCDSAI",
            "areas": ["Reinforcement Learning", "Graph Neural Networks"],
            "bio": "Head of RBCDSAI at IIT Madras. Focus on multi-agent RL and graph models.",
            "email": "ravi@cse.iitm.ac.in"
        }
    ]
    for pr in profs:
        p_vec = get_embedding(f"{pr['institute']} {pr['lab']} {' '.join(pr['areas'])} {pr['bio']}")
        db.add(Contact(
            name=pr["name"], institute=pr["institute"], lab=pr["lab"],
            research_areas=pr["areas"], bio=pr["bio"], email=pr["email"], embedding=p_vec
        ))

    db.commit()
    rag.safe(rag.reindex_user, db, user.id)
    return {"status": "Database seeded successfully", "user_id": str(user.id)}


# ================= RAG =================
@app.post("/v1/rag/reindex")
def rag_reindex(user_id: UUID, db: Session = Depends(get_db)):
    """Rebuild the vector index from the relational tables (safe to run any time)."""
    return rag.reindex_user(db, user_id)


@app.get("/v1/rag/search")
def rag_search(user_id: UUID, q: str, k: int = 5, source_type: str = None, db: Session = Depends(get_db)):
    """Debug/inspect what the LLM would be shown for a query."""
    return rag.retrieve(db, user_id, q, k=k, source_types=[source_type] if source_type else None)


@app.get("/v1/rag/stats")
def rag_stats(user_id: UUID, db: Session = Depends(get_db)):
    counts = {}
    for c in db.query(DocumentChunk).filter(DocumentChunk.user_id == str(user_id)).all():
        counts[c.source_type] = counts.get(c.source_type, 0) + 1
    return {"chunks_by_source": counts, "total": sum(counts.values())}


# ================= SEMS (exam prep module) =================
@app.post("/v1/semesters", response_model=SemesterOut)
def create_semester(payload: SemesterCreate, db: Session = Depends(get_db)):
    # A new semester becomes "current"; retire any previous current one so
    # generate_study_plan and /semesters/current have a single source of truth.
    db.query(Semester).filter(Semester.user_id == str(payload.user_id), Semester.is_current == True).update({"is_current": False})  # noqa: E712
    row = Semester(user_id=str(payload.user_id), **payload.model_dump(exclude={"user_id"}), is_current=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/v1/semesters/current", response_model=SemesterOut)
def get_current_semester(user_id: UUID, db: Session = Depends(get_db)):
    sem = db.query(Semester).filter(Semester.user_id == str(user_id), Semester.is_current == True).first()  # noqa: E712
    if not sem:
        raise HTTPException(status_code=404, detail="No current semester set up yet")
    return sem


@app.patch("/v1/semesters/{semester_id}", response_model=SemesterOut)
def update_semester(semester_id: UUID, payload: SemesterCreate, db: Session = Depends(get_db)):
    sem = db.query(Semester).filter(Semester.id == str(semester_id)).first()
    if not sem:
        raise HTTPException(status_code=404, detail="Semester not found")
    for field, value in payload.model_dump(exclude={"user_id"}, exclude_unset=True).items():
        setattr(sem, field, value)
    db.commit()
    db.refresh(sem)
    return sem


@app.post("/v1/courses", response_model=CourseOut)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    row = Course(user_id=str(payload.user_id), semester_id=str(payload.semester_id),
                 code=payload.code, name=payload.name, credits=payload.credits,
                 faculty=payload.faculty, source=payload.source)
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_course, db, row)
    return row


@app.get("/v1/courses", response_model=List[CourseOut])
def list_courses(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(Course).filter(Course.user_id == str(user_id)).all()


@app.post("/v1/courses/{course_id}/topics", response_model=TopicOut)
def create_topic(course_id: UUID, payload: TopicCreate, db: Session = Depends(get_db)):
    row = Topic(course_id=str(course_id), **payload.model_dump(exclude={"course_id"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/v1/courses/{course_id}/topics", response_model=List[TopicOut])
def list_topics(course_id: UUID, db: Session = Depends(get_db)):
    return db.query(Topic).filter(Topic.course_id == str(course_id)).all()


@app.patch("/v1/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: UUID, payload: TopicUpdate, db: Session = Depends(get_db)):
    row = db.query(Topic).filter(Topic.id == str(topic_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Topic not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@app.post("/v1/exams", response_model=ExamOut)
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"user_id", "course_id"})
    row = Exam(user_id=str(payload.user_id), course_id=str(payload.course_id), **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_exam, db, row)
    return row


@app.get("/v1/exams", response_model=List[ExamOut])
def list_exams(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(Exam).filter(Exam.user_id == str(user_id)).order_by(Exam.exam_date.asc().nulls_last()).all()


@app.patch("/v1/exams/{exam_id}", response_model=ExamOut)
def update_exam(exam_id: UUID, payload: ExamCreate, db: Session = Depends(get_db)):
    row = db.query(Exam).filter(Exam.id == str(exam_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Exam not found")
    for field, value in payload.model_dump(exclude={"user_id", "course_id"}, exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    rag.safe(rag.index_exam, db, row)
    return row


@app.get("/v1/exams/{exam_id}/risk", response_model=ExamRiskOut)
def get_exam_risk(exam_id: UUID, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == str(exam_id)).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    course = db.query(Course).filter(Course.id == exam.course_id).first()
    topics = db.query(Topic).filter(Topic.course_id == exam.course_id).all()
    risk = compute_exam_risk(exam, topics)
    return ExamRiskOut(exam_id=exam.id, course_name=course.name if course else "Unknown course", **risk)


@app.get("/v1/exam-dashboard", response_model=List[ExamRiskOut])
def exam_dashboard(user_id: UUID, db: Session = Depends(get_db)):
    """All non-completed exams with their risk estimate, soonest/highest-risk first -
    what SEMS's own spec calls the exam map."""
    exams = db.query(Exam).filter(Exam.user_id == str(user_id), Exam.status != "completed").all()
    out = []
    for exam in exams:
        course = db.query(Course).filter(Course.id == exam.course_id).first()
        topics = db.query(Topic).filter(Topic.course_id == exam.course_id).all()
        risk = compute_exam_risk(exam, topics)
        out.append(ExamRiskOut(exam_id=exam.id, course_name=course.name if course else "Unknown course", **risk))
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out.sort(key=lambda r: (order.get(r.risk_level, 4), r.days_until if r.days_until is not None else 9999))
    return out


def _enrich_study_blocks(blocks: List[StudyBlock], db: Session) -> List[StudyBlockOut]:
    topic_ids = {b.topic_id for b in blocks if b.topic_id}
    topics = {t.id: t for t in db.query(Topic).filter(Topic.id.in_(topic_ids)).all()} if topic_ids else {}
    course_ids = {t.course_id for t in topics.values()}
    courses = {c.id: c for c in db.query(Course).filter(Course.id.in_(course_ids)).all()} if course_ids else {}
    out = []
    for b in blocks:
        t = topics.get(b.topic_id) if b.topic_id else None
        c = courses.get(t.course_id) if t else None
        out.append(StudyBlockOut(
            id=b.id, exam_id=b.exam_id, topic_id=b.topic_id, plan_date=b.plan_date,
            duration_min=b.duration_min, mode=b.mode, status=b.status,
            priority_score=float(b.priority_score) if b.priority_score is not None else None,
            generated_reason=b.generated_reason, actual_duration_min=b.actual_duration_min,
            feedback=b.feedback, topic_name=t.name if t else None, course_name=c.name if c else None,
        ))
    return out


@app.post("/v1/study-plans/generate", response_model=List[StudyBlockOut])
def generate_study_plan_endpoint(payload: StudyPlanGenerateRequest, db: Session = Depends(get_db)):
    blocks = sems_generate_study_plan(payload.user_id, db, payload.plan_date, payload.available_minutes)
    return _enrich_study_blocks(blocks, db)


@app.get("/v1/study-plans/current", response_model=List[StudyBlockOut])
def get_current_study_plan(user_id: UUID, plan_date: date = None, db: Session = Depends(get_db)):
    plan_date = plan_date or date.today()
    blocks = (
        db.query(StudyBlock)
        .filter(StudyBlock.user_id == str(user_id), StudyBlock.plan_date == plan_date)
        .order_by(StudyBlock.priority_score.desc().nulls_last()).all()
    )
    return _enrich_study_blocks(blocks, db)


@app.get("/v1/study-plans/today", response_model=List[StudyBlockOut])
def get_today_study_plan(user_id: UUID, db: Session = Depends(get_db)):
    return get_current_study_plan(user_id, date.today(), db)


@app.post("/v1/study-blocks/{block_id}/complete", response_model=StudyBlockOut)
def complete_study_block_endpoint(block_id: UUID, payload: StudyBlockComplete, db: Session = Depends(get_db)):
    block = db.query(StudyBlock).filter(StudyBlock.id == str(block_id)).first()
    if not block:
        raise HTTPException(status_code=404, detail="Study block not found")
    block = sems_complete_study_block(
        block, db, payload.completed, payload.actual_duration_min,
        payload.difficulty_felt, payload.confidence_now,
    )
    return _enrich_study_blocks([block], db)[0]


@app.post("/v1/study-blocks/{block_id}/reschedule", response_model=StudyBlockOut)
def reschedule_study_block(block_id: UUID, new_date: date, db: Session = Depends(get_db)):
    block = db.query(StudyBlock).filter(StudyBlock.id == str(block_id)).first()
    if not block:
        raise HTTPException(status_code=404, detail="Study block not found")
    if block.status != "planned":
        raise HTTPException(status_code=409, detail=f"Block is already '{block.status}', not planned")
    block.plan_date = new_date
    block.status = "rescheduled" if block.plan_date != new_date else block.status
    block.status = "planned"  # stays actionable on its new date
    db.commit()
    db.refresh(block)
    return block


# ---- Timetable/syllabus CSV importer: parse-then-review, never silent-save ----
# ---- Timetable/syllabus CSV importer: parse-then-review, never silent-save ----
@app.post("/v1/courses/import-csv/preview", response_model=CourseCsvPreviewOut)
def import_courses_csv_preview(csv_text: str = Body(..., embed=True)):
    """Parses pasted/uploaded CSV text into a reviewable preview - nothing is
    saved until /confirm. Column names are matched flexibly (course_code,
    code, subject_code, ...); see agent_service._COL_SYNONYMS."""
    result = parse_course_csv(csv_text)
    return CourseCsvPreviewOut(rows=result["rows"], detected_columns=result["detected_columns"])


@app.post("/v1/courses/import-csv/confirm", response_model=List[CourseOut])
def import_courses_csv_confirm(payload: CourseCsvConfirm, db: Session = Depends(get_db)):
    created = []
    for row in payload.rows:
        course = Course(
            user_id=str(payload.user_id), semester_id=str(payload.semester_id),
            code=row.code, name=row.name, credits=row.credits, faculty=row.faculty,
            source="csv_import",
        )
        db.add(course)
        db.flush()  # get course.id before creating the exam
        if row.exam_date:
            db.add(Exam(
                user_id=str(payload.user_id), course_id=course.id, exam_type="End Semester",
                exam_date=row.exam_date, exam_time=row.exam_time, venue=row.venue,
                confidence_pct=row.confidence_pct, status="tentative",
            ))
        created.append(course)
    db.commit()
    for c in created:
        db.refresh(c)
        rag.safe(rag.index_course, db, c)
    return created


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)