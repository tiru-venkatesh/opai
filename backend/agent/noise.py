"""Cheap, local check for keyboard-mash / meaningless input so it never reaches an LLM."""
from __future__ import annotations

import re

_VOWELS = set("aeiouy")
_MASH = ("asdf", "sdfs", "dfgh", "fgh", "qwer", "wert", "zxcv", "xcvb", "hjkl", "jkl;", "sdf", "dsa f")
# Short tokens that ARE meaningful for a student/builder assistant: never treat as noise.
_SHORT_OK = {
    "dsa", "os", "ml", "ai", "dl", "cn", "oop", "oops", "dbms", "sql", "git", "cpp", "c", "java", "js", "ts", "html",
    "css", "api", "aws", "gcp", "cv", "gpa", "cgpa", "sem", "exam", "exams", "quiz", "plan", "task", "tasks", "todo",
    "help", "jobs", "job", "intern", "today", "tmrw", "lab", "labs", "viva", "mid", "mids", "fees", "yes", "no", "ok",
    "okay", "sure", "stop", "undo", "list", "show", "what", "why", "how", "who", "when", "where", "ugc", "gate",
    "tcp", "udp", "http", "https", "dns", "cpu", "gpu", "ram", "rom", "ssh", "tls", "ssl", "xml", "php", "npm", "pip",
    "jwt", "crud", "rest", "ide", "jdk", "vpn", "url", "sdk", "cnn", "rnn", "svm", "knn", "gan", "nlp", "llm", "rag",
    "hmm", "pls", "plz", "tcs", "dp", "bfs", "dfs", "bst", "mst", "rdbms", "nosql", "cat", "gre", "ielts", "nptel", "mooc", "repo", "pr", "bug", "fix", "next", "done", "skip", "more", "menu",
}


def _max_consonant_run(word: str) -> int:
    best = run = 0
    for ch in word:
        if ch.isalpha() and ch not in _VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _token_is_noise(tok: str) -> bool:
    t = tok.lower()
    if len(t) < 3:
        return False
    letters = re.sub(r"[^a-z]", "", t)
    if len(letters) < 3:
        return False
    if any(m in t for m in _MASH) and len(t) >= 6:
        return True
    vr = sum(c in _VOWELS for c in letters) / len(letters)
    if len(letters) <= 5:
        return vr == 0 and t not in _SHORT_OK            # "sdf", "xzkq"
    if re.search(r"[a-z]\d+[a-z]", t) and len(t) >= 8:    # "dfasf0sdfasdf"
        return True
    if _max_consonant_run(letters) >= 5:
        return True
    return vr < 0.2 or vr > 0.75


def is_noise(message: str) -> bool:
    """True when the whole message looks like random typing."""
    text = (message or "").strip()
    if not text:
        return True
    if re.fullmatch(r"[\W_]+", text):                     # only punctuation / symbols
        return True
    toks = re.findall(r"[^\s]+", text)
    if len(toks) > 6:
        return False
    return all(_token_is_noise(t) for t in toks)


def is_short_unknown(message: str) -> bool:
    """A single very short alphabetic word we cannot place ("hihu"). Greetings/known words are excluded by caller."""
    t = (message or "").strip().lower()
    return bool(re.fullmatch(r"[a-z]{3,4}", t)) and t not in _SHORT_OK


NOISE_REPLY = ("That didn’t look like a request. Try “add an exam…”, “add a task…”, "
               "or ask a question about your notes.")


def short_unknown_reply(message: str) -> str:
    w = (message or "").strip()
    return (f"I’m not sure what “{w}” means. If you meant to say hi, hi! Otherwise tell me what you want to do — "
            "for example “add an exam…”, “add a task…”, or ask about your notes.")
