"""DSA Coach: pure logic for diagnosing weak patterns, picking the next problems and scheduling re-solves.
No database, no network, no web framework, so every rule here is unit-testable.

What this module may know about a problem: a title, a link, a platform, a pattern tag, a difficulty and how the
attempt went. It never stores a problem statement, a solution or code. Problem links in PROBLEM_BANK are plain
links to the external platform.

Rules (all deterministic, all shown to the learner):
  * An attempt ends as solved | hinted | failed. "solved" means no hints and no solution peeking; the server
    downgrades a "solved" that used hints, and a peek at the solution never counts as solved.
  * Each problem has a mastery stage 0-5. A clean re-solve climbs one stage and the next revision moves out along
    REVISION_DAYS (1, 3, 7, 14, 30). A hint costs a stage and brings it back in 2 days. A failure or a peek resets to
    stage 0 and brings it back tomorrow. "Mastered" means stage 5 AND at least two clean solves after the first try.
  * A pattern's weakness comes from recent attempts only (half-life 14 days). Re-solves count 1.5x because being
    able to redo a problem without help is the real test. Fewer than MIN_EVIDENCE attempts is "not enough data",
    never "weak".
  * Tomorrow's plan is one new problem, one revision and one mixed problem. The mixed one hides its pattern on
    purpose: the learner has to name the pattern before coding.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

REVISION_DAYS = (1, 3, 7, 14, 30)
MAX_STAGE = len(REVISION_DAYS)
HINT_RETRY_DAYS = 2
HALF_LIFE_DAYS = 14.0
LOOKBACK_DAYS = 90
MIN_EVIDENCE = 2.0                   # weighted attempts needed before a pattern can be called weak or strong
WEAK_BELOW = 0.55                    # strength below this = weak
STRONG_FROM = 0.80
RESOLVE_WEIGHT = 1.5

RESULTS = ("solved", "hinted", "failed")
PLATFORMS = ("LeetCode", "GeeksforGeeks", "Codeforces", "Other")
MISTAKES = ("wrong_pattern", "edge_case", "off_by_one", "implementation_bug", "complexity", "forgot_approach", "syntax", "time_pressure", "other")
MISTAKE_LABEL = {"wrong_pattern": "Picked the wrong pattern", "edge_case": "Missed an edge case", "off_by_one": "Off-by-one",
                 "implementation_bug": "Bug in the implementation", "complexity": "Too slow (complexity)", "forgot_approach": "Forgot the approach",
                 "syntax": "Syntax or language slip", "time_pressure": "Ran out of time", "other": "Something else"}
DIFFICULTIES = ("Easy", "Medium", "Hard")
STATES = ("new", "learning", "shaky", "solid", "mastered")

PATTERNS: Dict[str, str] = {
    "arrays-hashing": "Arrays and hashing", "prefix-sum": "Prefix sums", "two-pointers": "Two pointers", "sliding-window": "Sliding window",
    "stack-queue": "Stack and queue", "linked-list": "Linked lists", "binary-search": "Binary search", "sorting": "Sorting",
    "recursion": "Recursion", "trees": "Trees and BST", "heap": "Heaps", "intervals": "Intervals", "greedy": "Greedy",
    "backtracking": "Backtracking", "graphs": "Graphs", "dp": "Dynamic programming",
}
PATTERN_ORDER = list(PATTERNS)

# roadmap topic name (lowercase, language prefix removed) -> pattern
TOPIC_PATTERN: Dict[str, str] = {
    "arrays and strings": "arrays-hashing", "hash maps and sets": "arrays-hashing", "prefix sums": "prefix-sum",
    "two pointers": "two-pointers", "sliding window": "sliding-window", "stack and queue": "stack-queue", "linked lists": "linked-list",
    "sorting algorithms": "sorting", "binary search": "binary-search", "rotated arrays and search on answer": "binary-search",
    "binary tree traversals": "trees", "binary search trees": "trees", "heaps and priority queues": "heap", "intervals": "intervals",
    "greedy": "greedy", "subsets and permutations": "backtracking", "graph traversal (bfs and dfs)": "graphs", "topological sort": "graphs",
    "1d dynamic programming": "dp", "classic dp patterns": "dp", "recursion basics": "recursion",
}

# (slug, title, difficulty, pattern). Links only: https://leetcode.com/problems/<slug>/
PROBLEM_BANK: List[Tuple[str, str, str, str]] = [
    ("contains-duplicate", "Contains Duplicate", "Easy", "arrays-hashing"), ("valid-anagram", "Valid Anagram", "Easy", "arrays-hashing"),
    ("two-sum", "Two Sum", "Easy", "arrays-hashing"), ("group-anagrams", "Group Anagrams", "Medium", "arrays-hashing"),
    ("top-k-frequent-elements", "Top K Frequent Elements", "Medium", "arrays-hashing"), ("longest-consecutive-sequence", "Longest Consecutive Sequence", "Medium", "arrays-hashing"),
    ("range-sum-query-immutable", "Range Sum Query - Immutable", "Easy", "prefix-sum"), ("product-of-array-except-self", "Product of Array Except Self", "Medium", "prefix-sum"),
    ("subarray-sum-equals-k", "Subarray Sum Equals K", "Medium", "prefix-sum"), ("continuous-subarray-sum", "Continuous Subarray Sum", "Medium", "prefix-sum"),
    ("valid-palindrome", "Valid Palindrome", "Easy", "two-pointers"), ("two-sum-ii-input-array-is-sorted", "Two Sum II - Input Array Is Sorted", "Medium", "two-pointers"),
    ("3sum", "3Sum", "Medium", "two-pointers"), ("container-with-most-water", "Container With Most Water", "Medium", "two-pointers"),
    ("trapping-rain-water", "Trapping Rain Water", "Hard", "two-pointers"),
    ("best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock", "Easy", "sliding-window"),
    ("longest-substring-without-repeating-characters", "Longest Substring Without Repeating Characters", "Medium", "sliding-window"),
    ("longest-repeating-character-replacement", "Longest Repeating Character Replacement", "Medium", "sliding-window"),
    ("permutation-in-string", "Permutation in String", "Medium", "sliding-window"), ("minimum-window-substring", "Minimum Window Substring", "Hard", "sliding-window"),
    ("valid-parentheses", "Valid Parentheses", "Easy", "stack-queue"), ("min-stack", "Min Stack", "Medium", "stack-queue"),
    ("daily-temperatures", "Daily Temperatures", "Medium", "stack-queue"), ("evaluate-reverse-polish-notation", "Evaluate Reverse Polish Notation", "Medium", "stack-queue"),
    ("largest-rectangle-in-histogram", "Largest Rectangle in Histogram", "Hard", "stack-queue"),
    ("reverse-linked-list", "Reverse Linked List", "Easy", "linked-list"), ("merge-two-sorted-lists", "Merge Two Sorted Lists", "Easy", "linked-list"),
    ("linked-list-cycle", "Linked List Cycle", "Easy", "linked-list"), ("remove-nth-node-from-end-of-list", "Remove Nth Node From End of List", "Medium", "linked-list"),
    ("reorder-list", "Reorder List", "Medium", "linked-list"),
    ("binary-search", "Binary Search", "Easy", "binary-search"), ("search-a-2d-matrix", "Search a 2D Matrix", "Medium", "binary-search"),
    ("koko-eating-bananas", "Koko Eating Bananas", "Medium", "binary-search"), ("find-minimum-in-rotated-sorted-array", "Find Minimum in Rotated Sorted Array", "Medium", "binary-search"),
    ("search-in-rotated-sorted-array", "Search in Rotated Sorted Array", "Medium", "binary-search"),
    ("merge-sorted-array", "Merge Sorted Array", "Easy", "sorting"), ("sort-colors", "Sort Colors", "Medium", "sorting"), ("sort-an-array", "Sort an Array", "Medium", "sorting"),
    ("fibonacci-number", "Fibonacci Number", "Easy", "recursion"), ("powx-n", "Pow(x, n)", "Medium", "recursion"),
    ("maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "Easy", "trees"), ("invert-binary-tree", "Invert Binary Tree", "Easy", "trees"),
    ("diameter-of-binary-tree", "Diameter of Binary Tree", "Easy", "trees"), ("binary-tree-level-order-traversal", "Binary Tree Level Order Traversal", "Medium", "trees"),
    ("validate-binary-search-tree", "Validate Binary Search Tree", "Medium", "trees"), ("kth-smallest-element-in-a-bst", "Kth Smallest Element in a BST", "Medium", "trees"),
    ("last-stone-weight", "Last Stone Weight", "Easy", "heap"), ("kth-largest-element-in-an-array", "Kth Largest Element in an Array", "Medium", "heap"),
    ("k-closest-points-to-origin", "K Closest Points to Origin", "Medium", "heap"), ("task-scheduler", "Task Scheduler", "Medium", "heap"),
    ("find-median-from-data-stream", "Find Median from Data Stream", "Hard", "heap"),
    ("merge-intervals", "Merge Intervals", "Medium", "intervals"), ("insert-interval", "Insert Interval", "Medium", "intervals"),
    ("non-overlapping-intervals", "Non-overlapping Intervals", "Medium", "intervals"),
    ("jump-game", "Jump Game", "Medium", "greedy"), ("jump-game-ii", "Jump Game II", "Medium", "greedy"), ("gas-station", "Gas Station", "Medium", "greedy"),
    ("hand-of-straights", "Hand of Straights", "Medium", "greedy"),
    ("subsets", "Subsets", "Medium", "backtracking"), ("permutations", "Permutations", "Medium", "backtracking"), ("combination-sum", "Combination Sum", "Medium", "backtracking"),
    ("word-search", "Word Search", "Medium", "backtracking"), ("n-queens", "N-Queens", "Hard", "backtracking"),
    ("number-of-islands", "Number of Islands", "Medium", "graphs"), ("max-area-of-island", "Max Area of Island", "Medium", "graphs"),
    ("clone-graph", "Clone Graph", "Medium", "graphs"), ("rotting-oranges", "Rotting Oranges", "Medium", "graphs"),
    ("course-schedule", "Course Schedule", "Medium", "graphs"), ("pacific-atlantic-water-flow", "Pacific Atlantic Water Flow", "Medium", "graphs"),
    ("climbing-stairs", "Climbing Stairs", "Easy", "dp"), ("house-robber", "House Robber", "Medium", "dp"), ("coin-change", "Coin Change", "Medium", "dp"),
    ("unique-paths", "Unique Paths", "Medium", "dp"), ("longest-increasing-subsequence", "Longest Increasing Subsequence", "Medium", "dp"),
    ("word-break", "Word Break", "Medium", "dp"), ("longest-common-subsequence", "Longest Common Subsequence", "Medium", "dp"),
]
BANK_BY_KEY = {s: dict(key=s, title=t, difficulty=d, pattern=p, url=f"https://leetcode.com/problems/{s}/", platform="LeetCode") for s, t, d, p in PROBLEM_BANK}

_LC = re.compile(r"^https?://(?:www\.)?leetcode\.com/problems/([a-z0-9-]+)", re.I)


# ---------------------------------------------------------------- identity
def problem_key(title: Optional[str], url: Optional[str]) -> str:
    """Stable key so a second attempt of the same problem lands on the same mastery row."""
    m = _LC.match((url or "").strip())
    if m:
        return m.group(1).lower()
    t = re.sub(r"[^a-z0-9]+", "-", (title or "").strip().lower()).strip("-")
    if t in BANK_BY_KEY:
        return t
    if t:
        return t[:120]
    u = re.sub(r"[^a-z0-9]+", "-", (url or "").strip().lower()).strip("-")
    return u[:120]


def pattern_for_topic(topic_name: Optional[str]) -> Optional[str]:
    key = re.sub(r"^(python|java|c\+\+|javascript)\s+", "", (topic_name or "").strip().lower())
    return TOPIC_PATTERN.get(key)


def clean_mistakes(tags: Optional[Iterable[str]]) -> List[str]:
    out: List[str] = []
    for t in tags or []:
        if t not in MISTAKES:
            raise ValueError("Mistake must be one of: " + ", ".join(MISTAKES))
        if t not in out:
            out.append(t)
    return out[:5]


def effective_result(result: str, hints_used: int, saw_solution: bool) -> str:
    """Server-side honesty: a 'solved' that needed hints is 'hinted'; reading the solution is never 'solved'."""
    if result not in RESULTS:
        raise ValueError("result must be one of: " + ", ".join(RESULTS))
    if saw_solution and result == "solved":
        return "hinted"
    if result == "solved" and hints_used > 0:
        return "hinted"
    return result


# ---------------------------------------------------------------- mastery (one row per problem)
def next_mastery(stage: int, clean_resolves: int, attempts: int, result: str, on: date) -> Dict[str, Any]:
    """New mastery numbers after an attempt. `attempts` is the count BEFORE this one, so attempts >= 1 means a re-solve."""
    stage = max(0, min(int(stage or 0), MAX_STAGE))
    is_resolve = attempts >= 1
    if result == "solved":
        stage = min(MAX_STAGE, stage + 1)
        days = REVISION_DAYS[stage - 1]
        if is_resolve:
            clean_resolves += 1
    elif result == "hinted":
        stage = max(0, stage - 1)
        days = HINT_RETRY_DAYS
    else:
        stage, days = 0, 1
    return dict(stage=stage, clean_resolves=clean_resolves, attempts=attempts + 1, next_review=on + timedelta(days=days),
                state=mastery_state(stage, clean_resolves, attempts + 1, result))


def mastery_state(stage: int, clean_resolves: int, attempts: int, last_result: Optional[str]) -> str:
    if not attempts:
        return "new"
    if stage >= MAX_STAGE and clean_resolves >= 2:
        return "mastered"
    if last_result in ("hinted", "failed"):
        return "shaky" if attempts > 1 or last_result == "hinted" else "learning"
    if stage >= 3:
        return "solid"
    if stage == 2:
        return "shaky"
    return "learning"


def due_items(rows: List[Dict[str, Any]], on: date) -> List[Dict[str, Any]]:
    """Mastery rows to revise on `on`: most overdue first, then lowest stage first."""
    due = [r for r in rows if r.get("next_review") and r["next_review"] <= on and r.get("state") != "mastered"]
    return sorted(due, key=lambda r: (r["next_review"], r.get("stage", 0), r.get("key", "")))


# ---------------------------------------------------------------- pattern weakness
def _value(result: str) -> float:
    return {"solved": 1.0, "hinted": 0.5}.get(result, 0.0)


def pattern_stats(attempts: List[Dict[str, Any]], on: date) -> Dict[str, Dict[str, Any]]:
    """Per pattern: strength 0-1 (recency weighted), evidence, label and the mistakes behind it.
    Each attempt: {pattern, result, on (date), is_resolve (bool), mistakes (list)}."""
    acc: Dict[str, Dict[str, Any]] = {}
    for a in attempts:
        p = a.get("pattern")
        if p not in PATTERNS:
            continue
        age = (on - a["on"]).days
        if age < 0 or age > LOOKBACK_DAYS:
            continue
        w = math.pow(0.5, age / HALF_LIFE_DAYS) * (RESOLVE_WEIGHT if a.get("is_resolve") else 1.0)
        s = acc.setdefault(p, dict(num=0.0, den=0.0, n=0, solved=0, hinted=0, failed=0, mistakes={}, last=None))
        s["num"] += w * _value(a["result"])
        s["den"] += w
        s["n"] += 1
        s[a["result"]] += 1
        s["last"] = max(s["last"], a["on"]) if s["last"] else a["on"]
        for m in a.get("mistakes") or []:
            s["mistakes"][m] = s["mistakes"].get(m, 0) + 1
    out: Dict[str, Dict[str, Any]] = {}
    for p in PATTERN_ORDER:
        s = acc.get(p)
        if not s:
            out[p] = dict(pattern=p, name=PATTERNS[p], attempts=0, strength=None, weakness=None, label="untested", evidence=0.0,
                          solved=0, hinted=0, failed=0, top_mistakes=[], last_attempt=None)
            continue
        strength = s["num"] / s["den"] if s["den"] else 0.0
        label = "not enough data" if s["den"] < MIN_EVIDENCE else "weak" if strength < WEAK_BELOW else "strong" if strength >= STRONG_FROM else "steady"
        top = sorted(s["mistakes"].items(), key=lambda kv: (-kv[1], kv[0]))[:2]
        out[p] = dict(pattern=p, name=PATTERNS[p], attempts=s["n"], strength=round(strength, 3), weakness=round(100 * (1 - strength)), label=label,
                      evidence=round(s["den"], 2), solved=s["solved"], hinted=s["hinted"], failed=s["failed"],
                      top_mistakes=[dict(tag=k, label=MISTAKE_LABEL[k], count=v) for k, v in top], last_attempt=s["last"].isoformat())
    return out


def weakest_patterns(stats: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Patterns labelled weak, worst first. Never includes 'not enough data' or untested patterns."""
    return sorted((s for s in stats.values() if s["label"] == "weak"), key=lambda s: (s["strength"], -s["evidence"], s["pattern"]))


def resolve_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Can the learner re-solve without help? Counts repeat attempts only."""
    repeats = [r for r in rows if r.get("is_resolve")]
    clean = sum(1 for r in repeats if r["result"] == "solved")
    return dict(resolves=len(repeats), clean=clean, rate=round(100 * clean / len(repeats)) if repeats else None)


# ---------------------------------------------------------------- picking problems
def _difficulty_for(strength: Optional[float]) -> str:
    if strength is None or strength < 0.5:
        return "Easy"
    return "Medium" if strength < 0.85 else "Hard"


def pick_new(pattern: str, strength: Optional[float], seen: Iterable[str], avoid: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """An unseen bank problem for the pattern at a difficulty that fits the current strength. Falls back to the
    nearest difficulty, then to any unseen problem of the pattern."""
    seen, avoid = set(seen), set(avoid)
    pool = [p for p in PROBLEM_BANK if p[3] == pattern and p[0] not in seen and p[0] not in avoid]
    if not pool:
        return None
    want = DIFFICULTIES.index(_difficulty_for(strength))
    pool.sort(key=lambda p: (abs(DIFFICULTIES.index(p[2]) - want), DIFFICULTIES.index(p[2]), p[0]))
    return dict(BANK_BY_KEY[pool[0][0]])


def _pick_new_pattern(stats: Dict[str, Dict[str, Any]], roadmap_pattern: Optional[str], seen: set, avoid_patterns: Iterable[str] = ()) -> Tuple[Optional[str], str]:
    avoid_patterns = set(avoid_patterns)
    for s in weakest_patterns(stats):
        if s["pattern"] not in avoid_patterns and pick_new(s["pattern"], s["strength"], seen):
            return s["pattern"], f"{s['name']} is your weakest pattern right now ({s['solved']} solved, {s['hinted']} with hints, {s['failed']} failed recently)."
    if roadmap_pattern and roadmap_pattern not in avoid_patterns and pick_new(roadmap_pattern, stats.get(roadmap_pattern, {}).get("strength"), seen):
        return roadmap_pattern, f"{PATTERNS[roadmap_pattern]} is where your roadmap is right now."
    for p in PATTERN_ORDER:                                           # least practised first, in roadmap order
        if p not in avoid_patterns and stats[p]["attempts"] == 0 and pick_new(p, None, seen):
            return p, f"You have not tried {PATTERNS[p]} yet."
    rest = sorted((s for s in stats.values() if s["pattern"] not in avoid_patterns and pick_new(s["pattern"], s["strength"], seen)),
                  key=lambda s: (s["strength"] if s["strength"] is not None else 0, s["pattern"]))
    return (rest[0]["pattern"], f"{rest[0]['name']} has the most room to grow.") if rest else (None, "")


RECALL_NEW = "Before you open it: say in one line how you would start. Then solve without hints and note where you got stuck."
RECALL_REVISION = "Before you open it: write the approach from memory in two lines. Then solve it again without hints."
RECALL_MIXED = "The pattern is hidden on purpose. Name it first, in one line, then solve. Naming it is the skill being trained."


def plan_tomorrow(stats: Dict[str, Dict[str, Any]], mastery: List[Dict[str, Any]], seen_keys: Iterable[str], on: date,
                  roadmap_pattern: Optional[str] = None, minutes: int = 60) -> Dict[str, Any]:
    """Tomorrow: one new, one revision, one mixed. `on` is the day the plan is FOR."""
    seen = set(seen_keys)
    items: List[Dict[str, Any]] = []
    used_keys: set = set()
    used_patterns: set = set()

    # 1. revision: most overdue first; if nothing is due, the shakiest problem that has not been seen for a few days
    due = due_items(mastery, on)
    rev = due[0] if due else None
    if rev is None:
        shaky = [r for r in mastery if r.get("state") in ("shaky", "learning") and r.get("last_attempt") and (on - r["last_attempt"]).days >= 1]
        rev = sorted(shaky, key=lambda r: (r.get("stage", 0), r["last_attempt"], r["key"]))[0] if shaky else None
    if rev:
        overdue = (on - rev["next_review"]).days if rev.get("next_review") else 0
        why = (("Due for a re-solve" if overdue <= 0 else f"Overdue by {overdue} day" + ("s" if overdue != 1 else "")) + ": you solved it with " +
               ("hints" if rev.get("last_result") == "hinted" else "trouble" if rev.get("last_result") == "failed" else "no help") + " last time.")
        items.append(dict(slot="revision", title=rev["title"], url=rev.get("url"), key=rev["key"], pattern=rev["pattern"], pattern_name=PATTERNS.get(rev["pattern"], rev["pattern"]),
                          difficulty=rev.get("difficulty"), reason=why, recall=RECALL_REVISION, reveal_pattern=True, minutes=max(10, minutes // 3)))
        used_keys.add(rev["key"])
        used_patterns.add(rev["pattern"])
    else:
        items.append(dict(slot="revision", title=None, reason="Nothing is due for revision yet. Solve something new first and it will show up here.", reveal_pattern=True))

    # 2. new problem
    pat, why = _pick_new_pattern(stats, roadmap_pattern, seen | used_keys)
    new = pick_new(pat, stats[pat]["strength"], seen | used_keys) if pat else None
    if new:
        items.append(dict(slot="new", title=new["title"], url=new["url"], key=new["key"], pattern=pat, pattern_name=PATTERNS[pat], difficulty=new["difficulty"],
                          reason=why, recall=RECALL_NEW, reveal_pattern=True, minutes=max(15, minutes // 2)))
        used_keys.add(new["key"])
        used_patterns.add(pat)
    else:
        items.append(dict(slot="new", title=None, reason="You have tried every problem in the built-in list. Pick your own and log it.", reveal_pattern=True))

    # 3. mixed: a different pattern, pattern hidden until the learner names it
    mpat, _ = _pick_new_pattern(stats, roadmap_pattern, seen | used_keys, used_patterns)
    mixed = pick_new(mpat, stats[mpat]["strength"], seen | used_keys) if mpat else None
    if mixed:
        items.append(dict(slot="mixed", title=mixed["title"], url=mixed["url"], key=mixed["key"], pattern=mpat, pattern_name=PATTERNS[mpat], difficulty=mixed["difficulty"],
                          reason="Mixed practice: a different pattern, so you practise choosing the pattern instead of following the topic.",
                          recall=RECALL_MIXED, reveal_pattern=False, minutes=max(10, minutes // 4)))
    else:
        items.append(dict(slot="mixed", title=None, reason="No unseen problem left for a different pattern.", reveal_pattern=False))
    order = {"new": 0, "revision": 1, "mixed": 2}
    return dict(date=on.isoformat(), items=sorted(items, key=lambda i: order[i["slot"]]))


# ---------------------------------------------------------------- practice streak and reminders
def practice_days(days: Iterable[date]) -> List[date]:
    return sorted(set(days))


def practice_streak(days: Iterable[date], today: date) -> Dict[str, Any]:
    """Consecutive calendar days with at least one attempt. Today is still open: an empty today does not break it."""
    ds = set(days)
    done_today = today in ds
    cur, d = 0, today if done_today else today - timedelta(days=1)
    while d in ds:
        cur += 1
        d -= timedelta(days=1)
    longest = run = 0
    prev: Optional[date] = None
    for x in sorted(ds):
        run = run + 1 if prev and (x - prev).days == 1 else 1
        longest = max(longest, run)
        prev = x
    last = max((x for x in ds if x <= today), default=None)
    gap = (today - last).days if last else None
    return dict(current=cur, longest=longest, done_today=done_today, at_risk=bool(cur and not done_today), days_since_last=gap)


# opt-in reminder defaults
DEFAULT_TIMES = ("20:00", "22:30", "23:45")
MAX_PER_DAY = 3
RECOVERY_AFTER_DAYS = 3
DEFAULT_QUIET = ("00:00", "07:00")                  # nothing is sent between these local times (the window may wrap midnight)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_quiet_hours(local_hhmm: str, start: str, end: str) -> bool:
    """True when `local_hhmm` is inside [start, end). Handles windows that wrap midnight (23:00 -> 07:00) and an empty window (start == end)."""
    t, a, b = _minutes(local_hhmm), _minutes(start), _minutes(end)
    if a == b:
        return False
    return a <= t < b if a < b else (t >= a or t < b)


def nudge(*, streak: Dict[str, Any], slot: int, sent_today: int, local_hhmm: str, quiet: Tuple[str, str] = DEFAULT_QUIET, max_per_day: int = MAX_PER_DAY) -> Optional[Dict[str, str]]:
    """Decide what (if anything) to send for reminder slot `slot` (0 = first of the day). Returns {title, body, tone} or None.

    Never sent: when today is already done, during quiet hours, past the daily cap, or when the learner has been away for
    RECOVERY_AFTER_DAYS or more (they get a single gentle comeback note in the first slot instead of pressure)."""
    if streak["done_today"] or sent_today >= max_per_day or in_quiet_hours(local_hhmm, quiet[0], quiet[1]):
        return None
    away = streak.get("days_since_last")
    if away is not None and away >= RECOVERY_AFTER_DAYS:
        if slot > 0:
            return None
        return dict(tone="comeback", title="Ready for a light restart?",
                    body="No pressure. One easy problem you already know takes about 10 minutes and gets you back in the rhythm.")
    cur = streak["current"]
    if slot == 0:
        return dict(tone="gentle", title="Today's DSA practice",
                    body=(f"You are on a {cur}-day streak. One problem keeps it going." if cur else "One problem today is enough. Open tomorrow's plan in OPAI."))
    if not cur:
        return None                                                  # no streak to protect: the gentle note was enough
    if slot == 1:
        return dict(tone="risk", title=f"Your {cur}-day streak is open",
                    body="You have not logged a problem today. Even one easy revision counts once you log it.")
    return dict(tone="last", title="Last call for today",
                body=f"Log one problem before midnight to keep your {cur}-day streak. Skip it if today is a rest day.")
