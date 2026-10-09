"""Pure-Python syllabus structure extractor (no DB, no LLM). Text in -> units/topics + clarification questions out.

Handles the usual Indian-university layouts:
  "Unit 1: Arrays and Strings", "UNIT-II  Trees", "Module 3 - Graphs", "1. Introduction", "Chapter 4"
followed by topic lines or a comma/semicolon/dash separated topic list.
"""
from __future__ import annotations

import re
from typing import Dict, List

_UNIT = re.compile(
    r"^\s*(?:unit|module|chapter|section|part)\s*[-:.\u2013\u2014]?\s*([ivxlc]+|\d+)\s*[-:.)\u2013\u2014]*\s*(.*)$", re.I)
_NUMBERED = re.compile(r"^\s*(\d{1,2})[.)]\s+(\S.*)$")
_COURSE_CODE = re.compile(r"\b([A-Z]{2,5}\s?-?\d{3,4}[A-Z]?)\b")
_CREDITS = re.compile(r"\b(?:credits?|L-?T-?P)\s*[:=-]?\s*(\d+(?:\.\d)?)", re.I)
_NOISE = re.compile(r"^(page\s*\d+|\d+\s*/\s*\d+|syllabus|course (?:outcomes?|objectives?)|references?|text ?books?|"
                    r"reference books?|co\d|total (?:hours|lectures))\b", re.I)
_SPLIT = re.compile(r"\s*(?:;|•|\u2022|\s[-\u2013\u2014]\s|,(?![^()]*\)))\s*")
_STOP = re.compile(r"^(?:text ?books?|reference books?|references?|suggested reading|course outcomes?|evaluation|assessment)\b", re.I)
_HOURS = re.compile(r"\(?\b(\d{1,2})\s*(?:hrs?|hours?|lectures?|periods?)\b\)?", re.I)


def _roman(s: str) -> int:
    if s.isdigit():
        return int(s)
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    t, prev = 0, 0
    for ch in reversed(s.lower()):
        v = vals.get(ch, 0)
        t += -v if v < prev else v
        prev = max(prev, v)
    return t


def _clean(t: str) -> str:
    t = _HOURS.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" .:-\u2013\u2014\t")


def _topics_from(text: str) -> List[str]:
    out = []
    for part in _SPLIT.split(text):
        p = _clean(part)
        if 3 <= len(p) <= 90 and not _NOISE.match(p):
            out.append(p)
    return out


def extract_structure(text: str) -> Dict:
    """Returns {code, credits, units:[{unit,name,hours,topics:[..]}], questions:[..]}."""
    lines = [l.rstrip() for l in (text or "").replace("\r", "").split("\n")]
    head = "\n".join(lines[:40])
    code = (_COURSE_CODE.search(head) or [None, None])[1]
    cr = _CREDITS.search(head)
    units: List[Dict] = []
    cur = None
    stopped = False
    has_unit_words = any(_UNIT.match(l.strip()) for l in lines)   # then "1. xyz" lines (prerequisites etc.) are not units
    for raw in lines:
        line = raw.strip()
        if not line or _NOISE.match(line):
            if line and units and _STOP.match(line):
                cur = None
                stopped = True
            continue
        if stopped:
            continue
        m = _UNIT.match(line)
        if m:
            num = _roman(m.group(1))
            title = _clean(m.group(2))
            hrs = _HOURS.search(line)
            cur = {"unit": f"Unit {num}" + (f": {title[:60]}" if title and len(title) < 70 else ""),
                   "name": title or f"Unit {num}", "hours": int(hrs.group(1)) if hrs else None, "topics": []}
            units.append(cur)
            if title and len(title) >= 70:                    # heading line already carries the topic list
                cur["topics"].extend(_topics_from(title))
            continue
        n = None if has_unit_words else _NUMBERED.match(line)
        if n and cur is None:                                 # numbered-heading style syllabus, no "Unit" words
            cur = {"unit": f"Unit {n.group(1)}: {_clean(n.group(2))[:60]}", "name": _clean(n.group(2)),
                   "hours": None, "topics": []}
            units.append(cur)
            continue
        if n and cur is not None and len(_clean(n.group(2))) < 45 and len(line) < 60 and not cur["topics"] and \
                int(n.group(1)) == len(units) + 1:
            cur = {"unit": f"Unit {n.group(1)}: {_clean(n.group(2))[:60]}", "name": _clean(n.group(2)),
                   "hours": None, "topics": []}
            units.append(cur)
            continue
        if cur is not None:
            cur["topics"].extend(_topics_from(line))
    for u in units:                                           # de-duplicate, keep order
        seen, keep = set(), []
        for t in u["topics"]:
            k = t.lower()
            if k not in seen:
                seen.add(k)
                keep.append(t)
        u["topics"] = keep[:40]
        if not u["topics"] and u["name"]:
            u["topics"] = [u["name"]]
    units = [u for u in units if u["topics"]]

    questions: List[str] = []
    if not units:
        questions.append("I couldn't find units or topics in this file. Is it a syllabus? If it's scanned, upload a clearer PDF or paste the topics.")
    else:
        if len(units) == 1:
            questions.append("I found only one unit. Is that the whole syllabus, or are some pages missing?")
        thin = [u["unit"] for u in units if len(u["topics"]) == 1]
        if thin:
            questions.append(f"These units have no topic list, so I used the title as the topic: {', '.join(thin[:4])}. Do you want to add topics?")
    if not code:
        questions.append("What is the course code (for example CS301)?")
    questions.append("Which units are in the mid-sem and which are in the end-sem?")
    questions.append("When is the exam, and how many marks is it? Open book or closed book?")
    questions.append("Rate your confidence 1-5 for each unit so I can plan where to start.")
    return {"code": code.replace(" ", "") if code else None, "credits": float(cr.group(1)) if cr else None,
            "units": units, "questions": questions}


# ---- Multi-course booklets (e.g. a university's whole "Course Structure & Syllabus" PDF) ----
_OBJ = re.compile(r"^\s*course\s+objectives?\b", re.I)
_SEMLINE = re.compile(r"^\s*((?:I{1,3}|IV)\s*year\s*(?:I{1,2})\s*sem\w*)\s*(.*)$", re.I)
_TITLE_END = re.compile(r"^\s*(?:\(|l\s*t\s*p\s*c\b|\d|pre-?requisites?|common to|course\s)", re.I)


def _title_after_sem(lines: List[str], i: int, limit: int):
    """Title = text after the 'II Year I Semester' header, until 'L T P C' / '(Common to ...)' / a number line."""
    m = _SEMLINE.match(lines[i])
    sem = re.sub(r"\s+", " ", m.group(1)).strip()
    parts = []
    first = m.group(2)
    for k, raw in enumerate([first] + lines[i + 1:limit]):
        t = raw.strip()
        if not t:
            if parts:
                break
            continue
        if k > 0 and _TITLE_END.match(t):
            break
        cut = re.split(r"\s+l\s*t\s*p\s*c\b", t, flags=re.I)[0].strip()
        if cut:
            parts.append(cut)
        if cut != t:
            break
    title = re.sub(r"\s+", " ", " ".join(parts)).strip(" -\u2013")
    return sem, re.sub(r"\s*\((?:common to|professional elective|open elective|skill enhancement)[^)]*\)?\s*$", "", title, flags=re.I).strip()


def split_courses(text: str) -> List[Dict]:
    """If the text holds several courses, return [{title, sem, text}]; else []."""
    lines = (text or "").replace("\r", "").split("\n")
    if sum(1 for l in lines if _OBJ.match(l)) < 3:
        return []
    starts = [i for i, l in enumerate(lines) if _SEMLINE.match(l)]
    found = []
    for n, i in enumerate(starts):
        nxt = starts[n + 1] if n + 1 < len(starts) else len(lines)
        # only real course pages: a "Course Objectives" heading must follow before the next semester header
        if not any(_OBJ.match(lines[k]) for k in range(i + 1, min(i + 25, nxt))):
            continue
        sem, title = _title_after_sem(lines, i, min(i + 8, nxt))
        if len(title) >= 3:
            found.append((i, sem, title))
    out = []
    for n, (i, sem, title) in enumerate(found):
        end = found[n + 1][0] if n + 1 < len(found) else len(lines)
        out.append({"title": title.title() if title.isupper() else title, "sem": sem, "text": "\n".join(lines[i:end])})
    return out if len(out) >= 3 else []


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower().replace("&", " and ")).replace("  ", " ").strip()


def pick_course(courses: List[Dict], query: str):
    """Match a typed course name to one of the split courses. None if no confident match."""
    q = _norm(query or "")
    if len(q) < 3:
        return None
    for c in courses:
        if _norm(c["title"]) == q:
            return c
    for c in courses:
        if q in _norm(c["title"]):
            return c
    words = [w for w in q.split() if len(w) > 2]
    if words:
        for c in courses:
            if all(w in _norm(c["title"]) for w in words):
                return c
    return None
