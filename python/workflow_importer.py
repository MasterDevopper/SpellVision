from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from comfy_slot_mapper import build_profile_from_scan, save_profile
from workflow_scanner import WorkflowScanReport, load_workflow_source, save_scan_report, scan_workflow


@dataclass
class ImportedWorkflowArtifacts:
    import_root: str
    workflow_path: str
    profile_path: str
    scan_report_path: str


@dataclass
class WorkflowImportResult:
    ok: bool
    import_slug: str
    inferred_task_command: str
    inferred_media_type: str
    artifacts: ImportedWorkflowArtifacts
    missing_custom_nodes: list[str] = field(default_factory=list)
    model_references: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def import_workflow(
    source: str | Path | dict[str, Any],
    destination_root: str | Path,
    profile_name: str | None = None,
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

    warnings = [issue.message for issue in report.warnings] + profile.warnings
    errors = [issue.message for issue in report.errors]

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
        ),
        missing_custom_nodes=report.missing_custom_nodes,
        model_references=[asdict(item) for item in report.model_references],
        warnings=warnings,
        errors=errors,
    )


def _build_import_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "imported-workflow"
