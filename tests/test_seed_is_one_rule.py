"""Zero is a seed, and every family has to agree that it is.

Measured across the twelve graph builders before this, seed ``0`` meant four different things:

* nine builders (all six image families, Hunyuan t2v and i2v, Mochi) rendered seed 0;
* the two Wan builders rendered seed **1** -- ``int(req.get("seed") or ... or 1)`` followed by
  ``if seed <= 0: seed = 1``;
* the two split builders rendered ``int(time.time() * 1000) % 2147483647``, so an explicitly
  requested seed became a clock reading and the render could not be reproduced from its own
  metadata;
* the diffusers video path attached no generator at all, i.e. rendered nondeterministically.

The same request therefore reproduced on Flux, quietly changed on Wan, and could not be reproduced
at all on a split route. That is the "the value you set is not the value used" shape -- the same one
as the sampler dropdown that did nothing, and it is invisible for exactly the same reason: every
path returns a picture.

Zero is legal (``KSampler``'s ``seed`` has ``min: 0``) and people type it deliberately.
Randomisation belongs to the client, which generates a random integer when Random is ticked; a
builder inventing its own is both wrong and redundant.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

# Tree-wide property, not a call-site check: every seed assignment goes through resolve_seed / stated_seed.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from comfy_graph_helpers import resolve_seed, stated_seed  # noqa: E402


# --- the rule ------------------------------------------------------------------------------------


@pytest.mark.parametrize("request_payload,expected", [
    ({"seed": 0}, 0),
    ({"seed": "0"}, 0),
    ({"seed": 42}, 42),
    ({"seed": "42"}, 42),
    ({"noise_seed": 7}, 7),
    ({"seed": None, "noise_seed": 9}, 9),
])
def test_a_stated_seed_is_the_seed_used(request_payload, expected):
    assert resolve_seed(request_payload) == expected


@pytest.mark.parametrize("request_payload", [{}, {"seed": ""}, {"seed": "   "}, {"seed": "None"},
                                             {"seed": None}, {"seed": "not a number"}])
def test_an_absent_or_unusable_seed_falls_to_zero(request_payload):
    """Deterministic, and the value every family already used for an absent seed."""
    assert resolve_seed(request_payload) == 0


def test_a_negative_seed_clamps_rather_than_meaning_randomise():
    """ComfyUI would reject it, and inventing a value is the thing this exists to stop."""
    assert resolve_seed({"seed": -5}) == 0


def test_seed_is_never_derived_from_the_clock():
    """The split builders did exactly that, which made those renders unreproducible from their own
    metadata -- the seed recorded was not the seed that could be replayed."""
    first = resolve_seed({"seed": 0})
    second = resolve_seed({"seed": 0})
    assert first == second == 0


# --- the ratchet ---------------------------------------------------------------------------------


# The tree-wide half of this rule now lives in tests/test_sweeps.py, which sweeps all 92 modules.
#
# It used to live here, scoped to a three-file BUILDER_FILES tuple -- and it was green while three
# modules outside that tuple rendered seed 0 as 7 (clothes_only), as 4419 (look_completion) and as a
# prompt hash (ltx_smoke_test_route, whose _safe_int returns its fallback for anything <= 0). A
# ratchet scoped to where its defect was found is a memo, not a rule; see sweeps/sources.py.
#
# What stays here is what the sweep cannot express: the BEHAVIOUR of the resolver itself, and the
# original shapes named literally, because each read as deliberate where it stood.

from sweeps import sources  # noqa: E402


def _python_sources():
    return sources.python_sources()


def test_no_builder_reaches_for_the_clock_to_invent_a_seed():
    """The split builders derived a seed from time.time(), which made those renders unreproducible
    from their own metadata -- the seed recorded was not a seed that could be replayed."""
    for path in _python_sources():
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            text = ast.unparse(node)
            if "time.time" in text or "random" in text.lower():
                start = max(0, node.lineno - 4)
                context = chr(10).join(lines[start:node.lineno])
                assert "seed" not in context.lower(), (
                    f"{sources.relative(path)}:{node.lineno} {text}"
                )


def _code_only(source: str) -> str:
    """The source with every string literal blanked out.

    A plain text scan for an antipattern matches the DOCUMENTATION of that antipattern -- and this
    repo documents them thoroughly. `resolve_seed`'s own docstring quotes `if seed <= 0: seed = 1`
    to explain what it replaced, and a naive scan reports the fix as the bug. The same shape once
    made the endpoint ratchet fail on the guard message that names the env var it forbids reading.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.end_lineno:
            for index in range(node.lineno - 1, min(node.end_lineno, len(lines))):
                lines[index] = ""
    return chr(10).join(lines)


def test_the_original_shapes_are_gone():
    """Named literally, because each of these read as deliberate where it stood -- a clamp, a
    fallback, a randomiser -- and only looked wrong beside the other eleven builders."""
    for path in _python_sources():
        source = _code_only(path.read_text(encoding="utf-8", errors="replace"))
        rel = sources.relative(path)
        assert 'req.get("seed") or req.get("noise_seed") or 1' not in source, rel
        assert "seed = int(time.time() * 1000) % 2147483647" not in source, rel
        # The clamps that moved a legal value. 0 is a seed; these turned it into 1, or into
        # "no generator at all" on the diffusers video path.
        assert "if seed <= 0:" not in source, rel
        assert "if seed > 0:" not in source, rel


def test_saying_nothing_stays_distinguishable_from_saying_zero():
    """The LTX templates carry two deliberately different blueprint seeds (43 base, 42 refine) so
    the refine noise is not correlated with the base noise. A silent request must leave them alone,
    which "absent means 0" cannot express -- so the distinction lives in stated_seed rather than in
    a second seed rule."""
    assert stated_seed({}) is None
    assert stated_seed({"seed": ""}) is None
    assert stated_seed({"seed": 0}) == 0
    assert stated_seed({"seed": 5}) == 5
    assert stated_seed({"seed": -1}) == 0


