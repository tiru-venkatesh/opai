"""
RAG layer for OPA.

Note: RAG is not "trained". Nothing is fine-tuned. The model stays as-is, and this
module (1) chunks + embeds your own data (resume, projects, reflections, sent
emails, cover letters, weak areas), (2) stores vectors in `document_chunks`,
and (3) retrieves the most relevant chunks at prompt time so Groq answers from
YOUR data. "Training" = indexing. Every write path below re-indexes automatically.

Embedder: fastembed (BAAI/bge-small-en-v1.5) when available. If the model can't
load (offline, no disk, import error), it falls back to a dependency-free hashed
bag-of-words embedder so the app never breaks. Each chunk remembers which
embedder produced it (metadata_json["embedder"]); mismatched chunks are re-embedded
lazily, so switching embedders is safe.

Set RAG_EMBEDDER=hash to force the fallback, RAG_EMBEDDER=fastembed to force fastembed.
"""
import os
import re
import math
import zlib
import logging
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from database import (
    DocumentChunk, Project, DailyPlan, OutreachHistory, Contact, Academic, Application,
    User, ClientRequest, Course, Exam, MemoryItem,
)

log = logging.getLogger("opa.rag")

# source_type values used in document_chunks
RESUME = "resume"
PROJECT = "project"
REFLECTION = "plan_reflection"
OUTREACH = "outreach_email"
COVER_LETTER = "cover_letter"
ACADEMIC = "academic_note"
PROFILE = "profile"
REQUEST = "client_request"
COURSE = "course"
MEMORY = "memory_item"

# ------------------------------------------------------------------ embedding
FASTEMBED_TAG = "bge-small-en-v1.5"
HASH_DIM = 512
HASH_TAG = f"hash-{HASH_DIM}-s1"  # bump when tokenize()/_hash_embed change so old chunks re-embed lazily

_fe_model = None
_fe_failed = False


def _load_fastembed():
    global _fe_model, _fe_failed
    if _fe_model is not None or _fe_failed:
        return _fe_model
    if os.getenv("RAG_EMBEDDER", "auto").lower() == "hash":
        _fe_failed = True
        return None
    try:
        from fastembed import TextEmbedding
        _fe_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    except Exception as e:  # import error, offline model download, etc.
        _fe_failed = True
        if os.getenv("RAG_EMBEDDER", "auto").lower() == "fastembed":
            raise
        log.warning("fastembed unavailable (%s); using hashed fallback embedder", e)
    return _fe_model


_STOP = set(
    "a an the and or of to in on for with at by from is are was were be been it this that these those "
    "as i my me we our you your they their he she his her its into over under about can could should "
    "would will do does did have has had not no yes so if then than also just more most some any all".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#\-]*")


def _stem(t: str) -> str:
    """Very light suffix stripping so 'applications'~'application', 'studying'~'study'.
    Applied identically to queries and chunks, so it only needs to be consistent."""
    if not t.isalpha() or len(t) < 5:
        return t
    for suf, rep_ in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[:-len(suf)] + rep_
    return t


def tokenize(text: str) -> List[str]:
    return [_stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def _hash_embed(text: str) -> List[float]:
    toks = tokenize(text)
    feats: Dict[int, float] = {}
    counts: Dict[str, int] = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    for t, c in counts.items():
        h = zlib.crc32(t.encode())
        sign = 1.0 if (h >> 16) & 1 else -1.0
        feats[h % HASH_DIM] = feats.get(h % HASH_DIM, 0.0) + sign * (1.0 + math.log(c))
    for a, b in zip(toks, toks[1:]):
        h = zlib.crc32(f"{a} {b}".encode())
        sign = 1.0 if (h >> 16) & 1 else -1.0
        feats[h % HASH_DIM] = feats.get(h % HASH_DIM, 0.0) + sign * 0.5
    norm = math.sqrt(sum(v * v for v in feats.values())) or 1.0
    vec = [0.0] * HASH_DIM
    for i, v in feats.items():
        vec[i] = v / norm
    return vec


def embed_texts(texts: Sequence[str]) -> "tuple[List[List[float]], str]":
    """Returns (vectors, embedder_tag)."""
    model = _load_fastembed()
    if model is not None:
        try:
            return [v.tolist() for v in model.embed(list(texts))], FASTEMBED_TAG
        except Exception as e:
            log.warning("fastembed embed() failed (%s); using hashed fallback", e)
    return [_hash_embed(t) for t in texts], HASH_TAG


def embed_one(text: str) -> List[float]:
    return embed_texts([text])[0][0]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


# ------------------------------------------------------------------- chunking
def chunk_text(text: str, max_chars: int = 600, overlap: int = 100) -> List[str]:
    """Paragraph-first packing; over-long paragraphs are split on sentences, with a small overlap."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[\-\u2022*]\s)", text) if p.strip()]
    units: List[str] = []
    for p in paras:
        if len(p) <= max_chars:
            units.append(p)
            continue
        cur = ""
        for s in re.split(r"(?<=[.!?])\s+", p):
            if len(s) > max_chars:  # pathological: no punctuation
                if cur:
                    units.append(cur)
                    cur = ""
                units.extend(s[i:i + max_chars] for i in range(0, len(s), max_chars - overlap))
            elif len(cur) + len(s) + 1 > max_chars:
                units.append(cur)
                cur = (cur[-overlap:] + " " + s).strip() if overlap else s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            units.append(cur)
    chunks: List[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + len(u) + 1 > max_chars:
            chunks.append(cur)
            cur = u
        else:
            cur = (cur + "\n" + u).strip()
    if cur:
        chunks.append(cur)
    return chunks


# ------------------------------------------------------------------- indexing
def _meta(ch: DocumentChunk) -> dict:
    return ch.metadata_json or {}


def delete_source(db: Session, user_id, source_type: str, source_id: str, commit: bool = True) -> int:
    uid = str(user_id)
    rows = db.query(DocumentChunk).filter(
        DocumentChunk.user_id == uid, DocumentChunk.source_type == source_type
    ).all()
    n = 0
    for r in rows:
        if _meta(r).get("source_id") == source_id:
            db.delete(r)
            n += 1
    if commit:
        db.commit()
    return n


def index_source(
    db: Session, user_id, source_type: str, source_id: str, text: str,
    title: str = "", meta: Optional[dict] = None,
) -> int:
    """Idempotent: replaces every chunk previously stored for (user, source_type, source_id)."""
    uid = str(user_id)
    delete_source(db, uid, source_type, source_id, commit=False)
    pieces = chunk_text(text)
    if not pieces:
        db.commit()
        return 0
    contents = [f"[{title}] {p}" if title else p for p in pieces]
    vecs, tag = embed_texts(contents)
    for i, (content, vec) in enumerate(zip(contents, vecs)):
        db.add(DocumentChunk(
            user_id=uid, source_type=source_type, content=content, embedding=vec,
            metadata_json={**(meta or {}), "source_id": source_id, "title": title, "chunk": i, "embedder": tag},
        ))
    db.commit()
    return len(contents)


def index_resume(db: Session, user_id, resume_id: str, text: str, label: str = "", target_role: str = "") -> int:
    """One resume among possibly several - source_id is the Resume row's own id
    so each version gets its own chunks (Ask-this-resume filters on it)."""
    title = f"Resume: {label}" if label else "Resume"
    return index_source(db, user_id, RESUME, resume_id, text, title=title,
                        meta={"label": label, "target_role": target_role})


def index_project(db: Session, p: Project) -> int:
    body = " ".join(filter(None, [
        p.description or "",
        ("Tech stack: " + ", ".join(p.tech_stack)) if p.tech_stack else "",
        f"Status: {p.status}" if p.status else "",
        f"GitHub: {p.github_link}" if p.github_link else "",
    ]))
    return index_source(db, p.user_id, PROJECT, p.id, body, title=f"Project: {p.title}", meta={"status": p.status})


def index_reflection(db: Session, user_id, plan_date, reflection: str, note: Optional[str] = None) -> int:
    text = " ".join(filter(None, [reflection, f"Pattern: {note}" if note else ""]))
    return index_source(db, user_id, REFLECTION, f"plan-{plan_date}", text, title=f"Reflection {plan_date}",
                        meta={"date": str(plan_date)})


def index_outreach(db: Session, row: OutreachHistory, contact: Optional[Contact] = None) -> int:
    who = f" to {contact.name} ({contact.institute})" if contact else ""
    return index_source(
        db, row.user_id, OUTREACH, row.id, f"Subject: {row.subject}\n\n{row.email_text}",
        title=f"Email{who}", meta={"status": row.status, "contact_id": row.contact_id},
    )


def index_academic(db: Session, a: Academic) -> int:
    bits = [f"Subject {a.subject}."]
    if a.exam_date:
        bits.append(f"Exam on {a.exam_date}.")
    if a.priority:
        bits.append(f"Priority {a.priority}.")
    if a.task:
        bits.append(f"Study task: {a.task}.")
    weak = ", ".join(a.weak_areas or [])
    if weak:
        bits.append(f"Weak areas: {weak}.")
    bits.append("Done." if a.done else "Not done yet.")
    return index_source(db, a.user_id, ACADEMIC, a.id, " ".join(bits), title=f"Academics: {a.subject}")


def index_application(db: Session, a: Application) -> int:
    facts = [f"Application to {a.company} for {a.role}.", f"Status: {a.status}." if a.status else "",
             f"Deadline: {a.deadline}." if a.deadline else "", f"Type: {a.type}." if a.type else ""]
    parts = [" ".join(f for f in facts if f), a.notes or "",
             ("Cover letter: " + a.cover_letter) if a.cover_letter else "",
             ("Resume bullets: " + "; ".join(a.resume_bullets)) if a.resume_bullets else ""]
    text = " ".join(p for p in parts if p).strip()
    return index_source(db, a.user_id, COVER_LETTER, a.id, text, title=f"Application: {a.company} / {a.role}",
                        meta={"status": a.status})


def index_profile(db: Session, u: User) -> int:
    bits = [f"Name: {u.name}." if u.name else "",
            f"Degree: {u.degree}." if u.degree else "",
            f"Branch: {u.branch}." if u.branch else "",
            f"CGPA: {u.cgpa}." if u.cgpa is not None else "",
            f"GitHub: {u.github}." if u.github else "",
            f"Skills: {u.skills}." if u.skills else "",
            f"Highlight: {u.highlight}." if u.highlight else ""]
    text = " ".join(b for b in bits if b).strip()
    return index_source(db, u.id, PROFILE, u.id, text, title="Profile")


def index_request(db: Session, r: ClientRequest) -> int:
    bits = [f"Client: {r.client}.", f"Ask: {r.ask}." if r.ask else "", f"Scope: {r.scope}." if r.scope else "",
            f"Timeline: {r.timeline}." if r.timeline else "", f"Price: {r.price}." if r.price else "",
            f"Status: {r.status}." if r.status else ""]
    return index_source(db, r.user_id, REQUEST, r.id, " ".join(b for b in bits if b),
                        title=f"Client request: {r.client}", meta={"status": r.status})


def index_course(db: Session, c: Course) -> int:
    """One chunk per course that also carries its exams, so 'when is my X exam?' resolves from a single hit."""
    bits = [f"Course {c.name}" + (f" ({c.code})" if c.code else "") + ".",
            f"Credits: {c.credits}." if c.credits is not None else "",
            f"Faculty: {c.faculty}." if c.faculty else ""]
    for e in db.query(Exam).filter(Exam.course_id == c.id).all():
        when = f" on {e.exam_date}" if e.exam_date else " (date not set)"
        if e.exam_time:
            when += f" at {e.exam_time}"
        if e.venue:
            when += f", venue {e.venue}"
        bits.append(f"{e.exam_type or 'Exam'}{when}, status {e.status}.")
    return index_source(db, c.user_id, COURSE, c.id, " ".join(b for b in bits if b), title=f"Course: {c.name}")


def index_exam(db: Session, e: Exam) -> int:
    c = db.get(Course, e.course_id)
    return index_course(db, c) if c else 0


def index_memory_item(db: Session, m: MemoryItem) -> int:
    """Only confirmed (active) memories are retrievable; forgotten/unconfirmed ones are removed from the index."""
    if m.status != "active":
        return delete_source(db, m.user_id, MEMORY, m.id)
    return index_source(db, m.user_id, MEMORY, m.id, f"{m.type} memory: {m.content}", title="Memory",
                        meta={"type": m.type})


def safe(fn: Callable, *args, **kwargs):
    """Indexing must never break the request that triggered it."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.warning("RAG index hook %s failed: %s", getattr(fn, "__name__", fn), e)
        try:
            args[0].rollback()
        except Exception:
            pass
        return None


# ------------------------------------------------------------------ retrieval
def _lexical(query_toks: Iterable[str], content: str) -> float:
    q = set(query_toks)
    if not q:
        return 0.0
    c = set(tokenize(content))
    return len(q & c) / len(q)


def retrieve(
    db: Session, user_id, query: str, k: int = 4,
    source_types: Optional[Sequence[str]] = None,
    where: Optional[Callable[[dict], bool]] = None,
    min_score: float = 0.05,
) -> List[dict]:
    """Hybrid ranking: cosine(embedding) + 0.15 * keyword overlap. Returns dicts, best first."""
    uid = str(user_id)
    if not (query or "").strip():
        return []
    q = db.query(DocumentChunk).filter(DocumentChunk.user_id == uid)
    if source_types:
        q = q.filter(DocumentChunk.source_type.in_(list(source_types)))
    rows = q.all()
    if where:
        rows = [r for r in rows if where(_meta(r))]
    if not rows:
        return []

    qvecs, tag = embed_texts([query])
    qvec = qvecs[0]

    # self-heal chunks embedded with a different embedder (or legacy rows with no tag)
    stale = [r for r in rows if _meta(r).get("embedder") != tag or not r.embedding]
    if stale:
        vecs, _ = embed_texts([r.content for r in stale])
        for r, v in zip(stale, vecs):
            r.embedding = v
            r.metadata_json = {**_meta(r), "embedder": tag}
        db.commit()

    qtoks = tokenize(query)
    seen, scored = set(), []
    for r in rows:
        key = " ".join(r.content.split())[:160]
        if key in seen:
            continue
        seen.add(key)
        score = cosine_similarity(r.embedding or [], qvec) + 0.15 * _lexical(qtoks, r.content)
        if score >= min_score:
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"score": round(s, 4), "source_type": r.source_type, "content": r.content, "meta": _meta(r)}
        for s, r in scored[:k]
    ]


def format_context(hits: List[dict], empty: str = "(none)") -> str:
    if not hits:
        return empty
    return "\n".join(f"- ({h['source_type']}) {h['content']}" for h in hits)


def reindex_user(db: Session, user_id) -> Dict[str, int]:
    """Rebuilds every derived source from the relational tables and re-embeds all remaining chunks."""
    uid = str(user_id)
    out = {"projects": 0, "reflections": 0, "outreach": 0, "academics": 0, "applications": 0,
           "profile": 0, "requests": 0, "courses": 0, "memory": 0, "re_embedded": 0}
    for p in db.query(Project).filter(Project.user_id == uid).all():
        out["projects"] += index_project(db, p)
    for pl in db.query(DailyPlan).filter(DailyPlan.user_id == uid, DailyPlan.reflection.isnot(None)).all():
        if pl.reflection:
            out["reflections"] += index_reflection(db, uid, pl.plan_date, pl.reflection)
    for o in db.query(OutreachHistory).filter(OutreachHistory.user_id == uid).all():
        out["outreach"] += index_outreach(db, o, db.query(Contact).filter(Contact.id == o.contact_id).first())
    for a in db.query(Academic).filter(Academic.user_id == uid).all():
        out["academics"] += index_academic(db, a)
    for a in db.query(Application).filter(Application.user_id == uid).all():
        out["applications"] += index_application(db, a) or 0
    user = db.query(User).filter(User.id == uid).first()
    if user:
        out["profile"] += index_profile(db, user)
    for r in db.query(ClientRequest).filter(ClientRequest.user_id == uid).all():
        out["requests"] += index_request(db, r)
    for c in db.query(Course).filter(Course.user_id == uid).all():
        out["courses"] += index_course(db, c)
    for m in db.query(MemoryItem).filter(MemoryItem.user_id == uid, MemoryItem.status == "active").all():
        out["memory"] += index_memory_item(db, m)
    rows = db.query(DocumentChunk).filter(DocumentChunk.user_id == uid).all()
    if rows:
        vecs, tag = embed_texts([r.content for r in rows])
        for r, v in zip(rows, vecs):
            r.embedding = v
            r.metadata_json = {**_meta(r), "embedder": tag}
        db.commit()
        out["re_embedded"] = len(rows)
    return out
