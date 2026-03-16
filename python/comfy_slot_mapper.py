from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from workflow_scanner import SlotCandidate, WorkflowScanReport


@dataclass
class SlotBinding:
    slot: str
    node_id: str
    input_name: str
    path: str
    confidence: float
    note: str | None = None


@dataclass
class WorkflowProfile:
    profile_name: str
    task_command: str
    media_type: str
    backend_kind: str
    workflow_source: str
    slot_bindings: dict[str, SlotBinding] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    model_family_hints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["slot_bindings"] = {
            key: asdict(binding) for key, binding in self.slot_bindings.items()
        }
        return payload


def build_profile_from_scan(
    report: WorkflowScanReport,
    workflow_source_path: str,
    profile_name: str | None = None,
    backend_kind: str = "comfy_workflow",
) -> WorkflowProfile:
    chosen: dict[str, SlotBinding] = {}

    grouped: dict[str, list[SlotCandidate]] = {}
    for candidate in report.slot_candidates:
        grouped.setdefault(candidate.slot, []).append(candidate)

    warnings: list[str] = []
    for slot, candidates in grouped.items():
        candidates = sorted(candidates, key=lambda item: (-item.confidence, item.node_id, item.input_name))
        best = candidates[0]
        chosen[slot] = SlotBinding(
            slot=slot,
            node_id=best.node_id,
            input_name=best.input_name,
            path=best.path,
            confidence=best.confidence,
            note=best.reason,
        )
        if len(candidates) > 1 and abs(candidates[0].confidence - candidates[1].confidence) < 0.03:
            warnings.append(f"Slot '{slot}' has multiple near-equal candidates; review binding before production use.")

    inferred_name = profile_name or _default_profile_name(report, workflow_source_path)
    tags = sorted(set([report.inferred_task_command, report.inferred_media_type, *report.inferred_model_family_hints]))

    return WorkflowProfile(
        profile_name=inferred_name,
        task_command=report.inferred_task_command,
        media_type=report.inferred_media_type,
        backend_kind=backend_kind,
        workflow_source=workflow_source_path,
        slot_bindings=chosen,
        tags=tags,
        model_family_hints=report.inferred_model_family_hints,
        warnings=warnings + [issue.message for issue in report.warnings],
        metadata={
            "graph_format": report.graph_format,
            "node_count": report.node_count,
            "missing_custom_nodes": report.missing_custom_nodes,
            "model_references": [asdict(ref) for ref in report.model_references],
            "scan_report_id": report.report_id,
        },
    )


def save_profile(profile: WorkflowProfile, path: str | Path) -> str:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    return str(out_path)


def _default_profile_name(report: WorkflowScanReport, workflow_source_path: str) -> str:
    base = Path(workflow_source_path).stem or "Imported Workflow"
    base = re.sub(r"[_\-]+", " ", base).strip()
    if report.inferred_task_command and report.inferred_task_command != "unknown":
        return f"{base} ({report.inferred_task_command.upper()})"
    return base or "Imported Workflow"
