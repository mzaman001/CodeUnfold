"""Structured, categorized session-memory for saved lesson takeaways.

Previously, saved lessons were flat strings, and `_get_lessons_context()`
always injected the most recent 5 into every prompt regardless of
whether they had anything to do with the problem currently being solved
-- a "Sliding Window" lesson from an hour ago is noise (and wasted
prompt tokens) when the student is now stuck on a graph problem.

This module tags each saved lesson with the LeetCode topic(s) it likely
covers (via lightweight keyword matching -- no extra AI call, no new
dependency) and prioritizes surfacing lessons whose topics overlap with
the current problem. If nothing overlaps (new topic, or tagging missed
everything), it falls back to the most recent lessons rather than
showing nothing, so behavior degrades gracefully instead of going silent.
"""
import re

# Keyword -> topic tag. Case-insensitive substring/word-boundary match
# against the problem text. Intentionally simple and dependency-free;
# false negatives (a lesson goes untagged) just mean graceful fallback
# to recency-based selection, not a crash or a wrong answer.
TOPIC_KEYWORDS = {
    "Hash Map": [r"hash\s*map", r"hash\s*table", r"\bdictionary\b"],
    "Two Pointers": [r"two[\s-]*pointer"],
    "Sliding Window": [r"sliding\s*window"],
    "Binary Search": [r"binary\s*search"],
    "Linked List": [r"linked\s*list", r"\blistnode\b"],
    "Stack": [r"\bstack\b", r"parenthes", r"balanced\s*brackets"],
    "Queue": [r"\bqueue\b", r"\bbfs\b", r"breadth[\s-]*first"],
    "Tree": [r"\btree\b", r"\btreenode\b", r"\bbinary\s*tree\b"],
    "Graph": [r"\bgraph\b", r"adjacency", r"\bdfs\b", r"depth[\s-]*first"],
    "Dynamic Programming": [r"dynamic\s*programming", r"\bdp\b", r"memoiz", r"subproblem"],
    "Backtracking": [r"backtrack", r"permutation", r"combination", r"n-queens"],
    "Greedy": [r"\bgreedy\b", r"\binterval\b"],
    "Heap": [r"\bheap\b", r"priority\s*queue", r"kth\s*(largest|smallest)"],
    "Sorting": [r"\bsort(ed|ing)?\b"],
    "Bit Manipulation": [r"bit\s*manipulation", r"\bxor\b", r"bitwise"],
    "Recursion": [r"recursi"],
    "String": [r"\bstring\b", r"substring", r"anagram", r"palindrome"],
    "Array": [r"\barray\b", r"subarray", r"\bnums\b"],
}

_COMPILED = {tag: [re.compile(p, re.IGNORECASE) for p in patterns] for tag, patterns in TOPIC_KEYWORDS.items()}


def infer_tags(text: str) -> list:
    """Returns the list of topic tags whose keywords appear in `text`.

    Order matches TOPIC_KEYWORDS' declaration order (roughly specific ->
    general, so e.g. "Hash Map" is checked before the very broad "Array").
    A problem can legitimately match multiple tags.
    """
    if not text:
        return []
    return [tag for tag, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]


def build_lesson(title: str, takeaway: str, problem_text: str, language: str) -> dict:
    """Builds a structured lesson record from a saved takeaway."""
    return {
        "title": title,
        "takeaway": takeaway,
        "tags": infer_tags(problem_text) or infer_tags(title),
        "language": language,
    }


def select_relevant_lessons(lessons: list, problem_text: str, max_lessons: int = 5) -> list:
    """Picks the most relevant saved lessons for the current problem.

    Ranks by tag overlap with the current problem (most overlapping tags
    first), then by recency as a tiebreaker. If no lesson shares any tag
    with the current problem (including the case where nothing could be
    tagged at all), falls back to the most recent `max_lessons` -- the
    old behavior -- so the feature degrades gracefully instead of ever
    silently dropping all context.
    """
    if not lessons:
        return []

    current_tags = set(infer_tags(problem_text))
    indexed = list(enumerate(lessons))  # preserve original (chronological) order for recency tiebreak

    def overlap_score(item):
        idx, lesson = item
        return len(current_tags & set(lesson.get("tags", [])))

    scored = sorted(indexed, key=lambda item: (overlap_score(item), item[0]), reverse=True)
    top = scored[:max_lessons]

    if current_tags and any(overlap_score(item) > 0 for item in top):
        return [lesson for _, lesson in top]

    # No relevant overlap found -- fall back to plain recency.
    return [lesson for lesson in lessons[-max_lessons:]][::-1]


def format_lessons_context(lessons: list) -> str:
    """Renders selected lessons into the prompt-injected context block."""
    if not lessons:
        return ""
    lines = []
    for lesson in lessons:
        tag_prefix = f"[{', '.join(lesson['tags'])}] " if lesson.get("tags") else ""
        lines.append(f"- {tag_prefix}{lesson['title']}: {lesson['takeaway']}")
    return "\n\nLESSONS FROM YOUR MEMORY (avoid repeating past mistakes):\n" + "\n".join(lines)
