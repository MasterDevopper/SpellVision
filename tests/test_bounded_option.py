"""Zero is a value the user can state, and 80 sites turned it into a default.

``float(req.get(key) or default)`` is wrong wherever 0 means something, because 0 is falsy. Measured
across this repo: **80 sites, 45 of them in one file**. Two of them did worse than lose the value --
they INVERTED it. A video denoise of 0.0 means "return the input unchanged"; ``or 1.0`` turned that
into "ignore the input entirely", the opposite request.

The half of this that is easy to get wrong in the other direction: not every zero is sayable. A
stated ``steps=0`` is a mistake, and the old code's answer -- quietly render 28 steps -- is how the
mistake stayed invisible. So the bounds table answers "is zero sayable here" once per field, and an
out-of-range value is clamped **and reported** rather than replaced in silence.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from request_payload import (  # noqa: E402
    FIELD_ALIASES,
    FIELD_BOUNDS,
    _bounds_for,
    bounded_option,
    numeric_option,
)


# --- the fields where zero is a request ------------------------------------------------------------

ZERO_IS_SAYABLE = [
    ("cfg", 7.0, "unconditional sampling, and the cockpit's spin box offers it"),
    ("denoise", 1.0, "return the input unchanged"),
    ("limit", 20, "return no rows"),
    ("timeout_sec", 30.0, "do not wait"),
    ("shift", 5.0, "no shift"),
    ("lora_scale", 1.0, "the LoRA off, without unloading it"),
]


@pytest.mark.parametrize("field,default,meaning", ZERO_IS_SAYABLE)
def test_a_stated_zero_is_honoured(field: str, default, meaning: str) -> None:
    assert bounded_option({field: 0}, field, default) == 0, meaning
    assert bounded_option({field: 0.0}, field, default) == 0, meaning
    assert bounded_option({field: "0"}, field, default) == 0, meaning


@pytest.mark.parametrize("field,default,meaning", ZERO_IS_SAYABLE)
def test_the_default_still_applies_when_nothing_is_stated(field: str, default, meaning: str) -> None:
    assert bounded_option({}, field, default) == default
    assert bounded_option({field: None}, field, default) == default
    assert bounded_option({field: ""}, field, default) == default
    assert bounded_option({field: "auto"}, field, default) == default


def test_a_denoise_of_zero_is_not_inverted() -> None:
    """The sharpest instance: two video builders read `req.get("denoise") or ... or 1.0`.

    0.0 and 1.0 are not "a value and its default", they are opposite instructions.
    """
    assert bounded_option({"denoise": 0.0}, "denoise", 1.0) == 0.0
    assert bounded_option({"denoise_strength": 0.0}, "denoise", 1.0) == 0.0


# --- the fields where zero is a mistake, and saying so is the point --------------------------------

# batch_size is deliberately absent: its default IS 1, which is also its minimum, so it cannot
# distinguish "clamped" from "replaced by the default" and would assert nothing.
@pytest.mark.parametrize("field,default", [("steps", 28), ("fps", 16), ("width", 832),
                                           ("height", 480), ("frames", 81)])
def test_a_zero_that_cannot_be_honoured_is_clamped_not_replaced(field: str, default,
                                                                caplog) -> None:
    with caplog.at_level(logging.WARNING):
        value = bounded_option({field: 0}, field, default)
    assert value == 1, "clamped to the minimum, not swapped for the default"
    assert value != default, (
        "substituting the default is what made a stated 0 invisible: the render came back looking "
        "normal and nothing said the number had been ignored"
    )
    assert any(field in record.getMessage() for record in caplog.records)


def test_a_value_above_the_maximum_is_clamped(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert bounded_option({"denoise": 4.0}, "denoise", 1.0) == 1.0
    assert caplog.records


def test_a_default_is_never_clamped_or_warned_about(caplog) -> None:
    """Only a STATED value is held to the range. A default outside its own bounds is a bug worth
    seeing, not something to quietly correct."""
    with caplog.at_level(logging.WARNING):
        assert bounded_option({}, "steps", 0) == 0
    assert not caplog.records


# --- resolution order ------------------------------------------------------------------------------

def test_the_request_outranks_the_operating_point_which_outranks_the_literal() -> None:
    table = {"steps": 12}
    assert bounded_option({"steps": 4}, "steps", 30, table=table) == 4
    assert bounded_option({}, "steps", 30, table=table) == 12
    assert bounded_option({}, "steps", 30, table={}) == 30


def test_a_stated_zero_in_the_request_still_beats_the_operating_point() -> None:
    """The whole failure mode, one level down: a falsy request value fell through to the table."""
    assert bounded_option({"cfg": 0.0}, "cfg", 7.0, table={"cfg": 3.5}) == 0.0


def test_every_alias_of_a_field_resolves_to_it() -> None:
    """The alias lists had DRIFTED between call sites: cfg was read as
    ("cfg", "guidance_scale") in the WAN core builder, ("cfg", "cfg_scale") in the wrapper, and
    plain ("cfg",) elsewhere -- so which spelling worked depended on which family you rendered."""
    # 1 rather than a larger number: it is inside every field's range, including denoise, whose
    # maximum is 1.0. A test value that trips a bound would be measuring the clamp, not the alias.
    for field, names in FIELD_ALIASES.items():
        for name in names:
            assert bounded_option({name: 1}, field, 99) == 1, f"{field} did not accept {name}"


def test_the_first_alias_wins_when_several_are_present() -> None:
    assert bounded_option({"cfg": 1.0, "guidance_scale": 9.0}, "cfg", 7.0) == 1.0


# --- types and shapes ------------------------------------------------------------------------------

def test_the_return_type_follows_the_default() -> None:
    assert isinstance(bounded_option({}, "steps", 30), int)
    assert isinstance(bounded_option({"steps": 12.0}, "steps", 30), int)
    assert isinstance(bounded_option({}, "cfg", 7.0), float)


def test_a_bool_is_not_a_number() -> None:
    """True would arrive as 1 and become a real value."""
    assert bounded_option({"steps": True}, "steps", 30) == 30
    assert bounded_option({"steps": False}, "steps", 30) == 30


def test_unparseable_input_falls_back_rather_than_raising() -> None:
    assert bounded_option({"steps": "many"}, "steps", 30) == 30
    assert bounded_option({"steps": object()}, "steps", 30) == 30
    assert bounded_option(None, "steps", 30) == 30


def test_bounds_are_inherited_by_suffix() -> None:
    """So startup_timeout_sec gets timeout_sec's "zero means do not wait" without being listed.

    Enumerating every spelling is the habit this pass is about: the list is right on the day it is
    written and one rename behind ever after.
    """
    assert _bounds_for("startup_timeout_sec") == FIELD_BOUNDS["timeout_sec"]
    assert _bounds_for("version_check_timeout_sec") == FIELD_BOUNDS["timeout_sec"]
    assert _bounds_for("comfy_timeout_sec") == FIELD_BOUNDS["timeout_sec"]
    assert bounded_option({"startup_timeout_sec": 0}, "startup_timeout_sec", 60.0) == 0.0
    assert _bounds_for("something_nobody_declared") == (None, None)


def test_numeric_option_still_means_what_its_three_callers_read_it_as() -> None:
    """It delegates now. Two implementations of "honour a stated zero" is how this started."""
    assert numeric_option({"budget_sec": 0}, "budget_sec", 120.0) == 0.0
    assert numeric_option({}, "budget_sec", 120.0) == 120.0
    assert numeric_option({"budget_sec": True}, "budget_sec", 120.0) == 120.0
    # No aliasing: numeric_option's callers pass an exact key and expect exactly that key.
    assert numeric_option({"guidance_scale": 3.0}, "cfg", 7.0) == 7.0


def test_every_field_with_bounds_has_aliases_and_the_reverse() -> None:
    """The two tables describe the same set of fields; a field in one and not the other is a
    half-declared field, which is how `dpmpp_2m_sde` ended up offered and unmapped."""
    assert set(FIELD_BOUNDS) == set(FIELD_ALIASES)
    for field, names in FIELD_ALIASES.items():
        assert names[0] == field, f"{field}'s own name must be its first alias"
