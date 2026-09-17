"""One CivitAI example image's `meta` -> normalised sampling fields.

`meta` is uploader-supplied and undocumented. Captured live on 2026-09-16, it arrives in two
shapes that need different handling:

    {"sampler": "Euler", "scheduler": "beta", "steps": 8, "cfgScale": 1}      # split
    {"sampler": "er_sde_simple", "steps": 10, "cfgScale": 1, "clipSkip": 1}   # combined

For the combined shape the split is resolved against the live ComfyUI catalogues rather than by
string surgery: the LONGEST catalogue sampler that prefixes the text wins, and the remainder only
becomes a scheduler if it is one. Splitting on the last underscore instead would turn
"dpmpp_2m_sde" into "dpmpp_2m" + "sde" -- a real sampler paired with a scheduler that does not
exist, which is worse than not parsing it at all.

A1111 spellings ("DPM++ 2M Karras", "Euler a") are mapped explicitly; anything unrecognised
returns None so the caller can fall through to a lower-provenance source.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

from family_operating_points import COMFY_KSAMPLER_CATALOG, COMFY_SCHEDULER_CATALOG

# A1111 display spellings -> ComfyUI sampler names. Only what is actually seen in the wild.
_A1111_SAMPLERS: dict[str, str] = {
    "euler a": "euler_ancestral",
    "euler": "euler",
    "lms": "lms",
    "heun": "heun",
    "dpm2": "dpm_2",
    "dpm2 a": "dpm_2_ancestral",
    "dpm++ 2s a": "dpmpp_2s_ancestral",
    "dpm++ 2m": "dpmpp_2m",
    "dpm++ sde": "dpmpp_sde",
    "dpm++ 2m sde": "dpmpp_2m_sde",
    "dpm++ 3m sde": "dpmpp_3m_sde",
    "ddim": "ddim",
    "plms": "plms",
    "lcm": "lcm",
    "uni_pc": "uni_pc",
    "unipc": "uni_pc",
    "restart": "restart",
}

_SIZE_RE = re.compile(r"^\s*(\d{2,5})\s*[x×]\s*(\d{2,5})\s*$")


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def split_sampler(text: Any) -> tuple[str | None, str | None]:
    """(sampler, scheduler) from either shape, or (None, None) when unrecognised."""
    raw = _norm(text)
    if not raw:
        return None, None

    schedulers = {_norm(s) for s in COMFY_SCHEDULER_CATALOG}

    # A1111 display form: "DPM++ 2M Karras" -- words, with an optional trailing scheduler.
    if " " in raw and "_" not in raw:
        words = raw.split()
        for cut in range(len(words), 0, -1):
            head = " ".join(words[:cut])
            if head in _A1111_SAMPLERS:
                tail = " ".join(words[cut:]).strip()
                scheduler = tail if tail in schedulers else None
                return _A1111_SAMPLERS[head], scheduler
        return None, None

    # Comfy form: an exact sampler, or sampler + "_" + scheduler.
    samplers = sorted({_norm(s) for s in COMFY_KSAMPLER_CATALOG}, key=len, reverse=True)
    if raw in samplers:
        return raw, None
    for sampler in samplers:
        if raw.startswith(sampler + "_"):
            tail = raw[len(sampler) + 1 :]
            if tail in schedulers:
                return sampler, tail
    return (raw, None) if raw in samplers else (None, None)


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Normalised fields from one example image's meta. Unknown fields are ABSENT, never guessed."""
    if not isinstance(meta, dict):
        return {}
    out: dict[str, Any] = {}

    steps = _as_int(meta.get("steps"))
    if steps is not None and steps > 0:
        out["steps"] = steps

    cfg = _as_float(meta.get("cfgScale", meta.get("cfg_scale", meta.get("cfg"))))
    if cfg is not None and cfg >= 0:
        out["cfg"] = cfg

    clip_skip = _as_int(meta.get("clipSkip", meta.get("clip_skip")))
    if clip_skip is not None and clip_skip > 0:
        out["clip_skip"] = clip_skip

    seed = _as_int(meta.get("seed"))
    if seed is not None:
        out["seed"] = seed

    sampler, scheduler = split_sampler(meta.get("sampler"))
    explicit = _norm(meta.get("scheduler"))
    if explicit and explicit in {_norm(s) for s in COMFY_SCHEDULER_CATALOG}:
        scheduler = explicit
    if sampler:
        out["sampler"] = sampler
    if scheduler:
        out["scheduler"] = scheduler

    match = _SIZE_RE.match(str(meta.get("Size") or meta.get("size") or ""))
    if match:
        out["width"] = int(match.group(1))
        out["height"] = int(match.group(2))
    else:
        width = _as_int(meta.get("width"))
        height = _as_int(meta.get("height"))
        if width and height:
            out["width"] = width
            out["height"] = height

    return out


def mode_over(metas: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Most common value per field across example images.

    `n` is how many examples carried that winning value and `total` is how many were examined --
    both travel with the answer, because "8 steps in 8 of 10 examples" and "8 steps in 1 of 10"
    are different claims and the caller has to be able to tell them apart.
    """
    parsed = [parse_meta(meta) for meta in metas or []]
    total = len(parsed)
    if not total:
        return {}
    fields = {key for row in parsed for key in row}
    out: dict[str, dict[str, Any]] = {}
    for field in sorted(fields):
        if field == "seed":
            continue  # a seed is never a recommendation
        values = [row[field] for row in parsed if field in row]
        if not values:
            continue
        value, count = Counter(values).most_common(1)[0]
        out[field] = {"value": value, "n": count, "total": total}
    return out
