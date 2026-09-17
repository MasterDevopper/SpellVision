"""The worker command over ``endpoint_capability``: ask an endpoint whether it can run this job.

Separated from the capability logic on purpose. ``endpoint_capability`` speaks HTTP to one ComfyUI
and answers a question about a graph; this module is where a *request* becomes that question --
which endpoint, which graph, and how the answer is shaped for the wire.

The graph can arrive three ways, in this order:

1. ``req["prompt"]`` -- an already-compiled API prompt. This is the one W6 Task 4 will use, because
   the routing decision happens after the cockpit has compiled the graph it is about to submit.
2. ``req["workflow"]`` -- the same thing under the name the workflow paths use.
3. ``req["import_root"]`` / ``req["profile_path"]`` -- an imported workflow on disk, compiled by the
   loader the substitution offer already uses, so the gate asks about the graph the launch path
   would really send rather than a second reading of it.

Filed DIAGNOSTIC in ``worker_command_audience`` until Task 4 gives it a ``qt_ui/`` route. The
audience ratchet requires a literal in the UI for anything called user-facing, and promoting it
early would assert a route that does not exist.
"""
from __future__ import annotations

from typing import Any

from comfy_endpoint import comfy_endpoint
from endpoint_capability import check_endpoint

MESSAGE_TYPE = "endpoint_capability"


def _graph_from_request(req: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    for key in ("prompt", "workflow", "compiled_prompt"):
        value = req.get(key)
        if isinstance(value, dict) and value:
            return value, key
    if req.get("import_root") or req.get("profile_path"):
        try:
            from model_resolution_commands import _load_graph
            from workflow_library_commands import _resolve_import_root
        except Exception as exc:  # pragma: no cover - import guard
            return None, f"workflow loading unavailable ({exc})"
        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return None, "import_root did not resolve to a workflow directory"
        graph, source = _load_graph(import_root, None)
        return (graph if isinstance(graph, dict) and graph else None), source
    return None, "no prompt, workflow or import_root in the request"


def handle_endpoint_capability_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    endpoint = str(comfy_endpoint(req)).rstrip("/")
    label = str(req.get("endpoint_label") or req.get("endpoint_id") or "").strip()

    graph, graph_source = _graph_from_request(req)
    if graph is None:
        where = label or endpoint
        return {
            "type": MESSAGE_TYPE,
            "ok": False,
            "action": MESSAGE_TYPE,
            "endpoint": endpoint,
            "label": label,
            "graph_source": graph_source,
            "checks_run": [],
            "refusals": [{
                "check": "graph", "code": "no_graph",
                "detail": f"There is no graph to check, so {where} cannot be cleared to run it: {graph_source}.",
                "missing": [],
            }],
            "message": f"There is no graph to check, so {where} cannot be cleared to run it: {graph_source}.",
        }

    report = check_endpoint(
        graph,
        endpoint,
        label=label,
        health_timeout_sec=_seconds(req, "health_timeout_sec", 5.0),
        models_timeout_sec=_seconds(req, "models_timeout_sec", 15.0),
        object_info_timeout_sec=_seconds(req, "object_info_timeout_sec", 30.0),
    )
    payload = report.payload()
    payload["type"] = MESSAGE_TYPE
    payload["action"] = MESSAGE_TYPE
    payload["graph_source"] = graph_source
    return payload


def _seconds(req: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(req.get(key, default))
    except (TypeError, ValueError):
        return default
    # A zero or negative budget would mean "never time out" to http.client, which is the opposite
    # of what someone typing 0 wants from a gate whose whole job is to not hang.
    return value if value > 0 else default
