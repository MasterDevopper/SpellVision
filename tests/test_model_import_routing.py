"""Where an imported file lands, and what must never be filed as a model.

`dest_subdir` matches on substrings of the FILENAME, and a workflow is named after the model it
drives -- so "Krea2 Two Image Edit v1.2.json" hit the krea2 rule and was copied into
models/diffusion_models/, where it later showed up as garbage in ComfyUI's loader lists. Anything
without a matching token fell through to "checkpoints".

This is not an edge case: a Civitai model of type "Workflows" ships a .json, and a checkpoint
version routinely bundles its workflow next to the weights.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_import import dest_subdir, is_model_file  # noqa: E402


@pytest.mark.parametrize(
    "filename",
    [
        "Krea2 Two Image Edit v1.2.json",
        "loxsUtopicWorldKrea2_v10BF16.json",
        "workflow.zip",
        "notes.txt",
        "preview.png",
    ],
)
def test_a_non_model_file_never_lands_in_a_loader_directory(filename):
    assert not is_model_file(filename)
    assert dest_subdir("Checkpoint", filename) == "workflows"


def test_the_family_token_no_longer_captures_a_workflow():
    """The specific regression: the krea2 rule fires on any filename containing "krea2", and a
    workflow named after the model contains it."""
    assert dest_subdir("Workflows", "Krea2 Two Image Edit v1.2.json") != "diffusion_models"


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("loxsUtopicWorldKrea2_v10BF16.safetensors", "diffusion_models"),
        ("qwen_image_vae.safetensors", "vae"),
        ("some_lora.safetensors", "loras"),
        ("loxsUtopicWorldKrea2_v10BF16_txt.safetensors", "text_encoders"),
        ("4x-UltraSharp.pth", "upscale_models"),
    ],
)
def test_real_model_files_still_route_where_they_did(filename, expected):
    assert is_model_file(filename)
    assert dest_subdir("Checkpoint", filename) == expected


def test_an_unrecognised_model_file_still_falls_back_to_its_declared_type():
    assert dest_subdir("LORA", "mystery.safetensors") == "loras"
    assert dest_subdir("Checkpoint", "mystery.safetensors") == "checkpoints"
