"""Offload ordering for the native (diffusers) video pipeline.

The bug this pins: _load_native_video_pipeline called `pipe.to(device)` and THEN
`enable_model_cpu_offload()`. apply_memory_profile's contract in memory_optimization.py is
explicit that the caller must NOT pre-move to CUDA -- accelerate's offload hooks own device
placement, so pre-moving defeats them. The pipeline ended up resident on the GPU *and* paying
the hook overhead: the worst of both, while the code read as if it were saving memory.

Offload was also hardcoded on (`req.get("enable_cpu_offload", True)`), so a 32GB PERFORMANCE
card paid a ~10-20% throughput cost for savings the ordering had already destroyed.

Uses a fake pipeline that records the call order, so the contract is asserted without diffusers,
CUDA, or a model on disk.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import native_runners as nr  # noqa: E402
from memory_optimization import MemoryProfile  # noqa: E402


class _BaseWs:
    """The worker-module surface _load_native_video_pipeline reaches for, stubbed."""

    @staticmethod
    def _video_model_stack_from_request(_req):
        return {}

    @staticmethod
    def _stack_summary(_stack):
        return "fake-stack"

    @staticmethod
    def torch_dtype_and_device():
        import torch

        return torch.float32, "cpu"


class FakePipe:
    def __init__(self):
        self.calls: list[str] = []

    def to(self, device):  # noqa: ARG002
        self.calls.append("to")
        return self

    def enable_model_cpu_offload(self):
        self.calls.append("offload")

    def set_progress_bar_config(self, **_):
        self.calls.append("progress")

    def enable_attention_slicing(self):
        self.calls.append("slice")


@pytest.fixture
def harness(monkeypatch):
    """Drive _load_native_video_pipeline with a fake pipeline class and a chosen profile."""
    made: list[FakePipe] = []

    class FakeCls:
        @staticmethod
        def from_pretrained(*_a, **_k):
            p = FakePipe()
            made.append(p)
            return p

    monkeypatch.setattr(nr, "_native_video_pipeline_candidates", lambda *a, **k: ["FakeVideoPipeline"])

    class FakeWs(_BaseWs):
        @staticmethod
        def _import_diffusers_symbol(_name):
            return FakeCls

        @staticmethod
        def optimize_pipeline(pipe, device, *, profile=None):  # noqa: ARG004
            pipe.calls.append("optimize")
            return pipe

    monkeypatch.setattr(nr, "_ws", lambda: FakeWs)
    # A diffusers-format reference (no weights suffix), so the loader takes the pipeline path
    # rather than the "split stack is not wired into diffusers" bail-out.
    monkeypatch.setattr(nr, "_native_video_model_reference", lambda *a, **k: "fake/video-pipeline")
    return made


def _load(req, monkeypatch, profile):
    monkeypatch.setattr(nr, "auto_select_memory_profile", lambda: profile)
    pipe, _device, _dtype, _cls = nr._load_native_video_pipeline(req, "t2v", "wan_diffusers")
    return pipe


def test_offload_is_never_preceded_by_a_device_move(harness, monkeypatch):
    pipe = _load({"enable_cpu_offload": True}, monkeypatch, MemoryProfile.LOW_VRAM)
    assert "offload" in pipe.calls
    assert "to" not in pipe.calls, (
        f"pre-moved to device before offload, defeating the hooks: {pipe.calls}"
    )


def test_optimizations_run_before_offload_hooks_exist(harness, monkeypatch):
    pipe = _load({"enable_cpu_offload": True}, monkeypatch, MemoryProfile.LOW_VRAM)
    assert pipe.calls.index("optimize") < pipe.calls.index("offload")


def test_performance_profile_does_not_offload_by_default(harness, monkeypatch):
    pipe = _load({}, monkeypatch, MemoryProfile.PERFORMANCE)
    assert "offload" not in pipe.calls, "offload cost paid on a card with headroom"
    assert "to" in pipe.calls, "must be placed on the device when not offloading"


def test_constrained_profile_offloads_by_default(harness, monkeypatch):
    pipe = _load({}, monkeypatch, MemoryProfile.LOW_VRAM)
    assert "offload" in pipe.calls
    assert "to" not in pipe.calls


def test_request_can_force_offload_off_on_a_small_card(harness, monkeypatch):
    pipe = _load({"enable_cpu_offload": False}, monkeypatch, MemoryProfile.LOW_VRAM)
    assert "offload" not in pipe.calls
    assert "to" in pipe.calls


def test_request_can_force_offload_on_for_a_big_card(harness, monkeypatch):
    pipe = _load({"enable_cpu_offload": True}, monkeypatch, MemoryProfile.PERFORMANCE)
    assert "offload" in pipe.calls
    assert "to" not in pipe.calls


def test_pipeline_is_still_placed_when_offload_raises(harness, monkeypatch):
    """A failed offload must fall back to an explicit device move, not leave it on CPU."""

    class Boom(FakePipe):
        def enable_model_cpu_offload(self):
            raise RuntimeError("accelerate missing")

    monkeypatch.setattr(nr, "auto_select_memory_profile", lambda: MemoryProfile.LOW_VRAM)
    monkeypatch.setattr(nr, "_native_video_pipeline_candidates", lambda *a, **k: ["FakeVideoPipeline"])
    monkeypatch.setattr(nr, "_native_video_model_reference", lambda *a, **k: "fake/video-pipeline")

    class FakeCls:
        @staticmethod
        def from_pretrained(*_a, **_k):
            return Boom()

    class FakeWs(_BaseWs):
        @staticmethod
        def _import_diffusers_symbol(_name):
            return FakeCls

        @staticmethod
        def optimize_pipeline(pipe, device, *, profile=None):  # noqa: ARG004
            return pipe

    monkeypatch.setattr(nr, "_ws", lambda: FakeWs)
    pipe, _d, _dt, _c = nr._load_native_video_pipeline({}, "t2v", "wan_diffusers")
    assert "to" in pipe.calls
