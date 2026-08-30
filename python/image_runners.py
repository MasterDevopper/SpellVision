"""Diffusers image runners: t2i/i2i plus LoRA, IP-Adapter, and upscale.

Extracted from worker_service.py. Pipeline cache and Comfy native graphs
stay elsewhere; this module only runs the local image path.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
import os
import time
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from worker_service_state import (
    ActiveJobHandle,
    JobCancelledError,
    JobEmitter,
    JobRecord,
    JobState,
    cancel_job,
    complete_job,
    raise_if_cancelled,
    transition_job,
)
from request_payload import bounded_option, resolve_request_lora
from native_image_graphs import _should_route_native_image
from worker_runtime import CACHE_LOCK, MODEL_CACHE
from vram import worker_vram


def _ws():
    import worker_service as ws
    return ws


def _lora_cache_keys(pipe_role: str) -> tuple[str, str]:
    role = pipe_role.lower().strip()
    if role not in {"t2i", "i2i"}:
        raise ValueError(f"Unknown LoRA pipe role: {pipe_role}")
    return (f"active_lora_path_{role}", f"active_lora_scale_{role}")


def get_cached_lora_state(pipe_role: str) -> tuple[str | None, float | None]:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        return MODEL_CACHE.get(path_key), MODEL_CACHE.get(scale_key)


def set_cached_lora_state(pipe_role: str, lora_path: str | None, lora_scale: float | None) -> None:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        MODEL_CACHE[path_key] = lora_path
        MODEL_CACHE[scale_key] = lora_scale


def _lora_adapter_name(normalized_path: str) -> str:
    # peft adapter names must be simple identifiers; derive a stable,
    # collision-free name from the LoRA's absolute path.
    digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:12]
    return f"lora_{digest}"


def _lora_adapter_registry() -> dict[str, str]:
    # normalized LoRA path -> adapter name, for adapters already loaded onto the
    # current model's (shared) pipelines. Reset on model swap; kept across
    # t2i<->i2i role switches within a model. Call under CACHE_LOCK.
    registry = MODEL_CACHE.get("lora_adapters")
    if not isinstance(registry, dict):
        registry = {}
        MODEL_CACHE["lora_adapters"] = registry
    return registry


def active_adapter_names(pipe: Any) -> list[str]:
    try:
        if hasattr(pipe, "get_active_adapters"):
            return [str(name) for name in pipe.get_active_adapters()]
    except Exception:
        pass
    return []


def _disable_pipe_adapters(pipe: Any) -> None:
    # Run pristine base weights for THIS generation without unloading any
    # adapters -- they stay resident on the shared modules for the other role.
    try:
        if hasattr(pipe, "disable_lora"):
            pipe.disable_lora()
            return
    except Exception:
        pass
    try:
        if hasattr(pipe, "set_adapters"):
            pipe.set_adapters([])
    except Exception:
        pass


def ensure_lora_adapter_loaded(pipe: Any, normalized_path: str) -> tuple[str, bool]:
    # Load the LoRA exactly once as a NAMED adapter (never fused, so the base
    # UNet weights -- shared between the t2i/i2i pipes -- are never mutated).
    # Returns (adapter_name, newly_loaded).
    adapter_name = _lora_adapter_name(normalized_path)
    with CACHE_LOCK:
        existing = _lora_adapter_registry().get(normalized_path)
    if existing:
        return existing, False

    pipe.load_lora_weights(normalized_path, adapter_name=adapter_name)
    with CACHE_LOCK:
        _lora_adapter_registry()[normalized_path] = adapter_name
    return adapter_name, True


def reset_lora_state(pipe: Any, pipe_role: str | None = None) -> None:
    # Non-destructive no-LoRA path: DISABLE adapters for this pipe's next
    # generation, but do NOT unload -- the other role's adapter must stay
    # resident on the shared UNet. Base weights are never mutated (we never
    # fuse), so disabling == clean base output.
    _disable_pipe_adapters(pipe)
    if pipe_role:
        set_cached_lora_state(pipe_role, None, None)


def maybe_load_lora(pipe: Any, lora_path: str, lora_scale: float, pipe_role: str) -> tuple[bool, dict[str, Any]]:
    normalized_path = os.path.abspath(lora_path).strip() if lora_path else ""
    cached_path, cached_scale = get_cached_lora_state(pipe_role)

    if not normalized_path:
        cleared = bool(cached_path)
        reset_lora_state(pipe, pipe_role)
        return False, {
            "lora_cache_hit": False,
            "lora_reloaded": False,
            "lora_cleared": cleared,
            "active_lora_path": None,
            "active_lora_scale": None,
        }

    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"LoRA file not found: {normalized_path}")

    try:
        import peft  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from exc

    adapter_name, newly_loaded = ensure_lora_adapter_loaded(pipe, normalized_path)

    # ALWAYS (re)select + scale this role's adapter right before generating. The
    # UNet is shared between the t2i/i2i pipes, so the active adapter is global
    # state the other role may have changed -- selecting every time is what makes
    # the two roles independent. set_adapters is a cheap toggle (no reload, no
    # fuse), so there is deliberately no cache-hit short-circuit that skips it.
    try:
        if hasattr(pipe, "enable_lora"):
            pipe.enable_lora()
    except Exception:
        pass
    pipe.set_adapters([adapter_name], adapter_weights=[float(lora_scale)])

    same_as_cached = (
        cached_path == normalized_path
        and cached_scale is not None
        and abs(float(cached_scale) - float(lora_scale)) < 1e-9
    )
    set_cached_lora_state(pipe_role, normalized_path, float(lora_scale))

    return True, {
        "lora_cache_hit": (not newly_loaded) and same_as_cached,
        "lora_reloaded": newly_loaded,
        "lora_cleared": False,
        "active_lora_path": normalized_path,
        "active_lora_scale": float(lora_scale),
    }


def _scheduler_from_config(scheduler_cls: Any, base_config: Any, **kwargs: Any) -> tuple[Any, list[str]]:
    """Build the scheduler, and report any kwarg that did not survive into it.

    Checked against the RESULT, not against an exception. diffusers' ``from_config`` does not reject
    an unknown kwarg -- it collects it into unused_kwargs and carries on -- so the old
    ``except TypeError`` retry never fired, and "ddim + karras" shipped as the default for 112
    checkpoints while rendering ddim with no karras. Nothing raised; the flag was simply absent
    afterwards, which is exactly what the live measurement found.

    Asking the built object what it has is also the more durable question: it stays correct however
    diffusers decides to handle an option a class does not know.
    """
    if scheduler_cls is None:
        return None, []
    try:
        scheduler = scheduler_cls.from_config(base_config, **kwargs)
    except TypeError:
        scheduler = scheduler_cls.from_config(base_config)
        dropped = sorted(kwargs)
    else:
        config = getattr(scheduler, "config", {}) or {}
        dropped = sorted(key for key, value in kwargs.items() if config.get(key) != value)
    if dropped:
        logging.warning(
            "%s did not take %s; the scheduler was built without it. The choice the user made has "
            "no effect on this sampler.", scheduler_cls.__name__, ", ".join(dropped))
    return scheduler, dropped


_SCHEDULER_IMPORTS: dict[str, tuple[str, str]] = {
    "euler": ("diffusers.schedulers.scheduling_euler_discrete", "EulerDiscreteScheduler"),
    "euler_ancestral": ("diffusers.schedulers.scheduling_euler_ancestral_discrete", "EulerAncestralDiscreteScheduler"),
    "heun": ("diffusers.schedulers.scheduling_heun_discrete", "HeunDiscreteScheduler"),
    "dpm_2": ("diffusers.schedulers.scheduling_k_dpm_2_discrete", "KDPM2DiscreteScheduler"),
    "dpm_2_ancestral": ("diffusers.schedulers.scheduling_k_dpm_2_ancestral_discrete", "KDPM2AncestralDiscreteScheduler"),
    "lms": ("diffusers.schedulers.scheduling_lms_discrete", "LMSDiscreteScheduler"),
    "dpmpp_2m": ("diffusers.schedulers.scheduling_dpmsolver_multistep", "DPMSolverMultistepScheduler"),
    "dpmpp_sde": ("diffusers.schedulers.scheduling_dpmsolver_singlestep", "DPMSolverSinglestepScheduler"),
    # Offered in the sdxl allowlist since it was written and mapped nowhere, so a user who picked it
    # got whatever scheduler happened to be loaded. Measured: applied=False, and the render came back
    # byte-identical to plain euler. diffusers expresses the SDE variant as an algorithm_type on the
    # multistep solver rather than as its own class, which is why a name-to-class table missed it.
    "dpmpp_2m_sde": ("diffusers.schedulers.scheduling_dpmsolver_multistep", "DPMSolverMultistepScheduler"),
    "ddpm": ("diffusers.schedulers.scheduling_ddpm", "DDPMScheduler"),
    "ddim": ("diffusers.schedulers.scheduling_ddim", "DDIMScheduler"),
    "deis": ("diffusers.schedulers.scheduling_deis_multistep", "DEISMultistepScheduler"),
    "pndm": ("diffusers.schedulers.scheduling_pndm", "PNDMScheduler"),
    "lcm": ("diffusers.schedulers.scheduling_lcm", "LCMScheduler"),
    "uni_pc": ("diffusers.schedulers.scheduling_unipc_multistep", "UniPCMultistepScheduler"),
}

# Every entry above solves an epsilon/v-prediction diffusion ODE over a sigma schedule. A
# FLOW-MATCHING model (SD3 / SD3.5, and the FLUX family) is a different formulation -- it learns a
# velocity field between noise and data -- so those schedulers are not slower or worse for it, they
# are wrong for it. Swapping one in still renders, which is exactly why this needed its own table
# rather than a comment: the failure would have been a quietly degraded image, not an exception.
#
# diffusers 0.37.0 ships three flow-matching schedulers and no more, so this table is the honest
# extent of the choice. A sampler with no entry here is reported as unmapped and the pipeline keeps
# its own scheduler -- there is no dpmpp_2m for a flow-matching model to fall back to.
# Config a sampler needs beyond its class. Kept beside the import table rather than inside the
# apply function so the two stay readable as one fact per sampler.
_SAMPLER_EXTRA_CONFIG: dict[str, dict[str, Any]] = {
    "dpmpp_2m_sde": {"algorithm_type": "sde-dpmsolver++"},
}

# Sigma-schedule shaping. These are the flags a SCHEDULER choice sets, and they are the ones that
# leak: diffusers stores them in the scheduler config, the worker rebuilds each scheduler from the
# LIVE config, so a flag set by one render survives into the next. Listed here so the rebuild can
# clear all of them and set only what was asked for.
_SIGMA_SHAPE_FLAGS: dict[str, str] = {
    "karras": "use_karras_sigmas",
    "exponential": "use_exponential_sigmas",
    "beta": "use_beta_sigmas",
}


def _request_scoped_config_keys() -> frozenset[str]:
    """Every config key this module sets on behalf of ONE request.

    All of them must be cleared before the next rebuild, or the previous render's choice survives.
    Derived from the two tables rather than restated, because listing them by hand is how
    algorithm_type was missed the first time: stripping only the sigma flags left the SDE variant
    switched on for a later plain dpmpp_2m request.
    """
    keys = set(_SIGMA_SHAPE_FLAGS.values())
    for extra in _SAMPLER_EXTRA_CONFIG.values():
        keys.update(extra)
    return frozenset(keys)


_FLOW_MATCH_IMPORTS: dict[str, tuple[str, str]] = {
    "euler": ("diffusers.schedulers.scheduling_flow_match_euler_discrete",
              "FlowMatchEulerDiscreteScheduler"),
    "heun": ("diffusers.schedulers.scheduling_flow_match_heun_discrete",
             "FlowMatchHeunDiscreteScheduler"),
    "lcm": ("diffusers.schedulers.scheduling_flow_match_lcm", "FlowMatchLCMScheduler"),
}


def pipeline_is_flow_matching(pipe: Any) -> bool:
    """Whether this pipeline samples a flow-matching formulation.

    Asked of the LIVE pipeline -- the class of the scheduler diffusers itself chose when loading the
    checkpoint -- rather than of a family table. A family table would be a second resolver that has
    to be kept in step with what diffusers actually does, and it would be wrong the first time a
    checkpoint routed somewhere its filename did not predict.
    """
    scheduler = getattr(pipe, "scheduler", None)
    return type(scheduler).__name__.startswith("FlowMatch") if scheduler is not None else False


def _load_scheduler_class(sampler_name: str, *, flow_match: bool = False) -> Any:
    table = _FLOW_MATCH_IMPORTS if flow_match else _SCHEDULER_IMPORTS
    import_spec = table.get(sampler_name)
    if import_spec is None:
        return None
    module_name, class_name = import_spec
    try:
        return getattr(importlib.import_module(module_name), class_name)
    except Exception:
        return None


def apply_sampler_and_scheduler(pipe: Any, req: dict[str, Any]) -> dict[str, Any]:
    if pipe is None or not hasattr(pipe, "scheduler"):
        return {"applied": False, "sampler": None, "scheduler": None}

    sampler_name = str(req.get("sampler") or "").strip().lower()
    scheduler_name = str(req.get("scheduler") or "").strip().lower()

    flow_match = pipeline_is_flow_matching(pipe)
    scheduler_cls = _load_scheduler_class(sampler_name, flow_match=flow_match)
    if scheduler_cls is None:
        # The pipeline keeps its own default and the render still succeeds, so without this line the
        # user asks for one sampler, silently gets another, and nothing anywhere says so. WARNING
        # because the root logger sits there and anything below it is invisible (CLAUDE.md s4).
        # The sidecar records the same fact durably as sampler_applied=False.
        if sampler_name:
            logging.warning(
                "Sampler %r has no %s scheduler mapping; the pipeline default (%s) was used "
                "instead. Recorded in the metadata as sampler_applied=false.",
                sampler_name,
                "flow-matching" if flow_match else "diffusers",
                type(getattr(pipe, "scheduler", None)).__name__)
        return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}

    extra_config: dict[str, Any] = dict(_SAMPLER_EXTRA_CONFIG.get(sampler_name, {}))
    # Sigma-schedule shaping is meaningless on a flow-matching scheduler -- there is no sigma
    # schedule to reshape -- so the flag is dropped rather than passed and silently ignored, and the
    # returned scheduler name reflects what was actually used.
    if flow_match:
        scheduler_name = ""
    elif scheduler_name in _SIGMA_SHAPE_FLAGS:
        extra_config[_SIGMA_SHAPE_FLAGS[scheduler_name]] = True

    # Build from a config with EVERY shaping flag stripped, then set only the one asked for.
    #
    # Without this the flags are sticky, because the rebuild reads pipe.scheduler.config -- the
    # PREVIOUS render's config, on a pipeline the worker deliberately keeps warm. Measured on one
    # loaded SDXL pipeline: request dpmpp_2m + karras, then request dpmpp_2m + NORMAL, and
    # use_karras_sigmas is still true; the second image is byte-identical to the first (MAD 0.00)
    # and differs from the same request on a clean load by MAD 41.61. So switching a scheduler back
    # did nothing until the model was reloaded -- the user states a value and the software keeps the
    # old one.
    base_config = dict(pipe.scheduler.config)
    for key in _request_scoped_config_keys():
        base_config.pop(key, None)

    try:
        new_scheduler, dropped = _scheduler_from_config(scheduler_cls, base_config, **extra_config)
        if new_scheduler is not None:
            pipe.scheduler = new_scheduler
            applied_scheduler = scheduler_name
            if scheduler_name and _SIGMA_SHAPE_FLAGS.get(scheduler_name) in dropped:
                # The sampler took, the sigma shaping did not. Reporting the scheduler as applied
                # here is what made "ddim + karras" look like a working default.
                applied_scheduler = ""
            return {
                "applied": True,
                "sampler": sampler_name or None,
                "scheduler": applied_scheduler or None,
                "scheduler_requested": scheduler_name or None,
                "scheduler_applied": bool(applied_scheduler) if scheduler_name else None,
                "scheduler_class": scheduler_cls.__name__,
            }
    except Exception as exc:
        return {
            "applied": False,
            "sampler": sampler_name or None,
            "scheduler": scheduler_name or None,
            "error": str(exc),
        }

    return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}


def build_generation_kwargs(
    req: dict[str, Any],
    generator: torch.Generator,
    extra: dict[str, Any] | None = None,
    pipe: Any = None,
) -> dict[str, Any]:
    prompt = req["prompt"]
    negative = req.get("negative_prompt") or ""

    kwargs: dict[str, Any] = {
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
    }

    # OPTION B routing (see note above): native string path unless the prompt needs sd_embed.
    if pipe is not None and _ws()._prompt_needs_weighted_embeds(pipe, prompt, negative):
        from sd_embed.embedding_funcs import get_weighted_text_embeddings_sdxl

        pe, npe, ppe, nppe = get_weighted_text_embeddings_sdxl(pipe, prompt=prompt, neg_prompt=negative)
        # MUST NOT also pass prompt=/negative_prompt= -- diffusers rejects string + embeds together.
        kwargs["prompt_embeds"] = pe
        kwargs["pooled_prompt_embeds"] = ppe
        kwargs["negative_prompt_embeds"] = npe
        kwargs["negative_pooled_prompt_embeds"] = nppe
        logging.warning(
            "[long-prompt] sd_embed embed path: prompt_chars=%d weighting=%s (>77 tokens or (word:w) syntax)",
            len(prompt),
            _ws()._has_weighting_syntax(prompt) or _ws()._has_weighting_syntax(negative),
        )
    else:
        kwargs["prompt"] = prompt
        if req.get("negative_prompt"):
            kwargs["negative_prompt"] = req["negative_prompt"]

    if extra:
        kwargs.update(extra)

    return kwargs


def attach_progress_callback(
    pipe: Any,
    kwargs: dict[str, Any],
    req: dict[str, Any],
    emitter: JobEmitter,
    job: JobRecord,
    active_job: ActiveJobHandle,
) -> None:
    total_steps = int(req["steps"])
    signature = inspect.signature(pipe.__call__)

    def step_end_callback(_pipe: Any, step_index: int, _timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step_index + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step_index + 1, total_steps, f"running step {step_index + 1}/{total_steps}")
        return callback_kwargs

    def legacy_callback(step: int, _timestep: Any, _latents: Any) -> None:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step + 1, total_steps, f"running step {step + 1}/{total_steps}")

    if "callback_on_step_end" in signature.parameters:
        kwargs["callback_on_step_end"] = step_end_callback
    elif "callback" in signature.parameters:
        kwargs["callback"] = legacy_callback
        kwargs["callback_steps"] = 1


def maybe_apply_ipadapter(pipe, req: dict[str, Any], weight: float, emitter=None, job=None) -> tuple[bool, str]:
    """Best-effort IP-Adapter attach for pose/style-flexible I2I.

    Returns (applied, note). Never raises for missing files/APIs — Character Studio
    still works via pure denoise when adapters are absent.
    """
    if pipe is None or not hasattr(pipe, "load_ip_adapter"):
        return False, "pipeline has no load_ip_adapter"

    candidates: list[str] = []
    for key in ("ipadapter_file", "ip_adapter_path", "ipadapter_path"):
        raw = str(req.get(key) or "").strip()
        if raw:
            candidates.append(raw)

    roots: list[Path] = []
    for env_key in ("SPELLVISION_MODELS_ROOT", "SPELLVISION_ASSETS_ROOT"):
        v = os.environ.get(env_key, "").strip()
        if v:
            roots.append(Path(v))
    roots.extend(
        [
            Path(os.environ.get("SPELLVISION_MODELS", "").strip())
            if os.environ.get("SPELLVISION_MODELS", "").strip()
            else None,
        ]
    )
    roots = [r for r in roots if r is not None]
    subdirs = ("ipadapter", "ip_adapter", "IP-Adapter", "ip-adapter")
    name_hints = (
        "ip-adapter-plus_sdxl_vit-h",
        "ip-adapter-plus-face_sdxl_vit-h",
        "ip-adapter_sdxl",
        "ip-adapter-plus_sd15",
        "ip-adapter_sd15",
    )
    if not candidates:
        for root in roots:
            if not root.exists():
                continue
            for sub in subdirs:
                folder = root / sub
                if not folder.exists():
                    continue
                for hint in name_hints:
                    for ext in (".safetensors", ".bin"):
                        hit = folder / f"{hint}{ext}"
                        if hit.exists():
                            candidates.append(str(hit))
                for p in folder.rglob("*"):
                    if p.is_file() and "ip-adapter" in p.name.lower() and p.suffix.lower() in {".safetensors", ".bin"}:
                        candidates.append(str(p))
            if candidates:
                break

    if not candidates:
        return False, "no ip-adapter weights found under models/ipadapter"

    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        key = os.path.normcase(os.path.abspath(c))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(c):
            unique.append(c)

    if not unique:
        return False, "ip-adapter candidates missing on disk"

    weight = max(0.05, min(1.0, float(weight)))
    last_err = ""
    for path in unique[:6]:
        try:
            folder = str(Path(path).parent)
            name = Path(path).name
            try:
                pipe.load_ip_adapter(folder, subfolder="", weight_name=name)
            except TypeError:
                pipe.load_ip_adapter(folder, weight_name=name)
            if hasattr(pipe, "set_ip_adapter_scale"):
                try:
                    pipe.set_ip_adapter_scale(weight)
                except Exception:
                    pipe.set_ip_adapter_scale([weight])
            note = f"loaded {name} @ {weight:.2f}"
            logging.warning("IP-Adapter applied: %s", note)
            if emitter is not None and job is not None:
                try:
                    emitter.status(job, f"ip-adapter: {note}")
                except Exception:
                    pass
            return True, note
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue
    return False, f"load failed: {last_err[:160]}"


def maybe_apply_request_upscale(
    req: dict[str, Any],
    image_path: str,
    emitter: JobEmitter | None = None,
    job: JobRecord | None = None,
) -> str:
    """Optional post-gen upscale driven by UI payload (algorithmic or model).

    Algorithmic path uses PIL. Model path tries RealESRGAN/basicsr when present; otherwise
    falls back to lanczos with a warning. Never fabricates success.
    """
    enabled = bool(req.get("upscale_enabled"))
    method = str(req.get("upscale_method") or "none").strip().lower()
    if not enabled or method in {"", "none", "off", "false", "0"}:
        return image_path

    try:
        scale = bounded_option(req, "upscale_scale", 2.0)
    except (TypeError, ValueError):
        scale = 2.0
    scale = max(1.0, min(scale, 4.0))
    if scale <= 1.01 and method != "model":
        return image_path

    path = Path(image_path)
    if not path.is_file():
        return image_path

    if emitter is not None and job is not None:
        try:
            emitter.status(job, f"upscaling ×{scale:g} ({method})")
        except Exception:
            pass

    try:
        from PIL import Image as PILImage  # type: ignore
    except Exception as exc:  # pragma: no cover
        logging.warning("[upscale] PIL unavailable: %s", exc)
        return image_path

    try:
        with PILImage.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            tw, th = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
            out = im

            if method == "model":
                model_name = str(req.get("upscale_model_name") or req.get("upscale_model") or "").strip()
                used_model = False
                # Best-effort RealESRGAN path; fall back cleanly.
                try:
                    # Optional dependency — many installs lack it.
                    from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore
                    from realesrgan import RealESRGANer  # type: ignore

                    models_root = str(req.get("models_root") or "").strip()
                    model_path = model_name
                    if model_path and not Path(model_path).is_file() and models_root:
                        cand = Path(models_root) / "upscale_models" / model_path
                        if cand.is_file():
                            model_path = str(cand)
                    if model_path and Path(model_path).is_file():
                        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
                        upsampler = RealESRGANer(scale=4, model_path=model_path, model=net, tile=0, half=False)
                        import numpy as np  # type: ignore

                        arr = np.array(im)[:, :, ::-1]  # RGB->BGR
                        output, _ = upsampler.enhance(arr, outscale=scale)
                        out = PILImage.fromarray(output[:, :, ::-1])
                        used_model = True
                except Exception as exc:
                    logging.warning("[upscale] model path failed (%s); falling back to lanczos", exc)

                if not used_model:
                    method = "lanczos"

            if method != "model":
                resample = {
                    "nearest": PILImage.Resampling.NEAREST,
                    "bilinear": PILImage.Resampling.BILINEAR,
                    "bicubic": PILImage.Resampling.BICUBIC,
                    "lanczos": PILImage.Resampling.LANCZOS,
                }.get(method, PILImage.Resampling.LANCZOS)
                out = im.resize((tw, th), resample)

            out_path = path.with_name(f"{path.stem}_up{scale:g}{path.suffix}")
            out.save(out_path, "PNG")
            # Prefer replacing original output so UI/history still point at the final asset.
            try:
                out_path.replace(path)
                final = str(path)
            except Exception:
                final = str(out_path)
                req["output"] = final
            logging.warning("[upscale] wrote %s via %s ×%s", final, method, scale)
            return final
    except Exception as exc:
        logging.warning("[upscale] failed: %s", exc)
        return image_path


REQUIRED_IMAGE_REQUEST_KEYS = ("model", "prompt", "output", "metadata_output",
                               "width", "height", "steps", "cfg", "seed")


def require_request_keys(req: dict[str, Any], command: str, *extra: str) -> None:
    """Fail with a message that names what is missing, before any model is loaded.

    These runners read the request with bare subscripts in 33 places, so a caller that omits one
    field surfaced as ``KeyError: 'output'`` -- raised deep inside the run, AFTER a multi-gigabyte
    pipeline load and a full sampling pass, with nothing saying which caller or which field. Found
    exactly that way while measuring the SDXL operating point: two consecutive runs died on
    ``'output'`` and then ``'metadata_output'``, one field per attempt.

    Checked up front instead, so a malformed request costs nothing and says what to fix. The UI
    always sends these; the callers that can get it wrong are the chain engine, dataset generation,
    a requeue from history, and anything driving the worker protocol directly.
    """
    missing = [key for key in (*REQUIRED_IMAGE_REQUEST_KEYS, *extra) if key not in req]
    if missing:
        raise ValueError(
            f"{command} request is missing required field(s): {', '.join(missing)}. "
            f"Present: {', '.join(sorted(req)) or 'nothing'}."
        )


def run_t2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    if _should_route_native_image({**req, "command": "t2i"}):
        raise RuntimeError(
            "This checkpoint is a native Comfy family (Krea 2 / Flux / …) and cannot load through "
            "diffusers from_single_file. Restart SpellVision so the worker picks up native routing."
        )
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)
    # Validated AFTER the QUEUED -> STARTING transition, not before it, and the ordering is
    # load-bearing. The state machine permits QUEUED -> {STARTING, CANCELLED} only, so a raise
    # while the item is still QUEUED cannot be recorded as FAILED -- the error lands on the item
    # but its state stays "queued" and it never drains. Caught by the e2e lifecycle test when this
    # guard first ran one line too early.
    #
    # Everything expensive is still downstream: the transition costs nothing, and the pipeline load
    # has not started.
    require_request_keys(req, "t2i")
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    pipe, _, device, dtype, detected, cache_hit, model_swap_cleanup = _ws().get_or_load_pipelines(req["model"], req.get("model_family"))
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    lora_path, lora_scale = resolve_request_lora(req)
    if lora_path:
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, lora_path, lora_scale, "t2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "t2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "width": int(req["width"]),
            "height": int(req["height"]),
        },
        pipe=pipe,
    )
    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")
    maybe_apply_request_upscale(req, req["output"], emitter, job)

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
        scheduler_stats=scheduler_stats,
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        **worker_vram().payload(),
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
        "active_adapters": active_adapter_names(pipe),
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=_ws().output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **_ws().runtime_prep_metadata(req),
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_i2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)
    # Validated AFTER the QUEUED -> STARTING transition, not before it, and the ordering is
    # load-bearing. The state machine permits QUEUED -> {STARTING, CANCELLED} only, so a raise
    # while the item is still QUEUED cannot be recorded as FAILED -- the error lands on the item
    # but its state stays "queued" and it never drains. Caught by the e2e lifecycle test when this
    # guard first ran one line too early.
    #
    # Everything expensive is still downstream: the transition costs nothing, and the pipeline load
    # has not started.
    require_request_keys(req, "i2i", "input_image")
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    _, pipe, device, dtype, detected, cache_hit, model_swap_cleanup = _ws().get_or_load_pipelines(req["model"], req.get("model_family"))
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    lora_path, lora_scale = resolve_request_lora(req)
    if lora_path:
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, lora_path, lora_scale, "i2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "i2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    input_image = Image.open(req["input_image"]).convert("RGB")
    raise_if_cancelled(active_job, emitter, "input image preparation")

    # Resolve I2I strength / denoise. Character Studio "Reference freedom" sends
    # denoise_strength (higher = freer pose). Prefer explicit strength, then denoise_strength.
    strength_raw = req.get("strength", None)
    if strength_raw is None or str(strength_raw).strip() in {"", "None"}:
        strength_raw = req.get("denoise_strength", req.get("denoise", 0.6))
    try:
        strength = float(strength_raw)
    except Exception:
        strength = 0.6
    strength = max(0.05, min(0.99, strength))

    # pose_flexible: never clamp so hard that the photo locks the pose (floor 0.55).
    ref_mode = str(req.get("reference_mode") or "").strip().lower()
    if ref_mode in {"pose_flexible", "ipadapter_soft", "style"}:
        strength = max(strength, 0.55)

    ipadapter_weight = None
    try:
        if req.get("ipadapter_weight") is not None:
            ipadapter_weight = max(0.05, min(1.0, float(req.get("ipadapter_weight"))))
    except Exception:
        ipadapter_weight = None

    # Soft IP-Adapter path when available (diffusers IPAdapterMixin + ip_adapter weights on disk).
    # Never fails the job if missing — falls back to pure I2I denoise.
    ipadapter_applied = False
    ipadapter_note = ""
    if ref_mode in {"pose_flexible", "ipadapter_soft", "style"} or ipadapter_weight is not None:
        try:
            ipadapter_applied, ipadapter_note = maybe_apply_ipadapter(
                pipe,
                req,
                weight=ipadapter_weight if ipadapter_weight is not None else max(0.2, 1.0 - strength),
                emitter=emitter,
                job=job,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("IP-Adapter soft path skipped: %s", exc)
            ipadapter_note = f"skipped: {exc}"

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "image": input_image,
            "strength": strength,
        },
        pipe=pipe,
    )
    try:
        import inspect

        sig = inspect.signature(pipe.__call__)
        if ipadapter_applied and "ip_adapter_image" in sig.parameters:
            kwargs["ip_adapter_image"] = input_image
            if "ip_adapter_scale" in sig.parameters and ipadapter_weight is not None:
                kwargs["ip_adapter_scale"] = ipadapter_weight
    except Exception:
        pass

    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(
        job,
        f"running pipeline (i2i strength={strength:.2f}"
        + (f", ipadapter={ipadapter_note}" if ipadapter_note else "")
        + ")",
    )
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")
    maybe_apply_request_upscale(req, req["output"], emitter, job)

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
        scheduler_stats=scheduler_stats,
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        **worker_vram().payload(),
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
        "active_adapters": active_adapter_names(pipe),
        **_ws().runtime_prep_metadata(req),
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload

