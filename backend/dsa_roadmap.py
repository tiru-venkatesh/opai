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
    at most MAINT_MINUTES (MAINT_MINUTES_CLOSE when the exam is within CLOSE_EXAM_DAYS), review only, no new heavy
    topic. The user can always override (Normal / Maintenance / Paused). "Paused" generates no DSA blocks.
  * Spaced revision: every completed session or review sets the topic's next review date from the learner's own
    confidence (REVIEW_DAYS). Due reviews form the Revision Queue; a revision slot is inserted after
    REVISION_EVERY learn sessions in a row.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

WEEKS = 12                        # "90-day roadmap" = 12 weeks
EXAM_WINDOW_DAYS = 7              # exam within a week -> maintenance (light revision only)
CLOSE_EXAM_DAYS = 3               # exam within 3 days -> even lighter
MAINT_MINUTES = 20
MAINT_MINUTES_CLOSE = 15
REVISION_EVERY = 2                # after 2 learn sessions in a row, a due revision takes the next slot
REVIEW_DAYS = {1: 1, 2: 1, 3: 3, 4: 7, 5: 14}   # confidence -> days until the next review
STATUSES = ("not_started", "learning", "practicing", "revised", "comfortable")
STATUS_LABEL = {"not_started": "Not started", "learning": "Learning", "practicing": "Practicing",
                "revised": "Revised", "comfortable": "Comfortable"}
ADVANCED = {"practicing", "revised", "comfortable"}
LANGUAGES = ("Python", "Java", "C++", "JavaScript")
GOALS = ("Placement preparation", "Internship preparation", "Learn DSA from basics", "Interview revision")
LEGACY_GOALS = ("Internship interviews", "Strengthen fundamentals")      # accepted for plans created before the refinement
LEVELS = ("Starting from basics", "Know syntax, weak at DSA", "Already know basic DSA", "Revising for interviews")
MODES = ("auto", "normal", "maintenance", "paused")
OUTCOMES = ("completed", "partial", "could_not_start")
DIFFICULTY = ("concept", "pattern", "implementation", "time", "resource_unclear", "need_practice", "nothing")

LEARN_URL = "https://neetcode.io/roadmap"
GFG_ROADMAP = "https://www.geeksforgeeks.org/dsa/complete-roadmap-to-learn-dsa-from-scratch/"


def _lc(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


# (phase no, name, [first week, last week], [(topic name, practice link or None)])
PHASES: List[Tuple[int, str, Tuple[int, int], List[Tuple[str, Optional[str]]]]] = [
    (1, "Foundation", (1, 2), [("{lang} basics", _lc("fizz-buzz")), ("Big-O", _lc("contains-duplicate")), ("Recursion basics", _lc("fibonacci-number")), ("Foundation review", None)]),
    (2, "Arrays and Hashing", (3, 3), [("Arrays and strings", _lc("contains-duplicate")), ("Hash maps and sets", _lc("two-sum")), ("Prefix sums", _lc("product-of-array-except-self"))]),
    (3, "Two Pointers and Sliding Window", (4, 4), [("Two pointers", _lc("valid-palindrome")), ("Sliding window", _lc("best-time-to-buy-and-sell-stock"))]),
    (4, "Stack, Queue, and Linked Lists", (5, 5), [("Stack and queue", _lc("valid-parentheses")), ("Linked lists", _lc("reverse-linked-list"))]),
    (5, "Binary Search and Sorting", (6, 6), [("Sorting algorithms", _lc("sort-an-array")), ("Binary search", _lc("binary-search")), ("Rotated arrays and search on answer", _lc("search-in-rotated-sorted-array"))]),
    (6, "Trees and BST", (7, 7), [("Binary tree traversals", _lc("maximum-depth-of-binary-tree")), ("Binary search trees", _lc("validate-binary-search-tree"))]),
    (7, "Heaps, Intervals, and Greedy", (8, 8), [("Heaps and priority queues", _lc("kth-largest-element-in-an-array")), ("Intervals", _lc("merge-intervals")), ("Greedy", _lc("jump-game"))]),
    (8, "Backtracking", (9, 9), [("Subsets and permutations", _lc("subsets"))]),
    (9, "Graphs", (10, 10), [("Graph traversal (BFS and DFS)", _lc("number-of-islands")), ("Topological sort", _lc("course-schedule"))]),
    (10, "Dynamic Programming", (11, 11), [("1D dynamic programming", _lc("climbing-stairs")), ("Classic DP patterns", _lc("coin-change"))]),
    (11, "Revision and Interview Preparation", (12, 12), [("Revise weakest topics", None), ("Pattern summary sheet", None)]),
]


def weeks_for(daily: int) -> int:
    """Honest roadmap length from daily time: 20-25 min -> 18 weeks, 30 -> 16, 45 -> 14, 60 -> 12, 90+ -> 10."""
    d = int(daily)
    return 18 if d <= 25 else 16 if d <= 35 else 14 if d <= 50 else 12 if d < 90 else 10


def scaled(a: int, b: int, weeks: int = WEEKS) -> Tuple[int, int]:
    """A phase's week range stretched/squeezed from the 12-week base to `weeks`, still contiguous."""
    lo = (a - 1) * weeks // WEEKS + 1
    hi = max(lo, b * weeks // WEEKS)
    return lo, hi


def build_topics(language: str = "Python", level: str = "Starting from basics", today: Optional[date] = None, weeks: int = WEEKS) -> List[Dict[str, Any]]:
    """Flat, ordered topic list for a new roadmap. Links are only defaults; the user can edit them.

    `level` only sets the starting point: topics the learner already knows are marked 'practicing' (advanced,
    confidence 3) so the roadmap opens at the first topic they still need. They are NOT deleted; they come back
    through spaced revision. 'Revising for interviews' marks everything as revised and staggers the reviews."""
    out = _build(language, weeks)
    today = today or date.today()
    skip_through = {"Know syntax, weak at DSA": 0, "Already know basic DSA": 2}.get(level)   # phase numbers fully skipped
    if level == "Know syntax, weak at DSA":
        for t in out[:1]:
            t.update(status="practicing", confidence=3, next_review=today + timedelta(days=3))
    elif skip_through:
        for t in out:
            if t["phase_no"] <= skip_through:
                t.update(status="practicing", confidence=3, next_review=today + timedelta(days=3 + t["position"] // 3))
    elif level == "Revising for interviews":
        for t in out:
            t.update(status="revised", confidence=3, next_review=today + timedelta(days=t["position"] // 3))
    return out


def _build(language: str, weeks: int = WEEKS) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pos = 0
    for no, name, (a, b), topics in PHASES:
        a, b = scaled(a, b, weeks)
        n = len(topics)
        span = b - a + 1
        for i, (tname, practice) in enumerate(topics):
            out.append(dict(position=pos, phase_no=no, phase=name, name=tname.replace("{lang}", language),
                            planned_week=a + (i * span) // n, status="not_started", confidence=None, next_review=None,
                            learn_url=LEARN_URL, practice_url=practice, notes=""))
            pos += 1
    return out


def phase_weeks(no: int, weeks: int = WEEKS) -> Tuple[int, int]:
    return scaled(*next(p[2] for p in PHASES if p[0] == no), weeks)


def planned_weeks(language: str, weeks: int) -> List[int]:
    """planned_week for every topic position at a given roadmap length (used when daily time changes)."""
    return [t["planned_week"] for t in _build(language, weeks)]



# ---------------------------------------------------------------- roadmap tracks
# A track is a preset over (goal, level, daily minutes). It is not stored: it is derived from the plan, so no migration is needed.
TRACKS: List[Dict[str, Any]] = [
    dict(key="foundation", name="Foundation Track", best_for="Beginner or weak programming basics", goal="Learn DSA from basics", level="Starting from basics", minutes=30, minutes_range=(20, 35)),
    dict(key="placement", name="Placement Core", best_for="Basic coding ability, aiming for placements", goal="Placement preparation", level="Know syntax, weak at DSA", minutes=45, minutes_range=(36, 90)),
    dict(key="internship", name="Internship Sprint", best_for="An internship or assessment is coming up", goal="Internship preparation", level="Know syntax, weak at DSA", minutes=60, minutes_range=(45, 180)),
    dict(key="interview", name="Interview Revision", best_for="Already knows the fundamentals", goal="Interview revision", level="Revising for interviews", minutes=45, minutes_range=(30, 90)),
]
TRACK_BY_KEY = {t["key"]: t for t in TRACKS}


def recommend_track(goal: str, level: str, daily: int) -> str:
    """Track key for an answer set. Level beats goal for beginners: weak basics always start on Foundation."""
    if level == "Starting from basics" or goal in ("Learn DSA from basics", "Strengthen fundamentals"):
        return "foundation"
    if goal == "Interview revision" or goal == "Interview" or level == "Revising for interviews":
        return "interview"
    if goal in ("Internship preparation", "Internship interviews") and daily >= 45:
        return "internship"
    return "placement"


def track_summary(goal: str, level: str, daily: int) -> Dict[str, Any]:
    """Recommendation shown to the learner, with an honest pace note (never promises more than the time allows)."""
    t = TRACK_BY_KEY[recommend_track(goal, level, daily)]
    weeks = weeks_for(daily)
    note = ""
    if daily < 45 and t["key"] in ("placement", "internship"):
        note = f"At {daily} min/day the full roadmap takes about {weeks} weeks. Aim for 45+ min/day if your target date is close."
    elif daily >= 90 and t["key"] == "foundation":
        note = "You have time to spare: if the basics feel easy, switch to Placement Core."
    return dict(key=t["key"], name=t["name"], best_for=t["best_for"], weeks=weeks, minutes=daily, note=note)



def weekly_review(topics: List[Dict[str, Any]], rows: List[Dict[str, Any]], planned: int, week: int, today: date,
                  pace_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Summary of the current roadmap week. `rows` = this week's sessions: {topic_id, status, outcome, confidence}.
    A session only counts when it was really done (could_not_start is logged but not counted). Never shames an empty week."""
    byid = {t["id"]: t for t in topics}
    done = [r for r in rows if r.get("status") == "done" and r.get("outcome") != "could_not_start"]
    pace_info = pace_info or pace(topics, week)
    studied: Dict[str, int] = {}
    for r in done:
        c = r.get("confidence") or (byid.get(r["topic_id"]) or {}).get("confidence")
        if c and r["topic_id"] in byid:
            studied[r["topic_id"]] = c
    strongest = max(studied.items(), key=lambda kv: kv[1], default=None)
    weakest = min(studied.items(), key=lambda kv: kv[1], default=None)
    out: Dict[str, Any] = dict(week=week, completed=len(done), planned=planned, empty=not done, pace=pace_info["state"], pace_message=pace_info["message"],
                               strongest=None, needs_attention=None, next_week=[], options=[])
    if strongest:
        out["strongest"] = dict(name=byid[strongest[0]]["name"], confidence=strongest[1])
    if weakest and weakest[1] <= 3 and (not strongest or weakest[0] != strongest[0]):
        out["needs_attention"] = dict(name=byid[weakest[0]]["name"], confidence=weakest[1])
    if out["empty"]:
        out["message"] = "No DSA sessions were completed this week. Do not restart the roadmap: your progress and revision dates are kept."
        out["options"] = [dict(id="gentle", label="Restart gently with 20 min"), dict(id="target", label="Move target date"), dict(id="pause", label="Pause until exams end")]
        return out
    nxt: List[str] = []
    if out["needs_attention"]:
        nxt.append(f"Finish {out['needs_attention']['name']}")
    for t in sorted(topics, key=lambda x: x["position"]):
        if len(nxt) >= 2:
            break
        if t["planned_week"] == week + 1 and not is_advanced(t["status"]):
            nxt.append(f"Start {t['name']}")
    due = due_reviews(topics, today + timedelta(days=7))
    if due and len(nxt) < 3:
        nxt.append(f"Review {due[0]['name']}")
    out["next_week"] = nxt[:3] or ["Keep going with the current topic"]
    out["message"] = f"Completed {len(done)} of {planned} planned sessions."
    return out


def split_minutes(daily: int) -> Tuple[int, int, int]:
    """(learn, practice, notes). 65 -> (25, 30, 10)."""
    daily = max(15, int(daily))
    notes = max(5, int(daily * 0.15 / 5 + 0.5) * 5)
    learn = max(5, int(daily * 0.38 / 5 + 0.5) * 5)
    practice = max(5, daily - learn - notes)
    return learn, practice, notes


def week_number(start: date, today: date, weeks: int = WEEKS) -> Tuple[int, bool]:
    """(week 1..weeks, overrun). overrun = past the planned roadmap length."""
    w = (today - start).days // 7 + 1
    return min(weeks, max(1, w)), w > weeks


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
    if override == "paused":
        return "paused", "DSA is paused (set by you). No DSA blocks are generated; your progress is kept."
    if override == "maintenance":
        return "maintenance", "Maintenance mode is on (set by you)."
    if override == "normal":
        return "normal", ""
    if exam_days is not None and 0 <= exam_days <= EXAM_WINDOW_DAYS:
        when = "today" if exam_days == 0 else "tomorrow" if exam_days == 1 else f"in {exam_days} days"
        return "maintenance", f"Exam {when}. DSA is in maintenance so semester exams come first."
    return "normal", ""


def day_minutes(daily: int, mode: str, exam_days: Optional[int] = None) -> int:
    if mode == "paused":
        return 0
    if mode == "maintenance":
        close = exam_days is not None and 0 <= exam_days <= CLOSE_EXAM_DAYS
        return min(MAINT_MINUTES_CLOSE if close else MAINT_MINUTES, int(daily))
    return int(daily)


def next_review_date(confidence: Optional[int], from_day: date) -> date:
    """Spaced revision: confidence 1-2 -> tomorrow, 3 -> 3 days, 4 -> 7 days, 5 -> 14 days. Unrated counts as 3."""
    c = confidence if confidence in REVIEW_DAYS else 3
    return from_day + timedelta(days=REVIEW_DAYS[c])


def review_minutes(daily: int, confidence: Optional[int]) -> int:
    """A revision is short: 20 min when shaky, 15 when okay, 10 when strong, never more than the day's time."""
    m = 20 if (confidence or 3) <= 2 else 15 if confidence == 3 else 10
    return max(5, min(m, int(daily)))


def due_reviews(topics: List[Dict[str, Any]], today: date) -> List[Dict[str, Any]]:
    """Topics whose review date has come, most overdue first, then weakest first."""
    due = [t for t in topics if t.get("next_review") and t["next_review"] <= today]
    return sorted(due, key=lambda t: (t["next_review"], t["confidence"] if t["confidence"] is not None else 3, t["position"]))


def week_plan(days_per_week: int) -> Dict[str, int]:
    """Weekly mix: e.g. 6 days -> 3 learning, 2 revision, 1 reflection."""
    d = max(1, min(int(days_per_week), 7))
    rev = 2 if d >= 5 else 1 if d >= 3 else 0
    refl = 1 if d >= 4 else 0
    return {"learning": d - rev - refl, "revision": rev, "reflection": refl}


def pick_topic(topics: List[Dict[str, Any]], mode: str, due: Optional[List[Dict[str, Any]]] = None,
               learn_streak: int = 0) -> Tuple[Optional[Dict[str, Any]], str]:
    """Topic for the day and why. Maintenance never starts a new topic and reviews what is due first.
    In normal mode a due revision takes the slot after REVISION_EVERY learn sessions in a row."""
    ordered = sorted(topics, key=lambda x: x["position"])
    act = active_topic(ordered)
    done = [t for t in ordered if is_advanced(t["status"])]
    due = due or []
    if mode == "paused":
        return None, "learn"
    if mode == "maintenance":
        if due:
            return due[0], "review"
        if done:
            weakest = sorted(done, key=lambda t: (t["confidence"] if t["confidence"] is not None else 3, -t["position"]))[0]
            return weakest, "review"
        return act, "review"
    if due and (learn_streak >= REVISION_EVERY or not act):
        return due[0], "revise"
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
    if kind == "revise":                       # spaced revision: recall first, then one external example if needed
        recall = max(5, daily // 2)
        return [
            {"kind": "recall", "label": f"Recall {name} without notes and explain the pattern", "minutes": recall, "url": None},
            {"kind": "revision", "label": "Open one external example if you got stuck", "minutes": max(5, daily - recall), "url": topic.get("practice_url") or topic.get("learn_url")},
        ]
    learn, practice, notes = split_minutes(daily)
    if not int(topic.get("sessions_done") or 0):      # concept first: external practice only after the first session
        return [
            {"kind": "learn", "label": f"Learn {name}", "minutes": learn + practice, "url": topic.get("learn_url")},
            {"kind": "notes", "label": "Write what you understood in your own words", "minutes": notes, "url": None},
        ]
    return [
        {"kind": "learn", "label": f"Learn {name}", "minutes": learn, "url": topic.get("learn_url")},
        {"kind": "practice", "label": "Optional external practice" if topic.get("practice_url") else "Revisit what you found hard", "minutes": practice, "url": topic.get("practice_url")},
        {"kind": "notes", "label": "Write short notes / pattern summary", "minutes": notes, "url": None},
    ]


PHASE_WHY = {
    1: "later topics need comfort with loops, functions, lists and how to reason about cost",
    2: "most interview patterns start with fast lookup and counting",
    3: "these two patterns remove nested loops from array and string problems",
    4: "they teach how data is linked and ordered in memory",
    5: "ordered search shows up in many problems once data is sorted",
    6: "trees build on recursion and prepare you for graphs",
    7: "they handle scheduling and top-k choices that appear in interviews",
    8: "it is recursion applied to choices, a bridge to graphs and DP",
    9: "graphs combine traversal, recursion and queues",
    10: "DP needs recursion and patterns you already studied",
    11: "this is where weak topics get fixed before interviews",
}


def why_now(topic: Dict[str, Any], kind: str, mode: str) -> str:
    n = topic["name"]
    if mode == "maintenance":
        return "Exams come first, so DSA stays light: only revise, no new heavy topic."
    if kind in ("revise", "review"):
        return f"{n} is due for recall. A short review now keeps it from fading."
    return f"{n} is next because {PHASE_WHY.get(topic.get('phase_no'), 'it follows the roadmap order')}."


def lock_states(topics: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Per topic: done | current | next | later. Later topics say what unlocks them (user can still mark them known)."""
    out: Dict[str, Dict[str, str]] = {}
    seen_current, seen_next, prev = False, False, None
    for t in sorted(topics, key=lambda x: x["position"]):
        if is_advanced(t["status"]):
            out[t["id"]] = {"state": "done", "why": ""}
        elif not seen_current:
            seen_current = True
            out[t["id"]] = {"state": "current", "why": ""}
        elif not seen_next:
            seen_next = True
            out[t["id"]] = {"state": "next", "why": ""}
        else:
            out[t["id"]] = {"state": "later", "why": f"Opens after {prev}" if prev else ""}
        prev = t["name"]
    return out


def status_after_session(status: str, sessions_before: int, confidence: Optional[int], outcome: str = "completed") -> str:
    """New topic status after a completed (normal) session. confidence is the learner's own 1-5 rating.
    A partly completed session never advances the topic."""
    if outcome == "partial" and status in ("not_started", "learning"):
        return "learning"
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
    out.append({"text": "Optional: external practice for finished topics", "done": False})
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


def next_milestone(topics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Finish the current phase. Estimate = sessions still needed for its unfinished topics (2 per topic)."""
    act = active_topic(topics)
    if not act:
        return {"text": "Roadmap complete. Keep revising on schedule.", "sessions_remaining": 0}
    left = [t for t in topics if t["phase_no"] == act["phase_no"] and not is_advanced(t["status"])]
    n = sum(max(1, 2 - int(t.get("sessions_done") or 0)) for t in left)
    return {"text": f"Complete {act['phase']}", "sessions_remaining": n}


def clean_tags(tags: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for t in tags or []:
        if t not in DIFFICULTY:
            raise ValueError("Difficulty must be one of: " + ", ".join(DIFFICULTY))
        if t not in out:
            out.append(t)
    return out


# ---------------------------------------------------------------- resource preferences (inherited by every topic)
LEARN_SOURCES = {"NeetCode": LEARN_URL, "YouTube": None, "GeeksforGeeks": GFG_ROADMAP, "Custom": None}
PRACTICE_SOURCES = {"LeetCode": "https://leetcode.com/problemset/", "Codeforces": "https://codeforces.com/problemset",
                    "GeeksforGeeks": "https://www.geeksforgeeks.org/explore", "Custom": None}
NOTES_SOURCES = ("OPAI notes", "Notion", "Google Drive", "Custom")
DEFAULT_RESOURCES = {"learn": {"source": "NeetCode", "url": None}, "practice": {"source": "LeetCode", "url": None},
                     "notes": {"source": "OPAI notes", "url": None}}
_CHOICES = {"learn": tuple(LEARN_SOURCES), "practice": tuple(PRACTICE_SOURCES), "notes": NOTES_SOURCES}


def clean_resources(cur: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a partial update into the stored preferences. Custom needs a link; Notion/Drive may carry an optional link."""
    out = {k: dict(v) for k, v in DEFAULT_RESOURCES.items()}
    for k, v in (cur or {}).items():
        if k in out and isinstance(v, dict):
            out[k].update({x: v.get(x) for x in ("source", "url")})
    for k, v in (new or {}).items():
        if k not in out or not isinstance(v, dict):
            raise ValueError("Unknown resource setting")
        src = v.get("source", out[k]["source"])
        if src not in _CHOICES[k]:
            raise ValueError(f"{k} source must be one of: " + ", ".join(_CHOICES[k]))
        url = clean_url(v.get("url")) if "url" in v else out[k]["url"]
        if src == "Custom" and not url:
            raise ValueError("Custom needs a link (https://…)")
        out[k] = {"source": src, "url": url if src in ("Custom", "Notion", "Google Drive") else None}
    return out


def default_links(language: str) -> List[Tuple[Optional[str], Optional[str]]]:
    return [(t["learn_url"], t["practice_url"]) for t in _build(language)]


def source_url(kind: str, res: Optional[Dict[str, Any]], topic_name: str) -> Optional[str]:
    from urllib.parse import quote_plus
    r = {**DEFAULT_RESOURCES[kind], **((res or {}).get(kind) or {})}
    if r["source"] == "Custom":
        return r["url"]
    if kind == "learn" and r["source"] == "YouTube":
        return "https://www.youtube.com/results?search_query=" + quote_plus(topic_name + " DSA")
    return (LEARN_SOURCES if kind == "learn" else PRACTICE_SOURCES)[r["source"]]


def effective_links(topic: Dict[str, Any], default: Tuple[Optional[str], Optional[str]], res: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """A link the learner edited on the topic wins; untouched topics inherit the chosen sources (never a fixed problem)."""
    learn, practice = topic.get("learn_url"), topic.get("practice_url")
    if not learn or learn == default[0]:
        learn = source_url("learn", res, topic["name"])
    if practice == default[1]:                       # untouched default (a specific problem) -> the chosen practice source
        practice = source_url("practice", res, topic["name"]) if default[1] else None
    return learn, practice
