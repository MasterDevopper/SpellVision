from pathlib import Path
path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

memopt_check = Path("python/memory_optimization.py")
if not memopt_check.exists():
    raise SystemExit("python/memory_optimization.py is missing.")

needle = '''def build_pipelines(model_name_or_path: str) -> tuple[Any, Any, str, str, str]:
    dtype, device = torch_dtype_and_device()
    detected = detect_pipeline_type(model_name_or_path)
    use_safetensors = model_name_or_path.lower().endswith(".safetensors")

    if is_local_file(model_name_or_path):
        if detected == "sdxl":
            try:
                t2i_pipe = StableDiffusionXLPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=use_safetensors,
                )
                i2i_pipe = StableDiffusionXLImg2ImgPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=use_safetensors,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load local SDXL checkpoint as an SDXL pipeline: {model_name_or_path}. "
                    f"SpellVision will not fall back to the legacy SD pipeline for a checkpoint that looks like SDXL. Original error: {exc}"
                ) from exc
        elif detected in {"flux", "sd3"}:
            raise RuntimeError(
                f"Direct local single-file loading for {detected.upper()} checkpoints is not configured in the worker yet: {model_name_or_path}"
            )
        else:
            t2i_pipe = StableDiffusionPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=use_safetensors,
            )
            i2i_pipe = StableDiffusionImg2ImgPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=use_safetensors,
            )
            detected = "sd"
    else:
        if detected == "sdxl":
            t2i_pipe = StableDiffusionXLPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
            i2i_pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
        else:
            t2i_pipe = AutoPipelineForText2Image.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )
            i2i_pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )

    t2i_pipe = optimize_pipeline(t2i_pipe.to(device), device)
    i2i_pipe = optimize_pipeline(i2i_pipe.to(device), device)

    return t2i_pipe, i2i_pipe, device, str(dtype), detected
'''

replacement = '''def build_pipelines(
    model_name_or_path: str,
    *,
    memory_profile: Any = None,
    enable_vae_tiling: bool = False,
) -> tuple[Any, Any, str, str, str]:
    """Sprint 15D Pass 1: VRAM-optimized image pipeline construction."""
    from memory_optimization import (
        build_paired_pipelines,
        coerce_memory_profile,
    )

    profile = coerce_memory_profile(memory_profile)

    result = build_paired_pipelines(
        model_name_or_path,
        detect_pipeline_type=detect_pipeline_type,
        profile=profile,
        enable_vae_tiling=enable_vae_tiling,
    )

    with CACHE_LOCK:
        MODEL_CACHE["last_memory_report"] = result.report.to_dict()

    return (
        result.t2i_pipe,
        result.i2i_pipe,
        result.device,
        result.dtype_str,
        result.detected,
    )
'''

if needle not in text:
    raise SystemExit("Could not find build_pipelines insertion point in worker_service.py")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
print("Applied Sprint 15D Pass 1: image build_pipelines now shares submodules via from_pipe.")
