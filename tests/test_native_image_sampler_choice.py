"""The cockpit's sampler choice must reach a native image graph.

Every native image builder hardcoded its sampler, so ``req["sampler"]`` -- which the cockpit's
Advanced row sends, and which BOTH the diffusers path (``image_runners.apply_sampler_and_scheduler``)
and the video path (``native_video_graphs``) already honoured -- was silently dropped for the six
native image families.

Measured, not inferred: submitting Krea 2 with ``sampler="er_sde"`` produced a graph carrying
``sampler_name: "euler"`` and came back in 2.0s off ComfyUI's node cache, byte-identical to the
euler render. A visible, per-family-populated dropdown that did nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import native_image_graphs as nig  # noqa: E402

# Live KSampler choices, trimmed. The real object_info is 1360 classes; these tests only need the
# sampler/scheduler combos, in the legacy [[choices]] shape.
OBJECT_INFO = {
    "KSampler": {
        "input": {
            "required": {
                "sampler_name": [["euler", "er_sde", "res_multistep", "dpmpp_2m", "heun"]],
                "scheduler": [["simple", "normal", "karras", "beta"]],
            }
        }
    }
}


def test_a_requested_sampler_is_honoured():
    sampler, scheduler = nig._sampling_for("krea2", {"sampler": "er_sde"}, OBJECT_INFO, "euler", "simple")
    assert sampler == "er_sde"


def test_no_request_falls_back_to_the_family_default():
    sampler, scheduler = nig._sampling_for("krea2", {}, OBJECT_INFO, "euler", "simple")
    assert sampler == "er_sde"      # krea2's operating point pins it
    assert scheduler == "simple"


def test_a_sampler_outside_the_family_allowlist_is_refused_not_forwarded():
    """ComfyUI answers an unknown sampler with a 400. A request that reached the queue should not
    die there because a stale dropdown entry was passed straight through."""
    sampler, _ = nig._sampling_for("krea2", {"sampler": "heun"}, OBJECT_INFO, "euler", "simple")
    assert sampler != "heun"


def test_a_sampler_absent_from_the_live_list_is_refused():
    """The allow-list is intersected with what this ComfyUI build actually offers."""
    thin = {"KSampler": {"input": {"required": {
        "sampler_name": [["euler"]], "scheduler": [["simple"]]}}}}
    sampler, _ = nig._sampling_for("krea2", {"sampler": "er_sde"}, thin, "euler", "simple")
    assert sampler == "euler"


def test_the_scheduler_is_honoured_the_same_way():
    _, scheduler = nig._sampling_for("krea2", {"scheduler": "normal"}, OBJECT_INFO, "euler", "simple")
    assert scheduler == "normal"


@pytest.mark.parametrize("family", ["flux", "pixart", "lumina", "z_image", "anima", "krea2"])
def test_every_native_image_family_resolves_rather_than_hardcodes(family):
    """All six, so a new builder copied from an old one cannot reintroduce the hardcode."""
    result = nig._sampling_for(family, {}, OBJECT_INFO, "euler", "simple")
    assert result[0] and result[1]


def test_no_builder_still_writes_a_sampler_literal():
    """Structural: the defect was six copies of the same hardcode, and the fix is only durable if a
    seventh cannot be added quietly."""
    source = Path(nig.__file__).read_text(encoding="utf-8", errors="replace")
    for line in source.splitlines():
        if '"sampler_name"' in line and "sampler_name," not in line:
            assert "_sampling_for" in line or "_set_if_allowed" in line, (
                f"a hardcoded sampler is back: {line.strip()}"
            )
