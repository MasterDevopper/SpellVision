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

# Precision-as-variant, probed from the transformer's REAL dtype (NOT its filename). The Flux-A
# thesis outcome, now the SHARED precision detector for every family whose companion encoders ship
# in fp8/fp16 flavors (Flux T5, Hunyuan llava, ...). probe_source="primary_dtype" ->
# _primary_dtype_probe reads the transformer safetensors header; the tokens match that probe's
# OUTPUT strings ("f8_e4m3"/"bf16"/"f16"/...), which is why bare "f8"/"e4m3"/"f16" appear rather
# than filename forms like "e4m3fn". default="fp16" is the safe superset (an fp16 encoder runs with
# an fp8-cast transformer; the reverse degrades) AND the graceful fallback when the header is
# unreadable (e.g. a .gguf transformer -> probe returns "" -> default fp16).
_PRIMARY_DTYPE_PRECISION: dict[str, Any] = {
    "probe_source": "primary_dtype",
    "order": [
        {"variant": "fp8", "any_tokens": ["f8", "e4m3", "e5m2", "fp8"]},
        {"variant": "fp16", "any_tokens": ["f16", "bf16", "fp16"]},
    ],
    "default": "fp16",
}

# LLaVA-Llama-3 (HunyuanVideo's LLM text encoder), precision-ranked -- same shape as the T5 order.
_LLAVA_PREFERRED_BY_VARIANT: dict[str, list[str]] = {
    "fp8": ["llava_llama3_fp8_scaled.safetensors", "llava_llama3_fp16.safetensors"],
    "fp16": ["llava_llama3_fp16.safetensors", "llava_llama3_fp8_scaled.safetensors"],
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
                "source": {
                    "hf_repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                    "path": "split_files/vae/wan_2.1_vae.safetensors",
                },
            },
            "text_encoder": {
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5_xxl_fp16.safetensors"],
                "valid_predicate": {"all_of": ["umt5"]},
                "source": {
                    "hf_repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
                    "path": "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                },
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
                "source": {
                    "hf_repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
                    "path": "split_files/clip_vision/clip_vision_h.safetensors",
                },
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
    # ============================ Flux (transformer + companions) ============================
    # First NEW consumer of the engine (Doc 19 model build-order #3). No prior worker resolver to
    # equivalence-check -- this is correctness-against-known-right-answer. The thesis test: Flux's
    # T5 PRECISION-MATCH (fp8 transformer -> fp8 T5, fp16/bf16 -> fp16 T5) reduces to existing
    # primitives + ONE generic engine extension (variant_detection.probe_source="primary_dtype"),
    # NOT Flux-specific logic. A Flux single-file checkpoint (fluxmania_*) carries transformer(+vae)
    # but NOT the text encoders -- they are passed as local companions (clip_l + T5), which is why
    # local assembly avoids the gated FLUX.1-dev repo (STEP 0 verified).
    "flux": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,      # the user-selected Flux transformer/checkpoint IS the input
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "vae": {
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["ae.safetensors", "ae.sft", "flux_vae.safetensors"],
                # "ae." alone also matches "sdxl_vae." / "wan_2.1_vae." (since "vae" contains "ae"),
                # so exclude "vae" from that branch; the explicit flux-vae branch still matches "flux_vae".
                "valid_predicate": {"any_of": [{"all_of": ["ae."], "none_of": ["vae"]}, {"all_of": ["flux", "vae"]}]},
            },
            "text_encoder": {          # CLIP-L (Flux's first text encoder)
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "clip_l_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["clip_l.safetensors"],
                "valid_predicate": {"all_of": ["clip_l"]},
            },
            "text_encoder_2": {        # T5-XXL, PRECISION-MATCHED to the transformer (the thesis test)
                "required": True,
                "explicit_keys": ["text_encoder_2_path", "text_encoder_2", "t5_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "variant_detection": _PRIMARY_DTYPE_PRECISION,   # dtype-probe (shared; Flux-A canonical)
                "preferred_by_variant": {
                    "fp8": ["t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"],
                    "fp16": ["t5xxl_fp16.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"],
                },
                # "t5xxl" (Flux/SD3) NOT "umt5" (Wan) -- the underscore in "umt5_xxl" means it does
                # not contain the substring "t5xxl", so this correctly excludes the Wan encoder.
                "valid_predicate": {"all_of": ["t5xxl"]},
            },
        },
    },
    # ===================== PixArt-Sigma (T2I) -- first of the 4 unregistered image families =====================
    # Grounded live + render-proven (STEP 0): transformer-only DiT (header blocks.0.attn.*, metadata
    # modelspec.architecture=pixart-sigma, F16), loads via CheckpointLoaderSimple. Companions: T5-XXL
    # (the SAME t5xxl Flux uses, precision-matched to the transformer) + the SDXL 4-ch VAE (NOT Flux's
    # ae). The graph is a per-family sibling builder (_build_pixart_image_prompt: CLIPLoader(type=pixart)
    # + CLIPTextEncodePixArtAlpha + real CFG, not the Flux DualCLIP+FluxGuidance graph) -- but this
    # resolver row is pure data like every other. Canonical key "pixart" everywhere (no alias trap).
    "pixart": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "text_encoder": {          # T5-XXL (PixArt's only text encoder), precision-matched to the transformer
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "t5_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "variant_detection": _PRIMARY_DTYPE_PRECISION,   # dtype-probe (shared; same as Flux's T5)
                "preferred_by_variant": {
                    "fp8": ["t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"],
                    "fp16": ["t5xxl_fp16.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"],
                },
                "valid_predicate": {"all_of": ["t5xxl"]},   # excludes umt5 (Wan) -- no "t5xxl" substring
            },
            "vae": {                   # SDXL 4-ch VAE -- PixArt uses the SD/SDXL VAE, NOT Flux's ae
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                # research wanted sdxl-vae-fp16-fix (NOT on disk); only sdxl_vae is present -> falls to it.
                "preferred": ["sdxl-vae-fp16-fix.safetensors", "sdxl_vae.safetensors"],
                # {sdxl AND vae} matches sdxl_vae WITHOUT grabbing Flux's "ae." or Wan's "*_vae" (no "sdxl").
                "valid_predicate": {"all_of": ["sdxl", "vae"]},
            },
        },
    },
    # ===================== Lumina Image 2.0 (T2I) -- 2nd unregistered image family; Gemma-collision dress rehearsal =====================
    # Grounded live + render-proven (STEP 0): lumina_2.safetensors is an ALL-IN-ONE Lumina 2.0 DiT
    # (cap_embedder/context_refiner) with BAKED VAE + BAKED gemma2_2b. So NO vae slot (the builder uses
    # CheckpointLoaderSimple's baked VAE, like SDXL). Gemma IS resolved (resolver-driven separate
    # CLIPLoader(type=lumina2) -- the pass's crux + generalizes to a transformer-only Lumina; baked-CLIP
    # and separate-CLIPLoader render identically). Graph: ModelSamplingAuraFlow(shift) + CLIPTextEncodeLumina2
    # + res_multistep -- a distinct sibling builder, NOT the Flux/PixArt graph.
    #   THE LANDMINE (proven two-sided): naive {all_of:["gemma"]} grabs Lumina's gemma_2_2b AND LTX's
    #   gemma_3_12B. Size-specific {all_of:["gemma_2"], none_of:["gemma_3","12b"]} matches ONLY
    #   gemma_2_2b_fp16. (Keyed on "gemma_2" NOT "2b" -- "2b" is a substring of "12b". Note for Qwen.)
    #   LTX keeps its gemma_3_12B by construction: LTX's gemma is a HARDCODED template value
    #   (ltx_av_native.json), not resolver-driven -- the predicate can't touch it.
    "lumina": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "text_encoder": {          # Gemma-2-2B (Lumina's encoder), SIZE-SPECIFIC to exclude LTX's gemma_3_12B
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "gemma_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["gemma_2_2b_fp16.safetensors", "gemma_2_2b.safetensors"],
                "valid_predicate": {"all_of": ["gemma_2"], "none_of": ["gemma_3", "12b"]},
            },
            # NO vae slot -- baked into the all-in-one checkpoint (CheckpointLoaderSimple supplies it).
        },
    },
    # ===================== Z-Image Turbo (T2I) -- 3rd image family; FIRST split-stack (UNETLoader) =====================
    # Grounded live + render-proven (STEP 0): z_image_turbo_bf16 is a transformer-only DiT (cap_embedder,
    # Lumina-derived, BF16) in diffusion_models/ -> loads via UNETLoader (NOT CheckpointLoaderSimple).
    # Companions are EXTERNAL: Qwen-3-4B encoder + the Flux ae VAE (official; NOT the name-obvious
    # zImage_vae footgun). Distilled Turbo: builder pins cfg~1.0 + ~8 steps + shift 3. BASE bf16 only --
    # SVDQ/int4/nunchaku/GGUF quant variants are the deferred quant-loader subsystem arc, NOT here.
    #   LANDMINE 1 (Qwen collision): naive {all_of:["qwen"]} grabs qwen_2.5_vl_7b (Qwen-Image) AND
    #   qwen_3_4b (Z-Image). {all_of:["qwen_3_4b"]} matches ONLY qwen_3_4b -- the full distinguishing
    #   token (avoids the 2b-in-12b substring trap; excludes a future Anima qwen_3_0.6b too).
    #   LANDMINE 2 (VAE): {all_of:["ae."], none_of:["vae"]} = Flux ae, excludes zImage_vae / wan / sdxl /
    #   qwen_image_vae (all contain "vae"). Z-Image shares Flux's ae -- per-family rows, both resolve it.
    "z_image": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "text_encoder": {          # Qwen-3-4B, size-specific to exclude Qwen-Image's 2.5-VL-7B + Anima's 0.6b
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "qwen_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["qwen_3_4b.safetensors"],
                "valid_predicate": {"all_of": ["qwen_3_4b"]},
            },
            "vae": {                   # Flux ae (official) -- NOT zImage_vae/wan/qwen_image_vae
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["ae.safetensors", "ae.sft"],
                # "ae." also matches "*vae*" (vae contains ae); none_of:["vae"] excludes every *_vae file.
                "valid_predicate": {"all_of": ["ae."], "none_of": ["vae"]},
            },
        },
    },
    # ===================== Anima (T2I/I2I) -- 4th image family; CLOSES the arc. Mirror of Z-Image. =====================
    # Grounded live + render-proven (STEP 0): anima-base-v1.0 is a transformer-only Cosmos-Predict2-
    # derived 2B DiT (header net.blocks.*.adaln_modulation_*, no __metadata__, BF16) in
    # diffusion_models/anima/ -> loads via UNETLoader (split-stack, like Z-Image). Companions are the
    # MIRROR-HALF of Z-Image's: Qwen-3-0.6B encoder (NOT the 4B) + qwen_image_vae (NOT Flux's ae). The
    # graph is a NON-distilled sibling builder (_build_anima_image_prompt: CLIPLoader(type=
    # stable_diffusion) + generic CLIPTextEncode + er_sde + cfg MAPPED, NO shift node) -- the OPPOSITE
    # of Z-Image's Turbo pinning; recipe grounded from the official image_anima_preview.json blueprint.
    #   LANDMINE 1 (Qwen collision -- the arc's capstone, TWO-SIDED): three qwen encoders coexist on
    #   disk (qwen_2.5_vl_7b, qwen_3_4b [Z-Image], qwen_3_06b_base [Anima]). {all_of:["qwen_3_06b"]}
    #   matches ONLY qwen_3_06b_base; Z-Image's {all_of:["qwen_3_4b"]} still matches ONLY qwen_3_4b,
    #   UNBROKEN. Disjoint by construction (06b vs 4b share no substring; neither grabs 2.5_vl_7b).
    #   The 2b-in-12b substring lesson (Lumina's Gemma) carries: keyed on the full "qwen_3_06b" token.
    #   LANDMINE 2 (VAE -- the FLIP of Z-Image): {all_of:["qwen_image","vae"]} = qwen_image_vae. Z-Image
    #   resolved "ae." and EXCLUDED qwen_image_vae; Anima does the opposite. Mutually consistent: both
    #   coexist on disk, neither predicate grabs the other's VAE (ae. lacks "qwen_image"; qwen_image_vae
    #   contains "vae" so Z-Image's none_of:["vae"] excludes it).
    # License: non-commercial (CircleStone Labs + NVIDIA Open Model) -- flagged in MODEL_FAMILIES["anima"].
    "anima": {
        "slots": {
            "primary": {
                "required": True,
                "is_primary": True,
                "explicit_keys": ["model", "model_path", "primary_path"],
            },
            "text_encoder": {          # Qwen-3-0.6B -- the MIRROR-HALF of Z-Image's 4B (two-sided proof)
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "qwen_path"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["qwen_3_06b_base.safetensors"],
                "valid_predicate": {"all_of": ["qwen_3_06b"]},
            },
            "vae": {                   # qwen_image_vae -- the FLIP of Z-Image's ae (both coexist on disk)
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["qwen_image_vae.safetensors"],
                "valid_predicate": {"all_of": ["qwen_image", "vae"]},
            },
        },
    },
    # Krea 2 (T2I/I2I) -- official bases only. Users find their own LoRA/variant files.
    # Raw is the required default UNET. Turbo is an offered speed-lane base, never required.
    # Companions: qwen3vl_4b + qwen_image_vae. Do not install official style LoRAs as family slots.
    "krea2": {
        "slots": {
            "unet_raw": {
                "required": True,
                "explicit_keys": ["model", "model_path", "primary_path", "raw_model", "raw_path"],
                "comfy_class": "UNETLoader",
                "comfy_input": "unet_name",
                "preferred": [
                    "krea2_raw_fp8_scaled.safetensors",
                    "krea2_raw_bf16.safetensors",
                ],
                "valid_predicate": {"all_of": ["krea2", "raw"]},
                "source": {
                    "hf_repo": "Comfy-Org/Krea-2",
                    "path": "diffusion_models/krea2_raw_fp8_scaled.safetensors",
                },
            },
            "unet_turbo": {
                "required": False,
                "optional": True,
                "explicit_keys": ["turbo_model", "turbo_path"],
                "comfy_class": "UNETLoader",
                "comfy_input": "unet_name",
                "preferred": [
                    "krea2_turbo_fp8_scaled.safetensors",
                    "krea2_turbo_bf16.safetensors",
                    "krea2_turbo_nvfp4.safetensors",
                ],
                "valid_predicate": {"all_of": ["krea2", "turbo"]},
                "source": {
                    "hf_repo": "Comfy-Org/Krea-2",
                    "path": "diffusion_models/krea2_turbo_fp8_scaled.safetensors",
                },
            },
            "text_encoder": {
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder"],
                "explicit_sources": ["stack"],
                "comfy_class": "CLIPLoader",
                "comfy_input": "clip_name",
                "preferred": [
                    "qwen3vl_4b_fp8_scaled.safetensors",
                    "qwen3vl_4b_bf16.safetensors",
                ],
                "valid_predicate": {"all_of": ["qwen3vl", "4b"]},
                "source": {
                    "hf_repo": "Comfy-Org/Krea-2",
                    "path": "text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
                },
            },
            "vae": {
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack"],
                "comfy_class": "VAELoader",
                "comfy_input": "vae_name",
                "preferred": ["qwen_image_vae.safetensors"],
                "valid_predicate": {"all_of": ["qwen_image", "vae"]},
                "source": {
                    "hf_repo": "Comfy-Org/Krea-2",
                    "path": "vae/qwen_image_vae.safetensors",
                },
            },
        },
    },
    # ===================== HunyuanVideo (T2V + I2V) -- grounded live /object_info 2026-07-08 =====================
    # Keyed to the registry/contract canonical "hunyuan_video" (VIDEO_FAMILY_CONTRACTS + MODEL_FAMILIES
    # both use it; the alias "hunyuan" resolves via family_manifest's alias step). Grounded against a
    # live /object_info dump on this box -- what the file scan could NOT tell us, and where the
    # Wan-shaped draft was wrong:
    #   - Text encoders load via DualCLIPLoader(type="hunyuan_video") = clip_l + llava_llama3. Each
    #     encoder slot draws its choice list from the shared CLIPLoader/clip_name file set (same
    #     convention as the Flux row). The clip_name1/clip_name2 slot ORDER is a builder concern for
    #     the Hunyuan graph pass, not the combo source, so it is deliberately not encoded here.
    #   - llava is the precision-matched primary encoder -> mapped to the contract's "text_encoder"
    #     slot (so the floor is satisfied, no phantom slot). clip_l is the auxiliary, an EXTRA slot
    #     beyond the contract floor (the current video cockpit surfaces only one text_encoder combo;
    #     surfacing clip_l is a later Hunyuan-cockpit pass -- this pass stages the DATA).
    #   - VAE = hunyuan_video_vae_bf16.
    #   - NO clip_vision slot (the draft assumed one, Wan-style). Live /object_info: the mainstream
    #     I2V node HunyuanImageToVideo takes start_image + vae with NO clip_vision input;
    #     CLIP_VISION_OUTPUT is consumed only by the ALTERNATE nodes (TextEncodeHunyuanVideo_ImageToVideo,
    #     HunyuanVideo15ImageToVideo). So clip_vision is GRAPH-dependent, not a hard I2V requirement
    #     (unlike Wan 2.1's clip_vision_h) -- declaring it required_for i2v would be a FALSE T3-block.
    #     It joins this row only when the Hunyuan-I2V builder picks its conditioning node (Wan added
    #     its clip_vision row only after the i2v wire landed -- same discipline).
    # No primary slot (mirrors Wan): the contract floor ("model","vae","text_encoder") supplies "model"
    # as a PROVIDED slot; precision is probed from the user-selected transformer regardless.
    "hunyuan_video": {
        "slots": {
            "vae": {
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack", "req"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["hunyuan_video_vae_bf16.safetensors"],
                "valid_predicate": {"all_of": ["hunyuan", "vae"]},
            },
            "text_encoder": {   # llava_llama3 -- the LLM encoder, precision-matched to the transformer
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "llava_path", "llava"],
                "explicit_sources": ["stack", "req"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "variant_detection": _PRIMARY_DTYPE_PRECISION,   # dtype-probe (shared)
                "preferred_by_variant": _LLAVA_PREFERRED_BY_VARIANT,
                # "llava_llama3" also matches the clip_vision file llava_llama3_vision.safetensors;
                # none_of:["vision"] keeps the vision tower out of the text-encoder choice set (belt-
                # and-suspenders -- that file lives in models/clip_vision, a different combo, anyway).
                "valid_predicate": {"all_of": ["llava_llama3"], "none_of": ["vision"]},
            },
            "text_encoder_clip_l": {   # CLIP-L -- the auxiliary encoder (EXTRA slot, beyond the floor)
                "required": True,
                "explicit_keys": ["clip_l_path", "clip_l"],
                "explicit_sources": ["stack", "req"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["clip_l.safetensors"],
                "valid_predicate": {"all_of": ["clip_l"]},
            },
            # i2v-only vision tower (v1-concat conditioning). applies_to_tasks:["i2v"] gates it OUT of
            # t2v (the resolver's task gate OMITs it), and it is OPTIONAL (required=False, NO required_for)
            # -- the mainstream HunyuanImageToVideo variant needs no clip_vision, so requiring it would be
            # a false T3-block (see the row header note). It resolves llava_llama3_vision.safetensors from
            # models/clip_vision when present; absent, it is simply omitted (the graph/variant decides).
            "clip_vision": {
                "required": False,
                "applies_to_tasks": ["i2v"],
                "explicit_keys": ["clip_vision", "clip_vision_path"],
                "explicit_sources": ["req", "stack"],
                "comfy_class": "CLIPVisionLoader", "comfy_input": "clip_name",
                "preferred": ["llava_llama3_vision.safetensors"],
                "valid_predicate": {"all_of": ["llava_llama3", "vision"]},
            },
        },
    },
    # ===================== LTX-2.3 (T2V + I2V, AV) -- grounded from the official ComfyUI-LTXVideo =====================
    # example_workflows/2.3/LTX-2.3_T2V_I2V_Two_Stage_Distilled.json (construction-identity verified). The
    # LTX checkpoint is the user-provided primary (no "model" slot, mirrors Wan/Hunyuan). The two builders
    # (single-stage-full + distilled two-stage) patch their repo-owned templates directly and do NOT resolve
    # via this row today -- it is the declarative surface for readiness/auto-population. Route discipline
    # mirrors Hunyuan clip_vision: the distilled-two-stage-only companions (spatial_upscaler, distilled lora)
    # are OPTIONAL so they never false-block the single-stage-full route, which doesn't use them.
    "ltx": {
        "slots": {
            "text_encoder": {   # Gemma -- loaded by LTXAVTextEncoderLoader in BOTH routes
                "required": True,
                "explicit_keys": ["ltx_text_encoder", "text_encoder"],
                "explicit_sources": ["req", "stack"],
                "comfy_class": "LTXAVTextEncoderLoader", "comfy_input": "text_encoder",
                "preferred": ["comfy_gemma_3_12B_it.safetensors"],
                "valid_predicate": {"all_of": ["gemma"]},
            },
            "vae": {   # route-dependent: two-stage draws VAE from the checkpoint; single-stage-full loads a
                       # separate LTX VAE. OPTIONAL so it never false-blocks the two-stage route.
                "required": False,
                "explicit_keys": ["ltx_video_vae", "vae_path", "vae"],
                "explicit_sources": ["req", "stack"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "valid_predicate": {"all_of": ["ltx"], "any_of": [{"all_of": ["vae"]}]},
            },
            "lora": {   # distilled LoRA -- the two-stage route's defining feature; OPTIONAL (route-dependent)
                "required": False,
                "explicit_keys": ["ltx_lora", "lora_path", "lora"],
                "explicit_sources": ["req", "stack"],
                "comfy_class": "LoraLoaderModelOnly", "comfy_input": "lora_name",
                "preferred": ["ltx-2.3-22b-distilled-lora-384-1.1.safetensors"],
                "valid_predicate": {"all_of": ["ltx", "distilled"]},
            },
            "spatial_upscaler": {   # ×2 latent upscaler -- two-stage route ONLY; OPTIONAL, never blocks single-stage
                "required": False,
                "explicit_keys": ["ltx_spatial_upscaler", "spatial_upscaler"],
                "explicit_sources": ["req", "stack"],
                "comfy_class": "LatentUpscaleModelLoader", "comfy_input": "model_name",
                "preferred": ["ltx-2.3-spatial-upscaler-x2-1.1.safetensors"],
                "valid_predicate": {"all_of": ["ltx", "upscal"]},
            },
        },
    },
    # ===================== Mochi (Genmo Mochi-1, T2V only) -- grounded live /object_info + official ComfyUI blueprint =====================
    # Single transformer (mochi_preview_bf16, loaded via UNETLoader) = the user-provided primary, so no
    # "model" slot (the contract floor supplies it, mirroring Wan/Hunyuan/LTX). CLIPLoader(type="mochi")
    # loads T5-XXL; VAELoader loads the dedicated mochi_vae. Both grounded from the live object_info combos
    # on this box (t5xxl_fp16.safetensors + mochi_vae.safetensors present).
    "mochi": {
        "slots": {
            "text_encoder": {   # T5-XXL (Mochi's only text encoder), loaded via CLIPLoader(type="mochi")
                "required": True,
                "explicit_keys": ["text_encoder_path", "text_encoder", "t5_path", "t5"],
                "explicit_sources": ["stack", "req"],
                "comfy_class": "CLIPLoader", "comfy_input": "clip_name",
                "preferred": ["t5xxl_fp16.safetensors"],
                # "t5xxl" excludes Wan's umt5_xxl (contains "t5" but not "t5xxl").
                "valid_predicate": {"all_of": ["t5xxl"]},
            },
            "vae": {   # dedicated Mochi VAE (mochi_vae.safetensors) -- NOT an SD/Flux ae
                "required": True,
                "explicit_keys": ["vae_path", "vae"],
                "explicit_sources": ["stack", "req"],
                "comfy_class": "VAELoader", "comfy_input": "vae_name",
                "preferred": ["mochi_vae.safetensors"],
                "valid_predicate": {"all_of": ["mochi", "vae"]},
            },
        },
    },
}


def family_manifest(family: str) -> dict[str, Any] | None:
    """Return the manifest row for a family, or None if unmanifested (-> engine floors on contract slots).

    Resolves registry ALIASES: a row is keyed by its canonical MODEL_FAMILIES key (e.g.
    "hunyuan_video"), but a caller may hand us an alias ("hunyuan"). Exact key wins; on a miss we map
    the alias -> canonical key via MODEL_FAMILIES and retry. The import is lazy so this file stays
    dependency-free at module load (and returns None gracefully if the registry is unavailable).
    """
    key = str(family or "").strip().lower()
    row = COMPONENT_MANIFEST.get(key)
    if row is not None:
        return row
    try:
        from model_registry import MODEL_FAMILIES
    except Exception:
        return None
    for canon, spec in MODEL_FAMILIES.items():
        aliases = {str(a).strip().lower() for a in (getattr(spec, "aliases", ()) or ())}
        if key == str(canon).strip().lower() or key in aliases:
            return COMPONENT_MANIFEST.get(str(canon).strip().lower())
    return None
