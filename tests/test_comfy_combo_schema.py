"""`/object_info` publishes a combo in two shapes, and every reader has to know both.

ComfyUI is mid-migration. Measured against the live core (v0.34.0, `12d5279`) on 2026-09-02:

* **1738** combos in the legacy shape `[[choices], {...}]`
* **562** in the V3 shape `["COMBO", {"multiselect": false, "options": [...]}]`

Which shape a class publishes is a property of that class, not of the core, so a reader that knows
one shape is correct until the class it reads is migrated -- and then it returns an empty list.
Every caller in this tree reads an empty list as *"no constraint"* rather than as *"I could not
read it"*, which is how this cost a whole feature silently:

`UpscaleModelLoader.model_name` is one of the classes that has already moved.
`upscale_engine._combo_choices` indexed `raw[0]` for a list, got the string `"COMBO"`,
returned `[]`; `resolve_upscale_model_name` returned `""`; `graft_pixel_upscale` returned the graph
untouched. The pixel upscale route did nothing at all, on every family that reaches it, and
reported success.

Seven readers of that one question existed and one was correct. The module docstring named a wrong
one: `_comfy_input_choices` (16 call sites, legacy only) sat one letter away from
`_sv_comfy_input_choices` (4 call sites, both shapes). They are now one function with two names,
and `tests/sweeps` rule `combo-options-through-one-reader` fails a new eighth.

The fixtures below are the two real shapes, copied from the live payload.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import clothes_only  # noqa: E402
import comfy_graph_helpers as helpers  # noqa: E402
import family_operating_points  # noqa: E402
import upscale_engine  # noqa: E402
from video_adapters.base import input_choices  # noqa: E402

UPSCALERS = [
    "4x-AnimeSharp.safetensors",
    "4x-UltraSharp.pth",
    "remacri_original.safetensors",
]


def legacy(class_name: str, input_name: str, choices: list[str]) -> dict:
    """The shape 1738 combos still use."""
    return {class_name: {"input": {"required": {input_name: [list(choices), {}]}}}}


def v3(class_name: str, input_name: str, choices: list[str]) -> dict:
    """The shape 562 combos have moved to -- including UpscaleModelLoader."""
    return {
        class_name: {
            "input": {
                "required": {
                    input_name: ["COMBO", {"multiselect": False, "options": list(choices)}]
                }
            }
        }
    }


# --- the reader ------------------------------------------------------------------------------


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_the_one_reader_reads_both_shapes(shape) -> None:
    info = shape("UpscaleModelLoader", "model_name", UPSCALERS)
    assert helpers._comfy_input_choices(info, "UpscaleModelLoader", "model_name") == UPSCALERS


def test_the_two_names_are_one_function() -> None:
    """Both were imported across the tree, so both survive -- as the same object. A second
    implementation behind the second name is exactly the defect this file documents."""
    assert helpers._sv_comfy_input_choices is helpers._comfy_input_choices


def test_an_unreadable_shape_is_empty_not_an_exception() -> None:
    """A third shape must degrade to 'no choices', not take a builder down mid-graph."""
    weird = {"X": {"input": {"required": {"y": "not a spec at all"}}}}
    assert helpers._comfy_input_choices(weird, "X", "y") == []
    assert helpers._comfy_input_choices({}, "X", "y") == []


# --- every site that reads choices -------------------------------------------------------------


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_upscale_model_resolves_under_both_shapes(shape) -> None:
    """The regression this file exists for: under V3 this returned "" and the graft became a
    no-op."""
    info = shape("UpscaleModelLoader", "model_name", UPSCALERS)
    assert upscale_engine.resolve_upscale_model_name(info, "") == UPSCALERS[0]
    assert upscale_engine.resolve_upscale_model_name(info, "remacri_original.safetensors") == (
        "remacri_original.safetensors"
    )


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_the_pixel_graft_actually_grafts_under_both_shapes(shape) -> None:
    """End to end: the route's whole job is to exist in the submitted graph."""
    info = shape("UpscaleModelLoader", "model_name", UPSCALERS)
    info["ImageUpscaleWithModel"] = {"input": {"required": {"upscale_model": ["UPSCALE_MODEL"], "image": ["IMAGE"]}}}
    graph = {
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "sv"}},
        "8": {"class_type": "VAEDecode", "inputs": {}},
    }
    out = upscale_engine.graft_pixel_upscale(graph, info, model_name="")
    classes = [node.get("class_type") for node in out.values()]
    assert "ImageUpscaleWithModel" in classes and "UpscaleModelLoader" in classes
    assert out["9"]["inputs"]["images"] != ["8", 0], "SaveImage still reads the un-upscaled image"


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_sampler_choices_read_under_both_shapes(shape) -> None:
    """The live intersection is what keeps a family from offering a sampler the core dropped.
    Unreadable means it silently stops intersecting, which does not fail -- it just stops
    constraining."""
    info = shape("KSampler", "sampler_name", ["euler", "dpmpp_2m", "ddim"])
    assert family_operating_points._object_info_choices(info, "sampler_name") == {
        "euler", "dpmpp_2m", "ddim"
    }


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_krea2_unet_name_resolves_under_both_shapes(shape) -> None:
    info = shape("UNETLoader", "unet_name", ["krea2/loxsUtopicWorldKrea2_v10Quants.safetensors"])
    resolved = clothes_only.resolve_krea2_unet_name(info, "loxsUtopicWorldKrea2_v10Quants.safetensors")
    assert resolved.endswith("loxsUtopicWorldKrea2_v10Quants.safetensors")
    assert "krea2/" in resolved, "the subdirectory the loader expects was dropped"


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_checkpoint_name_resolves_under_both_shapes(shape) -> None:
    """This is what makes a checkpoint in a subfolder bind: the catalog entry carries the
    separator and the subdirectory, and a bare basename is not what the loader accepts."""
    info = shape("CheckpointLoaderSimple", "ckpt_name", ["sdxl\\anima_pencil-XL.safetensors"])
    assert helpers._comfy_ckpt_name_for_model(
        info, "D:/AI_ASSETS/models/checkpoints/sdxl/anima_pencil-XL.safetensors"
    ) == "sdxl\\anima_pencil-XL.safetensors"


@pytest.mark.parametrize("shape", [legacy, v3], ids=["legacy", "v3"])
def test_video_adapter_choices_read_under_both_shapes(shape) -> None:
    info = shape("CLIPLoader", "clip_name", ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"])
    assert input_choices(info, "CLIPLoader", "clip_name") == [
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    ]
