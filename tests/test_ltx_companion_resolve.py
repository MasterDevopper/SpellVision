"""Live 2026-09-10: LTX tab swapped the checkpoint then T3-blocked on text_encoder
and auto-filled LTX23_audio_vae (audio, not video)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from component_resolver import matches_predicate  # noqa: E402
from model_dependency_manifest import family_manifest  # noqa: E402


def test_ltx_vae_predicate_rejects_audio() -> None:
    pred = family_manifest("ltx")["slots"]["vae"]["valid_predicate"]
    assert matches_predicate("ltx23_video_vae_bf16.safetensors", pred)
    assert not matches_predicate("ltx23_audio_vae_bf16.safetensors", pred)


def test_ltx_text_encoder_predicate_accepts_gemma() -> None:
    pred = family_manifest("ltx")["slots"]["text_encoder"]["valid_predicate"]
    assert matches_predicate("comfy_gemma_3_12b_it.safetensors", pred)


def test_resolve_graph_model_names_rewrites_ltx_text_encoder_absolute_path() -> None:
    """Live 2026-09-10: four LTX submits wrote D:/.../comfy_gemma_3_12B_it.safetensors
    into LTXAVTextEncoderLoader.text_encoder. _resolve_graph_model_names skipped that
    key, so Comfy 400'd. Dest graphs exist; no mp4."""
    from comfy_prompt_client import _MODEL_FILE_INPUT_NAMES, _resolve_graph_model_names

    assert "text_encoder" in _MODEL_FILE_INPUT_NAMES
    catalog = r"ltx\comfy_gemma_3_12B_it.safetensors"
    object_info = {
        "LTXAVTextEncoderLoader": {
            "input": {
                "required": {
                    "text_encoder": [[catalog], {}],
                }
            }
        }
    }
    graph = {
        "4982": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": r"D:/AI_ASSETS/models/text_encoders/ltx/comfy_gemma_3_12B_it.safetensors",
            },
        }
    }
    _resolve_graph_model_names(graph, object_info)
    assert graph["4982"]["inputs"]["text_encoder"] == catalog
