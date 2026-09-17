"""The render's own record, read off disk instead of assumed from the wire.

The worker's LAST message on the harness's socket is ``EventEmitter.result`` (``worker_tcp.py``):
after generation returns, the TCP handler calls ``emitter.result(job)``, which flattens
``asdict(job.result)`` onto the top level of a bare ``{"type": "result", ...}`` payload -- there is
no nested ``"result"`` key on that message. An earlier ``job_update`` push (``emit_job_update``,
called from inside the runner before that) DOES nest its fields under ``"result"``, but it is not
the last message with ``state == "completed"``, so it never survives to be the terminal message
``measure_optimizations_link.render`` returns. A reader that looks for a nested ``result`` key on
the terminal message finds nothing on every real run -- which is exactly what happened on the 36-render
matrix that recorded zero rows.

The render's sidecar has none of that ambiguity. Every render writes ``generation_time_sec`` and its
own ``optimizations`` block to the path the request itself named as ``metadata_output`` -- this
harness put that path on the request, so it does not need to guess it back. This module reads that
one file and hands back plain values; it does not decide what a caller does when the file is
missing, because "the job completed but reported no time" is a refusal the caller owns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_sidecar(path: str) -> tuple[dict[str, Any] | None, str | None]:
    """The metadata JSON a render wrote next to its output, or why it could not be read.

    Returns ``(None, reason)`` for a missing path, a missing file, a body that is not valid JSON, or
    a body that parsed to something other than an object -- one shape for the caller to check instead
    of three different exception types.
    """
    if not path:
        return None, "no metadata_output path was given for this render"
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"the sidecar at {path} could not be read: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"the sidecar at {path} did not parse as JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"the sidecar at {path} was not a JSON object"
    return data, None


def seconds_from(sidecar: dict[str, Any] | None) -> float | None:
    """``generation_time_sec`` off a sidecar already read, or ``None``."""
    if not isinstance(sidecar, dict):
        return None
    value = sidecar.get("generation_time_sec")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def provenance_from(sidecar: dict[str, Any] | None) -> dict[str, Any] | None:
    """The ``optimizations`` block off a sidecar already read, or ``None`` when it is absent or
    empty -- never an empty dict, so a caller can use plain truthiness to decide whether to fall
    back."""
    if not isinstance(sidecar, dict):
        return None
    block = sidecar.get("optimizations")
    return dict(block) if isinstance(block, dict) and block else None


def resolve_seconds(sidecar: dict[str, Any] | None, result: dict[str, Any]) -> float | None:
    """The render time: the sidecar's own figure, or the terminal message's, or neither."""
    seconds = seconds_from(sidecar)
    if seconds is not None:
        return seconds
    value = result.get("generation_time_sec")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def resolve_provenance(
    sidecar: dict[str, Any] | None, result: dict[str, Any], fallback: dict[str, Any] | None,
) -> dict[str, Any]:
    """The build that produced this render: the sidecar's own block, then the terminal message's,
    then the argv read back at restart -- each one step further from the render it is describing."""
    provenance = provenance_from(sidecar)
    if provenance is not None:
        return {**provenance, "provenance_source": "render_sidecar"}
    envelope = result.get("optimizations")
    if isinstance(envelope, dict) and envelope:
        return {**envelope, "provenance_source": "render_result"}
    return {
        **dict(fallback or {}),
        "provenance_source": "restart_argv",
        "probe_error": ("neither the sidecar nor the render's result carried an optimizations "
                        "block; this provenance was read from the restart reply's argv instead"),
    }
