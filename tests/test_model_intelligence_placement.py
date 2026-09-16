"""Where a downloaded weight belongs.

Today a download from the Models page lands in the asset cache and the library never shows it.
The mapping below mirrors ModelManagerPage::destSubdirForWeight so the C++ drop path and the
Python download path put the same file in the same place -- two resolvers for one question is the
defect Doc 50 rule 5 is about.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import placement


@pytest.mark.parametrize(
    "name,kind,expected",
    [
        ("anything.safetensors", "checkpoint", "checkpoints"),
        ("anything.safetensors", "lora", "loras"),
        ("anything.safetensors", "vae", "vae"),
        ("anything.safetensors", "text_encoder", "text_encoders"),
        ("anything.safetensors", "clip_vision", "clip_vision"),
        ("anything.safetensors", "embedding", "embeddings"),
        ("anything.safetensors", "upscaler", "upscale_models"),
        ("anything.safetensors", "controlnet", "controlnet"),
        ("anything.safetensors", "diffusion_model", "diffusion_models"),
        ("mystery.safetensors", None, "checkpoints"),
        ("some_lora_v1.safetensors", None, "loras"),
        ("sdxl_vae.safetensors", None, "vae"),
        ("4x-UltraSharp.pth", None, "upscale_models"),
    ],
)
def test_subdir_for(name, kind, expected):
    assert placement.subdir_for(Path(name), kind=kind) == expected


def test_place_moves_the_file_into_the_library(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    source = cache / "w.safetensors"
    source.write_bytes(b"weights")
    root = tmp_path / "models"
    landed = placement.place(source, root, kind="lora")
    assert landed == root / "loras" / "w.safetensors"
    assert landed.read_bytes() == b"weights"
    assert not source.exists()


def test_place_can_copy_instead_of_moving(tmp_path: Path):
    source = tmp_path / "w.safetensors"
    source.write_bytes(b"weights")
    landed = placement.place(source, tmp_path / "models", kind="lora", move=False)
    assert landed.exists()
    assert source.exists()


def test_place_never_overwrites_an_existing_weight(tmp_path: Path):
    root = tmp_path / "models"
    (root / "loras").mkdir(parents=True)
    (root / "loras" / "w.safetensors").write_bytes(b"the one already there")
    source = tmp_path / "w.safetensors"
    source.write_bytes(b"the new one")
    landed = placement.place(source, root, kind="lora")
    assert (root / "loras" / "w.safetensors").read_bytes() == b"the one already there"
    assert landed.name != "w.safetensors"
    assert landed.read_bytes() == b"the new one"
