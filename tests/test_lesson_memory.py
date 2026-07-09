import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lesson_memory import infer_tags, build_lesson, select_relevant_lessons, format_lessons_context


# ---------- infer_tags ----------

def test_infer_tags_detects_hash_map():
    assert "Hash Map" in infer_tags("Use a hash map to store seen values")


def test_infer_tags_detects_multiple_topics():
    tags = infer_tags("Given a binary tree, use BFS (breadth-first search) to traverse level by level")
    assert "Tree" in tags
    assert "Queue" in tags  # BFS keyword maps to Queue


def test_infer_tags_no_match_returns_empty_list():
    assert infer_tags("some totally unrelated text about cooking pasta") == []


def test_infer_tags_empty_input_returns_empty_list():
    assert infer_tags("") == []
    assert infer_tags(None) == []


def test_infer_tags_case_insensitive():
    assert "Dynamic Programming" in infer_tags("use DYNAMIC PROGRAMMING here")


def test_infer_tags_dp_word_boundary_does_not_false_positive():
    # "dp" should not match inside unrelated words like "adapt"
    assert "Dynamic Programming" not in infer_tags("adapt the loop condition")


# ---------- build_lesson ----------

def test_build_lesson_tags_from_problem_text():
    lesson = build_lesson("Two Sum", "use a hash map for O(1) lookup", "array of nums with hash map", "Python")
    assert lesson["title"] == "Two Sum"
    assert lesson["takeaway"] == "use a hash map for O(1) lookup"
    assert "Hash Map" in lesson["tags"]
    assert lesson["language"] == "Python"


def test_build_lesson_falls_back_to_title_tags_if_problem_text_untagged():
    lesson = build_lesson("Binary Search Problem", "takeaway", "no relevant keywords here", "Python")
    assert "Binary Search" in lesson["tags"]


# ---------- select_relevant_lessons ----------

def test_select_relevant_lessons_prioritizes_tag_overlap():
    lessons = [
        {"title": "Old Tree Problem", "takeaway": "dfs traversal", "tags": ["Tree", "Graph"], "language": "Python"},
        {"title": "Recent Sort Problem", "takeaway": "quicksort", "tags": ["Sorting"], "language": "Python"},
    ]
    selected = select_relevant_lessons(lessons, "Given a binary tree, traverse it", max_lessons=1)
    assert selected[0]["title"] == "Old Tree Problem"


def test_select_relevant_lessons_falls_back_to_recency_when_no_overlap():
    lessons = [
        {"title": "First", "takeaway": "t1", "tags": ["Sorting"], "language": "Python"},
        {"title": "Second", "takeaway": "t2", "tags": ["Heap"], "language": "Python"},
    ]
    selected = select_relevant_lessons(lessons, "totally unrelated cooking text", max_lessons=5)
    # No overlap possible (no tags inferred from the current problem) -> most recent first
    assert selected[0]["title"] == "Second"
    assert selected[1]["title"] == "First"


def test_select_relevant_lessons_empty_list_returns_empty():
    assert select_relevant_lessons([], "some problem", max_lessons=5) == []


def test_select_relevant_lessons_respects_max_lessons():
    lessons = [{"title": f"L{i}", "takeaway": "t", "tags": [], "language": "Python"} for i in range(10)]
    selected = select_relevant_lessons(lessons, "problem", max_lessons=3)
    assert len(selected) == 3


# ---------- format_lessons_context ----------

def test_format_lessons_context_includes_tags_and_takeaway():
    lessons = [{"title": "Two Sum", "takeaway": "use a hash map", "tags": ["Hash Map"], "language": "Python"}]
    context = format_lessons_context(lessons)
    assert "Two Sum" in context
    assert "use a hash map" in context
    assert "[Hash Map]" in context


def test_format_lessons_context_empty_list_returns_empty_string():
    assert format_lessons_context([]) == ""


def test_format_lessons_context_handles_untagged_lesson():
    lessons = [{"title": "Mystery", "takeaway": "something", "tags": [], "language": "Python"}]
    context = format_lessons_context(lessons)
    assert "Mystery: something" in context
