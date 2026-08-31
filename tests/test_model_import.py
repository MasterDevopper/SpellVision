from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_import import dest_filename, dest_subdir, family_hints, import_model_choices, inspect_model_url, noise_role


def test_dest_and_roles() -> None:
    assert dest_subdir("LORA") == "loras"
    assert dest_subdir("Upscaler") == "upscale_models"
    assert dest_subdir("", "4x-UltraSharp.pth") == "upscale_models"
    assert dest_subdir("Checkpoint", "qwen_image_vae.safetensors") == "vae"
    assert dest_subdir("Checkpoint", "insight_a1_txt.safetensors") == "text_encoders"
    assert dest_subdir("Checkpoint", "insight_a1.safetensors") == "checkpoints"
    assert family_hints("insight", "A1", "insight_a1.safetensors", base_model="Anima") == ["anima"]
    assert family_hints("insight", "1", "insight_1.safetensors", base_model="Illustrious") == ["illustrious"]
    assert family_hints("insight", "A1", "insight_a1.safetensors") == []
    assert noise_role("wan2.2_i2v_high_noise_14B.safetensors") == "high"
    assert noise_role("wan2.2_i2v_low_noise_14B.safetensors") == "low"
    assert "anima" in family_hints("Bowsette Anima v1")
    assert "illustrious" in family_hints("style illustrious XL")


def test_inspect_lists_versions_and_pairs() -> None:
    payload = {
        "name": "Demo Dual",
        "type": "Checkpoint",
        "modelVersions": [
            {
                "id": 11,
                "name": "v1 Anima",
                "files": [
                    {"name": "demo_high_noise.safetensors", "sizeKB": 10, "downloadUrl": "https://civitai.com/api/download/models/11?type=high"},
                    {"name": "demo_low_noise.safetensors", "sizeKB": 10, "downloadUrl": "https://civitai.com/api/download/models/11?type=low"},
                ],
            },
            {
                "id": 17,
                "name": "v17 Illustrious",
                "files": [
                    {"name": "demo_v17_illustrious.safetensors", "sizeKB": 20, "downloadUrl": "https://civitai.com/api/download/models/17"},
                ],
            },
        ],
    }
    catalog = inspect_model_url(
        "https://civitai.com/models/99/demo",
        civitai_get=lambda url: payload,
    )
    assert catalog["ok"] is True
    names = {row["filename"] for row in catalog["choices"]}
    assert "demo_high_noise.safetensors" in names
    assert "demo_v17_illustrious.safetensors" in names
    high = next(row for row in catalog["choices"] if row["noise_role"] == "high")
    assert high["pair_required"] is True
    assert high["pair_with"]
    v17 = next(row for row in catalog["choices"] if "v17" in row["filename"])
    assert "illustrious" in v17["family_hints"]


def test_insight_anima_vs_illustrious_uses_base_model() -> None:
    payload = {
        "name": "insight",
        "type": "Checkpoint",
        "modelVersions": [
            {
                "id": 3228379,
                "name": "A1",
                "baseModel": "Anima",
                "files": [
                    {"name": "qwen_image_vae.safetensors"},
                    {"name": "insight_a1_txt.safetensors"},
                    {"name": "insight_a1.safetensors"},
                ],
            },
            {
                "id": 2832979,
                "name": "1",
                "baseModel": "Illustrious",
                "files": [{"name": "insight_1.safetensors"}],
            },
        ],
    }
    anima = inspect_model_url(
        "https://civitai.red/models/2520599/insight?modelVersionId=3228379",
        civitai_get=lambda url: payload,
    )
    illus = inspect_model_url(
        "https://civitai.red/models/2520599/insight?modelVersionId=2832979",
        civitai_get=lambda url: payload,
    )
    anima_files = {row["filename"]: row for row in anima["choices"]}
    illus_files = {row["filename"]: row for row in illus["choices"]}
    assert set(anima_files) == {"qwen_image_vae.safetensors", "insight_a1_txt.safetensors", "insight_a1.safetensors"}
    assert anima_files["insight_a1.safetensors"]["family_hints"] == ["anima"]
    assert anima_files["insight_a1.safetensors"]["dest_subdir"] == "checkpoints"
    assert anima_files["qwen_image_vae.safetensors"]["dest_subdir"] == "vae"
    assert anima_files["insight_a1_txt.safetensors"]["dest_subdir"] == "text_encoders"
    assert illus_files["insight_1.safetensors"]["family_hints"] == ["illustrious"]
    assert illus_files["insight_1.safetensors"]["dest_subdir"] == "checkpoints"
    assert "insight_1.safetensors" not in anima_files
    assert "insight_a1.safetensors" not in illus_files


def test_oversized_lora_three_families_no_filename_clash() -> None:
    payload = {
        "name": "OversizedShirt&Stockings",
        "type": "LORA",
        "modelVersions": [
            {"id": 3228232, "name": "Anima", "baseModel": "Anima",
             "files": [{"name": "OversizedANI_epoch_03.safetensors"}]},
            {"id": 1400339, "name": "IL", "baseModel": "Illustrious",
             "files": [{"name": "Oversized-000003.safetensors"}]},
            {"id": 688391, "name": "PONY", "baseModel": "Pony",
             "files": [{"name": "Oversized-000003.safetensors"}]},
        ],
    }
    rows = {}
    for vid in ("3228232", "1400339", "688391"):
        catalog = inspect_model_url(
            f"https://civitai.red/models/615814/x?modelVersionId={vid}",
            civitai_get=lambda url, _p=payload: _p,
        )
        assert len(catalog["choices"]) == 1
        row = catalog["choices"][0]
        rows[vid] = row
        assert row["dest_subdir"] == "loras"
    assert rows["3228232"]["family_hints"] == ["anima"]
    assert rows["1400339"]["family_hints"] == ["illustrious"]
    assert rows["688391"]["family_hints"] == ["pony"]
    assert rows["3228232"]["dest_filename"] == "OversizedANI_epoch_03_anima.safetensors"
    assert rows["1400339"]["dest_filename"] == "Oversized-000003_illustrious.safetensors"
    assert rows["688391"]["dest_filename"] == "Oversized-000003_pony.safetensors"
    assert dest_filename(rows["1400339"], "Oversized-000003.safetensors") != dest_filename(rows["688391"], "Oversized-000003.safetensors")


def test_import_pair_downloads_both(tmp_path: Path) -> None:
    catalog = inspect_model_url(
        "https://civitai.com/models/99/demo",
        civitai_get=lambda url: {
            "name": "Demo",
            "type": "Checkpoint",
            "modelVersions": [{
                "id": 11,
                "name": "v1",
                "files": [
                    {"name": "a_high_noise.safetensors", "downloadUrl": "high"},
                    {"name": "a_low_noise.safetensors", "downloadUrl": "low"},
                ],
            }],
        },
    )
    high = next(row for row in catalog["choices"] if row["noise_role"] == "high")

    class Fake:
        def __init__(self, ref: str):
            path = tmp_path / "cache" / f"{ref}.safetensors"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            self.local_path = str(path)

    result = import_model_choices(
        catalog,
        [high["choice_id"]],
        install_root=str(tmp_path / "models"),
        materialize=lambda ref, **kwargs: Fake(ref),
    )
    assert len(result["installed"]) == 2
    assert all(Path(path).is_file() for path in result["installed"])
