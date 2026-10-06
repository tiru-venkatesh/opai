"""Pure-Python syllabus structure extractor (no DB, no LLM). Text in -> units/topics + clarification questions out.

Handles the usual Indian-university layouts:
  "Unit 1: Arrays and Strings", "UNIT-II  Trees", "Module 3 - Graphs", "1. Introduction", "Chapter 4"
followed by topic lines or a comma/semicolon/dash separated topic list.
"""
from __future__ import annotations

import re
from typing import Dict, List

_DASH = "-\u2013\u2014\u2212"
_UNIT = re.compile(
    r"^\s*(?:unit|module|chapter|section|part)\s*[" + _DASH + r":.]?\s*([ivxlc]+|\d+)\b\s*[" + _DASH + r":.)]*\s*(.*)$", re.I)
_PAGE_NOISE = re.compile(r"^(?:jawaharlal nehru technological|kakinada\b|r\d{2}\s+b\.?\s?tech|\d{1,3}$|<<page)", re.I)
_NUMBERED = re.compile(r"^\s*(\d{1,2})[.)]\s+(\S.*)$")
_COURSE_CODE = re.compile(r"\b([A-Z]{2,5}\s?-?\d{3,4}[A-Z]?)\b")
_CREDITS = re.compile(r"\b(?:credits?|L-?T-?P)\s*[:=-]?\s*(\d+(?:\.\d)?)", re.I)
_NOISE = re.compile(r"^(page\s*\d+|\d+\s*/\s*\d+|syllabus|course (?:outcomes?|objectives?)|references?|text ?books?|"
                    r"reference books?|co\d|total (?:hours|lectures))\b", re.I)
_SPLIT = re.compile(r"\s*(?:;|•|\u2022|\s[-\u2013\u2014]\s|,(?![^()]*\)))\s*")
_STOP = re.compile(r"^(?:text ?books?|reference books?|references?|suggested reading|e-?resources?|web (?:links|resources)|"
                   r"online resources?|learning resources?)\b", re.I)
_STOP_AFTER_UNITS = re.compile(r"^(?:course outcomes?|evaluation|assessment|co\d)\b", re.I)
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


def _split_long(p: str) -> List[str]:
    if len(p) <= 90:
        return [p]
    out = []
    for q in re.split(r"\s+and\s+|\s+&\s+", p):
        q = q.strip()
        if len(q) > 90:
            q = q[:90].rsplit(" ", 1)[0]
        out.append(q)
    return out


def _topics_from(text: str) -> List[str]:
    out = []
    text = re.sub(r"(?<=[a-z\)])\.\s+(?=[A-Z])", "; ", text)      # sentence ends act as separators
    text = re.sub(r"\s*:\s+", "; ", text)                          # "Heading: a, b" -> heading and topics
    for part in _SPLIT.split(text):
        for p in _split_long(_clean(part)):
            if 3 <= len(p) and not _NOISE.match(p):
                out.append(p)
    return out


def _lab_topics(lines: List[str]) -> List[str]:
    """Lab courses list experiments, not units: use the 'Experiments covering the topics' bullets."""
    out, on = [], False
    for raw in lines:
        l = raw.strip()
        if re.match(r"^experiments covering", l, re.I):
            on = True
            continue
        if on and re.match(r"^(sample experiments|exercise|week|text ?books?|references?|course outcomes?)", l, re.I):
            break
        if on and l and not _PAGE_NOISE.match(l):
            out.append(l.lstrip("\u2022\u25cf\uf0b7-\u2013* \t"))
    return _topics_from(" ".join(out))


def extract_structure(text: str) -> Dict:
    """Returns {code, credits, units:[{unit,name,hours,topics:[..]}], questions:[..]}."""
    lines = [l.rstrip() for l in (text or "").replace("\r", "").replace("\f", "\n").split("\n")]
    lines = [l for l in lines if not _PAGE_NOISE.match(l.strip())]
    head = "\n".join(lines[:40])
    code = (_COURSE_CODE.search(head) or [None, None])[1]
    cr = _CREDITS.search(head)
    has_unit_words = any(_UNIT.match(l.strip()) for l in lines)
    units: List[Dict] = []
    cur = None
    stopped = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _STOP.match(line) or (units and _STOP_AFTER_UNITS.match(line)):
            cur = None
            stopped = True
            continue
        if stopped:
            m0 = _UNIT.match(line)
            if not m0:
                continue
            stopped = False                                   # a new unit heading after a stop section resumes
        if _NOISE.match(line) and cur is None:
            continue
        m = _UNIT.match(line)
        if m:
            num = _roman(m.group(1))
            title = _clean(m.group(2))
            hrs = _HOURS.search(line)
            cur = {"unit": f"Unit {num}" + (f": {title[:60]}" if title and len(title) < 70 else ""),
                   "name": title or f"Unit {num}", "hours": int(hrs.group(1)) if hrs else None, "topics": [], "_buf": []}
            units.append(cur)
            if title and len(title) >= 70:                    # heading line already carries the topic list
                cur["_buf"].append(title)
            continue
        n = _NUMBERED.match(line)
        if n and cur is None and not has_unit_words:          # numbered-heading style, only when no "Unit" words exist
            cur = {"unit": f"Unit {n.group(1)}: {_clean(n.group(2))[:60]}", "name": _clean(n.group(2)),
                   "hours": None, "topics": [], "_buf": []}
            units.append(cur)
            continue
        if cur is not None:
            cur["_buf"].append(line)
    for u in units:
        buf = " ".join(u.pop("_buf"))
        if buf:
            u["topics"] = _topics_from(buf)
            lab = re.match(r"^([A-Za-z][A-Za-z &/\-]{2,45}?)\s*[:\-\u2013]", buf)   # "Introduction: ..." names the unit
            if lab and u["name"].startswith("Unit "):
                u["name"] = lab.group(1).strip()
                u["unit"] = f"{u['unit'].split(':')[0]}: {u['name']}"
    for u in units:                                           # de-duplicate, keep order
        seen, keep = set(), []
        for t in u["topics"]:
            k = t.lower()
            if k not in seen:
                seen.add(k)
                keep.append(t)
        if len(keep) > 1 and keep[0].lower().rstrip("- ") == u["name"].lower():
            keep = keep[1:]                                   # the heading label is not a topic itself
        u["topics"] = keep[:60]
        if not u["topics"] and u["name"]:
            u["topics"] = [u["name"]]
    units = [u for u in units if u["topics"]]
    if not units:                                             # lab course: experiments instead of units
        lab = _lab_topics(lines)
        if lab:
            units = [{"unit": "Unit 1: Lab experiments", "name": "Lab experiments", "hours": None, "topics": lab[:60]}]

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


# ---------------------------------------------------------------- multi-course booklets (e.g. a whole JNTU regulation PDF)
_LTPC = re.compile(r"(?:^|\s)L\s+T\s+P\s+C\s*$")
_YEARSEM = re.compile(r"\b(I{1,3}|IV)\s+Year\s+(I{1,2})\s+Sem(?:ester)?\b", re.I)
_TITLE_STOP = re.compile(r"^(?:course objectives?|course outcomes?|pre-?requisites?|objectives?|unit\b)", re.I)
_TITLE_NOISE = re.compile(r"^(?:\d[\d.\s\-]*|[\d.\-]\s[\d.\-]\s[\d.\-]\s[\d.\-]+)$")


def _strip_parens(text: str) -> str:
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _course_title(window: List[str]) -> str:
    parts, depth = [], 0
    for raw in window:
        l = raw.strip()
        if not l or _PAGE_NOISE.match(l):
            continue
        if _TITLE_STOP.match(l):
            break
        l = _YEARSEM.sub(" ", l)
        l = re.sub(r"\bL\s+T\s+P\s+C\b", " ", l)
        l = re.sub(r"(?:\s+[\d.\-]+){4}\s*$", "", l)          # trailing "3 0 0 3"
        # drop parenthetical notes that may span lines: (Common to CSE, ...), (PROFESSIONAL ELECTIVE-IV)
        keep = []
        for ch in l:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth:
                depth -= 1
            elif depth == 0:
                keep.append(ch)
        l = re.sub(r"\\s+", " ", "".join(keep)).strip(" -\u2013\u2014")
        if not l or _TITLE_NOISE.match(l) or re.match(r"^[\d.\-\s]+$", l):
            continue
        if re.match(r"^[a-z\u2022\u25cf]", l):                 # lowercase / bullet start = body text, not a title
            break
        parts.append(l)
        if len(parts) >= 3:
            break
    t = " ".join(parts)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _pretty(t: str) -> str:
    if t.isupper():
        small = {"and", "of", "to", "in", "for", "the", "through", "using", "with", "on"}
        words = []
        for i, w in enumerate(t.lower().split()):
            words.append(w if (i and w in small) else (w.upper() if w in {"ai", "iot", "ml", "ipr", "devops", "cse", "it"} else w.capitalize()))
        t = " ".join(words)
        t = t.replace("Devops", "DevOps")
    return t


def split_courses(text: str) -> List[Dict]:
    """Detect a multi-course booklet. Returns [{title, year_sem, text}] (empty when it is a single course).
    Pages must be separated by a form-feed line so a title never leaks in from the previous page."""
    raw = (text or "").replace("\r", "").split("\n")
    # page index per line
    page_start, pg = [], 0
    for i, l in enumerate(raw):
        if l.strip() == "\f" or l == "\f":
            pg = i
        page_start.append(pg)
    body_hint = re.compile(r"course objectives?|course outcomes?|pre-?requisites?|^unit\\b", re.I)
    marks, have = [], set()
    # primary anchor: "II Year I Semester" near the top of a page, followed by course body text
    for i, l in enumerate(raw):
        s = l.strip()
        if page_start[i] in have or not _YEARSEM.search(s) or re.match(r"^b\.?\s?tech", s, re.I) or i - page_start[i] > 14:
            continue
        if any(body_hint.search(x.strip()) for x in raw[i:i + 14]):
            marks.append(i)
            have.add(page_start[i])
    # fallback anchor: the "L T P C" line, on pages without a year/semester header
    for i, l in enumerate(raw):
        s = l.strip()
        if page_start[i] not in have and _LTPC.search(s) and not re.search(r"category|title|s\.?\s?no", s, re.I):
            marks.append(i)
    marks.sort()
    if len(marks) < 3:
        return []
    starts = []
    for i in marks:
        lo = max(page_start[i], i - 3)
        starts.append((lo, i))
    courses = []
    for k, (lo, i) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(raw)
        window = raw[lo:i + 7]
        title = _course_title(window)
        ys = _YEARSEM.search(" ".join(raw[lo:i + 7]))
        body = "\n".join(raw[lo:end])
        if len(title) < 3 or len(body) < 400:
            continue
        courses.append({"title": _pretty(title), "year_sem": (f"{ys.group(1).upper()} Year {ys.group(2).upper()} Sem" if ys else ""),
                        "text": body})
    return courses


def course_labels(courses: List[Dict]) -> List[str]:
    """Unique, human-readable label per detected course (the same title can appear in several semesters)."""
    seen, out = {}, []
    for c in courses:
        base = c["title"] + (f" ({c['year_sem']})" if c["year_sem"] else "")
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base} #{seen[base]}")
    return out


def pick_course(courses: List[Dict], wanted: str):
    """Match what the user typed/tapped to a detected course. Returns index or None."""
    w = re.sub(r"[^a-z0-9]+", " ", (wanted or "").lower()).strip()
    if len(w) < 3:
        return None
    labels = course_labels(courses)
    norm = lambda x: re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()
    for i, l in enumerate(labels):                            # exact label (what the chips send)
        if norm(l) == w:
            return i
    for i, c in enumerate(courses):                           # exact title
        if norm(c["title"]) == w:
            return i
    hits = [i for i, c in enumerate(courses) if w in norm(c["title"])]
    if "lab" not in w.split():
        hits = [i for i in hits if not norm(courses[i]["title"]).endswith(" lab")] or hits
    if len(hits) >= 1 and len({norm(courses[i]["title"]) for i in hits}) == 1:
        return hits[0]
    return None
