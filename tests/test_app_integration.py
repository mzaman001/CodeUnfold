"""Integration test that runs the actual main.py script via Streamlit's
AppTest framework, rather than only unit-testing extracted helpers.

This exists specifically because a real user hit a `StreamlitAPIException`
in production: main.py tried to reassign `st.session_state.user_code`
after the code-editor widget (which owns that same key) had already been
instantiated in the same script run. None of the pure-function unit tests
in this suite could have caught that, since it's a Streamlit
runtime/widget-lifecycle issue, not a logic bug in an extracted function.
AppTest actually executes the script end-to-end and surfaces exceptions
the way a live app run would.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("GROQ_API_KEY", "fake-key-for-tests")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from streamlit.testing.v1 import AppTest

MAIN_PATH = str(Path(__file__).resolve().parents[1] / "main.py")


def _fresh_app():
    at = AppTest.from_file(MAIN_PATH, default_timeout=15)
    at.run()
    assert not at.exception, f"App crashed on initial load: {at.exception}"
    return at


def test_app_loads_without_exception():
    _fresh_app()


def test_solve_button_does_not_raise_streamlit_api_exception():
    """Regression test for the `user_code` widget-key reassignment crash.

    Fills the problem + code editor, clicks 'Reveal Solution', and asserts
    the app doesn't blow up with StreamlitAPIException. The AI call itself
    is expected to fail in this sandboxed test environment (no real
    network access to Groq/Gemini) -- that's fine, it should surface as a
    handled `st.error` message inside the try/except, not an unhandled
    exception from the framework.
    """
    at = _fresh_app()

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    code_box = next((w for w in at.text_area if w.key == "user_code"), None)
    if code_box is not None:
        code_box.set_value("x" * 6000)  # deliberately over MAX_CODE_CHARS

    solve_btn = next(b for b in at.button if "Reveal Solution" in (b.label or ""))
    solve_btn.click().run()

    assert not at.exception, f"Unhandled exception after solve click: {at.exception}"


def test_hint_button_does_not_raise_streamlit_api_exception():
    at = _fresh_app()

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    hint_btn = next(b for b in at.button if "Get Hints" in (b.label or ""))
    hint_btn.click().run()

    assert not at.exception, f"Unhandled exception after hint click: {at.exception}"


def test_socratic_mode_toggle_and_hint_flow_do_not_raise():
    """Exercises the Socratic hint mode end-to-end through AppTest: toggle
    it on, fill the problem, click Get Hints. The AI call fails in this
    sandboxed environment (no real network), which should surface as a
    handled error inside the try/except -- not an unhandled exception.
    """
    at = _fresh_app()

    socratic_toggle = next((w for w in at.toggle if w.key == "socratic_mode"), None)
    assert socratic_toggle is not None, "Socratic Mode toggle not found in sidebar"
    socratic_toggle.set_value(True).run()
    assert not at.exception, f"Unhandled exception after enabling Socratic mode: {at.exception}"

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    hint_btn = next(b for b in at.button if "Get Hints" in (b.label or ""))
    hint_btn.click().run()

    assert not at.exception, f"Unhandled exception in Socratic hint flow: {at.exception}"


def test_save_lesson_to_memory_builds_structured_record():
    """Seeds a fake generated solution directly into session state (since
    the real AI call can't reach the network in this sandboxed test) and
    clicks 'Save this approach to memory', confirming the resulting
    record is a structured, tagged dict rather than a flat string --
    and that nothing crashes along the way.
    """
    at = AppTest.from_file(MAIN_PATH, default_timeout=15)
    at.run()
    assert not at.exception

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value(
        "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]\n\nclass Solution:\n    def twoSum(self, nums, target):"
    )
    at.run()  # commit the widget value into session_state before reading it back
    at.session_state["problem_text"] = at.session_state["_problem_widget"]
    at.session_state["current_solution"] = (
        "<problem_statement>Two Sum</problem_statement>"
        "<key_idea>use a hash map</key_idea>"
        "<approach>iterate once</approach>"
        "<code>```python\nclass Solution:\n    def twoSum(self, nums, target):\n        return []\n```</code>"
        "<explanation>explained</explanation>"
        "<complexity>O(n)</complexity>"
        "<takeaway>Use a hash map for O(1) lookups on Two Sum style problems.</takeaway>"
    )
    at.run()
    assert not at.exception, f"Unhandled exception rendering solution: {at.exception}"

    save_btn = next((b for b in at.button if "Save this approach to memory" in (b.label or "")), None)
    assert save_btn is not None, "Save-to-memory button not found"
    save_btn.click().run()

    assert not at.exception, f"Unhandled exception after saving lesson: {at.exception}"
    saved = at.session_state["lessons_memory"]
    assert len(saved) == 1
    assert isinstance(saved[0], dict)
    assert "Array" in saved[0]["tags"]  # inferred from "nums" in the problem text
    assert "hash map" in saved[0]["takeaway"].lower()
