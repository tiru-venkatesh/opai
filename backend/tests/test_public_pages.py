"""Public pages Google's reviewers read (landing, login, privacy) and the promises they make.

Run: cd backend && python -m pytest tests/test_public_pages.py -q
Two kinds of check: (1) the pages actually say the required things, near the top; (2) what the privacy
policy says about the AI provider stays true: no LLM prompt may include the user's email, photo or date of birth.
"""
import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")


def read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


def visible_text(html):
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---------------------------------------------------------------- landing
def test_landing_states_purpose_scope_and_links_before_the_fold():
    html = read(FRONTEND, "landing.html")
    hero = html[html.index('<section class="relative min-h-[92vh]'):html.index('<section id="product"')]
    text = visible_text(hero)
    assert "personal workspace and AI assistant for students" in text
    assert "gmail.send" in text and "cannot read your inbox" in text
    assert 'href="/privacy"' in hero and 'href="/terms"' in hero


def test_landing_has_a_google_user_data_block():
    html = read(FRONTEND, "landing.html")
    block = html[html.index('id="google-data"'):html.index('<section id="trust"')]
    text = visible_text(block)
    for needle in ("gmail.send", "Limited Use", "Google API Services User Data Policy", "NCII",
                   "never sends your Google email address or profile picture", "not used to train AI models"):
        assert needle in text, needle
    assert "https://developers.google.com/terms/api-services-user-data-policy" in block
    assert 'href="/privacy#google-data"' in block


# ---------------------------------------------------------------- login
def test_login_links_to_privacy_and_terms():
    html = read(FRONTEND, "login.html")
    gate = html[html.index('class="gate-legal"'):]
    gate = gate[:gate.index("</p>")]
    assert 'href="/privacy"' in gate and 'href="/terms"' in gate and "gmail" in gate.lower()


# ---------------------------------------------------------------- privacy policy
def test_privacy_policy_has_the_required_google_statements():
    html = read(FRONTEND, "privacy.html")
    text = visible_text(html)
    assert 'id="google-data"' in html
    for needle in ("Limited Use", "Google API Services User Data Policy", "NCII", "gmail.send",
                   "cannot read, search, list, modify or delete"):
        assert needle in text, needle


def test_privacy_policy_lists_what_goes_to_the_ai_provider():
    text = visible_text(read(FRONTEND, "privacy.html"))
    groq = text[text.index("our AI inference provider"):]
    groq = groq[:groq.index("Hosting and database providers")]
    for needle in ("your message", "excerpts", "name, course and branch, college, year and semester, skills, goals and time zone",
                   "outreach draft", "profile highlight"):
        assert needle in groq, needle
    for never in ("Google email address", "profile picture", "date of birth", "password", "Gmail access tokens"):
        assert never in groq, never


# ---------------------------------------------------------------- the promise stays true
LLM_MARKERS = ("generate_json(", "generate_text(", "chat.completions", "_llm_json(", "chat_with_tools(")
FORBIDDEN = {"email", "date_of_birth", "photo", "photo_url", "photoURL"}
USERISH = {"u", "user", "me", "profile", "usr"}


def _attrs_on_user(node):
    return [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr in FORBIDDEN
            and isinstance(n.value, ast.Name) and n.value.id in USERISH]


def test_no_llm_prompt_reads_the_users_email_dob_or_photo():
    """Every function that calls the LLM, and the KARNA context builder, must not touch these user fields."""
    files = ["attach.py", "extras_api.py", "opportunities_api.py", "pdf_timetable.py", "rag_api.py", "main.py",
             os.path.join("agent", "capture.py"), os.path.join("agent", "learn.py"), os.path.join("agent", "router.py"),
             os.path.join("agent", "orchestrator.py"), os.path.join("agent", "reminder_chat.py")]
    checked, bad = 0, []
    for rel in files:
        path = os.path.join(BACKEND, rel)
        if not os.path.exists(path):
            continue
        src = read(path)
        for fn in [n for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            seg = ast.get_source_segment(src, fn) or ""
            if any(m in seg for m in LLM_MARKERS):
                checked += 1
                bad += [f"{rel}:{fn.name} reads user.{a}" for a in _attrs_on_user(fn)]
    assert checked >= 8, f"only {checked} LLM-calling functions found; the scan may be broken"
    assert not bad, bad


def test_karna_context_builder_never_reads_email_dob_or_photo():
    src = read(BACKEND, "agent", "karna_prompt.py")
    assert not _attrs_on_user(ast.parse(src)), "karna_prompt reads a field the privacy policy says is never sent"
    assert "date_of_birth" not in src
