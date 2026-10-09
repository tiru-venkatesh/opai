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
