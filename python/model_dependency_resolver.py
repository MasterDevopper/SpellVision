from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import os
import shutil

from model_sources import materialize_asset, parse_asset_reference
from workflow_scanner import ModelReference, WorkflowScanReport


MODEL_SUBDIR_MAP = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "vae": "vae",
    "controlnet": "controlnet",
    "clip": "clip",
    "unet": "unet",
    "repo_id": "diffusion_models",
}


@dataclass
class ModelDependency:
    kind: str
    source_value: str
    node_id: str
    input_name: str
    comfy_subdir: str
    resolved_source_kind: str | None = None
    destination_path: str | None = None
    install_action: str = "review"
    exists: bool = False
    notes: list[str] = field(default_factory=list)
    materialized: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelInstallPlan:
    comfy_models_root: str
    dependencies: list[ModelDependency] = field(default_factory=list)
    install_actions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Model roots ComfyUI is configured to use that could not be read, as {"path", "reason"}.
    # Non-empty means "already present" is UNDER-reporting: anything living on that root is about
    # to be listed as missing and offered as a download the user may already own. Reported rather
    # than inferred, because the failure otherwise looks exactly like an empty drive.
    unreadable_roots: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelApplyResult:
    ok: bool
    plan: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_extra_model_path_roots(comfy_root: Path) -> dict[str, list[Path]]:
    """Parse comfy_root/extra_model_paths.yaml into {model_type: [abs dirs]}.

    Tolerant by design: a missing file or any parse error yields an empty mapping
    (callers fall back to comfy_root/models, today's behavior) and never raises.
    """
    yaml_path = Path(comfy_root) / "extra_model_paths.yaml"
    roots: dict[str, list[Path]] = {}
    if not yaml_path.is_file():
        return roots
    try:
        import yaml  # PyYAML ships in the runtime venv (ComfyUI depends on it).

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return roots
    if not isinstance(data, dict):
        return roots

    for section in data.values():
        if not isinstance(section, dict):
            continue
        base = str(section.get("base_path") or "").strip()
        if not base:
            continue
        base_path = Path(base)
        for key, rel in section.items():
            if key == "base_path" or not isinstance(rel, str):
                continue
            # A subdir mapping may list multiple newline-separated relative paths.
            for piece in rel.splitlines():
                piece = piece.strip()
                if not piece:
                    continue
                roots.setdefault(str(key).strip().lower(), []).append(base_path / piece)
    return roots


def _build_model_search_context(
    comfy_root: Path,
) -> tuple[dict[str, list[Path]], Path, set[str], list[dict[str, str]]]:
    """Return (subdir_roots, models_root, all_basenames, unreadable_roots).

    subdir_roots maps a comfy model subdir (checkpoints/loras/vae/...) to the extra
    roots configured for it; all_basenames is the set of lowercased filenames found
    recursively under comfy_root/models and every extra_model_paths base/subdir, so
    a model is "present" if it exists anywhere ComfyUI is configured to look.

    The fourth value is the point of this signature. A configured root that cannot be READ is not
    the same as a root with nothing in it, and the two used to be indistinguishable: ``Path.is_dir``
    answers False for any OSError, and ``os.walk`` discards errors unless given an ``onerror``
    handler. So a root that was merely unavailable contributed nothing and said nothing.

    Observed on this machine: ``D:/AI_ASSETS/models`` -- which holds essentially every checkpoint
    here -- locked by BitLocker. The index dropped from thousands of files to 57, every model on
    that drive resolved as MISSING, and the install plan would have offered to download models the
    user already owns, at tens of gigabytes each, with nothing anywhere saying the drive was locked.
    Under-reporting presence is the dangerous direction: over-reporting fails loudly at load time,
    while this fails by quietly proposing an expensive wrong answer.
    """
    comfy_root = Path(comfy_root)
    models_root = comfy_root / "models"
    extra = _load_extra_model_path_roots(comfy_root)

    subdir_roots: dict[str, list[Path]] = {}
    walk_roots: set[Path] = set()

    def add_walk_root(candidate: Path) -> None:
        """Queue a root for indexing, resolved when possible and raw when not.

        ``Path.resolve`` RAISES on a BitLocker-locked drive rather than returning the path
        unchanged, and the old ``except Exception: pass`` around it dropped the root there -- before
        the walk, before any error handler, leaving nothing to report. Every checkpoint on this
        machine lives under ``D:/AI_ASSETS/models``; with D: locked, all seven of its configured
        roots vanished at this line and the index quietly fell to 57 files.

        Keeping the unresolved path means the failure surfaces where it can be described, at the
        scandir below, instead of becoming an absence.
        """
        try:
            walk_roots.add(candidate.resolve())
        except OSError:
            walk_roots.add(candidate)

    add_walk_root(models_root)
    for type_key, dirs in extra.items():
        for d in dirs:
            subdir_roots.setdefault(type_key, []).append(d)
            add_walk_root(d)

    all_basenames: set[str] = set()
    unreadable: list[dict[str, str]] = []
    seen_unreadable: set[str] = set()

    # NOT guarded by Path.is_dir(): that method answers False for any OSError, so a locked or
    # permission-denied root was skipped before os.scandir ever ran and never reported. Letting
    # scandir raise is what makes the difference between "empty" and "unreadable" observable.
    def note_unreadable(path: Any, error: BaseException) -> None:
        key = str(path)
        if key in seen_unreadable:
            return
        seen_unreadable.add(key)
        unreadable.append({"path": key, "reason": str(error) or error.__class__.__name__})

    for root in walk_roots:
        try:
            with os.scandir(root) as entries:
                next(iter(entries), None)
        except (FileNotFoundError, NotADirectoryError):
            # A configured root that simply is not there. Normal -- extra_model_paths lists roots
            # optimistically -- and nothing is being hidden by staying quiet.
            continue
        except OSError as exc:
            note_unreadable(root, exc)
            continue
        for _dirpath, _dirnames, files in os.walk(root, onerror=lambda exc: note_unreadable(
                getattr(exc, "filename", root), exc)):
            for name in files:
                all_basenames.add(name.lower())

    # A configured root that fails only on some of its subtrees still counts: the index is
    # incomplete, and an incomplete index is exactly what makes a present model look missing.
    return subdir_roots, models_root, all_basenames, unreadable


def _model_present(
    ref_value: str,
    comfy_subdir: str,
    subdir_roots: dict[str, list[Path]],
    models_root: Path,
    all_basenames: set[str],
) -> bool:
    norm = str(ref_value or "").replace("\\", "/").strip().lstrip("/")
    if not norm:
        return False
    basename = Path(norm).name

    # Precise: exact relative path (or basename) under a subdir-mapped root.
    roots = list(subdir_roots.get(comfy_subdir, []))
    roots.append(models_root / comfy_subdir)
    # A reference that names a folder must be found AT that path. The basename shortcut below is
    # for bare names only -- applying it to "flux/ae.safetensors" would accept "vae/ae.safetensors",
    # which is a different file, and the launch path would then bind that one.
    qualified = "/" in norm
    for root in roots:
        try:
            if (root / norm).is_file():
                return True
            if not qualified and (root / basename).is_file():
                return True
        except Exception:
            continue

    # Fallback: the file exists somewhere under a configured model root. Handles subfolder
    # references (ltx/foo.safetensors) and kind/subdir mismatches.
    #
    # ONLY for a reference that names no folder of its own. A reference like "flux/ae.safetensors"
    # is ASSERTING where the file lives, and the subfolder is precisely the disambiguator the
    # author chose -- honouring a match somewhere else marks a different file present, and
    # _sv_choose_comfy_choice's own basename fallback then binds and executes it. Generic names
    # make that likely rather than exotic: ae.safetensors, clip_l.safetensors, model.safetensors
    # and qwen_image_vae.safetensors all appear under several architectures.
    #
    # A folder-qualified reference that is not found where it says it lives is reported missing,
    # which is the honest answer and lets the resolution tiers offer a real choice.
    if "/" in norm:
        return False
    return basename.lower() in all_basenames


def build_model_install_plan(
    report: WorkflowScanReport,
    *,
    comfy_root: str | Path,
    auto_materialize: bool = False,
    cache_root: str | None = None,
    civitai_api_key: str | None = None,
    use_declarations: bool = True,
) -> ModelInstallPlan:
    """Resolve a workflow's model references, in order of how certain each answer is.

      0. already present under a configured model root (extra_model_paths-aware);
      1. the workflow declares an exact download URL for it (``properties.models``);
      2. the reference is itself a URL / Civitai id -- materialise it;
      3. anything else is reported for review. Never guessed at, never substituted.

    Tier 1 is the addition: a loader node can carry ``{name, url, directory}``, which is an exact
    URL and destination rather than a filename to go hunting for. Measured here: 7 of 80 workflows,
    20 declarations. Where it exists it is the only tier that cannot be wrong.
    """
    comfy_root = Path(comfy_root).resolve()
    models_root = comfy_root / "models"
    plan = ModelInstallPlan(comfy_models_root=str(models_root))

    subdir_roots, _models_root, all_basenames, unreadable_roots = _build_model_search_context(comfy_root)
    plan.unreadable_roots = list(unreadable_roots)
    for entry in unreadable_roots:
        plan.errors.append(
            f"model root {entry['path']} could not be read ({entry['reason']}); models stored "
            "there will be reported missing"
        )

    def present_checker(ref_value: str, comfy_subdir: str) -> bool:
        return _model_present(ref_value, comfy_subdir, subdir_roots, models_root, all_basenames)

    declarations: dict[str, Any] = {}
    if use_declarations:
        try:
            from workflow_model_declarations import declared_models

            declarations = declared_models(report.nodes)
        except Exception:
            declarations = {}

    for ref in report.model_references:
        dep = _build_model_dependency(
            ref,
            models_root=models_root,
            auto_materialize=auto_materialize,
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
            present_checker=present_checker,
            declarations=declarations,
        )
        plan.dependencies.append(dep)
        if dep.install_action != "already_present":
            plan.install_actions.append(
                {
                    "kind": dep.install_action,
                    "model_kind": dep.kind,
                    "source_value": dep.source_value,
                    "destination_path": dep.destination_path,
                    "node_id": dep.node_id,
                    "input_name": dep.input_name,
                    "materialized": dep.materialized,
                    "notes": dep.notes,
                }
            )

    return plan


def apply_model_install_plan(
    plan: ModelInstallPlan,
    *,
    copy_mode: str = "copy",
    cache_root: str | None = None,
    civitai_api_key: str | None = None,
) -> ModelApplyResult:
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for action in plan.install_actions:
        kind = action.get("kind")
        destination_path = str(action.get("destination_path") or "")
        materialized = action.get("materialized") or {}
        source_path = str(materialized.get("local_path") or materialized.get("value") or "")

        if kind == "already_present":
            results.append({"ok": True, "action": action, "message": "already present"})
            continue

        if kind == "review":
            results.append({"ok": False, "action": action, "message": "manual review required"})
            continue

        if kind == "download_declared":
            # The URL came from the workflow, so the download runs through the same hardened path as
            # every other fetch (scheme and size checks, disk headroom, atomic replace) rather than
            # a bare urlopen on user-supplied input.
            url = str(materialized.get("url") or "")
            if not url:
                msg = f"No declared URL for {destination_path}"
                errors.append(msg)
                results.append({"ok": False, "action": action, "message": msg})
                continue
            try:
                fetched = materialize_asset(
                    url,
                    asset_type=str(action.get("model_kind") or "model"),
                    cache_root=cache_root,
                    civitai_api_key=civitai_api_key,
                )
                source_path = str(fetched.local_path or fetched.value or "")
                kind = "copy_downloaded"
            except Exception as exc:
                msg = f"Could not download {url}: {exc}"
                errors.append(msg)
                results.append({"ok": False, "action": action, "message": msg})
                continue

        if kind in {"copy_local", "copy_downloaded"}:
            if not source_path or not os.path.exists(source_path):
                msg = f"Source asset not found for destination {destination_path}"
                errors.append(msg)
                results.append({"ok": False, "action": action, "message": msg})
                continue

            dest = Path(destination_path)
            dest.parent.mkdir(parents=True, exist_ok=True)

            try:
                if os.path.abspath(source_path) != os.path.abspath(destination_path):
                    if copy_mode == "move":
                        shutil.move(source_path, destination_path)
                    else:
                        shutil.copy2(source_path, destination_path)
                results.append({"ok": True, "action": action, "message": "materialized"})
            except Exception as exc:
                msg = str(exc)
                errors.append(msg)
                results.append({"ok": False, "action": action, "message": msg})
            continue

        results.append({"ok": False, "action": action, "message": f"Unhandled action kind: {kind}"})
        errors.append(f"Unhandled action kind: {kind}")

    return ModelApplyResult(
        ok=not errors,
        plan=plan.to_dict(),
        results=results,
        errors=errors,
    )


def _build_model_dependency(
    ref: ModelReference,
    *,
    models_root: Path,
    auto_materialize: bool,
    cache_root: str | None,
    civitai_api_key: str | None,
    present_checker=None,
    declarations: dict[str, Any] | None = None,
) -> ModelDependency:
    comfy_subdir = MODEL_SUBDIR_MAP.get(ref.kind, "other")
    declaration = None
    if declarations:
        from workflow_model_declarations import declaration_for

        declaration = declaration_for(declarations, ref.value)
        # The declaration names its own destination, which is more reliable than deriving one from
        # the node class -- a CLIPLoader can declare "text_encoders" while MODEL_SUBDIR_MAP says
        # "clip". _safe_directory has already rejected anything that is not a plain component.
        if declaration is not None and declaration.directory:
            comfy_subdir = declaration.directory
    target_dir = models_root / comfy_subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    # First: is the referenced model already present under ANY configured model
    # root (comfy_root/models or an extra_model_paths.yaml mapping)? This is the
    # model analogue of the node side's "actually installed" check.
    if present_checker is not None and present_checker(ref.value, comfy_subdir):
        return ModelDependency(
            kind=ref.kind,
            source_value=ref.value,
            node_id=ref.node_id,
            input_name=ref.input_name,
            comfy_subdir=comfy_subdir,
            resolved_source_kind=None,
            destination_path=None,
            install_action="already_present",
            exists=True,
            notes=["present under a configured model root (extra_model_paths-aware)"],
        )

    destination_path = None
    materialized_payload = None
    notes: list[str] = []
    install_action = "review"
    exists = False
    resolved_source_kind = None

    # Tier 1. An exact URL the workflow itself supplied beats parsing the reference: a bare
    # filename carries no source at all, and this one is not inferred from anything.
    if declaration is not None:
        return ModelDependency(
            kind=ref.kind,
            source_value=ref.value,
            node_id=ref.node_id,
            input_name=ref.input_name,
            comfy_subdir=comfy_subdir,
            resolved_source_kind="workflow_declared_url",
            destination_path=str(target_dir / Path(declaration.name).name),
            install_action="download_declared",
            exists=False,
            notes=[f"the workflow declares a download URL for this file: {declaration.url}"],
            materialized={
                "kind": "workflow_declared_url",
                "value": declaration.url,
                "url": declaration.url,
                "filename": declaration.name,
                "directory": declaration.directory,
            },
        )

    parsed = parse_asset_reference(ref.value, asset_type=ref.kind)
    resolved_source_kind = parsed.kind

    if parsed.kind == "model_name":
        # A filename with no source. Not an error and not a dead end -- it is what the later
        # resolution tiers (name search, an offered substitution) exist for. Say so, rather than
        # reporting a path that does not exist.
        #
        # There is no hash tier here despite an earlier version of this comment naming one: no
        # workflow in the library carries a hash (measured across 415), so there is nothing to look
        # one up by. Hashes are used where they exist -- model_sources verifies a download against
        # the provider's SHA256 -- but that verifies a file already chosen; it cannot choose one.
        notes.append("the workflow names this model but gives no source; needs a search or a chosen substitute")
        install_action = "review"
    elif parsed.kind in {"local_file", "local_dir"}:
        source_path = str(parsed.path or "")
        candidate_name = Path(source_path).name if source_path else Path(ref.value).name
        destination_path = str(target_dir / candidate_name) if candidate_name else None

        if source_path and os.path.exists(source_path):
            if destination_path and os.path.exists(destination_path):
                exists = True
                install_action = "already_present"
                notes.append("destination already exists")
            else:
                install_action = "copy_local"
                materialized_payload = {
                    "kind": parsed.kind,
                    "value": source_path,
                    "local_path": source_path,
                }
        else:
            notes.append("local source path does not exist")
    elif parsed.kind in {"direct_url", "civitai_download_url", "civitai_model_page", "civitai_model_version"}:
        try:
            materialized = materialize_asset(
                ref.value,
                asset_type=ref.kind,
                cache_root=cache_root,
                civitai_api_key=civitai_api_key,
                force_download=bool(auto_materialize),
            )
            candidate_name = Path(str(materialized.local_path or materialized.value or "")).name or (parsed.filename or f"{ref.kind}.bin")
            destination_path = str(target_dir / candidate_name)
            materialized_payload = {
                "kind": materialized.resolved_kind,
                "value": materialized.value,
                "local_path": materialized.local_path,
                "repo_id": materialized.repo_id,
                "metadata": materialized.metadata,
            }
            install_action = "copy_downloaded" if materialized.local_path else "review"
        except Exception as exc:
            notes.append(f"materialize failed: {exc}")
    elif parsed.kind == "hf_repo":
        notes.append("Hugging Face repo reference detected; install path depends on selected runtime")
        install_action = "review"
        materialized_payload = {
            "kind": parsed.kind,
            "value": parsed.repo_id,
            "repo_id": parsed.repo_id,
        }
    else:
        notes.append("unhandled source kind")
        install_action = "review"

    return ModelDependency(
        kind=ref.kind,
        source_value=ref.value,
        node_id=ref.node_id,
        input_name=ref.input_name,
        comfy_subdir=comfy_subdir,
        resolved_source_kind=resolved_source_kind,
        destination_path=destination_path,
        install_action=install_action,
        exists=exists,
        notes=notes,
        materialized=materialized_payload,
    )
