<div align="center">
  <h1>CodeUnfold</h1>
  <p><strong>A Socratic AI Tutor for LeetCode</strong></p>
  
  <p>
    <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/built_with-Streamlit-ff4b4b?style=for-the-badge&logo=streamlit&logoColor=white" alt="Built with Streamlit" /></a>
    <a href="https://groq.com/"><img src="https://img.shields.io/badge/Powered%20by-Groq-f59e0b?style=for-the-badge" alt="Powered by Groq" /></a>
    <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License" />
    <a href="https://github.com/mzaman001/CodeUnfold/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/mzaman001/CodeUnfold/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI status" /></a>
  </p>

  <p><em>Paste a LeetCode problem, and the tutor will guide you to the solution conceptually rather than just outputting the final code.</em></p>
  
  <!-- TODO: Add a demo GIF or screenshot of the app here -->
</div>

---

## What is CodeUnfold?

Most AI coding assistants are designed to write code for you. CodeUnfold is designed to teach. When you paste a problem, it uses Socratic questioning and structured hints to help you arrive at the algorithm yourself.

It runs locally as a Streamlit app and uses free-tier LLM APIs (Groq and Gemini) to generate responses.

## Key Features

- **Socratic Hint Mode:** The AI asks guiding questions one at a time. It evaluates your answers and converges on the full algorithm only after a few rounds of interaction.
- **Concept-First Explanations:** Explains data structures and algorithms using real-world analogies before diving into complexity. For example, it explains a hash map as a "phone book where you search by name instead of flipping pages," not just "O(1) lookup."
- **Code Diff Fix Loop:** Paste your failing LeetCode console output, and the app diagnoses the logic flaw, providing a red/green diff of the necessary changes.
- **Durable Problem History:** Automatically snapshots your generated solutions and hints into a local SQLite database, so you don't lose them when switching between problems — or refreshing the page. Restore any past problem from the sidebar.
- **Socratic Session Resume:** If you refresh mid-conversation, the app picks your Socratic exchange back up where it left off.
- **Recall Review:** Retrieval practice on saved lessons and past problems — the app quizzes you on a takeaway's key idea, then gives specific feedback, so what you learned actually sticks.
- **Progress Dashboard:** All-time stats from your history: problems solved, hint-only attempts, fix-loop revisions, and your language/topic coverage.
- **Verified Solutions:** For Python and JavaScript, the generated code is executed locally against the problem's example inputs to verify correctness before it is shown to you.

## Local Setup

**Requirements:** Python 3.10+. Node.js 20+ (optional, required only if you want JavaScript solution verification).

### 1. Get API Keys
The app relies on free-tier APIs. You need at least one, but both are recommended for failover:
- [Groq Console](https://console.groq.com) (Primary, faster response times)
- [Google AI Studio](https://aistudio.google.com) (Fallback)

### 2. Installation
Clone the repository and install the dependencies:

```bash
git clone https://github.com/mzaman001/CodeUnfold.git
cd CodeUnfold

pip install -r requirements.txt
cp .env.example .env
```

### 3. Configuration
Add your API keys to the `.env` file:
```env
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

### 4. Run the App
```bash
streamlit run main.py
```
The app will be available at `http://localhost:8501`.

## Architecture Overview

CodeUnfold is built to be fast, stateless on the server (beyond best-effort SQLite), and secure against basic prompt injection:

- **Strict XML Parsing:** The frontend relies on strictly parsed XML tags from the AI to render multi-tab UI components cleanly.
- **Input Sanitization:** User inputs (problem text, pasted code, errors) are wrapped in isolated XML tags (`<user_problem>`, `<error_report>`) before hitting the LLM to prevent prompt injection.
- **Rate Limiting:** Implements a two-layer rate limit: a per-session sliding window (to nudge users) and a global process-wide daily token budget (to protect free-tier quotas).
- **Session State & SQLite:** Current state is held in Streamlit's in-memory session. Saved lessons, problem history, and in-progress Socratic exchanges are written to a lightweight local SQLite database keyed to the URL.

For a deeper dive into the module structure, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Limitations

- **Persistence:** The local SQLite storage (lessons, problem history, in-progress Socratic exchanges) is URL-scoped and best-effort. It is not a full account system and will not sync across different browsers or devices.
- **Execution Verification:** `code_verifier.py` uses a simple, timeout-bounded subprocess to check code. **It is not a hardened security sandbox.** It is safe for personal use, but do not expose it to untrusted code execution on a public server.
- **Language Support for Verification:** Automated test verification only supports Python and JavaScript. For other languages, the app relies on the LLM's self-reported correctness.

For more details on the threat model and sanitization, see [`SECURITY.md`](./SECURITY.md).

## Contributing & Tests

To run the test suite (which includes both unit tests and Streamlit `AppTest` integration tests):

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
ruff check .
```

If you're working with an AI coding assistant (Claude Code, Cursor, etc.), point it to [`AGENTS.md`](./AGENTS.md) before starting. Human contributors, please read [`CONTRIBUTING.md`](./CONTRIBUTING.md) for pull request guidelines.

## License
MIT
