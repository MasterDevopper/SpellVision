"""Gates for two 'don't ship a footgun' worker fixes surfaced by the accel-LoRA validation:

  1. TeaCache class selector must SKIP the wrapper-topology nodes (WanVideoTeaCache / HyVideoTeaCache)
     -- they output TEACACHEARGS, not MODEL, and inserting one into the native-core model chain makes
     ComfyUI reject the whole graph (HTTP 400). With only wrapper nodes present the selector must return
     None so the enable flag degrades to "no TeaCache" (valid graph), not "broken graph".
  2. _is_split_video_stack_request must route a wan_dual_noise stack (no primary model) to the split
     path, the same as split_stack -- otherwise it raises in _native_video_model_reference before the
     dual-noise builder ever runs.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import worker_service as ws  # noqa: E402


def _oi(*class_names):
    # minimal object_info: each class present with an empty input schema
    return {c: {"input": {"required": {}}} for c in class_names}


# --------------------------------------------------------------------------- Fix 1: TeaCache selector

def test_teacache_class_none_when_only_wrapper_nodes():
    """Only the wrapper-family TeaCache nodes present -> None (incompatible with the native graph)."""
    oi = _oi("WanVideoTeaCache", "HyVideoTeaCache", "UNETLoader", "KSamplerAdvanced")
    assert ws._spellvision_teacache_class(oi) is None


def test_teacache_class_selects_standalone_when_present():
    """The compatible standalone model-wrapper node is selected (explicit-name loop)."""
    assert ws._spellvision_teacache_class(_oi("TeaCache", "WanVideoTeaCache")) == "TeaCache"
    assert ws._spellvision_teacache_class(_oi("TeaCacheForVidGen")) == "TeaCacheForVidGen"


def test_teacache_class_fallback_still_finds_compatible_nonstandard_name():
    """A compatible node whose name contains 'teacache' but is NOT a *VideoTeaCache wrapper is still
    found by the substring fallback (the exclusion is narrow, not a blanket 'teacache' skip)."""
    assert ws._spellvision_teacache_class(_oi("MyTeaCacheModelNode")) == "MyTeaCacheModelNode"


def test_apply_teacache_only_wrapper_nodes_inserts_nothing():
    """TeaCache ENABLED + only wrapper nodes present -> no TeaCache node inserted, no raise, valid graph;
    teacache_available flagged False. (The whole point: enable degrades to no-op, not HTTP-400 graph.)"""
    prompt = {
        "4": {"class_type": "UNETLoader", "inputs": {}},
        "8": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["4", 0]}},
    }
    req = {"teacache_enabled": True, "teacache_profile": "balanced"}
    oi = _oi("WanVideoTeaCache", "UNETLoader", "KSamplerAdvanced")
    out = ws._spellvision_apply_teacache_to_native_video_prompt(prompt, req, oi)
    inserted = [nid for nid, n in out.items() if "teacache" in str(n.get("class_type") or "").lower().replace("_", "")]
    assert inserted == [], f"no TeaCache node may be inserted when only wrapper nodes exist, got {inserted}"
    assert req.get("teacache_available") is False, "teacache_available must be False when no compatible node exists"
    # the sampler still reads the raw UNET -- graph untouched
    assert out["8"]["inputs"]["model"] == ["4", 0]


# --------------------------------------------------------------------------- Fix 2: dual-noise routing

def _dual_noise_req_no_model():
    return {
        "command": "t2v",
        "native_video_stack_kind": "wan_dual_noise",
        "video_model_stack": {
            "stack_kind": "wan_dual_noise",
            "high_noise_path": "D:/AI_ASSETS/models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
            "low_noise_path": "D:/AI_ASSETS/models/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
        },
        # NO "model" / primary_path -- the case that used to raise before the early-return.
    }


def test_dual_noise_routes_to_split_without_primary_model():
    """wan_dual_noise with no primary model -> routed to the split path (True), NOT raising in
    _native_video_model_reference."""
    assert ws._is_split_video_stack_request(_dual_noise_req_no_model()) is True


def test_split_stack_still_routes():
    # unchanged behavior for the original split_stack kind
    assert ws._is_split_video_stack_request({"native_video_stack_kind": "split_stack"}) is True
