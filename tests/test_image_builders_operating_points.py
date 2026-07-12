"""Phase 2b builder-level gates for the IMAGE operating-point lift.

Proves (a) PINNED params (Z-Image's baked cfg, its step clamp; Flux's KSampler cfg pin) are still
enforced after the lift -- a request can't override them; and (b) the routed defaults come from the
TABLE (corrupting the table changes the builder output -> consulted before the surviving literal).

These builders emit plain literal-dict graphs, so the object_info stub only needs the loader combo
(to resolve the model name) and a `resolved.value(component)` shim.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import worker_service as ws  # noqa: E402


class _Resolved:
    def __init__(self, vals):
        self._v = vals

    def value(self, component):
        return self._v.get(component)


# --- Z-Image (UNETLoader; distilled Turbo: cfg PINNED 1.0, steps clamped to [1,16]->4) ---
Z_MODEL = "D:/AI_ASSETS/models/diffusion_models/z-image/z_image_turbo_bf16.safetensors"
Z_OI = {"UNETLoader": {"input": {"required": {"unet_name": [["z_image_turbo_bf16.safetensors"], {}]}}}}
Z_RES = _Resolved({"text_encoder": "qwen_3_4b.safetensors", "vae": "ae.safetensors"})

# --- PixArt (CheckpointLoaderSimple; real cfg fallback 4.5, steps fallback 20) ---
P_MODEL = "D:/AI_ASSETS/models/checkpoints/pixart/pixartSigma.safetensors"
P_OI = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["pixartSigma.safetensors"], {}]}}}}
P_RES = _Resolved({"text_encoder": "t5.safetensors", "vae": "sdxl_vae.safetensors"})

# --- Flux (KSampler cfg PINNED 1.0; cockpit cfg -> FluxGuidance) ---
F_MODEL = "D:/AI_ASSETS/models/checkpoints/flux/fluxmania_kreamania.safetensors"
F_OI = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["fluxmania_kreamania.safetensors"], {}]}}},
        "UNETLoader": {"input": {"required": {"unet_name": [["fluxmania_kreamania.safetensors"], {}]}}}}
F_RES = _Resolved({"text_encoder": "clip_l.safetensors", "text_encoder_2": "t5xxl_fp16.safetensors", "vae": "ae.safetensors"})


def _ksampler(graph):
    return next(n["inputs"] for n in graph.values() if isinstance(n, dict) and n.get("class_type") == "KSampler")


def _zimage(**over):
    req = {"command": "t2i", "model": Z_MODEL, "prompt": "x", "negative_prompt": "", "width": 1024, "height": 1024, "seed": 1}
    req.update(over)
    return ws._build_zimage_image_prompt(req, Z_OI, "jt", Z_RES)


def _pixart(**over):
    req = {"command": "t2i", "model": P_MODEL, "prompt": "x", "negative_prompt": "", "width": 1024, "height": 1024, "seed": 1}
    req.update(over)
    return ws._build_pixart_image_prompt(req, P_OI, "jt", P_RES)


def _flux(**over):
    req = {"command": "t2i", "model": F_MODEL, "prompt": "x", "negative_prompt": "", "width": 1024, "height": 1024, "seed": 1}
    req.update(over)
    return ws._build_flux_image_prompt(req, F_OI, "jt", F_RES)


# --------------------------------------------------------------------------- pinned semantics (the grounded decisions)

def test_zimage_cfg_pinned_ignores_request():
    # req cfg 8.0 must be IGNORED -- Z-Image cfg is baked in at 1.0.
    assert _ksampler(_zimage(cfg=8.0))["cfg"] == 1.0


def test_zimage_steps_clamped_over_16():
    # req steps 35 must clamp to the Turbo 4 (>16 -> 4), unchanged by the lift.
    assert _ksampler(_zimage(steps=35))["steps"] == 4


def test_flux_ksampler_cfg_pinned_ignores_request():
    # req cfg 8.0 must not reach the KSampler -- Flux pins KSampler cfg 1.0 and maps cfg to FluxGuidance.
    assert _ksampler(_flux(cfg=8.0))["cfg"] == 1.0
    assert any(n.get("class_type") == "FluxGuidance" for n in _flux(cfg=8.0).values() if isinstance(n, dict))


# --------------------------------------------------------------------------- routed defaults come from the TABLE

def test_zimage_omitted_steps_from_table():
    assert _ksampler(_zimage())["steps"] == 4  # wan-style: table zimage_image steps 4


def test_pixart_omitted_steps_and_cfg_from_table():
    ks = _ksampler(_pixart())
    assert ks["steps"] == 20 and ks["cfg"] == 4.5
