"""DSA Roadmap: pure planning logic. No database, no network, no web framework, so it is fully unit-testable.

OPAI is NOT a coding-practice product. This module only plans, tracks, reminds and adapts. The actual
coding happens on external platforms (LeetCode, GeeksforGeeks, Codeforces, ...). We store links, never
problem statements, solutions or code.

Adaptation rules (all deterministic, shown to the user):
  * The "active" topic is the first topic, in roadmap order, that is not yet advanced
    (advanced = status practicing / revised / comfortable). The roadmap slides with the learner: if they fall
    behind they keep working on the same topic instead of skipping ahead; if they are ahead they pull the next one forward.
  * After a session the user rates confidence 1-5 and the topic status is updated by `status_after_session`:
    confidence <= 2 keeps the topic one more day; >= 4 lets it advance after a single session.
  * In exam season (an exam within EXAM_WINDOW_DAYS, or manual override) DSA drops to Maintenance:
    at most MAINT_MINUTES, review only, no new heavy topic.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

WEEKS = 12                        # "90-day roadmap" = 12 weeks
EXAM_WINDOW_DAYS = 14
MAINT_MINUTES = 20
STATUSES = ("not_started", "learning", "practicing", "revised", "comfortable")
STATUS_LABEL = {"not_started": "Not started", "learning": "Learning", "practicing": "Practicing",
                "revised": "Revised", "comfortable": "Comfortable"}
ADVANCED = {"practicing", "revised", "comfortable"}
LANGUAGES = ("Python", "Java", "C++", "JavaScript")
GOALS = ("Placement preparation", "Internship interviews", "Strengthen fundamentals")
MODES = ("auto", "normal", "maintenance")

LEARN_URL = "https://neetcode.io/roadmap"
GFG_ROADMAP = "https://www.geeksforgeeks.org/dsa/complete-roadmap-to-learn-dsa-from-scratch/"


def _lc(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


# (phase no, name, [first week, last week], [(topic name, practice link or None)])
PHASES: List[Tuple[int, str, Tuple[int, int], List[Tuple[str, Optional[str]]]]] = [
    (1, "Foundation", (1, 1), [("{lang} basics", _lc("fizz-buzz")), ("Big-O", _lc("contains-duplicate")), ("Recursion basics", _lc("fibonacci-number"))]),
    (2, "Arrays and Hashing", (2, 3), [("Arrays and strings", _lc("contains-duplicate")), ("Hash maps and sets", _lc("two-sum")), ("Prefix sums", _lc("product-of-array-except-self"))]),
    (3, "Two Pointers and Sliding Window", (4, 4), [("Two pointers", _lc("valid-palindrome")), ("Sliding window", _lc("best-time-to-buy-and-sell-stock"))]),
    (4, "Stack, Queue, and Linked Lists", (5, 5), [("Stack and queue", _lc("valid-parentheses")), ("Linked lists", _lc("reverse-linked-list"))]),
    (5, "Binary Search", (6, 6), [("Binary search", _lc("binary-search")), ("Rotated arrays and search on answer", _lc("search-in-rotated-sorted-array"))]),
    (6, "Trees and BST", (7, 7), [("Binary tree traversals", _lc("maximum-depth-of-binary-tree")), ("Binary search trees", _lc("validate-binary-search-tree"))]),
    (7, "Heaps, Intervals, and Greedy", (8, 8), [("Heaps and priority queues", _lc("kth-largest-element-in-an-array")), ("Intervals", _lc("merge-intervals")), ("Greedy", _lc("jump-game"))]),
    (8, "Backtracking", (9, 9), [("Subsets and permutations", _lc("subsets"))]),
    (9, "Graphs", (10, 10), [("Graph traversal (BFS and DFS)", _lc("number-of-islands")), ("Topological sort", _lc("course-schedule"))]),
    (10, "Dynamic Programming", (11, 11), [("1D dynamic programming", _lc("climbing-stairs")), ("Classic DP patterns", _lc("coin-change"))]),
    (11, "Revision and Interview Preparation", (12, 12), [("Revise weakest topics", None), ("Pattern summary sheet", None)]),
]


def build_topics(language: str = "Python") -> List[Dict[str, Any]]:
    """Flat, ordered topic list for a new roadmap. Links are only defaults; the user can edit them."""
    out: List[Dict[str, Any]] = []
    pos = 0
    for no, name, (a, b), topics in PHASES:
        n = len(topics)
        span = b - a + 1
        for i, (tname, practice) in enumerate(topics):
            out.append(dict(position=pos, phase_no=no, phase=name, name=tname.replace("{lang}", language),
                            planned_week=a + (i * span) // n, status="not_started", confidence=None,
                            learn_url=LEARN_URL, practice_url=practice, notes=""))
            pos += 1
    return out


def phase_weeks(no: int) -> Tuple[int, int]:
    return next(p[2] for p in PHASES if p[0] == no)


def split_minutes(daily: int) -> Tuple[int, int, int]:
    """(learn, practice, notes). 65 -> (25, 30, 10)."""
    daily = max(15, int(daily))
    notes = max(5, int(daily * 0.15 / 5 + 0.5) * 5)
    learn = max(5, int(daily * 0.38 / 5 + 0.5) * 5)
    practice = max(5, daily - learn - notes)
    return learn, practice, notes


def week_number(start: date, today: date) -> Tuple[int, bool]:
    """(week 1..WEEKS, overrun). overrun = past the planned 12 weeks."""
    w = (today - start).days // 7 + 1
    return min(WEEKS, max(1, w)), w > WEEKS


def is_advanced(status: str) -> bool:
    return status in ADVANCED


def active_topic(topics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for t in sorted(topics, key=lambda x: x["position"]):
        if not is_advanced(t["status"]):
            return t
    return None


def pace(topics: List[Dict[str, Any]], week: int) -> Dict[str, Any]:
    """Compare finished topics with those the schedule says should be finished before this week starts."""
    expected = sum(1 for t in topics if t["planned_week"] < week)
    done = sum(1 for t in topics if is_advanced(t["status"]))
    diff = done - expected
    if diff <= -2:
        state, msg = "behind", f"About {-diff} topics behind. The roadmap slides with you: keep the current topic, no skipping ahead."
    elif diff >= 2:
        state, msg = "ahead", f"About {diff} topics ahead of schedule. Nice. Next topics are pulled forward."
    else:
        state, msg = "on_track", "On track."
    return {"state": state, "expected": expected, "done": done, "diff": diff, "message": msg}


def mode_for(exam_days: Optional[int], override: str = "auto") -> Tuple[str, str]:
    """('normal' | 'maintenance', reason)."""
    if override == "maintenance":
        return "maintenance", "Maintenance mode is on (set by you)."
    if override == "normal":
        return "normal", ""
    if exam_days is not None and 0 <= exam_days <= EXAM_WINDOW_DAYS:
        when = "today" if exam_days == 0 else "tomorrow" if exam_days == 1 else f"in {exam_days} days"
        return "maintenance", f"Exam {when}. DSA is in maintenance so semester exams come first."
    return "normal", ""


def day_minutes(daily: int, mode: str) -> int:
    return min(MAINT_MINUTES, int(daily)) if mode == "maintenance" else int(daily)


def pick_topic(topics: List[Dict[str, Any]], mode: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Topic for the day and why. Maintenance never starts a new topic."""
    ordered = sorted(topics, key=lambda x: x["position"])
    act = active_topic(ordered)
    done = [t for t in ordered if is_advanced(t["status"])]
    if mode == "maintenance":
        if done:
            weakest = sorted(done, key=lambda t: (t["confidence"] if t["confidence"] is not None else 3, -t["position"]))[0]
            return weakest, "review"
        return act, "review"
    if act:
        return act, "learn"
    if done:   # whole roadmap advanced: spend the time on the weakest topic
        weakest = sorted(done, key=lambda t: (t["confidence"] if t["confidence"] is not None else 3, t["position"]))[0]
        return weakest, "revise"
    return None, "learn"


def day_blocks(topic: Dict[str, Any], mode: str, kind: str, daily: int) -> List[Dict[str, Any]]:
    """The small timed blocks for one day. `url` is an external link or None."""
    name = topic["name"]
    if mode == "maintenance":
        m = day_minutes(daily, mode)
        return [{"kind": "review", "label": f"Review {name}, or watch one topic explanation", "minutes": m, "url": topic.get("learn_url")}]
    learn, practice, notes = split_minutes(daily)
    verb = "Revise" if kind == "revise" else "Learn"
    return [
        {"kind": "learn", "label": f"{verb} {name}", "minutes": learn, "url": topic.get("learn_url")},
        {"kind": "practice", "label": "Practice one linked external question" if topic.get("practice_url") else "Revisit problems you found hard", "minutes": practice, "url": topic.get("practice_url")},
        {"kind": "notes", "label": "Write short notes / pattern summary", "minutes": notes, "url": None},
    ]


def status_after_session(status: str, sessions_before: int, confidence: Optional[int]) -> str:
    """New topic status after a completed (normal) session. confidence is the learner's own 1-5 rating."""
    c, n = confidence, sessions_before + 1
    if status in ("not_started", "learning"):
        if c is not None and c <= 2:
            return "learning"                      # needs another day
        if (c is not None and c >= 4) or n >= 2:
            return "practicing"                    # moves on to the next topic
        return "learning"
    if status == "practicing":
        return "comfortable" if (c or 0) >= 5 else "revised" if (c or 0) >= 4 else "practicing"
    if status == "revised":
        return "comfortable" if (c or 0) >= 5 else "revised"
    return status


def week_bullets(topics: List[Dict[str, Any]], week: int) -> List[Dict[str, Any]]:
    ordered = sorted(topics, key=lambda x: x["position"])
    cur = [t for t in ordered if t["planned_week"] == week]
    prev = [t for t in ordered if t["planned_week"] < week]
    out = [{"text": f"Learn {t['name']}", "done": is_advanced(t["status"])} for t in cur]
    out.append({"text": "Practice selected external problems", "done": False})
    if prev:
        out.append({"text": f"Revise {prev[-1]['name']}", "done": prev[-1]["status"] in ("revised", "comfortable")})
    return out


def week_days(start: date, week: int, by_date: Dict[date, str], today: date) -> List[Dict[str, Any]]:
    """Seven day cells for the current roadmap week: done | skipped | planned | missed | upcoming."""
    first = start + timedelta(days=7 * (week - 1))
    cells = []
    for i in range(7):
        d = first + timedelta(days=i)
        st = by_date.get(d)
        if st in ("done", "skipped"):
            s = st
        elif d > today:
            s = "upcoming"
        elif d == today:
            s = "planned"
        else:
            s = "missed" if st is None or st == "planned" else st
        cells.append({"date": d.isoformat(), "label": d.strftime("%a")[0], "state": s})
    return cells


_URL = re.compile(r"^https?://[^\s<>\"']+$", re.I)


def clean_url(v: Optional[str]) -> Optional[str]:
    """None/empty clears the link. Only plain http(s) links are stored (no javascript:, data:, etc.)."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if len(v) > 500 or not _URL.match(v):
        raise ValueError("Link must be a plain http(s) URL under 500 characters.")
    return v
