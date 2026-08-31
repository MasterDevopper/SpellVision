from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from krea2_regional_inpaint import (
    REQUIRED_CLASSES,
    build_krea2_regional_inpaint_graph,
    graph_uses_classes,
)


def _graph():
    return build_krea2_regional_inpaint_graph(
        unet_name="loxsUtopicWorldKrea2_v10Quants.safetensors",
        lock_image="051_whbs_underwear.png",
        mask_image="mask_outfit_orange.png",
        edit_prompt="fitted opaque white t-shirt",
        identity_prompt="the same specific woman, gold hoop earrings, icy blue eyes",
        seed=5051,
    )


def test_graph_has_every_live_class() -> None:
    missing = graph_uses_classes(_graph())
    assert missing == [], missing


def test_no_conditioning_set_mask() -> None:
    types = {n["class_type"] for n in _graph().values()}
    assert "ConditioningSetMask" not in types
    assert "ConditioningCombine" not in types


def test_identity_is_folded_into_positive() -> None:
    text = _graph()["4"]["inputs"]["text"]
    assert "same specific woman" in text
    assert "white t-shirt" in text


def test_sampler_sees_inpaint_latent() -> None:
    g = _graph()
    assert g["8"]["inputs"]["positive"] == ["4", 0]
    assert g["8"]["inputs"]["latent_image"] == ["24", 0]
    assert g["8"]["inputs"]["denoise"] == 0.7
    assert g["24"]["class_type"] == "VAEEncodeForInpaint"
    assert g["24"]["inputs"]["mask"] == ["15", 0]


def test_save_composites_onto_lock() -> None:
    g = _graph()
    assert g["10"]["inputs"]["images"] == ["25", 0]
    assert g["25"]["class_type"] == "ImageCompositeMasked"
    assert g["25"]["inputs"]["destination"] == ["11", 0]
    assert g["25"]["inputs"]["source"] == ["9", 0]


def test_missing_mask_raises() -> None:
    try:
        build_krea2_regional_inpaint_graph(
            unet_name="x.safetensors",
            lock_image="a.png",
            mask_image="",
            edit_prompt="tee",
        )
    except ValueError as exc:
        assert "mask" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_required_classes_tuple_is_complete() -> None:
    assert "VAEEncodeForInpaint" in REQUIRED_CLASSES
    assert "ImageCompositeMasked" in REQUIRED_CLASSES
    assert "GrowMask" in REQUIRED_CLASSES


def test_denoise_is_honored() -> None:
    g = build_krea2_regional_inpaint_graph(
        unet_name="x.safetensors",
        lock_image="a.png",
        mask_image="m.png",
        edit_prompt="tee",
        denoise=0.55,
    )
    assert g["8"]["inputs"]["denoise"] == 0.55


def test_noise_mask_mode_uses_set_latent() -> None:
    g = build_krea2_regional_inpaint_graph(
        unet_name="x.safetensors",
        lock_image="a.png",
        mask_image="m.png",
        edit_prompt="tee",
        latent_mode="noise_mask",
        denoise=0.7,
    )
    assert g["24"]["class_type"] == "VAEEncode"
    assert g["26"]["class_type"] == "SetLatentNoiseMask"
    assert g["8"]["inputs"]["latent_image"] == ["26", 0]


def test_worker_command_contract_is_documented() -> None:
    root = Path(__file__).resolve().parent.parent
    text = (root / "runtime/style/datasets/wrought_house_v1/FEATURE_BLUEPRINT.md").read_text(
        encoding="utf-8"
    )
    assert "denoise=0.70" in text
    assert "Utopic Quants" in text
