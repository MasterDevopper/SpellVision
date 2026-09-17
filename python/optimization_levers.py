"""What can be measured on this stack, what cannot, and why -- as data rather than as prose.

The 2026 optimization landscape (``docs/superpowers/specs/2026-09-15-t2-t6-research/t4-research.md``)
lists two dozen levers. Most of them cannot run on core v0.34.0 with torch 2.10 + cu128, and the
reasons are specific and perishable -- a torch bump makes half of them reachable. Recorded here, the
harness measures exactly the reachable set and the generated document can state each cut with its
reason, instead of the next wave re-deriving the same list from the same research file.

Three statuses, and the middle one is the one worth having:

``runnable``
    Reachable on this stack today, through a launch arm this repository can actually produce or a
    request key a builder actually reads.

``blocked``
    The lever exists on this core, and SpellVision cannot ASK for it. Not a property of ComfyUI --
    a gap in this repository, named so it can be closed. ``ck_int8_attention`` is the sharpest
    example: ``comfy_launch_policy.normalize_backend`` accepts only sage and sdpa, so an arm naming
    ``ck`` falls through to automatic selection and produces a labelled row that is not what it
    claims to be. That is precisely the failure this wave exists to remove, so the lever is declared
    and withheld rather than offered and silently wrong.

``CUT_LEVERS``
    Not reachable at all on this stack, with the reason. Published by Task 5.

**On SageAttention.** The installed package is ``sageattention 1.0.6`` -- SA1, Triton kernels only.
The research says the SA2.2 wheel (woct0rdho abi3, sm120 kernels) is the first real measurement and
it is not installed. Installing it is deliberately not in this wave (ruling W3-P3: swapping a
package inside the owner's live ComfyUI venv changes their render environment, which is the owner's
call). So every sage row records the installed version, or the number is uninterpretable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# SA1. Recorded on every sage row -- see the module docstring.
SAGEATTENTION_INSTALLED = "1.0.6"

RUNNABLE = "runnable"
BLOCKED = "blocked"

# The guards a row may carry. A lever that is faster and wrong is not a win, so no row ships with
# seconds alone.
GUARD_BLACK_FRAME = "black_frame"   # SageAttention's documented overflow failure (pv_accum_dtype).
GUARD_FRAME0_MAE = "frame0_mae"     # i2v: did the first frame stay the keyframe.
GUARD_ARTEFACT = "artefact"         # caching and quantization: visible degradation at equal seed.


@dataclass(frozen=True)
class Lever:
    """One column of the matrix.

    ``arm`` is a ``comfy_launch_policy.arm_args`` dict and means the cell needs a ComfyUI restart;
    ``request`` is worker-request keys and means it does not. A lever has one or the other, never
    both -- a cell that changed two things at once would measure their sum.
    """

    id: str
    label: str
    kind: str                                   # "launch" | "graph"
    status: str
    note: str
    arm: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    guard_kinds: tuple[str, ...] = ()
    families: tuple[str, ...] | None = None     # None = every family
    blocked_reason: str = ""


# The baseline is pinned EXPLICITLY, both flags spelled. A bare launch that happens to land on SDPA
# is not evidence that SDPA was asked for -- which is exactly how this morning's silent relaunch
# turned a sage session into an SDPA one with nothing in the data to say so.
BASELINE_LEVER = Lever(
    id="sdpa_baseline",
    label="SDPA (core default, pinned)",
    kind="launch",
    status=RUNNABLE,
    note="The reference every delta on this row is measured against. --use-pytorch-cross-attention "
         "is spelled out rather than left implicit.",
    arm={"attention": "sdpa"},
    guard_kinds=(GUARD_BLACK_FRAME,),
)

ALL_LEVERS: tuple[Lever, ...] = (
    BASELINE_LEVER,
    Lever(
        id="sage_attention",
        label="SageAttention",
        kind="launch",
        status=RUNNABLE,
        note=f"sageattention {SAGEATTENTION_INSTALLED} is installed -- SA1, Triton kernels. The "
             "research puts the first real measurement at SA2.2 (sm120 CUDA kernels), whose wheel "
             "is not installed here and is not this wave's to install (W3-P3). Read every number "
             "on this row as SA1.",
        arm={"attention": "sage"},
        guard_kinds=(GUARD_BLACK_FRAME,),
    ),
    Lever(
        id="fast_fp16_accumulation",
        label="--fast fp16_accumulation",
        kind="launch",
        status=RUNNABLE,
        note="allow_fp16_accumulation. PR #6453 measured SDXL 4 -> 5 it/s on a 3090. Issue #8689 "
             "reports Flux + fp16acc + SA2 + compile producing noise, so the artefact guard is not "
             "ceremonial on this row.",
        arm={"fast": ["fp16_accumulation"]},
        guard_kinds=(GUARD_BLACK_FRAME, GUARD_ARTEFACT),
    ),
    Lever(
        id="fast_fp8_matrix_mult",
        label="--fast fp8_matrix_mult",
        kind="launch",
        status=RUNNABLE,
        note="Only engages when the weights are float8_e4m3fn and the card supports fp8 compute "
             "(sm89+). On a bf16 checkpoint the flag is inert, so the row would report the "
             "measurement noise of an unchanged configuration as a delta.",
        arm={"fast": ["fp8_matrix_mult"]},
        guard_kinds=(GUARD_BLACK_FRAME, GUARD_ARTEFACT),
        families=("wan22_fp8", "flux_fp8", "ltx_fp8"),
    ),
    Lever(
        id="fixed_vram_budget",
        label="--reserve-vram 22",
        kind="launch",
        status=RUNNABLE,
        note="The only arm where a memory number means anything. DynamicVRAM expands to fill what "
             "is available, so an unconstrained peak measures availability; measured on this box, "
             "LTX 97f at 2048x1280 peaked 30.98 GB unconstrained and 11.47 GB at a 22 GB reserve -- "
             "the same render.",
        arm={"vram_headroom": 22.0},
        guard_kinds=(GUARD_BLACK_FRAME,),
    ),
    Lever(
        id="dynamic_vram_off",
        label="--disable-dynamic-vram",
        kind="launch",
        status=RUNNABLE,
        note="Turns off comfy-aimdo's CUDA-level paging. Expected to be slower or to OOM; measured "
             "so that the default has a number behind it rather than a reputation.",
        arm={"dynamic_vram": False},
        guard_kinds=(GUARD_BLACK_FRAME,),
    ),
    Lever(
        id="vae_tiling",
        label="VAEDecodeTiled",
        kind="graph",
        status=RUNNABLE,
        note="The one graph-level lever the request layer already carries end to end "
             "(`enable_vae_tiling`, resolved in comfy_graph_helpers). Trades time for decode VRAM, "
             "so it is the lever whose memory column is worth having -- run it inside the fixed "
             "reserve arm or the number says nothing.",
        request={"enable_vae_tiling": True},
        guard_kinds=(GUARD_BLACK_FRAME, GUARD_ARTEFACT),
    ),
    # --- declared and withheld ------------------------------------------------------------------
    Lever(
        id="ck_int8_attention",
        label="Comfy-Kitchen INT8 attention",
        kind="launch",
        status=BLOCKED,
        note="Core v0.32 ships --use-ck-attention; the research flags it as 'might break some' and "
             "on cu128 it takes the Triton path rather than the CUDA one.",
        arm={"attention": "ck"},
        guard_kinds=(GUARD_BLACK_FRAME, GUARD_ARTEFACT),
        blocked_reason=(
            "comfy_launch_policy.normalize_backend accepts only sage and sdpa spellings. An arm "
            "naming 'ck' resolves to automatic selection and launches something else, producing a "
            "row labelled ck that did not run ck. Unblocking it is a launch-policy change, not a "
            "harness one."
        ),
    ),
    Lever(
        id="easycache",
        label="EasyCache",
        kind="graph",
        status=BLOCKED,
        note="Core node since v0.3.52 (reuse 0.2, start 0.15, end 0.95), 1.3-2x on Flux/Wan/Hunyuan/"
             "LTX/Qwen/Lumina2 and poor with 4-step distilled routes.",
        guard_kinds=(GUARD_ARTEFACT,),
        blocked_reason=(
            "No builder in python/ inserts the EasyCache node and no request key reaches one. "
            "Measuring it needs a graph change first, which is a separate piece of work from "
            "measuring it."
        ),
    ),
    Lever(
        id="pruna_vaed",
        label="PrunaVAED decoder (LTX)",
        kind="graph",
        status=BLOCKED,
        note="Core v0.30.2 ships the LTX-2.3 Pruna decoder: ~1.7x decode at ~50% decode VRAM. It is "
             "a decoder file swap, and the decode side is where LTX's peak actually lives.",
        families=("ltx",),
        guard_kinds=(GUARD_ARTEFACT,),
        blocked_reason=(
            "The LTX templates name their VAE decoder directly; nothing in the request selects a "
            "decoder file. Reachable only after the LTX builder takes a decoder parameter."
        ),
    ),
    Lever(
        id="fp16_cast",
        label="fp32 -> fp16 CPU cast (diffusers)",
        kind="graph",
        status=BLOCKED,
        note="Shipped and measured already: ~18.9 -> ~11.7 GB on an fp32 SDXL checkpoint, and "
             "28.5 -> 6.57 GB once shared-weight loading landed with it.",
        guard_kinds=(GUARD_ARTEFACT,),
        blocked_reason=(
            "worker_runtime.CAST_FP32_TO_FP16 is a module constant, not a request key, so the two "
            "arms cannot be run inside one session. An A/B needs a worker restart between arms, "
            "which this harness deliberately does not do -- it restarts ComfyUI, not the product."
        ),
    ),
)

# Not reachable on this stack at all. Task 5 publishes these with their reasons; a cut with no
# reason gets re-litigated every wave.
CUT_LEVERS: dict[str, str] = {
    "sage_attention_3": (
        "SA3's FP4 kernels need torch 2.12 / cu131. This stack is torch 2.10 + cu128, and the core "
        "registers the backend but exposes no flag for it."
    ),
    "nvfp4": (
        "Requires cu130. On cu128 the research measures it up to 2x SLOWER than fp8, so running it "
        "here would measure the emulation, not the format."
    ),
    "flash_attention": (
        "No verified FlashAttention 2 wheel for torch 2.10 / cu128 / sm120, and the research rates "
        "it at or below SDPA for diffusion anyway."
    ),
    "teacache": (
        "Dead. Last upstream commit 2025-07-12, and it has failed to import since the 2026-01-05 "
        "core change (#11660)."
    ),
    "magcache": (
        "Dead. Last upstream commit 2025-11-27; already removed from this box's ComfyUI as a dead "
        "end against the v0.34.0 rope change."
    ),
    "gguf": "The research measures it as the slowest of the weight formats. Nothing to win.",
    "radial_sparse_attention": (
        "Wrapper-only, and the core's Block Sparse attention is Hunyuan3D-only -- not usable on the "
        "native Wan or LTX routes this project ships."
    ),
    "torch_compile": (
        "Not cut on merit -- deferred. torch.compile x DynamicVRAM is an OPEN upstream limitation "
        "(aimdo #13, #14536), so it needs its own --disable-dynamic-vram lane rather than a column "
        "in a matrix whose every other cell runs with DynamicVRAM on."
    ),
}

# family -> the modes to measure it in. Deliberately small: the matrix is levers x families x 3
# runs, and every added family is another hour.
DEFAULT_FAMILIES: dict[str, tuple[str, ...]] = {
    "krea2": ("t2i",),          # the family the published A/B used
    "sdxl": ("t2i",),
    "wan22_fp8": ("i2v",),
    "ltx": ("t2v",),
}


def runnable_levers() -> tuple[Lever, ...]:
    return tuple(lever for lever in ALL_LEVERS if lever.status == RUNNABLE)


def blocked_levers() -> tuple[Lever, ...]:
    return tuple(lever for lever in ALL_LEVERS if lever.status == BLOCKED)


def lever(lever_id: str) -> Lever:
    for candidate in ALL_LEVERS:
        if candidate.id == lever_id:
            return candidate
    raise KeyError(f"no such lever: {lever_id!r}")


def required_guards(lever_id: str, mode: str) -> tuple[str, ...]:
    """Which quality guards a row for this lever and mode must carry.

    ``black_frame`` is on every row rather than only on the attention ones: a black output is the
    cheapest catastrophic failure to detect and the most expensive to publish a speedup over.
    ``frame0_mae`` is added for i2v, where the question "is this still the keyframe" has an answer.
    """
    guards = set(lever(lever_id).guard_kinds) or {GUARD_BLACK_FRAME}
    guards.add(GUARD_BLACK_FRAME)
    if mode == "i2v":
        guards.add(GUARD_FRAME0_MAE)
    return tuple(sorted(guards))
