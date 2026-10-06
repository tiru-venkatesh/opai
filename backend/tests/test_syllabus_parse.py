import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from syllabus_parse import extract_structure

SAMPLE = """CS301 Data Structures  Credits: 4
UNIT I: Arrays and Strings (8 hrs)
Arrays in Java; multidimensional arrays; String vs StringBuilder
UNIT-II Trees
Binary tree, BST, Heap tree
Module 3 - Graphs
BFS, DFS, Dijkstra
Text Books
Cormen
"""

def test_units_topics_code_and_textbook_excluded():
    r = extract_structure(SAMPLE)
    assert r["code"] == "CS301" and r["credits"] == 4.0
    assert [u["unit"].split(":")[0] for u in r["units"]] == ["Unit 1", "Unit 2", "Unit 3"]
    assert "Heap tree" in r["units"][1]["topics"]
    assert "Cormen" not in r["units"][2]["topics"]

def test_not_a_syllabus_asks_user():
    r = extract_structure("hello world")
    assert r["units"] == [] and "syllabus" in r["questions"][0].lower()


# ---- booklet / JNTU-style regressions
from syllabus_parse import split_courses, course_labels, pick_course

def _course(title, extra=""):
    unit = "\n".join(f"UNIT - {r}\nTopic {r} alpha, beta gamma, delta epsilon.\n" for r in ["I", "II", "III"])
    return (f"R23 B.Tech CSE COURSE STRUCTURE & SYLLABUS\nL T P C\nII Year I Semester\n3 0 0 3\n{title}\n"
            "Pre-requisite:\n1. Knowledge in Computer Programming.\nCourse Outcomes: After this\nCO1: Describe things\n"
            + unit + extra + "Textbooks:\n1. Some Author\n" + "x" * 300)

def test_booklet_is_split_and_prereqs_are_not_units():
    book = "\n\f\n".join(_course(t) for t in ["ARTIFICIAL INTELLIGENCE", "COMPUTER NETWORKS", "COMPILER DESIGN"])
    cs = split_courses(book)
    assert [c["title"] for c in cs] == ["Artificial Intelligence", "Computer Networks", "Compiler Design"]
    st = extract_structure(cs[0]["text"])
    assert [u["unit"].split(":")[0] for u in st["units"]] == ["Unit 1", "Unit 2", "Unit 3"]   # not "Knowledge in..."
    assert pick_course(cs, "i am cse") is None and pick_course(cs, "compiler design") == 2

def test_en_dash_unit_heading_and_outcomes_before_units():
    r = extract_structure("Course Outcomes:\nCO1: x\nUNIT\u2013I\nAlpha, Beta\nUNIT \u2013 II\nGamma, Delta\nTextbooks:\nBook")
    assert len(r["units"]) == 2 and "Gamma" in r["units"][1]["topics"]
