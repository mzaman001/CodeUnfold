"""Live guard against Groq silently retiring a configured model ID.

This exists because it just happened: GROQ_MAIN_MODEL and GROQ_FAST_MODEL
pointed at two models (llama-3.3-70b-versatile, llama-3.1-8b-instant) that
Groq had removed from its catalog. Nothing failed loudly -- every request
just 404'd on that leg and silently fell through to the Gemini chain,
moving 100% of real traffic onto Gemini's free-tier quota instead of
splitting it with Groq. No test caught it, because no test had ever asked
Groq whether the configured IDs still existed.

This test does exactly that -- but only when a real GROQ_API_KEY is
available. In CI and in a full `pytest` run, GROQ_API_KEY ends up set to a
fake placeholder (test_app_integration.py sets it at import time, and
python-dotenv's load_dotenv() doesn't override an already-set variable by
default), so this skips there rather than making a real network call with
a bogus key. Run this file directly --

    pytest tests/test_model_availability.py

-- to actually exercise it against the project's real .env key. Do that
periodically (a good habit: before assuming "the app still generates
lessons" after time away from the project) to catch the next deprecation
before it silently degrades every request again.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import pytest
from dotenv import load_dotenv

from ai_client import GROQ_MAIN_MODEL, GROQ_FAST_MODEL

load_dotenv()
_real_key = os.environ.get("GROQ_API_KEY")
_has_real_key = bool(_real_key) and _real_key != "fake-key-for-tests"


@pytest.mark.skipif(not _has_real_key, reason="requires a real GROQ_API_KEY to check live model availability")
def test_configured_groq_models_are_still_available():
    from groq import Groq

    client = Groq(api_key=_real_key)
    available = {m.id for m in client.models.list().data}

    assert GROQ_MAIN_MODEL in available, (
        f"GROQ_MAIN_MODEL={GROQ_MAIN_MODEL!r} is no longer on Groq's model list -- "
        "every request is silently 404ing on this leg and falling through to Gemini. "
        "Update ai_client.GROQ_MAIN_MODEL to a currently-available model."
    )
    assert GROQ_FAST_MODEL in available, (
        f"GROQ_FAST_MODEL={GROQ_FAST_MODEL!r} is no longer on Groq's model list -- "
        "update ai_client.GROQ_FAST_MODEL to a currently-available model."
    )
