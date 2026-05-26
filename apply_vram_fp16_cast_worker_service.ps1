$patch = @'
"""
VRAM Pass (companion): thread cast_fp32_to_fp16 through build_pipelines.

The cast itself lives in memory_optimization.build_paired_pipelines and
defaults to True, so the fix is already active without this patch. This
companion patch plumbs the flag through worker_service.build_pipelines
so a future UI setting (the "kill switch") has a wire to ride -- without
it, build_pipelines has no parameter to expose.

Two edits, both in worker_service.py:

  1. Add ``cast_fp32_to_fp16: bool = True`` to build_pipelines's
     keyword-only signature.
  2. Pass it through to build_paired_pipelines.

Nothing in the current call path passes the flag (get_or_load_pipelines
calls build_pipelines(model_name_or_path) with positional arg only), so
behavior is governed by the default -- True -- exactly as intended. When
a settings toggle is added later it sets this kwarg; today the default
is the behavior.
"""
from pathlib import Path
path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

# --- 1. Add the parameter to build_pipelines' signature ---
sig_needle = '''def build_pipelines(
    model_name_or_path: str,
    *,
    memory_profile: Any = None,
    enable_vae_tiling: bool = False,
) -> tuple[Any, Any, str, str, str]:'''

sig_replacement = '''def build_pipelines(
    model_name_or_path: str,
    *,
    memory_profile: Any = None,
    enable_vae_tiling: bool = False,
    cast_fp32_to_fp16: bool = True,
) -> tuple[Any, Any, str, str, str]:'''

if sig_needle not in text:
    raise SystemExit("Could not find build_pipelines signature in worker_service.py")
text = text.replace(sig_needle, sig_replacement, 1)

# --- 2. Pass the flag through to build_paired_pipelines ---
call_needle = '''    result = build_paired_pipelines(
        model_name_or_path,
        detect_pipeline_type=detect_pipeline_type,
        profile=profile,
        enable_vae_tiling=enable_vae_tiling,
    )'''

call_replacement = '''    result = build_paired_pipelines(
        model_name_or_path,
        detect_pipeline_type=detect_pipeline_type,
        profile=profile,
        enable_vae_tiling=enable_vae_tiling,
        cast_fp32_to_fp16=cast_fp32_to_fp16,
    )'''

if call_needle not in text:
    raise SystemExit("Could not find build_paired_pipelines call in worker_service.py")
text = text.replace(call_needle, call_replacement, 1)

path.write_text(text, encoding="utf-8")
print("Applied VRAM Pass companion: cast_fp32_to_fp16 threaded through build_pipelines.")
'@
Set-Content .\scripts\refactors\apply_vram_fp16_cast_worker_service.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_vram_fp16_cast_worker_service.py
