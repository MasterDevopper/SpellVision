"""A request option where ZERO is a legitimate value.

`float(req.get(key) or default)` is the idiom this replaces, and it is wrong whenever 0 means
something: 0 is falsy, so an explicit zero is silently swapped for the default. This bit three
times in one branch -- an object_info budget, a Civitai variants vram_gb, and the class-index
builder, where the driver passed budget_sec=0 to mean "one slice" and got 120 seconds, so a probe
against an unreachable ComfyUI hung for two minutes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from worker_service_state import numeric_option  # noqa: E402


def test_an_explicit_zero_is_honoured():
    assert numeric_option({"budget_sec": 0}, "budget_sec", 120.0) == 0.0
    assert numeric_option({"budget_sec": 0.0}, "budget_sec", 120.0) == 0.0
    assert numeric_option({"limit": 0}, "limit", 20) == 0.0


def test_an_absent_key_takes_the_default():
    assert numeric_option({}, "budget_sec", 120.0) == 120.0


def test_none_takes_the_default():
    """Explicit null is "I have no opinion", which is what the default is for."""
    assert numeric_option({"budget_sec": None}, "budget_sec", 120.0) == 120.0


def test_an_unparseable_value_takes_the_default_rather_than_raising():
    assert numeric_option({"budget_sec": "soon"}, "budget_sec", 120.0) == 120.0
    assert numeric_option({"budget_sec": []}, "budget_sec", 120.0) == 120.0


def test_a_bool_is_not_silently_read_as_a_number():
    """True == 1 in Python, so a bool would otherwise become a one-second timeout."""
    assert numeric_option({"budget_sec": True}, "budget_sec", 120.0) == 120.0
    assert numeric_option({"budget_sec": False}, "budget_sec", 120.0) == 120.0


def test_a_numeric_string_is_accepted():
    assert numeric_option({"budget_sec": "45"}, "budget_sec", 120.0) == 45.0


def test_negative_values_pass_through_for_the_caller_to_validate():
    """This helper parses; it does not police ranges. A caller that cares clamps."""
    assert numeric_option({"budget_sec": -5}, "budget_sec", 120.0) == -5.0
