from __future__ import annotations

import json
import logging
import os
import struct
from pathlib import Path
from typing import Any

from comfy_graph_helpers import (
    vae_decode_node,
    text_encoder_device,
    text_encoder_device_input,
    sampling_for as _sampling_for,
    resolve_seed,
    task_of,
    _comfy_ckpt_name_for_model,
    _comfy_input_choices,
    _comfy_unet_name_for_model,
    _emit_wan_lora_chain,
    _filename_prefix_from_output,
    _set_if_allowed,
    _wan_lora_stack_entries,
)
from request_payload import bounded_option
from component_resolver import resolve_stack
from family_operating_points import operating_point_params
from model_classification import classify_model
from upscale_engine import graft_pixel_upscale, resolve_upscale_route

log = logging.getLogger("spellvision.worker")

NATIVE_IMAGE_FAMILIES = {"flux", "pixart", "lumina", "z_image", "anima", "krea2", "sd3"}

def _native_image_family(req: dict[str, Any]) -> str:
    """Classified family for native-image routing (metadata -> request tag -> directory -> filename),
    the same classifier the rest of the worker uses. Empty string if unresolvable."""
    model = str(req.get("model") or "").strip()
    if not model:
        return ""
    try:
        from model_classification import classify_model
        fam = (classify_model(model, requested_family=req.get("model_family")).family or "").strip().lower()
    except Exception:
        fam = str(req.get("model_family") or "").strip().lower()
    if fam in NATIVE_IMAGE_FAMILIES:
        return fam
    lower = model.lower().replace("\\", "/")
    if "krea2" in lower or "krea-2" in lower:
        return "krea2"
    return fam

def _resolve_native_image_stack(req: dict[str, Any], object_info: dict[str, Any], family: str):
    """Producer-side component resolution for a native-image family (Doc 19 §6). FAMILY-GENERAL:
    resolve_stack against the on-disk ComfyUI choices, keyed on the classified family (flux / pixart /
    ...). Image mode has no A2 cockpit auto-populate, so the loader resolves worker-side. choices_for
    is _comfy_input_choices == EXACTLY the files ComfyUI can reference in the graph, so the resolver's
    choice set never diverges from what actually loads. Precision-matched companions (e.g. T5 to the
    transformer dtype) come from the family's manifest row.
    """
    from component_resolver import resolve_stack
    primary = str(req.get("model") or "")
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    fam = str(family or "").strip().lower()
    return resolve_stack(
        primary,
        family=fam,
        requested_family=fam,
        stack=stack,
        req=req,
        task=task_of(req, "t2i"),
        choices_for=lambda cls, inp: _comfy_input_choices(object_info, cls, inp),
    )

def _flux_guidance_from_request(req: dict[str, Any]) -> float:
    """Cockpit 'cfg' -> Flux distilled guidance (FluxGuidance.guidance); KSampler cfg stays pinned 1.0.

    Flux uses distilled guidance, not real classifier-free guidance, so the user-facing cfg slider
    drives the FluxGuidance node. Falls back to 3.5 (the Flux sweet spot) when cfg is absent/<=0.
    (The cockpit default cfg ~6.5 is SDXL-tuned and reads a bit high for Flux; a Simple-mode Flux
    default is a later tuning item, not a correctness issue.)
    """
    raw = req.get("cfg")
    if raw is None:
        raw = req.get("guidance")
    try:
        g = float(raw) if raw is not None else 0.0
    except Exception:
        g = 0.0
    return g if g > 0 else 3.5

def _flux_denoise_from_request(req: dict[str, Any]) -> float:
    """Cockpit i2i strength -> Flux KSampler.denoise, REMAPPED onto a higher band.

    Empirically (2x2 prompt x input swap at denoise 0.9, warmth = mean(R-B)): i2i lets the SUBJECT
    follow the prompt but the OUTPUT TONE is dominated by the INPUT's palette at moderate denoise -- a
    warm input yields warm outputs and a cool input cool outputs, REGARDLESS of the prompt's color
    words. (Same beach prompt: a WARM beach on a warm input, a COOL beach on a cool input; a "cold
    blue winter" prompt on a warm input still comes out warm.) So a prompt whose palette opposes the
    input looks like it "didn't apply". TESTED mechanism (denoise sweep + steps-isolation): the tone
    is carried by the RETAINED INPUT LATENT, not sampling -- at fixed denoise 0.85, 20 vs 60 steps
    give the same warmth (+69.0 / +67.9), ruling out step-count. And it is FREQUENCY-DEPENDENT, not
    proportional: warmth stays pinned to the input (~+69) across denoise 0.4-0.9 while MAE/structure
    rises smoothly (9->20), then tone CLIFFS (0.95 -> +48, 1.0 -> -85). So the prompt rewrites
    high-freq STRUCTURE at moderate denoise while the input's low-freq TONE survives almost to denoise
    1.0. Remapping strength [0,1] -> denoise ~[0.55, 1.0] therefore makes STRUCTURE/detail edits
    responsive across the whole slider, but a palette INVERSION still needs strength -> near-max
    (denoise >~0.95, where the input is nearly ignored) -- a fundamental i2i limit here, not something
    the remap overcomes. Flux-native path only; SDXL i2i (the separate
    diffusers run_i2i) keeps the literal strength=denoise mapping. NOTE: this is INPUT-PALETTE
    DOMINANCE, not prompt-strength and not subject-overlap -- both were falsified by the swap test.
    """
    raw = req.get("strength")
    if raw is None:
        raw = req.get("denoise")
    try:
        s = float(raw) if raw is not None else -1.0
    except Exception:
        s = -1.0
    if not (0.0 <= s <= 1.0):
        s = 0.6  # sensible default strength when absent/out-of-range
    return round(0.55 + 0.45 * s, 4)  # [0,1] strength -> [0.55, 1.0] Flux denoise

def _flux_checkpoint_incompatible_reason(model_path: str) -> str | None:
    """Header-peek a flux checkpoint; return an ACTIONABLE reason if it is a DIFFUSERS-format transformer
    (transformer_blocks.*/single_transformer_blocks.* naming), which CheckpointLoaderSimple cannot load ->
    it raises the cryptic 'Could not detect model type'. Returns None if it looks loadable or is unreadable
    (let ComfyUI surface its own error). Cheap: reads only the safetensors header key map."""
    try:
        import struct
        with open(model_path, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            header = json.loads(fh.read(n).decode("utf-8", "ignore"))
    except Exception:
        return None
    keys = [k for k in header if k != "__metadata__"]
    if keys and any(k.startswith(("transformer_blocks.", "single_transformer_blocks.")) for k in keys):
        return (
            f"Flux model {os.path.basename(model_path)!r} is a DIFFUSERS-format transformer "
            "(transformer_blocks.* keys), which ComfyUI's CheckpointLoaderSimple cannot load "
            "('could not detect model type'). Convert it to ComfyUI format, or use a ComfyUI-format flux "
            "checkpoint (or a flux UNET placed under diffusion_models/)."
        )
    return None

def _build_flux_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                             resolved: Any) -> dict[str, Any]:
    """Grounded Flux t2i graph. Companions come from resolve_stack (precision-matched T5), NOT
    hardcoded; cockpit cfg -> FluxGuidance.guidance. Structure is B-img1's proven live binding
    (DualCLIPLoader clip_name1=clip_l / clip_name2=T5 / type=flux, FluxGuidance, EmptySD3LatentImage);
    only the filenames are supplied by the resolver.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(
            f"Flux checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}. "
            "It must live under the ComfyUI checkpoints path."
        )
    _flux_reason = _flux_checkpoint_incompatible_reason(model_path)
    if _flux_reason:
        raise RuntimeError(_flux_reason)
    # Resolver-driven companions (precision-matched T5). The canonical-name fallbacks only guard a
    # slot that resolved empty WITHOUT being flagged missing; the T3 gate in run_native_image is the
    # real completeness guard.
    clip_l = resolved.value("text_encoder") or "clip_l.safetensors"
    t5 = resolved.value("text_encoder_2") or "t5xxl_fp16.safetensors"
    vae = resolved.value("vae") or "ae.safetensors"

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # Flux latent (16ch, /8 VAE + /2 patch) needs dims divisible by 16

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    # Phase 2b: steps default lifted to the table (flux_image). cfg is PINNED 1.0 + FluxGuidance
    # mapping and sampler/scheduler are hardcoded euler/simple -- recorded in the table, NOT routed.
    _defaults = operating_point_params("flux_image", "default")
    try:
        steps = bounded_option(req, "steps", 20, table=_defaults)
    except Exception:
        steps = 20
    seed = resolve_seed(req, "seed")
    guidance = _flux_guidance_from_request(req)  # cockpit cfg -> FluxGuidance.guidance
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    # Shared Flux stack (resolver-driven companions, precision-matched T5, cfg->guidance) -- identical
    # for t2i and i2i. Only the LATENT SOURCE + KSampler denoise differ between the two.
    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": clip_l, "clip_name2": t5, "type": "flux",
            **text_encoder_device_input(req, object_info, "DualCLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0]),
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        # i2i: uploaded input image -> LoadImage -> VAEEncode -> latent. denoise < 1.0 is what makes
        # the output conditioned on the input (1.0 would ignore it = a from-scratch render).
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Flux i2i graph requires an uploaded input image (input_image_comfy_name).")
        denoise = _flux_denoise_from_request(req)  # cockpit strength -> KSampler.denoise
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    sampler_name, scheduler_name = _sampling_for("flux", req, object_info, "euler", "simple")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": 1.0,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["5", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_pixart_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """PixArt-Sigma t2i/i2i graph -- grounded live + render-proven (STEP 0). Architecturally distinct
    from Flux: transformer via CheckpointLoaderSimple, T5 via CLIPLoader(type="pixart"), the SDXL 4-ch
    VAE, CLIPTextEncodePixArtAlpha (resolution-aware, takes width/height), and REAL classifier-free
    guidance (KSampler.cfg), NOT the Flux DualCLIP+FluxGuidance graph. Companions are resolver-driven
    (resolved.value), same provenance as the Flux builder.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(
            f"PixArt checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}."
        )
    t5 = resolved.value("text_encoder") or "t5xxl_fp16.safetensors"   # precision-matched via manifest
    vae = resolved.value("vae") or "sdxl_vae.safetensors"

    def _snap8(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 8)  # SD/SDXL 4-ch VAE latent is /8

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap8(req.get("width"), 1024)
    height = _snap8(req.get("height"), 1024)
    _defaults = operating_point_params("pixart_image", "default")  # Phase 2b: steps/cfg lifted (sampler/scheduler pinned)
    try:
        steps = bounded_option(req, "steps", 20, table=_defaults)
    except Exception:
        steps = 20
    seed = resolve_seed(req, "seed")
    try:
        cfg = bounded_option(req, "cfg", 4.5, table=_defaults)  # PixArt uses REAL CFG (unlike Flux's pinned 1.0 + FluxGuidance)
    except Exception:
        cfg = 4.5
    if cfg <= 0:
        cfg = 4.5
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": t5, "type": "pixart",
                         **text_encoder_device_input(req, object_info, "CLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncodePixArtAlpha", "inputs": {"width": width, "height": height, "text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncodePixArtAlpha", "inputs": {"width": width, "height": height, "text": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0]),
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("PixArt i2i graph requires an uploaded input image (input_image_comfy_name).")
        # Literal strength->denoise (NOT the Flux remap -- that was calibrated to Flux's measured
        # input-tone dominance; PixArt uses real CFG + real negative and its i2i behavior is untested).
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    sampler_name, scheduler_name = _sampling_for("pixart", req, object_info, "euler", "normal")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_lumina_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """Lumina Image 2.0 t2i/i2i graph -- grounded live + render-proven (STEP 0). The all-in-one
    lumina_2 checkpoint BAKES the VAE, so VAEDecode/VAEEncode use CheckpointLoaderSimple's VAE output
    (["1",2]) -- NO VAELoader. The Gemma-2-2B text encoder IS resolver-driven (separate
    CLIPLoader(type=lumina2), size-specific predicate excludes LTX's gemma_3_12B). Distinct from
    Flux/PixArt: sigma shift via ModelSamplingAuraFlow, CLIPTextEncodeLumina2 (system_prompt="superior"
    handles Lumina's prompt convention -- no manual prefix), res_multistep sampler, real cfg.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(f"Lumina checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}.")
    gemma = resolved.value("text_encoder") or "gemma_2_2b_fp16.safetensors"   # size-specific gemma_2_2b

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # Lumina uses the 16-ch VAE latent (EmptySD3LatentImage), /16 like Flux

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    _defaults = operating_point_params("lumina_image", "default")  # Phase 2b: steps/cfg lifted (shift 6.0 + sampler/scheduler pinned)
    try:
        steps = bounded_option(req, "steps", 30, table=_defaults)
    except Exception:
        steps = 30
    seed = resolve_seed(req, "seed")
    try:
        cfg = bounded_option(req, "cfg", 4.0, table=_defaults)  # Lumina uses REAL cfg
    except Exception:
        cfg = 4.0
    if cfg <= 0:
        cfg = 4.0
    shift = 6.0  # Lumina 2.0 sigma shift (official regime; render-proven clean at shift 6 / res_multistep)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": gemma, "type": "lumina2",
                         **text_encoder_device_input(req, object_info, "CLIPLoader")}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": shift}},
        "4": {"class_type": "CLIPTextEncodeLumina2", "inputs": {"system_prompt": "superior", "user_prompt": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncodeLumina2", "inputs": {"system_prompt": "superior", "user_prompt": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["1", 2]),  # baked VAE from checkpoint
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Lumina i2i graph requires an uploaded input image (input_image_comfy_name).")
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}}  # baked VAE
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    sampler_name, scheduler_name = _sampling_for("lumina", req, object_info, "res_multistep", "normal")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,  # model = the shifted MODEL from node 5
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_zimage_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """Z-Image Turbo t2i/i2i graph -- the FIRST split-stack image family (STEP 0, render-proven). The
    transformer loads via UNETLoader (diffusion_models/, NOT CheckpointLoaderSimple); the Qwen-3-4B
    encoder + Flux ae VAE are EXTERNAL, resolver-driven. Distilled Turbo: cfg is PINNED at 1.0 (CFG is
    baked in -- the cockpit's SDXL-tuned cfg 6.5 would over-cook) and steps default to 4 (the official
    Turbo NFE), ignoring the SDXL-default 35. Graph GROUNDED from the official Comfy-Org/z_image_turbo
    blueprint (Text to Image (Z-Image-Turbo).json): CLIPLoader(type="lumina2" -- Z-Image is
    Lumina-derived) + generic CLIPTextEncode + ModelSamplingAuraFlow(shift 3) + KSampler(res_multistep,
    simple). BASE bf16 only -- SVDQ/int4/nunchaku/GGUF quant variants are the deferred quant-loader arc.
    """
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Z-Image transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    qwen = resolved.value("text_encoder") or "qwen_3_4b.safetensors"   # size-specific gemma... qwen_3_4b
    vae = resolved.value("vae") or "ae.safetensors"                    # Flux ae (NOT zImage_vae)

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # 16-ch ae latent (EmptySD3LatentImage), /16 like Flux/Lumina

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")  # inert at cfg 1.0; wired for completeness
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    # Phase 2b: steps default lifted (zimage_image). cfg 1.0 (baked, cockpit IGNORED) and shift 3.0
    # are PINNED -- recorded in the table, NOT routed. The <1 / >16 -> 4 clamp below stays inline.
    _defaults = operating_point_params("zimage_image", "default")
    try:
        steps = bounded_option(req, "steps", 4, table=_defaults)
    except Exception:
        steps = 4
    if steps < 1 or steps > 16:
        steps = 4  # official Turbo is 4 NFE; ignore the SDXL-default 35 (Simple-mode default fix)
    seed = resolve_seed(req, "seed")
    cfg = 1.0     # distilled Turbo: CFG is baked in; real cfg over-saturates. Cockpit cfg IGNORED.
    shift = 3.0   # Z-Image sigma shift (render-proven clean)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": qwen, "type": "lumina2",
                         **text_encoder_device_input(req, object_info, "CLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": shift}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0]),
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Z-Image i2i graph requires an uploaded input image (input_image_comfy_name).")
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    sampler_name, scheduler_name = _sampling_for("z_image", req, object_info, "res_multistep", "simple")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_anima_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                              resolved: Any) -> dict[str, Any]:
    """Anima t2i/i2i graph -- the 4th image family, CLOSES the arc. Split-stack like Z-Image
    (UNETLoader, diffusion_models/anima/, a Cosmos-Predict2-derived 2B DiT) but the recipe is the
    OPPOSITE: Anima is NON-distilled. Companions are the MIRROR-HALF of Z-Image's: the Qwen-3-0.6B
    encoder (NOT the 4B) + qwen_image_vae (the FLIP of Z-Image's ae) -- both resolver-driven, both
    coexisting with Z-Image's on the same disk. Recipe GROUNDED from the official ComfyUI
    Template-Library blueprint (image_anima_preview.json): CLIPLoader(type="stable_diffusion") +
    generic CLIPTextEncode + EmptyLatentImage + KSampler(er_sde, simple) with NO ModelSamplingAuraFlow
    shift node. cfg is MAPPED from the cockpit (default 4, the blueprint value; NOT pinned to 1.0 like
    Z-Image's Turbo) and steps default to 30 (mapped, NOT the Turbo 4) -- do NOT copy Z-Image's pinning.
    Anima is anime/illustration-only by design (no realism). License: non-commercial -- see
    MODEL_FAMILIES["anima"].
    """
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Anima transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    qwen = resolved.value("text_encoder") or "qwen_3_06b_base.safetensors"   # 0.6B (mirror-half of Z-Image's 4B)
    vae = resolved.value("vae") or "qwen_image_vae.safetensors"              # qwen_image_vae (FLIP of Z-Image's ae)

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")  # active (cfg > 1, unlike Z-Image)
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    _defaults = operating_point_params("anima_image", "default")  # Phase 2b: steps/cfg lifted (sampler/scheduler pinned; cfg NOT pinned -- mapped)
    try:
        steps = bounded_option(req, "steps", 30, table=_defaults)
    except Exception:
        steps = 30
    if steps < 1:
        steps = 30  # NON-distilled: honor the cockpit (30-50 typical); blueprint default 30, NO Turbo-4 pin
    try:
        cfg = bounded_option(req, "cfg", 4.0, table=_defaults)
    except Exception:
        cfg = 4.0
    if cfg <= 0:
        cfg = 4.0   # MAPPED from cockpit (blueprint 4-5 band); NOT pinned like Z-Image's Turbo cfg=1.0
    seed = resolve_seed(req, "seed")
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": qwen, "type": "stable_diffusion",
                         **text_encoder_device_input(req, object_info, "CLIPLoader")}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0]),
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Anima i2i graph requires an uploaded input image (input_image_comfy_name).")
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    # NO shift node: KSampler.model comes straight from UNETLoader (blueprint has no ModelSamplingAuraFlow).
    sampler_name, scheduler_name = _sampling_for("anima", req, object_info, "er_sde", "simple")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


def _sd3_checkpoint_bundles_text_encoders(model_path: str) -> bool:
    """Whether this SD3 checkpoint carries its own CLIP/T5 weights.

    SD3.5 ships both ways and the graph differs: the "incl_clips" build bundles clip_l, clip_g and
    t5xxl, while ``sd3.5_large_fp8_scaled.safetensors`` is the transformer alone and needs a
    TripleCLIPLoader beside it -- the note node in Comfy-Org's own blueprint says exactly that.

    Read from the safetensors header, not from the filename. ``_incl_clips_`` is a naming convention
    a rename breaks, and getting this wrong does not fail loudly: wiring a bundled checkpoint's CLIP
    output when there is none produces a conditioning of nothing, which still renders.
    """
    path = str(model_path or "")
    if not path.lower().endswith(".safetensors") or not os.path.isfile(path):
        # Unreadable is not "no". Assume bundled, which is the shipping default, and let ComfyUI
        # raise a real error rather than silently wiring an unrelated text encoder.
        return True
    try:
        with open(path, "rb") as handle:
            length = struct.unpack("<Q", handle.read(8))[0]
            if length <= 0 or length > 80_000_000:
                return True
            header = json.loads(handle.read(length).decode("utf-8", "replace"))
    except Exception:
        return True
    return any(str(key).startswith("text_encoders.") for key in header)


def _build_sd3_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                            resolved: Any) -> dict[str, Any]:
    """Stable Diffusion 3 / 3.5 t2i+i2i, grounded on the blueprint the checkpoint's own repo ships
    (``Comfy-Org/stable-diffusion-3.5-fp8`` -> ``sd3.5-t2i-fp8-scaled-workflow.json``).

    Two things here are load-bearing and neither is guessable from the family name:

    * **EmptySD3LatentImage, never EmptyLatentImage.** SD3's latent space is 16-channel. A 4-channel
      latent is accepted by the graph and decodes to noise -- the same silent-garbage trap the Krea 2
      builder carries a warning about.
    * **The checkpoint may or may not carry its own text encoders**, so the CLIP source is decided by
      reading the file's header rather than assuming (``_sd3_checkpoint_bundles_text_encoders``).

    Routed native rather than through diffusers deliberately. ``from_single_file`` reads the
    checkpoint but pulls its config from the gated ``stabilityai/stable-diffusion-3.5-medium`` repo,
    which puts a third-party licence acceptance in a user's first-run path; and the native route is
    where SpellVision's memory work lives (DynamicVRAM staging, tiled decode, sage attention).

    Operating point is the blueprint's own: 30 steps, cfg 5.45, euler / sgm_uniform. NOT changed on
    the strength of the one-image-per-sampler comparison run when the family landed -- Krea 2's
    default moved only after three measured pairs, and one render is an impression, not a result.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(
            f"SD3 checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r} "
            "(must be under a checkpoints/ root Comfy can see)."
        )

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    _defaults = operating_point_params("sd3_image", "default")
    try:
        steps = bounded_option(req, "steps", 30, table=_defaults)
    except Exception:
        steps = 30
    try:
        cfg = bounded_option(req, "cfg", 5.45, table=_defaults)
    except Exception:
        cfg = 5.45
    if cfg <= 0:
        cfg = 5.45
    seed = resolve_seed(req, "seed")
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = task_of(req) == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
    }

    if _sd3_checkpoint_bundles_text_encoders(model_path):
        clip_ref: list[Any] = ["1", 1]
    else:
        # The transformer-only build. All three encoders are required together -- SD3 conditions on
        # clip_l + clip_g + t5xxl -- so a missing one is refused rather than substituted.
        clip_l = resolved.value("clip_l") or "clip_l.safetensors"
        clip_g = resolved.value("clip_g") or "clip_g.safetensors"
        t5 = resolved.value("t5") or resolved.value("text_encoder") or "t5xxl_fp8_e4m3fn_scaled.safetensors"
        available = set(_comfy_input_choices(object_info, "TripleCLIPLoader", "clip_name1") or ())
        missing = [n for n in (clip_l, clip_g, t5) if available and n not in available]
        if missing:
            raise RuntimeError(
                f"This SD3 checkpoint carries no text encoders, and ComfyUI cannot see: "
                f"{', '.join(missing)}. SD3 conditions on clip_l + clip_g + t5xxl together; "
                "SpellVision will not substitute a different encoder for a missing one."
            )
        graph["2"] = {"class_type": "TripleCLIPLoader", "inputs": {
            "clip_name1": clip_l, "clip_name2": clip_g, "clip_name3": t5}}
        clip_ref = ["2", 0]

    graph["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}}
    graph["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_ref}}
    graph["9"] = vae_decode_node(req, object_info, samples=["8", 0], vae=["1", 2])
    graph["10"] = {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}}

    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("SD3 i2i graph requires an uploaded input image (input_image_comfy_name).")
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        # 16-channel. EmptyLatentImage here would decode to noise.
        graph["7"] = {"class_type": "EmptySD3LatentImage",
                      "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]

    sampler_name, scheduler_name = _sampling_for("sd3", req, object_info, "euler", "sgm_uniform")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_krea2_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                              resolved: Any) -> dict[str, Any]:
    """Krea 2 t2i/i2i. Grounded from live Comfy 2026-08-17 source, not a guessed node list.

    - CLIPLoader type ``krea2`` is in ``nodes.py`` CLIPLoader.INPUT_TYPES.
    - UNETLoader loads ``image_model=krea2`` (``supported_models.Krea2``).
    - VAE is ``qwen_image_vae`` via VAELoader (same file as Anima).
    - Latent is 16-ch (``Wan21.latent_channels``); EmptySD3LatentImage is the 16-ch 2D empty
      latent in this Comfy. Do not use EmptyLatentImage (4-ch).
    - Shift 1.15 is ``Krea2.sampling_settings`` via ModelSamplingAuraFlow (multiplier 1.0).
    - Raw (default): 52 / 3.5. Turbo: 8 / CFG 1 (not 0). Filename snap; LoRAs optional.
    """
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Krea 2 transformer is not visible to ComfyUI UNETLoader: {model_path!r} "
            "(must be under a diffusion_models/ root Comfy can see)."
        )
    clip_name = resolved.value("text_encoder") or "qwen3vl_4b_fp8_scaled.safetensors"
    vae = resolved.value("vae") or "qwen_image_vae.safetensors"
    variant = "turbo" if "turbo" in Path(model_path).name.lower() else "raw"
    defaults = operating_point_params("krea2_image", variant) or operating_point_params("krea2_image", "raw")

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    try:
        steps = bounded_option(req, "steps", 8, table=defaults)
    except Exception:
        steps = 8
    try:
        cfg = bounded_option(req, "cfg", 1.0, table=defaults)
        if cfg <= 0.0:
            cfg = 1.0
    except Exception:
        cfg = 1.0
    seed = resolve_seed(req, "seed")
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    mask_name = str(req.get("inpaint_mask_comfy_name") or "").strip()
    if mask_name:
        from krea2_regional_inpaint import build_krea2_regional_inpaint_graph

        lock_name = str(req.get("input_image_comfy_name") or "").strip()
        if not lock_name:
            raise RuntimeError("Krea 2 inpaint graph requires input_image_comfy_name.")
        identity = str(req.get("identity_prompt") or "").strip()
        if not identity:
            identity = (
                "the same specific woman, same face, same body, same pose, "
                "face fully visible, no second face"
            )
        # An eighth denoise idiom in this file, reading only `denoise` -- so the cockpit's
        # `strength` was invisible here while the six builders above read `strength` and not
        # `denoise`. The resolver reads all three.
        denoise = bounded_option(req, "denoise", 0.7)
        latent_mode = str(req.get("latent_mode") or "inpaint").strip().lower() or "inpaint"
        return build_krea2_regional_inpaint_graph(
            request=req,
            object_info=object_info,
            unet_name=unet_name,
            clip_name=clip_name,
            vae_name=vae,
            lock_image=lock_name,
            mask_image=mask_name,
            edit_prompt=prompt,
            identity_prompt=identity,
            negative_prompt=negative or (
                "second face, extra face, framed photo, inset portrait, "
                "sheer, nude, mosaic, extra limbs"
            ),
            seed=seed,
            steps=steps,
            cfg=cfg,
            denoise=denoise,
            latent_mode=latent_mode,
            filename_prefix=prefix,
        )
    # Krea 2's text encoder is a 4B model. The reference workflow pins it to the CPU; copying that
    # would impose the author's machine on every user, so it is routed through the shared memory
    # profile instead. `device` is an OPTIONAL CLIPLoader input taking exactly {"default","cpu"} --
    # read from a live /object_info, not from the workflow.
    clip_device = text_encoder_device(req, object_info, "CLIPLoader")

    is_i2i = task_of(req) == "i2i"
    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": clip_name, "type": "krea2",
                         **({"device": clip_device} if clip_device else {})}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": vae_decode_node(req, object_info, samples=["8", 0], vae=["3", 0]),
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    # Enabled LoRAs only. Empty stack keeps UNET -> shift byte-identical; never required.
    model_ref = _emit_wan_lora_chain(graph, object_info, ["1", 0], _wan_lora_stack_entries(req), node_prefix="krea_lora_")
    graph["5"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": model_ref, "shift": 1.15}}
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Krea 2 i2i graph requires an uploaded input image (input_image_comfy_name).")
        # `0.0 < denoise` rejected a stated zero and silently substituted 0.6 -- so "leave my image
        # alone" produced a substantially altered one, and an absent value and a stated 0.0 were
        # indistinguishable. Flux, in this same file, has always used the inclusive form. The
        # resolver resolves `strength` too, which is the key the cockpit actually sends.
        denoise = bounded_option(req, "denoise", 0.6)
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    sampler_name, scheduler_name = _sampling_for("krea2", req, object_info, "euler", "simple")
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": sampler_name, "scheduler": scheduler_name,
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph

def _build_native_image_prompt(family: str, req: dict[str, Any], object_info: dict[str, Any],
                               job_id: str, resolved: Any) -> dict[str, Any]:
    """Dispatch to the per-family native-image graph builder. Each family's architecture differs
    (Flux DualCLIP+FluxGuidance; PixArt CLIPLoader(pixart)+PixArtAlpha; Lumina CLIPLoader(lumina2)+
    ModelSamplingAuraFlow+Lumina2+res_multistep; Z-Image UNETLoader+CLIPLoader(lumina2)+cfg~1.0;
    Anima UNETLoader+CLIPLoader(stable_diffusion)+er_sde+cfg-mapped, no shift), so the GRAPH is
    per-family even though resolve/route/T3 are shared. Add a branch to register a family.
    """
    fam = str(family or "").strip().lower()
    builders = {
        "flux": _build_flux_image_prompt,
        "pixart": _build_pixart_image_prompt,
        "lumina": _build_lumina_image_prompt,
        "z_image": _build_zimage_image_prompt,
        "anima": _build_anima_image_prompt,
        "krea2": _build_krea2_image_prompt,
        "sd3": _build_sd3_image_prompt,
    }
    build = builders.get(fam) or builders["flux"]
    graph = build(req, object_info, job_id, resolved)
    if resolve_upscale_route(fam, req.get("upscale_method"), enabled=bool(req.get("upscale_enabled"))) == "pixel_comfy":
        graph = graft_pixel_upscale(
            graph,
            object_info,
            model_name=req.get("upscale_model_name") or req.get("upscale_model"),
        )
    return graph

def _should_route_native_image(req: dict[str, Any]) -> bool:
    """Route a NATIVE-IMAGE family's t2i/i2i to the ComfyUI-native path instead of the diffusers loader.

    Native-image families (NATIVE_IMAGE_FAMILIES: flux, pixart, ...) are transformer-only checkpoints
    that either can't load through diffusers from_single_file (Flux's gated-config STOP) or have a
    distinct ComfyUI-native DiT graph (PixArt). Family is the same classifier the rest of the worker
    uses; every other family (SDXL i2i included) keeps its existing diffusers path.
    """
    command = task_of(req)
    if command not in {"t2i", "i2i"}:
        return False
    return _native_image_family(req) in NATIVE_IMAGE_FAMILIES

