import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_verifier import extract_examples, verify_solution, _parse_assignments, _to_python_literal


# ---------- extract_examples ----------

def test_extract_examples_single_line_format():
    text = "Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]"
    examples = extract_examples(text)
    assert len(examples) == 1
    assert examples[0]["input"] == "nums = [2,7,11,15], target = 9"
    assert examples[0]["output"] == "[0,1]"


def test_extract_examples_multiline_format():
    text = 'Example:\nInput: s = "()[]{}"\nOutput: true\n\nMore prose here.'
    examples = extract_examples(text)
    assert len(examples) == 1
    assert examples[0]["output"] == "true"


def test_extract_examples_none_found_returns_empty_list():
    assert extract_examples("just a plain description with no examples") == []


def test_extract_examples_caps_at_max():
    text = "\n\n".join(f"Input: x = {i} -> Output: {i}" for i in range(10))
    assert len(extract_examples(text)) <= 3


# ---------- literal parsing helpers ----------

def test_to_python_literal_handles_leetcode_booleans():
    assert _to_python_literal("true") is True
    assert _to_python_literal("false") is False


def test_to_python_literal_handles_lists():
    assert _to_python_literal("[0,1]") == [0, 1]


def test_parse_assignments_multiple_vars():
    result = _parse_assignments("nums = [2,7,11,15], target = 9")
    assert result == {"nums": [2, 7, 11, 15], "target": 9}


def test_parse_assignments_single_var():
    result = _parse_assignments('s = "()[]{}"')
    assert result == {"s": "()[]{}"}


# ---------- verify_solution: end-to-end execution ----------

TWO_SUM_PROBLEM = """Given an array of integers nums and an integer target, return indices
of the two numbers such that they add up to target.

Example: Input: nums = [2,7,11,15], target = 9 -> Output: [0,1]

class Solution:
    def twoSum(self, nums, target):"""

CORRECT_TWO_SUM = """class Solution:
    def twoSum(self, nums, target):
        seen = {}
        for i, n in enumerate(nums):
            if target - n in seen:
                return [seen[target - n], i]
            seen[n] = i
        return []
"""

WRONG_TWO_SUM = """class Solution:
    def twoSum(self, nums, target):
        return [99, 99]
"""


def test_verify_solution_passes_correct_python_code():
    result = verify_solution(CORRECT_TWO_SUM, "Python", TWO_SUM_PROBLEM)
    assert result["verified"] is True
    assert result["passed"] is True


def test_verify_solution_flags_wrong_python_code():
    result = verify_solution(WRONG_TWO_SUM, "Python", TWO_SUM_PROBLEM)
    assert result["verified"] is True
    assert result["passed"] is False
    assert result["results"][0]["error"] is not None


def test_verify_solution_no_examples_is_not_verified_not_silently_passed():
    result = verify_solution(CORRECT_TWO_SUM, "Python", "no example here at all")
    assert result["verified"] is False
    assert result["passed"] is None
    assert result["reason"]


def test_verify_solution_empty_code_is_not_verified():
    result = verify_solution("", "Python", TWO_SUM_PROBLEM)
    assert result["verified"] is False
    assert result["passed"] is None


def test_verify_solution_unsupported_language_is_not_verified():
    result = verify_solution(CORRECT_TWO_SUM, "Rust", TWO_SUM_PROBLEM)
    assert result["verified"] is False
    assert "Rust" in result["reason"]


def test_verify_solution_infinite_loop_times_out_rather_than_hangs():
    hanging_code = """class Solution:
    def twoSum(self, nums, target):
        while True:
            pass
"""
    result = verify_solution(hanging_code, "Python", TWO_SUM_PROBLEM)
    assert result["verified"] is True
    assert result["passed"] is False


def test_verify_solution_survives_missing_resource_module(monkeypatch, tmp_path):
    """Regression test: the harness used to do a bare `import resource` at
    module scope, which raises ModuleNotFoundError on Windows (no such
    module there) and crashes the subprocess for every single Python
    verification -- silently turning correct code into a reported
    failure. `resource` is now imported inside its own try/except.

    This simulates "no resource module" by shadowing it with a stub
    package on PYTHONPATH ahead of the real one, since subprocess.run
    inherits the parent's environment (including PYTHONPATH).
    """
    fake_module_dir = tmp_path / "fake_no_resource"
    fake_module_dir.mkdir()
    (fake_module_dir / "resource.py").write_text(
        "raise ImportError(\"No module named 'resource' (simulated Windows)\")"
    )
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", f"{fake_module_dir}{os.pathsep}{existing}" if existing else str(fake_module_dir)
    )

    result = verify_solution(CORRECT_TWO_SUM, "Python", TWO_SUM_PROBLEM)
    assert result["verified"] is True
    assert result["passed"] is True
