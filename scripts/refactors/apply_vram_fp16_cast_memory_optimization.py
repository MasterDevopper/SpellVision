"""
VRAM Pass: runtime fp32 -> fp16 cast for fp32-on-disk checkpoints.

The worker log confirmed every local SDXL checkpoint in this install is
fp32 on disk -- diffusers requests torch.float16, finds no fp16 weights,
and silently falls back to fp32. resident_dtype() already DETECTS this
(it drives the "Silent dtype fallback detected" warning). This pass acts
on the detection instead of only reporting it.

What it does
------------
In build_paired_pipelines(), for the PERFORMANCE profile on CUDA, right
AFTER apply_memory_profile(t2i_pipe, ...) and BEFORE the .to(device)
move: if the requested dtype was fp16 but the resident UNet dtype is
fp32, cast the pipeline to fp16 *while it is still on CPU*. Casting on
CPU means the fp32 weights are never fully resident in VRAM -- they are
converted in system RAM, and only the fp16 result is moved to the GPU.
Because t2i and i2i share submodule references (built via from_pipe),
casting t2i casts the shared weights i2i also points at.

Why only PERFORMANCE
--------------------
BALANCED / LOW_VRAM install accelerate offload hooks that manage device
*and* dtype placement themselves; injecting a manual .to(dtype) there
fights the hooks. PERFORMANCE is the profile that pins everything to GPU
and is the documented default for a high-VRAM card, so that is where the
cast belongs. If a future profile needs it, this is the pattern to copy.

Kill switch
-----------
A new keyword-only parameter ``cast_fp32_to_fp16: bool = True`` gates the
behavior. Default-on so the fix applies automatically; settable to False
to get the old fp32-resident behavior back if a checkpoint ever shows a
visible quality regression from the cast (very unlikely for SDXL, which
is trained and normally run in fp16).
"""
from pathlib import Path
path = Path("python/memory_optimization.py")
text = path.read_text(encoding="utf-8")

# --- 1. Add the kill-switch parameter to the signature ---
sig_needle = '''def build_paired_pipelines(
    model_name_or_path: str,
    *,
    detect_pipeline_type: DetectPipelineTypeFn,
    profile: Optional[MemoryProfile] = None,
    enable_vae_tiling: bool = False,
    use_safetensors_for_single_file: bool = True,
) -> PairedPipelinesResult:'''

sig_replacement = '''def build_paired_pipelines(
    model_name_or_path: str,
    *,
    detect_pipeline_type: DetectPipelineTypeFn,
    profile: Optional[MemoryProfile] = None,
    enable_vae_tiling: bool = False,
    use_safetensors_for_single_file: bool = True,
    cast_fp32_to_fp16: bool = True,
) -> PairedPipelinesResult:'''

if sig_needle not in text:
    raise SystemExit("Could not find build_paired_pipelines signature")
text = text.replace(sig_needle, sig_replacement, 1)

# --- 2. Insert the CPU-side cast before the PERFORMANCE .to(device) move ---
# Anchor: the apply_memory_profile(t2i_pipe...) line + the PERFORMANCE guard
# that immediately follows. We insert the cast block between them.
cast_needle = '''    profile_notes_t2i = apply_memory_profile(t2i_pipe, profile=profile, device=device)

    if profile == MemoryProfile.PERFORMANCE and device == "cuda":
        # Move shared weights to GPU once. The references in i2i_pipe see
        # the move automatically.
        t2i_pipe = t2i_pipe.to(device)'''

cast_replacement = '''    profile_notes_t2i = apply_memory_profile(t2i_pipe, profile=profile, device=device)

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
            log.info(
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
        t2i_pipe = t2i_pipe.to(device)'''

if cast_needle not in text:
    raise SystemExit("Could not find the PERFORMANCE .to(device) insertion zone")
text = text.replace(cast_needle, cast_replacement, 1)

# --- 3. Record the cast in the report notes so MemoryReport reflects it ---
# The log.info "Pipeline ready" line reads report.notes. We append a note
# right before the report is logged. Anchor on the warning block that
# follows -- we insert the note-append just before the final log.info or
# the silent-fallback warning. Simplest reliable anchor: the return.
note_needle = '''    return PairedPipelinesResult(
        t2i_pipe=t2i_pipe,
        i2i_pipe=i2i_pipe,
        device=device,
        dtype_str=str(dtype),'''

note_replacement = '''    if fp32_cast_applied:
        report.notes.append("fp32_cast_to_fp16")

    return PairedPipelinesResult(
        t2i_pipe=t2i_pipe,
        i2i_pipe=i2i_pipe,
        device=device,
        dtype_str=str(dtype),'''

if note_needle not in text:
    raise SystemExit("Could not find PairedPipelinesResult return for note append")
text = text.replace(note_needle, note_replacement, 1)

path.write_text(text, encoding="utf-8")
print("Applied VRAM Pass: fp32->fp16 runtime cast added to build_paired_pipelines.")
