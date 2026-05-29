$patch = @'
"""
Sprint 15D Pass 2: VRAM ordering fix for native video pipelines.

Fixes the bug in _load_native_video_pipeline where enable_model_cpu_offload()
was being called AFTER pipe.to(device). Diffusers offload methods install
accelerate hooks that manage device placement themselves; pre-moving to
CUDA defeats them and produces only marginal memory savings.

This patch routes the native video loader through memory_optimization.
apply_memory_profile, which enforces the correct ordering for all three
profiles:

  PERFORMANCE  - caller-managed pipe.to(device) AFTER attention/VAE opts
  BALANCED     - enable_model_cpu_offload(), NO pre-move to device
  LOW_VRAM     - enable_sequential_cpu_offload(), NO pre-move to device

Also adds request-driven memory_profile / enable_vae_tiling support and
records a video MemoryReport on VIDEO_RUNTIME_CACHE for telemetry.

Backwards compatible: when a request specifies enable_cpu_offload=True
(the previous default) without memory_profile, BALANCED is used —
behaviorally equivalent to the old code's intent, but with the ordering
bug fixed so the savings are real.

Prerequisite: python/memory_optimization.py must exist.
"""
from pathlib import Path
path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

memopt_check = Path("python/memory_optimization.py")
if not memopt_check.exists():
    raise SystemExit(
        "python/memory_optimization.py is missing. Drop the module file into "
        "python/ before running this patch."
    )

needle = '''        try:
            pipe = optimize_pipeline(pipe.to(device), device)
        except Exception:
            try:
                pipe.to(device)
            except Exception:
                pass

        try:
            if hasattr(pipe, "enable_model_cpu_offload") and bool(req.get("enable_cpu_offload", True)):
                pipe.enable_model_cpu_offload()
        except Exception:
            pass

        return pipe, device, str(dtype), class_name
'''

replacement = '''        # Sprint 15D Pass 2: VRAM ordering fix for native video pipelines.
        #
        # The previous code called pipe.to(device) BEFORE
        # enable_model_cpu_offload(). The diffusers docs are explicit that
        # offload methods install accelerate hooks that manage device
        # placement themselves; pre-moving to CUDA defeats them and the
        # gain in memory consumption is otherwise marginal because the
        # weights have already been allocated on the GPU.
        #
        # We now route through memory_optimization.apply_memory_profile,
        # which enforces the correct ordering for PERFORMANCE / BALANCED /
        # LOW_VRAM.
        from memory_optimization import (
            MemoryProfile,
            apply_attention_optimizations,
            apply_memory_profile,
            coerce_memory_profile,
            memory_report,
        )

        # Pick a profile from the request, preserving the previous
        # "enable_cpu_offload=True by default" behavior when no explicit
        # profile is supplied — that maps cleanly to BALANCED.
        requested_profile = req.get("memory_profile")
        if requested_profile is None:
            profile = (
                MemoryProfile.BALANCED
                if bool(req.get("enable_cpu_offload", True))
                else MemoryProfile.PERFORMANCE
            )
        else:
            profile = coerce_memory_profile(requested_profile)

        # Attention/VAE slicing first — these mutate submodules in place
        # and have no device-placement side effects.
        opt_notes = apply_attention_optimizations(
            pipe,
            device=device,
            enable_vae_tiling=bool(req.get("enable_vae_tiling", False)),
        )

        # Then the offload strategy. For PERFORMANCE this is a no-op
        # record and we move to device ourselves below. For BALANCED /
        # LOW_VRAM the offload methods manage device placement themselves
        # and we MUST NOT pre-move.
        profile_notes = apply_memory_profile(pipe, profile=profile, device=device)

        if profile == MemoryProfile.PERFORMANCE and device == "cuda":
            try:
                pipe = pipe.to(device)
            except Exception:
                pass

        # Stash the video memory report for telemetry / debugging. Safe
        # under exception because the cache is best-effort.
        try:
            with VIDEO_RUNTIME_LOCK:
                VIDEO_RUNTIME_CACHE["last_memory_report"] = memory_report(
                    pipe, profile, opt_notes + profile_notes
                ).to_dict()
        except Exception:
            pass

        return pipe, device, str(dtype), class_name
'''

if needle not in text:
    raise SystemExit("Could not find native video loader offload block in worker_service.py")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
print("Applied Sprint 15D Pass 2: native video loader uses correct offload ordering.")
'@
Set-Content .\scripts\refactors\apply_sprint15d_pass2_native_video_loader.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_sprint15d_pass2_native_video_loader.py
