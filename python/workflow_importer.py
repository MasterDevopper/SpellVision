from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from comfy_slot_mapper import build_profile_from_scan, save_profile
from model_dependency_resolver import apply_model_install_plan, build_model_install_plan
from node_dependency_resolver import apply_node_install_plan, build_node_install_plan
from workflow_scanner import load_workflow_source, save_scan_report, scan_workflow


@dataclass
class ImportedWorkflowArtifacts:
    import_root: str
    workflow_path: str
    profile_path: str
    scan_report_path: str
    dependency_plan_path: str | None = None
    dependency_apply_result_path: str | None = None


@dataclass
class WorkflowImportResult:
    ok: bool
    import_slug: str
    inferred_task_command: str
    inferred_media_type: str
    artifacts: ImportedWorkflowArtifacts
    capability_report: dict[str, Any] = field(default_factory=dict)
    supported_modes: list[str] = field(default_factory=list)
    classification_confidence: float = 0.0
    missing_custom_nodes: list[str] = field(default_factory=list)
    model_references: list[dict[str, Any]] = field(default_factory=list)
    dependency_plan: dict[str, Any] | None = None
    dependency_apply_result: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def import_workflow(
    source: str | Path | dict[str, Any],
    destination_root: str | Path,
    profile_name: str | None = None,
    *,
    comfy_root: str | Path | None = None,
    python_executable: str = "python",
    node_catalog: dict[str, Any] | str | Path | None = None,
    auto_apply_node_deps: bool = False,
    auto_apply_model_deps: bool = False,
    civitai_api_key: str | None = None,
    model_cache_root: str | None = None,
) -> WorkflowImportResult:
    workflow_source, payload = load_workflow_source(source)
    report = scan_workflow(payload, source_kind=workflow_source.source_kind)

    slug = _build_import_slug(profile_name or workflow_source.display_name or "imported-workflow")
    import_root = Path(destination_root) / slug
    import_root.mkdir(parents=True, exist_ok=True)

    workflow_path = import_root / "workflow.json"
    workflow_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    scan_path = import_root / "scan_report.json"
    save_scan_report(report, scan_path)

    profile = build_profile_from_scan(
        report=report,
        workflow_source_path=str(workflow_path),
        profile_name=profile_name,
        backend_kind="comfy_workflow",
    )
    profile_path = import_root / "profile.json"
    save_profile(profile, profile_path)

    dependency_plan_payload = None
    dependency_plan_path = None
    dependency_apply_payload = None
    dependency_apply_result_path = None
    warnings = [issue.message for issue in report.warnings] + profile.warnings
    errors = [issue.message for issue in report.errors]

    if comfy_root:
        node_plan = build_node_install_plan(
            report,
            comfy_root=comfy_root,
            node_catalog=node_catalog,
            python_executable=python_executable,
        )
        model_plan = build_model_install_plan(
            report,
            comfy_root=comfy_root,
            auto_materialize=auto_apply_model_deps,
            cache_root=model_cache_root,
            civitai_api_key=civitai_api_key,
        )

        dependency_plan_payload = {
            "node_plan": node_plan.to_dict(),
            "model_plan": model_plan.to_dict(),
        }
        dependency_plan_path = import_root / "dependency_plan.json"
        dependency_plan_path.write_text(json.dumps(dependency_plan_payload, indent=2), encoding="utf-8")

        if auto_apply_node_deps or auto_apply_model_deps:
            dependency_apply_payload = {}
            if auto_apply_node_deps:
                dependency_apply_payload["node_apply_result"] = apply_node_install_plan(
                    node_plan,
                    comfy_root=comfy_root,
                    python_executable=python_executable,
                ).to_dict()
            if auto_apply_model_deps:
                dependency_apply_payload["model_apply_result"] = apply_model_install_plan(model_plan).to_dict()

            dependency_apply_result_path = import_root / "dependency_apply_result.json"
            dependency_apply_result_path.write_text(json.dumps(dependency_apply_payload, indent=2), encoding="utf-8")

            for bucket in dependency_apply_payload.values():
                if not bucket.get("ok", False):
                    errors.extend(bucket.get("errors", []))

    capability_payload = asdict(report.capability_report) if report.capability_report else {}

    return WorkflowImportResult(
        ok=not errors,
        import_slug=slug,
        inferred_task_command=report.inferred_task_command,
        inferred_media_type=report.inferred_media_type,
        artifacts=ImportedWorkflowArtifacts(
            import_root=str(import_root),
            workflow_path=str(workflow_path),
            profile_path=str(profile_path),
            scan_report_path=str(scan_path),
            dependency_plan_path=str(dependency_plan_path) if dependency_plan_path else None,
            dependency_apply_result_path=str(dependency_apply_result_path) if dependency_apply_result_path else None,
        ),
        capability_report=capability_payload,
        supported_modes=list(capability_payload.get("supported_modes") or []),
        classification_confidence=float(capability_payload.get("confidence") or 0.0),
        missing_custom_nodes=report.missing_custom_nodes,
        model_references=[asdict(item) for item in report.model_references],
        dependency_plan=dependency_plan_payload,
        dependency_apply_result=dependency_apply_payload,
        warnings=warnings,
        errors=errors,
    )


def _build_import_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "imported-workflow"
