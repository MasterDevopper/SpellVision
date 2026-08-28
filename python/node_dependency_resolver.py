"""Which custom node packs a workflow needs, and installing them.

Builds a plan (``build_node_install_plan``) before touching anything, then applies it
(``apply_node_install_plan``) -- the plan is inspectable so the UI can show what will happen
instead of a progress bar over a surprise.

Licence is DISCLOSED, never a gate. ``is_auto_installable()`` is reserved for a future unattended
toggle: kjnodes, VHS, rgthree and easy-use all normalise to UNKNOWN, so gating installs on it would
block exactly the packs that matter.

Resolution order and the measured dead ends are recorded in ``workflow_pack_resolver`` -- a
workflow names its own packs through ``properties.cnr_id`` / ``aux_id``, which beats every
name-similarity heuristic tried (0 of 16).
"""
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
from node_pack_installer import install_node_pack
from workflow_pack_resolver import (
    PackResolution,
    WorkflowPackPlan,
    package_name_for,
    resolve_report_packs,
)
from workflow_scanner import WorkflowScanReport


# Minimum confidence before a catalog match is ACTIONED rather than merely offered.
# The weakest single name signal is an alias hit (0.35); a lone alias is a suggestion, not grounds
# to run an install. Two independent signals, or one strong pattern hit (0.7), clear this.
_INSTALL_CONFIDENCE_FLOOR = 0.5


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
    # Set when the resolution came from the workflow's own declared pack identity rather than from
    # a name match against the starter catalog. `install_ref` is the exact revision to install.
    source: str = "starter_catalog"
    pack_id: str | None = None
    install_ref: str | None = None
    ref_kind: str = "unknown"
    license: str | None = None

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
    pack_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager_present": self.manager_present,
            "manager_bootstrapped": self.manager_bootstrapped,
            "installed_packages": self.installed_packages,
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "install_actions": self.install_actions,
            "unresolved_classes": self.unresolved_classes,
            "logs": self.logs,
            "pack_plan": self.pack_plan,
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
    use_declared_packs: bool = True,
    pack_plan: WorkflowPackPlan | None = None,
    registry_offline: bool = False,
    **pack_kwargs: Any,
) -> NodeInstallPlan:
    """Resolve a scan report's missing node classes to installable packs.

    Two tiers, in order:

      1. **What the workflow declares.** ComfyUI stamps each node with the pack it came from
         (``properties.cnr_id`` / ``aux_id`` / ``ver``), so for most classes the file already names
         the pack *and the exact revision*. This is evidence, not a guess, and it carries the licence
         and repo for disclosure.
      2. **A name match against the starter catalog.** Only for classes with no declared identity.
         Kept behind a confidence floor because a name match is a guess -- see ``_resolve_class_name``.

    Pass ``pack_plan`` to supply a pre-computed tier-1 result (or, in tests, a deterministic one);
    ``use_declared_packs=False`` disables tier 1 entirely; ``registry_offline=True`` keeps tier 1 but
    makes no network calls, so aux_id packs still resolve and cnr_id-only packs report honestly that
    they could not be checked.
    """
    catalog = load_node_catalog(node_catalog)
    catalog_entries = list(catalog.get("packages", []))
    installed_snapshot = list_installed_nodes(comfy_root, python_executable=python_executable)
    installed_names = {name.lower() for name in installed_snapshot.get("names", [])}

    plan = NodeInstallPlan(
        manager_present=bool(installed_snapshot.get("manager_present")),
        installed_packages=sorted(installed_snapshot.get("names", [])),
        logs=[installed_snapshot.get("command_result", {})],
    )

    declared_by_class: dict[str, PackResolution] = {}
    if use_declared_packs:
        if pack_plan is None:
            try:
                pack_plan = resolve_report_packs(report, offline=registry_offline, **pack_kwargs)
            except Exception as exc:  # a Registry hiccup must not take the whole plan down
                pack_plan = None
                plan.logs.append({"stage": "declared_pack_resolution", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        if pack_plan is not None:
            plan.pack_plan = pack_plan.to_dict()
            for resolution in pack_plan.resolved():
                for class_name in resolution.class_names:
                    declared_by_class[class_name] = resolution

    seen_packages: set[str] = set()
    for class_name in sorted(set(report.missing_custom_nodes)):
        resolution = declared_by_class.get(class_name)
        if resolution is not None:
            dep = _dependency_from_declaration(class_name, resolution)
        else:
            dep = _resolve_class_name(class_name, catalog_entries, report)
        package_name_lower = (dep.resolved_package or "").lower()

        if package_name_lower and package_name_lower in installed_names:
            dep.installed = True
            dep.action = "already_installed"
            dep.reason = dep.reason or "matching package appears installed"
        elif dep.resolved_package and dep.install_method in {"manager", "git"}:
            dep.action = "install"
            # One action per PACK, not per class: a pack providing eight missing classes must be
            # installed once. Installing it eight times is the failure mode Retry Dependencies had.
            if package_name_lower not in seen_packages:
                seen_packages.add(package_name_lower)
                plan.install_actions.append(
                    {
                        "kind": "manager_install" if dep.install_method == "manager" else "git_clone",
                        "class_name": dep.class_name,
                        "class_names": sorted(resolution.class_names) if resolution else [dep.class_name],
                        "package_name": dep.resolved_package,
                        "pack_id": dep.pack_id,
                        "repo_url": dep.repo_url,
                        "install_ref": dep.install_ref,
                        "ref_kind": dep.ref_kind,
                        "license": dep.license,
                        "source": dep.source,
                        "reason": dep.reason,
                        "confidence": dep.confidence,
                        "requires_confirmation": True,
                    }
                )
        else:
            plan.unresolved_classes.append(class_name)

        plan.dependencies.append(dep)

    return plan


def _dependency_from_declaration(class_name: str, resolution: PackResolution) -> NodeDependency:
    """A dependency the workflow itself named. Confidence 1.0 -- this is a declaration, not a match."""
    package_name = package_name_for(resolution)
    return NodeDependency(
        class_name=class_name,
        candidates=[
            NodeCandidate(
                package_name=package_name,
                install_method="git",
                repo_url=resolution.repo_url,
                confidence=1.0,
                reason=resolution.reason,
            )
        ],
        resolved_package=package_name,
        install_method="git",
        repo_url=resolution.repo_url,
        reason=resolution.reason,
        confidence=1.0,
        source=resolution.source,
        pack_id=resolution.pack_id,
        install_ref=resolution.install_ref,
        ref_kind=resolution.ref_kind,
        license=resolution.license,
    )


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
        install_ref = str(action.get("install_ref") or "").strip() or None
        if not repo_url:
            errors.append(f"No repo_url available for class {action.get('class_name')}")
            continue
        # Archive install first: it needs no git (nothing ships git with the app), it pins the exact
        # revision the workflow declared, and it installs requirements under a torch constraints
        # file. clone_custom_node_repo stays as the fallback for a host the archive path refuses.
        try:
            outcome = install_node_pack(
                comfy_root,
                repo_url,
                package_name=package_name,
                ref=install_ref,
                python_executable=python_executable,
            ).to_dict()
        except ValueError as exc:
            outcome = clone_custom_node_repo(
                comfy_root,
                repo_url,
                package_name=package_name,
                python_executable=python_executable,
            ).to_dict()
            outcome.setdefault("message", None)
            outcome["fallback_reason"] = f"archive install unavailable: {exc}"
        results.append(outcome)
        if not outcome.get("ok"):
            errors.append(outcome.get("message") or f"Failed to install {package_name or repo_url}")

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

        # Everything above is derived from the CLASS NAME -- it is actual evidence that this entry
        # provides this class. A model-family hint is not: it describes the workflow, not the class.
        name_evidence = score > 0.0

        model_families = {str(item).lower() for item in entry.get("model_families", []) or []}
        if report_hints and model_families.intersection(report_hints):
            # A family hint may only RANK a candidate that name evidence already produced. Letting it
            # CREATE one made every unknown class in a flux/wan workflow resolve to whichever catalog
            # entry claimed the most families -- measured on basict2i-v23, 33 of 34 dependencies
            # resolved to ComfyUI-TeaCache at 0.20 with action="install" and unresolved_classes=[],
            # so one click of Retry Dependencies installed TeaCache 33 times and fixed nothing.
            if name_evidence:
                score += 0.2
                reasons.append("model family hint aligned")

        if name_evidence:
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

    # A confidence floor as well as the evidence gate above. An installable method is not on its own
    # a reason to install: a single weak alias hit should be offered for review, never actioned.
    # Below the floor the class is reported honestly as unresolved rather than mis-attributed.
    installable_method = best.install_method in {"manager", "git"}
    action = "install" if (installable_method and best.confidence >= _INSTALL_CONFIDENCE_FLOOR) else "manual_review"
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
