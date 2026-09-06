"""Graph shape tests for the Wrought transport. Hermetic: no ComfyUI is contacted."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
sys.path.insert(0, str(ROOT / "python"))

import wrought_comfy as wc  # noqa: E402


def _by_class(graph: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append(node_id)
    return out


def test_t2i_graph_is_the_locked_recipe():
    g = wc.t2i_graph("pos", "neg", seed=7, prefix="x", width=768, height=1024)
    classes = _by_class(g)
    for needed in ("UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode",
                   "ModelSamplingAuraFlow", "EmptySD3LatentImage", "KSampler", "VAEDecode",
                   "SaveImage"):
        assert needed in classes, needed
    ks = g[classes["KSampler"][0]]["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (52, 3.5, "euler", "simple")
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["shift"] == 1.15
    assert g[classes["CLIPLoader"][0]]["inputs"]["type"] == "krea2"
    assert ks["seed"] == 7
    assert g[classes["EmptySD3LatentImage"][0]]["inputs"] == {"width": 768, "height": 1024, "batch_size": 1}


def test_reference_edit_graph_routes_the_reference_into_the_positive():
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png")
    classes = _by_class(g)
    assert "LoadImage" in classes and "TextEncodeQwenImageEditPlus" in classes
    assert "FluxKontextMultiReferenceLatentMethod" in classes
    load = classes["LoadImage"][0]
    enc = g[classes["TextEncodeQwenImageEditPlus"][0]]["inputs"]
    assert enc["image1"] == [load, 0] and enc["vae"][0] == classes["VAELoader"][0]
    method = classes["FluxKontextMultiReferenceLatentMethod"][0]
    assert g[method]["inputs"]["conditioning"] == [classes["TextEncodeQwenImageEditPlus"][0], 0]
    assert g[method]["inputs"]["reference_latents_method"] == "index_timestep_zero"
    ks = g[classes["KSampler"][0]]["inputs"]
    assert ks["positive"] == [method, 0]
    # the NEGATIVE is the real house negative, not ConditioningZeroOut -- we run CFG 3.5 on RAW
    assert g[ks["negative"][0]]["class_type"] == "CLIPTextEncode"
    assert g[ks["negative"][0]]["inputs"]["text"] == "neg"


def test_no_graph_carries_a_disk_path():
    g = wc.reference_edit_graph("pos", "neg", 1, "x", 8, 8, reference_name="skin_000.png")
    assert g[_by_class(g)["LoadImage"][0]]["inputs"]["image"] == "skin_000.png"
    assert ":\\" not in str(g) and "C:/" not in str(g)


@pytest.mark.needs_comfy
def test_live_core_knows_every_node_class_we_emit():
    """Doc 50 rule 2: the class names come from a live /object_info, not from memory."""
    from comfy_prompt_client import _http_get_json
    info = _http_get_json("http://127.0.0.1:8188", "/object_info", timeout=60)
    g = wc.reference_edit_graph("pos", "neg", 1, "x", 8, 8, reference_name="r.png")
    for node in g.values():
        assert node["class_type"] in info, node["class_type"]
    ref = info["FluxKontextMultiReferenceLatentMethod"]["input"]["required"]
    assert "reference_latents_method" in ref


def test_lane_a_suit_graph_uses_a_different_seed_and_the_uploaded_name():
    g = wc.reference_edit_graph("suit prompt", "neg", seed=9_500_007, prefix="wv2_orc_007_suit",
                                width=1216, height=1728, reference_name="wv2_orc_007_skin_00001_.png")
    ks = g[[k for k, n in g.items() if n["class_type"] == "KSampler"][0]]["inputs"]
    assert ks["seed"] == 9_500_007
    load = g[[k for k, n in g.items() if n["class_type"] == "LoadImage"][0]]["inputs"]["image"]
    assert load.endswith(".png") and "/" not in load


def test_reference_edit_graph_carries_krea_s_own_reference_lora_by_default():
    # Measured 2026-09-06: Utopic cannot consume reference tokens without this LoRA (latent
    # checkerboard) -- see wrought_comfy.reference_edit_graph's docstring and
    # evidence/v2_reference_edit_probes_2026-09-06.jpg. The LoRA sits between the checkpoint and
    # ModelSamplingAuraFlow, so every downstream sampling node rides the patched model.
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png")
    classes = _by_class(g)
    lora_id = classes["LoraLoaderModelOnly"][0]
    lora = g[lora_id]["inputs"]
    assert lora["lora_name"] == "krea2_style_reference.safetensors"
    assert lora["strength_model"] == 1.0
    assert lora["model"] == [classes["UNETLoader"][0], 0]
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["model"] == [lora_id, 0]


def test_reference_edit_graph_omits_the_lora_when_asked():
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png", lora=None)
    classes = _by_class(g)
    assert "LoraLoaderModelOnly" not in classes
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["model"] == [classes["UNETLoader"][0], 0]
