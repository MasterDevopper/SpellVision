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
# encoder to resolve) and no contract (contracts are the video-readiness mechanism).
#
# They also owe NO OPERATING POINTS, which is not an omission. Measured 2026-08-28 while trying to
# choose values for an sdxl row: nothing on the diffusers path reads FAMILY_OPERATING_POINTS.
# ``image_runners`` passes ``req["steps"]`` and ``req["cfg"]`` straight into the pipeline and never
# imports the table; ``worker_service`` consults it only for VIDEO family status payloads. So an
# sdxl row would be inert -- it would sit in the table looking authoritative and change nothing,
# which is precisely the "looks correct while being wrong" shape this whole audit is about.
#
# What they DO owe is a sampler allowlist, and that one genuinely works: rendering the same SDXL
# prompt and seed through dpmpp_2m/karras and euler/normal produced images differing by a mean
# absolute 30.6 per channel, so ``apply_sampler_and_scheduler`` is really applying the choice.
# Their effective steps/cfg defaults are the cockpit's (28 / 7.0), which is the standard SDXL
# baseline and renders well.
#
# The alternative -- wiring the diffusers path to the table so per-family steps/cfg defaults become
# real -- is a deliberate product change, not a gap fix: it would alter generation defaults for the
# highest-volume families on this box (112 sdxl checkpoints) and each family's values would need
# their own render validation first. Left undone on purpose.
#
# Lineages (pony, illustrious) load their parent architecture's pipeline through the same runner,
# so exactly the same reasoning applies to them.
EXPECTED_LAYERS: dict[str, tuple[str, ...]] = {
    ROUTING_NATIVE_IMAGE: (LAYER_MANIFEST, LAYER_OPERATING_POINTS, LAYER_SAMPLERS,
                           LAYER_BUILDER, LAYER_COCKPIT),
    ROUTING_NATIVE_VIDEO: (LAYER_MANIFEST, LAYER_OPERATING_POINTS, LAYER_SAMPLERS,
                           LAYER_BUILDER, LAYER_CONTRACT, LAYER_COCKPIT),
    ROUTING_DIFFUSERS: (LAYER_SAMPLERS, LAYER_COCKPIT),
    ROUTING_LINEAGE: (LAYER_SAMPLERS, LAYER_COCKPIT),
    ROUTING_UNROUTED: (),
}

# Families whose steps/cfg live in a shipped graph template rather than in a tuning table, and for
# which a cockpit value is deliberately ignored. LTX's distilled two-stage route drives its own
# sigmas via ManualSigmas and pins the guiders at cfg 1 -- the builder warns and overrides rather
# than honouring a passed cfg -- so an operating-point row would advertise control that does not
# exist. Two existing tests assert this emptiness on purpose
# (test_family_operating_points, test_wan_dual_noise_builder), and an earlier pass of this sweep
# "fixed" it by adding a row and broke both. A template-driven family still owes a SAMPLER
# allowlist, because the sampler genuinely is overridable.
TEMPLATE_DRIVEN_FAMILIES = frozenset({"ltx"})

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
    """The body of ``humanImageFamily`` in the Qt asset scanner, or "" when unreadable.

    Scoped to that ONE function on purpose. A first version scanned the whole 600-line file for the
    family name and reported `lumina` and `pixart` as undetectable — which was wrong twice over.
    Detection is not done in C++ at all (``scanImageModelCatalog`` overrides the local guess with
    ``model_classification.classify_model``), and the names did appear elsewhere in the file. The
    real thing C++ owns per family is the **display label**: an unmapped family falls through to
    the generic "Image", so a Lumina checkpoint reads the same as an unclassified one.

    Still text-scanned, and the duplication is itself the finding — one declared family list read
    by both sides would remove the need. Returning "" degrades to "cannot tell", never "absent".
    """
    path = Path(__file__).resolve().parents[1] / "qt_ui" / "assets" / "AssetCatalogScanner.cpp"
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # BOTH display functions. The scanner splits them by task -- humanImageFamily has no wan/ltx
    # entry and is not supposed to -- so checking a video family against the image function
    # reported four correctly-supported families as broken. Scoping to one function fixed one
    # error and introduced another; the fix is to scope to the right function per task.
    bodies: list[str] = []
    for signature in ("QString humanImageFamily(", "QString humanVideoFamily("):
        start = source.find(signature)
        if start < 0:
            continue
        end = source.find("\n}", start)
        bodies.append(source[start:end if end > start else len(source)])
    return "\n".join(bodies).lower()


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

        expected = EXPECTED_LAYERS.get(routing, ())
        if family in TEMPLATE_DRIVEN_FAMILIES:
            expected = tuple(l for l in expected if l != LAYER_OPERATING_POINTS)

        report.append(FamilyCapability(
            family=family,
            task_family=getattr(spec, "task_family", "unknown"),
            routing=routing,
            present=frozenset(present),
            expected=expected,
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
