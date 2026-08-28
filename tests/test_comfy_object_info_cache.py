"""/object_info is ~2MB of JSON that was fetched and parsed on EVERY native job.

The node set it describes is static for the lifetime of a ComfyUI process, so it is cached per
endpoint with an explicit invalidation on restart/install and a TTL backstop. These tests pin the
contract that matters: repeat calls do not re-fetch, and anything that can change the node set
does force a re-fetch.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import comfy_prompt_client as cpc  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    cpc.invalidate_comfy_object_info("test setup")
    yield
    cpc.invalidate_comfy_object_info("test teardown")


@pytest.fixture
def counted_fetch(monkeypatch):
    calls: list[str] = []

    # Mirrors the real signature, budget_sec included: a double that is narrower than the function
    # it replaces turns a caller passing a new argument into a TypeError instead of a test result.
    def fake(api_url: str, *, budget_sec: float | None = None):
        calls.append(api_url)
        return {"KSampler": {"input": {}}, "_call": len(calls)}

    monkeypatch.setattr(cpc, "_fetch_comfy_object_info", fake)
    return calls


def test_repeat_calls_hit_the_cache(counted_fetch):
    first = cpc._comfy_object_info("http://127.0.0.1:8188")
    for _ in range(5):
        cpc._comfy_object_info("http://127.0.0.1:8188")
    assert counted_fetch == ["http://127.0.0.1:8188"]
    assert first["_call"] == 1


def test_distinct_endpoints_are_cached_separately(counted_fetch):
    cpc._comfy_object_info("http://127.0.0.1:8188")
    cpc._comfy_object_info("http://127.0.0.1:8189")
    cpc._comfy_object_info("http://127.0.0.1:8188")
    assert counted_fetch == ["http://127.0.0.1:8188", "http://127.0.0.1:8189"]


def test_invalidation_forces_a_refetch(counted_fetch):
    cpc._comfy_object_info("http://127.0.0.1:8188")
    cpc.invalidate_comfy_object_info("comfy runtime restarted")
    cpc._comfy_object_info("http://127.0.0.1:8188")
    assert len(counted_fetch) == 2


def test_force_refresh_bypasses_the_cache(counted_fetch):
    cpc._comfy_object_info("http://127.0.0.1:8188")
    cpc._comfy_object_info("http://127.0.0.1:8188", force_refresh=True)
    assert len(counted_fetch) == 2


def test_expired_ttl_refetches(counted_fetch, monkeypatch):
    cpc._comfy_object_info("http://127.0.0.1:8188")
    # Age the entry past the TTL without sleeping.
    with cpc._OBJECT_INFO_LOCK:
        stamp, payload = cpc._OBJECT_INFO_CACHE["http://127.0.0.1:8188"]
        cpc._OBJECT_INFO_CACHE["http://127.0.0.1:8188"] = (stamp - cpc._OBJECT_INFO_TTL_SEC - 1.0, payload)
    cpc._comfy_object_info("http://127.0.0.1:8188")
    assert len(counted_fetch) == 2


def test_a_failed_fetch_is_not_cached(monkeypatch):
    calls: list[str] = []

    def boom(api_url: str, *, budget_sec: float | None = None):
        calls.append(api_url)
        raise RuntimeError("comfy down")

    monkeypatch.setattr(cpc, "_fetch_comfy_object_info", boom)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cpc._comfy_object_info("http://127.0.0.1:8188")
    assert len(calls) == 3
