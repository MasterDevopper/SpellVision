"""What does it mean for a model family to be "supported", and which families actually are?

Six families (anima, flux, hunyuan_video, krea2, mochi, wan) were brought to a high standard by
hand, one at a time, and the pattern was never written down. The result is that a family can be
declared supported while silently missing a layer -- `lumina` and `pixart` have a manifest,
operating points, a sampler allowlist and a native builder, and no user can select either of them,
because the Qt asset scanner cannot detect their files.

This module makes "supported" a computable property so that gap is visible in a test rather than in
a bug report.

## Parity is routing-aware, not a checklist

An earlier version of this measurement scanned module source text for family names and reported
false gaps in both directions:

- `sdxl` was reported as missing a native graph builder and a family contract. It routes through
  **diffusers** (`NATIVE_IMAGE_FAMILIES` deliberately excludes it), so neither layer applies.
- `flux`, `krea2`, `anima`, `pixart` and `lumina` were reported as HAVING a family contract.
  `VIDEO_FAMILY_CONTRACTS` is video-only; the substring `flux` matched `flux3` and `krea2` matched
  a comment.

So a layer is only a gap when the family's **routing class** requires it. Expectations are declared
in ``EXPECTED_LAYERS`` and every reported gap names the routing that makes it a gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# --- layers -------------------------------------------------------------------------------

LAYER_MANIFEST = "manifest"          # component stack (unet/vae/text encoder) in COMPONENT_MANIFEST
LAYER_OPERATING_POINTS = "op_points"  # tuned steps/cfg/sampler defaults
LAYER_SAMPLERS = "samplers"          # per-family sampler allowlist
LAYER_BUILDER = "builder"            # native graph builder
LAYER_CONTRACT = "contract"          # video family contract + validation_status
LAYER_COCKPIT = "cockpit"            # the Qt asset scanner can detect the family's files

ALL_LAYERS = (
    LAYER_MANIFEST, LAYER_OPERATING_POINTS, LAYER_SAMPLERS,
    LAYER_BUILDER, LAYER_CONTRACT, LAYER_COCKPIT,
)

# --- routing classes ----------------------------------------------------------------------

ROUTING_NATIVE_IMAGE = "native_image"   # builds a ComfyUI graph from code (native_image_graphs)
ROUTING_NATIVE_VIDEO = "native_video"   # NativeFamilyPlugin in native_video_graphs
ROUTING_DIFFUSERS = "diffusers"         # loaded as a diffusers pipeline (SDXL / SD1.5 and lineages)
ROUTING_LINEAGE = "lineage"             # a finetune lineage that loads a parent architecture
ROUTING_UNROUTED = "unrouted"           # in the registry with no generation path at all

# What each routing class owes. A family is at parity when it has every layer its routing expects.
#
# Diffusers families need no manifest (a checkpoint is self-contained -- no separate VAE or text
# encoder to resolve) and no contract (contracts are the video-readiness mechanism). They still owe
# operating points, a sampler allowlist and cockpit detection, because those are what the user
# touches.
#
# Lineages (pony, illustrious) load their parent architecture's pipeline, so they owe only the
# layers that are lineage-specific: sampler/operating-point tuning and cockpit detection.
EXPECTED_LAYERS: dict[str, tuple[str, ...]] = {
    ROUTING_NATIVE_IMAGE: (LAYER_MANIFEST, LAYER_OPERATING_POINTS, LAYER_SAMPLERS,
                           LAYER_BUILDER, LAYER_COCKPIT),
    ROUTING_NATIVE_VIDEO: (LAYER_MANIFEST, LAYER_OPERATING_POINTS, LAYER_SAMPLERS,
                           LAYER_BUILDER, LAYER_CONTRACT, LAYER_COCKPIT),
    ROUTING_DIFFUSERS: (LAYER_OPERATING_POINTS, LAYER_SAMPLERS, LAYER_COCKPIT),
    ROUTING_LINEAGE: (LAYER_OPERATING_POINTS, LAYER_SAMPLERS, LAYER_COCKPIT),
    ROUTING_UNROUTED: (),
}

# Families that load a parent architecture rather than their own.
LINEAGE_FAMILIES = frozenset({"pony", "illustrious"})
# Families the worker loads through diffusers rather than a native ComfyUI graph.
DIFFUSERS_FAMILIES = frozenset({"sdxl", "stable_diffusion", "sd2", "sd3"})


@dataclass(frozen=True)
class FamilyCapability:
    family: str
    task_family: str
    routing: str
    present: frozenset[str]
    expected: tuple[str, ...]

    @property
    def gaps(self) -> tuple[str, ...]:
        """Expected layers this family does not have. Empty means at parity."""
        return tuple(layer for layer in self.expected if layer not in self.present)

    @property
    def at_parity(self) -> bool:
        """No missing layer AND a real generation path.

        An unrouted family expects nothing, so a bare `not self.gaps` would report it as at
        parity -- the most misleading possible answer for a family the app cannot generate with.
        """
        return not self.gaps and self.routing != ROUTING_UNROUTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "task_family": self.task_family,
            "routing": self.routing,
            "present": sorted(self.present),
            "expected": list(self.expected),
            "gaps": list(self.gaps),
            "at_parity": self.at_parity,
        }


def _cockpit_source() -> str:
    """The Qt asset scanner's source, or "" when it cannot be read.

    Text-scanned deliberately and with the fragility acknowledged: family detection lives in C++
    (`AssetCatalogScanner.cpp`) and there is no shared data file for Python to consult. That
    duplication is itself the finding -- a single declared family list, read by both sides, would
    make this function unnecessary. Returning "" degrades to "cannot tell", never to "absent".
    """
    path = Path(__file__).resolve().parents[1] / "qt_ui" / "assets" / "AssetCatalogScanner.cpp"
    try:
        return path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return ""


def _operating_point_key(family: str, aliases: dict[str, str], known: Iterable[str]) -> str | None:
    """Resolve a family key to its operating-point key, tolerating the naming drift.

    Operating points are keyed by task-suffixed names (`krea2_image`, `hunyuan_video`) and reached
    through an alias map. The map is hand-maintained and has already drifted: it carries `zimage`
    and `z-image` but not `z_image`, which is the actual registry key, so the family could not
    resolve its own tuned defaults by name.
    """
    known_set = set(known)
    for candidate in (aliases.get(family), family, f"{family}_image", f"{family}_video"):
        if candidate and candidate in known_set:
            return candidate
    return None


def family_capability_report() -> list[FamilyCapability]:
    """Every registry family with the layers it has and the layers its routing expects."""
    from model_registry import MODEL_FAMILIES

    # Imported WITHOUT a try/except on purpose. An earlier draft wrapped each of these and fell
    # back to an empty dict, and when the operating-points constant was named differently than
    # assumed, every family reported missing layers -- a confidently wrong report produced by the
    # guard that was supposed to make it robust. "This data source is missing" and "this family has
    # no entry" must not be the same answer, so a broken import fails loudly here instead.
    from family_operating_points import (  # noqa: F401  (name pinned by this import)
        FAMILY_OPERATING_POINTS,
        FAMILY_SAMPLER_ALLOWLISTS,
        _FAMILY_SAMPLING_ALIASES,
    )
    from model_dependency_manifest import COMPONENT_MANIFEST
    from native_image_graphs import NATIVE_IMAGE_FAMILIES
    from native_video_graphs import NATIVE_VIDEO_FAMILY_PLUGINS
    from video_family_contracts import VIDEO_FAMILY_CONTRACTS

    native_video = {p.family for p in NATIVE_VIDEO_FAMILY_PLUGINS}
    cockpit_src = _cockpit_source()
    op_keys = set(FAMILY_OPERATING_POINTS)

    report: list[FamilyCapability] = []
    for family, spec in MODEL_FAMILIES.items():
        if family == "unknown":
            continue

        if family in NATIVE_IMAGE_FAMILIES:
            routing = ROUTING_NATIVE_IMAGE
        elif family in native_video:
            routing = ROUTING_NATIVE_VIDEO
        elif family in LINEAGE_FAMILIES:
            routing = ROUTING_LINEAGE
        elif family in DIFFUSERS_FAMILIES:
            routing = ROUTING_DIFFUSERS
        else:
            routing = ROUTING_UNROUTED

        op_key = _operating_point_key(family, _FAMILY_SAMPLING_ALIASES, op_keys)
        sampler_key = _operating_point_key(family, _FAMILY_SAMPLING_ALIASES,
                                           set(FAMILY_SAMPLER_ALLOWLISTS))

        present: set[str] = set()
        if family in COMPONENT_MANIFEST:
            present.add(LAYER_MANIFEST)
        if op_key:
            present.add(LAYER_OPERATING_POINTS)
        if sampler_key:
            present.add(LAYER_SAMPLERS)
        if family in NATIVE_IMAGE_FAMILIES or family in native_video:
            present.add(LAYER_BUILDER)
        if family in VIDEO_FAMILY_CONTRACTS:
            present.add(LAYER_CONTRACT)
        # "" means unreadable -- do not claim absence from a file we could not open.
        if cockpit_src and family in cockpit_src:
            present.add(LAYER_COCKPIT)

        report.append(FamilyCapability(
            family=family,
            task_family=getattr(spec, "task_family", "unknown"),
            routing=routing,
            present=frozenset(present),
            expected=EXPECTED_LAYERS.get(routing, ()),
        ))

    report.sort(key=lambda c: (c.at_parity, c.family))
    return report


def families_with_gaps() -> dict[str, tuple[str, ...]]:
    """family -> its missing layers, for the families that are not at parity."""
    return {c.family: c.gaps for c in family_capability_report() if c.gaps}


def format_report(report: list[FamilyCapability] | None = None) -> str:
    """A scannable table. Used by the test's failure message and by dev scripts."""
    rows = report if report is not None else family_capability_report()
    width = max((len(c.family) for c in rows), default=10) + 2
    lines = [f"{'family':<{width}}{'routing':<15}{'gaps'}"]
    for capability in rows:
        if capability.gaps:
            gaps = ", ".join(capability.gaps)
        elif capability.routing == ROUTING_UNROUTED:
            # Never render this as "at parity". An unrouted family expects no layers, so an
            # empty gap list is the most misleading thing we could print about it.
            gaps = "NO GENERATION PATH"
        else:
            gaps = "-- at parity"
        lines.append(f"{capability.family:<{width}}{capability.routing:<15}{gaps}")
    return "\n".join(lines)
