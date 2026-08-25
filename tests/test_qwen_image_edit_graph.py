from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from qwen_image_edit_graph import (
    REQUIRED_CLASSES,
    UNET_NAME,
    build_qwen_image_edit_graph,
    graph_uses_classes,
)


def _graph(**kwargs):
    base = dict(
        input_image="051_whbs_underwear.png",
        prompt="Change the orange crop to a white t-shirt. Keep the same woman.",
        seed=5051,
    )
    base.update(kwargs)
    return build_qwen_image_edit_graph(**base)


def test_graph_has_every_live_class() -> None:
    assert graph_uses_classes(_graph()) == []


def test_starts_from_empty_latent_not_vaeencode() -> None:
    g = _graph()
    types = {n["class_type"] for n in g.values()}
    assert "VAEEncode" not in types
    assert "VAEEncodeForInpaint" not in types
    assert g["8"]["inputs"]["latent_image"] == ["12", 0]
    assert g["8"]["inputs"]["denoise"] == 1.0
    assert g["12"]["class_type"] == "EmptySD3LatentImage"


def test_image_goes_through_edit_encoder() -> None:
    g = _graph()
    assert g["4"]["class_type"] == "TextEncodeQwenImageEditPlus"
    assert g["4"]["inputs"]["image1"] == ["11", 0]
    assert g["4"]["inputs"]["vae"] == ["3", 0]


def test_omit_vae_ref_when_requested() -> None:
    g = _graph(pass_vae=False)
    assert "vae" not in g["4"]["inputs"]


def test_clip_type_is_qwen_image_not_krea2() -> None:
    assert _graph()["2"]["inputs"]["type"] == "qwen_image"


def test_default_unet_is_2511() -> None:
    assert UNET_NAME.startswith("qwen_image_edit_2511")
    assert _graph()["1"]["inputs"]["unet_name"] == UNET_NAME


def test_missing_image_raises() -> None:
    try:
        build_qwen_image_edit_graph(input_image="", prompt="x")
    except ValueError as exc:
        assert "input_image" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_reference_image_wires_image2() -> None:
    g = _graph(reference_images=("051_style.png",))
    assert g["14"]["class_type"] == "LoadImage"
    assert g["14"]["inputs"]["image"] == "051_style.png"
    assert g["4"]["inputs"]["image2"] == ["14", 0]
    assert g["12"]["class_type"] == "EmptySD3LatentImage"


def test_too_many_refs_raises() -> None:
    try:
        _graph(reference_images=("a.png", "b.png", "c.png"))
    except ValueError as exc:
        assert "2 extra" in str(exc)
    else:
        raise AssertionError("expected ValueError")
