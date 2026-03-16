from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import re

from comfy_manager_bridge import (
    clone_custom_node_repo,
    ensure_manager_installed,
    install_registered_nodes,
    list_installed_nodes,
)
from workflow_scanner import WorkflowScanReport


@dataclass
class NodeCandidate:
    package_name: str
    install_method: str
    repo_url: str | None = None
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NodeDependency:
    class_name: str
    candidates: list[NodeCandidate] = field(default_factory=list)
    resolved_package: str | None = None
    install_method: str | None = None
    repo_url: str | None = None
    installed: bool = False
    action: str = "manual_review"
    reason: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [c.to_dict() for c in self.candidates]
        return payload


@dataclass
class NodeInstallPlan:
    manager_present: bool
    manager_bootstrapped: bool = False
    installed_packages: list[str] = field(default_factory=list)
    dependencies: list[NodeDependency] = field(default_factory=list)
    install_actions: list[dict[str, Any]] = field(default_factory=list)
    unresolved_classes: list[str] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager_present": self.manager_present,
            "manager_bootstrapped": self.manager_bootstrapped,
            "installed_packages": self.installed_packages,
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "install_actions": self.install_actions,
            "unresolved_classes": self.unresolved_classes,
            "logs": self.logs,
        }


@dataclass
class NodeApplyResult:
    ok: bool
    plan: dict[str, Any]
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_node_install_plan(
    report: WorkflowScanReport,
    *,
    comfy_root: str | Path,
    node_catalog: dict[str, Any] | str | Path | None = None,
    python_executable: str = "python",
) -> NodeInstallPlan:
    catalog = load_node_catalog(node_catalog)
    catalog_entries = list(catalog.get("packages", []))
    installed_snapshot = list_installed_nodes(comfy_root, python_executable=python_executable)
    installed_names = {name.lower() for name in installed_snapshot.get("names", [])}

    plan = NodeInstallPlan(
        manager_present=bool(installed_snapshot.get("manager_present")),
        installed_packages=sorted(installed_snapshot.get("names", [])),
        logs=[installed_snapshot.get("command_result", {})],
    )

    for class_name in sorted(set(report.missing_custom_nodes)):
        dep = _resolve_class_name(class_name, catalog_entries, report)
        package_name_lower = (dep.resolved_package or "").lower()

        if package_name_lower and package_name_lower in installed_names:
            dep.installed = True
            dep.action = "already_installed"
            dep.reason = dep.reason or "matching package appears installed"
        elif dep.resolved_package and dep.install_method in {"manager", "git"}:
            dep.action = "install"
            plan.install_actions.append(
                {
                    "kind": "manager_install" if dep.install_method == "manager" else "git_clone",
                    "class_name": dep.class_name,
                    "package_name": dep.resolved_package,
                    "repo_url": dep.repo_url,
                    "reason": dep.reason,
                    "confidence": dep.confidence,
                }
            )
        else:
            plan.unresolved_classes.append(class_name)

        plan.dependencies.append(dep)

    return plan


def apply_node_install_plan(
    plan: NodeInstallPlan,
    *,
    comfy_root: str | Path,
    python_executable: str = "python",
    bootstrap_manager: bool = True,
) -> NodeApplyResult:
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    if bootstrap_manager:
        _, manager_logs = ensure_manager_installed(comfy_root, python_executable=python_executable)
        if manager_logs:
            plan.manager_bootstrapped = True
            plan.logs.extend([log.to_dict() for log in manager_logs])

    manager_packages = [a["package_name"] for a in plan.install_actions if a.get("kind") == "manager_install" and a.get("package_name")]
    if manager_packages:
        install_results = install_registered_nodes(
            comfy_root,
            manager_packages,
            python_executable=python_executable,
        )
        results.extend([item.to_dict() for item in install_results])
        for item in install_results:
            if not item.ok:
                errors.append(item.message or f"Failed to install {item.package_name} via manager")

    for action in [a for a in plan.install_actions if a.get("kind") == "git_clone"]:
        repo_url = str(action.get("repo_url") or "").strip()
        package_name = str(action.get("package_name") or "").strip() or None
        if not repo_url:
            errors.append(f"No repo_url available for class {action.get('class_name')}")
            continue
        outcome = clone_custom_node_repo(
            comfy_root,
            repo_url,
            package_name=package_name,
            python_executable=python_executable,
        )
        results.append(outcome.to_dict())
        if not outcome.ok:
            errors.append(outcome.message or f"Failed to install {package_name or repo_url} via git")

    return NodeApplyResult(
        ok=not errors,
        plan=plan.to_dict(),
        results=results,
        errors=errors,
    )


def load_node_catalog(node_catalog: dict[str, Any] | str | Path | None) -> dict[str, Any]:
    if isinstance(node_catalog, dict):
        return node_catalog

    if node_catalog:
        path = Path(node_catalog)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

    default_path = Path(__file__).resolve().parent / "starter_node_catalog.json"
    if default_path.exists():
        return json.loads(default_path.read_text(encoding="utf-8"))

    return {"packages": []}


def _resolve_class_name(
    class_name: str,
    catalog_entries: list[dict[str, Any]],
    report: WorkflowScanReport,
) -> NodeDependency:
    candidates: list[NodeCandidate] = []
    normalized = class_name.strip().lower()
    report_hints = {hint.lower() for hint in (report.inferred_model_family_hints or [])}

    for entry in catalog_entries:
        score = 0.0
        reasons: list[str] = []

        package_name = str(entry.get("package_name") or "").strip()
        install_method = str(entry.get("install_method") or "manual").strip().lower()
        repo_url = str(entry.get("repo_url") or "").strip() or None

        if not package_name:
            continue

        for pattern in entry.get("class_name_patterns", []) or []:
            pattern_norm = str(pattern).strip().lower()
            if pattern_norm and pattern_norm in normalized:
                score += 0.7
                reasons.append(f"class pattern '{pattern}' matched")

        package_norm = package_name.lower()
        if package_norm and package_norm.replace("comfyui-", "") in normalized:
            score += 0.45
            reasons.append("package name resembles class")

        aliases = [str(alias).lower() for alias in entry.get("aliases", []) or []]
        for alias in aliases:
            if alias and alias in normalized:
                score += 0.35
                reasons.append(f"alias '{alias}' matched")

        model_families = {str(item).lower() for item in entry.get("model_families", []) or []}
        if report_hints and model_families.intersection(report_hints):
            score += 0.2
            reasons.append("model family hint aligned")

        if score > 0:
            candidates.append(
                NodeCandidate(
                    package_name=package_name,
                    install_method=install_method,
                    repo_url=repo_url,
                    confidence=min(score, 1.0),
                    reason="; ".join(reasons),
                )
            )

    candidates.sort(key=lambda item: (-item.confidence, item.package_name.lower()))
    best = candidates[0] if candidates else None

    if best is None:
        return NodeDependency(
            class_name=class_name,
            candidates=[],
            action="manual_review",
            reason="No catalog match for custom node class",
            confidence=0.0,
        )

    action = "install" if best.install_method in {"manager", "git"} else "manual_review"
    return NodeDependency(
        class_name=class_name,
        candidates=candidates,
        resolved_package=best.package_name,
        install_method=best.install_method,
        repo_url=best.repo_url,
        action=action,
        reason=best.reason,
        confidence=best.confidence,
    )
