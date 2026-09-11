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


# --------------------------------------------------------------------------- generic fallback observability

def test_generic_fallback_warns_and_marks_route(monkeypatch, caplog):
    """The generic unknown-family path must emit a WARNING naming the family + reasoned defaults and mark
    native_video_route='generic_fallback'. That path is normally unreachable (the readiness gate blocks
    non-production families before it), so no-op the gate to simulate a future production family with no
    dedicated builder. The build then raises on the missing stack -- AFTER the observability fires."""
    import logging as _logging
    import pytest as _pytest
    import native_video_graphs as nvg

    monkeypatch.setattr(ws, "_raise_if_unvalidated_native_video_family", lambda *a, **k: None)
    monkeypatch.setattr(nvg, "_raise_if_unvalidated_native_video_family", lambda *a, **k: None)
    req = {"command": "t2v", "resolved_native_video_family": "zzz_future_family"}
    with caplog.at_level(_logging.WARNING):
        with _pytest.raises(RuntimeError):  # no stack -> raises, but the warning + marker fire first
            ws._build_native_split_video_prompt(req, {}, command="t2v", family="zzz_future_family", job_id="jt")

    msgs = [r.getMessage() for r in caplog.records]
    assert any("GENERIC fallback" in m and "not validated" in m and "zzz_future_family" in m for m in msgs), \
        f"generic-fallback warning must fire naming the family + reasoned defaults; got {msgs}"
    assert any("cfg=4.5" in m and "sampler=euler" in m for m in msgs), f"warning must name the applied defaults; got {msgs}"
    assert req.get("native_video_route") == "generic_fallback", "the fallback must mark native_video_route for the result payload"


def test_diffusers_flux_uses_unet_loader_when_visible(monkeypatch) -> None:
    import native_image_graphs as nig

    monkeypatch.setattr(nig, "_flux_checkpoint_incompatible_reason", lambda _p: "DIFFUSERS-format")
    graph = _flux()
    assert graph["1"]["class_type"] == "UNETLoader"
    assert graph["1"]["inputs"]["unet_name"] == "fluxmania_kreamania.safetensors"


def test_diffusers_flux_still_refuses_when_unet_is_invisible(monkeypatch) -> None:
    import native_image_graphs as nig
    import pytest

    monkeypatch.setattr(nig, "_flux_checkpoint_incompatible_reason", lambda _p: "DIFFUSERS-format transformer")
    oi = {
        "CheckpointLoaderSimple": F_OI["CheckpointLoaderSimple"],
        "UNETLoader": {"input": {"required": {"unet_name": [[], {}]}}},
    }
    req = {"command": "t2i", "model": F_MODEL, "prompt": "x", "width": 1024, "height": 1024, "seed": 1}
    with pytest.raises(RuntimeError, match="DIFFUSERS-format"):
        ws._build_flux_image_prompt(req, oi, "jt", F_RES)


def test_quantized_diffusers_flux_is_refused_even_if_unet_is_visible(tmp_path) -> None:
    """Live hole: fluxmania_legacy is transformer_blocks + qweight. UNETLoader still 400s."""
    import json
    import struct

    import native_image_graphs as nig
    import pytest

    keys = {
        "single_transformer_blocks.0.norm.linear.qweight": {
            "dtype": "U8",
            "shape": [1],
            "data_offsets": [0, 1],
        },
        "transformer_blocks.0.attn.to_q.qweight": {
            "dtype": "U8",
            "shape": [1],
            "data_offsets": [1, 2],
        },
    }
    raw = json.dumps(keys).encode("utf-8")
    path = tmp_path / "fluxmania_legacy.safetensors"
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\x00")
    reason = nig._flux_checkpoint_incompatible_reason(str(path))
    assert reason is not None
    assert "quantized" in reason.lower()
    oi = {
        "CheckpointLoaderSimple": F_OI["CheckpointLoaderSimple"],
        "UNETLoader": {"input": {"required": {"unet_name": [["fluxmania_legacy.safetensors"], {}]}}},
    }
    req = {
        "command": "t2i",
        "model": str(path),
        "prompt": "x",
        "width": 1024,
        "height": 1024,
        "seed": 1,
    }
    with pytest.raises(RuntimeError, match="quantized"):
        nig._build_flux_image_prompt(req, oi, "jt", F_RES)
