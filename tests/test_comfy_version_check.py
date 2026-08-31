"""Is the installed ComfyUI behind? Both halves of the answer were already available and discarded.

`/system_stats` carries `system.comfyui_version` and was fetched in four places with the body thrown
away; `api.github.com/repos/Comfy-Org/ComfyUI/releases/latest` gives the newest release with no auth
and no git.

Two traps these tests pin down:

  * the repo MOVED -- comfyanonymous/ComfyUI 301-redirects, Comfy-Org/ComfyUI answers;
  * versions are not strings. Plain lexical sort over the 183 published tags returns v0.9.2 as
    newest; sort -V returns v0.34.1. Comparison must be a numeric tuple.

And the failure direction matters: an unreachable GitHub must read as "unknown", never "up to date".
A silent false negative strands someone on an old core, which is the outcome the update button
exists to prevent.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from comfy_version_check import (  # noqa: E402
    STATUS_AHEAD,
    STATUS_UNKNOWN,
    STATUS_UP_TO_DATE,
    STATUS_UPDATE_AVAILABLE,
    check_comfy_version,
    compare_versions,
    installed_version_from_system_stats,
    parse_version,
)


def _release(tag="v0.34.1", **kwargs):
    base = {"tag_name": tag, "prerelease": False, "draft": False,
            "html_url": f"https://github.com/Comfy-Org/ComfyUI/releases/tag/{tag}",
            "published_at": "2026-08-01T00:00:00Z"}
    base.update(kwargs)
    return base


def _fetch(release, calls=None):
    def fetch(url, *, timeout=10.0):
        if calls is not None:
            calls.append(url)
        if release is None:
            raise OSError("connection refused")
        return release
    return fetch


# --- version comparison --------------------------------------------------------------------------

def test_versions_compare_numerically_not_lexically():
    """The sort trap: as strings, "0.9.2" > "0.34.1"."""
    assert compare_versions("0.9.2", "0.34.1") == STATUS_UPDATE_AVAILABLE
    assert compare_versions("0.34.1", "0.9.2") == STATUS_AHEAD


def test_the_v_prefix_is_ignored_on_either_side():
    assert compare_versions("0.34.1", "v0.34.1") == STATUS_UP_TO_DATE


def test_differing_component_counts_compare_sensibly():
    assert compare_versions("0.34", "0.34.0") == STATUS_UP_TO_DATE
    assert compare_versions("0.34", "0.34.1") == STATUS_UPDATE_AVAILABLE


def test_a_release_candidate_parses_to_its_base_version():
    assert parse_version("0.34.1-rc2") == (0, 34, 1)


def test_an_unparseable_version_is_unknown_not_an_update():
    assert compare_versions("nightly", "0.34.1") == STATUS_UNKNOWN
    assert compare_versions("0.27.0", None) == STATUS_UNKNOWN


# --- the check ------------------------------------------------------------------------------------

def test_an_older_install_offers_the_update(tmp_path):
    result = check_comfy_version("0.27.0", fetch=_fetch(_release()), cache_path=tmp_path / "c.json")
    assert result.status == STATUS_UPDATE_AVAILABLE
    assert result.update_available is True
    assert result.installed == "0.27.0" and result.latest == "v0.34.1"
    assert result.release_url.endswith("v0.34.1")


def test_a_current_install_is_up_to_date(tmp_path):
    result = check_comfy_version("0.34.1", fetch=_fetch(_release()), cache_path=tmp_path / "c.json")
    assert result.status == STATUS_UP_TO_DATE
    assert result.update_available is False


def test_an_unreachable_github_is_unknown_never_up_to_date(tmp_path):
    result = check_comfy_version("0.27.0", fetch=_fetch(None), cache_path=tmp_path / "c.json")
    assert result.status == STATUS_UNKNOWN
    assert result.update_available is False
    assert "Could not reach GitHub" in result.reason


def test_a_stale_cache_beats_no_answer(tmp_path):
    cache = tmp_path / "c.json"
    check_comfy_version("0.27.0", fetch=_fetch(_release()), cache_path=cache)
    # TTL expired AND the network is down: the last known release is still better than "unknown".
    result = check_comfy_version("0.27.0", fetch=_fetch(None), cache_path=cache, ttl=-1)
    assert result.status == STATUS_UPDATE_AVAILABLE
    assert result.from_cache is True


def test_a_prerelease_is_not_offered_as_an_update(tmp_path):
    result = check_comfy_version("0.27.0", fetch=_fetch(_release("v0.35.0-rc1", prerelease=True)),
                                 cache_path=tmp_path / "c.json")
    assert result.status == STATUS_UNKNOWN
    assert result.update_available is False


def test_comfy_not_running_is_unknown(tmp_path):
    result = check_comfy_version(None, fetch=_fetch(_release()), cache_path=tmp_path / "c.json")
    assert result.status == STATUS_UNKNOWN
    assert "not running" in result.reason


def test_the_result_is_cached_so_the_status_poll_does_not_hammer_github(tmp_path):
    calls: list[str] = []
    fetch = _fetch(_release(), calls)
    cache = tmp_path / "c.json"
    for _ in range(5):
        check_comfy_version("0.27.0", fetch=fetch, cache_path=cache)
    assert len(calls) == 1
    assert calls[0].startswith("https://api.github.com/repos/Comfy-Org/ComfyUI/"), \
        "comfyanonymous/ComfyUI 301-redirects; the release API answers on Comfy-Org"


def test_force_bypasses_the_cache(tmp_path):
    calls: list[str] = []
    fetch = _fetch(_release(), calls)
    cache = tmp_path / "c.json"
    check_comfy_version("0.27.0", fetch=fetch, cache_path=cache)
    check_comfy_version("0.27.0", fetch=fetch, cache_path=cache, force=True)
    assert len(calls) == 2


# --- reading the installed version -----------------------------------------------------------------

def test_installed_version_is_read_from_system_stats():
    stats = {"system": {"comfyui_version": "0.34.0", "pytorch_version": "2.10.0+cu128"}}
    assert installed_version_from_system_stats(stats) == "0.34.0"


def test_a_missing_or_malformed_system_stats_yields_none():
    assert installed_version_from_system_stats(None) is None
    assert installed_version_from_system_stats({}) is None
    assert installed_version_from_system_stats({"system": {}}) is None
