"""Pure request-shape helpers. No torch -- safe for unit tests."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

# WARNING and above: the root logger sits at WARNING, so log.info is invisible in this repo
# (CLAUDE.md 4). What this module reports is a value the user stated being changed.
log = logging.getLogger("spellvision.request")


# --- numeric request options -------------------------------------------------------------------------

# The aliases each logical field is accepted under. These were per-call-site tuples and they had
# DRIFTED: cfg was read as ("cfg", "guidance_scale") in the WAN core builder, ("cfg", "cfg_scale") in
# the wrapper and the generic builder, and plain ("cfg",) elsewhere -- so which spelling worked
# depended on which family you were rendering. One table, so it cannot happen again.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "batch_size": ("batch_size",),
    "cfg": ("cfg", "cfg_scale", "guidance_scale"),
    "denoise": ("denoise", "denoise_strength"),
    "fps": ("fps", "frame_rate"),
    "frames": ("frames", "num_frames", "frame_count", "length", "video_length"),
    "height": ("height",),
    "limit": ("limit",),
    "lora_scale": ("lora_scale",),
    "shift": ("shift", "sampling_shift", "model_sampling_shift", "flow_shift"),
    "steps": ("steps", "num_inference_steps"),
    "timeout_sec": ("timeout_sec",),
    "upscale_scale": ("upscale_scale",),
    "width": ("width",),
}

# What each field may legitimately be. The point of the table is the LOW bound: it is the honest
# answer to "is zero sayable here", asked once per field instead of guessed at 80 call sites.
#
#   cfg 0        -- unconditional sampling, and the cockpit's spin box offers it
#   denoise 0    -- return the input unchanged, which is what an i2i strength of 0 means
#   limit 0      -- return no rows
#   timeout 0    -- do not wait
#   shift 0      -- no shift
#   lora_scale 0 -- the LoRA off, without unloading it
#
#   steps 0      -- NOT sayable; a render needs at least one step
#   fps 0        -- NOT sayable
#   width 0      -- NOT sayable
#
# The second group is why this is not simply "honour whatever was stated". A stated 0 for steps is a
# mistake, and quietly substituting 28 for it is how the mistake stays invisible: the render comes
# back looking fine and nothing said the number was ignored. Out of range is CLAMPED and reported.
FIELD_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "batch_size": (1, None),
    "cfg": (0.0, None),
    "denoise": (0.0, 1.0),
    "fps": (1, None),
    "frames": (1, None),
    "height": (1, None),
    "limit": (0, None),
    "lora_scale": (0.0, None),
    "shift": (0.0, None),
    "steps": (1, None),
    "timeout_sec": (0.0, None),
    "upscale_scale": (1.0, None),
    "width": (1, None),
}

def _bounds_for(field: str) -> tuple[float | None, float | None]:
    """The range for a field, by exact name then by suffix.

    The suffix step is what makes ``startup_timeout_sec`` and ``version_check_timeout_sec`` inherit
    ``timeout_sec``'s "zero means do not wait" without either of them being listed. Enumerating every
    spelling is the habit this whole pass is about: the list would be right on the day it was written
    and one rename behind ever after.
    """
    if field in FIELD_BOUNDS:
        return FIELD_BOUNDS[field]
    for name, bounds in FIELD_BOUNDS.items():
        if field.endswith("_" + name) or field.startswith(name + "_"):
            return bounds
    return (None, None)


_UNSET = object()


def _as_number(value: Any) -> float | None:
    """The number in ``value``, or None if it does not state one.

    A bool is not a number here: ``True`` would arrive as 1 and quietly become a real value. A blank
    or ``"auto"`` string is "not stated" -- that is what the cockpit's Auto entry sends, and several
    call sites grew a ``str(...).strip() or ...`` dance around exactly this.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "auto":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bounded_option(
    req: Mapping[str, Any] | None,
    field: str,
    default: float | int,
    *,
    table: Mapping[str, Any] | None = None,
    aliases: Sequence[str] | None = None,
    minimum: Any = _UNSET,
    maximum: Any = _UNSET,
) -> Any:
    """A numeric request option where a stated value is honoured -- **including zero**.

    ``float(req.get(key) or default)`` is the idiom this replaces. It is wrong wherever 0 means
    something, because 0 is falsy: the explicit zero is swapped for the default and nothing says so.
    Measured across this repo: 80 sites, 45 in one file. Two of them INVERTED a video denoise, so a
    stated 0.0 -- return the input unchanged -- rendered at full strength.

    Resolution, first hit wins:

    1. any of the field's aliases in ``req``, if it states a number;
    2. the same, in ``table`` -- the family's operating point;
    3. ``default``.

    The result is then held to the field's range. A stated value outside it is clamped and reported
    at WARNING, which is the part that separates this from "honour anything": a stated ``steps=0``
    is a mistake, and silently rendering 28 steps instead is how the mistake stays invisible.

    Returns an ``int`` when ``default`` is an ``int``, so call sites keep the type they had.
    """
    names = tuple(aliases) if aliases else FIELD_ALIASES.get(field, (field,))
    low, high = _bounds_for(field)
    if minimum is not _UNSET:
        low = minimum
    if maximum is not _UNSET:
        high = maximum

    stated: float | None = None
    source = ""
    for source_map, source_name in ((req, "request"), (table, "operating point")):
        if not source_map:
            continue
        for name in names:
            if name not in source_map:
                continue
            value = _as_number(source_map.get(name))
            if value is not None:
                stated, source = value, source_name
                break
        if stated is not None:
            break

    value = float(default) if stated is None else stated

    if stated is not None:
        if low is not None and value < low:
            log.warning("%s=%s is below the minimum %s; using %s (stated in the %s).",
                        field, stated, low, low, source)
            value = float(low)
        elif high is not None and value > high:
            log.warning("%s=%s is above the maximum %s; using %s (stated in the %s).",
                        field, stated, high, high, source)
            value = float(high)

    return int(round(value)) if isinstance(default, int) else value


def numeric_option(req: Mapping[str, Any], key: str, default: float) -> float:
    """``bounded_option`` with no range and no aliases -- the original three call sites' contract.

    Kept as a name because it is what those callers read as, and delegating rather than duplicating
    is the whole point: two implementations of "honour a stated zero" is how this file ended up
    needed in the first place.
    """
    return float(bounded_option(req, key, float(default), aliases=(key,),
                                minimum=None, maximum=None))


def resolve_request_lora(req: dict[str, Any]) -> tuple[str | None, float]:
    """Return (path, scale) from `lora`/`lora_scale` or the first enabled `loras[]` item."""
    raw = req.get("lora")
    if isinstance(raw, str) and raw.strip() and raw.strip().lower() != "none":
        try:
            scale = float(req.get("lora_scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        return raw.strip(), scale

    items = req.get("loras")
    if not isinstance(items, list):
        return None, 1.0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        path = item.get("path") or item.get("name") or item.get("value")
        if not isinstance(path, str) or not path.strip():
            continue
        weight = item.get("weight", item.get("strength", 1.0))
        try:
            scale = float(weight)
        except (TypeError, ValueError):
            scale = 1.0
        return path.strip(), scale
    return None, 1.0


def studio_effective_mode(requested: str, payload: dict[str, Any]) -> str:
    mode = (requested or "t2i").strip().lower() or "t2i"
    image = payload.get("input_image")
    if mode == "t2i" and isinstance(image, str) and image.strip():
        return "i2i"
    return mode
