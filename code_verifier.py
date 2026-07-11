"""Best-effort execution-based verification of AI-generated solutions.

This directly addresses the audit's top-ranked finding: the app's prior
"Verification" step was the model narrating that it "mentally traced 2
edge cases" against the code it just wrote — a hallucination-prone claim,
not a check. If the model's code was subtly wrong, the student learned
the wrong thing with full confidence.

This module replaces that narration with an actual subprocess execution
for Python and JavaScript — the two languages the rest of the app already
special-cases with "No local run support" messaging for every other
language. If it can't verify (no extractable example, no runtime
available, unsupported language), it says so explicitly rather than
silently implying success.

Scope, stated plainly (do not oversell this the way the old feature
oversold itself):
- Example extraction from the pasted problem text is regex-based and
  best-effort. It handles the "Input: ... -> Output: ..." and
  "Input: ...\\nOutput: ..." shapes the app's own example problems (and
  most pasted LeetCode problems) use. Anything more exotic won't be
  found, and verification is skipped rather than guessed at.
- Python method-signature inference is also regex-based: it reads the
  first method defined on `class Solution` and maps input variables to
  parameters by name.
- This is a lightweight, timeout-bounded, best-effort-network-disabled
  subprocess check meant to catch obviously wrong output on the
  student's own machine's trust boundary (a single free Streamlit
  instance, not a multi-tenant code execution service). It is NOT a
  hardened sandbox suitable for executing arbitrary untrusted code from
  the open internet — the CPU/memory rlimits and timeout are a safety
  net against a buggy or slow AI-generated solution, not a security
  boundary against a malicious one. If this app's threat model ever
  changes (e.g. accepting code from anonymous internet users to execute
  on shared infra), this needs a real sandbox (gVisor, Docker
  --network=none, or a hosted execution API), not this.
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 5
MAX_EXAMPLES = 3

# Pass 1 (primary): the "Input: ... Output: ..." shape, on one line or
# across two lines. Covers the app's own example problems and most
# pasted LeetCode problems.
_EXAMPLE_RE = re.compile(
    r"input:\s*(?P<input>.*?)\s*(?:->\s*)?output:\s*(?P<output>.*?)"
    r"(?=\n\s*\n|\n\s*input:|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Pass 2 (fallback): "Example 1: nums = [2,7,11,15], target = 9, Output:
# [0,1]" -- variable assignments given directly after "Example N:" with
# no separate "Input:" label, just a trailing "Output:". Common in
# problems pasted from sources that compress the Input: line away.
_EXAMPLE_NO_INPUT_LABEL_RE = re.compile(
    r"example\s*\d*\s*:\s*(?P<input>[a-zA-Z_]\w*\s*=.*?)\s*,?\s*output:\s*(?P<output>.*?)"
    r"(?=\n\s*\n|\n\s*example\s*\d*\s*:|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Pass 3 (fallback): the bare "assignments -> result" arrow shape with no
# Input:/Output: labels at all (the shape this app's own quick-start
# example problems use in their one-liner summaries).
_EXAMPLE_ARROW_RE = re.compile(
    r"(?P<input>[a-zA-Z_]\w*\s*=\s*.+?)\s*->\s*(?P<output>.+?)(?=\n|\Z)",
    re.IGNORECASE,
)


def _run_pass(pattern: re.Pattern, text: str) -> list:
    examples = []
    for m in pattern.finditer(text or ""):
        inp = m.group("input").strip().strip(",")
        out = m.group("output").strip()
        # Trim trailing junk a greedy line-boundary miss could pull in.
        out = out.splitlines()[0].strip() if out else out
        if inp and out:
            examples.append({"input": inp, "output": out})
        if len(examples) >= MAX_EXAMPLES:
            break
    return examples


def extract_examples(problem_text: str) -> list:
    """Best-effort extraction of (input_str, output_str) pairs.

    Tries progressively looser patterns until one matches: the standard
    "Input: ... Output: ..." shape first, then "Example N: <assignments>,
    Output: ..." (no separate Input: label), then a bare "<assignments> ->
    <result>" arrow shape. Stops at the first pass that finds anything,
    rather than combining passes, to keep results predictable -- once a
    problem's format is recognized, later looser passes won't also fire
    and produce noisy duplicate/conflicting matches.

    Returns a list of dicts: {"input": "...", "output": "..."}.
    Empty list if nothing matched — callers must treat that as
    "verification not possible", never as "verification passed".
    """
    text = problem_text or ""
    for pattern in (_EXAMPLE_RE, _EXAMPLE_NO_INPUT_LABEL_RE, _EXAMPLE_ARROW_RE):
        examples = _run_pass(pattern, text)
        if examples:
            return examples
    return []


def _to_python_literal(raw: str):
    """Converts a LeetCode-style literal (incl. true/false/null) to Python."""
    s = raw.strip().rstrip(",")
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        return ast.literal_eval(s)
    except Exception:
        # Bare/unquoted string fallback (e.g. an identifier-like output).
        return s


def _parse_assignments(input_str: str) -> dict:
    """Parses "nums = [2,7,11,15], target = 9" into {"nums": [...], "target": 9}.

    Best-effort: assumes at most one level of nesting inside each value
    (typical for LeetCode-style examples). Falls back to skipping a
    variable it can't confidently parse rather than raising.
    """
    assignments = {}
    pairs = re.findall(r"(\w+)\s*=\s*(.*?)(?=,\s*\w+\s*=|\Z)", input_str, re.DOTALL)
    for name, raw_value in pairs:
        try:
            assignments[name] = _to_python_literal(raw_value)
        except Exception:
            continue
    return assignments


def _infer_python_method(code: str):
    """Finds the first method on `class Solution` and its parameter names.

    The parameter group after `self` is optional -- a method with no
    other parameters (e.g. `def isPalindrome(self):`) previously failed
    to match at all (the regex required a literal comma after `self`),
    silently falling through to "couldn't be matched to the solution's
    parameters" with no indication the regex itself was the problem.
    """
    m = re.search(r"class\s+Solution\b.*?def\s+(\w+)\s*\(self\s*(?:,\s*([^)]*))?\)", code, re.DOTALL)
    if not m:
        return None
    method_name = m.group(1)
    params = []
    for p in (m.group(2) or "").split(","):
        p = p.strip()
        if not p:
            continue
        name = p.split(":")[0].split("=")[0].strip()
        if name:
            params.append(name)
    return method_name, params


_PY_HARNESS_TEMPLATE = """
import sys, json, socket

# Best-effort resource limits: a safety net against a slow/buggy
# AI-generated solution (e.g. an accidental infinite loop), not a
# security boundary. See code_verifier.py module docstring.
# `resource` is Unix-only (no such module on Windows), so both the
# import and the setrlimit calls are optional -- the subprocess timeout
# in the parent process is the real, cross-platform backstop.
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
except Exception:
    pass

def _blocked_socket(*a, **kw):
    raise OSError("network access disabled during verification")
socket.socket = _blocked_socket

sys.path.insert(0, {solution_dir!r})
try:
    from solution_module import Solution
    sol = Solution()
    kwargs = {kwargs!r}
    result = getattr(sol, {method_name!r})(**kwargs)
    expected = {expected!r}
    if result == expected:
        print("PASS")
    else:
        print(f"FAIL|{{result!r}}|{{expected!r}}")
except Exception as e:
    print(f"ERROR|{{type(e).__name__}}: {{e}}")
"""


def _run_python_example(code: str, example: dict, tmpdir: Path) -> dict:
    inferred = _infer_python_method(code)
    if not inferred:
        return {**example, "passed": None, "error": "could not identify a Solution method to call"}
    method_name, params = inferred

    assignments = _parse_assignments(example["input"])
    kwargs = {p: assignments[p] for p in params if p in assignments}
    if len(kwargs) != len(params):
        return {**example, "passed": None, "error": "could not map example input to method parameters"}

    expected = _to_python_literal(example["output"])

    solution_path = tmpdir / "solution_module.py"
    solution_path.write_text(code)

    harness_code = _PY_HARNESS_TEMPLATE.format(
        solution_dir=str(tmpdir), kwargs=kwargs, method_name=method_name, expected=expected
    )
    harness_path = tmpdir / "harness.py"
    harness_path.write_text(harness_code)

    try:
        proc = subprocess.run(
            [sys.executable, str(harness_path)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            cwd=str(tmpdir),
        )
    except subprocess.TimeoutExpired:
        return {**example, "passed": False, "error": f"timed out after {TIMEOUT_SECONDS}s"}

    out = proc.stdout.strip()
    if out == "PASS":
        return {**example, "passed": True, "error": None}
    if out.startswith("FAIL|"):
        _, got, exp = out.split("|", 2)
        return {**example, "passed": False, "error": f"got {got}, expected {exp}"}
    if out.startswith("ERROR|"):
        return {**example, "passed": False, "error": out.split("|", 1)[1]}
    return {**example, "passed": False, "error": (proc.stderr or "unknown execution error")[:200]}


_JS_HARNESS_TEMPLATE = """
const solution = require({solution_path!r});
const input = {input_json};
const expected = {expected_json};
try {{
  const Cls = solution.Solution || solution;
  const inst = new Cls();
  const methodName = Object.getOwnPropertyNames(Cls.prototype).find(n => n !== 'constructor');
  const result = inst[methodName](...input);
  if (JSON.stringify(result) === JSON.stringify(expected)) {{
    console.log("PASS");
  }} else {{
    console.log("FAIL|" + JSON.stringify(result) + "|" + JSON.stringify(expected));
  }}
}} catch (e) {{
  console.log("ERROR|" + e.toString());
}}
"""


def _run_js_example(code: str, example: dict, tmpdir: Path) -> dict:
    assignments = _parse_assignments(example["input"])
    if not assignments:
        return {**example, "passed": None, "error": "could not parse example input"}

    expected = _to_python_literal(example["output"])

    # Best-effort: append a CommonJS export so `require()` can reach the class.
    export_code = code + "\nmodule.exports = typeof Solution !== 'undefined' ? Solution : module.exports;\n"
    solution_path = tmpdir / "solution.js"
    solution_path.write_text(export_code)

    # json.dumps produces valid JS-literal-compatible JSON regardless of
    # what characters appear in the value (quotes, apostrophes, unicode,
    # etc). The previous approach -- repr() a Python list, then
    # string-replace single quotes with double quotes -- broke on any
    # string value containing an apostrophe (e.g. "it's a test"), turning
    # ['it\'s a test'] into the invalid JS ["it"s a test"] and crashing
    # the harness with a SyntaxError. json.dumps escapes correctly instead.
    harness_code = _JS_HARNESS_TEMPLATE.format(
        solution_path="./solution.js",
        input_json=json.dumps(list(assignments.values())),
        expected_json=json.dumps(expected),
    )
    harness_path = tmpdir / "harness.js"
    harness_path.write_text(harness_code)

    try:
        proc = subprocess.run(
            ["node", "--no-addons", str(harness_path)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            cwd=str(tmpdir),
        )
    except subprocess.TimeoutExpired:
        return {**example, "passed": False, "error": f"timed out after {TIMEOUT_SECONDS}s"}

    out = proc.stdout.strip()
    if out == "PASS":
        return {**example, "passed": True, "error": None}
    if out.startswith("FAIL|"):
        _, got, exp = out.split("|", 2)
        return {**example, "passed": False, "error": f"got {got}, expected {exp}"}
    if out.startswith("ERROR|"):
        return {**example, "passed": False, "error": out.split("|", 1)[1]}
    return {**example, "passed": False, "error": (proc.stderr or "unknown execution error")[:200]}


def verify_solution(code: str, language: str, problem_text: str) -> dict:
    """Runs `code` against examples extracted from `problem_text`.

    Returns:
      {
        "verified": bool,          # did we actually manage to run a check?
        "passed": bool | None,     # overall pass/fail; None if not verified
        "results": [ {input, output, passed, error}, ... ],
        "reason": str,             # populated when verified is False
      }
    """
    if language not in ("Python", "JavaScript"):
        return {"verified": False, "passed": None, "results": [],
                "reason": f"execution-based verification isn't supported for {language} yet"}

    if language == "JavaScript" and not shutil.which("node"):
        return {"verified": False, "passed": None, "results": [],
                "reason": "Node.js isn't available on this host, so JavaScript verification was skipped"}

    if not code or not code.strip():
        return {"verified": False, "passed": None, "results": [],
                "reason": "no code was extracted from the response to verify"}

    examples = extract_examples(problem_text)
    if not examples:
        return {"verified": False, "passed": None, "results": [],
                "reason": "no example input/output could be found in the problem text"}

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for ex in examples:
            if language == "Python":
                results.append(_run_python_example(code, ex, tmpdir))
            else:
                results.append(_run_js_example(code, ex, tmpdir))

    ran_at_least_one = any(r["passed"] is not None for r in results)
    if not ran_at_least_one:
        return {"verified": False, "passed": None, "results": results,
                "reason": "examples were found but couldn't be matched to the solution's parameters"}

    checked = [r for r in results if r["passed"] is not None]
    overall = all(r["passed"] for r in checked)
    return {"verified": True, "passed": overall, "results": results, "reason": ""}
