from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from look_completion import (
    CONTRACT,
    NEGATIVE_PROMPT,
    PRESENT_REGIONS,
    TARGET_HEIGHT,
    TARGET_NAME,
    TARGET_WIDTH,
    LookCompleteRefused,
    build_graph_for_plan,
    build_krea2_t2i_graph,
    classify_crop,
    classify_still,
    figure_metrics,
    inventory_robust,
    pad_source_to_canvas,
    payload_from_request,
    plan_look_complete,
    regions_for_crop,
    run_look_complete_job,
    sha256_file,
)


def _blank(path: Path, size: tuple[int, int], color: tuple[int, int, int] = (255, 255, 255)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def _paint_full_body(path: Path) -> Path:
    """Tall sheet: head, torso, legs, two small feet, white around the toes."""
    im = Image.new("RGB", (200, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((80, 10, 120, 55), fill=(210, 170, 140))  # face
    d.rectangle((70, 55, 130, 80), fill=(40, 40, 40))  # hair
    d.rectangle((65, 80, 135, 200), fill=(70, 110, 80))  # torso clothes
    d.rectangle((75, 200, 125, 330), fill=(70, 110, 80))  # legs
    d.rectangle((78, 330, 95, 385), fill=(50, 40, 35))  # left foot
    d.rectangle((105, 330, 122, 385), fill=(50, 40, 35))  # right foot
    im.save(path)
    return path


def _paint_bust(path: Path) -> Path:
    """Square crop: head + torso, empty lower third."""
    im = Image.new("RGB", (200, 220), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((70, 8, 130, 70), fill=(210, 170, 140))
    d.rectangle((60, 55, 140, 85), fill=(30, 30, 30))
    d.rectangle((50, 85, 150, 130), fill=(90, 60, 50))
    im.save(path)
    return path


def _paint_three_quarter(path: Path) -> Path:
    """Squat portrait truncated at the thighs (wide bottom touch)."""
    im = Image.new("RGB", (220, 240), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((80, 6, 140, 60), fill=(210, 170, 140))
    d.rectangle((55, 60, 165, 160), fill=(80, 90, 70))
    d.rectangle((60, 160, 160, 239), fill=(80, 90, 70))
    im.save(path)
    return path


def _paint_face(path: Path) -> Path:
    im = Image.new("RGB", (160, 160), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((50, 10, 110, 70), fill=(210, 170, 140))
    d.rectangle((48, 8, 112, 28), fill=(20, 20, 20))
    im.save(path)
    return path


def _paint_clothes(path: Path) -> Path:
    im = Image.new("RGB", (200, 280), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.polygon([(70, 40), (130, 40), (150, 200), (50, 200)], fill=(20, 20, 20))
    im.save(path)
    return path


def test_inventory_parse_and_dupe_collapse(tmp_path: Path) -> None:
    root = tmp_path / "Robust addon checker"
    witch = root / "witch"
    witch.mkdir(parents=True)
    body = _paint_full_body(witch / "witch_concept_01_front.jpg")
    loose = root / "loose_witch_concept_01_front.jpg"
    loose.write_bytes(body.read_bytes())
    _paint_bust(root / "gyaru.jfif")
    _paint_clothes(root / "clothes.jfif")
    # unique extra still
    _paint_face(root / "lips.jfif")

    index = inventory_robust(root, apply_vision_sample=False)
    assert index["contract"] == CONTRACT
    assert index["counts"]["files_seen"] == 5
    assert index["counts"]["unique_hashes"] == 4
    assert index["counts"]["duplicate_extra_files"] == 1
    assert "witch" in index["packs"]

    by_name = {}
    for entry in index["entries"]:
        for rel in entry["paths"]:
            by_name[rel] = entry
    witch_entry = by_name["witch/witch_concept_01_front.jpg"]
    assert "loose_witch_concept_01_front.jpg" in witch_entry["paths"]
    assert witch_entry["pack"] == "witch"
    assert witch_entry["crop"] == "full_body"
    assert set(witch_entry["present_regions"]) >= {"face", "hair", "torso_clothes", "legs", "feet"}

    clothes = by_name["clothes.jfif"]
    assert clothes["crop"] == "clothes_only"
    assert clothes["sha256"] == hashlib.sha256((root / "clothes.jfif").read_bytes()).hexdigest()


def test_sha256_matches_bytes(tmp_path: Path) -> None:
    path = tmp_path / "a.png"
    path.write_bytes(b"not-an-image-but-hashed")
    assert sha256_file(path) == hashlib.sha256(b"not-an-image-but-hashed").hexdigest()


def test_classify_crop_filename_clothes_only() -> None:
    crop, collage = classify_crop(name="clothes.jfif", width=736, height=1308)
    assert crop == "clothes_only"
    assert collage is False


def test_plan_full_body_is_noop(tmp_path: Path) -> None:
    path = _paint_full_body(tmp_path / "witch_concept_01_front.jpg")
    plan = plan_look_complete(path, pack="witch")
    assert plan.refused is False
    assert plan.crop == "full_body"
    assert plan.already_complete is True
    assert plan.method == "noop"
    assert "feet" in plan.present_regions
    assert plan.missing_regions == []
    payload = plan.to_payload()
    assert payload["already_complete"] is True
    assert payload["target"] == TARGET_NAME


def test_plan_bust_extends_down(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "gyaru.jfif")
    plan = plan_look_complete(path)
    assert plan.refused is False
    assert plan.crop == "bust"
    assert plan.method == "t2i_identity"
    assert "feet" in plan.missing_regions
    assert "legs" in plan.missing_regions
    assert "face" in plan.present_regions
    assert "torso_clothes" in plan.present_regions
    assert TARGET_WIDTH == 768 and TARGET_HEIGHT == 1344
    assert "head to toe" in plan.prompt
    assert "feet visible" in plan.prompt
    assert "maxi dress" in plan.negative_prompt


def test_plan_three_quarter_keeps_present_outfit(tmp_path: Path) -> None:
    path = _paint_three_quarter(tmp_path / "witch_concept_01_3q.jpg")
    plan = plan_look_complete(path, pack="witch")
    assert plan.crop == "three_quarter"
    assert "legs" in plan.present_regions
    assert "feet" in plan.missing_regions
    assert "fitted olive pants" in plan.prompt
    assert "maxi" not in plan.outfit_clause
    assert "witch hat" in plan.prompt


def test_refuse_clothes_only(tmp_path: Path) -> None:
    path = _paint_clothes(tmp_path / "clothes.jfif")
    plan = plan_look_complete(path)
    assert plan.refused is True
    assert plan.crop == "clothes_only"
    assert "clothes_only" in plan.refuse_reason
    with pytest.raises(LookCompleteRefused):
        plan.to_payload()


def test_refuse_clothes_only_from_regions_without_file() -> None:
    plan = plan_look_complete(
        None,
        present_regions=["torso_clothes"],
        crop="clothes_only",
        classify_pixels=False,
    )
    assert plan.refused is True
    with pytest.raises(LookCompleteRefused, match="clothes_only"):
        payload_from_request(
            {
                "input_image": "C:/no/such/clothes.jfif",
                "present_regions": ["torso_clothes"],
                "crop": "clothes_only",
                "target": TARGET_NAME,
                "model": "user_pick.safetensors",
            }
        )


def test_payload_shape_for_look_complete(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "baddie.jfif")
    payload = payload_from_request(
        {
            "command": "look_complete",
            "input_image": str(path),
            "present_regions": ["face", "hair", "torso_clothes"],
            "target": TARGET_NAME,
            "seed": 4419,
            "model": "C:/models/user_pick.safetensors",
        }
    )
    assert payload["command"] == "look_complete"
    assert payload["input_image"] == str(path)
    assert payload["present_regions"] == ["face", "hair", "torso_clothes"]
    assert payload["missing_regions"] == ["legs", "feet", "hands"]
    assert payload["target"] == "full_body_768x1344"
    assert payload["width"] == 768
    assert payload["height"] == 1344
    assert payload["method"] == "t2i_identity"
    assert payload["model"] == "C:/models/user_pick.safetensors"
    assert payload["unet_name"] == "user_pick.safetensors"
    assert "F:/AI_ASSETS" not in payload["model"]
    assert payload["steps"] == 52
    assert payload["cfg"] == 3.5
    assert payload["seed"] == 4419
    assert "head to toe" in payload["prompt"]
    assert payload["negative_prompt"] == NEGATIVE_PROMPT
    for region in payload["present_regions"] + payload["missing_regions"]:
        assert region in PRESENT_REGIONS


def test_payload_rejects_bad_target(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "x.png")
    with pytest.raises(Exception, match="target"):
        payload_from_request({"input_image": str(path), "target": "512square", "model": "user_pick.safetensors"})


def test_payload_requires_model(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "x.png")
    with pytest.raises(Exception, match="model"):
        payload_from_request({"input_image": str(path), "target": TARGET_NAME})


def test_t2i_graph_is_empty_latent_768x1344() -> None:
    graph = build_krea2_t2i_graph(
        prompt="full body, entire figure, head to toe, feet visible, witch",
        seed=7,
        unet_name="user_pick.safetensors",
    )
    assert graph["7"]["class_type"] == "EmptySD3LatentImage"
    assert graph["7"]["inputs"]["width"] == 768
    assert graph["7"]["inputs"]["height"] == 1344
    assert graph["2"]["inputs"]["type"] == "krea2"
    assert graph["1"]["inputs"]["unet_name"] == "user_pick.safetensors"
    assert graph["8"]["inputs"]["latent_image"] == ["7", 0]
    assert graph["8"]["inputs"]["denoise"] == 1.0
    assert graph["8"]["inputs"]["steps"] == 52
    assert graph["8"]["inputs"]["cfg"] == 3.5
    assert "ConditioningSetMask" not in {n["class_type"] for n in graph.values()}


def test_pad_inpaint_graph_reuses_regional_builder(tmp_path: Path) -> None:
    src = _paint_bust(tmp_path / "bust.png")
    plan = plan_look_complete(src, method="pad_inpaint")
    plan.unet_name = "user_pick.safetensors"
    canvas = tmp_path / "canvas.png"
    mask = tmp_path / "mask.png"
    info = pad_source_to_canvas(src, canvas, mask)
    assert Image.open(canvas).size == (768, 1344)
    assert Image.open(mask).size == (768, 1344)
    assert info["band_top"] < TARGET_HEIGHT
    # Empty band is white on the mask.
    mx = Image.open(mask)
    assert mx.getpixel((10, 1330)) == 255
    graph = build_graph_for_plan(plan, lock_image="canvas.png", mask_image="mask.png")
    types = {n["class_type"] for n in graph.values()}
    assert "VAEEncodeForInpaint" in types
    assert graph["1"]["inputs"]["unet_name"] == "user_pick.safetensors"
    assert "head to toe" in graph["4"]["inputs"]["text"]


def test_noop_graph_raises(tmp_path: Path) -> None:
    path = _paint_full_body(tmp_path / "full.png")
    plan = plan_look_complete(path)
    with pytest.raises(Exception, match="already"):
        build_graph_for_plan(plan)


def test_regions_for_crop_table() -> None:
    assert "feet" in regions_for_crop("full_body")
    assert "feet" not in regions_for_crop("bust")
    assert "legs" not in regions_for_crop("face")
    assert regions_for_crop("clothes_only") == ["torso_clothes"]


def test_figure_metrics_on_bust(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "b.png")
    metrics = figure_metrics(Image.open(path).convert("RGB"))
    assert metrics["bot_fill"] < 0.05
    assert metrics["vertical_span"] < 0.85


def test_look_complete_job_requires_image() -> None:
    try:
        run_look_complete_job({}, None, None, None)
    except Exception as exc:
        assert "input_image" in str(exc)
    else:
        raise AssertionError("expected LookCompleteError")


def test_look_complete_job_requires_model(tmp_path: Path) -> None:
    path = _paint_bust(tmp_path / "x.png")
    try:
        run_look_complete_job({"input_image": str(path)}, None, None, None)
    except Exception as exc:
        assert "model" in str(exc)
    else:
        raise AssertionError("expected LookCompleteError")


def test_sporty_bear_keeps_muzzle_not_kemonomimi(tmp_path: Path) -> None:
    path = tmp_path / "sporty_bear_concept_01_3q.png"
    Image.new("RGB", (720, 1280), (200, 180, 160)).save(path)
    plan = plan_look_complete(
        path,
        crop="three_quarter",
        present_regions=["face", "hair", "torso_clothes", "legs", "hands"],
        classify_pixels=False,
        pack="sporty bear",
    )
    assert "muzzle" in plan.identity_clause
    assert "kemonomimi" not in plan.prompt
    assert "orange cropped puffer" in plan.outfit_clause
    assert "gold B" in plan.outfit_clause
