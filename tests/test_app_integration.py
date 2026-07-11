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

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

MAIN_PATH = str(Path(__file__).resolve().parents[1] / "main.py")


@pytest.fixture(autouse=True)
def isolated_persistence_db(tmp_path, monkeypatch):
    """Every test in this file runs main.py, which initializes the
    persistence layer (persistence.init_db) at import/session-init time.
    Without this, every AppTest-based test would create/write to the
    real app's default codeunfold_data.db file sitting next to the
    source code -- not a test's job to touch. Points every test at an
    isolated per-test temp DB instead.
    """
    monkeypatch.setenv("CODEUNFOLD_DB_PATH", str(tmp_path / "test_codeunfold.db"))


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


def test_solve_button_with_mocked_streaming_response_produces_final_solution(monkeypatch):
    """Integration test for the streaming solve flow: mocks
    ai_client.call_ai_stream to yield real chunks (instead of failing due
    to no network access), and confirms the full pipeline -- streaming
    render, code extraction, and final structured solution -- produces
    the expected end state. Covers the actual success path, not just
    that failures are handled gracefully.
    """
    import ai_client

    fake_response = (
        "<title>Two Sum</title>"
        "<problem_statement>Find two numbers that sum to target</problem_statement>"
        "<key_idea>Use a hash map for O(1) lookups</key_idea>"
        "<approach>Iterate once, checking complements</approach>"
        "<code>```python\nclass Solution:\n    def twoSum(self, nums, target):\n        seen = {}\n        "
        "for i, n in enumerate(nums):\n            if target - n in seen:\n                return [seen[target - n], i]\n            "
        "seen[n] = i\n        return []\n```</code>"
        "<explanation>Hash map lookups are O(1) average case</explanation>"
        "<complexity>Time: O(n), Space: O(n)</complexity>"
        "<takeaway>Use a hash map when you need fast lookups</takeaway>"
    )

    def _fake_stream(prompt, user_key=None):
        # Yield in a few chunks to actually exercise streaming, not just
        # a single-chunk response.
        chunk_size = 50
        for i in range(0, len(fake_response), chunk_size):
            yield fake_response[i:i + chunk_size]

    monkeypatch.setattr(ai_client, "call_ai_stream", _fake_stream)

    at = _fresh_app()
    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    solve_btn = next(b for b in at.button if "Reveal Solution" in (b.label or ""))
    solve_btn.click().run()

    assert not at.exception, f"Unhandled exception: {at.exception}"
    assert at.session_state["current_solution"] is not None
    assert "Two Sum" in at.session_state["current_solution"]
    assert "def twoSum" in at.session_state["raw_code"]
    # The real code_verifier.py should have run against the extracted
    # code and the example -- confirming the whole pipeline, not just
    # that streaming text arrived.
    verification = at.session_state["verification"]
    assert verification["verified"] is True
    assert verification["passed"] is True


def test_hint_button_does_not_raise_streamlit_api_exception():
    at = _fresh_app()

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    hint_btn = next(b for b in at.button if "Get Hints" in (b.label or ""))
    hint_btn.click().run()

    assert not at.exception, f"Unhandled exception after hint click: {at.exception}"


def test_fix_loop_end_to_end_with_stubbed_response(monkeypatch):
    """Integration test for P2.9: seeds a buggy solution, pastes an
    error, clicks 'Fix My Solution' with a stubbed AI fix response, and
    confirms the whole pipeline -- error history tracking, code
    extraction, re-verification, and diff injection into the displayed
    solution -- works end to end.
    """
    import ai_client

    fixed_code_response = (
        "<problem_statement>Two Sum</problem_statement>"
        "<key_idea>x</key_idea><approach>x</approach>"
        "<code>```python\nclass Solution:\n    def twoSum(self, nums, target):\n        seen = {}\n        "
        "for i, n in enumerate(nums):\n            if target - n in seen:\n                return [seen[target - n], i]\n            "
        "seen[n] = i\n        return []\n```</code>"
        "<explanation>Fixed: was returning the wrong indices</explanation>"
        "<complexity>O(n)</complexity><takeaway>Watch your index bookkeeping</takeaway>"
    )

    def _fake_call_ai(prompt, user_key=None):
        assert "IndexError" in prompt  # confirms the pasted error actually reached the prompt
        return ai_client.AIResult(text=fixed_code_response, provider="fake-model", notices=[])

    monkeypatch.setattr(ai_client, "call_ai", _fake_call_ai)

    at = _fresh_app()
    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")
    at.run()
    at.session_state["problem_text"] = at.session_state["_problem_widget"]

    # Seed a buggy prior solution directly (as if a real solve had already happened).
    at.session_state["raw_code"] = (
        "class Solution:\n    def twoSum(self, nums, target):\n        return [99, 99]\n"
    )
    at.session_state["current_solution"] = (
        "<problem_statement>Two Sum</problem_statement><key_idea>x</key_idea><approach>x</approach>"
        "<code>```python\nclass Solution:\n    def twoSum(self, nums, target):\n        return [99, 99]\n```</code>"
        "<explanation>x</explanation><complexity>x</complexity><takeaway>x</takeaway>"
    )
    at.run()
    assert not at.exception

    error_box = next((w for w in at.text_area if w.key == "error_input_box"), None)
    assert error_box is not None, "error input box not found -- did the solution section render?"
    error_box.set_value("IndexError: list index out of range")

    fix_btn = next(b for b in at.button if "Fix My Solution" in (b.label or ""))
    fix_btn.click().run()

    assert not at.exception, f"Unhandled exception in fix loop: {at.exception}"
    assert len(at.session_state["attempt_errors"]) == 1
    assert "IndexError" in at.session_state["attempt_errors"][0]
    assert "seen[target - n]" in at.session_state["raw_code"]  # the fixed code, not the old [99, 99] stub

    verification = at.session_state["verification"]
    assert verification["verified"] is True
    assert verification["passed"] is True

    # The diff should have been injected into the displayed solution.
    assert "Code Diff" in at.session_state["current_solution"]
    # show_update_alert is a show-once flag: the display code renders a
    # success message and resets it to False within the same run, so by
    # now it's expected to be False again -- confirm the success message
    # it gates actually rendered instead of checking the flag's final value.
    success_messages = [str(el.value) for el in at.success]
    assert any("updated" in msg.lower() for msg in success_messages), (
        f"expected an update notice to have rendered; got: {success_messages}"
    )


def test_fix_loop_respects_session_call_cap(monkeypatch):
    """The fix loop previously had no _check_session_limit call at all
    (a real quota-bypass gap fixed alongside B7/B8) -- confirm it now
    respects the exhausted per-session cap like every other AI-call site.
    """
    at = _fresh_app()
    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")
    at.run()
    at.session_state["problem_text"] = at.session_state["_problem_widget"]
    at.session_state["raw_code"] = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"
    at.session_state["current_solution"] = (
        "<problem_statement>x</problem_statement><key_idea>x</key_idea><approach>x</approach>"
        "<code>```python\nx\n```</code><explanation>x</explanation><complexity>x</complexity><takeaway>x</takeaway>"
    )
    at.session_state["session_ai_calls"] = 5  # SESSION_AI_CALL_LIMIT, already exhausted
    at.run()
    assert not at.exception

    error_box = next(w for w in at.text_area if w.key == "error_input_box")
    error_box.set_value("some error")
    fix_btn = next(b for b in at.button if "Fix My Solution" in (b.label or ""))
    fix_btn.click().run()

    assert not at.exception
    # raw_code must be unchanged -- the fix call should have been blocked
    # before ever reaching call_ai.
    assert at.session_state["raw_code"] == "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"


def test_socratic_full_conversation_converges_to_hint_tabs(monkeypatch):
    """Integration test for P2.11: exercises a complete Socratic
    conversation -- opening question, student answers, round 2 question,
    student answers again, convergence into the full hint tabs -- with
    stubbed AI responses (real-shaped, matching what ai_client's prompt
    builders actually ask for) rather than only unit-testing the parsing
    functions in isolation.
    """
    import ai_client

    call_count = {"n": 0}

    def _fake_call_ai(prompt, user_key=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Opening Socratic question
            text = "<question>Why might checking every pair be slow for large inputs?</question>"
        elif call_count["n"] == 2:
            # Round 1 feedback -> next question (not yet final turn)
            text = (
                "<feedback>Right, that's O(n^2).</feedback>"
                "<next_question>What data structure gives O(1) lookups?</next_question>"
            )
        else:
            # Final turn -> converge into hint tabs
            text = (
                "<feedback>Exactly, a hash map!</feedback>"
                "<intuition>Use a hash map to store seen values for O(1) lookup.</intuition>"
                "<walkthrough>Trace nums=[2,7,11,15]: at i=0 seen={}, at i=1 seen={2:0}...</walkthrough>"
                "<pseudocode>for i, n in enumerate(nums): check if target-n in seen</pseudocode>"
            )
        return ai_client.AIResult(text=text, provider="fake-model", notices=[])

    monkeypatch.setattr(ai_client, "call_ai", _fake_call_ai)

    at = _fresh_app()
    socratic_toggle = next(w for w in at.toggle if w.key == "socratic_mode")
    socratic_toggle.set_value(True).run()

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")

    hint_btn = next(b for b in at.button if "Get Hints" in (b.label or ""))
    hint_btn.click().run()
    assert not at.exception, f"crashed on opening question: {at.exception}"
    assert at.session_state["socratic_pending_question"] == "Why might checking every pair be slow for large inputs?"

    # Round 1: answer the opening question
    answer_box = next((w for w in at.text_area if w.key == "socratic_answer_box"), None)
    assert answer_box is not None, "Socratic answer box not found"
    answer_box.set_value("Because you check every pair, that's O(n^2)")
    submit_btn = next(b for b in at.button if "Submit Answer" in (b.label or ""))
    submit_btn.click().run()
    assert not at.exception, f"crashed on round 1 answer: {at.exception}"
    assert at.session_state["socratic_pending_question"] == "What data structure gives O(1) lookups?"
    assert len(at.session_state["socratic_conversation"]) == 1
    assert at.session_state["socratic_conversation"][0]["feedback"] == "Right, that's O(n^2)."

    # Round 2 (final turn): answer again, should converge into hint tabs
    answer_box = next(w for w in at.text_area if w.key == "socratic_answer_box")
    answer_box.set_value("A hash map")
    submit_btn = next(b for b in at.button if "Submit Answer" in (b.label or ""))
    submit_btn.click().run()
    assert not at.exception, f"crashed on round 2 answer: {at.exception}"

    assert at.session_state["socratic_done"] is True
    assert at.session_state["socratic_pending_question"] is None
    assert at.session_state["current_hints"] is not None
    assert "hash map" in at.session_state["current_hints"].lower()
    # Confirm it actually rendered through the hint tabs, not a raw-text fallback.
    assert "<intuition>" in at.session_state["current_hints"]


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


def test_socratic_skip_button_respects_exhausted_session_call_cap():
    """Regression test for B8: the Socratic 'skip to full hints' button
    used to check only the global daily budget and the per-session
    sliding window, silently skipping the per-session 5-free-calls cap
    that every other AI-call site enforced -- letting a user bypass that
    cap via this one button. Now every AI-call site goes through the same
    consolidated check_and_consume_rate_limits() gate.
    """
    at = _fresh_app()

    at.session_state["session_ai_calls"] = 5  # SESSION_AI_CALL_LIMIT, already exhausted
    problem = "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]"
    at.session_state["problem_text"] = problem
    at.session_state["_problem_widget"] = problem
    at.session_state["socratic_pending_question"] = "Why might brute force be slow?"
    at.session_state["socratic_conversation"] = []
    at.session_state["socratic_done"] = False
    at.run()
    assert not at.exception

    skip_btn = next((b for b in at.button if "Just show me the full hints" in (b.label or "")), None)
    assert skip_btn is not None, "skip button not found"
    skip_btn.click().run()
    assert not at.exception

    has_hints = "current_hints" in at.session_state and at.session_state["current_hints"] is not None
    assert not has_hints, "B8 regression: skip button bypassed the exhausted per-session call cap"


def test_socratic_max_turns_is_configurable():
    """Regression test for B19: SOCRATIC_MAX_TURNS was a hardcoded
    constant (always 2 rounds). Now it's a sidebar slider (1-5, default
    2) backed by st.session_state.socratic_max_turns.
    """
    at = _fresh_app()

    toggle = next(w for w in at.toggle if w.key == "socratic_mode")
    toggle.set_value(True).run()
    assert not at.exception

    slider = next((w for w in at.slider if w.key == "socratic_max_turns"), None)
    assert slider is not None, "Socratic rounds slider not found"
    assert slider.value == 2  # default matches ai_client.SOCRATIC_MAX_TURNS

    slider.set_value(4).run()
    assert not at.exception
    assert at.session_state["socratic_max_turns"] == 4


def test_first_run_key_textbox_actually_wires_up_the_key(monkeypatch):
    """Regression test for B6: the first-run "no API keys configured"
    screen's textbox used to capture the typed key into a local variable
    that was immediately discarded by st.stop() -- the key never reached
    anywhere the app could actually use it, leaving a first-time user
    with zero keys stuck at a dead end. Now the typed key is stored in
    session_state and flows into the sidebar's key field, so call_ai()
    actually uses it.

    Note: get_clients() is @st.cache_resource, which persists across
    AppTest reruns within the same pytest process -- so we explicitly
    clear it before (to force re-evaluation with no keys in the
    environment) and after (so we don't leak a "no keys" cache into
    other tests that expect the fake keys set at module import time).
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    st.cache_resource.clear()
    try:
        at = AppTest.from_file(MAIN_PATH, default_timeout=15)
        at.run()
        assert not at.exception, f"App crashed on the no-keys screen: {at.exception}"

        key_widget = next((w for w in at.text_input if w.key == "_fallback_key_widget"), None)
        assert key_widget is not None, "no-keys screen with fallback textbox did not render"

        key_widget.set_value("fake-gemini-key-12345")
        at.run()
        assert not at.exception, f"App crashed after typing a fallback key: {at.exception}"

        assert at.session_state["fallback_user_key"] == "fake-gemini-key-12345"
        sidebar_key_field = next((w for w in at.text_input if "Your Gemini API Key" in (w.label or "")), None)
        assert sidebar_key_field is not None, "app did not proceed past the no-keys screen"
        assert sidebar_key_field.value == "fake-gemini-key-12345", "typed key did not flow into the sidebar field"
    finally:
        st.cache_resource.clear()


def test_save_lesson_to_memory_builds_structured_record(tmp_path, monkeypatch):
    """Seeds a fake generated solution directly into session state (since
    the real AI call can't reach the network in this sandboxed test) and
    clicks 'Save this approach to memory', confirming the resulting
    record is a structured, tagged dict rather than a flat string --
    and that nothing crashes along the way.
    """
    monkeypatch.setenv("CODEUNFOLD_DB_PATH", str(tmp_path / "test_codeunfold.db"))
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
        "<title>Two Sum</title>"
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
    assert saved[0]["title"] == "Two Sum"  # from the <title> tag, not a truncated problem-text guess
    assert "Array" in saved[0]["tags"]  # inferred from "nums" in the problem text
    assert "hash map" in saved[0]["takeaway"].lower()


def test_lessons_persist_across_sessions_for_same_client_id(tmp_path, monkeypatch):
    """Integration test for P1.1: a saved lesson should be reloadable by
    a fresh AppTest run using the same client_id, simulating a tab
    refresh (which keeps the URL, and therefore the ?cid= query param).
    Uses an isolated temp DB path so this test doesn't touch the real
    app's persistence file.
    """
    monkeypatch.setenv("CODEUNFOLD_DB_PATH", str(tmp_path / "test_codeunfold.db"))

    at = AppTest.from_file(MAIN_PATH, default_timeout=15)
    at.run()
    assert not at.exception
    client_id = at.session_state["client_id"]
    assert at.session_state["persistence_available"] is True

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]")
    at.run()
    at.session_state["problem_text"] = at.session_state["_problem_widget"]
    at.session_state["current_solution"] = (
        "<title>Two Sum</title>"
        "<problem_statement>x</problem_statement><key_idea>x</key_idea><approach>x</approach>"
        "<code>```python\nx\n```</code><explanation>x</explanation><complexity>x</complexity>"
        "<takeaway>use a hash map</takeaway>"
    )
    at.run()
    save_btn = next(b for b in at.button if "Save this approach to memory" in (b.label or ""))
    save_btn.click().run()
    assert not at.exception

    # Verify directly against the persistence layer (simulating a fresh
    # session with the same client_id, as a tab refresh would produce).
    import persistence
    loaded = persistence.load_lessons_from_db(persistence.get_db_path(), client_id)
    assert len(loaded) == 1
    assert loaded[0]["title"] == "Two Sum"
    assert loaded[0]["takeaway"] == "use a hash map"


def test_forget_lessons_button_clears_persisted_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEUNFOLD_DB_PATH", str(tmp_path / "test_codeunfold.db"))

    at = AppTest.from_file(MAIN_PATH, default_timeout=15)
    at.run()
    assert not at.exception
    client_id = at.session_state["client_id"]

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [1] -> Output: [1]")
    at.run()
    at.session_state["problem_text"] = at.session_state["_problem_widget"]
    at.session_state["current_solution"] = (
        "<title>Sample</title>"
        "<problem_statement>x</problem_statement><key_idea>x</key_idea><approach>x</approach>"
        "<code>```python\nx\n```</code><explanation>x</explanation><complexity>x</complexity>"
        "<takeaway>t</takeaway>"
    )
    at.run()
    save_btn = next(b for b in at.button if "Save this approach to memory" in (b.label or ""))
    save_btn.click().run()
    assert not at.exception

    forget_btn = next((b for b in at.button if "Forget my saved lessons" in (b.label or "")), None)
    assert forget_btn is not None, "Forget button not found"
    forget_btn.click().run()
    assert not at.exception

    assert at.session_state["lessons_memory"] == []
    import persistence
    assert persistence.load_lessons_from_db(persistence.get_db_path(), client_id) == []


def test_saved_lessons_are_capped_fifo(tmp_path, monkeypatch):
    """Regression test for B17: lessons_memory previously grew without
    bound across a long session. Saving beyond MAX_LESSONS_IN_MEMORY
    should evict the oldest entries, keeping only the most recent ones.
    """
    monkeypatch.setenv("CODEUNFOLD_DB_PATH", str(tmp_path / "test_codeunfold.db"))
    from app_helpers import MAX_LESSONS_IN_MEMORY

    at = AppTest.from_file(MAIN_PATH, default_timeout=15)
    at.run()
    assert not at.exception

    problem_box = next(w for w in at.text_area if w.key == "_problem_widget")
    problem_box.set_value("Example: Input: nums = [1] -> Output: [1]")
    at.run()
    at.session_state["problem_text"] = at.session_state["_problem_widget"]

    for i in range(MAX_LESSONS_IN_MEMORY + 5):
        at.session_state["current_solution"] = (
            f"<title>Problem {i}</title>"
            "<problem_statement>x</problem_statement><key_idea>x</key_idea><approach>x</approach>"
            "<code>```python\nx\n```</code><explanation>x</explanation><complexity>x</complexity>"
            f"<takeaway>takeaway {i}</takeaway>"
        )
        at.session_state["lesson_saved"] = False
        at.run()
        save_btn = next(b for b in at.button if "Save this approach to memory" in (b.label or ""))
        save_btn.click().run()
        assert not at.exception

    saved = at.session_state["lessons_memory"]
    assert len(saved) == MAX_LESSONS_IN_MEMORY
    # Oldest entries (Problem 0..4) should have been evicted; the most
    # recent one (Problem N+4) should still be present.
    assert saved[-1]["title"] == f"Problem {MAX_LESSONS_IN_MEMORY + 4}"
    assert all(int(lesson["title"].split()[-1]) >= 5 for lesson in saved)
