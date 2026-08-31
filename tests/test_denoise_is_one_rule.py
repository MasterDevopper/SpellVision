"""A stated denoise of 0.0 means "return the input unchanged", and eight sites disagreed.

Phase 2b built ``bounded_option`` for exactly this and drove the ``zero-is-sayable`` sweep to zero.
It stayed at zero through Phases 3 and 4 while the defect it was written for sat **eight times in
two files**, because the rule matched one SHAPE of the mistake:

    six image builders   ``if not (0.0 < denoise <= 1.0): denoise = 0.6``
                         a stated 0.0 silently became 0.6, and an absent value was indistinguishable
                         from a stated zero -- both took the same branch
    the inpaint graph    ``if not (0.0 < denoise_f <= 1.0): raise``
                         at least it said so, but it still refused a value the spin box offers
    the inpaint caller   ``float(req.get("denoise") if ... is not None else 0.7)``
                         a ninth default, reading only ``denoise``

None of those is ``x or 0.6``, so R2 -- which checked ``BoolOp`` -- reported clean. Flux, a hundred
lines above the six, has always used the inclusive form.

And the resolver could not have fixed them anyway: ``strength`` is what the cockpit actually sends
for i2i (``GenerationRequestBuilder`` writes both ``denoise_strength`` and ``strength``) and it was
missing from the alias table, so a stated 0.35 resolved to the default. The six builders read
``strength`` directly and the inpaint caller read ``denoise`` -- the two halves of one control,
split across one file.

The rule now reads which fields allow zero from ``FIELD_BOUNDS``, the same table ``bounded_option``
resolves against, rather than from a second list that could disagree with it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from request_payload import FIELD_ALIASES, FIELD_BOUNDS, bounded_option  # noqa: E402


# --- the key the cockpit sends ---------------------------------------------------------------------

def test_strength_resolves_as_denoise() -> None:
    """The cockpit sends `strength`; the alias table did not know the name."""
    assert "strength" in FIELD_ALIASES["denoise"]
    assert bounded_option({"strength": 0.35}, "denoise", 0.6) == 0.35


@pytest.mark.parametrize("key", ["denoise", "denoise_strength", "strength"])
def test_a_stated_zero_survives_under_every_spelling(key: str) -> None:
    assert bounded_option({key: 0.0}, "denoise", 0.6) == 0.0


def test_an_absent_value_is_distinguishable_from_a_stated_zero() -> None:
    """The six builders collapsed these into one branch: absent produced 0.0, which was then
    rejected and became 0.6 -- so did a stated 0.0. Neither the user nor the log could tell."""
    assert bounded_option({}, "denoise", 0.6) == 0.6
    assert bounded_option({"strength": 0.0}, "denoise", 0.6) == 0.0


def test_the_explicit_key_outranks_the_alias() -> None:
    assert bounded_option({"denoise": 0.2, "strength": 0.9}, "denoise", 0.6) == 0.2


def test_the_lora_strength_does_not_collide() -> None:
    """The LoRA weight is also called `strength`, which is why aliasing it needed checking: it lives
    inside a stack ITEM, never at the top level of a request."""
    stack = {"lora_stack": [{"name": "x", "strength": 0.8}]}
    assert bounded_option(stack, "denoise", 0.6) == 0.6


# --- zero is legal here and not everywhere -------------------------------------------------------

def test_the_bounds_table_is_the_one_answer() -> None:
    """Which fields allow zero is decided once, in the table the resolver reads. The sweep reads the
    same table -- a second list would be one more copy of the answer to keep in step."""
    assert FIELD_BOUNDS["denoise"][0] == 0
    assert FIELD_BOUNDS["cfg"][0] == 0
    assert FIELD_BOUNDS["steps"][0] == 1, "steps 0 is not a render, and the guard should say so"
    assert FIELD_BOUNDS["width"][0] == 1


def test_a_stated_zero_is_clamped_for_a_field_that_forbids_it() -> None:
    assert bounded_option({"steps": 0}, "steps", 20) == 1


def test_the_upper_bound_still_holds() -> None:
    assert bounded_option({"strength": 5.0}, "denoise", 0.6) == 1.0


# --- the builders honour it ------------------------------------------------------------------------

def _flux_denoise(strength):
    from native_image_graphs import _flux_denoise_from_request

    return _flux_denoise_from_request({"strength": strength})


def test_flux_keeps_its_deliberate_remap() -> None:
    """Flux is NOT normalised to the others. Its [0,1] -> [0.55, 1.0] remap was calibrated against
    measured input-tone dominance, and flattening it would be applying a rule at the wrong level --
    the mistake this audit keeps finding, committed in the name of fixing it."""
    assert _flux_denoise(0.0) == pytest.approx(0.55)
    assert _flux_denoise(1.0) == pytest.approx(1.0)


def test_flux_already_honoured_zero_and_was_the_evidence() -> None:
    """`0.0 <= s <= 1.0`, inclusive, a hundred lines above six exclusive copies. A rule applied
    correctly once in the same file is this audit's whole subject."""
    assert _flux_denoise(0.0) != _flux_denoise(0.6)


def test_the_inpaint_graph_accepts_zero_and_still_refuses_nonsense() -> None:
    """It used to raise on a stated 0.0. Refusing loudly beat substituting silently, but it still
    rejected a value the spin box offers and KSampler accepts."""
    from krea2_regional_inpaint import build_krea2_regional_inpaint_graph

    graph = build_krea2_regional_inpaint_graph(
        unet_name="k.safetensors", clip_name="c.safetensors", vae_name="v.safetensors",
        lock_image="lock.png", mask_image="mask.png", edit_prompt="x", identity_prompt="y",
        negative_prompt="", seed=1, steps=8, cfg=1.0, grow_mask_by=4, feather=4,
        denoise=0.0, latent_mode="inpaint", filename_prefix="p",
    )
    assert graph

    with pytest.raises(ValueError):
        build_krea2_regional_inpaint_graph(
            unet_name="k.safetensors", clip_name="c.safetensors", vae_name="v.safetensors",
            lock_image="lock.png", mask_image="mask.png", edit_prompt="x", identity_prompt="y",
            negative_prompt="", seed=1, steps=8, cfg=1.0, grow_mask_by=4, feather=4,
            denoise=1.5, latent_mode="inpaint", filename_prefix="p",
        )


# --- the widened rule -------------------------------------------------------------------------------

def test_the_rule_now_sees_the_guard_form() -> None:
    """The point of this file. R2 was written for this defect, drove itself to zero, and stayed
    there for two phases while eight copies survived in a shape it did not match."""
    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import rules

    rule = [r for r in rules.ALL_RULES if r.name == "zero-is-sayable"][0]
    assert not rule.run(), [str(v) for v in rule.run()]

    guarded = "\n".join([
        "def f(req):",
        "    denoise = req.get('strength')",
        "    if not (0.0 < denoise <= 1.0):",
        "        denoise = 0.6",
        "    return denoise",
    ])
    import ast

    found = rules._check_exclusive_zero_guard(Path("python/fake.py"), ast.parse(guarded))
    assert found, "the widened rule does not catch the form it was widened for"


def test_the_rule_does_not_flag_a_field_whose_minimum_is_one() -> None:
    """`if steps < 1` is correct, and a rule that could not tell the difference would push someone
    into accepting a zero-step render to silence it."""
    import ast

    from sweeps import rules

    ok = "\n".join([
        "def f(req):",
        "    steps = req.get('steps')",
        "    if not (0 < steps <= 100):",
        "        steps = 20",
        "    return steps",
    ])
    assert not rules._check_exclusive_zero_guard(Path("python/fake.py"), ast.parse(ok))
