"""Tenglish (Telugu+English) + Telugu-script chat capture. Pure functions, no DB. Run: python -m pytest tests -q"""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from agent.capture import detect, heuristic_fields, parse_date

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
YEAR_OR_NEXT = lambda m, d: (lambda x: (x if x >= date.today() else x.replace(year=x.year + 1)).isoformat())(date(date.today().year, m, d))

ADDS = [
    ("oka project add cheyyi KARNA RAG ani, FastAPI React vadi", "create_project", {"title": "KARNA RAG", "tech_stack": ["FastAPI", "React"]}),
    ("KARNA RAG ane project pettu, FastAPI React tho", "create_project", {"title": "KARNA RAG", "tech_stack": ["FastAPI", "React"]}),
    ("ఒక ప్రాజెక్ట్ జోడించు KARNA RAG అని, FastAPI React వాడి", "create_project", {"title": "KARNA RAG", "tech_stack": ["FastAPI", "React"]}),
    ("OS exam undi 20 Nov ki", "create_academic", {"subject": "OS", "exam_date": YEAR_OR_NEXT(11, 20)}),
    ("Operating Systems exam add cheyyi repu", "create_academic", {"subject": "Operating Systems", "exam_date": D(1)}),
    ("exam pettu DBMS 30th Oct varaku, high priority", "create_academic", {"subject": "DBMS", "priority": "high", "exam_date": YEAR_OR_NEXT(10, 30)}),
    ("రేపు OS పరీక్ష పెట్టు", "create_academic", {"subject": "OS", "exam_date": D(1)}),
    ("Acme Corp lo ML Intern ki apply chesanu, 30 Oct deadline", "create_application", {"company": "Acme Corp", "role": "ML Intern"}),
    ("ML Intern role ki Acme Corp lo application add cheyyi 30 Oct", "create_application", {"company": "Acme Corp", "role": "ML Intern"}),
    ("Google Research lo internship undi, deadline 15 Dec", "create_opportunity", {"company_or_lab": "Google Research", "title": "Internship at Google Research"}),
    ("Radisson nunchi client request add cheyyi, booking website kavali", "create_request", {"client": "Radisson", "ask": "booking website"}),
]
NOT_ADDS = [
    "ela add cheyali project resume lo?",
    "project add cheyocha?",
    "exam enduku add cheyyali ikkada?",
    "ఎలా ప్రాజెక్ట్ జోడించాలి?",
    "task add cheyyi repu gym",
    "how do I add a project to my resume?",
]


@pytest.mark.parametrize("msg,tool,expect", ADDS)
def test_tenglish_adds(msg, tool, expect):
    hit = detect(msg)
    assert hit and hit[1] == tool, (msg, hit)
    f = heuristic_fields(tool, msg)
    for k, v in expect.items():
        assert f.get(k) == v, (msg, k, f)


@pytest.mark.parametrize("msg", NOT_ADDS)
def test_tenglish_questions_and_tasks_are_not_captured(msg):
    assert detect(msg) is None, msg


def test_tenglish_dates():
    assert parse_date("repu") == D(1) and parse_date("ellundi") == D(2) and parse_date("ee roju") == D(0)
    assert parse_date("next week lo") == D(7) and parse_date("3 rojullo") == D(3) and parse_date("2 vaaraalalo") == D(14)
    assert parse_date("20 Nov ki") == YEAR_OR_NEXT(11, 20) and parse_date("నవంబర్ 20 కి") == YEAR_OR_NEXT(11, 20)


def test_english_unchanged():
    assert detect("add an exam for Operating Systems on 20 Nov") == ("academics", "create_academic")
    assert heuristic_fields("create_application", "add an application as ML Intern at Acme Corp deadline 30 Oct")["company"] == "Acme Corp"


HI_ADDS = [
    ("ek project add karo KARNA RAG naam se, FastAPI React ke saath", "create_project"),
    ("OS ka exam hai 20 Nov ko", "create_academic"),
    ("Operating Systems exam add kar do kal", "create_academic"),
    ("exam daal do DBMS 30th Oct tak", "create_academic"),
    ("Acme Corp mein ML Intern ke liye apply kar diya, 30 Oct deadline", "create_application"),
    ("Google Research mein internship hai, deadline 15 Dec", "create_opportunity"),
    ("\u090f\u0915 \u092a\u094d\u0930\u094b\u091c\u0947\u0915\u094d\u091f add \u0915\u0930\u094b KARNA", "create_project"),
]
HI_NOT = ["project resume mein kaise add karu?", "applications kahan hai?", "exam kyun add karna hai?", "task add karo kal gym"]


@pytest.mark.parametrize("msg,tool", HI_ADDS)
def test_hinglish_adds(msg, tool):
    hit = detect(msg)
    assert hit and hit[1] == tool, (msg, hit)


@pytest.mark.parametrize("msg", HI_NOT)
def test_hinglish_questions_and_tasks_not_captured(msg):
    assert detect(msg) is None, msg


def test_hinglish_dates():
    assert parse_date("kal") == D(1) and parse_date("parso") == D(2) and parse_date("aaj") == D(0)


def test_opportunity_with_modifier_word():
    f = heuristic_fields("create_opportunity", "Microsoft lo summer internship undi 5 Jan deadline")
    assert f["company_or_lab"] == "Microsoft" and f["title"] == "Internship at Microsoft"
