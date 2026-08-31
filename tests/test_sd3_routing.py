"""SD3 must be recognised as SD3, and a flow-matching pipeline must get a flow-matching scheduler.

Both halves were found by putting a real SD3.5 checkpoint on the box
(`sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors`, the Comfy-Org repack) and asking the code
what it made of it. Both failed, and neither failed loudly.

1. The classifier answered ``stable_diffusion`` at **0.97 confidence from the metadata layer** --
   its highest-priority, highest-trust source. The checkpoint's real SAI modelspec string is
   ``"stable-diffusion-v3.5-medium"``, with a **v** before the number, so the literal
   ``"stable-diffusion-3"`` check missed it and the generic ``"stable-diffusion"`` branch below
   claimed it. Display and routing would have agreed with each other and both been wrong -- and
   ``detect_image_pipeline_type`` would have handed an SD3 checkpoint to ``StableDiffusionPipeline``.

2. ``apply_sampler_and_scheduler`` had no flow-matching entry at all. All twelve of its schedulers
   solve an epsilon/v-prediction diffusion ODE over a sigma schedule; SD3 and FLUX learn a velocity
   field. Swapping one in still renders, so the failure would have been a quietly degraded image.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_classification import _family_from_arch_string  # noqa: E402


# --- the arch string is parsed, not spelled out --------------------------------------------------


@pytest.mark.parametrize("arch,family", [
    # Recorded verbatim from the shipped checkpoint's __metadata__.
    ("stable-diffusion-v3.5-medium", "sd3"),
    # SD3.0's own spelling, and the spelling the old check expected.
    ("stable-diffusion-v3-medium", "sd3"),
    ("stable-diffusion-3-medium", "sd3"),
    ("sd3", "sd3"),
    # The neighbours that must not move.
    ("stable-diffusion-xl-v1-base", "sdxl"),
    ("stable-diffusion-v2-1", "sd2"),
    ("stable-diffusion-v1-5", "stable_diffusion"),
    ("flux-1-dev", "flux"),
])
def test_the_architecture_string_resolves_to_the_right_family(arch, family):
    assert _family_from_arch_string(arch) == family


def test_the_generic_branch_cannot_swallow_a_versioned_variant():
    """The shape, not the typo. ``stable-diffusion`` is a prefix of every specific spelling, so an
    unanticipated variant used to land silently on SD 1.5 -- the most confident possible wrong
    answer -- rather than on "I don't know". Parsing the digit fails safe: an unrecognised version
    yields None and the next classification layer gets its turn."""
    assert _family_from_arch_string("stable-diffusion-v9-experimental") is None
    # ...while a genuinely unversioned string is still the original family, not None.
    assert _family_from_arch_string("stable-diffusion") == "stable_diffusion"


def test_an_sdxl_string_is_not_read_as_version_one():
    """``stable-diffusion-xl-v1-base`` carries a v1, but the 1 belongs to the XL release, not to
    the SD generation. It is caught by the sdxl branch before the version parse is reached, and
    that ordering is load-bearing."""
    assert _family_from_arch_string("stable-diffusion-xl-v1-base") == "sdxl"
    assert _family_from_arch_string("stable-diffusion-xl-v1-base-anima") == "sdxl"


# --- flow matching -------------------------------------------------------------------------------


pytest.importorskip("diffusers", reason="the scheduler classes are the subject of these tests")


@pytest.fixture
def pipes():
    from diffusers import EulerDiscreteScheduler, FlowMatchEulerDiscreteScheduler

    class Pipe:
        def __init__(self, scheduler):
            self.scheduler = scheduler

    return Pipe(FlowMatchEulerDiscreteScheduler()), Pipe(EulerDiscreteScheduler())


def test_flow_matching_is_read_off_the_live_pipeline_not_a_family_table(pipes):
    """Asked of the scheduler diffusers itself chose when loading the checkpoint. A family table
    would be a second resolver to keep in step, and it would be wrong the first time a checkpoint
    routed somewhere its filename did not predict."""
    from image_runners import pipeline_is_flow_matching

    flow, epsilon = pipes
    assert pipeline_is_flow_matching(flow) is True
    assert pipeline_is_flow_matching(epsilon) is False
    assert pipeline_is_flow_matching(None) is False


@pytest.mark.parametrize("sampler,expected", [
    ("euler", "FlowMatchEulerDiscreteScheduler"),
    ("heun", "FlowMatchHeunDiscreteScheduler"),
    ("lcm", "FlowMatchLCMScheduler"),
])
def test_a_flow_matching_pipeline_gets_the_flow_matching_scheduler(pipes, sampler, expected):
    from image_runners import apply_sampler_and_scheduler

    flow, _ = pipes
    result = apply_sampler_and_scheduler(flow, {"sampler": sampler})
    assert result["applied"] is True
    assert type(flow.scheduler).__name__ == expected


def test_a_sampler_with_no_flow_matching_equivalent_is_refused_not_approximated(pipes):
    """There is no dpmpp_2m for a flow-matching model. Substituting the sigma-schedule version
    would still render, which is the whole problem -- so the pipeline keeps its own scheduler and
    the request is reported as unapplied, the same way an unmapped sampler already was."""
    from image_runners import apply_sampler_and_scheduler

    flow, _ = pipes
    before = type(flow.scheduler).__name__
    result = apply_sampler_and_scheduler(flow, {"sampler": "dpmpp_2m"})
    assert result["applied"] is False
    assert type(flow.scheduler).__name__ == before


def test_the_epsilon_path_is_untouched(pipes):
    """The change must not move any family that was already right."""
    from image_runners import apply_sampler_and_scheduler

    _, epsilon = pipes
    assert apply_sampler_and_scheduler(epsilon, {"sampler": "dpmpp_2m"})["applied"] is True
    assert type(epsilon.scheduler).__name__ == "DPMSolverMultistepScheduler"


def test_sigma_shaping_is_dropped_rather_than_passed_to_a_flow_matching_scheduler(pipes):
    """`karras` reshapes a sigma schedule, and a flow-matching scheduler has none. Passing it would
    be silently ignored, so the returned scheduler name reports what was actually used instead of
    what was asked for."""
    from image_runners import apply_sampler_and_scheduler

    flow, epsilon = pipes
    assert apply_sampler_and_scheduler(flow, {"sampler": "euler", "scheduler": "karras"})["scheduler"] is None
    assert apply_sampler_and_scheduler(epsilon, {"sampler": "euler", "scheduler": "karras"})["scheduler"] == "karras"
