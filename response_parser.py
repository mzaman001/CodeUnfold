"""Pure-function parsing helpers for LLM responses.

Pulled out of main.py so the parsing logic — the most regression-prone
part of this app (see the audit's finding on brittle XML-tag extraction,
and the duplicated extraction blocks in the solve/fix handlers) — can be
unit tested in isolation from Streamlit's session state and rerun model.
Nothing in this module imports streamlit; every function is a plain
string-in, value-out transform.
"""
import re


def extract_tag(text: str, tag: str):
    """Returns the stripped contents of <tag>...</tag>, or None if absent."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def extract_code_block(text: str) -> str:
    """Extracts the longest fenced ``` code block from a response.

    Prefers to search inside a <code>...</code> tag if one is present,
    falling back to searching the whole response otherwise. Returns ""
    if no fenced block is found.

    Known limitation (see audit, "hidden issues"): the "longest block
    wins" heuristic is a reasonable default but can misfire if the model
    includes a longer illustrative "why the brute-force approach fails"
    block before the real solution. Flagged here rather than silently
    relied on.
    """
    code_section = extract_tag(text, "code")
    search_text = code_section if code_section is not None else text
    matches = re.findall(r"```(?:\w+)?\n(.*?)```", search_text, re.DOTALL | re.IGNORECASE)
    return max(matches, key=len).strip() if matches else ""


def extract_sections(text: str, tags: list) -> dict:
    """Extracts every tag in `tags`. Returns a dict of tag -> text.

    A tag missing from the response maps to None (never a KeyError) so
    callers can uniformly check `all(sections.values())` to decide
    whether the structured (tabbed) UI can be trusted, or whether to
    fall back to a raw text dump — the same defensive pattern main.py
    already used inline, just now in one shared, testable place.
    """
    return {tag: extract_tag(text, tag) for tag in tags}


HINT_TAGS = ["intuition", "walkthrough", "pseudocode"]
REVIEW_TAGS = ["critique", "logic_flaw", "fix_direction"]
SOLUTION_TAGS = [
    "problem_statement", "key_idea", "approach", "worked_example",
    "code", "explanation", "complexity", "takeaway",
]


def extract_hint_sections(text: str):
    """Returns the 3-tag hint dict if ALL tags are present, else None."""
    sections = extract_sections(text, HINT_TAGS)
    return sections if all(sections.values()) else None


def extract_review_sections(text: str):
    """Returns the 3-tag code-review dict if ALL tags are present, else None."""
    sections = extract_sections(text, REVIEW_TAGS)
    return sections if all(sections.values()) else None


def extract_solution_sections(text: str):
    """Returns the 7-tag solution dict if ALL tags are present, else None."""
    sections = extract_sections(text, SOLUTION_TAGS)
    return sections if all(sections.values()) else None


def extract_socratic_question(text: str):
    """Returns the opening Socratic question, or None if not found."""
    return extract_tag(text, "question")


def extract_socratic_followup(text: str):
    """Parses a Socratic follow-up turn.

    Returns a dict with a "kind" of either:
      - "next_question": {"kind": "next_question", "feedback": ..., "next_question": ...}
      - "converged": {"kind": "converged", "feedback": ..., "intuition": ..., "walkthrough": ..., "pseudocode": ...}
    or None if the response didn't match either expected shape.
    """
    feedback = extract_tag(text, "feedback")
    if feedback is None:
        return None

    next_question = extract_tag(text, "next_question")
    if next_question:
        return {"kind": "next_question", "feedback": feedback, "next_question": next_question}

    hint_sections = extract_hint_sections(text)
    if hint_sections:
        return {"kind": "converged", "feedback": feedback, **hint_sections}

    return None
