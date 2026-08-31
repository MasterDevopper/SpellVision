"""A catalog match must be earned by the CLASS NAME, and actioned only above a confidence floor.

Regression: `model_families` contributed +0.2 and could be the SOLE contributor, so any entry
declaring a family the workflow hinted at became a candidate for EVERY unknown class. Measured on
runtime/imported_workflows/basict2i-v23-json: 33 of 34 dependencies resolved to ComfyUI-TeaCache at
confidence 0.20, all with action="install", and `unresolved_classes` was empty -- a plan that
reported full coverage while resolving nothing. One click of "Retry Dependencies" ran
`cm-cli install ComfyUI-TeaCache` 33 times and fixed none of them.

Both halves are load-bearing: the evidence gate stops a family hint CREATING a candidate, and the
floor stops a single weak alias hit being actioned.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from node_dependency_resolver import _INSTALL_CONFIDENCE_FLOOR, _resolve_class_name  # noqa: E402
from workflow_scanner import WorkflowScanReport, WorkflowSource  # noqa: E402


def _report(hints: list[str]) -> WorkflowScanReport:
    return WorkflowScanReport(
        report_id="test",
        source=WorkflowSource(source_kind="test", display_name="test"),
        graph_format="comfy_ui_graph",
        node_count=0,
        nodes=[],
        inferred_model_family_hints=list(hints),
    )


# Shaped like the real ComfyUI-TeaCache entry, which declares five families.
GREEDY_ENTRY = {
    "package_name": "ComfyUI-TeaCache",
    "install_method": "manager",
    "repo_url": "https://example.invalid/teacache.git",
    "class_name_patterns": ["teacache"],
    "aliases": ["teacache"],
    "model_families": ["wan", "ltx", "hunyuan_video", "cogvideox", "flux"],
}


def test_family_hint_alone_never_creates_a_candidate():
    """The exact TeaCache bug: an unrelated class in a flux workflow must not resolve to it."""
    dep = _resolve_class_name("UltralyticsDetectorProvider", [GREEDY_ENTRY], _report(["flux"]))
    assert dep.action == "manual_review"
    assert dep.resolved_package is None
    assert dep.candidates == []


def test_family_hint_still_ranks_a_real_name_match():
    """A hint must keep working as a tie-breaker once the class name has already matched.

    Uses an entry whose only name signal is a single alias (0.35), so the hint's +0.2 is visible.
    A class matching pattern + package + alias saturates at the min(score, 1.0) clamp and could
    never show a difference.
    """
    entry = {
        "package_name": "ComfyUI-Widgets",
        "install_method": "git",
        "repo_url": "https://example.invalid/widgets.git",
        "class_name_patterns": [],
        "aliases": ["sampler"],
        "model_families": ["flux"],
    }
    with_hint = _resolve_class_name("FancySamplerNode", [entry], _report(["flux"]))
    without_hint = _resolve_class_name("FancySamplerNode", [entry], _report([]))
    assert with_hint.resolved_package == "ComfyUI-Widgets"
    assert with_hint.confidence > without_hint.confidence
    # And the hint is what carries this one over the floor.
    assert without_hint.action == "manual_review"
    assert with_hint.action == "install"


def test_weak_alias_match_is_offered_not_actioned():
    """A single alias hit (0.35) is below the floor -- suggest it, do not install it."""
    entry = {
        "package_name": "ComfyUI-Thing",
        "install_method": "git",
        "repo_url": "https://example.invalid/thing.git",
        "class_name_patterns": [],
        "aliases": ["xy"],
        "model_families": [],
    }
    dep = _resolve_class_name("SomeXyNode", [entry], _report([]))
    assert dep.candidates, "still surfaced as a candidate for review"
    assert dep.confidence < _INSTALL_CONFIDENCE_FLOOR
    assert dep.action == "manual_review"


def test_strong_pattern_match_is_actioned():
    """A pattern hit (0.7) clears the floor and should install."""
    entry = {
        "package_name": "ComfyUI-LTXVideo",
        "install_method": "git",
        "repo_url": "https://example.invalid/ltx.git",
        "class_name_patterns": ["ltxv"],
        "aliases": [],
        "model_families": ["ltx"],
    }
    dep = _resolve_class_name("LTXVPreprocess", [entry], _report(["ltx"]))
    assert dep.action == "install"
    assert dep.resolved_package == "ComfyUI-LTXVideo"
    assert dep.confidence >= _INSTALL_CONFIDENCE_FLOOR


def test_unmatched_class_is_honestly_unresolved():
    dep = _resolve_class_name("CompletelyUnrelatedNode", [GREEDY_ENTRY], _report(["wan", "ltx"]))
    assert dep.action == "manual_review"
    assert dep.confidence == 0.0
