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


def build_model_install_plan(
    report: WorkflowScanReport,
    *,
    comfy_root: str | Path,
    auto_materialize: bool = False,
    cache_root: str | None = None,
    civitai_api_key: str | None = None,
) -> ModelInstallPlan:
    comfy_root = Path(comfy_root).resolve()
    models_root = comfy_root / "models"
    plan = ModelInstallPlan(comfy_models_root=str(models_root))

    for ref in report.model_references:
        dep = _build_model_dependency(
            ref,
            models_root=models_root,
            auto_materialize=auto_materialize,
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
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
) -> ModelDependency:
    comfy_subdir = MODEL_SUBDIR_MAP.get(ref.kind, "other")
    target_dir = models_root / comfy_subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    destination_path = None
    materialized_payload = None
    notes: list[str] = []
    install_action = "review"
    exists = False
    resolved_source_kind = None

    parsed = parse_asset_reference(ref.value, asset_type=ref.kind)
    resolved_source_kind = parsed.kind

    if parsed.kind in {"local_file", "local_dir"}:
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
