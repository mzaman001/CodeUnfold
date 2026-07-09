import streamlit as st
import re
import time
import difflib
from dotenv import load_dotenv
from logger import log
import styles
from ai_client import (
    call_ai, build_solve_prompt,
    build_fix_prompt,
    build_pedagogical_hint_prompt, build_code_review_prompt,
    build_socratic_question_prompt, build_socratic_feedback_prompt,
    SOCRATIC_MAX_TURNS,
    get_clients
)
from rate_limiter import RateLimiter
from response_parser import (
    extract_tag, extract_code_block, extract_hint_sections,
    extract_review_sections, extract_solution_sections,
    extract_socratic_question, extract_socratic_followup,
)
from code_verifier import verify_solution
from lesson_memory import build_lesson
from app_helpers import (
    MAX_PROBLEM_CHARS, MAX_CODE_CHARS, SESSION_AI_CALL_LIMIT,
    _enforce_server_side_length, _get_user_code_capped,
    _check_session_limit, _increment_session_calls, _show_session_limit_warning,
    _check_global_limit, _get_lessons_context, _show_error,
)

load_dotenv()

st.set_page_config(page_title="CodeUnfold", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

# ---------- CSS ----------
st.markdown(styles.BASE_CSS, unsafe_allow_html=True)


# Initialize AI clients on start
_default_gemini, _groq_client = get_clients()

if not _default_gemini and not _groq_client:
    st.error("🔑 No API keys configured. The app can't function without at least one.")
    st.markdown("""
    **Get a free Groq key in 30 seconds (recommended):**
    1. Go to [console.groq.com](https://console.groq.com)
    2. Sign in → Create API Key → Copy it
    3. Paste it below or add it to your `.env` file as `GROQ_API_KEY`
    """)
    user_key_setup = st.text_input("Paste your Groq or Gemini API key here to continue:", type="password")
    st.stop()
elif not _default_gemini:
    st.sidebar.warning("⚠️ Gemini key not set. Using Groq only.")
elif not _groq_client:
    st.sidebar.warning("⚠️ Groq key not set. Using Gemini only (slower).")


# ---------- Session State ----------
_defaults = {
    "problem_text": "",
    "current_solution": None,
    "current_hints": None,
    "raw_code": "",
    "show_update_alert": False,
    "lesson_saved": False,
    "attempt_errors": [],
    "verification": None,
    "language": "Python",
    "user_code": "",
    "socratic_mode": False,
    "socratic_conversation": [],
    "socratic_pending_question": None,
    "socratic_done": False,
}
for key, default in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

if "ai_limiter" not in st.session_state:
    st.session_state.ai_limiter = RateLimiter(max_calls=15, window_seconds=60)
    st.session_state.session_ai_calls = 0  # Per-visitor cap counter
    st.session_state.lessons_memory = []  # Ephemeral memory for this session

def _reset_problem_state():
    """Clears everything derived from the current problem/language/code.
    Shared by the language-change handler and the form-submit handler so
    the reset list only has to be maintained in one place (the two paths
    used to duplicate this inline -- see the audit's dead-code finding
    for the analogous `_sync_problem` duplication this replaces)."""
    st.session_state.current_solution = None
    st.session_state.current_hints = None
    st.session_state.raw_code = ""
    st.session_state.attempt_errors = []
    st.session_state.lesson_saved = False
    st.session_state.verification = None
    st.session_state.socratic_conversation = []
    st.session_state.socratic_pending_question = None
    st.session_state.socratic_done = False

def _sync_language():
    _reset_problem_state()
    st.session_state.user_code = ""

def _trigger_fix_loop(prob_text: str, errors: list, user_key: str = None):
    error_history = "\n".join(f"Error #{i + 1}:\n{e}" for i, e in enumerate(errors))
    code_to_fix = st.session_state.raw_code or "(code unavailable)"
    
    fix_prompt = build_fix_prompt(
        prob_text, code_to_fix, error_history, 
        st.session_state.language, _get_lessons_context(prob_text)
    )
    
    if not _check_session_limit(user_key):
        st.warning(f"💡 You've used all {SESSION_AI_CALL_LIMIT} free AI calls for this session. Add your own free Gemini API key in ⚙️ **Settings** in the sidebar for unlimited access.")
        return
    if not st.session_state.ai_limiter.allow():
        st.error("Too many requests! Please wait a moment.")
        return
    if not _check_global_limit(user_key):
        st.error(
            "🛑 This app has hit its shared daily AI quota (protecting the free Groq/Gemini keys "
            "everyone shares). Add your own free Gemini API key in ⚙️ **Settings** for unlimited access, "
            "or try again after the daily reset."
        )
        return

    with st.spinner("Analyzing error and generating fix..."):
        try:
            old_code = st.session_state.raw_code
            t0 = time.time()
            new_text = call_ai(fix_prompt, user_key)
            t1 = time.time()
            _increment_session_calls()
            
            # Extract the main solution code robustly via XML tags
            st.session_state.raw_code = extract_code_block(new_text)

            # Re-verify: a "fix" is only actually a fix if it passes the
            # example. Re-running this here (not just after the initial
            # solve) closes the same trust gap for the fix loop.
            st.session_state.verification = verify_solution(
                st.session_state.raw_code, st.session_state.language, prob_text
            )

            if old_code and st.session_state.raw_code:
                diff = list(difflib.unified_diff(
                    old_code.splitlines(), 
                    st.session_state.raw_code.splitlines(), 
                    fromfile='Previous Code', 
                    tofile='Fixed Code', 
                    lineterm=''
                ))
                if diff:
                    diff_text = "\n".join(diff)
                    diff_markdown = f"### 🔍 Code Diff (What Changed)\n```diff\n{diff_text}\n```\n\n---\n\n"
                    # Inject diff into problem_statement tag so it renders in the Overview tab
                    if "<problem_statement>" in new_text:
                        new_text = re.sub(r"(<problem_statement>)", r"\1\n" + diff_markdown, new_text, flags=re.IGNORECASE)
                    else:
                        new_text = diff_markdown + new_text

            new_text = new_text + f"\n\n---\n*⏱️ Fix generated in {t1-t0:.1f}s*"
            st.session_state.current_solution = new_text
            st.session_state.show_update_alert = True
            st.rerun()
        except Exception as e:
            st.error(f"An error occurred: {e}")


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 🤖 CodeUnfold")
    st.caption("AI-Powered LeetCode Tutor")
    st.divider()

    st.markdown("### ⚡ API Status")
    status_col1, status_col2 = st.columns(2)
    with status_col1:
        if _groq_client:
            st.success("Groq ✓")
        else:
            st.error("Groq ✗")
    with status_col2:
        if _default_gemini:
            st.success("Gemini ✓")
        else:
            st.error("Gemini ✗")
    
    st.divider()

    st.radio("UI Theme", ["AMOLED", "Deep Dark"], key="theme", horizontal=True)

    st.toggle(
        "🧠 Socratic Hints",
        key="socratic_mode",
        help="When on, 'Get Hints' asks you one guiding question at a time instead of showing everything at once. Answer a couple of rounds and it converges into the full hint breakdown.",
    )

    with st.expander("🔑 API Settings", expanded=False):
        user_gemini_key = st.text_input("Your Gemini API Key (Optional)", type="password")
        if user_gemini_key:
            st.toast("Using your personal Gemini key!", icon="✅")
    
    with st.expander("🧠 Session Memory", expanded=True):
        st.caption("Lessons save for this session. Persist longer by self-hosting.")
        # Read the structured records directly rather than round-tripping
        # through the formatted prompt-context string (which was fragile
        # to parse back apart, e.g. if a takeaway itself contained a line
        # starting with "- ").
        saved_lessons = st.session_state.get("lessons_memory", [])
        if saved_lessons:
            for lesson in reversed(saved_lessons[-5:]):
                tag_prefix = f"`{', '.join(lesson['tags'])}` " if lesson.get("tags") else ""
                summary = f"{lesson['title']}: {lesson['takeaway']}"
                st.caption(f"• {tag_prefix}{summary[:60]}{'...' if len(summary) > 60 else ''}")
        else:
            st.caption("No lessons yet.")

# ---------- Dynamic CSS Injection ----------
bg_color = "#000000" if st.session_state.get("theme") == "AMOLED" else "#0f172a"
sidebar_bg = "#000000" if st.session_state.get("theme") == "AMOLED" else "#1e293b"

st.markdown(styles.theme_css(bg_color, sidebar_bg), unsafe_allow_html=True)


# ---------- Main UI ----------
header_col1, header_col2 = st.columns([2, 1])
with header_col1:
    st.markdown("# 🤖 CodeUnfold")
with header_col2:
    st.selectbox(
        "Language", ["Python", "JavaScript", "Java", "C++", "Go", "Rust"],
        key="language",
        on_change=_sync_language,
        label_visibility="collapsed"
    )
    if st.session_state.language not in ["Python", "JavaScript"]:
        st.caption("ℹ️ Solutions in this language aren't run against the example (verification only supports Python/JS)")

st.markdown("### Problem Input")
with st.form("input_form"):
    st.text_area(
        "Paste your coding problem here:",
        height=150,
        max_chars=5000,
        key="_problem_widget",
        placeholder="Paste problem description + starter code template...\n\nTip: Include both the problem AND the starter code for best results.",
        label_visibility="collapsed"
    )

    st.text_area(
        "Your Current Code (Optional):",
        height=150,
        max_chars=5000,
        key="user_code",
        placeholder="Paste your current attempt here if you want a code review instead of generic hints...",
        label_visibility="visible"
    )

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        hint_button = st.form_submit_button("💡 Get Hints", use_container_width=True, type="secondary")
    with btn_col2:
        solve_button = st.form_submit_button("🔍 Reveal Solution", use_container_width=True, type="primary")

# Manual state sync when form is submitted
if hint_button or solve_button:
    # Server-side enforcement: the widgets' `max_chars` is a client-side
    # property only. A request crafted outside the browser could still
    # reach this handler with an oversized value, so re-truncate here
    # before anything derived from it reaches a prompt builder.
    #
    # Note: `user_code` is NOT re-truncated here even though it has the
    # same enforcement need, because `user_code` is also the *widget key*
    # for the code editor below -- Streamlit raises a StreamlitAPIException
    # if session_state for an already-instantiated widget's key is set
    # directly in the same run. Its length is enforced instead at the
    # point of use, via `_get_user_code_capped()` below.
    new_text = _enforce_server_side_length(st.session_state._problem_widget, MAX_PROBLEM_CHARS)
    if new_text != st.session_state.problem_text:
        st.session_state.problem_text = new_text
        _reset_problem_state()

problem_text = st.session_state.problem_text

# ---------- Onboarding Welcome ----------
if not problem_text:
    st.markdown("---")
    st.markdown("### 👋 Welcome to CodeUnfold")
    st.markdown("""
    **How it works:**
    1. Paste any LeetCode problem — include the starter code template for best results
    2. Click **Get Hints** to get guided nudges and solve it yourself
    3. Click **Reveal Solution** for a full step-by-step lesson with analogies
    4. Save proven approaches to session memory
    """)
    st.markdown("### 🚀 Try it now with an example")
    ex_col1, ex_col2 = st.columns(2)
    with ex_col1:
        if st.button("🔢 Two Sum", use_container_width=True):
            _text = """Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target. You may assume that each input would have exactly one solution, and you may not use the same element twice.

Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]

class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:"""
            st.session_state.problem_text = _text
            st.session_state["_problem_widget"] = _text
            _reset_problem_state()
            st.rerun()
    with ex_col2:
        if st.button("💞 Valid Parentheses", use_container_width=True):
            _text = """Given a string s containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid. An input string is valid if open brackets are closed by the same type of brackets, and in the correct order.

Example: Input: s = "()[]{}" -> Output: true

class Solution:
    def isValid(self, s: str) -> bool:"""
            st.session_state.problem_text = _text
            st.session_state["_problem_widget"] = _text
            _reset_problem_state()
            st.rerun()


if hint_button and problem_text:
    log.info(f"User Action: Request Hint - Language: {st.session_state.language}")
    if st.session_state.current_hints:
        st.rerun()  # Already generated, just display
    if st.session_state.socratic_pending_question and not st.session_state.socratic_done:
        st.rerun()  # Socratic exchange already in progress, don't restart it
    if not _check_session_limit(user_gemini_key):
        st.warning(f"💡 You've used all {SESSION_AI_CALL_LIMIT} free AI calls for this session. Add your own free Gemini API key in ⚙️ **Settings** in the sidebar for unlimited access.")
        st.stop()
    if not st.session_state.ai_limiter.allow():
        st.error("⏳ Too many requests! Please wait a moment.")
        st.stop()
    if not _check_global_limit(user_gemini_key):
        st.error(
            "🛑 This app has hit its shared daily AI quota (protecting the free Groq/Gemini keys "
            "everyone shares). Add your own free Gemini API key in ⚙️ **Settings** for unlimited access, "
            "or try again after the daily reset."
        )
        st.stop()
    _show_session_limit_warning()
        
    user_code_capped = _get_user_code_capped()
    if user_code_capped and len(user_code_capped.strip()) > 5:
        hint_prompt = build_code_review_prompt(problem_text, user_code_capped, st.session_state.language)
        spinner_msg = "Reviewing your code..."
    elif st.session_state.socratic_mode:
        # Socratic mode: ask one diagnostic question instead of the full
        # hint breakdown. The answer-submission flow lives further down,
        # in the "Display Socratic Flow" block, since it happens on a
        # follow-up interaction rather than this initial button click.
        try:
            with st.spinner("Thinking of a question to ask you..."):
                q_result = call_ai(build_socratic_question_prompt(problem_text, st.session_state.language), user_gemini_key)
            _increment_session_calls()
            question = extract_socratic_question(q_result)
            if question:
                st.session_state.socratic_pending_question = question
                st.session_state.socratic_conversation = []
                st.session_state.socratic_done = False
                st.rerun()
            else:
                # Model didn't follow the format -- fall back to the
                # standard hint flow rather than showing a dead end.
                hint_prompt = build_pedagogical_hint_prompt(problem_text, st.session_state.language)
                with st.spinner("Analyzing problem and generating hints..."):
                    result = call_ai(hint_prompt, user_gemini_key)
                _increment_session_calls()
                st.session_state.current_hints = result
                st.session_state.current_solution = None
                st.rerun()
        except Exception as e:
            _show_error(e, "Socratic question generation")
        st.stop()
    else:
        hint_prompt = build_pedagogical_hint_prompt(problem_text, st.session_state.language)
        spinner_msg = "Analyzing problem and generating hints..."
        
    try:
        with st.spinner(spinner_msg):
            t0 = time.time()
            result = call_ai(hint_prompt, user_gemini_key)
            t1 = time.time()
                
        result += f"\n\n---\n*⏱️ Hints generated in {t1-t0:.1f}s*"
        _increment_session_calls()
        st.session_state.current_hints = result
        st.session_state.current_solution = None
        st.rerun()
    except Exception as e:
        _show_error(e, "hint generation")

elif solve_button and problem_text:
    log.info(f"User Action: Reveal Solution - Language: {st.session_state.language}")
    if st.session_state.current_solution:
        st.rerun()  # Already generated, just display
    if not _check_session_limit(user_gemini_key):
        st.warning(f"💡 You've used all {SESSION_AI_CALL_LIMIT} free AI calls for this session. Add your own free Gemini API key in ⚙️ **Settings** in the sidebar for unlimited access.")
        st.stop()
    if not st.session_state.ai_limiter.allow():
        st.error("⏳ Too many requests! Please wait a moment.")
        st.stop()
    if not _check_global_limit(user_gemini_key):
        st.error(
            "🛑 This app has hit its shared daily AI quota (protecting the free Groq/Gemini keys "
            "everyone shares). Add your own free Gemini API key in ⚙️ **Settings** for unlimited access, "
            "or try again after the daily reset."
        )
        st.stop()

    st.session_state.attempt_errors = []
    st.session_state.lesson_saved = False

    solve_prompt = build_solve_prompt(problem_text, st.session_state.language, _get_lessons_context(problem_text))
    
    try:
        with st.spinner(f"Generating {st.session_state.language} lesson..."):
            t0 = time.time()
            result = call_ai(solve_prompt, user_gemini_key)
            t1 = time.time()

        result = result + f"\n\n---\n*⏱️ Lesson generated in {t1-t0:.1f}s*"
        _increment_session_calls()
        st.session_state.raw_code = extract_code_block(result)

        # Actually run the extracted code against the example(s) in the
        # problem text instead of trusting the model's own "I mentally
        # traced 2 edge cases" narration. See code_verifier.py for scope
        # and limitations of this check.
        with st.spinner("Checking the solution against the example..."):
            st.session_state.verification = verify_solution(
                st.session_state.raw_code, st.session_state.language, problem_text
            )

        st.session_state.current_solution = result.strip()
        st.session_state.current_hints = None
        st.session_state.show_update_alert = False
        st.session_state.lesson_saved = False
        st.rerun()
    except Exception as e:
        _show_error(e, "solution generation")


# ---------- Display Socratic Flow ----------
if st.session_state.socratic_pending_question and not st.session_state.socratic_done:
    with st.chat_message("user", avatar="👤"):
        st.markdown(f"**Problem:** {problem_text[:80]}...")
    with st.chat_message("assistant", avatar="🤖"):
        turn_number = len(st.session_state.socratic_conversation) + 1
        st.markdown(f"### 🧠 Socratic Hint — Round {turn_number} of {SOCRATIC_MAX_TURNS}")
        for past in st.session_state.socratic_conversation:
            st.markdown(f"**Q:** {past['question']}")
            st.caption(f"Your answer: {past['answer']}")
            if past.get("feedback"):
                st.info(past["feedback"])
        st.markdown(f"**Q:** {st.session_state.socratic_pending_question}")

        answer = st.text_area("Your answer:", key="socratic_answer_box", height=80)
        col_a, col_b = st.columns([1, 1])
        submit_answer = col_a.button("↩️ Submit Answer", use_container_width=True, key="socratic_submit")
        skip_socratic = col_b.button("⏭️ Just show me the full hints", use_container_width=True, key="socratic_skip")

        if skip_socratic:
            if not _check_global_limit(user_gemini_key) or not st.session_state.ai_limiter.allow():
                st.error("⏳ Rate limited — please wait a moment and try again.")
                st.stop()
            try:
                with st.spinner("Analyzing problem and generating hints..."):
                    result = call_ai(build_pedagogical_hint_prompt(problem_text, st.session_state.language), user_gemini_key)
                _increment_session_calls()
                st.session_state.current_hints = result
                st.session_state.current_solution = None
                st.session_state.socratic_pending_question = None
                st.session_state.socratic_done = True
                st.rerun()
            except Exception as e:
                _show_error(e, "hint generation")

        if submit_answer:
            if not answer.strip():
                st.warning("Type an answer first (even a guess is fine!).")
            elif not _check_global_limit(user_gemini_key) or not st.session_state.ai_limiter.allow():
                st.error("⏳ Rate limited — please wait a moment and try again.")
            else:
                answer_capped = _enforce_server_side_length(answer.strip(), MAX_CODE_CHARS)
                is_final_turn = turn_number >= SOCRATIC_MAX_TURNS
                conversation_so_far = st.session_state.socratic_conversation + [
                    {"question": st.session_state.socratic_pending_question, "answer": answer_capped}
                ]
                try:
                    with st.spinner("Reading your answer..."):
                        fb_result = call_ai(
                            build_socratic_feedback_prompt(
                                problem_text, st.session_state.language, conversation_so_far, is_final_turn
                            ),
                            user_gemini_key,
                        )
                    _increment_session_calls()
                    parsed = extract_socratic_followup(fb_result)

                    if parsed is None:
                        # Model didn't follow the expected format -- don't get
                        # stuck in a broken loop, fall back to full hints.
                        st.session_state.current_hints = fb_result
                        st.session_state.current_solution = None
                        st.session_state.socratic_pending_question = None
                        st.session_state.socratic_done = True
                    elif parsed["kind"] == "converged":
                        conversation_so_far[-1]["feedback"] = parsed["feedback"]
                        st.session_state.socratic_conversation = conversation_so_far
                        st.session_state.current_hints = fb_result
                        st.session_state.current_solution = None
                        st.session_state.socratic_pending_question = None
                        st.session_state.socratic_done = True
                    else:  # "next_question"
                        conversation_so_far[-1]["feedback"] = parsed["feedback"]
                        st.session_state.socratic_conversation = conversation_so_far
                        st.session_state.socratic_pending_question = parsed["next_question"]
                    st.rerun()
                except Exception as e:
                    _show_error(e, "Socratic follow-up")

# ---------- Display Hints ----------
if st.session_state.current_hints and not st.session_state.current_solution:
    with st.chat_message("user", avatar="👤"):
        st.markdown(f"**Problem:** {problem_text[:80]}...")
    with st.chat_message("assistant", avatar="🤖"):
        hints_text = st.session_state.current_hints
        review = extract_review_sections(hints_text)
        hints = extract_hint_sections(hints_text)

        if review:
            st.markdown("### 🧑‍💻 Code Review")
            tab1, tab2, tab3 = st.tabs(["🔍 Critique", "🧠 Logic Flaw", "🏗️ Fix Direction"])
            with tab1:
                st.markdown(review["critique"])
            with tab2:
                st.markdown(review["logic_flaw"])
            with tab3:
                st.markdown(review["fix_direction"])
        elif hints:
            # If this hint text is the convergence point of a Socratic
            # exchange, it carries a <feedback> tag acknowledging the
            # student's last answer -- surface it instead of dropping it,
            # since it's the natural bridge from the Q&A into these tabs.
            socratic_feedback = extract_tag(hints_text, "feedback")
            if socratic_feedback:
                st.success(socratic_feedback)
            st.markdown("### 💡 Hints & Strategy")
            tab1, tab2, tab3 = st.tabs(["🧠 Intuition", "🚶 Walkthrough", "🏗️ Pseudo-code"])
            with tab1:
                st.markdown(hints["intuition"])
            with tab2:
                st.markdown(hints["walkthrough"])
            with tab3:
                st.markdown(hints["pseudocode"])
        else:
            # Fallback if AI failed to format properly
            st.write(hints_text)

# ---------- Display Solution + Fix Loop ----------
if st.session_state.current_solution:
    with st.chat_message("user", avatar="👤"):
        st.markdown(f"**Problem:** {problem_text[:80]}...")

    with st.chat_message("assistant", avatar="🤖"):
        if st.session_state.show_update_alert:
            st.success("Solution updated based on your error report.")
            st.session_state.show_update_alert = False

        st.markdown("### Solution Breakdown")
        sol_text = st.session_state.current_solution
        sections = extract_solution_sections(sol_text)

        if sections:
            s_tab1, s_tab2, s_tab3, s_tab4 = st.tabs(["📖 Overview", "🧠 Logic", "💻 Code", "💡 Takeaway"])
            with s_tab1:
                st.markdown(sections["problem_statement"])
                st.markdown(sections["key_idea"])
            with s_tab2:
                st.markdown(sections["approach"])
                st.markdown(sections["complexity"])
            with s_tab3:
                verification = st.session_state.get("verification")
                if verification:
                    if verification["verified"] and verification["passed"]:
                        st.success("✅ Ran against the example input — output matched.", icon="✅")
                    elif verification["verified"] and not verification["passed"]:
                        failed = [r for r in verification["results"] if r["passed"] is False]
                        detail = failed[0]["error"] if failed else "output did not match"
                        st.error(f"❌ Ran against the example input — this did **not** match: {detail}")
                    else:
                        st.caption(f"ℹ️ Not auto-verified: {verification['reason']}.")
                st.markdown(sections["code"])
                st.markdown(sections["explanation"])
            with s_tab4:
                st.markdown(sections["takeaway"])
        else:
            st.write(sol_text)

        error_count = len(st.session_state.attempt_errors)
        if error_count > 0:
            st.caption(f"🔄 Revised {error_count} time(s) based on your feedback.")

        # Save Memory
        if st.session_state.get("lesson_saved", False):
            st.success("✅ Saved to session memory!", icon="🧠")
            if st.button("Undo (Remove from Memory)"):
                if st.session_state.lessons_memory:
                    st.session_state.lessons_memory.pop()
                st.session_state.lesson_saved = False
                st.rerun()
        else:
            if st.button("💾 Save this approach to memory", use_container_width=True):
                sol_text = st.session_state.current_solution
                takeaway_text = extract_tag(sol_text, "takeaway") or "Saved solution approach."
                
                # Prepend the problem title (first line of problem text) to give context
                title = problem_text.split('\n')[0][:50] if problem_text else "Unknown Problem"
                lesson = build_lesson(title, takeaway_text, problem_text, st.session_state.language)
                
                st.session_state.lessons_memory.append(lesson)
                st.session_state.lesson_saved = True
                st.balloons()
                st.rerun()

        # Manual Fix Expander
        with st.expander("🐛 Paste a LeetCode error to fix the solution"):
            st.caption("Paste any error directly from LeetCode. The AI uses the exact real error to fix the code.")
            error_input = st.text_area("LeetCode error output:", height=120, key="error_input_box", label_visibility="collapsed")
            if st.button("🔧 Fix My Solution", type="primary", use_container_width=True):
                log.info("User Action: Submit LeetCode Error")
                if not error_input.strip():
                    st.warning("Paste your error output first.")
                else:
                    trimmed = _enforce_server_side_length(error_input.strip(), MAX_CODE_CHARS)
                    st.session_state.attempt_errors.append(trimmed)
                    st.session_state.attempt_errors = st.session_state.attempt_errors[-3:]
                    _trigger_fix_loop(problem_text, st.session_state.attempt_errors, user_gemini_key)
