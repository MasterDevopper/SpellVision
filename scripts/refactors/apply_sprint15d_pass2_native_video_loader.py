from pathlib import Path
path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

memopt_check = Path("python/memory_optimization.py")
if not memopt_check.exists():
    raise SystemExit("python/memory_optimization.py is missing.")

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
        from memory_optimization import (
            MemoryProfile,
            apply_attention_optimizations,
            apply_memory_profile,
            coerce_memory_profile,
            memory_report,
        )

        requested_profile = req.get("memory_profile")
        if requested_profile is None:
            profile = (
                MemoryProfile.BALANCED
                if bool(req.get("enable_cpu_offload", True))
                else MemoryProfile.PERFORMANCE
            )
        else:
            profile = coerce_memory_profile(requested_profile)

        opt_notes = apply_attention_optimizations(
            pipe,
            device=device,
            enable_vae_tiling=bool(req.get("enable_vae_tiling", False)),
        )

        profile_notes = apply_memory_profile(pipe, profile=profile, device=device)

        if profile == MemoryProfile.PERFORMANCE and device == "cuda":
            try:
                pipe = pipe.to(device)
            except Exception:
                pass

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
