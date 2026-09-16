"""The one answer to "what should this page show for this model".

Two tables and four sources disagree, so the order lives here and nowhere else:

    user
      > site:image-meta-mode          (>= MODE_QUORUM of the model's own example images)
      > card:snippet-regex > card:prose-regex
      > site:image-meta-weak          (fewer examples than the quorum -- evidence, not advice)
      > table:family-operating-point  (this project's own render comparisons)
      > table:family-default          (what the family's publisher states)

`table:family-operating-point` outranks `table:family-default` because the former was chosen by
measuring renders on this hardware and the latter is a generic published figure. The ranking is
NOT restated here: it is `recommended.PROVENANCE_ORDER` (which already carries every sidecar-side
provenance, Task 2's `site:image-meta-weak` included) with `table:family-operating-point` inserted
directly above the `table:family-default` it already contains. Two ordered lists for one concept is
exactly the defect this wave removes elsewhere.

Two rules make the answer usable rather than merely correct. A sampler the family's graph cannot
accept is dropped to the family's own default with a warning -- a cockpit offering a default the
generate path refuses is worse than one offering the family's. And a hardware cap snaps with a
warning, never silently: the user has to be able to see that the number they are looking at is not
the number the model asked for. The cap is a heuristic on purpose -- CLAUDE.md S6 records what
happens when a memory figure is read off a number nobody measured, and this module does not repeat
that mistake for VRAM, and does not invent an unmeasured host-RAM one either (`host_ram_gb` is
accepted for the caller's convenience and forward use; nothing here is tuned against it yet).

LTX is the reason a family's canvas cannot be read from one table alone: it deliberately has no
`FAMILY_OPERATING_POINTS` row (two tests elsewhere assert that absence on purpose), so its
width/height/fps/frames and `default_sampler` live on `FAMILY_SAMPLER_ALLOWLISTS["ltx"]` instead.
`_table_operating_point_entries` checks both, so no caller needs to know which families are which.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import family_operating_points as fop
from model_intelligence import family_seed_table, recommended

# recommended.PROVENANCE_ORDER, plus the runtime table ranked above the published floor it already
# contains. This is the ONLY place that ordering is extended -- see the module docstring.
_TABLE_OPERATING_POINT = "table:family-operating-point"
_TABLE_FAMILY_DEFAULT = "table:family-default"
_ORDER = list(recommended.PROVENANCE_ORDER)
_ORDER.insert(_ORDER.index(_TABLE_FAMILY_DEFAULT), _TABLE_OPERATING_POINT)
_RANK = {name: index for index, name in enumerate(_ORDER)}

_CANVAS_FIELDS = ("width", "height", "frames", "fps")

# Per-family canvas legality, transcribed from the ONE place each is actually enforced today
# (video_adapters/ltx_adapter.py for LTX; the matching `_snap` closures in native_video_graphs.py
# for mochi/hunyuan_video) -- not invented here. A family with no row here has no constraint of its
# own; `resolve_family_defaults`'s builders would tell us if that changes.
_CANVAS_SNAP: dict[str, dict[str, Any]] = {
    "ltx": {"wh_multiple": 32, "wh_mode": "nearest", "frame_stride": 8, "frame_min": 1, "frame_mode": "nearest"},
    "mochi": {"wh_multiple": 16, "wh_mode": "floor", "frame_stride": 6, "frame_min": 7, "frame_mode": "floor"},
    "hunyuan_video": {"wh_multiple": 16, "wh_mode": "floor", "frame_stride": 4, "frame_min": 5, "frame_mode": "floor"},
}

# A heuristic, not a measurement -- see the module docstring and CLAUDE.md S6. It exists only to
# catch a canvas that is unrunnable on its face (4K on an 8GB card), not to model any family's real
# footprint.
#
# Retuned 2026-09-16, because the old 0.5 / 6000 B/px was not generous, it was WRONG: it gave an
# 8 GB card 715 827 pixels, so a plain 1024x1024 SDXL default -- a size that renders fine on 8 GB --
# resolved to 846x846, and a 6 GB card to 732x732. A cap that refuses the default size of the most
# common family on the most common card is not catching the obvious case, it is the obvious case.
# It was latent only because nothing sends `vram_gb` yet, which is the worst way for a number to be
# safe.
#
# 0.75 / 1500 B/px gives 8 GB about 4.3 megapixels (~2072 square, and 1024x1024 passes with four
# times the room), 12 GB about 6.4, 32 GB about 17.2. 3840x2160 -- the 8.3 Mpx case this cap was
# written for -- is still refused on anything under ~15 GB. The direction of the error is
# deliberate: an unrunnable canvas fails with an OOM the user can read, while a silently shrunk one
# is a wrong render that looks like a working one.
_CAP_VRAM_FRACTION = 0.75
_CAP_BYTES_PER_PIXEL = 1_500


def _rank(provenance: str) -> int:
    return _RANK.get(str(provenance or ""), len(_ORDER))


def _mk_entry(value: Any, provenance: str, *, n: int | None = None, total: int | None = None) -> dict[str, Any]:
    confidence = (n / total) if (n and total) else 1.0
    return {"value": value, "provenance": provenance, "confidence": round(float(confidence), 3), "n": n, "total": total}


def _offer(out: dict[str, dict[str, Any]], field: str, entry: dict[str, Any]) -> None:
    if field not in recommended.FIELDS:
        return
    current = out.get(field)
    if current is None or _rank(entry["provenance"]) < _rank(current["provenance"]):
        out[field] = entry


def _apply_quorum(entry: dict[str, Any]) -> dict[str, Any]:
    """Re-derive `site:image-meta-mode` vs `site:image-meta-weak` from the STORED `n`.

    `recommended.build` applies `MODE_QUORUM` when it WRITES a sidecar. That made the quorum a
    property of one writer rather than of the concept, and every sidecar written before the quorum
    existed still claims full `site:image-meta-mode` rank at n=1. `sidecar.SCHEMA` did not change,
    so nothing re-derives them -- 67 sidecars on the owner's disks carried 16 such fields, one of
    which resolved `width 1792` from a single example under a caption reading "1 of 1 agree".

    So the gate is applied HERE as well, on the read, from the evidence the entry carries about
    itself. A file written by any version now resolves the same way, and a future writer that
    stores a rank its own `n` does not support cannot make this reader believe it. Deliberately
    NOT a schema bump: that invalidates old files rather than handling them, and leaves the next
    writer free to store a provenance the reader still trusts.

    An entry with no `n` at all is left alone: absent evidence is not evidence of thinness, and
    every field that carries this provenance from `meta_parse.mode_over` carries its count with it.
    """
    if str(entry.get("provenance") or "") != "site:image-meta-mode":
        return entry
    n = entry.get("n")
    if not isinstance(n, int) or n >= recommended.MODE_QUORUM:
        return entry
    return {**entry, "provenance": "site:image-meta-weak"}


# A sanity floor on the four fields a site value can make NONSENSE of rather than merely wrong.
# `hf_lookup` already bounds steps to 1..300; the image-meta path had no equivalent for any field,
# and a real sidecar on this box resolved `height 8` from one example image. These are the spin
# boxes' own ranges (ImageGenerationPage.cpp), so a value outside them could not be shown anyway --
# the C++ silently dropped the height and kept the width, leaving a canvas half from the model and
# half from whatever was there before, under a caption claiming the model published both.
_SANE_RANGE: dict[str, tuple[int, int]] = {
    "width": (64, 8192), "height": (64, 8192), "frames": (1, 2400), "fps": (1, 120),
}


def _is_sane(field: str, value: Any) -> bool:
    bounds = _SANE_RANGE.get(field)
    if bounds is None:
        return True
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return bounds[0] <= number <= bounds[1]


def _sidecar_entries(sidecar_payload: dict[str, Any] | None,
                     warnings: list[str] | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field, entry in ((sidecar_payload or {}).get("recommended") or {}).items():
        if field not in recommended.FIELDS or not isinstance(entry, dict) or not entry.get("provenance"):
            continue
        if not _is_sane(field, entry.get("value")):
            if warnings is not None:
                warnings.append(
                    f"{field} {entry.get('value')!r} from {entry.get('provenance')} is outside "
                    f"{_SANE_RANGE[field]}; using the family's value instead."
                )
            continue
        out[field] = _apply_quorum(dict(entry))
    return out


def _canonical_sampler_family(family_key: str | None, mode: str | None) -> str | None:
    """The `FAMILY_SAMPLER_ALLOWLISTS` key for a family, via the SAME alias map
    `FAMILY_OPERATING_POINTS` uses (`fop._FAMILY_SAMPLING_ALIASES`), so the two tables can never
    resolve one family two different ways. `mode` only breaks a tie the alias map does not settle
    (a family present under a task-suffixed key the alias map has not caught up with yet)."""
    if not family_key:
        return None
    if family_key in fop.FAMILY_SAMPLER_ALLOWLISTS:
        return family_key
    alias = fop._FAMILY_SAMPLING_ALIASES.get(family_key)
    if alias in fop.FAMILY_SAMPLER_ALLOWLISTS:
        return alias
    suffix = "_video" if str(mode or "").lower() in ("t2v", "i2v") else "_image"
    candidate = f"{family_key}{suffix}"
    return candidate if candidate in fop.FAMILY_SAMPLER_ALLOWLISTS else family_key


def _family_declares(family_key: str, operating_point: str) -> bool:
    """Whether this family actually HAS the named operating point -- in either store.

    `FAMILY_OPERATING_POINTS` names the runtime ones (wan's fast/quality). `family_seed_table` names
    the published ones as `family:variant` rows (`krea2:turbo`). A family that declares neither has
    no such point, and handing that name to `operating_point_params` returns `{}` -- which is how a
    wan file with "turbo" in its name lost the whole tuned point and came back at the seed floor.
    """
    if fop.operating_point_params(family_key, operating_point):
        return True
    return family_seed_table.declares_variant(family_key, operating_point)


def _select_operating_point(family_key: str | None, sidecar_payload: dict[str, Any] | None, path: str) -> str:
    """The sidecar's recorded variant -> that. Else a `turbo` path substring. Else the family's own
    default. Recorded in the result so the cockpit's Speed chip agrees with what was actually used.

    Both non-default answers are DECLARATION-GATED: a name this family does not declare falls back
    to the default rather than through to `operating_point_params` returning `{}`. That empty dict
    was the real damage -- `wan2.2_t2v_turbo_fp8.safetensors` resolved operating point "turbo", wan
    declares no such point, and the cockpit showed the seed floor's 20 / 3.5 where wan's own table
    says 28 / 4.0, while `operating_point` in the reply named a Speed chip that does not exist.

    `identity.variant` is the DATA answer (`sidecar.build_payload` records what CivitAI's version
    name says). The filename substring stays only as the last resort for a weight with no sidecar,
    it is not word-bounded, and it reads `turbo` out of `Turbocharged_Dreams_XL` -- which is exactly
    why it may no longer name a point the family has not declared.
    """
    if not family_key:
        return ""
    default = fop.default_operating_point(family_key)
    identity = (sidecar_payload or {}).get("identity") or {}
    named = str(identity.get("variant") or identity.get("operating_point") or "").strip().lower()
    if not named and "turbo" in Path(str(path or "")).stem.lower():
        named = "turbo"
    if named and _family_declares(family_key, named):
        return named
    return default


def _route_params(allow: dict[str, Any], route: str | None) -> dict[str, Any]:
    """The steps/cfg a ROUTE-keyed family declares, for the named route or its own default.

    Only LTX has these today, and only because one number cannot serve both its routes: the
    distilled two-stage default samples ~8 steps with the guiders pinned at 1, the opt-in
    single-stage-full path wants 25-40 at CFG 3-5 (CLAUDE.md S6). A family with no `routes` block
    returns nothing and every other path here is unchanged.
    """
    routes = allow.get("routes") or {}
    if not routes:
        return {}
    wanted = str(route or "").strip().lower() or str(allow.get("default_route") or "").strip()
    return dict(routes.get(wanted) or routes.get(str(allow.get("default_route") or "")) or {})


def _table_operating_point_entries(family_key: str | None, operating_point: str, mode: str | None,
                                   route: str | None = None) -> dict[str, dict[str, Any]]:
    if not family_key:
        return {}
    raw = dict(fop.operating_point_params(family_key, operating_point))
    canonical = _canonical_sampler_family(family_key, mode)
    allow = fop.FAMILY_SAMPLER_ALLOWLISTS.get(canonical, {}) if canonical else {}
    for field in _CANVAS_FIELDS:  # LTX's canvas lives here instead -- see module docstring.
        if not raw.get(field) and field in allow:
            raw[field] = allow[field]
    for field, value in _route_params(allow, route).items():
        if not raw.get(field):
            raw[field] = value
    if not raw.get("sampler") and allow.get("default_sampler"):
        raw["sampler"] = allow["default_sampler"]
    if not raw.get("scheduler") and allow.get("default_scheduler"):
        raw["scheduler"] = allow["default_scheduler"]
    return {f: _mk_entry(v, _TABLE_OPERATING_POINT) for f, v in raw.items() if f in recommended.FIELDS and v not in (None, "")}


def _table_family_default_entries(family_key: str | None, operating_point: str) -> dict[str, dict[str, Any]]:
    raw = family_seed_table.seed_for(family_key, operating_point)
    return {f: _mk_entry(v, _TABLE_FAMILY_DEFAULT) for f, v in raw.items() if f in recommended.FIELDS and v not in (None, "")}


def _enforce_allowlist(settings: dict[str, dict[str, Any]], field: str, kind: str, family_key: str | None,
                       live_values: list[str] | None, floor: dict[str, dict[str, Any]], mode: str | None,
                       warnings: list[str]) -> None:
    entry = settings.get(field)
    if entry is None or not family_key:
        return
    canonical = _canonical_sampler_family(family_key, mode)
    allowed_raw = fop.FAMILY_SAMPLER_ALLOWLISTS.get(canonical, {}).get(kind) if canonical else None
    if not allowed_raw:  # no row, or an explicit empty tuple (the family has no such choice at all)
        return
    allowed = set(allowed_raw)
    if live_values:
        allowed &= set(live_values)
    if entry["value"] in allowed:
        return
    original = entry["value"]
    fallback = floor.get(field)
    if fallback is None:
        settings.pop(field, None)
        replacement = "the family default"
    else:
        settings[field] = dict(fallback)
        replacement = fallback["value"]
    warnings.append(
        f"{field} {original!r} is not on {family_key}'s allowlist"
        + (f" (live: {sorted(live_values)})" if live_values else "")
        + f"; using {replacement!r} instead."
    )


def _snap_wh(value: int, multiple: int, mode: str) -> int:
    if mode == "nearest":
        return max(multiple, int(round(value / multiple)) * multiple)
    return max(multiple, value - (value % multiple))


def _snap_frames(value: int, stride: int, minimum: int, mode: str) -> int:
    if mode == "nearest":
        n = max(1, int(round((value - 1) / stride)))
        return n * stride + 1
    return ((max(minimum, value) - 1) // stride) * stride + 1


def _snap_canvas_legality(settings: dict[str, dict[str, Any]], family_key: str | None, mode: str | None,
                          warnings: list[str]) -> None:
    canonical = _canonical_sampler_family(family_key, mode)
    spec = _CANVAS_SNAP.get(canonical) if canonical else None
    if not spec:
        return
    for dim in ("width", "height"):
        entry = settings.get(dim)
        if entry is None:
            continue
        try:
            value = int(entry["value"])
        except (TypeError, ValueError):
            continue
        snapped = _snap_wh(value, spec["wh_multiple"], spec["wh_mode"])
        if snapped != value:
            warnings.append(f"{canonical} requires {dim} divisible by {spec['wh_multiple']}; snapped {value} -> {snapped}.")
            settings[dim] = {**entry, "value": snapped}
    entry = settings.get("frames")
    if entry is not None:
        try:
            value = int(entry["value"])
        except (TypeError, ValueError):
            value = None
        if value is not None:
            snapped = _snap_frames(value, spec["frame_stride"], spec["frame_min"], spec["frame_mode"])
            if snapped != value:
                warnings.append(f"{canonical} frame length must be (N*{spec['frame_stride']})+1; snapped {value} -> {snapped}.")
                settings["frames"] = {**entry, "value": snapped}


def _pixel_budget(vram_gb: float | None) -> float | None:
    try:
        gb = float(vram_gb) if vram_gb else 0.0
    except (TypeError, ValueError):
        return None
    if gb <= 0:
        return None  # unknown hardware -> no opinion, per spec
    return gb * (1024 ** 3) * _CAP_VRAM_FRACTION / _CAP_BYTES_PER_PIXEL


def _apply_hardware_cap(settings: dict[str, dict[str, Any]], vram_gb: float | None, warnings: list[str]) -> None:
    budget = _pixel_budget(vram_gb)
    width_e, height_e = settings.get("width"), settings.get("height")
    if budget is None or width_e is None or height_e is None:
        return
    try:
        width, height = int(width_e["value"]), int(height_e["value"])
    except (TypeError, ValueError):
        return
    pixels = width * height
    if pixels <= budget or pixels <= 0:
        return
    scale = (budget / pixels) ** 0.5
    new_width, new_height = max(64, int(width * scale)), max(64, int(height * scale))
    warnings.append(
        f"{width}x{height} is beyond a heuristic VRAM budget for ~{vram_gb}GB; capped to "
        f"{new_width}x{new_height}. This cap is a rough heuristic, not a measured per-family limit."
    )
    settings["width"] = {**width_e, "value": new_width, "provenance": f"{width_e['provenance']}:capped"}
    settings["height"] = {**height_e, "value": new_height, "provenance": f"{height_e['provenance']}:capped"}


def resolve_model_defaults(*, path: str, family: str | None, mode: str, sidecar_payload: dict[str, Any] | None,
                           live_samplers: list[str] | None = None, live_schedulers: list[str] | None = None,
                           vram_gb: float | None = None, host_ram_gb: float | None = None,
                           route: str | None = None) -> dict[str, Any]:
    family_key = str(family or "").strip().lower() or None
    warnings: list[str] = []

    operating_point = _select_operating_point(family_key, sidecar_payload, path)

    floor: dict[str, dict[str, Any]] = {}
    for field, entry in _table_family_default_entries(family_key, operating_point).items():
        _offer(floor, field, entry)
    for field, entry in _table_operating_point_entries(family_key, operating_point, mode, route).items():
        _offer(floor, field, entry)

    settings: dict[str, dict[str, Any]] = {k: dict(v) for k, v in floor.items()}
    for field, entry in _sidecar_entries(sidecar_payload, warnings).items():
        _offer(settings, field, entry)

    _enforce_allowlist(settings, "sampler", "samplers", family_key, live_samplers, floor, mode, warnings)
    _enforce_allowlist(settings, "scheduler", "schedulers", family_key, live_schedulers, floor, mode, warnings)
    # The cap runs BEFORE the legality snap, and the order is load-bearing: the other way round
    # (which is how this shipped) produced a capped LTX canvas of 1123x636 -- 1123 % 32 == 3, a pair
    # LTX's own adapter would refuse, displayed in the cockpit as though it were a size. Whatever
    # the cap picks, the snap is what makes it legal, so the snap has to be last.
    _apply_hardware_cap(settings, vram_gb, warnings)
    _snap_canvas_legality(settings, family_key, mode, warnings)

    return {
        "settings": settings,
        "family": family_key,
        "warnings": warnings,
        "operating_point": operating_point or None,
    }
