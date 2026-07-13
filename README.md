<div align="center">
  <h1>🤖 CodeUnfold</h1>
  <p><strong>The AI LeetCode Tutor That Actually Teaches</strong></p>
  
  <p>
    <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/built_with-Streamlit-ff4b4b?style=for-the-badge&logo=streamlit&logoColor=white" alt="Built with Streamlit" /></a>
    <a href="https://groq.com/"><img src="https://img.shields.io/badge/Powered%20by-Groq-f59e0b?style=for-the-badge" alt="Powered by Groq" /></a>
    <img src="https://img.shields.io/badge/cost-100%25_free-22c55e?style=for-the-badge" alt="Free" />
    <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License" />
    <a href="https://github.com/mzaman001/CodeUnfold/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/mzaman001/CodeUnfold/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI status" /></a>
  </p>

  <p><em>Paste any LeetCode problem. Get a step-by-step lesson that teaches you how to solve it — not just the answer.</em></p>
</div>

---

## 🌟 Why CodeUnfold?

Most AI tools just spit out the final code. You copy it, paste it, pass the test, and learn absolutely nothing. **CodeUnfold is different.** It forces you to learn.

- 🧠 **Concept-First Explanations:** Every technical term gets a real-world analogy. A hash map is explained *"like a phone book where you search by name instead of flipping pages."*
- 🗣️ **Socratic Hint Mode:** Instead of dumping all the hints at once, the AI asks you one guiding question at a time — you answer, it responds, and after a couple of rounds it converges into the full breakdown. Toggle it on in the sidebar.
- 💡 **Actionable Hints:** Stuck? Click 'Get Hints' to get the exact Data Structure, algorithm name, and the first 2 steps—without spoiling the final solution.
- ⚡ **Groq-Powered Speed:** Built on Groq (Llama 3.3 70B) for lightning-fast 2–4 second responses. Google Gemini 2.5 Flash steps in automatically as a fallback. Solutions and hints stream in token-by-token instead of making you stare at a spinner.
- 💾 **Lessons Survive a Refresh:** Saved lessons persist across a tab refresh (bookmark the URL) via lightweight local storage — not a full account system, but no longer gone the instant you reload.
- 🛠️ **The Fix Loop:** Paste a LeetCode error output. The AI sees the exact failure, diagnoses the issue, and fixes the code dynamically.
- 💸 **100% Free & Open Source:** Runs entirely on free-tier APIs. No credit cards, no subscriptions, no paywalls.

---

## ✨ Features at a Glance

| Feature | Description |
| :--- | :--- |
| **💡 Multi-Tab Hints** | Get unstuck with precise nudges (Intuition, Walkthrough, Pseudocode) instead of the full code. |
| **🗣️ Socratic Hint Mode** | Optional: instead of the full hint breakdown at once, the AI asks one diagnostic question, reacts to your answer, and converges into the full breakdown after a couple of rounds. |
| **🔍 Multi-Tab Solutions** | Full step-by-step lessons broken down into Overview, Logic, Code, and Takeaway tabs. |
| **✅ Execution-Checked Code** | For Python and JavaScript, the generated solution is actually run against the example from the problem before being shown — not just the model's own self-reported "I traced 2 edge cases" claim. |
| **🔧 Code Diff Fix Loop** | Paste your failing LeetCode console output; the AI automatically fixes the code and shows a red/green diff of exactly what changed. |
| **🧠 Structured Session Memory** | Save 1-click takeaways; each is auto-tagged by topic (Hash Map, DP, etc.) so future prompts surface the *relevant* past lessons for the current problem instead of just the most recent ones. |
| **🛡️ Two-Layer Rate Limiting** | A per-session sliding-window nudge, plus a process-wide daily budget shared across every visitor, to keep the shared free-tier API keys from being drained by ordinary traffic growth. See caveats below. |
| **⚡ Streaming Responses** | Solutions and standard hints stream in as they're generated instead of a silent multi-second spinner. |
| **💾 Cross-Refresh Lesson Storage** | Saved lessons survive a tab refresh via a lightweight local SQLite store keyed to the page URL. See Limitations below for exact scope. |
| **📜 Problem History** | Switching to a new problem, or re-clicking Hints/Solve/Fix, never silently discards what you already generated — every problem's latest solution/hints stay one click away in the sidebar. |

---

## 🚀 Quick Start (Under 1 Minute)

**Requirements:** Python 3.10+. Node.js 20+ if you want JavaScript solution verification (Python verification works with no extra setup).

### 1. Get Your Free API Keys
You only need one to start, but both are recommended for failover:
- **[Groq Console](https://console.groq.com)** — Fast, free, no credit card required. *(Primary)*
- **[Google AI Studio](https://aistudio.google.com)** — Generous free tier. *(Fallback)*

### 2. Clone & Setup
```bash
git clone https://github.com/mzaman001/CodeUnfold.git
cd CodeUnfold

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
```

### 3. Add Keys & Run
Edit your `.env` file and paste your API keys:
```env
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

Launch the app:
```bash
streamlit run main.py
```
Open `http://localhost:8501` and paste your first LeetCode problem!

> **Privacy note:** by default this app runs on Google's and Groq's free-tier API keys. Both providers' free-tier terms permit using submitted prompts to improve their models. Pasted LeetCode problems are typically public-domain-ish content, but avoid pasting proprietary take-home assignments or private company code unless you've added your own API key.

---

## 🧪 Running Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
ruff check .
```
Tests cover the pure-function layer (prompt builders, input sanitization, response parsing, rate limiters, the code-verification harness) plus an integration layer that runs the actual `main.py` script end-to-end via Streamlit's `AppTest` framework, catching runtime/widget-lifecycle issues that pure unit tests can't (e.g. session-state conflicts with widget keys). CI runs the same checks on every push/PR (see `.github/workflows/ci.yml`).

---

## 🚧 Limitations (read before deploying)

- **Persistence is best-effort and URL-scoped, not an account system.** Saved lessons survive a tab refresh (same URL) but not a fresh tab/browser without it, don't sync across devices, and live in a local SQLite file that doesn't survive a redeploy on most container platforms' ephemeral storage.
- **Single-instance rate limiting.** The shared daily budget guards one running process. Scaling to multiple instances behind a load balancer gives each instance its own independent budget.
- **Python/JS-only execution verification.** Java/C++/Go/Rust solutions are not run against the example — you see the model's own self-reported correctness for those, same as before this feature existed.
- **Free-tier data handling.** Groq and Gemini's free tiers may retain submitted prompts to improve their models. Don't paste proprietary code (the app shows a one-time reminder on first use).
- **`code_verifier.py` is not a hardened sandbox.** It's a timeout-bounded, best-effort-network-disabled subprocess check appropriate for catching an AI model's wrong answer on a low-traffic personal tool — not a security boundary for executing arbitrary code from anonymous users at scale.

See [`SECURITY.md`](./SECURITY.md) and [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full detail behind each of these.

---

## 🏗️ Architecture & Speed

Built for lightning-fast responses and security, even on public deployments:

- **Strict UI Tab Parsing:** AI responses are strictly forced into XML-like tags, allowing the Streamlit frontend to cleanly parse walls of text into beautiful UI tabs.
- **Prompt Injection Defense:** Every piece of user-controlled text that reaches a prompt — the problem statement, pasted code, pasted error output, and Socratic-mode answers — is sanitized and isolated inside its own XML tag boundary (`<user_problem>`, `<user_code>`, `<failed_code>`, `<error_report>`) before being sent to the model.
- **In-Memory Session State + Best-Effort Persistence:** Current problem/solution state lives purely in Streamlit's session state (gone on refresh, by design — dependency-free and free-tier-friendly). Saved lessons additionally get written to a local SQLite file keyed by a client id in the URL, so they survive a refresh of that same URL — see `persistence.py` and the Limitations section above for the exact (non-account-system) scope.
- **Tag-Aware Lesson Memory:** Saved lessons are tagged by topic via lightweight keyword matching (`lesson_memory.py`) -- no extra AI call, no new dependency. When building a prompt, only lessons whose topics overlap with the current problem are injected, falling back to plain recency if nothing overlaps.
- **Two-Layer Rate Limiting:** A per-session sliding-window limiter (a UX nudge — it resets on a fresh tab/session, so it does not by itself stop shared-quota abuse) plus a process-wide daily token bucket shared across every session on the running instance (the layer that actually protects the shared Groq/Gemini keys from being drained by ordinary traffic growth). Note: the process-wide layer only guards a single running instance — scaling to multiple instances would need a durable, cross-instance store instead.
- **Execution-Checked Solutions:** Python and JavaScript solutions are run against the example extracted from the problem text in a timeout-bounded subprocess before being shown as correct. This is best-effort (regex-based example extraction across three fallback patterns, not a hardened sandbox) — see `code_verifier.py` for exact scope.
- **Dual-Model Routing:** Automatically routes to Groq for speed, and gracefully falls back to Gemini if Groq is rate-limited.

For the full module map and why the code is organized this way, see [`ARCHITECTURE.md`](./ARCHITECTURE.md). For the threat model, sanitization details, and known limitations, see [`SECURITY.md`](./SECURITY.md).

---

## 🤝 Contributing

Human contributor? Start with [`CONTRIBUTING.md`](./CONTRIBUTING.md) for setup and PR expectations.

Working on this with an AI coding agent (Claude Code, Cursor, etc.)? Read [`AGENTS.md`](./AGENTS.md) first — it covers setup, required checks, and a short list of hard rules (mostly: don't reintroduce bugs that have already shipped once).

Contributions are always welcome! Whether it's adding new language sandboxes, improving the prompt engineering, or enhancing the UI.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

<div align="center">
  <p>If CodeUnfold helped you ace an interview, consider giving it a ⭐ on GitHub!</p>
</div>
