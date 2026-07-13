import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from response_parser import (
    extract_tag, extract_code_block,
    extract_hint_sections, extract_review_sections, extract_solution_sections,
    extract_socratic_question, extract_socratic_followup,
)


def test_extract_tag_present():
    assert extract_tag("<foo>bar</foo>", "foo") == "bar"


def test_extract_tag_strips_whitespace():
    assert extract_tag("<foo>\n  bar  \n</foo>", "foo") == "bar"


def test_extract_tag_missing_returns_none():
    assert extract_tag("<foo>bar</foo>", "baz") is None


def test_extract_tag_case_insensitive():
    assert extract_tag("<FOO>bar</FOO>", "foo") == "bar"


def test_extract_code_block_picks_longest():
    text = "```python\nshort\n```\nsome text\n```python\nlong block of code\n```"
    assert extract_code_block(text) == "long block of code"


def test_extract_code_block_prefers_code_tag_contents():
    text = (
        "```python\nlonger illustrative but-wrong example that is really long\n```\n"
        "<code>\n```python\nreal_solution()\n```\n</code>"
    )
    assert extract_code_block(text) == "real_solution()"


def test_extract_code_block_no_fence_returns_empty():
    assert extract_code_block("no code here") == ""


def test_extract_hint_sections_all_present():
    text = "<intuition>a</intuition><walkthrough>b</walkthrough><pseudocode>c</pseudocode>"
    result = extract_hint_sections(text)
    assert result == {"intuition": "a", "walkthrough": "b", "pseudocode": "c"}


def test_extract_hint_sections_missing_tag_returns_none():
    text = "<intuition>a</intuition><walkthrough>b</walkthrough>"
    assert extract_hint_sections(text) is None


def test_extract_review_sections_all_present():
    text = "<critique>a</critique><logic_flaw>b</logic_flaw><fix_direction>c</fix_direction>"
    result = extract_review_sections(text)
    assert result == {"critique": "a", "logic_flaw": "b", "fix_direction": "c"}


def test_extract_solution_sections_all_present():
    tags = ["problem_statement", "key_idea", "approach", "worked_example", "code", "explanation", "complexity", "takeaway"]
    text = "".join(f"<{t}>{t}_value</{t}>" for t in tags)
    result = extract_solution_sections(text)
    assert all(result[t] == f"{t}_value" for t in tags)


def test_extract_solution_sections_partial_returns_none():
    text = "<problem_statement>only this one</problem_statement>"
    assert extract_solution_sections(text) is None


def test_extract_socratic_question():
    text = "<question>Why might brute force be slow?</question>"
    assert extract_socratic_question(text) == "Why might brute force be slow?"


def test_extract_socratic_question_missing_returns_none():
    assert extract_socratic_question("no tags here") is None


def test_extract_socratic_followup_next_question_shape():
    text = "<feedback>Good start!</feedback><next_question>What about duplicates?</next_question>"
    result = extract_socratic_followup(text)
    assert result == {
        "kind": "next_question",
        "feedback": "Good start!",
        "next_question": "What about duplicates?",
    }


def test_extract_socratic_followup_converged_shape():
    text = (
        "<feedback>Nice.</feedback>"
        "<intuition>use a hash map</intuition>"
        "<walkthrough>step 1...</walkthrough>"
        "<pseudocode>for each...</pseudocode>"
    )
    result = extract_socratic_followup(text)
    assert result["kind"] == "converged"
    assert result["feedback"] == "Nice."
    assert result["intuition"] == "use a hash map"


def test_extract_socratic_followup_malformed_returns_none():
    assert extract_socratic_followup("no relevant tags") is None
