"""An upscale either happens or is reported. It is never silently substituted or silently dropped.

Every case here is a defect this engine shipped with, and they were all the same kind: **the wrong
answer arrived wearing the shape of the right one.**

* `Model` on an SDXL checkpoint -- the 112-checkpoint majority -- fell back to a lanczos resize,
  logged it at a level the root logger filters out, and returned a path as though the model upscale
  had run. `basicsr` and `realesrgan` are in **neither** venv, so that was every SDXL run.
* `krea2` and `sd3` were in `NATIVE_IMAGE_FAMILIES` and not in a second, smaller list, so they
  resolved to the PIL route -- which only the diffusers runner performs. Nobody performed it.
* `ImageUpscaleWithModel` has **no scale input** in the live schema, so the cockpit's Scale box
  changed nothing at all on the only route that reaches an upscale model.
* "Auto" meant `choices[0]`, which on this box is `4x-AnimeSharp.safetensors` -- an anime model as
  the default for every photoreal render, chosen by catalog order.
* A model name that matched no live choice was passed through unvalidated, turning a typo into a
  ComfyUI 400 rather than a message where the mistake was made.

`latent_ltx` was a fifth route name that no caller ever compared against, for a latent upscale the
LTX two-stage template performs and this module does not. A route name that names no route reads as
a capability on inspection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import upscale_engine  # noqa: E402
from upscale_engine import (  # noqa: E402
    ROUTE_NONE,
    ROUTE_PIXEL_COMFY,
    ROUTE_PIXEL_PIL,
    ROUTE_RESIZE_COMFY,
    ROUTE_UNAVAILABLE,
    UpscaleUnavailable,
    auto_upscale_model,
    graft_image_resize,
    graft_pixel_upscale,
    resolve_upscale_route,
)

# The six models actually installed, in the order the live loader publishes them.
INSTALLED = [
    "4x-AnimeSharp.safetensors",
    "4x-UltraSharp.pth",
    "4xNMKDYandereneoxl_v10.pt",
    "4xRealisticrescaler_100000G.pt",
    "remacri_extrasmoother.safetensors",
    "remacri_original.safetensors",
]

OBJECT_INFO = {
    "UpscaleModelLoader": {"input": {"required": {"model_name": [list(INSTALLED), {}]}}},
    "ImageUpscaleWithModel": {"input": {"required": {"upscale_model": ["UPSCALE_MODEL"], "image": ["IMAGE"]}}},
    "ImageScale": {"input": {"required": {"image": ["IMAGE"], "upscale_method": [["lanczos"], {}]}}},
    "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}},
}


def a_graph() -> dict:
    return {
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "sv"}},
    }


# --- routing ------------------------------------------------------------------------------------


@pytest.mark.parametrize("family", ["flux", "pixart", "lumina", "z_image", "anima", "krea2", "sd3"])
def test_every_native_image_family_can_upscale(family: str) -> None:
    """The list of families whose graph the builder builds is the list that can be grafted into.
    A second, smaller copy of it is what left krea2 and sd3 accepting the request and doing
    nothing."""
    assert resolve_upscale_route(family, "model", enabled=True) == ROUTE_PIXEL_COMFY


def test_an_algorithmic_method_on_a_native_family_resamples_rather_than_upgrading() -> None:
    """A native family's image never reaches PIL, so the resize happens in the graph -- with the
    filter the user chose. Substituting a *better* method is still substituting."""
    assert resolve_upscale_route("flux", "lanczos", enabled=True) == ROUTE_RESIZE_COMFY
    assert resolve_upscale_route("sd3", "nearest", enabled=True) == ROUTE_RESIZE_COMFY


def test_a_diffusers_family_keeps_the_pil_post_pass_for_what_pil_can_do() -> None:
    assert resolve_upscale_route("sdxl", "lanczos", enabled=True) == ROUTE_PIXEL_PIL


def test_a_model_upscale_the_build_cannot_run_is_unavailable_not_lanczos(monkeypatch) -> None:
    """The headline defect. With basicsr absent -- which is the state of both venvs -- a model
    upscale on a diffusers family has no mechanism, and saying so is the whole fix."""
    monkeypatch.setattr(upscale_engine, "_pil_model_path_available", lambda: False)
    assert resolve_upscale_route("sdxl", "model", enabled=True) == ROUTE_UNAVAILABLE
    assert resolve_upscale_route("sdxl", "pixel", enabled=True) == ROUTE_UNAVAILABLE

    note = upscale_engine.route_note(ROUTE_UNAVAILABLE, "sdxl", "model")
    assert "cannot perform it" in note and "Lanczos" in note, "the refusal has to say what to do"


def test_the_same_request_becomes_available_when_the_packages_are(monkeypatch) -> None:
    """A probe rather than a constant: installing the packages is a supported thing to do, and a
    constant would then be wrong in the other direction."""
    monkeypatch.setattr(upscale_engine, "_pil_model_path_available", lambda: True)
    assert resolve_upscale_route("sdxl", "model", enabled=True) == ROUTE_PIXEL_PIL


def test_disabled_and_none_are_still_none() -> None:
    assert resolve_upscale_route("flux", "model", enabled=False) == ROUTE_NONE
    assert resolve_upscale_route("flux", "none", enabled=True) == ROUTE_NONE


# --- which model "Auto" means -------------------------------------------------------------------


def test_auto_does_not_hand_a_photoreal_render_an_anime_model() -> None:
    assert auto_upscale_model(INSTALLED) == "4x-UltraSharp.pth"


def test_auto_still_answers_when_every_model_declares_a_subject() -> None:
    """A preference is not a refusal: with nothing general installed, catalog order is the honest
    fallback, and the user still gets an upscale."""
    assert auto_upscale_model(["4x-AnimeSharp.safetensors"]) == "4x-AnimeSharp.safetensors"
    assert auto_upscale_model([]) == ""


def test_a_stem_resolves_to_the_installed_filename() -> None:
    """Doc 27 spells four of these models as stems. A stem that did not resolve was passed through
    and became a 400 at submit."""
    assert upscale_engine.resolve_upscale_model_name(OBJECT_INFO, "remacri_original") == (
        "remacri_original.safetensors"
    )
    assert upscale_engine.resolve_upscale_model_name(
        OBJECT_INFO, "D:/AI_ASSETS/models/upscale_models/4x-UltraSharp.pth"
    ) == "4x-UltraSharp.pth"


def test_a_name_no_installed_model_matches_does_not_pass_through() -> None:
    assert upscale_engine.resolve_upscale_model_name(OBJECT_INFO, "4x-NotInstalled.pth") == ""


# --- the graft ------------------------------------------------------------------------------------


def test_graft_rewires_saveimage_through_the_upscale_model() -> None:
    grafted = graft_pixel_upscale(a_graph(), OBJECT_INFO, model_name="4x-UltraSharp.pth")
    saves = [n for n in grafted.values() if n.get("class_type") == "SaveImage"]
    assert len(saves) == 1
    up_id = saves[0]["inputs"]["images"][0]
    assert grafted[up_id]["class_type"] == "ImageUpscaleWithModel"
    assert grafted[up_id]["inputs"]["image"] == ["9", 0]
    loader_id = grafted[up_id]["inputs"]["upscale_model"][0]
    assert grafted[loader_id]["inputs"]["model_name"] == "4x-UltraSharp.pth"


def test_the_scale_box_reaches_the_graph() -> None:
    """`ImageUpscaleWithModel` applies the model's own factor and takes no scale, so an explicit
    ImageScale to the asked-for size is what makes the control mean anything. The target is computed
    from the render's dimensions, which is exact -- reading "4x" out of a filename is not."""
    grafted = graft_pixel_upscale(
        a_graph(), OBJECT_INFO, model_name="4x-UltraSharp.pth",
        scale=2.0, target_width=1024, target_height=1536,
    )
    save = next(n for n in grafted.values() if n.get("class_type") == "SaveImage")
    tail = grafted[save["inputs"]["images"][0]]
    assert tail["class_type"] == "ImageScale"
    assert (tail["inputs"]["width"], tail["inputs"]["height"]) == (2048, 3072)
    assert grafted[tail["inputs"]["image"][0]]["class_type"] == "ImageUpscaleWithModel"


def test_an_unresolvable_model_refuses_before_the_render() -> None:
    """The graph is built before any sampling, so refusing costs a message rather than a render."""
    with pytest.raises(UpscaleUnavailable) as excinfo:
        graft_pixel_upscale(a_graph(), OBJECT_INFO, model_name="4x-NotInstalled.pth")
    assert "4x-NotInstalled.pth" in str(excinfo.value)
    assert "4x-UltraSharp.pth" in str(excinfo.value), "the refusal has to list what IS available"


def test_a_core_without_the_upscale_nodes_refuses_rather_than_skipping() -> None:
    """This returned the graph untouched, which is indistinguishable from having upscaled."""
    with pytest.raises(UpscaleUnavailable):
        graft_pixel_upscale(a_graph(), {"SaveImage": {}}, model_name="4x-UltraSharp.pth")


def test_the_in_graph_resize_uses_the_filter_that_was_asked_for() -> None:
    grafted = graft_image_resize(
        a_graph(), OBJECT_INFO, method="nearest", scale=1.5, target_width=1024, target_height=1024)
    save = next(n for n in grafted.values() if n.get("class_type") == "SaveImage")
    node = grafted[save["inputs"]["images"][0]]
    assert node["class_type"] == "ImageScale"
    assert node["inputs"]["upscale_method"] == "nearest-exact", "ComfyUI's spelling of the same filter"
    assert (node["inputs"]["width"], node["inputs"]["height"]) == (1536, 1536)


def test_a_filter_comfy_does_not_offer_is_refused_not_swapped() -> None:
    with pytest.raises(UpscaleUnavailable):
        graft_image_resize(
            a_graph(), OBJECT_INFO, method="mitchell", scale=2.0, target_width=512, target_height=512)
