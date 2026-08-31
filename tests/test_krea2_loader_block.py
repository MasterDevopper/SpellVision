"""Four Krea 2 graphs opened the same way, and only one of them offloaded its text encoder.

The audit's headline duplication finding: the Krea 2 graph is hand-copied into four builders --
``native_image_graphs`` (t2i / i2i), ``krea2_regional_inpaint``, ``look_completion`` and
``clothes_only`` -- with identical node ids and identical wiring for the first six nodes. Only the
first passed a ``device`` to the CLIPLoader. That input is what the memory profile uses to move the
4B text encoder to system RAM when VRAM is tight, so **the same model fitted as t2i and OOM'd as
inpaint.**

It survived Phase 4c, which routed nine text-encoder sites through one resolver and drove that sweep
to zero, because the rule caught a device value written BY HAND and these four wrote none at all. An
omission has no syntax. The rule is widened here to look for the class rather than the value, and it
found two more the moment it ran: sd3's TripleCLIPLoader -- the family with three encoders and the
most to gain -- and the qwen edit graph.

What is shared is the loader block. What is not shared stays separate: the inpaint route runs
sixteen nodes through VAEEncodeForInpaint and ImageCompositeMasked where the t2i routes run ten, and
forcing one topology on both would be applying a rule at the wrong level -- the mistake this audit
keeps finding, committed in the name of fixing it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from krea2_graph import (  # noqa: E402
    CLIP_ID,
    KREA2_CLIP_TYPE,
    KREA2_SHIFT,
    UNET_ID,
    krea2_loader_block,
)

OBJ = {"CLIPLoader": {"input": {"optional": {"device": [["default", "cpu"], {}]}}}}

NAMES = dict(unet_name="k.safetensors", clip_name="c.safetensors", vae_name="v.safetensors")


def _block(**kwargs):
    return krea2_loader_block(positive="a knight", negative="blurry", **NAMES, **kwargs)


# --- the block itself ------------------------------------------------------------------------------

def test_the_block_is_the_six_nodes_every_copy_shared() -> None:
    block = _block()
    assert {n["class_type"] for n in block.values()} == {
        "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "ModelSamplingAuraFlow",
    }
    assert len(block) == 6


def test_the_shift_is_the_grounded_one() -> None:
    """1.15 is Krea2.sampling_settings via ModelSamplingAuraFlow, read from live Comfy source. All
    four copies carried the same literal and agreed, which is the one thing that made this merge
    safe to do without a render."""
    assert KREA2_SHIFT == 1.15
    assert _block()["5"]["inputs"]["shift"] == 1.15


def test_the_sampling_node_id_is_a_parameter_because_the_callers_disagreed() -> None:
    """The t2i graphs put ModelSamplingAuraFlow at "5" and the inpaint graph at "7". Renumbering a
    live graph to make them match would change every reference for no gain."""
    assert "5" in _block() and "7" not in _block()
    assert "7" in _block(sampling_node_id="7")


def test_the_text_encodes_are_wired_to_the_loader() -> None:
    block = _block()
    assert block["4"]["inputs"]["clip"] == [CLIP_ID, 0]
    assert block["6"]["inputs"]["clip"] == [CLIP_ID, 0]
    assert block["4"]["inputs"]["text"] == "a knight"
    assert block["6"]["inputs"]["text"] == "blurry"
    assert block["5"]["inputs"]["model"] == [UNET_ID, 0]


# --- the defect --------------------------------------------------------------------------------------

def test_the_device_reaches_the_loader() -> None:
    block = _block(request={"text_encoder_device": "cpu"}, object_info=OBJ)
    assert block[CLIP_ID]["inputs"]["device"] == "cpu"


def test_no_object_info_writes_no_device_rather_than_guessing() -> None:
    """Same rule as everywhere else: do not invent a vocabulary you cannot read. It also makes this
    refactor provably behaviour-preserving -- every caller's graph is byte-identical to what it
    produced before, until an object_info is supplied."""
    assert "device" not in _block()[CLIP_ID]["inputs"]


@pytest.mark.parametrize("builder", ["look_t2i", "clothes", "inpaint", "native"])
def test_every_krea2_route_honours_the_memory_profile(builder: str, monkeypatch) -> None:
    """The bug, stated as the property that prevents it. Before this, three of these four had no
    `device` key at all and the fourth did."""
    request = {"text_encoder_device": "cpu"}
    if builder == "look_t2i":
        from look_completion import build_krea2_t2i_graph

        graph = build_krea2_t2i_graph(
            prompt="x", negative_prompt="", width=768, height=1344, seed=1, steps=8, cfg=1.0,
            filename_prefix="p", request=request, object_info=OBJ, **NAMES)
    elif builder == "clothes":
        from clothes_only import build_clothes_only_krea2_graph

        graph = build_clothes_only_krea2_graph(
            prompt="x", negative="", width=768, height=1344, seed=1, steps=8, cfg=1.0,
            filename_prefix="p", request=request, object_info=OBJ, **NAMES)
    elif builder == "inpaint":
        from krea2_regional_inpaint import build_krea2_regional_inpaint_graph

        graph = build_krea2_regional_inpaint_graph(
            lock_image="l.png", mask_image="m.png", edit_prompt="x", identity_prompt="y",
            negative_prompt="", seed=1, steps=8, cfg=1.0, grow_mask_by=4, feather=4,
            denoise=0.7, latent_mode="inpaint", filename_prefix="p",
            request=request, object_info=OBJ, **NAMES)
    else:
        import native_image_graphs as nig

        monkeypatch.setattr(nig, "_comfy_unet_name_for_model", lambda info, path: "k.safetensors")

        class _R:
            def value(self, key):
                return None

        graph = nig._build_krea2_image_prompt(
            {"model": "diffusion_models/krea2.safetensors", "prompt": "x",
             "width": 1024, "height": 1024, "seed": 1, **request},
            OBJ, "job", _R())

    assert graph[CLIP_ID]["class_type"] == "CLIPLoader"
    assert graph[CLIP_ID]["inputs"]["device"] == "cpu", (
        f"{builder} does not offload its text encoder; this is the OOM-vs-fits bug"
    )
    assert graph[CLIP_ID]["inputs"]["type"] == KREA2_CLIP_TYPE


# --- what stays different -----------------------------------------------------------------------------

def test_the_inpaint_topology_is_not_forced_into_the_t2i_shape() -> None:
    """Merging these would be applying a rule at the wrong level. They differ because the work
    differs, not because nobody tidied them."""
    from krea2_regional_inpaint import build_krea2_regional_inpaint_graph
    from look_completion import build_krea2_t2i_graph

    t2i = build_krea2_t2i_graph(
        prompt="x", negative_prompt="", width=768, height=1344, seed=1, steps=8, cfg=1.0,
        filename_prefix="p", **NAMES)
    inpaint = build_krea2_regional_inpaint_graph(
        lock_image="l.png", mask_image="m.png", edit_prompt="x", identity_prompt="y",
        negative_prompt="", seed=1, steps=8, cfg=1.0, grow_mask_by=4, feather=4,
        denoise=0.7, latent_mode="inpaint", filename_prefix="p", **NAMES)

    assert len(t2i) == 10 and len(inpaint) > 10
    shared = {"1", "2", "3", "4", "6"}
    for node_id in shared:
        assert t2i[node_id]["class_type"] == inpaint[node_id]["class_type"]


def test_only_the_native_route_splices_a_lora_chain(monkeypatch) -> None:
    """The one declared difference in the block's own nodes: the native route re-points the shift
    node at the end of a LoRA chain. The other three have no LoRA support at all -- a gap that
    deserves its own decision rather than a silent inheritance."""
    import native_image_graphs as nig

    monkeypatch.setattr(nig, "_comfy_unet_name_for_model", lambda info, path: "k.safetensors")

    class _R:
        def value(self, key):
            return None

    graph = nig._build_krea2_image_prompt(
        {"model": "diffusion_models/krea2.safetensors", "prompt": "x",
         "width": 1024, "height": 1024, "seed": 1}, OBJ, "job", _R())
    assert graph["5"]["inputs"]["model"] == [UNET_ID, 0], "no LoRA selected: chain is a no-op"


# --- the widened rule -----------------------------------------------------------------------------

def test_the_rule_now_sees_an_omitted_device() -> None:
    """The point. Phase 4c drove this rule to zero across nine sites while four loaders sat with no
    device key: the rule caught a value written by hand, and an omission has no syntax."""
    import ast

    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import rules

    omitted = 'g = {"class_type": "CLIPLoader", "inputs": {"clip_name": n, "type": "krea2"}}'
    found = rules._check_text_encoder_omits_device(Path("python/fake.py"), ast.parse(omitted))
    assert found, "the widened rule does not catch the form it was widened for"

    splatted = ('g = {"class_type": "CLIPLoader", "inputs": {"clip_name": n, "type": "krea2",'
                ' **text_encoder_device_input(req, oi, "CLIPLoader")}}')
    assert not rules._check_text_encoder_omits_device(Path("python/fake.py"), ast.parse(splatted))


def test_a_node_that_is_not_a_text_encoder_is_left_alone() -> None:
    import ast

    from sweeps import rules

    other = 'g = {"class_type": "VAELoader", "inputs": {"vae_name": v}}'
    assert not rules._check_text_encoder_omits_device(Path("python/fake.py"), ast.parse(other))
