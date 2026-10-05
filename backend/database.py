import os
import uuid
import logging
from datetime import datetime as _dt
from sqlalchemy import (
    create_engine, Column, String, Integer, Numeric,
    Date, DateTime, ForeignKey, Text, JSON, Boolean, Index,
    event, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker

log = logging.getLogger("opa.db")


# Defaults to a local SQLite file so the project runs with zero external
# services. Point DATABASE_URL at a real Postgres instance (pgvector not
# required anymore - similarity search is done in Python) to use that instead,
# e.g. postgresql://opa_user:opa_password@localhost:5432/opa_db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./opa.db").strip()
# Hosts hand out "postgres://" or "postgresql://" with no driver. SQLAlchemy 2.x then
# defaults to psycopg v3, but requirements.txt ships psycopg2-binary, so pin the driver.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: free-tier Postgres closes idle connections; this reconnects instead of 500-ing.
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args, pool_pre_ping=True)

# SQLite needs explicit foreign-key enforcement and sane journaling settings.
# Without this, ON DELETE CASCADE/SET NULL declarations are silently ignored.
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def gen_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=gen_id)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    branch = Column(String)
    degree = Column(String)
    cgpa = Column(Numeric(4, 2))
    targets = Column(JSON, default=dict)
    preferences = Column(JSON, default=dict)
    # Frontend "Profile" tab fields - kept flat here (rather than inside
    # targets/preferences JSON) so they're simple to read/write directly.
    github = Column(String)
    skills = Column(Text)      # comma-separated, matched against opportunity/contact tags
    highlight = Column(Text)   # one-line resume highlight used in outreach drafts


class Resume(Base):
    """One of the student's resume versions (e.g. targeted at different roles).
    Multiple rows are expected - each is indexed into document_chunks under its
    own id so RAG/Ask can be scoped to a single version."""
    __tablename__ = "resumes"
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    label = Column(String, nullable=False)        # e.g. "SDE Intern v2", "ML Research"
    target_role = Column(String)                  # optional - tailors analysis + keyword scoring
    raw_text = Column(Text, nullable=False)
    skills = Column(JSON, default=list)
    summary = Column(Text)
    suggested_bullets = Column(JSON, default=list)
    score = Column(JSON, default=dict)             # {clarity, impact, keyword_match, structure, overall, notes}
    created_at = Column(DateTime, default=_dt.utcnow)
    updated_at = Column(DateTime, default=_dt.utcnow, onupdate=_dt.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    source_type = Column(String, nullable=False)  # 'resume', 'project', 'past_plan'
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    embedding = Column(JSON)  # list[float] - cosine similarity computed in Python


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (Index("ix_applications_user_status", "user_id", "status"), Index("ix_applications_user_deadline", "user_id", "deadline"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    type = Column(String, default="internship")
    status = Column(String, default="To Apply")
    deadline = Column(Date)
    link = Column(String)
    notes = Column(Text)
    resume_bullets = Column(JSON, default=list)
    cover_letter = Column(Text)
    follow_up_date = Column(Date)
    effort_minutes = Column(Integer, default=60)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_status", "status"), Index("ix_contacts_email", "email"))
    id = Column(String(36), primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    institute = Column(String, nullable=False)
    lab = Column(String)
    research_areas = Column(JSON, default=list)
    email = Column(String, nullable=False)
    bio = Column(Text)
    embedding = Column(JSON)  # list[float]
    # Denormalized outreach status for this contact, so the frontend can show
    # a status pill without joining outreach_history. Kept in sync by the
    # outreach endpoints (draft/mark-sent/reject).
    status = Column(String, default="Not started")  # Not started, Drafted, Sent
    sent_on = Column(Date)


class OutreachHistory(Base):
    __tablename__ = "outreach_history"
    __table_args__ = (Index("ix_outreach_user_status", "user_id", "status"), Index("ix_outreach_followup", "user_id", "follow_up_date"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="CASCADE"))
    subject = Column(String, nullable=False)
    email_text = Column(Text, nullable=False)
    status = Column(String, default="Draft")  # Draft, Sent, Replied, No Response
    sent_at = Column(DateTime)
    follow_up_date = Column(Date)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_user_status", "user_id", "status"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    description = Column(Text)
    tech_stack = Column(JSON, default=list)
    github_link = Column(String)
    status = Column(String, default="Planning")  # Planning, In Progress, Done
    milestones = Column(JSON, default=list)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status", "user_id", "status"), Index("ix_tasks_user_due", "user_id", "due_date"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, nullable=False)
    type = Column(String, default="general")  # project, academic, application, outreach
    due_date = Column(Date)
    estimated_minutes = Column(Integer, default=45)
    status = Column(String, default="todo")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (Index("ix_opportunities_status_deadline", "status", "deadline"), Index("ix_opportunities_company_title", "company_or_lab", "title"))
    id = Column(String(36), primary_key=True, default=gen_id)
    title = Column(String, nullable=False)
    company_or_lab = Column(String, nullable=False)
    type = Column(String, default="internship")  # internship, research, job
    description = Column(Text)
    link = Column(String)
    source = Column(String, default="manual")  # 'manual', 'scraper', etc.
    status = Column(String, default="New")  # New, Dismissed, Converted
    tags = Column(JSON, default=list)  # matched against the student's profile skills
    deadline = Column(Date)
    eligibility_note = Column(Text)          # e.g. "Final-year only" - free text, optional
    last_verified_at = Column(DateTime, default=_dt.utcnow)
    duplicate_of = Column(String(36), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)


class Academic(Base):
    __tablename__ = "academics"
    __table_args__ = (Index("ix_academics_user_exam", "user_id", "exam_date"), Index("ix_academics_user_done", "user_id", "done"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    subject = Column(String, nullable=False)
    exam_date = Column(Date)
    assignment_deadlines = Column(JSON, default=list)
    priority = Column(String, default="med")
    weak_areas = Column(JSON, default=list)
    task = Column(Text)                       # what to study, shown in the planner
    done = Column(Boolean, default=False)
    effort_minutes = Column(Integer, default=60)


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (Index("uq_daily_plans_user_date", "user_id", "plan_date", unique=True), Index("ix_daily_plans_user_date", "user_id", "plan_date"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    plan_date = Column(Date, nullable=False)
    time_blocks = Column(JSON, default=list)
    actual_completed = Column(JSON, default=list)
    reflection = Column(Text)


class ClientRequest(Base):
    """Inbound freelance/client work request (the frontend 'Requests' tab)."""
    __tablename__ = "client_requests"
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    client = Column(String, nullable=False)
    ask = Column(Text)
    scope = Column(Text)
    timeline = Column(String)
    price = Column(String)
    email = Column(String)
    status = Column(String, default="New")  # New, Scoped, Quoted, Won, Declined


class OutboxItem(Base):
    """Anything drafted (outreach email, proposal) that needs human approval
    before it's considered 'sent'. `ref` links back to what generated it,
    e.g. {"kind": "contact", "id": ...} or {"kind": "request", "id": ...}.

    risk_level: 'low' | 'medium' | 'high' - drives whether approval friction
    is required at all (low-risk planning actions can auto-apply) and how the
    Outbox UI should badge the item.
    approval_scope: e.g. 'single_use' - approving this item authorizes only
    this one action, not a standing permission.
    expires_at: an approval requested but not acted on by this time goes stale
    and must be re-drafted rather than silently sent later."""
    __tablename__ = "outbox_items"
    __table_args__ = (Index("ix_outbox_user_status", "user_id", "status"), Index("ix_outbox_expires", "expires_at"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    channel = Column(String, default="email")
    status = Column(String, default="pending")  # pending, approved, rejected, expired
    payload = Column(JSON, default=dict)         # {to, subject, body}
    ref = Column(JSON, default=dict)             # {kind, id}
    note = Column(Text)
    risk_level = Column(String, default="medium")
    approval_scope = Column(String, default="single_use")
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=_dt.utcnow)


class UserMemory(Base):
    __tablename__ = "user_memory"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    goals_summary = Column(Text)
    skills_summary = Column(Text)
    work_patterns = Column(JSON, default=list)
    recent_outcomes = Column(Text)


class MemoryItem(Base):
    """Structured, per-fact memory (as opposed to UserMemory's rolled-up
    summary text). Every item is typed, sourced, and dated so JARVIS never
    silently treats a guess as a confirmed fact, and the user can forget any
    single item without losing the rest.

    type: 'profile' (skills/goals/education/preferred roles - stable facts)
        | 'working' (current tasks/applications/deadlines/projects - active)
        | 'learning' (what the user completed/ignored/edited/rejected - used
          to bias future suggestions, never to auto-act)
    status: 'unconfirmed' (agent proposed it, not yet shown to user)
          | 'active' (confirmed / in use)
          | 'forgotten' (soft-deleted - kept only for audit, never surfaced)
    """
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_user_status", "user_id", "status"), Index("ix_memory_user_type", "user_id", "type"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(String, nullable=False)       # profile | working | learning
    content = Column(Text, nullable=False)
    source = Column(String, default="jarvis")   # jarvis | user | resume | rag | ...
    confidence = Column(Numeric(3, 2), default=1.0)
    status = Column(String, default="unconfirmed")
    created_at = Column(DateTime, default=_dt.utcnow)
    updated_at = Column(DateTime, default=_dt.utcnow, onupdate=_dt.utcnow)


class AgentActivityLog(Base):
    """Audit trail of every tool call JARVIS's agent loop actually executes.
    Backs the Outbox/Activity screen's 'what did the agent do and why', and
    is what an undo/rollback action would key off of."""
    __tablename__ = "agent_activity_log"
    __table_args__ = (Index("ix_activity_user_created", "user_id", "created_at"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    tool_name = Column(String, nullable=False)
    arguments = Column(JSON, default=dict)
    result_summary = Column(Text)
    risk_level = Column(String, default="low")
    status = Column(String, default="ok")   # ok | blocked | error
    created_at = Column(DateTime, default=_dt.utcnow)


# ================= SEMS (exam prep module) =================
# Phase-1 scope per the SEMS spec: semester setup, courses+exams, syllabus
# topics, a deterministic (non-LLM) risk/priority engine, and a study-block
# planner. Phase-2 (PYQ parsing, quiz generation, OCR) intentionally not
# modeled yet - see README "SEMS roadmap".

class Semester(Base):
    __tablename__ = "semesters"
    __table_args__ = (Index("ix_semesters_user_current", "user_id", "is_current"), Index("uq_semesters_user_term", "user_id", "semester_number", "academic_year", unique=True),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    college = Column(String)
    degree = Column(String)
    branch = Column(String)
    semester_number = Column(Integer)
    academic_year = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    exam_period_start = Column(Date)
    exam_period_end = Column(Date)
    daily_study_minutes = Column(Integer, default=180)      # "available study time"
    peak_start = Column(String, default="19:00")             # preferred/peak energy window
    peak_end = Column(String, default="22:00")
    is_current = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_dt.utcnow)


class Course(Base):
    __tablename__ = "sems_courses"
    __table_args__ = (Index("ix_courses_user_semester", "user_id", "semester_id"), Index("ix_courses_semester_code", "semester_id", "code"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    semester_id = Column(String(36), ForeignKey("semesters.id", ondelete="CASCADE"))
    code = Column(String)
    name = Column(String, nullable=False)
    credits = Column(Numeric(3, 1))
    faculty = Column(String)
    source = Column(String, default="manual")   # manual | csv_import
    created_at = Column(DateTime, default=_dt.utcnow)


class Topic(Base):
    """A syllabus topic within a course. Kept separate from any AI-generated
    plan, per the spec's rule that a regenerated plan must never touch the
    underlying syllabus map."""
    __tablename__ = "sems_topics"
    __table_args__ = (Index("ix_topics_course_unit", "course_id", "unit"), Index("ix_topics_course_status", "course_id", "status"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    course_id = Column(String(36), ForeignKey("sems_courses.id", ondelete="CASCADE"))
    unit = Column(String)                 # e.g. "Unit 2: Memory"
    name = Column(String, nullable=False)
    estimated_minutes = Column(Integer, default=60)
    difficulty = Column(Integer, default=3)    # 1-5
    exam_weightage = Column(Integer, default=10)  # % of that exam's marks, rough
    confidence = Column(Integer, default=1)    # 1-5, student-reported
    status = Column(String, default="not_started")  # not_started | in_progress | done
    last_revised = Column(Date)
    next_review = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=_dt.utcnow)


class Exam(Base):
    __tablename__ = "sems_exams"
    __table_args__ = (Index("ix_exams_user_date", "user_id", "exam_date"), Index("ix_exams_course_date", "course_id", "exam_date"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    course_id = Column(String(36), ForeignKey("sems_courses.id", ondelete="CASCADE"))
    exam_type = Column(String, default="End Semester")
    exam_date = Column(Date)
    exam_time = Column(String)
    venue = Column(String)
    weightage = Column(Integer, default=100)   # % of course grade this exam is worth
    confidence_pct = Column(Integer, default=100)  # extraction confidence when parsed, 0-100
    status = Column(String, default="tentative")  # tentative | confirmed | completed
    completed_feedback = Column(JSON)          # {perceived_difficulty, weak_topics: [...]}
    created_at = Column(DateTime, default=_dt.utcnow)


class StudyBlock(Base):
    __tablename__ = "sems_study_blocks"
    __table_args__ = (Index("ix_studyblocks_user_date", "user_id", "plan_date"), Index("ix_studyblocks_exam_topic", "exam_id", "topic_id"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    exam_id = Column(String(36), ForeignKey("sems_exams.id", ondelete="CASCADE"))
    topic_id = Column(String(36), ForeignKey("sems_topics.id", ondelete="CASCADE"))
    plan_date = Column(Date, nullable=False)
    duration_min = Column(Integer, default=45)
    mode = Column(String, default="learn")   # learn | practice | recall | revise | mock_test | buffer
    status = Column(String, default="planned")  # planned | done | missed | rescheduled
    priority_score = Column(Numeric(5, 2))
    generated_reason = Column(Text)
    actual_duration_min = Column(Integer)
    feedback = Column(JSON)   # {completed, difficulty, confidence}
    created_at = Column(DateTime, default=_dt.utcnow)


class DsaPlan(Base):
    """DSA Roadmap: a planning/tracking record only. No problems, solutions or code are stored here."""
    __tablename__ = "dsa_plans"
    __table_args__ = (Index("ix_dsa_plans_user", "user_id", "status"),)
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    goal = Column(String, default="Placement preparation")
    language = Column(String, default="Python")
    daily_minutes = Column(Integer, default=60)
    days_per_week = Column(Integer, default=5)
    weeks = Column(Integer, default=12)
    start_date = Column(Date)
    mode_override = Column(String, default="auto")   # auto | normal | maintenance
    status = Column(String, default="active")         # active | archived
    created_at = Column(DateTime, default=_dt.utcnow)


class DsaTopic(Base):
    __tablename__ = "dsa_topics"
    __table_args__ = (Index("ix_dsa_topics_plan_pos", "plan_id", "position"), Index("ix_dsa_topics_user", "user_id"))
    id = Column(String(36), primary_key=True, default=gen_id)
    plan_id = Column(String(36), ForeignKey("dsa_plans.id", ondelete="CASCADE"))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    position = Column(Integer, default=0)
    phase_no = Column(Integer, default=1)
    phase = Column(String)
    name = Column(String, nullable=False)
    planned_week = Column(Integer, default=1)
    status = Column(String, default="not_started")   # not_started | learning | practicing | revised | comfortable
    confidence = Column(Integer)                       # 1-5, the learner's own rating
    learn_url = Column(String)                         # one primary learning resource (external)
    practice_url = Column(String)                      # one practice link (external)
    notes = Column(Text)
    sessions_done = Column(Integer, default=0)
    last_session = Column(Date)
    updated_at = Column(DateTime, default=_dt.utcnow)


class DsaSession(Base):
    """One small DSA block per day, shown in Today."""
    __tablename__ = "dsa_sessions"
    __table_args__ = (Index("ux_dsa_session_day", "plan_id", "plan_date", unique=True), Index("ix_dsa_sessions_user_date", "user_id", "plan_date"))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    plan_id = Column(String(36), ForeignKey("dsa_plans.id", ondelete="CASCADE"))
    topic_id = Column(String(36), ForeignKey("dsa_topics.id", ondelete="CASCADE"))
    plan_date = Column(Date, nullable=False)
    minutes = Column(Integer, default=60)
    mode = Column(String, default="normal")           # normal | maintenance
    kind = Column(String, default="learn")            # learn | review | revise
    status = Column(String, default="planned")        # planned | done | skipped
    actual_minutes = Column(Integer)
    confidence = Column(Integer)
    created_at = Column(DateTime, default=_dt.utcnow)
    completed_at = Column(DateTime)


def _auto_migrate():
    """SQLite (and Postgres) support ADD COLUMN but create_all() never issues
    it for a table that already exists - so every time a model gains a new
    column, the live .db file quietly falls behind until a query against
    that column 500s with 'no such column' (exactly what happened with
    Course.faculty/source). This walks every mapped table, diffs its Python
    columns against what SQLite/Postgres actually has, and ADD COLUMNs
    whatever's missing - so old data survives a schema change instead of
    needing the database file deleted.

    Not a real migration tool (no renames, no drops, no data backfill) -
    for anything beyond "a new nullable column showed up", use Alembic.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table - create_all() above already made it
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                try:
                    col_type = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'))
                    added.append(f"{table.name}.{col.name}")
                except Exception as e:
                    log.warning("auto-migrate: could not add %s.%s (%s)", table.name, col.name, e)
    if added:
        log.warning("auto-migrated missing columns: %s", ", ".join(added))


def init_db():
    Base.metadata.create_all(bind=engine)
    _auto_migrate()
    # create_all() does not reliably add newly declared indexes to existing
    # tables on every backend; create mapped indexes explicitly and idempotently.
    for table in Base.metadata.sorted_tables:
        for idx in table.indexes:
            try:
                idx.create(bind=engine, checkfirst=True)
            except Exception as e:
                log.warning("db-index: could not create %s (%s)", idx.name, e)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Phase 1: typed actions, approvals ----------------
class ActionRecord(Base):
    """One typed action proposed by JARVIS / the Today engine / the UI.
    Models propose; only action_service executes. idempotency_key is unique per user."""
    __tablename__ = "actions"
    __table_args__ = (Index("ix_actions_user_created", "user_id", "created_at"),
                      Index("uq_actions_user_idem", "user_id", "idempotency_key", unique=True))
    id = Column(String(36), primary_key=True, default=gen_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    intent = Column(String, nullable=False)
    risk = Column(String, default="low")                 # low | medium | high
    status = Column(String, default="proposed")          # proposed | pending_approval | executed | rejected | failed
    source = Column(String, default="ui")                # ui | jarvis | today | system
    payload_json = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)
    reason = Column(Text)
    confidence = Column(Numeric(3, 2), default=1.0)
    requires_approval = Column(Boolean, default=False)
    idempotency_key = Column(String(80))
    created_at = Column(DateTime, default=_dt.utcnow)
    executed_at = Column(DateTime)


class ActionApproval(Base):
    __tablename__ = "approvals"
    id = Column(String(36), primary_key=True, default=gen_id)
    action_id = Column(String(36), ForeignKey("actions.id", ondelete="CASCADE"))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    decision = Column(String, nullable=False)            # approved | rejected
    approved_payload_hash = Column(String(64))
    approved_at = Column(DateTime, default=_dt.utcnow)
