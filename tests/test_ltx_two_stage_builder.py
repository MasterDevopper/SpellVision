"""Graph-structure gate for the LTX-2.3 DISTILLED TWO-STAGE route (the default LTX route).

Builds the prompt from a realistic cockpit payload and asserts the distilled invariants without a
render. Every one of these locked in a live defect:

* The cockpit ALWAYS sends ``cfg`` (7.0 default, 3.5 once the LTX family preset fires -- and that
  preset is tuned for the SINGLE-STAGE full model). The builder used to patch both CFGGuiders from
  it, so the distilled graph ran at 3.5-7.0 instead of its blueprint 1.
* The cockpit ALWAYS sends ``lora``/``lora_scale`` (weight defaults to 1.0 even with nothing
  selected). Node 4922 IS the distilled adapter, so those keys used to (a) replace the distilled
  LoRA with the user's -- leaving 8-step distilled sigmas driving a non-distilled model -- and
  (b) run it at 1.0 instead of the blueprint 0.5.
* Both RandomNoise nodes were patched with the same seed; the blueprint uses 43/42 deliberately.

Stage identity here is by DATAFLOW, not node-id order: 4829 (guider 4828, noise 4832, sampler 4831,
sigmas 4984) is BASE; 4971 (guider 4964, noise 4967, sampler 4976, sigmas 4985) is REFINE.

A green graph proves STRUCTURE only -- a coherent render stays the real acceptance.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import native_video_graphs as nvg  # noqa: E402


DISTILLED_MARKER = "distilled"
USER_LORA = "chel_ltx23_lora-step00009000.comfy.safetensors"


def _build(**overrides):
    """A payload shaped like what GenerationRequestBuilder actually emits for a T2V job."""
    req = {
        "prompt": "a lantern swaying on a porch",
        "negative_prompt": "blurry",
        "width": 768,
        "height": 512,
        "frames": 97,
        "fps": 24.0,
        "seed": 1234,
        # The cockpit sends all four of these unconditionally.
        "cfg": 7.0,
        "cfg_scale": 7.0,
        "lora": "",
        "lora_scale": 1.0,
    }
    req.update(overrides)
    built = nvg._build_native_ltx_two_stage_prompt(
        req, {}, command="generate_video", family="ltx", job_id="pytest-ltx"
    )
    graph = built.get("prompt", built) if isinstance(built, dict) else built
    return graph if "4922" in graph else built["prompt"]


def _dangling(graph):
    return [
        (node_id, key, value)
        for node_id, node in graph.items()
        for key, value in (node.get("inputs") or {}).items()
        if isinstance(value, list) and len(value) == 2 and str(value[0]) not in graph
    ]


def test_distilled_guiders_ignore_the_cockpit_cfg():
    graph = _build(cfg=7.0, cfg_scale=7.0)
    assert graph["4964"]["inputs"]["cfg"] == 1
    assert graph["4828"]["inputs"]["cfg"] == 1


def test_explicit_distilled_cfg_still_overrides():
    graph = _build(ltx_distilled_cfg=1.2)
    assert graph["4964"]["inputs"]["cfg"] == 1.2
    assert graph["4828"]["inputs"]["cfg"] == 1.2


def test_distilled_lora_is_pinned_and_keeps_blueprint_strength():
    graph = _build()
    assert DISTILLED_MARKER in graph["4922"]["inputs"]["lora_name"]
    assert graph["4922"]["inputs"]["strength_model"] == 0.5


def test_user_lora_chains_after_the_distilled_one_instead_of_replacing_it():
    graph = _build(lora=USER_LORA, lora_scale=0.8)

    # The distilled adapter survives untouched...
    assert DISTILLED_MARKER in graph["4922"]["inputs"]["lora_name"]
    assert graph["4922"]["inputs"]["strength_model"] == 0.5

    # ...and the user's lora is inserted downstream of it.
    chained = graph["8801"]
    assert chained["class_type"] == "LoraLoaderModelOnly"
    assert chained["inputs"]["lora_name"] == USER_LORA
    assert chained["inputs"]["strength_model"] == 0.8
    assert chained["inputs"]["model"] == ["4922", 0]

    # Both guiders now read through the chain, and nothing dangles.
    assert graph["4828"]["inputs"]["model"] == ["8801", 0]
    assert graph["4964"]["inputs"]["model"] == ["8801", 0]
    assert _dangling(graph) == []


@pytest.mark.parametrize("token", ["", "none", "off", "disabled", "no", "NONE"])
def test_lora_opt_out_tokens_skip_the_chain(token):
    graph = _build(lora=token)
    assert "8801" not in graph
    assert DISTILLED_MARKER in graph["4922"]["inputs"]["lora_name"]
    assert _dangling(graph) == []


def test_use_lora_false_skips_the_chain():
    graph = _build(lora=USER_LORA, use_lora=False)
    assert "8801" not in graph


def test_stage_seeds_are_decorrelated():
    graph = _build(seed=1234)
    base = graph["4832"]["inputs"]["noise_seed"]
    refine = graph["4967"]["inputs"]["noise_seed"]
    assert base == 1234
    assert refine != base


def test_stage_sampler_keys_map_by_dataflow():
    graph = _build(ltx_sampler_stage1="euler", ltx_sampler_stage2="heun")
    # 4831 drives the base sampler 4829; 4976 drives the refine sampler 4971.
    assert graph["4831"]["inputs"]["sampler_name"] == "euler"
    assert graph["4976"]["inputs"]["sampler_name"] == "heun"


def test_blueprint_sampler_defaults_survive_when_unset():
    graph = _build()
    assert graph["4831"]["inputs"]["sampler_name"] == "euler_ancestral_cfg_pp"
    assert graph["4976"]["inputs"]["sampler_name"] == "euler_cfg_pp"


def test_distilled_sigmas_are_untouched_by_a_steps_request():
    graph = _build(steps=30)
    assert graph["4984"]["inputs"]["sigmas"].startswith("1.0,")
    assert graph["4985"]["inputs"]["sigmas"].startswith("0.85,")
