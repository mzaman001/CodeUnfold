import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from response_parser import (
    extract_tag, extract_code_block,
    extract_hint_sections, extract_review_sections, extract_solution_sections,
    extract_socratic_question, extract_socratic_followup,
    replace_tag, find_quality_issues,
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


def test_replace_tag_swaps_contents():
    text = "<intuition>old</intuition><walkthrough>keep</walkthrough>"
    result = replace_tag(text, "intuition", "new")
    assert "new" in result
    assert "old" not in result
    assert "<walkthrough>keep</walkthrough>" in result


def test_replace_tag_missing_tag_returns_unchanged():
    text = "<intuition>old</intuition>"
    assert replace_tag(text, "walkthrough", "new") == text


def test_find_quality_issues_flags_short_section():
    issues = find_quality_issues({"intuition": "Too short."})
    assert "intuition" in issues


def test_find_quality_issues_flags_worked_example_without_numbers():
    long_no_numbers = "We look at each element and compare it to what we have seen so far in the map. " * 3
    issues = find_quality_issues({"worked_example": long_no_numbers})
    assert "worked_example" in issues


def test_find_quality_issues_flags_unglossed_jargon():
    text = (
        "We use a hash map to solve this efficiently. " * 3
        + "It avoids scanning the whole list every time we check a value against the rest."
    )
    issues = find_quality_issues({"key_idea": text})
    assert "key_idea" in issues
    assert any("hash map" in issue for issue in issues["key_idea"])


def test_find_quality_issues_passes_well_formed_section():
    text = (
        "A **hash map** (a lookup table where you can check 'have I seen this before?' "
        "instantly, like a phone book indexed by name) is the key idea here. At index 0 "
        "we see 2 and remember it. At index 1 we see 7 and check whether 9 - 7 = 2 is "
        "already stored -- it is, at index 0, so we return [0, 1] immediately without "
        "ever comparing every pair against every other pair."
    )
    assert find_quality_issues({"key_idea": text}) == {}


def test_find_quality_issues_never_flags_excluded_sections():
    assert find_quality_issues({"code": "x", "title": "x", "complexity": "x", "takeaway": "x"}) == {}


def test_find_quality_issues_ignores_falsy_sections():
    assert find_quality_issues({"intuition": None, "walkthrough": ""}) == {}
