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


# --- a re-placed identical weight is not a second copy ----------------------------------------


def test_placing_an_identical_weight_returns_the_existing_one(tmp_path):
    """`X_1.safetensors`, then `X_2`, each a full multi-GB copy of a weight already in the
    library. The never-overwrite rule is right; applying it to bytes that are already there is
    what turned a cache eviction into disk consumption."""
    source = tmp_path / "cache" / "m.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"the same weights")
    root = tmp_path / "models"

    first = placement.place(source, root, kind="checkpoint", move=False)
    second = placement.place(source, root, kind="checkpoint", move=False)

    assert first == second
    assert [p.name for p in (root / "checkpoints").iterdir()] == ["m.safetensors"]


def test_a_different_weight_with_the_same_name_still_gets_a_suffix(tmp_path):
    """The exception is byte-identity, not name-identity. A DIFFERENT file must never overwrite
    the one the user may be rendering with right now."""
    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "checkpoints" / "m.safetensors").write_bytes(b"the original")

    source = tmp_path / "cache" / "m.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"something else entirely")

    placed = placement.place(source, root, kind="checkpoint", move=False)
    assert placed.name == "m_1.safetensors"
    assert (root / "checkpoints" / "m.safetensors").read_bytes() == b"the original"


def test_move_false_leaves_the_source_where_it_is(tmp_path):
    """A cache hit is placed with move=False so the asset cache keeps its copy."""
    source = tmp_path / "cache" / "m.safetensors"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"w")
    placement.place(source, tmp_path / "models", kind="checkpoint", move=False)
    assert source.exists()
