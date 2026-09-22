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


def replace_tag(text: str, tag: str, new_content: str) -> str:
    """Replaces the contents of <tag>...</tag> with `new_content`.

    Used to patch a single flagged section after a targeted repair call
    (see ai_client.build_repair_prompt) without re-serializing the whole
    tagged response -- a repair spends tokens on one section, not the
    full solve/hint output. Returns `text` unchanged if the tag isn't
    found, so a malformed repair can never silently corrupt the response.
    """
    pattern = re.compile(rf"(<{tag}>)(.*?)(</{tag}>)", re.DOTALL | re.IGNORECASE)
    if not pattern.search(text):
        return text
    return pattern.sub(lambda m: f"{m.group(1)}\n{new_content}\n{m.group(3)}", text, count=1)


# Jargon terms the teaching prompts require to be glossed in plain
# English the first time they're used. Not exhaustive -- covers the
# terms most likely to appear unglossed when a model skips the rule
# under load, per build_pedagogical_hint_prompt's docstring rationale.
_JARGON_TERMS = [
    "hash map", "hash set", "pointer", "traversal", "memoization", "amortized",
    "recursion", "recursive", "dynamic programming", "greedy", "binary search",
    "two pointer", "sliding window", "big-o", "time complexity", "space complexity",
    "stack", "queue", "heap", "trie", "topological sort", "backtracking",
]

# Below this many characters, a section reads as a one-liner rather than
# the "depth is the goal, terseness is a failure" explanation the
# teaching prompts demand. Thresholds are deliberately loose (a real
# floor, not a target) to avoid flagging legitimately short sections.
MIN_SECTION_CHARS = {
    "intuition": 220, "key_idea": 200, "approach": 200, "walkthrough": 150,
    "worked_example": 150, "explanation": 150, "critique": 80, "logic_flaw": 100,
    "pseudocode": 80, "fix_direction": 80,
}


def find_quality_issues(sections: dict) -> dict:
    """Cheap, local (no-LLM) heuristics that flag likely rubric violations
    in an already-parsed section dict.

    This exists to make the repair pass in ai_client/main.py targeted
    instead of blind: the teaching prompts are already heavily tuned
    (worked examples, mandatory jargon-glossing, analogy-before-formal-
    name -- see ai_client.build_pedagogical_hint_prompt), so most
    responses already comply and a full critique-and-regenerate call on
    every response would double token cost for no benefit. Running this
    heuristic first and only spending a follow-up call on the sections it
    actually flags keeps the common case at zero extra cost.

    Returns {section_name: [issue, ...]} for sections with a problem;
    sections with none are omitted entirely. Heuristic, not exhaustive --
    false negatives are expected and fine; the goal is to catch what
    regularly slips through, not to guarantee compliance.
    """
    # Never flag these: "code" is code, not prose (jargon/length rules
    # don't apply and a "repair" call would risk mangling working code),
    # and "title"/"complexity"/"takeaway" are meant to be short by design.
    _EXCLUDED_SECTIONS = {"code", "title", "complexity", "takeaway", "next_question", "feedback"}

    issues = {}
    for name, text in sections.items():
        if not text or name in _EXCLUDED_SECTIONS:
            continue
        section_issues = []

        min_len = MIN_SECTION_CHARS.get(name)
        if min_len and len(text) < min_len:
            section_issues.append(
                f"too short ({len(text)} chars) -- needs a real beginner-level explanation, not a one-liner"
            )

        if name in ("worked_example", "walkthrough") and not re.search(r"\d", text):
            section_issues.append(
                "no concrete traced values found -- must trace the problem's own example with real numbers, not describe it abstractly"
            )

        lower = text.lower()
        for term in _JARGON_TERMS:
            idx = lower.find(term)
            if idx == -1:
                continue
            tail = text[idx: idx + len(term) + 60]
            if not any(marker in tail for marker in ("(", "--", "—", " - ")):
                section_issues.append(
                    f"uses '{term}' without a nearby plain-English gloss the first time it's used"
                )
                break  # one flagged term is enough signal; don't pile on

        if section_issues:
            issues[name] = section_issues
    return issues


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
