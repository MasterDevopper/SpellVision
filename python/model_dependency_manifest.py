"""Component dependency manifest — DATA for the Component Auto-Population System (Doc 19 §6).

This is the *manifest-as-data* half of the system: per family, per component slot, it declares
the resolution rules as plain data (no imperative branching, no `if family == ...`). The generic
engine in `component_resolver.py` interprets these rows; adding a model is a new manifest row, not
a code change (the explicit anti-god-file constraint).

Ground truth: every rule here is a lossless reduction of the battle-tested worker-side resolvers
(`_sv_core_wan_vae_name` / `_wan_vae_version_marker` / `_wan_vae_preference` /
`_sv_core_wan_clip_vision_name` in `worker_service.py`), which stay wired as the runtime backstop.
The equivalence gate asserts the engine driven by this data reproduces those resolvers byte-for-byte.

Schema (per slot):
    required            : bool           -- present in the completed stack's required set
    optional            : bool           -- resolved if present, omitted if absent (unless required_for hits)
    applies_to_tasks    : [str] | None   -- limit the slot to certain tasks (e.g. clip_vision -> i2v only); None = all
    required_for        : {variant?, task?} | None  -- promotes an optional slot to required when the probe matches
    explicit_keys       : [str]          -- request/stack keys whose value (if on disk) wins outright
    comfy_class/input   : str            -- the /object_info combo the runtime choices come from
    variant_detection   : {order:[{variant, any_tokens:[...]}], default} | None -- filename->variant probe
    preferred_by_variant: {variant: [filenames]} | None  -- version-ranked preference order
    preferred           : [filenames] | None             -- flat preference order (non-variant slots)
    valid_predicate     : {all_of?:[tok], any_of?:[rule]} -- a choice is "valid" if this matches its lowercased name
    baked_in            : bool           -- component ships inside the checkpoint (SDXL vae); absent-on-disk is valid
"""
from __future__ import annotations

from typing import Any


# --- reusable predicate/preference fragments (data, referenced by rows below) -----------------

# _wan_vae_version_marker: 2.2 tokens (or noise-half) win, then 2.1 tokens, else "" (-> 2.2 order).
_WAN_VAE_VARIANT_DETECTION: dict[str, Any] = {
    "order": [
        {"variant": "2.2", "any_tokens": ["wan2.2", "wan_2.2", "wan-2.2", "wan22", "high_noise", "low_noise"]},
        {"variant": "2.1", "any_tokens": ["wan2.1", "wan_2.1", "wan-2.1", "wan21", "i2v_480p_14b", "i2v_720p_14b"]},
    ],
    "default": "2.2",  # marker "" falls back to the 2.2-first order (unchanged legacy behavior)
}

# _wan_vae_preference: exact per-variant order from the resolver.
_WAN_VAE_PREFERRED_BY_VARIANT: dict[str, list[str]] = {
    "2.1": ["wan_2.1_vae.safetensors", "wan2.1_vae.safetensors", "wan2.2_vae.safetensors", "wan_2.2_vae.safetensors"],
    "2.2": ["wan2.2_vae.safetensors", "wan_2.2_vae.safetensors", "wan2.1_vae.safetensors", "wan_2.1_vae.safetensors"],
}


COMPONENT_MANIFEST: dict[str, dict[str, Any]] = {
    # ============================ Wan (2.1 single-model + 2.2 dual-noise) ============================
    # Slot list mirrors video_family_contracts["wan"].{required,optional}_components. VAE + clip_vision
    # carry the resolver rules the equivalence gate checks; text_encoder is the family default.
    "wan": {
        "slots": {
            "vae": {
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],          # _sv_core_wan_vae_name reads stack only
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "variant_detection": _WAN_VAE_VARIANT_DETECTION,
                "preferred_by_variant": _WAN_VAE_PREFERRED_BY_VARIANT,
                # generic fallback (_sv_core_wan_vae_name step 6): "wan" AND "vae" in the name.
                "valid_predicate": {"all_of": ["wan", "vae"]},
            },
            "text_encoder": {
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5_xxl_fp16.safetensors"],
                "valid_predicate": {"all_of": ["umt5"]},
            },
            "clip_vision": {
                "required": False,
                "optional": True,
                "applies_to_tasks": ["i2v"],           # never wired for t2v
                "required_for": {"variant": "2.1", "task": "i2v"},  # Wan 2.1 i2v needs it; 2.2 i2v omits
                "explicit_keys": ["clip_vision", "clip_vision_path"],
                "explicit_sources": ["req", "stack"],   # _sv_core_wan_clip_vision_name reads req then stack
                "comfy_class": "CLIPVisionLoader", "comfy_input": "clip_name",
                "variant_detection": _WAN_VAE_VARIANT_DETECTION,   # reuse the same version probe
                "preferred": ["clip_vision_h.safetensors", "clip_vision_vit_h.safetensors"],
                # _sv_core_wan_clip_vision_name step 5: "clip_vision_h" OR ("vit" AND "_h").
                "valid_predicate": {"any_of": [{"all_of": ["clip_vision_h"]}, {"all_of": ["vit", "_h"]}]},
                "omit_if_absent": True,
            },
        },
    },
    # ==================================== SDXL (all-in-one) ====================================
    # from_single_file loads ONE safetensors blob (memory_optimization.py:741): VAE baked in, no
    # separate clip_vision / text_encoder. No Wan-style resolver exists -> gate is "valid stack".
    "sdxl": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,      # the user-selected checkpoint IS the input, not a resolved companion
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "vae": {
                "required": False,
                "optional": True,
                "baked_in": True,               # VAE ships inside the checkpoint; absent-on-disk is valid
                "explicit_keys": ["vae_path", "vae"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["sdxl_vae.safetensors", "sdxl.vae.safetensors"],
                "valid_predicate": {"all_of": ["vae"]},
                "omit_if_absent": True,
            },
        },
    },
}


def family_manifest(family: str) -> dict[str, Any] | None:
    """Return the manifest row for a family, or None if unmanifested (-> engine floors on contract slots)."""
    return COMPONENT_MANIFEST.get(str(family or "").strip().lower())
