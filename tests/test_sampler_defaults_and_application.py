"""The user states a sampler and a scheduler. Both have to survive the trip.

Three defects, all measured on this box against LuxuriousPrisma_v30 (1024x1024, 30 steps, cfg 7,
seed 20260830) through the worker's own ``apply_sampler_and_scheduler``:

1. **A default nobody chose.** ``family_sampling_choices`` fell through to ``sorted(samplers)[0]``
   for a family that declared none. sdxl -- and pony, illustrious, stable_diffusion and sd, which
   alias to it -- has no operating-point row, so ddim + karras was the shipped default on 112
   checkpoints because "ddim" sorts first.

2. **A scheduler half that never applied.** DDIMScheduler does not accept ``use_karras_sigmas``, so
   ``from_config`` raised TypeError, the retry dropped the kwarg, and nothing said so. The shipped
   default was "ddim + karras" rendering ddim with no karras.

3. **A sticky flag.** The rebuild read ``pipe.scheduler.config`` -- the PREVIOUS render's -- on a
   pipeline the worker keeps warm. Request karras then request normal, and karras stayed:
   MAD 0.00 against the karras render, MAD 41.61 against the same request on a clean load.

Hermetic: the scheduler classes are real diffusers classes, but nothing here loads a checkpoint.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import image_runners  # noqa: E402
from family_operating_points import (  # noqa: E402
    FAMILY_SAMPLER_ALLOWLISTS,
    _FAMILY_SAMPLING_ALIASES,
    family_sampling_choices,
)


# --- 1. no family ships a default chosen by sort order ---------------------------------------------

ALL_FAMILY_KEYS = sorted(set(FAMILY_SAMPLER_ALLOWLISTS) | set(_FAMILY_SAMPLING_ALIASES))


@pytest.mark.parametrize("family", ALL_FAMILY_KEYS)
def test_no_family_defaults_to_whatever_sorts_first(family: str) -> None:
    """Every key, including the aliases -- pony and illustrious inherited sdxl's accident."""
    choices = family_sampling_choices(family)
    assert choices["default_sampler_source"] != "alphabetical", (
        f"{family} would render with {choices['default_sampler']!r} because it sorts first. "
        "Declare default_sampler, or pin it on the family's operating point."
    )
    assert choices["default_scheduler_source"] != "alphabetical", (
        f"{family} would render with the {choices['default_scheduler']!r} scheduler by sort order."
    )


def test_a_family_with_no_declared_default_is_refused_at_import() -> None:
    """The refusal is the point: a new allowlist entry cannot skip the decision."""
    from family_operating_points import _assert_every_family_declares_a_default

    FAMILY_SAMPLER_ALLOWLISTS["_test_undeclared"] = {
        "samplers": ("zebra", "aardvark"),
        "schedulers": ("normal",),
    }
    try:
        with pytest.raises(RuntimeError, match="sort order"):
            _assert_every_family_declares_a_default()
    finally:
        FAMILY_SAMPLER_ALLOWLISTS.pop("_test_undeclared", None)


def test_sdxl_defaults_to_the_measured_pair() -> None:
    for alias in ("sdxl", "pony", "illustrious", "stable_diffusion", "sd"):
        choices = family_sampling_choices(alias)
        assert (choices["default_sampler"], choices["default_scheduler"]) == ("dpmpp_2m", "karras"), alias


def test_hunyuan_defaults_to_what_its_graph_actually_builds() -> None:
    """euler/simple is what the shipped Hunyuan graph patches, and what the proven render used.

    The alphabetical fallback advertised dpmpp_2m/normal -- a default the graph could not produce,
    since it ignored the request entirely until the sampler was wired through.
    """
    choices = family_sampling_choices("hunyuan_video")
    assert (choices["default_sampler"], choices["default_scheduler"]) == ("euler", "simple")


# --- 2. an offered sampler has to be able to apply --------------------------------------------------

def _pipe(config: dict | None = None):
    return SimpleNamespace(scheduler=SimpleNamespace(config=dict(config or {})))


@pytest.mark.parametrize("family", sorted(FAMILY_SAMPLER_ALLOWLISTS))
def test_every_offered_sampler_has_a_mapping_or_is_a_comfy_only_family(family: str) -> None:
    """A sampler offered on the DIFFUSERS path must map to a diffusers scheduler.

    dpmpp_2m_sde sat in the sdxl allowlist with no mapping: measured applied=False, and the render
    came back byte-identical to plain euler. Only the families that reach the diffusers path are
    asked this -- a ComfyUI-native family's sampler names are ComfyUI's, not diffusers'.
    """
    if family not in {"sdxl"}:
        pytest.skip(f"{family} renders through ComfyUI; its sampler names are ComfyUI's")
    for sampler in FAMILY_SAMPLER_ALLOWLISTS[family]["samplers"]:
        assert image_runners._load_scheduler_class(sampler) is not None, (
            f"{family} offers {sampler!r} and the diffusers path cannot build it, so choosing it "
            "renders whatever scheduler happened to be loaded"
        )


def test_dpmpp_2m_sde_builds_the_sde_variant() -> None:
    pipe = _pipe()
    stats = image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m_sde"})
    assert stats["applied"]
    assert type(pipe.scheduler).__name__ == "DPMSolverMultistepScheduler"
    assert pipe.scheduler.config["algorithm_type"] == "sde-dpmsolver++", (
        "without the algorithm_type this is plain dpmpp_2m under a different name"
    )


def test_a_scheduler_the_sampler_cannot_take_is_reported_not_swallowed() -> None:
    """"ddim + karras" was the shipped default and the karras half never applied."""
    pipe = _pipe()
    stats = image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "ddim", "scheduler": "karras"})
    assert stats["applied"] is True, "the sampler itself applies"
    assert stats["scheduler_requested"] == "karras"
    assert stats["scheduler_applied"] is False
    assert stats["scheduler"] is None
    assert not pipe.scheduler.config.get("use_karras_sigmas", False)


# --- 3. a scheduler choice must not outlive its request ---------------------------------------------

def test_a_scheduler_flag_does_not_survive_into_the_next_render() -> None:
    """The worker keeps one pipeline warm across renders; the config must not accumulate.

    Measured before the fix: request karras, then normal, and the second image was byte-identical
    to the first (MAD 0.00) while differing from the same request on a clean load by MAD 41.61.
    """
    pipe = _pipe()
    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m", "scheduler": "karras"})
    assert pipe.scheduler.config.get("use_karras_sigmas") is True

    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m", "scheduler": "normal"})
    assert not pipe.scheduler.config.get("use_karras_sigmas", False), (
        "asking for normal after karras rendered karras until the model was reloaded"
    )


@pytest.mark.parametrize("first,second", [
    ("karras", "exponential"),
    ("exponential", "beta"),
    ("beta", "karras"),
    ("karras", "normal"),
])
def test_no_sigma_shaping_flag_leaks_between_requests(first: str, second: str) -> None:
    pipe = _pipe()
    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m", "scheduler": first})
    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m", "scheduler": second})
    expected = image_runners._SIGMA_SHAPE_FLAGS.get(second)
    for name, flag in image_runners._SIGMA_SHAPE_FLAGS.items():
        assert bool(pipe.scheduler.config.get(flag, False)) is (flag == expected), (
            f"after {first} then {second}, {flag} is wrong"
        )


def test_a_sampler_switch_does_not_carry_the_previous_samplers_extra_config() -> None:
    """dpmpp_2m_sde sets algorithm_type; plain dpmpp_2m must not inherit it."""
    pipe = _pipe()
    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m_sde"})
    assert pipe.scheduler.config["algorithm_type"] == "sde-dpmsolver++"

    image_runners.apply_sampler_and_scheduler(pipe, {"sampler": "dpmpp_2m"})
    assert pipe.scheduler.config["algorithm_type"] != "sde-dpmsolver++", (
        "the SDE variant leaked into the plain multistep request"
    )
