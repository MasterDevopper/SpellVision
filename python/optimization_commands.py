"""The worker command that reads the optimization ledger back out.

``optimization_results`` is USER_FACING as of W3 T6: the Runtime page's optimization panel is its
route (``qt_ui/ManagerPage.cpp``). It stayed DIAGNOSTIC while the row shape was settling; a surface
built on a shape that was still moving is how a number nobody measured gets published.

The reply carries ``cut_levers`` alongside the rows. The reasons a lever was cut are the half of the
evidence that never gets written down -- "we measured seven levers" reads as a complete answer until
someone asks why FlashAttention is not in the table -- so they travel with the results rather than
living only in a research file whose next revision will drop them.

It also carries two blocks the panel cannot render an honest row without:

``catalogue``
    Every lever the project knows about, measured or not, with its label and its status. Without it
    a panel could only show levers that already have rows -- and a lever nobody has measured
    disappearing from the table is precisely the invisibility this wave exists to remove.

``provenance``
    ``optimization_provenance.probe()``: what the RUNNING ComfyUI process was launched with, plus
    what is installed in its venv. Installed and active are different facts -- ``sageattention`` is
    installed on this box and the running process was launched without the flag -- and a panel that
    reads only one of them tells the user the other.
"""
from __future__ import annotations

from typing import Any

import optimization_levers
import optimization_provenance
import optimization_results


def _matches(row: dict[str, Any], key: str, wanted: str) -> bool:
    return not wanted or str(row.get(key) or "") == wanted


def _catalogue() -> list[dict[str, Any]]:
    """Every lever, in catalogue order, as the panel needs it.

    Labels live here rather than in the C++ so the two surfaces cannot disagree about what a lever
    is called; the UI derives installed/active from the provenance block and nothing else.
    """
    return [
        {
            "id": lever.id,
            "label": lever.label,
            "kind": lever.kind,
            "status": lever.status,
            "note": lever.note,
            "blocked_reason": lever.blocked_reason,
        }
        for lever in optimization_levers.ALL_LEVERS
    ]


def handle_optimization_results_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    family = str(req.get("family") or "").strip()
    lever = str(req.get("lever") or "").strip()

    raw_limit = req.get("limit")
    try:
        limit = int(raw_limit) if raw_limit not in (None, "") else None
    except (TypeError, ValueError):
        limit = None

    try:
        provenance = optimization_provenance.probe()
    except Exception as exc:  # noqa: BLE001 -- reading the ledger must not fail on a dead ComfyUI
        # probe() already swallows a failed HTTP read into an honest "unknown" block; this catches
        # the rarer case where resolving the endpoint itself raises. Either way the panel must be
        # told the arm could not be read, not handed a default it never observed.
        provenance = {"attention_backend": "unknown", "probe_error": str(exc), "comfy_argv": []}

    rows = optimization_results.read(limit=limit)
    if family or lever:
        rows = [row for row in rows if _matches(row, "family", family) and _matches(row, "lever", lever)]

    summary = optimization_results.summarize(rows)
    return {
        "type": "optimization_results",
        "ok": True,
        "rows": rows,
        "families": summary["families"],
        "levers": summary["levers"],
        "unmeasured_levers": optimization_results.unmeasured_levers(rows),
        "blocked_levers": {
            lever_def.id: lever_def.blocked_reason for lever_def in optimization_levers.blocked_levers()
        },
        "cut_levers": dict(optimization_levers.CUT_LEVERS),
        "catalogue": _catalogue(),
        "provenance": provenance,
        "path": str(optimization_results.ledger_path()),
    }
