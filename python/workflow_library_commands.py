"""Workflow-library TCP commands.

Extracted from worker_service.py. Import/scan/readiness stay in
workflow_importer / workflow_scanner; this file is the command layer.
"""
from __future__ import annotations

from comfy_endpoint import comfy_endpoint

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from comfy_graph_helpers import _sv_choose_comfy_choice, _sv_comfy_input_choices
from request_payload import bounded_option
from worker_service_state import JobRecord, numeric_option, utc_now_iso


def _ws():
    import worker_service as ws
    return ws


def handle_import_workflow_command(req: dict[str, Any]) -> dict[str, Any]:
    try:
        from workflow_importer import import_workflow
    except Exception as exc:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": f"workflow_importer import failed: {exc}",
        }

    source = str(req.get("source") or req.get("workflow_path") or "").strip()
    if not source:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": "import_workflow requires source",
        }

    destination_root = str(req.get("destination_root") or _ws().imported_workflows_root()).strip()
    profile_name = str(req.get("profile_name") or "").strip() or None
    auto_apply_node_deps = bool(req.get("auto_apply_node_deps", False))
    auto_apply_model_deps = bool(req.get("auto_apply_model_deps", False))
    comfy_root = str(req.get("comfy_root") or _ws().default_comfy_root()).strip()
    python_executable = str(req.get("python_executable") or sys.executable).strip()
    model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
    civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
    node_catalog = str(req.get("node_catalog") or _ws().starter_node_catalog_path()).strip()

    # A link is the form a shared workflow actually arrives in. Fetch it here, so import_workflow
    # keeps taking a payload and everything downstream (scan, profile, dependency plans) is
    # identical whether the graph came off disk or off the internet.
    source_url: str | None = None
    fetch_notes: list[str] = []
    from workflow_url_import import WorkflowFetchError, fetch_workflow_from_url, is_url

    if is_url(source):
        try:
            fetched = fetch_workflow_from_url(source, civitai_api_key=civitai_api_key)
        except WorkflowFetchError as exc:
            return {
                "type": "workflow_import_result",
                "ok": False,
                "action": "import_workflow",
                "source_url": source,
                "error": str(exc),
            }
        source_url = fetched.source_url
        fetch_notes = list(fetched.notes)
        profile_name = profile_name or fetched.display_name
        source = fetched.payload  # type: ignore[assignment]

    try:
        result = import_workflow(
            source=source,
            destination_root=destination_root,
            profile_name=profile_name,
            comfy_root=comfy_root,
            python_executable=python_executable,
            node_catalog=node_catalog,
            auto_apply_node_deps=auto_apply_node_deps,
            auto_apply_model_deps=auto_apply_model_deps,
            civitai_api_key=civitai_api_key,
            model_cache_root=model_cache_root,
        )

        payload: dict[str, Any]
        if hasattr(result, "to_dict"):
            payload = result.to_dict()
        elif isinstance(result, dict):
            payload = dict(result)
        else:
            payload = {
                "ok": False,
                "error": f"Unexpected import_workflow result type: {type(result).__name__}",
            }

        payload["type"] = "workflow_import_result"
        payload["action"] = "import_workflow"
        if source_url:
            payload["source_url"] = source_url
            if fetch_notes:
                payload.setdefault("warnings", [])
                payload["warnings"] = list(payload["warnings"]) + fetch_notes
        return payload
    except Exception as exc:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_list_workflow_profiles_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(_ws().imported_workflows_root())
    root.mkdir(parents=True, exist_ok=True)
    profiles: list[dict[str, Any]] = []
    for profile_path in sorted(root.glob("*/profile.json")):
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        profile_payload = dict(payload) if isinstance(payload, dict) else {}
        profile_payload.update(
            {
                "name": profile_payload.get("profile_name") or profile_path.parent.name,
                "workflow_path": profile_payload.get("workflow_source"),
                "profile_path": str(profile_path),
                "import_root": str(profile_path.parent),
                "import_slug": profile_path.parent.name,
            }
        )
        profiles.append(profile_payload)
    return {
        "type": "workflow_profiles",
        "ok": True,
        "action": "list_workflow_profiles",
        "profiles": profiles,
        "count": len(profiles),
        "profiles_root": str(root),
    }


# ---------------------------------------------------------------------------
# Imported-workflow lifecycle: re-check / retry-install / delete.
# These operate on an ALREADY-imported profile folder (<slug>) under
# _ws().imported_workflows_root(), reusing the same scan + dependency-plan building
# blocks the importer uses, but against the LIVE comfy_root.
# ---------------------------------------------------------------------------

def _resolve_import_root(req: dict[str, Any]) -> Path | None:
    import_root = str(req.get("import_root") or "").strip()
    if not import_root:
        profile_path = str(req.get("profile_path") or "").strip()
        if profile_path:
            import_root = str(Path(profile_path).resolve().parent)
    return Path(import_root) if import_root else None


def _validate_models_against_object_info(model_report, api_url: str) -> dict[str, Any] | None:
    """Validate each extracted model literal against the LIVE /object_info loader lists, resolving the
    SAME way the launch path does (basename via _sv_choose_comfy_choice) so readiness PREDICTS launch.

    Returns {"missing", "ambiguous", "present"} or None if ComfyUI is unreachable (caller then falls
    back to the disk-based model plan). Semantics, deliberately fail-closed:
      - missing   = literal resolves to nothing installed (or its loader list is empty) -> would 400.
      - ambiguous = a BARE literal basename-matches installed models in >1 subfolder -> would render the
                    WRONG model. Surfaced as needs-review, never silently passed.
      - present   = resolves to exactly one installed entry.
    We never trust the worker's resolver as a black box that always says yes: a name absent from the
    live list is missing, full stop.
    """
    try:
        object_info = _ws()._comfy_object_info(api_url)
    except Exception:
        return None
    if not isinstance(object_info, dict) or not object_info:
        return None

    class_by_node = {n.node_id: n.class_type for n in getattr(model_report, "nodes", [])}
    base = lambda v: str(v).replace("\\", "/").rsplit("/", 1)[-1].lower()
    subdir = lambda v: str(v).replace("\\", "/").rsplit("/", 1)[0] if "/" in str(v).replace("\\", "/") else ""

    missing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    present: list[dict[str, Any]] = []
    for ref in getattr(model_report, "model_references", []):
        cls = class_by_node.get(ref.node_id, "")
        key = ref.input_name
        val = str(ref.value or "").strip()
        if not val or not cls or cls not in object_info:
            # No loader class in the live schema -> a NODE problem (handled by the node check), not a
            # model-presence verdict. Skip rather than mislabel.
            continue
        choices = _sv_comfy_input_choices(object_info, cls, key)
        if not choices:
            missing.append({"value": val, "class_type": cls, "input": key,
                            "reason": f"{cls}.{key} has no installed options"})
            continue
        resolved = _sv_choose_comfy_choice(object_info, cls, key, val)
        basename_hits = [c for c in choices if base(c) == base(val)]
        if val not in choices and len({subdir(c) for c in basename_hits}) > 1:
            ambiguous.append({"value": val, "class_type": cls, "input": key,
                              "candidates": sorted(basename_hits)})
        elif resolved not in choices:
            missing.append({"value": val, "class_type": cls, "input": key,
                            "reason": f"not in {cls}.{key} ({len(choices)} installed)"})
        else:
            present.append({"value": val, "resolved": resolved, "class_type": cls})
    return {"missing": missing, "ambiguous": ambiguous, "present": present}


def _recheck_workflow_dependencies(
    import_root: Path,
    *,
    comfy_root: str,
    node_catalog: str,
    python_executable: str,
    model_cache_root: str,
    civitai_api_key: str | None,
    api_url: str | None = None,
):
    """Re-scan the imported workflow + rebuild node/model plans against the live comfy_root.
    Returns (report, node_plan, model_plan, live_models).

    Model literals come from the CONVERTED API-prompt graph (prompt_api.json = exactly what
    run_comfy_workflow submits at launch), because a raw UI-graph hides them in positional
    widgets_values and scan_workflow yields model_references=[] (the false-"Ready" root cause). We do
    NOT reimplement widgets_values mapping here. When api_url is given, model presence is validated
    against the live /object_info lists (see _validate_models_against_object_info)."""
    from workflow_scanner import load_workflow_source, scan_workflow
    from node_dependency_resolver import build_node_install_plan
    from model_dependency_resolver import build_model_install_plan

    workflow_json = import_root / "workflow.json"
    if not workflow_json.is_file():
        raise FileNotFoundError(f"workflow.json not found in import root: {import_root}")

    # Nodes: scan the raw graph against the LIVE class set, so "missing" means genuinely absent from
    # this ComfyUI rather than absent from a hardcoded 26-name builtin list. Without it, core classes
    # (UNETLoader, Canny, EmptySD3LatentImage, ...) and non-executing nodes (Note, Reroute) were
    # reported as missing custom nodes and permanently disabled the Launch button.
    live_classes: set[str] | None = None
    live_display_names: set[str] | None = None
    try:
        object_info = _ws()._comfy_object_info(api_url)
        if isinstance(object_info, dict) and object_info:
            live_classes = set(object_info.keys())
            # A graph can store the human-readable node name in `type`. The converter rewrites those
            # at submit time, so detection has to agree or Launch stays disabled on a workflow that
            # actually runs.
            from comfy_graph_converter import display_name_aliases

            live_display_names = set(display_name_aliases(object_info))
    except Exception:
        live_classes = None

    workflow_source, payload = load_workflow_source(str(workflow_json))
    report = scan_workflow(payload, source_kind=workflow_source.source_kind,
                           live_classes=live_classes, live_display_names=live_display_names)

    # Models: if the raw scan found none (the UI-graph case), re-derive them from the compiled
    # API-prompt form, where MODEL_FIELD_MAP reads named inputs. api_report.nodes carry the class_types
    # the live /object_info validation needs. An API-prompt import (e.g. ltx-api-json) already has
    # model_references from the raw scan -> left untouched (the positive control).
    model_report = report
    api_prompt = import_root / "prompt_api.json"
    if not report.model_references and api_prompt.is_file():
        try:
            _, api_payload = load_workflow_source(str(api_prompt))
            api_report = scan_workflow(api_payload)
            if api_report.model_references:
                report.model_references = api_report.model_references
                model_report = api_report
        except Exception:
            pass

    # Node packs resolve from what the workflow itself declares (properties.cnr_id / aux_id / ver)
    # before any name match against the starter catalog. search_undeclared consults the cached
    # class->pack reverse index if one has been built; it never builds it (that is a background job).
    node_plan = build_node_install_plan(
        report,
        comfy_root=comfy_root,
        node_catalog=node_catalog,
        python_executable=python_executable,
        search_undeclared=True,
    )
    model_plan = build_model_install_plan(
        report,
        comfy_root=comfy_root,
        auto_materialize=False,
        cache_root=model_cache_root,
        civitai_api_key=civitai_api_key,
    )
    live_models = _validate_models_against_object_info(model_report, api_url) if api_url else None
    return report, node_plan, model_plan, live_models


def _write_recheck_into_profile(import_root: Path, comfy_root: str, node_plan, model_plan, applied: bool, live_models: dict[str, Any] | None = None, report=None) -> dict[str, Any]:
    """Persist the live re-check into the imported profile so the UI's
    loadWorkflowRecord reflects reality. The UI counts missing nodes from
    scan_report.json, so that file is the authoritative one to rewrite.

    When live_models is supplied it is the AUTHORITATIVE model signal (validated against live
    /object_info the way launch resolves); the disk-based model_plan is only the fallback used when
    ComfyUI was unreachable."""
    # Genuinely missing = anything not already installed/present.
    missing_nodes = sorted({dep.class_name for dep in node_plan.dependencies if dep.action != "already_installed"})
    node_counts = {
        "checked": len(node_plan.dependencies),
        "already_installed": sum(1 for dep in node_plan.dependencies if dep.action == "already_installed"),
        "installable": len(node_plan.install_actions),
        "unresolved": len(node_plan.unresolved_classes),
    }

    model_warnings: list[str] = []
    if live_models is not None:
        missing_models = live_models.get("missing", [])
        ambiguous_models = live_models.get("ambiguous", [])
        present_models = live_models.get("present", [])
        # Only genuine absence blocks as a "missing dependency"; ambiguity is a needs-review warning
        # (not a missing asset) so it surfaces as review, not as a download prompt.
        missing_assets = [str(m.get("value") or "") for m in missing_models]
        model_counts = {
            "checked": len(missing_models) + len(ambiguous_models) + len(present_models),
            "already_present": len(present_models),
            "missing": len(missing_models),
            "ambiguous": len(ambiguous_models),
        }
        for m in missing_models:
            model_warnings.append(f"missing model '{m.get('value')}' — {m.get('reason')}")
        for m in ambiguous_models:
            model_warnings.append(
                f"ambiguous model '{m.get('value')}' basename-matches multiple installed subfolders "
                f"{m.get('candidates')} — needs review (would render the wrong model)")
        models_ok = not missing_models and not ambiguous_models
    else:
        missing_assets = [str(a.get("source_value") or a.get("destination_path") or "") for a in model_plan.install_actions]
        model_counts = {
            "checked": len(model_plan.dependencies),
            "already_present": sum(1 for dep in model_plan.dependencies if dep.install_action == "already_present"),
            "missing": len(model_plan.install_actions),
        }
        models_ok = not model_plan.install_actions

    # A configured model root that could not be READ makes every model stored on it look missing,
    # in both branches -- ComfyUI cannot enumerate a locked drive either, so /object_info is no more
    # authoritative here than the disk walk. Said first, because without it the only thing on screen
    # is a list of models to download that the user very likely already owns.
    for entry in getattr(model_plan, "unreadable_roots", []):
        model_warnings.insert(0, (
            f"model root {entry.get('path')} could not be read ({entry.get('reason')}) — models "
            "stored there are reported missing for that reason alone"
        ))

    # A workflow that references a subgraph definition it does not carry cannot be converted, so it
    # cannot launch -- and before this it was not represented anywhere in the readiness conjunction.
    # The instance node is stamped cnr_id="comfy-core", so it never appeared in missing_nodes
    # either: the workflow reported READY and then failed at submit. This is the last place that
    # green badge could still come from.
    # `report` is optional: two callers have it, and a future one may not. Absent means "nothing
    # known about subgraphs here", which must not read as "there are none" -- but it also must not
    # invent a blocker, so the conjunction below is unaffected when it is None.
    unresolved_subgraphs = list(getattr(report, "unresolved_subgraphs", []) or []) if report is not None else []
    ready = not missing_nodes and models_ok and not unresolved_subgraphs

    verb = "Applied installs, then re-checked" if applied else "Re-checked"
    ambiguous_note = f", {model_counts.get('ambiguous', 0)} ambiguous" if model_counts.get("ambiguous") else ""
    summary = (
        f"{verb} against live ComfyUI: nodes {node_counts['already_installed']}/{node_counts['checked']} "
        f"already installed, {node_counts['installable']} installable, {node_counts['unresolved']} unresolved; "
        f"models {model_counts['already_present']}/{model_counts['checked']} present, {model_counts['missing']} missing{ambiguous_note}."
    )

    readiness_block = {
        "ok": ready,
        "summary": summary,
        "missing_node_classes": missing_nodes,
        "missing_runtime_assets": missing_assets,
        # Its own channel, deliberately not merged into missing_node_classes: a UUID listed among
        # node classes reads as "install this pack", which is not something anyone can act on.
        "unresolved_subgraphs": unresolved_subgraphs,
        # Unavailable packs behind a muted/bypassed node. Not blockers -- they cannot fail a launch
        # -- but they become blockers the moment the user un-bypasses, so they are surfaced.
        "inactive_missing_node_classes": (
            list(getattr(report, "inactive_missing_nodes", []) or []) if report is not None else []
        ),
        "errors": [],
        "warnings": list(node_plan.unresolved_classes) + model_warnings,
        "checked_at": utc_now_iso(),
        "checked_comfy_root": comfy_root,
        "node_counts": node_counts,
        "model_counts": model_counts,
    }

    # scan_report.json drives the UI's missing-node count + early readiness check.
    scan_path = import_root / "scan_report.json"
    if scan_path.is_file():
        try:
            scan_obj = json.loads(scan_path.read_text(encoding="utf-8"))
            if isinstance(scan_obj, dict):
                scan_obj["missing_custom_nodes"] = missing_nodes
                scan_path.write_text(json.dumps(scan_obj, indent=2), encoding="utf-8")
        except Exception:
            pass

    # profile.json: refresh the static missing list + the last_launch_readiness block.
    profile_path = import_root / "profile.json"
    if profile_path.is_file():
        try:
            profile_obj = json.loads(profile_path.read_text(encoding="utf-8"))
            if isinstance(profile_obj, dict):
                metadata = profile_obj.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    profile_obj["metadata"] = metadata
                metadata["missing_custom_nodes"] = missing_nodes
                metadata["last_launch_readiness"] = readiness_block
                profile_path.write_text(json.dumps(profile_obj, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {
        "ready": ready,
        "summary": summary,
        "missing_node_classes": missing_nodes,
        "missing_runtime_assets": missing_assets,
        "node_counts": node_counts,
        "model_counts": model_counts,
    }


def handle_check_workflow_launch_readiness_command(req: dict[str, Any]) -> dict[str, Any]:
    """Cheap re-check (NO install): re-scan an imported profile against the live
    ComfyUI and rewrite its stored readiness/missing-node set."""
    try:
        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return {
                "type": "workflow_readiness_result",
                "ok": False,
                "action": "check_workflow_launch_readiness",
                "error": "check_workflow_launch_readiness requires a valid import_root or profile_path",
            }

        comfy_root = str(req.get("comfy_root") or _ws().default_comfy_root()).strip()
        node_catalog = str(req.get("node_catalog") or _ws().starter_node_catalog_path()).strip()
        python_executable = str(req.get("python_executable") or sys.executable).strip()
        model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
        civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
        api_url = comfy_endpoint(req)

        report, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
            import_root,
            comfy_root=comfy_root,
            node_catalog=node_catalog,
            python_executable=python_executable,
            model_cache_root=model_cache_root,
            civitai_api_key=civitai_api_key,
            api_url=api_url,
        )
        result = _write_recheck_into_profile(import_root, comfy_root, node_plan, model_plan, applied=False, live_models=live_models, report=report)
        return {
            "type": "workflow_readiness_result",
            "ok": True,
            "action": "check_workflow_launch_readiness",
            "import_root": str(import_root),
            **result,
        }
    except Exception as exc:
        return {
            "type": "workflow_readiness_result",
            "ok": False,
            "action": "check_workflow_launch_readiness",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_compile_workflow_prompt_command(req: dict[str, Any]) -> dict[str, Any]:
    """Compile an imported UI-graph workflow into an API prompt, against the LIVE schema.

    This is the single place a UI graph becomes an API prompt outside of launch. It exists to
    replace the C++ compiler in WorkflowLibraryPage, which used a hardcoded 21-class widget table
    and silently emitted ``"inputs": {}`` for anything outside it -- 530 nodes across 19 of 80
    workflows lost every widget value that way.

    THREE-STATE CONTRACT, and it is the whole point of this command. Callers must be able to tell:

      object_info_available=False        -> UNKNOWN. ComfyUI is not reachable, so nothing was
                                            checked. This is NOT "no missing nodes" and NOT
                                            "missing nodes"; a caller that collapses it into either
                                            will lie to the user.
      missing_classes non-empty          -> those classes are genuinely absent from the live schema.
      missing_classes == [] and available -> convertible.

    _validate_models_against_object_info already has the opposite bug on the model side: it returns
    None when ComfyUI is unreachable and the caller silently falls back to the disk plan, which can
    report ready. Do not repeat that here.

    A partial prompt is still returned when classes are missing, because it is useful for inspection
    -- but ``ok`` reflects whether it is COMPLETE, so nobody launches a partial graph by accident.
    """
    try:
        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return {
                "type": "workflow_compile_result",
                "ok": False,
                "action": "compile_workflow_prompt",
                "error": "compile_workflow_prompt requires a valid import_root or profile_path",
            }

        workflow_path = import_root / "workflow.json"
        if not workflow_path.is_file():
            return {
                "type": "workflow_compile_result",
                "ok": False,
                "action": "compile_workflow_prompt",
                "import_root": str(import_root),
                "error": f"workflow.json not found under {import_root}",
            }

        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        api_url = comfy_endpoint(req)

        from comfy_graph_converter import convert_ui_graph, is_ui_graph

        object_info: dict[str, Any] | None = None
        try:
            fetched = _ws()._comfy_object_info(api_url)
            if isinstance(fetched, dict) and fetched:
                object_info = fetched
        except Exception:
            object_info = None

        if object_info is None:
            # Report the unknown honestly rather than guessing in either direction.
            return {
                "type": "workflow_compile_result",
                "ok": False,
                "action": "compile_workflow_prompt",
                "import_root": str(import_root),
                "object_info_available": False,
                "missing_classes": [],
                "reason": "ComfyUI is not reachable, so node availability could not be checked.",
            }

        if not is_ui_graph(workflow):
            # Already an API prompt; nothing to compile.
            return {
                "type": "workflow_compile_result",
                "ok": True,
                "action": "compile_workflow_prompt",
                "import_root": str(import_root),
                "object_info_available": True,
                "graph_format": "comfy_api_prompt",
                "missing_classes": [],
                "node_count": len(workflow) if isinstance(workflow, dict) else 0,
                "compiled_prompt_path": None,
            }

        result = convert_ui_graph(workflow, object_info)

        compiled_path = import_root / "prompt_api.json"
        compiled_path.write_text(json.dumps(result.prompt, indent=2), encoding="utf-8")

        return {
            "type": "workflow_compile_result",
            "ok": not result.missing_classes,
            "action": "compile_workflow_prompt",
            "import_root": str(import_root),
            "object_info_available": True,
            "graph_format": "comfy_ui_graph",
            "compiled_prompt_path": str(compiled_path),
            "node_count": result.node_count,
            "missing_classes": result.missing_classes,
            "dropped_ui_only_count": len(result.dropped_ui_only),
        }
    except Exception as exc:
        return {
            "type": "workflow_compile_result",
            "ok": False,
            "action": "compile_workflow_prompt",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_build_node_class_index_command(req: dict[str, Any]) -> dict[str, Any]:
    """Build (or extend) the Registry class->pack reverse index.

    Most workflows name their own packs in ``properties.cnr_id`` / ``aux_id``, and that path needs no
    index at all. This exists for the rest: an older export whose nodes carry no properties gives
    nothing but a class name, and the Registry has no class->pack endpoint -- ``?search=`` is ignored
    and ``/comfy-nodes?comfy_node_name=X`` proves a class exists without naming its pack. Ranking
    packs by name similarity does not work either: measured on this library it resolved 0 of the 16
    undeclared classes, because the packs providing ``SetNode``, ``LoadImageBatch`` and
    ``CR Upscale Image`` share no words with those names.

    So the index has to be assembled by reading every pack's node list once -- 5340 packs, ~2s each
    sequentially. It is deliberately a separate command rather than something a dependency check
    triggers: ``budget_sec`` bounds one call's wall clock and the build resumes exactly where it
    stopped, so a caller can drive it in slices and watch ``packs_indexed`` climb.
    """
    try:
        from workflow_pack_resolver import ClassPackIndex, PackDirectory

        budget_sec = numeric_option(req, "budget_sec", 120.0)
        workers = max(1, min(8, int(req.get("workers") or 6)))

        directory = PackDirectory(req.get("directory_path") or None)
        if not directory.ensure(timeout=bounded_option(req, "timeout_sec", 20.0)):
            return {
                "type": "node_class_index_result",
                "ok": False,
                "action": "build_node_class_index",
                "error": "Could not read the pack list from the ComfyUI Registry.",
            }

        index = ClassPackIndex(req.get("index_path") or None)
        summary = index.build(
            directory,
            timeout=bounded_option(req, "timeout_sec", 20.0),
            workers=workers,
            budget_sec=budget_sec,
        )
        return {
            "type": "node_class_index_result",
            "ok": True,
            "action": "build_node_class_index",
            "index_path": str(index.path),
            **summary,
        }
    except Exception as exc:
        return {
            "type": "node_class_index_result",
            "ok": False,
            "action": "build_node_class_index",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_retry_workflow_dependencies_command(req: dict[str, Any]) -> dict[str, Any]:
    """Re-check against the live ComfyUI, then (if auto_apply_*) install ONLY the
    genuinely-missing-and-resolvable nodes/models, then re-check and persist."""
    try:
        from node_dependency_resolver import apply_node_install_plan
        from model_dependency_resolver import apply_model_install_plan

        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return {
                "type": "workflow_dependency_retry_result",
                "ok": False,
                "action": "retry_workflow_dependencies",
                "error": "retry_workflow_dependencies requires a valid import_root or profile_path",
            }

        comfy_root = str(req.get("comfy_root") or _ws().default_comfy_root()).strip()
        node_catalog = str(req.get("node_catalog") or _ws().starter_node_catalog_path()).strip()
        python_executable = str(req.get("python_executable") or sys.executable).strip()
        model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
        civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
        auto_apply_node_deps = bool(req.get("auto_apply_node_deps", False))
        auto_apply_model_deps = bool(req.get("auto_apply_model_deps", False))
        api_url = comfy_endpoint(req)

        # 1) Live re-check FIRST.
        report, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
            import_root,
            comfy_root=comfy_root,
            node_catalog=node_catalog,
            python_executable=python_executable,
            model_cache_root=model_cache_root,
            civitai_api_key=civitai_api_key,
            api_url=api_url,
        )

        apply_errors: list[str] = []
        applied = False
        # 2) Install ONLY install_actions. already_installed nodes are never in
        #    plan.install_actions, so they are skipped (not re-cloned).
        if auto_apply_node_deps and node_plan.install_actions:
            node_apply = apply_node_install_plan(node_plan, comfy_root=comfy_root, python_executable=python_executable)
            applied = True
            if not node_apply.ok:
                apply_errors.extend(node_apply.errors)
        if auto_apply_model_deps and model_plan.install_actions:
            model_apply = apply_model_install_plan(model_plan)
            applied = True
            if not model_apply.ok:
                apply_errors.extend(model_apply.errors)

        # 3) Re-check AFTER install to capture the post-install state, then persist.
        if applied:
            report, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
                import_root,
                comfy_root=comfy_root,
                node_catalog=node_catalog,
                python_executable=python_executable,
                model_cache_root=model_cache_root,
                civitai_api_key=civitai_api_key,
                api_url=api_url,
            )
        result = _write_recheck_into_profile(import_root, comfy_root, node_plan, model_plan, applied=applied, live_models=live_models, report=report)
        return {
            "type": "workflow_dependency_retry_result",
            "ok": not apply_errors,
            "action": "retry_workflow_dependencies",
            "import_root": str(import_root),
            "applied": applied,
            "apply_errors": apply_errors,
            **result,
        }
    except Exception as exc:
        return {
            "type": "workflow_dependency_retry_result",
            "ok": False,
            "action": "retry_workflow_dependencies",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_delete_workflow_profile_command(req: dict[str, Any]) -> dict[str, Any]:
    """Delete an imported workflow's <slug> folder, guarded against deleting
    anything that is not a direct child of _ws().imported_workflows_root()."""
    import shutil
    try:
        import_root = _resolve_import_root(req)
        if import_root is None:
            return {
                "type": "workflow_delete_result",
                "ok": False,
                "action": "delete_workflow_profile",
                "error": "delete_workflow_profile requires import_root or profile_path",
            }

        root = Path(_ws().imported_workflows_root()).resolve()
        target = import_root.resolve()

        # Safety: target must be a direct <slug> subfolder of the imported root,
        # never the root itself, a deeper path, or anything outside it.
        if target == root or target.parent != root or root not in target.parents:
            return {
                "type": "workflow_delete_result",
                "ok": False,
                "action": "delete_workflow_profile",
                "error": f"Refusing to delete '{target}': not a workflow folder directly under {root}",
            }

        if not target.is_dir():
            return {
                "type": "workflow_delete_result",
                "ok": True,
                "action": "delete_workflow_profile",
                "import_root": str(target),
                "already_absent": True,
            }

        shutil.rmtree(target)
        return {
            "type": "workflow_delete_result",
            "ok": True,
            "action": "delete_workflow_profile",
            "import_root": str(target),
            "deleted": True,
        }
    except Exception as exc:
        return {
            "type": "workflow_delete_result",
            "ok": False,
            "action": "delete_workflow_profile",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _discovery_normpath(path: str) -> str:
    """Normalize a path for dedupe comparison (case-insensitive on Windows)."""
    try:
        resolved = str(Path(path).resolve())
    except Exception:
        resolved = str(path)
    return os.path.normcase(resolved)


def _sha256_file_bytes(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def _imported_profile_identity_index(profiles_root: Path) -> dict[str, dict[str, Any]]:
    """Map sha256 -> imported-profile identity, built from Step 1's discovery keys.

    Reads existing profile.json files only; profiles without a
    discovery_source_sha256 (e.g. pre-Step-1 imports or in-memory sources) are
    skipped because they cannot be matched by content. WRITES NOTHING and never
    creates the directory.
    """
    index: dict[str, dict[str, Any]] = {}
    if not profiles_root.is_dir():
        return index
    for profile_path in sorted(profiles_root.glob("*/profile.json")):
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        sha = str(payload.get("discovery_source_sha256") or "").strip()
        if not sha or sha in index:
            continue
        index[sha] = {
            "profile_path": str(profile_path),
            "import_slug": profile_path.parent.name,
            "imported_source_path": payload.get("discovery_source_path"),
        }
    return index


def handle_discover_comfy_workflows_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    """List ComfyUI graph .json files and split them into discovered vs already-imported.

    Pure read + classify: recursively hashes every *.json under the workflows dir
    and cross-references each hash against existing imported profiles' Step-1
    discovery keys. WRITES NOTHING.
    """
    req = req or {}

    workflows_dir = str(req.get("workflows_dir") or "").strip()
    if not workflows_dir:
        comfy_root = str(req.get("comfy_root") or _ws().default_comfy_root()).strip()
        workflows_dir = str(Path(comfy_root) / "user" / "default" / "workflows")
    workflows_path = Path(workflows_dir)

    profiles_root = Path(str(req.get("destination_root") or _ws().imported_workflows_root()).strip())
    identity_index = _imported_profile_identity_index(profiles_root)

    discovered: list[dict[str, Any]] = []
    already_imported: list[dict[str, Any]] = []

    if workflows_path.is_dir():
        for source in sorted(workflows_path.rglob("*.json")):
            if not source.is_file():
                continue
            sha = _sha256_file_bytes(source)
            if sha is None:
                continue
            source_str = str(source.resolve())
            entry: dict[str, Any] = {
                "source_path": source_str,
                "sha256": sha,
                "filename": source.name,
                "already_imported": False,
            }
            match = identity_index.get(sha)
            if match is not None:
                imported_path = match.get("imported_source_path")
                path_changed = bool(
                    imported_path
                    and _discovery_normpath(str(imported_path)) != _discovery_normpath(source_str)
                )
                entry.update(
                    {
                        "already_imported": True,
                        "path_changed": path_changed,
                        "profile_path": match.get("profile_path"),
                        "import_slug": match.get("import_slug"),
                        "imported_source_path": imported_path,
                    }
                )
                already_imported.append(entry)
            else:
                discovered.append(entry)

    return {
        "type": "comfy_workflow_discovery",
        "ok": True,
        "action": "discover_comfy_workflows",
        "workflows_dir": str(workflows_path),
        "workflows_dir_exists": workflows_path.is_dir(),
        "profiles_root": str(profiles_root),
        "discovered": discovered,
        "already_imported": already_imported,
        "discovered_count": len(discovered),
        "already_imported_count": len(already_imported),
    }

