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


BUILDER_FILES = ("native_video_graphs.py", "native_image_graphs.py", "native_runners.py")


def _seed_assignments(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Assignments, not keyword arguments: `seed=seed,` inside a call is a use, not a decision.
        if re.match(r"^(seed|noise_seed)\s*=\s", stripped):
            out.append((number, stripped))
    return out


def test_every_builder_resolves_its_seed_through_the_one_rule():
    """The durable half. Twelve builders each wrote their own seed line and four of them were
    wrong; nothing in a green suite or a rendered frame would have shown it.

    A new builder writing ``int(req.get("seed") or 1)`` fails here rather than shipping a fifth
    meaning for zero.
    """
    offenders = []
    for name in BUILDER_FILES:
        for number, line in _seed_assignments(ROOT / "python" / name):
            if "resolve_seed(" not in line and "stated_seed(" not in line:
                offenders.append(f"{name}:{number}  {line}")
    assert not offenders, (
        "resolve seeds through comfy_graph_helpers.resolve_seed:\n  " + "\n  ".join(offenders)
    )


def test_no_builder_reaches_for_the_clock_to_invent_a_seed():
    for name in BUILDER_FILES:
        source = (ROOT / "python" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            text = ast.unparse(node)
            if "time.time" in text or "random" in text.lower():
                context = "\n".join(lines[max(0, node.lineno - 4):node.lineno])
                assert "seed" not in context.lower(), f"{name}:{node.lineno} {text}"


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


def test_the_four_original_shapes_are_gone():
    """Named literally, because each of these read as deliberate where it stood -- a clamp, a
    fallback, a randomiser -- and only looked wrong beside the other eleven builders."""
    for name in BUILDER_FILES:
        source = (ROOT / "python" / name).read_text(encoding="utf-8")
        assert 'req.get("seed") or req.get("noise_seed") or 1' not in source
        assert "seed = int(time.time() * 1000) % 2147483647" not in source
        assert "if seed <= 0:" not in source
        assert "if seed > 0:" not in source
