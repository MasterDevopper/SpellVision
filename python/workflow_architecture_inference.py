"""What architecture does this workflow actually need, and what on this box could serve it?

This is tier 4 of the model-resolution ladder (plan Workstream A4): when a workflow names a
checkpoint that is not on disk, and no exact identity or name search resolved it, we can still
offer the user an **architecture-compatible substitute** -- but only if we can say, with a stated
reason, which architecture the graph requires.

Doc 45 measured the first half of that: architecture is recoverable from the graph for 53 of 55
workflows, against 10 by filename-family matching. This module is that inference, built for
production, plus the half Doc 45 did not measure -- turning an inferred architecture into an
actual ranked candidate list from the local catalog.

## Three states, never two

``infer_required_architecture`` returns RESOLVED, AMBIGUOUS, or UNKNOWN. Ambiguous is a real
answer with a real candidate set (``EmptySD3LatentImage`` genuinely does not distinguish SD3 from
Flux from Krea 2), and it must not be flattened into either a confident guess or a blank. The
repeated failure mode in this codebase is a component that reports success while being wrong; an
architecture we cannot pin has to be visibly unpinned so the picker asks instead of assuming.

## Signal order, and why it is that order

Measured against the 81-workflow library (50 of which name a missing checkpoint):

1. ``CLIPLoader.type`` and friends -- a structural fact about the graph, and the text encoder is
   architecture-specific. Strongest available.
2. An **unambiguous** marker node -- ``EmptyLTXVLatentVideo`` cannot appear in a non-LTX graph.
3. **The missing model's own filename.** Doc 45 skipped this because it was measuring graph
   inference *against* filename matching, but for substitution they compose: the graph says what
   the pipeline needs, the name says what the author had.
4. **Latent dimensions, last and weakest.** The width>=768 rule reads well but was measured
   *wrong on 2 of the 2 cases where it fired for SD1.5*: ``endercomic-v1`` and
   ``simple-t2i-generator`` both run an Illustrious (i.e. SDXL) checkpoint at width 512. Authors
   render SDXL at small sizes routinely. So width only breaks a tie the filename could not.

Every raw value is normalised through ``infer_model_family`` rather than compared literally --
a real graph carried ``CLIPLoader.type = "Wan-2.2 T2V"``, which matches no hardcoded table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from model_classification import classify_model
from model_registry import infer_model_family

# --- architecture axis -------------------------------------------------------------------
#
# Deliberately NOT ``pipeline_type``: that collapses every video family to "video", which would
# say an LTX checkpoint can stand in for a Wan one. Substitution needs the finer axis. Lineage
# finetunes fold up into the architecture they load -- that fold is the entire reason an
# Illustrious request has ~114 candidates instead of 0.
_LINEAGE_TO_ARCHITECTURE: dict[str, str] = {
    "pony": "sdxl",
    "illustrious": "sdxl",
    "noobai": "sdxl",
    "animagine": "sdxl",
    "sd15": "stable_diffusion",
    "sd1.5": "stable_diffusion",
}


def architecture_of_family(family: Optional[str]) -> Optional[str]:
    """Fold a registry family key up to its architecture. Unknown stays unknown."""
    key = str(family or "").strip().lower()
    if not key or key == "unknown":
        return None
    return _LINEAGE_TO_ARCHITECTURE.get(key, key)


# --- marker nodes ------------------------------------------------------------------------
# A node class that can only appear in a graph of one architecture. Kept separate from the
# ambiguous table so "unambiguous marker" is a property of the data, not of a code branch.
_UNAMBIGUOUS_MARKERS: dict[str, str] = {
    "EmptyHunyuanLatentVideo": "hunyuan_video",
    "EmptyLTXVLatentVideo": "ltx",
    "LTXVImgToVideoConditionOnly": "ltx",
    "EmptyMochiLatentVideo": "mochi",
    "WanImageToVideo": "wan",
    "WanVideoModelLoader": "wan",
    "FluxGuidance": "flux",
    "CLIPTextEncodeSDXL": "sdxl",
    "CLIPTextEncodeSDXLRefiner": "sdxl",
    "SDXLPromptStyler": "sdxl",
    "CLIPTextEncodeLumina2": "lumina",
}

# A marker that narrows to a SET but does not pin one member. The set is the honest answer.
_AMBIGUOUS_MARKERS: dict[str, tuple[str, ...]] = {
    "EmptySD3LatentImage": ("sd3", "flux", "krea2", "lumina"),
    "ModelSamplingSD3": ("sd3", "flux"),
    "ModelSamplingAuraFlow": ("lumina", "krea2"),
    "EmptyLatentImage": ("sdxl", "stable_diffusion"),
}

# Loader inputs that bind the checkpoint / diffusion model a substitution would replace.
MODEL_LOADER_INPUTS: dict[str, str] = {
    "CheckpointLoaderSimple": "ckpt_name",
    "CheckpointLoader": "ckpt_name",
    "ImageOnlyCheckpointLoader": "ckpt_name",
    "UNETLoader": "unet_name",
    "UnetLoaderGGUF": "unet_name",
}

# Nodes whose ``type`` widget names the text-encoder architecture.
_CLIP_LOADER_TYPE_INPUTS: dict[str, str] = {
    "CLIPLoader": "type",
    "DualCLIPLoader": "type",
    "TripleCLIPLoader": "type",
    "CLIPLoaderGGUF": "type",
}

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ArchitectureInference:
    """``state`` is the contract. Read ``architecture`` only when state is RESOLVED."""

    state: str                                  # resolved | ambiguous | unknown
    architecture: Optional[str] = None          # set iff state == RESOLVED
    candidates: tuple[str, ...] = ()            # the narrowed set when state == AMBIGUOUS
    confidence: float = 0.0
    reason: str = ""
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_resolved(self) -> bool:
        return self.state == RESOLVED


def _nodes(graph: Any) -> Iterable[dict]:
    if isinstance(graph, dict):
        source: Iterable[Any] = graph.values()
    elif isinstance(graph, list):
        source = graph
    else:
        return
    for node in source:
        if isinstance(node, dict):
            yield node


def _class_of(node: dict) -> str:
    return str(node.get("class_type") or node.get("type") or "")


def missing_model_references(graph: Any, installed: Iterable[str]) -> list[str]:
    """Checkpoint/unet names the graph binds that are not in the installed set.

    Compared case-insensitively with separators normalised, because ComfyUI hands back
    ``sdxl\\foo.safetensors`` on Windows while a workflow may carry ``sdxl/foo.safetensors``.
    """
    have = {_norm_name(n) for n in installed}
    out: list[str] = []
    for node in _nodes(graph):
        field_name = MODEL_LOADER_INPUTS.get(_class_of(node))
        if not field_name:
            continue
        value = (node.get("inputs") or {}).get(field_name)
        if isinstance(value, str) and value and _norm_name(value) not in have:
            out.append(value)
    return out


def _norm_name(name: str) -> str:
    return str(name or "").strip().lower().replace("\\", "/")


def _architecture_from_text(text: str) -> Optional[str]:
    """Normalise any raw graph string through the family taxonomy.

    Never compare a widget value literally: a live workflow carried
    ``CLIPLoader.type = "Wan-2.2 T2V"``, which no hardcoded table contains but which
    ``infer_model_family`` reduces to ``wan``.
    """
    family = infer_model_family(str(text or ""))
    return architecture_of_family(family)


def infer_required_architecture(graph: Any, wanted_model: Optional[str] = None) -> ArchitectureInference:
    """Infer the architecture the graph needs. See the module docstring for signal order."""
    classes = [_class_of(n) for n in _nodes(graph)]

    # 1. Text-encoder type -- structural and architecture-specific.
    for node in _nodes(graph):
        field_name = _CLIP_LOADER_TYPE_INPUTS.get(_class_of(node))
        if not field_name:
            continue
        raw = (node.get("inputs") or {}).get(field_name)
        if not isinstance(raw, str) or not raw.strip():
            continue
        arch = _architecture_from_text(raw)
        if arch:
            return ArchitectureInference(
                state=RESOLVED, architecture=arch, confidence=0.95,
                reason=f"{_class_of(node)}.{field_name}={raw!r}",
                signals=("clip_loader_type",),
            )

    # 2. A marker node that admits exactly one architecture.
    for cls in classes:
        arch = _UNAMBIGUOUS_MARKERS.get(cls)
        if arch:
            return ArchitectureInference(
                state=RESOLVED, architecture=arch, confidence=0.90,
                reason=f"node {cls} occurs only in {arch} graphs",
                signals=("marker_node",),
            )

    # Narrow with whatever ambiguous markers are present -- intersect, because two ambiguous
    # markers can pin an architecture neither pins alone.
    narrowed: Optional[set[str]] = None
    seen_markers: list[str] = []
    for cls in classes:
        options = _AMBIGUOUS_MARKERS.get(cls)
        if not options:
            continue
        seen_markers.append(cls)
        narrowed = set(options) if narrowed is None else (narrowed & set(options))
    if narrowed is not None and len(narrowed) == 1:
        only = next(iter(narrowed))
        return ArchitectureInference(
            state=RESOLVED, architecture=only, confidence=0.85,
            reason=f"markers {', '.join(sorted(seen_markers))} intersect to {only}",
            signals=("marker_intersection",),
        )

    # 3. The name of the model the author actually used.
    if wanted_model:
        arch = architecture_of_family(classify_model(str(wanted_model)).family)
        if arch and (narrowed is None or arch in narrowed):
            return ArchitectureInference(
                state=RESOLVED, architecture=arch, confidence=0.75,
                reason=f"requested file {wanted_model!r} names the {arch} architecture",
                signals=("wanted_model_name",),
            )

    # 4. Latent dimensions -- weakest, and only to break a tie the name could not.
    #    Measured 0-for-2 as a standalone SD1.5 detector, so it never resolves alone.
    if narrowed and narrowed <= {"sdxl", "stable_diffusion"}:
        for node in _nodes(graph):
            if _class_of(node) != "EmptyLatentImage":
                continue
            width = (node.get("inputs") or {}).get("width")
            if isinstance(width, (int, float)) and not isinstance(width, bool):
                arch = "sdxl" if width >= 768 else "stable_diffusion"
                if arch in narrowed:
                    return ArchitectureInference(
                        state=RESOLVED, architecture=arch, confidence=0.55,
                        reason=f"EmptyLatentImage width={int(width)} (weak: dimensions only, no name signal)",
                        signals=("latent_dimensions",),
                    )
                break

    if narrowed:
        return ArchitectureInference(
            state=AMBIGUOUS, candidates=tuple(sorted(narrowed)), confidence=0.40,
            reason=f"markers {', '.join(sorted(seen_markers))} narrow to {len(narrowed)} architectures, none pinned",
            signals=("marker_node",),
        )
    return ArchitectureInference(
        state=UNKNOWN, confidence=0.0,
        reason="no architecture signal in the graph or the requested filename",
    )


# --- candidate ranking -------------------------------------------------------------------


@dataclass(frozen=True)
class SubstitutionCandidate:
    name: str
    architecture: str
    lineage: Optional[str]        # pony / illustrious / noobai / animagine / base
    lineage_match: bool           # same lineage as the model that was asked for
    score: float
    reason: str


def _lineage_of(name: str) -> Optional[str]:
    result = classify_model(str(name or ""))
    if result.family in _LINEAGE_TO_ARCHITECTURE:
        return result.family
    return result.sub_family


def rank_substitution_candidates(
    architecture: str,
    wanted_model: str,
    installed: Iterable[str],
) -> list[SubstitutionCandidate]:
    """Local checkpoints that can stand in, best first.

    Lineage is a PREFERENCE, not a gate. An Illustrious request is legally served by any SDXL
    checkpoint -- refusing the non-Illustrious ones is what turns "114 candidates" back into
    "0". Same-lineage models simply sort first, and the caller shows the distinction so the
    user's choice is informed rather than made for them.
    """
    target = str(architecture or "").strip().lower()
    if not target:
        return []
    wanted_lineage = _lineage_of(wanted_model) if wanted_model else None

    out: list[SubstitutionCandidate] = []
    for name in installed:
        result = classify_model(str(name))
        arch = architecture_of_family(result.family)
        if arch != target:
            continue
        lineage = _lineage_of(name)
        matched = bool(wanted_lineage and lineage and lineage == wanted_lineage)
        score = 0.5 + (0.4 if matched else 0.0) + min(result.confidence, 1.0) * 0.1
        reason = (
            f"same {target} architecture, same {lineage} lineage" if matched
            else f"same {target} architecture"
        )
        out.append(SubstitutionCandidate(
            name=str(name), architecture=target, lineage=lineage,
            lineage_match=matched, score=round(score, 3), reason=reason,
        ))

    out.sort(key=lambda c: (-c.score, c.name.lower()))
    return out
