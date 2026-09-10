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
