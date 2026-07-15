"""Unit tests for node_registry_resolver — pure, no network.

The Registry HTTP layer is injected via the `getter` seam, so these run in-container where
api.comfy.org is blocked. The load-bearing test is the auto-install gate: it must reject
UNKNOWN and every copyleft license, because the future auto-install toggle consults ONLY this
predicate before bypassing the user's confirmation click.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from node_registry_resolver import (  # noqa: E402
    ALLOWLIST,
    UNKNOWN_LICENSE,
    _normalize_license,
    is_auto_installable,
    resolve_missing_nodes,
)


# ---------------------------------------------------------------------------
# is_auto_installable — the safety gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lic", sorted(ALLOWLIST))
def test_allowlisted_licenses_are_auto_installable(lic):
    assert is_auto_installable(lic) is True


@pytest.mark.parametrize("lic", [
    None, "", UNKNOWN_LICENSE, "UNKNOWN",
    "GPL-3.0", "GPLv3", "gpl", "AGPL-3.0", "LGPL-3.0", "MPL-2.0",
    "CC-BY-NC-4.0", "CC-BY-SA-4.0",
    "LICENSE", "see repository", "Custom", "proprietary",
])
def test_unknown_and_copyleft_are_never_auto_installable(lic):
    assert is_auto_installable(lic) is False


def test_unknown_is_a_distinct_state_not_blank():
    # Empty / absent / filename -> UNKNOWN (surfaced), never "".
    assert _normalize_license("") == UNKNOWN_LICENSE
    assert _normalize_license(None) == UNKNOWN_LICENSE
    assert _normalize_license("LICENSE") == UNKNOWN_LICENSE
    assert _normalize_license({"file": "LICENSE"}) == UNKNOWN_LICENSE
    assert UNKNOWN_LICENSE not in ALLOWLIST  # so UNKNOWN can never be auto-installable


def test_license_normalization_variants():
    assert _normalize_license("MIT License") == "MIT"
    assert _normalize_license("Apache License 2.0") == "Apache-2.0"
    assert _normalize_license("bsd 3-clause") == "BSD-3-Clause"
    assert _normalize_license({"spdx": "MIT"}) == "MIT"
    assert _normalize_license("GPLv3") == "GPL-3.0"
    # An id we don't recognize is preserved (and thus not auto-installable).
    assert _normalize_license("WTFPL") == "WTFPL"
    assert is_auto_installable("WTFPL") is False


# ---------------------------------------------------------------------------
# resolve_missing_nodes — PURE lookup over a prebuilt class->pack index
# ---------------------------------------------------------------------------

def _index(classes):
    return {"classes": classes}


def test_resolved_entry_is_first_class_with_license_and_auto_flag():
    idx = _index({
        "IPAdapterAdvanced": {
            "pack_id": "comfyui_ipadapter_plus", "version": "2.0.0",
            "repo_url": "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
            "license": "GPL-3.0 license", "py_deps": ["insightface"],
        },
        "ImageResize+": {
            "pack_id": "comfyui_essentials", "version": "2.1.0",
            "repo_url": "https://github.com/cubiq/ComfyUI_essentials",
            "license": "MIT", "py_deps": [],
        },
    })
    rep = resolve_missing_nodes(["IPAdapterAdvanced", "ImageResize+", "TotallyNotARealNode"], index=idx)
    by_name = {r.class_name: r for r in rep.resolved}
    # copyleft pack: resolved, but NOT auto-installable (GPL-3.0 license -> normalized GPL-3.0)
    ipa = by_name["IPAdapterAdvanced"]
    assert ipa.status == "RESOLVED" and ipa.pack_id == "comfyui_ipadapter_plus"
    assert ipa.license == "GPL-3.0" and ipa.auto_installable is False
    assert ipa.py_deps == ["insightface"]
    # permissive pack: resolved AND auto-installable
    ess = by_name["ImageResize+"]
    assert ess.license == "MIT" and ess.auto_installable is True
    # class not in index -> UNRESOLVED, no Manager fallback
    assert [u.class_name for u in rep.unresolved] == ["TotallyNotARealNode"]
    assert rep.unresolved[0].status == "UNRESOLVED"


def test_missing_and_junk_license_surface_as_unknown_never_blank():
    idx = _index({
        "FooNode": {"pack_id": "foo_pack", "version": "0.1", "repo_url": "https://x/y"},           # no license key
        "BarNode": {"pack_id": "bar_pack", "version": "0.1", "license": "{}"},                       # Registry empty-json
        "BazNode": {"pack_id": "baz_pack", "version": "0.1", "license": {"file": "LICENSE"}},        # filename ref
    })
    rep = resolve_missing_nodes(["FooNode", "BarNode", "BazNode"], index=idx)
    for r in rep.resolved:
        assert r.license == UNKNOWN_LICENSE
        assert r.auto_installable is False  # UNKNOWN is never auto-installable


def test_class_not_in_index_is_unresolved_no_fallback():
    rep = resolve_missing_nodes(["A", "B"], index=_index({}))
    assert not rep.resolved and len(rep.unresolved) == 2
    assert all(u.status == "UNRESOLVED" and "no Registry pack" in u.reason for u in rep.unresolved)


def test_report_counts_and_dedup():
    idx = _index({"N1": {"pack_id": "p1", "version": "1", "license": "MIT"}})
    rep = resolve_missing_nodes(["N1", "N1", "N2"], index=idx)
    d = rep.to_dict()
    assert d["counts"]["requested"] == 2  # deduped
    assert d["counts"]["resolved"] == 1 and d["counts"]["unresolved"] == 1
    assert d["counts"]["resolved_auto_installable"] == 1
