from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Any
from uuid import UUID
from datetime import date as date_type, datetime as datetime_type


# ================= DAILY PLAN SCHEMAS =================
# The LLM only supplies content + an estimated duration - never a clock time.
# Actual start/end times are computed deterministically in Python
# (agent_service.assign_time_slots) to avoid time-arithmetic hallucinations.
class LLMTimeBlock(BaseModel):
    block_type: str = Field(description="'academics', 'project', or 'application'")
    task_title: str
    priority: str = Field(description="'high', 'medium', or 'low'")
    rationale: str
    duration_minutes: int = Field(description="Estimated minutes needed, between 15 and 180")


class LLMDailyPlan(BaseModel):
    rationale_overview: str
    blocks: List[LLMTimeBlock]


class TimeBlock(LLMTimeBlock):
    time_range: str = Field(description="Computed deterministically, e.g. '09:00 AM - 10:30 AM'")


class DailyPlanResponse(BaseModel):
    plan_date: str
    rationale_overview: str
    blocks: List[TimeBlock]


# ================= MATCHING & OUTREACH SCHEMAS =================
class MatchedOpportunity(BaseModel):
    opportunity_title: str
    company_or_lab: str
    match_score: float = Field(description="Between 0.0 and 1.0")
    why_match: str
    tailored_bullets: List[str]
    cover_letter_outline: str


class OpportunityMatchList(BaseModel):
    matches: List[MatchedOpportunity]


class ProfessorOutreachDraft(BaseModel):
    professor_id: str
    professor_name: str
    lab_name: str
    why_match: str
    subject_line: str
    email_body: str
    follow_up_days: int = 7
    research_brief: Optional[dict] = Field(
        default=None,
        description="{'research_area','relevant_work','matching_skill','proposed_contribution'} shown before send for easy verification"
    )
    short_version: Optional[str] = Field(default=None, description="A condensed 3-4 sentence alternative to email_body")
    repeat_warning: Optional[str] = Field(default=None, description="Set if this contact was already messaged recently")


# ================= JARVIS CHAT SCHEMA =================
class JarvisChatRequest(BaseModel):
    user_id: UUID
    message: str


class JarvisChatResponse(BaseModel):
    action: str = Field(description="'plan' | 'matches' | 'emails' | 'chat'")
    reply: str
    payload: Optional[Any] = None
    tool_calls: Optional[List[dict]] = Field(
        default=None,
        description="Audit trail of validated tool calls the agent actually executed this turn, for transparency."
    )


# ================= APPLICATIONS CRUD =================
class ApplicationCreate(BaseModel):
    user_id: UUID
    company: str
    role: str
    type: str = "internship"
    deadline: Optional[date_type] = None
    link: Optional[str] = None
    notes: Optional[str] = None
    effort_minutes: int = 60


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    deadline: Optional[date_type] = None
    link: Optional[str] = None
    notes: Optional[str] = None
    cover_letter: Optional[str] = None
    follow_up_date: Optional[date_type] = None
    effort_minutes: Optional[int] = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company: str
    role: str
    type: str
    status: str
    deadline: Optional[date_type] = None
    link: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[date_type] = None
    effort_minutes: int = 60


# ================= TASKS CRUD =================
class TaskCreate(BaseModel):
    user_id: UUID
    title: str
    type: str = "general"
    due_date: Optional[date_type] = None
    estimated_minutes: int = 45


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    due_date: Optional[date_type] = None
    estimated_minutes: Optional[int] = None
    status: Optional[str] = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    type: str
    due_date: Optional[date_type] = None
    estimated_minutes: int
    status: str


# ================= ACADEMICS CRUD =================
class AcademicCreate(BaseModel):
    user_id: UUID
    subject: str
    task: Optional[str] = None
    exam_date: Optional[date_type] = None
    priority: str = "med"
    weak_areas: List[str] = []
    effort_minutes: int = 60


class AcademicUpdate(BaseModel):
    subject: Optional[str] = None
    task: Optional[str] = None
    exam_date: Optional[date_type] = None
    priority: Optional[str] = None
    weak_areas: Optional[List[str]] = None
    effort_minutes: Optional[int] = None
    done: Optional[bool] = None


class AcademicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    subject: str
    task: Optional[str] = None
    exam_date: Optional[date_type] = None
    priority: str
    weak_areas: List[str] = []
    effort_minutes: int = 60
    done: bool = False


# ================= CONTACTS (PROFESSORS) =================
class ContactCreate(BaseModel):
    name: str
    institute: str
    lab: Optional[str] = None
    research_areas: List[str] = []
    email: str
    bio: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    institute: Optional[str] = None
    lab: Optional[str] = None
    research_areas: Optional[List[str]] = None
    email: Optional[str] = None
    bio: Optional[str] = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    institute: str
    lab: Optional[str] = None
    research_areas: List[str] = []
    email: str
    status: str = "Not started"
    sent_on: Optional[date_type] = None


# ================= RESUME (multi-version + Q&A) =================
class ResumeScore(BaseModel):
    clarity: int = Field(ge=0, le=10)
    impact: int = Field(ge=0, le=10)
    keyword_match: int = Field(ge=0, le=10)
    structure: int = Field(ge=0, le=10)
    overall: int = Field(ge=0, le=10)
    notes: str = ""


class ResumeCreate(BaseModel):
    user_id: UUID
    label: str
    target_role: Optional[str] = None
    text: str


class ResumeReanalyzeRequest(BaseModel):
    target_role: Optional[str] = None


class ResumeUpdate(BaseModel):
    """Partial edit. Omitted/None = leave unchanged. target_role="" clears it.
    Changing text or target_role re-scores and re-indexes the version."""
    label: Optional[str] = None
    target_role: Optional[str] = None
    text: Optional[str] = None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    target_role: Optional[str] = None
    raw_text: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = []
    suggested_bullets: List[str] = []
    score: Optional[ResumeScore] = None
    created_at: Optional[datetime_type] = None


class ResumeAskRequest(BaseModel):
    user_id: UUID
    question: str


class ResumeAskResponse(BaseModel):
    answer: str
    used_chunks: int


# ================= MEMORY =================
class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    goals_summary: Optional[str] = None
    skills_summary: Optional[str] = None
    work_patterns: List[str] = []
    recent_outcomes: Optional[str] = None


class MemoryUpdate(BaseModel):
    goals_summary: Optional[str] = None
    skills_summary: Optional[str] = None
    work_patterns: Optional[List[str]] = None
    recent_outcomes: Optional[str] = None


# ---- structured memory items (profile / working / learning) ----
class MemoryItemCreate(BaseModel):
    user_id: UUID
    type: str = Field(description="'profile' | 'working' | 'learning'")
    content: str
    source: str = "jarvis"
    confidence: float = 1.0
    # Agent-proposed memories land as 'unconfirmed' until the user approves
    # them; memories the user states directly can be created already 'active'.
    status: str = "unconfirmed"


class MemoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    content: str
    source: str
    confidence: float
    status: str
    created_at: Optional[Any] = None


class MemoryItemConfirm(BaseModel):
    status: str = Field(description="'active' to confirm, 'forgotten' to reject/forget")


# ---- agent activity log ----
class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tool_name: str
    arguments: dict
    result_summary: Optional[str] = None
    risk_level: str
    status: str
    created_at: Optional[Any] = None


# ================= PROJECTS CRUD =================
class ProjectCreate(BaseModel):
    user_id: UUID
    title: str
    description: Optional[str] = None
    tech_stack: List[str] = []
    github_link: Optional[str] = None
    status: str = "Planning"


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    github_link: Optional[str] = None
    status: Optional[str] = None
    milestones: Optional[List[str]] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: Optional[str] = None
    tech_stack: List[str] = []
    github_link: Optional[str] = None
    status: str
    milestones: List[str] = []

    @field_validator("tech_stack", "milestones", mode="before")
    @classmethod
    def _none_or_objects_to_str_list(cls, v):
        # Old rows can hold NULL or dict items; never 500 the list endpoint over it.
        if v is None:
            return []
        if isinstance(v, list):
            return [x if isinstance(x, str) else str((x.get("title") or x.get("name") or x) if isinstance(x, dict) else x) for x in v]
        return v


# ================= OPPORTUNITIES CRUD =================
class OpportunityCreate(BaseModel):
    title: str
    company_or_lab: str
    type: str = "internship"
    description: Optional[str] = None
    link: Optional[str] = None
    source: str = "manual"
    tags: List[str] = []
    deadline: Optional[date_type] = None
    eligibility_note: Optional[str] = None
    allow_duplicate: bool = Field(default=False, description="If false (default), a near-identical title+company is flagged instead of created twice")


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    company_or_lab: str
    type: str
    description: Optional[str] = None
    link: Optional[str] = None
    source: str
    status: str
    tags: List[str] = []
    deadline: Optional[date_type] = None
    eligibility_note: Optional[str] = None
    last_verified_at: Optional[Any] = None
    duplicate_of: Optional[str] = None


class OpportunityIntelOut(BaseModel):
    """Deterministic (non-LLM) scoring layer over a stored Opportunity - cheap
    enough to compute on every list call, unlike workflow_match_opportunities
    which is for LLM-scored ad-hoc job lists."""
    id: str
    title: str
    company_or_lab: str
    match_score: float = Field(description="0.0-1.0 skill-tag overlap against the student's profile skills")
    matched_skills: List[str]
    missing_skills: List[str]
    deadline: Optional[date_type] = None
    deadline_urgency: str = Field(description="'critical' (<3d) | 'soon' (<10d) | 'later' | 'none'")
    estimated_effort_minutes: int
    suggested_next_action: str
    source: str
    link: Optional[str] = None
    last_verified_at: Optional[Any] = None
    eligibility_note: Optional[str] = None


# ================= PROFILE =================
class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    email: str
    branch: Optional[str] = None
    degree: Optional[str] = None
    cgpa: Optional[float] = None
    github: Optional[str] = None
    skills: Optional[str] = None
    highlight: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    degree: Optional[str] = None
    cgpa: Optional[float] = None
    github: Optional[str] = None
    skills: Optional[str] = None
    highlight: Optional[str] = None


# ================= CLIENT REQUESTS (freelance pipeline) =================
class ClientRequestCreate(BaseModel):
    user_id: UUID
    client: str
    ask: Optional[str] = None
    scope: Optional[str] = None
    timeline: Optional[str] = None
    price: Optional[str] = None
    email: Optional[str] = None


class ClientRequestUpdate(BaseModel):
    client: Optional[str] = None
    ask: Optional[str] = None
    scope: Optional[str] = None
    timeline: Optional[str] = None
    price: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None


class ClientRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    client: str
    ask: Optional[str] = None
    scope: Optional[str] = None
    timeline: Optional[str] = None
    price: Optional[str] = None
    email: Optional[str] = None
    status: str = "New"


# ================= OUTBOX (approval queue) =================
class OutboxCreate(BaseModel):
    user_id: UUID
    channel: str = "email"
    payload: dict
    ref: Optional[dict] = None
    note: Optional[str] = None
    risk_level: Optional[str] = Field(default=None, description="'low'|'medium'|'high' - auto-classified if omitted")


class OutboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    channel: str
    status: str
    payload: dict
    ref: Optional[dict] = None
    note: Optional[str] = None
    risk_level: str = "medium"
    approval_scope: str = "single_use"
    expires_at: Optional[Any] = None


# ================= HISTORY & BACKGROUND JOBS =================
class HistorySummary(BaseModel):
    applications_total: int
    applications_by_status: dict
    outreach_total: int
    outreach_by_status: dict
    tasks_completed_last_7_days: int
    plans_logged: int
    recent_reflections: List[str] = []


class MemorySummarizeResponse(BaseModel):
    recent_outcomes: str


# ================= END-OF-DAY REFLECTION =================
class ReflectionRequest(BaseModel):
    user_id: UUID
    plan_date: date_type
    actual_completed: List[str] = Field(description="Task titles the student actually completed")


class ReflectionResponse(BaseModel):
    plan_date: str
    reflection: str
    updated_work_pattern: Optional[str] = None


# ================= AGENT PERMISSIONS =================
class AgentPermissionsOut(BaseModel):
    agent_enabled: bool
    can_read: List[str]
    can_create: List[str]
    can_send: List[str]
    max_tool_calls_per_turn: int
    max_outbox_approvals_per_day: int
    outbox_approvals_used_today: int
    connected_integrations: List[str]


class AgentPermissionsUpdate(BaseModel):
    agent_enabled: bool = Field(description="False = emergency stop; JARVIS tool loop refuses to execute anything")


# ================= SEMS (exam prep module) =================
class SemesterCreate(BaseModel):
    user_id: UUID
    college: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    semester_number: Optional[int] = None
    academic_year: Optional[str] = None
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    exam_period_start: Optional[date_type] = None
    exam_period_end: Optional[date_type] = None
    daily_study_minutes: int = 180
    peak_start: str = "19:00"
    peak_end: str = "22:00"


class SemesterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    college: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    semester_number: Optional[int] = None
    academic_year: Optional[str] = None
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    exam_period_start: Optional[date_type] = None
    exam_period_end: Optional[date_type] = None
    daily_study_minutes: int
    peak_start: str
    peak_end: str
    is_current: bool


class CourseCreate(BaseModel):
    user_id: UUID
    semester_id: UUID
    code: Optional[str] = None
    name: str
    credits: Optional[float] = None
    faculty: Optional[str] = None
    source: str = "manual"


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: Optional[str] = None
    name: str
    credits: Optional[float] = None
    faculty: Optional[str] = None
    source: str


class TopicCreate(BaseModel):
    course_id: UUID
    unit: Optional[str] = None
    name: str
    estimated_minutes: int = 60
    difficulty: int = Field(default=3, ge=1, le=5)
    exam_weightage: int = Field(default=10, ge=0, le=100)
    confidence: int = Field(default=1, ge=1, le=5)
    notes: Optional[str] = None


class TopicUpdate(BaseModel):
    confidence: Optional[int] = Field(default=None, ge=1, le=5)
    status: Optional[str] = Field(default=None, description="not_started | in_progress | done")
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: str
    unit: Optional[str] = None
    name: str
    estimated_minutes: int
    difficulty: int
    exam_weightage: int
    confidence: int
    status: str
    last_revised: Optional[date_type] = None
    next_review: Optional[date_type] = None
    notes: Optional[str] = None


class ExamCreate(BaseModel):
    user_id: UUID
    course_id: UUID
    exam_type: str = "End Semester"
    exam_date: Optional[date_type] = None
    exam_time: Optional[str] = None
    venue: Optional[str] = None
    weightage: int = 100
    confidence_pct: int = 100
    status: str = "tentative"


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: str
    exam_type: str
    exam_date: Optional[date_type] = None
    exam_time: Optional[str] = None
    venue: Optional[str] = None
    weightage: int
    confidence_pct: int
    status: str


class ExamRiskOut(BaseModel):
    """Deterministic (no LLM call) risk/prep estimate for one exam - labelled
    an OPA planning estimate, never presented as a predicted score."""
    exam_id: str
    course_name: str
    exam_date: Optional[date_type] = None
    days_until: Optional[int] = None
    preparation_pct: int
    risk_level: str = Field(description="'low' | 'medium' | 'high' | 'critical'")
    risk_score: float
    weak_topics: List[str]


class StudyBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    exam_id: Optional[str] = None
    topic_id: Optional[str] = None
    plan_date: date_type
    duration_min: int
    mode: str
    status: str
    priority_score: Optional[float] = None
    generated_reason: Optional[str] = None
    actual_duration_min: Optional[int] = None
    feedback: Optional[dict] = None
    topic_name: Optional[str] = None
    course_name: Optional[str] = None


class StudyPlanGenerateRequest(BaseModel):
    user_id: UUID
    plan_date: Optional[date_type] = None   # defaults to today
    available_minutes: Optional[int] = None  # defaults to the semester's daily_study_minutes


class StudyBlockComplete(BaseModel):
    completed: bool = True
    actual_duration_min: Optional[int] = None
    difficulty_felt: Optional[int] = Field(default=None, ge=1, le=5)
    confidence_now: Optional[int] = Field(default=None, ge=1, le=5)


class CourseCsvPreviewRow(BaseModel):
    row_index: int
    code: Optional[str] = None
    name: str
    credits: Optional[float] = None
    faculty: Optional[str] = None
    exam_date: Optional[date_type] = None
    exam_time: Optional[str] = None
    venue: Optional[str] = None
    confidence_pct: int = Field(description="How confident the parser is in this row's exam date/time (100 = exact column match)")
    issues: List[str] = []


class CourseCsvPreviewOut(BaseModel):
    rows: List[CourseCsvPreviewRow]
    detected_columns: dict


class CourseCsvConfirm(BaseModel):
    user_id: UUID
    semester_id: UUID
    rows: List[CourseCsvPreviewRow]