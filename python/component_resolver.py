"""Component Auto-Population engine — the generic, family-agnostic resolver (Doc 19 §6, Part 2).

Given a primary model + the manifest (`model_dependency_manifest`) + the on-disk ComfyUI choices,
produce a completed component stack with a confidence tier per slot:

    T1 (unambiguous)  -> silent auto-fill        TIER_UNAMBIGUOUS
    T2 (preferred)    -> best-pick, overridable  TIER_PREFERRED
    T3 (missing)      -> download hook           TIER_MISSING
    omit              -> optional, correctly absent (valid) / not-applicable for the task

It composes the four inputs Doc 19 §6.1 names: `classify_model` (family + confidence),
`video_family_contracts.required_components` (the slot floor — guaranteed non-empty even for a
never-seen checkpoint, A4), the manifest (slot -> resolution rules), and the on-disk diff. It
reuses `model_dependency_resolver.build_model_install_plan` ONLY as the T3 download hook (it does
not reimplement fetching).

Hard constraint (grep-checkable): this module contains ZERO family-specific branches — no
`if family == "wan"`, no family names in the control flow. All family knowledge lives in the
manifest DATA. Adding a family is a manifest row.

The per-slot resolution reproduces the worker-side resolvers exactly (`_sv_core_wan_vae_name`,
`_sv_core_wan_clip_vision_name`): explicit-wins -> version-preferred order -> generic valid
predicate -> missing/omit. The equivalence gate asserts byte-identical output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from model_dependency_manifest import family_manifest

# Tier constants (Doc 19 §6.2).
TIER_UNAMBIGUOUS = "T1"
TIER_PREFERRED = "T2"
TIER_MISSING = "T3"
TIER_OMIT = "omit"
TIER_PROVIDED = "provided"   # a contract slot with no manifest rule (user-supplied model), the floor


# --- generic predicate + variant interpreters (drive on manifest DATA, no family knowledge) ----

def matches_predicate(name_lower: str, pred: Optional[dict[str, Any]]) -> bool:
    """A choice satisfies a valid_predicate: {all_of:[tok...]} and/or {any_of:[sub-pred...]}."""
    if not pred:
        return True
    all_of = pred.get("all_of")
    if all_of is not None and not all(tok in name_lower for tok in all_of):
        return False
    any_of = pred.get("any_of")
    if any_of is not None and not any(matches_predicate(name_lower, sub) for sub in any_of):
        return False
    return True


def detect_variant(probe_text: str, detection: Optional[dict[str, Any]]) -> Optional[str]:
    """First-match variant from an ordered (variant, any_tokens) list; else the declared default."""
    if not detection:
        return None
    h = str(probe_text or "").replace("\\", "/").lower()
    for rule in detection.get("order", []):
        if any(tok in h for tok in rule.get("any_tokens", [])):
            return rule["variant"]
    return detection.get("default", "")


@dataclass
class ResolvedSlot:
    component: str
    tier: str
    value: Optional[str]                 # chosen filename, or None (missing / omitted / provided)
    required: bool
    valid_options: list[str] = field(default_factory=list)   # on-disk choices for the override menu
    variant: Optional[str] = None
    download_hint: Optional[dict[str, Any]] = None            # T3 only (feeds build_model_install_plan)
    note: str = ""


@dataclass
class ResolvedStack:
    family: str
    confidence: float
    task: Optional[str]
    slots: list[ResolvedSlot]

    def slot(self, component: str) -> Optional[ResolvedSlot]:
        for s in self.slots:
            if s.component == component:
                return s
        return None

    def value(self, component: str) -> Optional[str]:
        s = self.slot(component)
        return s.value if s else None

    def missing_required(self) -> list[ResolvedSlot]:
        return [s for s in self.slots if s.required and s.tier == TIER_MISSING]

    def is_complete(self) -> bool:
        return not self.missing_required()


def _first_explicit(spec: dict[str, Any], stack: dict[str, Any], req: dict[str, Any]) -> str:
    """Explicit value for a slot, honoring explicit_sources order (matches which dict each resolver reads)."""
    sources = spec.get("explicit_sources", ["stack", "req"])
    src_map = {"stack": stack, "req": req}
    for src in sources:
        d = src_map.get(src) or {}
        for key in spec.get("explicit_keys", []):
            val = str(d.get(key) or "").strip()
            if val:
                return val
    return ""


def _slot_required(spec: dict[str, Any], variant: Optional[str], task: Optional[str]) -> bool:
    if spec.get("required"):
        return True
    rf = spec.get("required_for")
    if isinstance(rf, dict):
        if rf.get("variant") is not None and rf["variant"] != variant:
            return False
        if rf.get("task") is not None and rf["task"] != task:
            return False
        return True
    return False


def resolve_slot(
    component: str,
    spec: dict[str, Any],
    *,
    primary_path: str,
    stack: dict[str, Any],
    req: dict[str, Any],
    task: Optional[str],
    family: str,
    choices_for: Callable[[str, str], list[str]],
) -> ResolvedSlot:
    """Resolve ONE slot generically, reproducing the worker resolver's precedence."""
    # Task gate (e.g. clip_vision -> i2v only).
    applies = spec.get("applies_to_tasks")
    if applies and task and task not in applies:
        return ResolvedSlot(component, TIER_OMIT, None, required=False, note="not applicable for task")

    # The user-selected primary checkpoint is the INPUT, not a companion resolved from ComfyUI
    # choices -- it is present iff a primary_path was given (an all-in-one SDXL blob, say).
    if spec.get("is_primary"):
        present = bool(str(primary_path or "").strip())
        return ResolvedSlot(
            component,
            TIER_PROVIDED if present else TIER_MISSING,
            Path(primary_path).name if present else None,
            required=bool(spec.get("required")),
            note="user-selected primary",
        )

    comfy_class = spec.get("comfy_class")
    comfy_input = spec.get("comfy_input")
    choices = choices_for(comfy_class, comfy_input) if comfy_class and comfy_input else []
    by_lower = {str(c).strip().lower(): str(c).strip() for c in choices}

    pred = spec.get("valid_predicate")
    valid = [c for c in choices if matches_predicate(str(c).lower(), pred)] if pred else list(choices)

    # Variant probe (matches the resolver: model path joined with the family string).
    variant = None
    if spec.get("variant_detection"):
        variant = detect_variant(f"{primary_path} {family}", spec["variant_detection"])

    required = _slot_required(spec, variant, task)

    # 1. explicit-wins.
    explicit = _first_explicit(spec, stack, req)
    if explicit:
        name = Path(explicit).name.lower()
        if name in by_lower:
            return ResolvedSlot(component, TIER_UNAMBIGUOUS, by_lower[name], required=required,
                                valid_options=valid, variant=variant, note="explicit")

    # 2. version-preferred order.
    prefs: list[str] = []
    pbv = spec.get("preferred_by_variant")
    if pbv:
        prefs = pbv.get(variant) or pbv.get(spec.get("variant_detection", {}).get("default", ""), [])
    elif spec.get("preferred"):
        prefs = spec["preferred"]
    for pref in prefs:
        found = by_lower.get(str(pref).lower())
        if found:
            tier = TIER_PREFERRED if len(valid) > 1 else TIER_UNAMBIGUOUS
            return ResolvedSlot(component, tier, found, required=required, valid_options=valid, variant=variant)

    # 3. generic valid-predicate fallback (first on-disk choice satisfying the predicate).
    if valid:
        tier = TIER_PREFERRED if len(valid) > 1 else TIER_UNAMBIGUOUS
        return ResolvedSlot(component, tier, valid[0], required=required, valid_options=valid, variant=variant)

    # 4. nothing valid on disk.
    if not required and spec.get("omit_if_absent"):
        return ResolvedSlot(component, TIER_OMIT, None, required=False, variant=variant, note="optional, absent")
    # T3 missing -> download hint (candidate for build_model_install_plan; NOT fetched here).
    hint = {"component": component, "family": family, "comfy_subdir": comfy_class, "preferred": prefs or None}
    return ResolvedSlot(component, TIER_MISSING, None, required=required, variant=variant,
                        download_hint=hint, note="no valid option on disk")


def resolve_stack(
    primary_path: str,
    *,
    choices_for: Callable[[str, str], list[str]],
    family: Optional[str] = None,
    requested_family: Optional[str] = None,
    stack: Optional[dict[str, Any]] = None,
    req: Optional[dict[str, Any]] = None,
    task: Optional[str] = None,
    contract_required: Optional[tuple[str, ...]] = None,
    confidence: Optional[float] = None,
) -> ResolvedStack:
    """Resolve the complete component stack for a primary model.

    `choices_for(comfy_class, comfy_input) -> [filenames]` supplies the on-disk ComfyUI choices
    (wired to `_comfy_input_choices(object_info, ...)` in production / the gate). `contract_required`
    is the family's `required_components` (the A4 floor); a slot with no manifest rule appears as
    TIER_PROVIDED so the output is guaranteed non-empty for a never-seen checkpoint.
    """
    stack = dict(stack or {})
    req = dict(req or {})

    # Family + confidence via the classifier (single source of truth), unless the caller pins it.
    if not family:
        try:
            from model_classification import classify_model
            cls = classify_model(primary_path, requested_family=requested_family)
            family = cls.family
            if confidence is None:
                confidence = cls.confidence
        except Exception:
            family = requested_family or "unknown"
    if confidence is None:
        confidence = 1.0

    manifest = family_manifest(family) or {}
    manifest_slots: dict[str, Any] = manifest.get("slots", {})

    resolved: list[ResolvedSlot] = []
    seen: set[str] = set()

    # Manifest-ruled slots (the auto-populated ones).
    for component, spec in manifest_slots.items():
        resolved.append(resolve_slot(
            component, spec, primary_path=primary_path, stack=stack, req=req,
            task=task, family=family, choices_for=choices_for,
        ))
        seen.add(component)

    # Contract floor (A4): every required contract slot must appear, even with no manifest rule.
    for component in (contract_required or ()):  # order preserved
        if component in seen:
            continue
        resolved.append(ResolvedSlot(component, TIER_PROVIDED, None, required=True,
                                     note="contract slot, no manifest rule (user-provided / floor)"))
        seen.add(component)

    return ResolvedStack(family=family, confidence=float(confidence), task=task, slots=resolved)
