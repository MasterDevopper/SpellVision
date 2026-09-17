"""The worker command that reads the optimization ledger back out.

``optimization_results`` is DIAGNOSTIC: nothing in ``qt_ui/`` reaches it yet, by design -- the row
shape has to settle against a real matrix run before a surface is built on it. It is registered now
anyway, because an unregistered wire type arrives at every client as ``client_warning`` with
``ok: false``, so a command that is only used from a terminal still has to be a first-class reply.

The reply carries ``cut_levers`` alongside the rows. The reasons a lever was cut are the half of the
evidence that never gets written down -- "we measured seven levers" reads as a complete answer until
someone asks why FlashAttention is not in the table -- so they travel with the results rather than
living only in a research file whose next revision will drop them.
"""
from __future__ import annotations

from typing import Any

import optimization_levers
import optimization_results


def _matches(row: dict[str, Any], key: str, wanted: str) -> bool:
    return not wanted or str(row.get(key) or "") == wanted


def handle_optimization_results_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    family = str(req.get("family") or "").strip()
    lever = str(req.get("lever") or "").strip()

    raw_limit = req.get("limit")
    try:
        limit = int(raw_limit) if raw_limit not in (None, "") else None
    except (TypeError, ValueError):
        limit = None

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
        "path": str(optimization_results.ledger_path()),
    }
