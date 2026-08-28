"""Worker command: what can we offer for the models a workflow is missing?

Assembles the pieces that already exist -- the graph converter, architecture inference, the local
catalog, and the Civitai exact-filename identification -- into one answer the UI can render as a
choice. It performs nothing: no download starts, no substitution is applied. Doc 19's rule is that
we never auto-download on a guess and never silently substitute, so this returns an *offer*.

Two sources for "what is installed", in that order:

  1. **Live ``/object_info``** when ComfyUI is up. This is what the launch path itself will see, so
     an offer built from it predicts the launch rather than approximating it.
  2. **The configured model roots on disk**, ``extra_model_paths.yaml``-aware, when it is not.

Both yield names RELATIVE to the category root (``sdxl/foo.safetensors``), which matters: the
classifier reads the architecture out of that leading folder, and a bare basename would classify
as unknown and offer nothing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from model_resolution_offer import build_offer
from workflow_architecture_inference import (
    MODEL_LOADER_INPUTS,
    ambiguous_model_references,
    infer_required_architecture,
    missing_model_references,
)

_WEIGHT_EXT = {".safetensors", ".ckpt", ".gguf", ".pt", ".pth", ".bin"}


def _ws():
    import worker_service as ws

    return ws


def installed_from_object_info(object_info: dict[str, Any]) -> list[str]:
    """Every checkpoint/unet name ComfyUI reports it can load.

    Delegates to the LAUNCH path's reader rather than parsing ``/object_info`` again. This function
    used to handle only the legacy ``[[choice, ...]]`` shape, and newer ComfyUI cores emit
    ``["COMBO", {"options": [...]}]`` for some nodes instead -- on the core in front of me
    ``KSamplerSelect`` has already migrated while the model loaders have not. A loader migrating
    would have made this return nothing for that loader, so a model on disk would read as missing
    and the picker would offer substitutes for a file the user already had.

    Sharing the reader is the point: a catalog that disagrees with the launcher's own resolution is
    a bug generator, and that disagreement is exactly what produced the false "112 substitutes"
    result earlier in this branch.
    """
    from comfy_graph_helpers import _sv_comfy_input_choices

    names: set[str] = set()
    for class_name, input_name in MODEL_LOADER_INPUTS.items():
        names.update(_sv_comfy_input_choices(object_info, class_name, input_name))
    return sorted(names)


# Walking the configured model roots means walking D:/AI_ASSETS, which on this box is tens of
# thousands of files. One offer is fine; answering for a whole library re-walked it per workflow
# and took minutes. Short TTL rather than explicit invalidation: a newly downloaded model must
# show up on its own, and 30s is faster than anyone can finish a download and come back.
_DISK_CATALOG_TTL_SEC = 30.0
_DISK_CATALOG_CACHE: dict[tuple[str, str], tuple[float, list[str]]] = {}


# Every category a model loader can bind from. `checkpoints` alone is not enough and the omission
# is invisible in the result rather than in an error: Wan and Hunyuan ship as diffusion models
# under `diffusion_models/` or `unet/`, so a checkpoints-only scan reported "nothing on disk to
# offer" for every video workflow while 30 compatible files sat one folder over.
MODEL_CATEGORY_SUBDIRS: tuple[str, ...] = ("checkpoints", "diffusion_models", "unet")


def installed_from_disk_all(
    comfy_root: str | os.PathLike[str],
    subdirs: tuple[str, ...] = MODEL_CATEGORY_SUBDIRS,
) -> list[str]:
    """Union of every model category a loader can bind from."""
    names: set[str] = set()
    for subdir in subdirs:
        names.update(installed_from_disk(comfy_root, subdir))
    return sorted(names)


def installed_from_disk(
    comfy_root: str | os.PathLike[str],
    subdir: str = "checkpoints",
    *,
    use_cache: bool = True,
) -> list[str]:
    """Weight files under every configured root for ``subdir``, relative to that root.

    Relative, not absolute and not basename-only: the architecture lives in the leading folder,
    and both other shapes throw it away.
    """
    import time

    from model_dependency_resolver import _load_extra_model_path_roots

    cache_key = (str(comfy_root), str(subdir))
    if use_cache:
        cached = _DISK_CATALOG_CACHE.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < _DISK_CATALOG_TTL_SEC:
            return list(cached[1])

    root_path = Path(comfy_root)
    roots: list[Path] = []
    default_root = root_path / "models" / subdir
    if default_root.is_dir():
        roots.append(default_root)
    for configured in (_load_extra_model_path_roots(root_path).get(subdir) or []):
        if configured.is_dir():
            roots.append(configured)

    names: set[str] = set()
    for root in roots:
        for dirpath, _dirnames, files in os.walk(root):
            for file_name in files:
                if Path(file_name).suffix.lower() not in _WEIGHT_EXT:
                    continue
                full = Path(dirpath) / file_name
                try:
                    names.add(full.relative_to(root).as_posix())
                except ValueError:
                    names.add(file_name)

    result = sorted(names)
    _DISK_CATALOG_CACHE[cache_key] = (time.monotonic(), result)
    return list(result)


def _loaders_have_inputs(graph: dict[str, Any]) -> bool:
    """True unless a model loader compiled to an empty ``inputs`` dict.

    This guard exists because the failure it catches is silent and reassuring. A graph whose
    loaders lost their widget values -- which is exactly what the superseded C++ converter
    produced for 530 nodes across 19 workflows -- binds no model names at all, so "which models
    are missing?" answers **none**, and the user is told everything is fine. An artifact that
    cannot be read must report unreadable, never empty.
    """
    loaders = [n for n in graph.values()
               if isinstance(n, dict) and str(n.get("class_type") or "") in MODEL_LOADER_INPUTS]
    if not loaders:
        return True  # genuinely no model loaders; nothing to be wrong about
    return any(isinstance(n.get("inputs"), dict) and n["inputs"] for n in loaders)


def _missing_node_classes(ui_graph: dict[str, Any], object_info: dict[str, Any]) -> list[str]:
    """Node classes the graph uses that this ComfyUI cannot provide.

    Reads the UI-graph shape directly, because the point is to explain a conversion that did not
    happen -- there is no API graph to inspect. UI-only nodes (Note, Reroute, ...) are excluded via
    the converter's own set rather than a second list that would drift away from it.
    """
    try:
        from comfy_graph_converter import _UI_ONLY_TYPES
    except Exception:
        _UI_ONLY_TYPES = frozenset()

    known = set(object_info or {})
    missing: list[str] = []
    for node in (ui_graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("type") or "").strip()
        if not class_type or class_type in _UI_ONLY_TYPES or class_type in known:
            continue
        if class_type not in missing:
            missing.append(class_type)
    return sorted(missing)


def _load_graph(import_root: Path, object_info: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """Return (graph, source). Source is reported so the UI can say where the answer came from."""
    # Why the live path did not produce a graph, stated rather than assumed. The first version of
    # this hardcoded "ComfyUI was unreachable" on the fallback, and then reported exactly that while
    # the catalog had just been read from a live /object_info -- the conversion had failed instead.
    # A message that names a cause it never checked is worse than one that names none.
    reason = "workflow.json is missing"

    workflow_path = import_root / "workflow.json"
    if workflow_path.is_file():
        try:
            raw = json.loads(workflow_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raw = None
            reason = f"workflow.json could not be parsed ({exc.__class__.__name__})"

        if isinstance(raw, dict):
            from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

            if not is_ui_graph(raw):
                return raw, "workflow.json"
            if not object_info:
                reason = "workflow.json is a UI graph and ComfyUI was unreachable"
            else:
                try:
                    converted = convert_ui_graph_to_api_prompt(raw, object_info)
                    if isinstance(converted, dict):
                        return converted, "workflow.json (converted against live /object_info)"
                    reason = "the UI-graph conversion returned no graph"
                except Exception as exc:
                    reason = f"the UI-graph conversion failed ({exc.__class__.__name__}: {exc})"

                # The usual cause is not a broken converter -- it is node classes this ComfyUI does
                # not have. Saying "stale artifact" when the real answer is "install these packs"
                # sends the reader to the wrong place entirely.
                missing = _missing_node_classes(raw, object_info)
                if missing:
                    shown = ", ".join(missing[:5])
                    more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
                    reason = (
                        f"the workflow needs {len(missing)} node class(es) this ComfyUI does not "
                        f"have: {shown}{more}"
                    )

    # Fallback: the previously compiled API graph. Only trustworthy if its loaders still carry
    # their inputs -- see _loaders_have_inputs.
    compiled_path = import_root / "prompt_api.json"
    if compiled_path.is_file():
        try:
            compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
        except Exception:
            compiled = None
        if isinstance(compiled, dict):
            if _loaders_have_inputs(compiled):
                return compiled, f"prompt_api.json (cached compile; {reason})"
            return None, f"prompt_api.json is stale -- its model loaders carry no inputs ({reason})"

    return None, f"no readable graph ({reason})"


def handle_resolve_missing_models_command(req: dict[str, Any]) -> dict[str, Any]:
    from workflow_library_commands import _resolve_import_root

    import_root = _resolve_import_root(req)
    if import_root is None or not import_root.is_dir():
        return {
            "type": "model_resolution_offers", "ok": False,
            "action": "resolve_missing_models",
            "error": "resolve_missing_models requires a valid import_root or profile_path",
        }

    api_url = str(
        req.get("comfy_api_url") or os.environ.get("COMFY_API_URL") or "http://127.0.0.1:8188"
    ).rstrip("/")

    # Short budget on purpose. The 120s default exists so a generation job can ride out a model
    # swap; a UI asking "what is missing?" must never block on that, and a refused connection for
    # six seconds means ComfyUI is down rather than busy.
    object_info: dict[str, Any] | None = None
    try:
        # Explicit None check, not `or`: a caller asking for a ZERO budget (try once, do not
        # retry) is falsy, and `or` would silently hand them the six-second default instead.
        requested_budget = req.get("object_info_budget_sec")
        budget = 6.0 if requested_budget is None else float(requested_budget)
        fetched = _ws()._comfy_object_info(api_url, budget_sec=budget)
        if isinstance(fetched, dict) and fetched:
            object_info = fetched
    except Exception:
        object_info = None

    graph, graph_source = _load_graph(import_root, object_info)
    if graph is None:
        return {
            "type": "model_resolution_offers", "ok": False,
            "action": "resolve_missing_models",
            "import_root": str(import_root),
            "object_info_available": bool(object_info),
            "graph_source": graph_source,
            "error": f"the workflow's model bindings could not be read: {graph_source}",
        }

    if object_info:
        installed = installed_from_object_info(object_info)
        catalog_source = "object_info"
    else:
        from comfy_bootstrap import default_comfy_root

        comfy_root = str(req.get("comfy_root") or default_comfy_root())
        installed = installed_from_disk_all(comfy_root)
        catalog_source = "disk"

    missing = missing_model_references(graph, installed)
    ambiguous = ambiguous_model_references(graph, installed)
    search_online = bool(req.get("search_online", True))

    offers = []
    seen: set[str] = set()
    for wanted in missing:
        if wanted in seen:
            continue
        seen.add(wanted)
        inference = infer_required_architecture(graph, wanted_model=wanted)
        offers.append(
            build_offer(
                wanted,
                graph=graph,
                installed=installed,
                search_online=search_online,
                inference=inference,
            ).to_dict()
        )

    return {
        "type": "model_resolution_offers", "ok": True,
        "action": "resolve_missing_models",
        "import_root": str(import_root),
        "graph_source": graph_source,
        "catalog_source": catalog_source,
        "catalog_size": len(installed),
        "object_info_available": bool(object_info),
        "searched_online": search_online,
        "missing_count": len(offers),
        "offers": offers,
        # Bare names that match installed models in more than one folder. The launch will resolve
        # them to *a* model; reporting them keeps "not reliably the intended one" visible.
        "ambiguous": ambiguous,
    }
