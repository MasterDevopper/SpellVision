"""
memory_optimization.py
======================

VRAM optimization helpers for SpellVision's diffusers-based image worker.

Problem this module solves
--------------------------

``worker_service.build_pipelines()`` historically instantiated the text-to-image
and image-to-image pipelines as two independent ``from_pretrained`` /
``from_single_file`` calls. For SDXL that means two complete copies of the
UNet (~2.6 GB fp16 each), the VAE (~0.3 GB), and the dual CLIP text encoders
(~0.7 GB combined) sitting on the GPU at once — roughly 14 GB resident for a
checkpoint that should occupy ~7 GB.

Layered on top of that, the worker never enabled CPU offloading for image
pipelines (only for native video), and ``variant="fp16"`` was only requested
on the ``from_pretrained`` path, never on ``from_single_file``. Community
single-file SDXL checkpoints have no fp16 variant on disk, so even when
``torch_dtype=torch.float16`` is requested, the actual UNet parameters could
silently end up at fp32 — doubling VRAM again with no visible warning.

What this module provides
-------------------------

1. ``build_paired_pipelines`` — loads the t2i pipeline normally, then
   constructs its img2img companion via ``DiffusionPipeline.from_pipe`` so
   every submodel (UNet, VAE, text_encoder, text_encoder_2, scheduler, ...)
   is shared by reference rather than duplicated. Falls back to
   ``**pipe.components`` on older diffusers releases that predate
   ``from_pipe``.

2. ``MemoryProfile`` — a three-step strategy enum:

   ===============  ==========================================  =========
   PERFORMANCE      no offloading, pipeline pinned to GPU       fastest
   BALANCED         ``enable_model_cpu_offload``                ~50% VRAM
   LOW_VRAM         ``enable_sequential_cpu_offload``           lowest VRAM
   ===============  ==========================================  =========

   ``auto_select_memory_profile`` picks one based on the GPU's total VRAM.

3. ``apply_memory_profile`` — applies the chosen offload strategy correctly.
   ``from_pipe`` siblings share weights but maintain independent
   execution-order hooks, so offload methods MUST be re-applied per pipeline
   after ``from_pipe`` rather than inherited. This module enforces that
   ordering.

4. ``apply_attention_optimizations`` — attention slicing, VAE slicing,
   optional VAE tiling for high-res generation, and a silent xformers
   attempt (PyTorch 2's built-in SDPA covers this case on torch >= 2 so
   missing xformers is no longer worth warning about).

5. ``resident_dtype`` / ``memory_report`` — diagnostics that catch silent
   fp32 fallback by reading the actual dtype off a UNet parameter after
   the load completes.

Integration into worker_service.py
----------------------------------

Replace the body of ``build_pipelines`` with a single call to
``build_paired_pipelines``. The new function returns a structured result
containing the same five values the old function returned, plus a
``MemoryReport`` for telemetry / logging.

A minimal integration looks like::

    from memory_optimization import (
        MemoryProfile,
        auto_select_memory_profile,
        build_paired_pipelines,
    )

    def build_pipelines(model_name_or_path):
        result = build_paired_pipelines(
            model_name_or_path,
            detect_pipeline_type=detect_pipeline_type,
            profile=auto_select_memory_profile(),
        )
        # Old four-return-value shape preserved for upstream callers:
        return (
            result.t2i_pipe,
            result.i2i_pipe,
            result.device,
            result.dtype_str,
            result.detected,
        )

To surface the report, store ``result.report`` on ``MODEL_CACHE`` and include
it in the worker's load-acknowledgement response so the UI can show real
VRAM figures instead of the current ``VRAM: active/idle`` placeholder.

References
----------

- Diffusers "Reduce memory usage":
  https://huggingface.co/docs/diffusers/optimization/memory
- ``DiffusionPipeline.from_pipe`` semantics:
  https://huggingface.co/docs/diffusers/using-diffusers/loading
- "Exploring simple optimizations for SDXL":
  https://huggingface.co/blog/simple_sdxl_optimizations
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import torch

# diffusers pipeline classes are imported lazily inside the builder so this
# module can be imported in environments where diffusers is not installed
# (e.g. lightweight tooling, lint runs). The lazy import also keeps the cold
# start of the worker process down — the diffusers import graph is heavy.


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------


class MemoryProfile(str, enum.Enum):
    """How aggressively to trade throughput for VRAM headroom.

    Members
    -------
    PERFORMANCE
        No offloading. Pipeline submodules stay on the GPU between calls.
        Lowest latency, highest VRAM. Default for systems with comfortable
        headroom (>= 16 GB VRAM for SDXL at 1024x1024).

    BALANCED
        ``enable_model_cpu_offload()`` — submodels move CPU<->GPU around
        each ``__call__`` based on the pipeline's execution order. For
        SDXL this typically brings resident VRAM from ~7 GB to ~3-4 GB
        with a ~10-20% inference time cost.

    LOW_VRAM
        ``enable_sequential_cpu_offload()`` — layer-level offloading. SDXL
        fits in ~2 GB but inference is roughly 2-3x slower. Useful for
        ~6 GB consumer cards.
    """

    PERFORMANCE = "performance"
    BALANCED = "balanced"
    LOW_VRAM = "low_vram"


def cuda_available() -> bool:
    """Thin wrapper so the rest of the module doesn't import torch directly
    in hot-path checks (and so tests can monkeypatch one place)."""
    return torch.cuda.is_available()


def select_torch_dtype() -> tuple[torch.dtype, str]:
    """Return ``(dtype, device)`` for the local environment.

    Returns
    -------
    tuple[torch.dtype, str]
        ``(torch.float16, "cuda")`` when CUDA is available, otherwise
        ``(torch.float32, "cpu")``. bfloat16 is supported on Ampere+ but
        fp16 is the universally-compatible choice for SDXL checkpoints
        downloaded from civitai/HF, which is the dominant case here.
    """
    if cuda_available():
        return torch.float16, "cuda"
    return torch.float32, "cpu"


def auto_select_memory_profile(
    *,
    performance_threshold_gb: float = 16.0,
    balanced_threshold_gb: float = 8.0,
) -> MemoryProfile:
    """Pick a memory profile based on the primary GPU's total VRAM.

    Heuristic targets SDXL-class models at 1024x1024:

    - >= 16 GB: PERFORMANCE (room for SDXL + LoRA + batch=2 comfortably).
    - 8 GB - 16 GB: BALANCED (model offload gets SDXL into ~4 GB resident,
      leaving headroom for the OS and other GPU consumers).
    - < 8 GB: LOW_VRAM (sequential offload is the only way SDXL fits).

    Parameters
    ----------
    performance_threshold_gb : float
        VRAM at or above which PERFORMANCE is selected. Default 16 GB.
    balanced_threshold_gb : float
        VRAM at or above which BALANCED is selected (otherwise LOW_VRAM).
        Default 8 GB.

    Returns
    -------
    MemoryProfile
    """
    if not cuda_available():
        # On CPU, none of these knobs apply. Return PERFORMANCE so we don't
        # accidentally call enable_*_cpu_offload on a CPU pipeline.
        return MemoryProfile.PERFORMANCE

    from vram import worker_vram

    total_gb = worker_vram().total_gb
    if total_gb is None:  # pragma: no cover - defensive, depends on driver
        log.warning("Could not query GPU memory; defaulting to BALANCED profile")
        return MemoryProfile.BALANCED

    if total_gb >= performance_threshold_gb:
        return MemoryProfile.PERFORMANCE
    if total_gb >= balanced_threshold_gb:
        return MemoryProfile.BALANCED
    return MemoryProfile.LOW_VRAM


def comfy_text_encoder_device(
    *,
    profile: "MemoryProfile | None" = None,
    requested: Any = None,
) -> str:
    """Which device a ComfyUI ``CLIPLoader`` should put a large text encoder on.

    Returns ``"default"`` (let ComfyUI place it, normally VRAM) or ``"cpu"``.

    Grounded against a live ``/object_info`` read, not a workflow: ``CLIPLoader`` takes an
    OPTIONAL ``device`` whose choices are exactly ``["default", "cpu"]``, flagged ``advanced``.
    Anything else is a 400 from ComfyUI.

    This exists because the Krea 2 reference workflow hardcodes ``cpu``. Copying that would have
    pinned every machine to the author's trade-off: a 4B encoder on the CPU costs encode latency on
    every generation, which is the wrong default on a card with headroom and the right one on a
    card without. So it is routed through the same profile the diffusers path already uses --
    PERFORMANCE keeps the encoder resident, BALANCED and LOW_VRAM push it to system RAM to leave
    VRAM for the transformer and the VAE decode.

    An explicit request value always wins; the profile only decides when nothing was asked for.
    """
    if requested is not None:
        wanted = str(requested).strip().lower()
        # Only the two values the live schema accepts. An unrecognised string is ignored rather
        # than forwarded, because forwarding it turns a typo into a failed generation.
        if wanted in {"default", "cpu"}:
            return wanted
        if wanted in {"gpu", "cuda"}:
            return "default"
        log.warning("Ignoring unsupported text encoder device %r; using the profile default.", requested)

    resolved = profile if profile is not None else auto_select_memory_profile()
    return "default" if resolved == MemoryProfile.PERFORMANCE else "cpu"


# ---------------------------------------------------------------------------
# Optimization application
# ---------------------------------------------------------------------------


def apply_attention_optimizations(
    pipe: Any,
    *,
    device: str,
    enable_vae_tiling: bool = False,
    enable_attention_slicing: bool = True,
) -> list[str]:
    """Enable attention slicing, VAE slicing, optional VAE tiling, and
    xformers attention if available.

    These optimizations operate at the submodule level. Because t2i and i2i
    companions share submodules (via ``from_pipe``), calling this once on
    either pipeline propagates the effect to the other. We still expose it
    as a per-pipeline call because it's safe — internal hasattr checks
    silently skip already-enabled features.

    Parameters
    ----------
    pipe : DiffusionPipeline
        The pipeline to optimize. Must NOT yet have a CPU-offload strategy
        attached (those install hooks that interact poorly with slicing).
    device : str
        Either ``"cuda"`` or ``"cpu"``. xformers is only attempted on CUDA.
    enable_vae_tiling : bool
        If True, also enable VAE tiling. Tiling helps at high resolutions
        (>= 1536 px) where the VAE decode peak is the OOM trigger. Has no
        meaningful cost at 1024x1024, so callers may choose to enable it
        unconditionally on low-VRAM systems.

    Returns
    -------
    list[str]
        Human-readable notes describing what was applied. Used in the
        ``MemoryReport`` for telemetry.
    """
    notes: list[str] = []

    # Silence the per-call tqdm progress bar that diffusers writes to stdout.
    # The worker has its own progress plumbing through the JSON socket
    # protocol; the diffusers bar would interleave with that and break the
    # parser.
    if hasattr(pipe, "set_progress_bar_config"):
        try:
            pipe.set_progress_bar_config(disable=True)
        except Exception:
            pass

    # Attention slicing: small peak-VRAM savings during the denoising loop, at a ~5-10% speed
    # cost. Pre-PyTorch-2 SDPA this was a big deal; on torch>=2 it only earns its keep under
    # real VRAM pressure. On a PERFORMANCE-profile card there is no pressure to trade against,
    # so the caller turns it off and the denoise loop keeps that 5-10%.
    if enable_attention_slicing and hasattr(pipe, "enable_attention_slicing"):
        try:
            pipe.enable_attention_slicing()
            notes.append("attention_slicing")
        except Exception as exc:
            log.debug("attention_slicing unavailable: %s", exc)
    elif not enable_attention_slicing:
        notes.append("attention_slicing_skipped_performance")

    # VAE slicing: split batched VAE decode into chunks. Minimal effect at
    # batch=1, real effect at batch >= 4. Safe to leave on.
    vae = getattr(pipe, "vae", None)
    if vae is not None and hasattr(vae, "enable_slicing"):
        try:
            vae.enable_slicing()
            notes.append("vae_slicing")
        except Exception as exc:
            log.debug("vae_slicing unavailable: %s", exc)

    # VAE tiling: spatial tiling of VAE decode. Important at high res
    # (1536+ px) where the VAE peak dominates. Off by default because at
    # 1024x1024 it's a small slowdown for no gain.
    if enable_vae_tiling and vae is not None and hasattr(vae, "enable_tiling"):
        try:
            vae.enable_tiling()
            notes.append("vae_tiling")
        except Exception as exc:
            log.debug("vae_tiling unavailable: %s", exc)

    # xformers memory-efficient attention. Since torch 2.0 the diffusers
    # default attention processor routes to torch.nn.functional.scaled_dot_
    # product_attention, which is competitive with xformers. We still try
    # xformers here for older torch installs but no longer log a warning
    # if it's not installed — that warning has caused user confusion in the
    # past ("why does it say xformers unavailable when my image generated
    # fine?").
    if device == "cuda" and hasattr(pipe, "enable_xformers_memory_efficient_attention"):
        try:
            pipe.enable_xformers_memory_efficient_attention()
            notes.append("xformers")
        except Exception:
            # SDPA covers this on torch>=2; silent fallback is correct.
            pass

    return notes


def apply_memory_profile(
    pipe: Any,
    *,
    profile: MemoryProfile,
    device: str,
) -> list[str]:
    """Apply the chosen offload strategy to a single pipeline.

    Ordering constraints
    --------------------

    - For ``PERFORMANCE``: the caller is responsible for calling
      ``pipe.to(device)`` themselves. This function is a no-op.
    - For ``BALANCED`` and ``LOW_VRAM``: the caller MUST NOT have called
      ``pipe.to(device)`` already. Both ``enable_model_cpu_offload()`` and
      ``enable_sequential_cpu_offload()`` install accelerate hooks that
      manage device placement themselves; pre-moving to CUDA defeats them
      and produces only marginal memory savings. The diffusers docs are
      explicit about this for sequential offload.

    Parameters
    ----------
    pipe : DiffusionPipeline
    profile : MemoryProfile
    device : str
        ``"cuda"`` or ``"cpu"``. Offloading is silently skipped on CPU.

    Returns
    -------
    list[str]
        Notes describing what was applied. Suitable for the MemoryReport.
    """
    notes: list[str] = []

    # Offloading is CUDA-only by definition (you can't offload from CPU).
    if device != "cuda":
        notes.append(f"profile={profile.value}_cpu_noop")
        return notes

    if profile == MemoryProfile.PERFORMANCE:
        # Caller handles .to(device); we record the choice and return.
        notes.append("profile=performance")
        return notes

    if profile == MemoryProfile.BALANCED:
        if hasattr(pipe, "enable_model_cpu_offload"):
            try:
                pipe.enable_model_cpu_offload()
                notes.append("model_cpu_offload")
            except Exception as exc:
                log.warning(
                    "enable_model_cpu_offload failed (falling back to "
                    "in-memory placement): %s",
                    exc,
                )
                # Fall back to plain GPU placement so the pipeline still works,
                # just with no memory savings.
                try:
                    pipe.to(device)
                    notes.append("fallback_to_device")
                except Exception:
                    notes.append("fallback_failed")
        else:
            notes.append("model_cpu_offload_unavailable")
        return notes

    if profile == MemoryProfile.LOW_VRAM:
        if hasattr(pipe, "enable_sequential_cpu_offload"):
            try:
                pipe.enable_sequential_cpu_offload()
                notes.append("sequential_cpu_offload")
            except Exception as exc:
                log.warning("enable_sequential_cpu_offload failed: %s", exc)
                # If sequential failed, try model offload as a partial
                # fallback before giving up entirely.
                try:
                    pipe.enable_model_cpu_offload()
                    notes.append("fallback_to_model_cpu_offload")
                except Exception:
                    try:
                        pipe.to(device)
                        notes.append("fallback_to_device")
                    except Exception:
                        notes.append("fallback_failed")
        else:
            notes.append("sequential_cpu_offload_unavailable")
        return notes

    # Unreachable in practice — keeps mypy / static checkers happy.
    return notes


def apply_global_torch_speed_flags() -> list[str]:
    """Set process-global torch flags that improve speed at no VRAM cost.

    Safe to call multiple times; the underlying flags are idempotent. We
    call this once during worker startup, not per-load.

    Returns
    -------
    list[str]
        Notes for the report.
    """
    notes: list[str] = []
    if not cuda_available():
        return notes

    # cuDNN autotuner picks the fastest convolution kernel for each input
    # shape. Diffusion pipelines reuse the same shapes across denoising
    # steps so this is a clear win after the first step warms up.
    try:
        torch.backends.cudnn.benchmark = True
        notes.append("cudnn_benchmark")
    except Exception:
        pass

    # TF32 on Ampere+. Faster matmul/conv with negligible accuracy loss in
    # the diffusion inference setting (it does not affect sampling determinism
    # in any user-visible way for the schedulers we use).
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        notes.append("tf32")
    except Exception:
        pass

    return notes


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def resident_dtype(pipe: Any) -> str:
    """Return the dtype of the UNet's first parameter as a string.

    This is the diagnostic that catches the silent-fp32-fallback case. When
    ``torch_dtype=torch.float16`` is requested but the checkpoint has no
    fp16 weights on disk and no fp16 variant in the snapshot, diffusers
    falls back to fp32 silently. The resident dtype is the only reliable
    way to tell — file size on disk doesn't, because storage dtype and
    runtime dtype can differ.

    Returns
    -------
    str
        e.g. ``"torch.float16"``, ``"torch.float32"``, or ``"unknown"``.
    """
    unet = getattr(pipe, "unet", None) or getattr(pipe, "transformer", None)
    if unet is None:
        return "unknown"
    try:
        return str(next(unet.parameters()).dtype)
    except StopIteration:
        return "unknown"
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class MemoryReport:
    """Snapshot of GPU memory state and the strategy applied at load time.

    Embed this in the worker's load-ack response so the UI can show real
    VRAM figures and confirm the chosen profile to the user.
    """

    profile: str
    resident_dtype: str
    allocated_gb: float
    reserved_gb: float
    total_gb: float
    notes: list[str] = field(default_factory=list)


def memory_report(pipe: Any, profile: MemoryProfile, notes: list[str]) -> MemoryReport:
    """Build a ``MemoryReport`` from current CUDA state and the pipeline."""
    dtype_str = resident_dtype(pipe)

    from vram import worker_vram

    # Zeros here are the same defect as the four native payloads, one layer down: an unreadable
    # device and an idle one produced identical numbers. MemoryReport's fields are floats, so the
    # zeros stay -- but they are now the reader's zeros, taken when a reading succeeded.
    reading = worker_vram()
    allocated = reading.allocated_gb or 0.0
    reserved = reading.reserved_gb or 0.0
    total = reading.total_gb or 0.0

    return MemoryReport(
        profile=profile.value,
        resident_dtype=dtype_str,
        allocated_gb=round(allocated, 2),
        reserved_gb=round(reserved, 2),
        total_gb=round(total, 2),
        notes=list(notes),
    )


# ---------------------------------------------------------------------------
# The main entry point: build a shared-weight pair of pipelines
# ---------------------------------------------------------------------------


@dataclass
class PairedPipelinesResult:
    """Bundle returned by ``build_paired_pipelines``.

    Attributes
    ----------
    t2i_pipe : DiffusionPipeline
        Text-to-image pipeline. Ready to call.
    i2i_pipe : DiffusionPipeline
        Image-to-image companion. Shares all submodels with ``t2i_pipe``
        (UNet, VAE, text encoders, scheduler). Independent execution-order
        hooks for offloading.
    device : str
        ``"cuda"`` or ``"cpu"``.
    dtype_str : str
        Stringified ``torch.dtype`` that was requested at load time.
        Compare against ``report.resident_dtype`` to detect silent fp32
        fallback.
    detected : str
        Pipeline family detected from the checkpoint name: ``"sd"``,
        ``"sdxl"``, ``"sd3"``, or ``"flux"``.
    report : MemoryReport
        Snapshot of memory state after load + optimization.
    """

    t2i_pipe: Any
    i2i_pipe: Any
    device: str
    dtype_str: str
    detected: str
    report: MemoryReport


# Type alias for the family-detector callable the caller injects (typically
# ``worker_service.detect_pipeline_type``). It accepts the model path and an
# optional registry family tag, returning the pipeline type ("sd"/"sdxl"/...).
DetectPipelineTypeFn = Callable[..., str]


def _build_companion_img2img(t2i_pipe: Any, *, pipeline_cls: type) -> Any:
    """Construct an i2i companion pipeline that shares weights with ``t2i_pipe``.

    Uses ``DiffusionPipeline.from_pipe`` when available (diffusers >= 0.21);
    falls back to ``pipeline_cls(**t2i_pipe.components)`` for older releases.
    Both approaches produce a pipeline where every submodule is the same
    Python object as the t2i version — modifying weights in one is visible
    in the other, but each pipeline owns its own scheduler config view and
    its own offload hooks.

    Parameters
    ----------
    t2i_pipe : DiffusionPipeline
        Already-loaded text-to-image pipeline.
    pipeline_cls : type
        The img2img pipeline class (e.g. ``StableDiffusionXLImg2ImgPipeline``).

    Returns
    -------
    DiffusionPipeline
        The img2img companion pipeline.
    """
    # Preferred path: from_pipe is diffusers-canonical for "give me a sibling
    # pipeline that shares model state". Per the docs, it explicitly does
    # NOT duplicate weights.
    if hasattr(pipeline_cls, "from_pipe"):
        try:
            return pipeline_cls.from_pipe(t2i_pipe)
        except Exception as exc:
            log.warning(
                "%s.from_pipe(t2i) failed; falling back to **components: %s",
                pipeline_cls.__name__,
                exc,
            )

    # Fallback: explicit component sharing. ``pipe.components`` returns a
    # dict mapping each component name (unet, vae, text_encoder, ...) to
    # the live object. Reconstructing the i2i pipeline with these as kwargs
    # gives us the same shared-reference semantics.
    components = t2i_pipe.components
    return pipeline_cls(**components)


def build_paired_pipelines(
    model_name_or_path: str,
    *,
    detect_pipeline_type: DetectPipelineTypeFn,
    profile: Optional[MemoryProfile] = None,
    enable_vae_tiling: bool = False,
    use_safetensors_for_single_file: bool = True,
    cast_fp32_to_fp16: bool = True,
    requested_family: Optional[str] = None,
) -> PairedPipelinesResult:
    """Load a t2i pipeline and its weight-sharing i2i companion.

    This is the function ``worker_service.build_pipelines`` should call.
    It encapsulates:

    1. Detection of pipeline family (sd / sdxl / sd3 / flux).
    2. Choice of ``from_pretrained`` vs ``from_single_file`` loader.
    3. fp16 variant selection for ``from_pretrained`` paths.
    4. Building the i2i companion via ``from_pipe`` so weights are shared.
    5. Application of attention/VAE optimizations once (propagates via
       shared submodules).
    6. Application of the chosen offload profile per pipeline, in the
       order required by diffusers (offload hooks before ``.to(device)``).
    7. A MemoryReport for the load.

    Parameters
    ----------
    model_name_or_path : str
        Either a HuggingFace repo id, a local directory containing a
        diffusers snapshot, or a local ``.safetensors`` / ``.ckpt`` file.
    detect_pipeline_type : Callable[[str], str]
        Function that returns one of ``"sd"``, ``"sdxl"``, ``"sd3"``,
        ``"flux"``. Injected so this module doesn't duplicate the detection
        logic from ``worker_service``.
    profile : MemoryProfile, optional
        If ``None``, ``auto_select_memory_profile()`` is used.
    enable_vae_tiling : bool
        Forwarded to ``apply_attention_optimizations``. Useful for
        high-resolution (>= 1536 px) generation.
    use_safetensors_for_single_file : bool
        Forwarded to ``from_single_file``. Defaults to True; community
        checkpoints are almost universally safetensors now.

    Returns
    -------
    PairedPipelinesResult

    Raises
    ------
    RuntimeError
        If single-file loading is requested for SD3 or Flux (not currently
        supported by this worker) or for an SDXL-looking checkpoint that
        fails to load as SDXL (we explicitly do NOT silently fall back to
        the SD1.5 pipeline in that case — the resulting images would be
        garbage and the user wouldn't know why).
    """
    # Lazy imports so the diffusers dependency graph isn't paid by anyone
    # who just imports this module for its types.
    from diffusers.pipelines.auto_pipeline import AutoPipelineForText2Image
    from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion import (
        StableDiffusionPipeline,
    )
    from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_img2img import (
        StableDiffusionImg2ImgPipeline,
    )
    from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl import (
        StableDiffusionXLPipeline,
    )
    from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl_img2img import (
        StableDiffusionXLImg2ImgPipeline,
    )

    if profile is None:
        profile = auto_select_memory_profile()

    dtype, device = select_torch_dtype()
    detected = detect_pipeline_type(model_name_or_path, requested_family)

    log.info(
        "Loading pipeline: path=%s detected=%s dtype=%s device=%s profile=%s",
        model_name_or_path,
        detected,
        dtype,
        device,
        profile.value,
    )

    # ---- Step 1: build the t2i pipeline. ----
    #
    # The branching here mirrors the original worker_service logic but is
    # cleaned up: single-file paths take the ``from_single_file`` route,
    # everything else takes ``from_pretrained``. We DO NOT instantiate i2i
    # here — that happens in step 2 via from_pipe.
    is_local_file = _is_local_file(model_name_or_path)

    if is_local_file:
        if detected in {"flux", "sd3"}:
            raise RuntimeError(
                f"Direct local single-file loading for {detected.upper()} "
                f"checkpoints is not configured in the worker yet: "
                f"{model_name_or_path}"
            )

        if detected == "sdxl":
            # SDXL single-file. ``variant`` does not apply here — single-file
            # checkpoints are one safetensors blob, no fp16 sibling files. The
            # dtype that ends up resident is determined entirely by
            # ``torch_dtype``. We verify it after load via resident_dtype().
            try:
                t2i_pipe = StableDiffusionXLPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=use_safetensors_for_single_file,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"SDXL single-file load failed for {model_name_or_path}. "
                    f"SpellVision will not fall back to the legacy SD pipeline "
                    f"for a checkpoint that looks like SDXL. Original error: "
                    f"{exc}"
                ) from exc
        else:
            t2i_pipe = StableDiffusionPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=use_safetensors_for_single_file,
            )
            detected = "sd"
    else:
        # Repo id or local snapshot directory. ``variant="fp16"`` is meaningful
        # here: if the snapshot contains *.fp16.safetensors files, diffusers
        # will preferentially load those, which both reduces download size and
        # ensures the resident dtype matches the request.
        variant = "fp16" if device == "cuda" else None

        if detected == "sdxl":
            t2i_pipe = StableDiffusionXLPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant=variant,
            )
        else:
            t2i_pipe = AutoPipelineForText2Image.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )

    # ---- Step 2: build the i2i companion sharing all weights. ----
    #
    # This is the core VRAM fix. The i2i_pipe constructed below holds the
    # SAME Python objects for unet, vae, text_encoder, etc. as t2i_pipe —
    # not copies. Only the pipeline wrapper itself is new.
    if detected == "sdxl":
        i2i_cls = StableDiffusionXLImg2ImgPipeline
    else:
        i2i_cls = StableDiffusionImg2ImgPipeline

    i2i_pipe = _build_companion_img2img(t2i_pipe, pipeline_cls=i2i_cls)

    # ---- Step 3: apply attention/VAE optimizations. ----
    #
    # These mutate the shared submodules in place, so we only need to call
    # them once. We pick t2i_pipe for the call to keep symmetry with the
    # offload step (also called per-pipeline, but starting with t2i).
    optimization_notes = apply_attention_optimizations(
        t2i_pipe,
        device=device,
        enable_vae_tiling=enable_vae_tiling,
        # Slicing trades ~5-10% denoise speed for peak VRAM. PERFORMANCE means the card has
        # headroom to spare, so take the speed.
        enable_attention_slicing=(profile != MemoryProfile.PERFORMANCE),
    )

    # ---- Step 4: apply the offload profile. ----
    #
    # CRITICAL ORDERING:
    #
    # - For PERFORMANCE: call .to(device) on t2i_pipe; i2i_pipe automatically
    #   sees the now-CUDA-resident submodules because they're shared
    #   references. Calling .to(device) on i2i_pipe afterwards is a no-op
    #   but we do it anyway to keep the API symmetric and to handle the
    #   theoretical case where a future diffusers version tracks
    #   per-pipeline device state independently.
    #
    # - For BALANCED / LOW_VRAM: enable_*_cpu_offload installs accelerate
    #   hooks that manage device placement themselves. We MUST NOT pre-move
    #   to CUDA. The diffusers docs are explicit that offload methods must
    #   be re-applied on each from_pipe sibling because the execution-order
    #   hooks are per-pipeline.
    profile_notes_t2i = apply_memory_profile(t2i_pipe, profile=profile, device=device)

    # ---- VRAM Pass: fp32 -> fp16 cast for fp32-on-disk checkpoints. ----
    #
    # The checkpoint requested fp16 but diffusers may have silently loaded
    # fp32 (no fp16 weights on disk). resident_dtype() tells us the truth.
    # We cast WHILE STILL ON CPU so the fp32 weights never fully land in
    # VRAM -- only the fp16 result is moved to the GPU below. t2i and i2i
    # share submodule references, so casting t2i casts the shared weights.
    fp32_cast_applied = False
    if (
        cast_fp32_to_fp16
        and profile == MemoryProfile.PERFORMANCE
        and device == "cuda"
        and "float16" in str(dtype)
        and "float16" not in resident_dtype(t2i_pipe)
    ):
        try:
            # CPU-side cast: pipeline is not on the device yet at this point.
            t2i_pipe = t2i_pipe.to(torch.float16)
            try:
                i2i_pipe = i2i_pipe.to(torch.float16)
            except Exception:
                # Shared submodules are already fp16 via the t2i cast; an
                # error here just means the i2i wrapper had nothing to do.
                pass
            fp32_cast_applied = True
            # WARNING level (not INFO): this logger inherits the root
            # default of WARNING, and this line is the matched answer to
            # the "Silent dtype fallback detected" warning -- both should
            # be visible in the worker log.
            log.warning(
                "fp32->fp16 cast applied on CPU before device move "
                "(checkpoint had no fp16 weights on disk): %s",
                model_name_or_path,
            )
        except Exception as exc:
            # If the cast fails for any reason, fall through with the
            # fp32 pipeline intact -- correctness over memory savings.
            log.warning(
                "fp32->fp16 cast failed, continuing with fp32 resident "
                "(higher VRAM): %s",
                exc,
            )

    if profile == MemoryProfile.PERFORMANCE and device == "cuda":
        # Move shared weights to GPU once. The references in i2i_pipe see
        # the move automatically.
        t2i_pipe = t2i_pipe.to(device)
        # Calling .to on i2i is harmless and future-proofs against any
        # diffusers change that tracks device on the wrapper too.
        try:
            i2i_pipe = i2i_pipe.to(device)
        except Exception:
            # If diffusers ever errors when .to is called on a pipeline whose
            # submodules are already on the target device, swallow it — the
            # weights are already where they need to be.
            pass

    profile_notes_i2i = apply_memory_profile(i2i_pipe, profile=profile, device=device)

    # ---- Step 5: build the report. ----
    all_notes = (
        optimization_notes
        + [f"t2i:{n}" for n in profile_notes_t2i]
        + [f"i2i:{n}" for n in profile_notes_i2i]
        + apply_global_torch_speed_flags()
    )
    report = memory_report(t2i_pipe, profile, all_notes)

    # Surface a single info log line with everything important. This is the
    # primary diagnostic for "why is my VRAM still high?" — the resident
    # dtype, the chosen profile, and the actual allocated memory are all
    # right here.
    log.info(
        "Pipeline ready: detected=%s requested_dtype=%s resident_dtype=%s "
        "profile=%s allocated=%.2fGB reserved=%.2fGB total=%.2fGB notes=%s",
        detected,
        dtype,
        report.resident_dtype,
        profile.value,
        report.allocated_gb,
        report.reserved_gb,
        report.total_gb,
        ",".join(report.notes),
    )

    # Warn loudly if the resident dtype doesn't match what we asked for —
    # this is the silent-fp32-fallback case.
    if device == "cuda" and "float16" in str(dtype) and "float16" not in report.resident_dtype:
        log.warning(
            "Silent dtype fallback detected: requested %s but UNet parameters "
            "are %s. This roughly doubles VRAM usage. The checkpoint at %s "
            "likely has no fp16 weights on disk.",
            dtype,
            report.resident_dtype,
            model_name_or_path,
        )

    if fp32_cast_applied:
        report.notes.append("fp32_cast_to_fp16")

    return PairedPipelinesResult(
        t2i_pipe=t2i_pipe,
        i2i_pipe=i2i_pipe,
        device=device,
        dtype_str=str(dtype),
        detected=detected,
        report=report,
    )


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _is_local_file(path: str) -> bool:
    """Match worker_service.is_local_file semantics without importing it.

    Kept private to avoid suggesting callers should use this for general
    file-existence checks.
    """
    import os
    return os.path.isfile(path)
