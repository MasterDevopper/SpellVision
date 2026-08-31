"""Clothes-only plates + shrinkwrap scaffold (Doc 44)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from clothes_only import (
    ClothesOnlyError,
    REQUIRED_VIEWS,
    UTOPIC_QUANTS_UNET,
    build_clothes_only_krea2_graph,
    build_clothes_only_prompt,
    garment_slug,
    prepare_clothes_dest,
    run_clothes_only,
    validate_clothes_only_request,
)
from garment_shrinkwrap import (
    BODY_VERTS_REQUIRED,
    GarmentShrinkwrapError,
    run_garment_shrinkwrap,
)

_REPO = Path(__file__).resolve().parents[1]


def _write(rel: str) -> str:
    return _REPO.joinpath(rel).read_text(encoding="utf-8")


def test_refuse_empty_garment() -> None:
    with pytest.raises(ClothesOnlyError, match="garment"):
        validate_clothes_only_request({"garment": "  ", "views": ["front"]})
    with pytest.raises(ClothesOnlyError, match="garment"):
        build_clothes_only_prompt("", views=["front"], dummy="none")


def test_refuse_empty_views() -> None:
    with pytest.raises(ClothesOnlyError, match="view"):
        validate_clothes_only_request({"garment": "white tee", "views": []})


def test_product_sheet_prompt_has_no_body() -> None:
    built = build_clothes_only_prompt("fitted opaque white tee", views=["front", "side"], dummy="none")
    assert built["dummy"] == "none"
    assert built["width"] == 1024
    assert built["height"] == 1024
    front = built["views"]["front"]
    assert "fitted opaque white tee" in front["prompt"]
    assert "isolated" in front["prompt"].lower()
    assert "fitted opaque white tee" in front["prompt"]
    assert "wrought style" in front["prompt"].lower()
    assert "studio product photo" not in front["prompt"].lower()
    assert "white background" not in front["prompt"].lower()
    assert "dark studio" in front["prompt"].lower() or "black backdrop" in front["prompt"].lower()
    assert "no model" in front["prompt"].lower() or "no body" in front["prompt"].lower()
    assert "white hair" not in front["prompt"].lower()
    assert "person" in front["negative"]
    assert "mannequin" in front["negative"]
    assert "front" in front["prompt"].lower()
    assert "side" in built["views"]["side"]["prompt"].lower()


def test_whbs_dummy_prompt_is_wrap_canvas() -> None:
    built = build_clothes_only_prompt("fitted opaque white tee", views=["front"], dummy="whbs")
    assert built["width"] == 768
    assert built["height"] == 1344
    prompt = built["views"]["front"]["prompt"].lower()
    assert "white hair" in prompt
    assert "sky-blue" in prompt or "sky blue" in prompt
    assert "warm brown" in prompt
    assert "gold hoop" in prompt
    assert "t-pose" in prompt or "t pose" in prompt
    assert "fitted opaque white tee" in prompt
    assert "wrought style" in prompt
    assert "short curly" not in prompt
    assert "second face" in built["views"]["front"]["negative"]


def test_refuse_unknown_dummy() -> None:
    with pytest.raises(ClothesOnlyError, match="dummy"):
        build_clothes_only_prompt("coat", views=["front"], dummy="mannequin")


def test_dest_layout_writes_notes_and_piece_list(tmp_path: Path) -> None:
    dest = prepare_clothes_dest(
        {
            "character_id": "witch",
            "garment": "Fitted Opaque White Tee",
            "runtime_root": str(tmp_path),
        }
    )
    assert dest.name == "fitted-opaque-white-tee"
    assert dest.parent.name == "garments"
    assert dest.parent.parent.name == "witch"
    notes = dest / "notes.txt"
    assert notes.is_file()
    text = notes.read_text(encoding="utf-8")
    assert "Fitted Opaque White Tee" in text
    assert "front" in text and "side" in text and "back" in text
    assert "Degraded" in text
    assert "14517" in text


def test_slug_is_stable() -> None:
    assert garment_slug("Fitted Opaque White Tee") == "fitted-opaque-white-tee"
    assert garment_slug("  leather coat!! ") == "leather-coat"


def test_krea2_graph_uses_native_loader_pattern() -> None:
    graph = build_clothes_only_krea2_graph(
        prompt="clean product sheet of a white tee, white background, no body",
        negative="person, mannequin",
        width=1024,
        height=1024,
        unet_name=UTOPIC_QUANTS_UNET,
        seed=7,
    )
    types = {node["class_type"] for node in graph.values()}
    assert "UNETLoader" in types
    assert "CLIPLoader" in types
    assert "VAELoader" in types
    assert "EmptySD3LatentImage" in types
    assert "KSampler" in types
    assert "SaveImage" in types
    clip = next(n for n in graph.values() if n["class_type"] == "CLIPLoader")
    assert clip["inputs"]["type"] == "krea2"
    unet = next(n for n in graph.values() if n["class_type"] == "UNETLoader")
    assert unet["inputs"]["unet_name"] == UTOPIC_QUANTS_UNET
    latent = next(n for n in graph.values() if n["class_type"] == "EmptySD3LatentImage")
    assert latent["inputs"]["width"] == 1024
    assert latent["inputs"]["height"] == 1024


def test_run_clothes_only_dry_run_payload(tmp_path: Path) -> None:
    result = run_clothes_only(
        {
            "garment": "fitted opaque white tee",
            "views": ["front", "side", "back"],
            "dummy": "none",
            "character_id": "character_01",
            "runtime_root": str(tmp_path),
            "dry_run": True,
        }
    )
    assert result["ok"] is True
    assert result["command"] == "clothes_only"
    assert result["dummy"] == "none"
    assert result["views"] == ["front", "side", "back"]
    dest = Path(result["dest"])
    assert dest.is_dir()
    assert (dest / "notes.txt").is_file()
    assert result["cook_complete"] is False
    assert "stills_to_mesh" in result["blocked_on"]
    assert result["plates"]["front"].endswith("front.png")
    job = json.loads((dest / "clothes_only_job.json").read_text(encoding="utf-8"))
    assert job["dummy"] == "none"
    assert job["wrap_dummy"] == "whbs"
    assert job["queue"] == []


def test_run_clothes_only_records_remaining_queue(tmp_path: Path) -> None:
    result = run_clothes_only(
        {
            "garment": "white tee",
            "queue": ["leather coat", "boots"],
            "views": REQUIRED_VIEWS,
            "dummy": "none",
            "character_id": "witch",
            "runtime_root": str(tmp_path),
            "dry_run": True,
        }
    )
    assert result["queue"] == ["leather coat", "boots"]
    notes = Path(result["dest"]).joinpath("notes.txt").read_text(encoding="utf-8")
    assert "leather coat" in notes
    assert "boots" in notes


def test_shrinkwrap_refuses_missing_plates(tmp_path: Path) -> None:
    dest = tmp_path / "garments" / "tee"
    dest.mkdir(parents=True)
    (dest / "front.png").write_bytes(b"front-bytes")
    with pytest.raises(GarmentShrinkwrapError, match="missing"):
        run_garment_shrinkwrap(
            {
                "plates_dir": str(dest),
                "views": ["front", "side", "back"],
            }
        )


def test_shrinkwrap_refuses_identical_hashes(tmp_path: Path) -> None:
    dest = tmp_path / "garments" / "tee"
    dest.mkdir(parents=True)
    blob = b"same-plate-bytes"
    for name in ("front.png", "side.png", "back.png"):
        (dest / name).write_bytes(blob)
    with pytest.raises(GarmentShrinkwrapError, match="identical"):
        run_garment_shrinkwrap({"plates_dir": str(dest), "views": ["front", "side", "back"]})


def test_shrinkwrap_scaffold_job_json(tmp_path: Path) -> None:
    dest = tmp_path / "garments" / "tee"
    dest.mkdir(parents=True)
    (dest / "front.png").write_bytes(b"front-unique")
    (dest / "side.png").write_bytes(b"side-unique")
    (dest / "back.png").write_bytes(b"back-unique")
    body = tmp_path / "female.glb"
    body.write_bytes(b"glb-stub")
    result = run_garment_shrinkwrap(
        {
            "plates_dir": str(dest),
            "views": ["front", "side", "back"],
            "body": str(body),
            "character_id": "witch",
        }
    )
    assert result["ok"] is True
    assert result["method"] == "projected_shrinkwrap_scaffold"
    assert result["body_verts_required"] == BODY_VERTS_REQUIRED == 14517
    assert result["cook_complete"] is False
    assert result["blocked_on"] == ["stills_to_mesh", "garment_cook"]
    job_path = Path(result["wrap_job"])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["method"] == "projected_shrinkwrap_scaffold"
    assert job["body_verts_required"] == 14517
    assert job["blocked_on"] == ["stills_to_mesh", "garment_cook"]
    assert Path(job["body"]).exists()
    hashes = {hashlib.sha256((dest / f"{v}.png").read_bytes()).hexdigest() for v in ("front", "side", "back")}
    assert len(hashes) == 3
    assert result["body_present"] is True
    assert result["blender_run"]["ran"] is False


def test_extract_garment_silhouette_from_white_bg(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw
    from garment_shrinkwrap import extract_garment_silhouette

    plate = tmp_path / "front.png"
    im = Image.new("RGB", (64, 64), (255, 255, 255))
    ImageDraw.Draw(im).rectangle((16, 8, 48, 56), fill=(40, 80, 40))
    im.save(plate)
    dest = tmp_path / "silhouette_front.png"
    info = extract_garment_silhouette(plate, dest)
    assert dest.is_file()
    assert 0.05 < info["frac"] < 0.8
    assert info["bbox"][2] > info["bbox"][0]


def test_extract_silhouette_dark_studio(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw
    from garment_shrinkwrap import extract_garment_silhouette

    plate = tmp_path / "front.png"
    im = Image.new("RGB", (64, 64), (8, 8, 8))
    ImageDraw.Draw(im).rectangle((16, 8, 48, 56), fill=(90, 110, 50))
    im.save(plate)
    dest = tmp_path / "silhouette_front.png"
    info = extract_garment_silhouette(plate, dest)
    assert dest.is_file()
    assert 0.05 < info["frac"] < 0.8


def test_extract_worn_garments_drops_dark_bg_and_skin(tmp_path: Path) -> None:
    from PIL import Image
    from garment_shrinkwrap import extract_worn_garments_from_dummy

    im = Image.new("RGB", (64, 96), (8, 8, 8))
    px = im.load()
    for y in range(20, 50):
        for x in range(20, 44):
            px[x, y] = (90, 110, 50)
    for y in range(10, 22):
        for x in range(24, 40):
            px[x, y] = (170, 110, 80)
    src = tmp_path / "dummy.png"
    im.save(src)
    dest = tmp_path / "extract"
    info = extract_worn_garments_from_dummy(src, dest)
    assert Path(info["path"]).is_file()
    assert 0.04 < info["frac"] < 0.6
    assert info["method"] == "worn_dummy_extract"


def test_split_front_pieces_two_islands(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw
    from garment_shrinkwrap import extract_garment_silhouette, split_front_garment_pieces

    plate = tmp_path / "front.png"
    im = Image.new("RGB", (80, 40), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.rectangle((4, 4, 28, 16), fill=(30, 80, 30))
    draw.rectangle((4, 22, 28, 36), fill=(30, 80, 30))
    im.save(plate)
    mask = tmp_path / "silhouette_front.png"
    extract_garment_silhouette(plate, mask)
    pieces = split_front_garment_pieces(mask, tmp_path, min_frac=0.02)
    assert len(pieces) >= 2
    assert (tmp_path / "silhouette_front_piece_00.png").is_file()


def test_shrinkwrap_records_missing_body(tmp_path: Path) -> None:
    dest = tmp_path / "garments" / "tee"
    dest.mkdir(parents=True)
    (dest / "front.png").write_bytes(b"a")
    (dest / "side.png").write_bytes(b"b")
    (dest / "back.png").write_bytes(b"c")
    result = run_garment_shrinkwrap(
        {
            "plates_dir": str(dest),
            "body": str(tmp_path / "missing-female.glb"),
        }
    )
    assert result["body_present"] is False
    job = json.loads(Path(result["wrap_job"]).read_text(encoding="utf-8"))
    assert job["body_missing"] is True


def test_worker_allow_set_and_dispatch_register_new_commands() -> None:
    tcp = _write("python/worker_tcp.py")
    service = _write("python/worker_service.py")
    queue = _write("python/worker_queue.py")
    for command in ("clothes_only", "garment_shrinkwrap", "krea2_regional_inpaint", "look_complete"):
        assert f'"{command}"' in tcp
        assert f'"{command}"' in service
        assert f'"{command}"' in queue
    assert "from clothes_only import" in service or "import clothes_only" in service
    assert "from garment_shrinkwrap import" in service or "import garment_shrinkwrap" in service
    assert "look_completion" in service
    assert "krea2_regional_inpaint" in service


def test_character_studio_emits_clothes_only_payload() -> None:
    cpp = _write("qt_ui/studios/CharacterStudioPage.cpp")
    header = _write("qt_ui/studios/CharacterStudioPage.h")
    assert "clothes_only" in cpp
    assert "dummy" in cpp
    assert "whbs" in cpp
    assert "front" in cpp and "side" in cpp and "back" in cpp
    assert "product sheet of %1" not in cpp
    assert "Clothes plates queued" in cpp
    assert "last_clothes_only_dest" in cpp
    assert "last_clothes_only_dest" in header or "lastClothesOnlyDest_" in header
    assert "setMinimumContentsLength(10)" in cpp
    assert "look_complete" in cpp
    assert "completeLookFromPresent" in cpp
    assert "Complete look" in cpp
    assert "garment_shrinkwrap" in cpp
    assert "Shrink-wrap to body" in cpp
    garments = cpp[cpp.find("case StageId::Garments") :]
    assert "generateRequested" in garments
    assert "t2i" in garments


def test_mainwindow_forwards_clothes_only_task_command() -> None:
    cpp = _write("qt_ui/MainWindow.cpp")
    # Found by NAME, not by file: these 200 lines moved out of MainWindow.cpp into their own
    # translation unit, and a test that spelled the filename broke on a refactor that changed no
    # behaviour at all.
    builder = definition_body("buildWorkerGenerationRequest")
    assert "clothes_only" in builder
    assert "look_complete" in builder
    assert "input_image" in builder
    submit = cpp[cpp.find("void MainWindow::submitStudioGenerationRequest") : cpp.find("void MainWindow::syncStudioPreviewsFromQueue")]
    assert "input_image" in submit
    assert "i2i" in submit
    assert "loras" in submit
    assert "model_family" in submit
