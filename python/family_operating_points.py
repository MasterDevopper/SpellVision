"""Per-family generation OPERATING POINTS -- tuning data + resolver (Phase 1, Wan-first).

GROUND TRUTH, NOT GUESSES. Every value here is empirically validated by a real render on the
target hardware (RTX 5090) -- the "why" is recorded per operating point below. This is the single
worker-owned source of truth that:
  * the video/image builders resolve blank/`auto` sampling params from (see ``resolve_family_defaults``),
    replacing the scattered inline ``req.get("steps") or 20`` literals; and
  * Phase 3 will ship to the UI (via the family-contract status payload) to drive a fast/quality
    selector and auto-populate the LoRA stack.

MANIFEST-AS-DATA (modeled on ``model_dependency_manifest.py``): adding a family or an operating point
is a NEW ROW here, not new code. A family may declare ANY SUBSET of params -- an image family may
only set ``steps``/``cfg``. The resolver treats a missing key as "not set", so the builder's own
inline literal still covers it (last-resort safety net during the phased migration).

Schema (per family):
    default_operating_point : str            -- used when the request names none (preserves today's behavior)
    operating_points        : {name: params}
        steps        : int
        cfg          : float
        sampler      : str
        scheduler    : str
        shift        : float
        lora         : {"accel": bool, "high"?: filename, "low"?: filename}
                       -- DECLARATIVE. Phase 3 auto-populates the UI's LoRA stack from this; the
                          builder does NOT auto-inject LoRAs (that would surprise a user who did not
                          add them). This pass records it, nothing consumes it yet.
        acceleration : {"type": "teacache" | "lora" | "none", ...}
                       -- DECLARATIVE. "quality" wants TeaCache once the standalone node is installed;
                          it degrades safely to no-op today via the selector fix (commit 19c26af).

Resolver precedence (per param): explicit request value  >  operating-point table value  >  absent
(the caller's own literal). A blank / "" / "auto" sampler|scheduler counts as "not provided" -- that
is exactly what the UI's "auto" sends (normalizeAutoValue -> ""), so it resolves from the table here
instead of from a builder's inline preference tuple.
"""
from __future__ import annotations

from typing import Any


# Lightx2v 4-step distill LoRAs (Wan 2.2 A14B t2v). Validated live: ~6.3x sampling vs the 28-step
# baseline, coherent output (accel-LoRA render pass). Declarative here; Phase 3 auto-populates the UI.
_WAN_LIGHTX2V_HIGH = "wan2.2_t2v_A14b_high_noise_lora_rank64_lightx2v_4step_1217.safetensors"
_WAN_LIGHTX2V_LOW = "wan2.2_t2v_A14b_low_noise_lora_rank64_lightx2v_4step_1217.safetensors"


FAMILY_OPERATING_POINTS: dict[str, dict[str, Any]] = {
    "wan": {
        "default_operating_point": "quality",
        "operating_points": {
            # 28-step full model. The validated CLEAN config from the noise diagnosis: the noisy render
            # was 28-step-no-LoRA at cfg 7 / dpmpp_2m / sgm_uniform; euler + simple + cfg ~4 at full
            # steps is coherent. TeaCache is the intended accelerant here, but the standalone node is
            # not installed -- the acceleration slot is DECLARATIVE and degrades to no-op (19c26af).
            "quality": {
                "steps": 28,
                "cfg": 4.0,
                "sampler": "euler",
                "scheduler": "simple",
                "shift": 5.0,
                "lora": {"accel": False},
                "acceleration": {"type": "teacache", "profile": "balanced"},
            },
            # Lightx2v 4-step config. Measured live at ~6.3x sampling vs the 28-step baseline with a
            # coherent frame. cfg 1 + 4 steps + the accel LoRAs (high -> high expert, low -> low, by the
            # builder's filename routing). TeaCache is deliberately "none" -- redundant at 4 steps.
            "fast": {
                "steps": 4,
                "cfg": 1.0,
                "sampler": "euler",
                "scheduler": "simple",
                "shift": 5.0,
                "lora": {"accel": True, "high": _WAN_LIGHTX2V_HIGH, "low": _WAN_LIGHTX2V_LOW},
                "acceleration": {"type": "none"},
            },
        },
    },
}


# Sampling params the resolver fills. Request-key aliases per logical param (worker request-schema
# knowledge lives here, not in the data table). String params treat "" / "auto" as "not provided".
_SAMPLING_PARAMS: tuple[str, ...] = ("steps", "cfg", "sampler", "scheduler", "shift")
_STRING_PARAMS = frozenset({"sampler", "scheduler"})
_REQUEST_ALIASES: dict[str, tuple[str, ...]] = {
    "steps": ("steps",),
    "cfg": ("cfg", "guidance_scale"),
    "sampler": ("video_sampler", "sampler"),
    "scheduler": ("video_scheduler", "scheduler"),
    "shift": ("shift", "model_sampling_shift"),
}


def _family_row(family: Any) -> dict[str, Any]:
    return FAMILY_OPERATING_POINTS.get(str(family or "").strip().lower(), {})


def default_operating_point(family: Any) -> str:
    """The operating point used when the request names none. "" for an unknown family."""
    return str(_family_row(family).get("default_operating_point") or "").strip()


def operating_point_params(family: Any, operating_point: Any) -> dict[str, Any]:
    """The FULL raw params for one operating point (steps/cfg/.../lora/acceleration), or {} if the
    family or operating point is unknown. Phase 3 reads lora/acceleration from here."""
    points = _family_row(family).get("operating_points", {})
    return dict(points.get(str(operating_point or "").strip(), {}))


def _request_override(req: dict[str, Any], param: str) -> Any:
    """The explicit request value for a logical param, or None if the request didn't provide one.
    Mirrors the old ``req.get(..) or <lit>`` semantics: a string "" / "auto" and a falsy number (0)
    both count as "not provided"."""
    for key in _REQUEST_ALIASES.get(param, ()):
        val = req.get(key)
        if val is None:
            continue
        if param in _STRING_PARAMS:
            text = str(val).strip()
            if not text or text.lower() == "auto":
                continue
            return text
        try:
            num: Any = int(val) if param == "steps" else float(val)
        except (TypeError, ValueError):
            continue
        if num:  # falsy 0 -> not provided (matches the old `or <literal>`)
            return num
    return None


def resolve_family_defaults(family: Any, operating_point: Any, req: dict[str, Any]) -> dict[str, Any]:
    """Effective sampling params for a request. Per param: explicit request value > operating-point
    table value > absent (caller's own literal). A blank/""/"auto" sampler|scheduler resolves from the
    table. Absent/blank operating_point -> the family's default_operating_point (so a normal request
    with no operating_point is unchanged). Unknown family/operating point -> only whatever the request
    itself supplied (empty otherwise), so the builder's literals still cover everything."""
    op = str(operating_point or "").strip() or default_operating_point(family)
    table = operating_point_params(family, op)
    effective: dict[str, Any] = {}
    for param in _SAMPLING_PARAMS:
        override = _request_override(req, param)
        if override is not None:
            effective[param] = override
        elif param in table:
            effective[param] = table[param]
    return effective
