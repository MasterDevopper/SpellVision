"""What build produced this render.

Every render already records its seconds. None records which build made them, which is why the
only published A/B on this project is distinguishable solely because a human typed "t4_sage" and
"t4_sdpa" into two output filenames. A number without its arm is not evidence.

The arm is read from the RUNNING process's argv, never from what the launcher intended: the Qt
sage probe fails open to SDPA on a cold first launch, so intent and reality have diverged here
before.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import optimization_provenance as op


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(getattr(request, "full_url", str(request)))
        return FakeResponse(json.dumps(self.payload).encode("utf-8"))


LIVE = {
    "system": {
        "comfyui_version": "0.34.0",
        "pytorch_version": "2.10.0+cu128",
        "python_version": "3.12.7",
        "argv": ["C:/sv/ComfyUI/main.py", "--listen", "127.0.0.1", "--port", "8188",
                 "--use-sage-attention"],
        # This is the REAL shape /system_stats sends -- a LIST of {name, installed, required}
        # dicts -- not a dict keyed by name. The old dict-shaped fixture here validated a parser
        # that silently dropped every entry; see test_probe_reads_the_live_stats below and the
        # commit that fixed this.
        "comfy_package_versions": [
            {"name": "comfyui-frontend-package", "installed": "1.49.6", "required": "1.49.6"},
            {"name": "comfy-kitchen", "installed": "0.2.31", "required": "0.2.31"},
            {"name": "comfy-aimdo", "installed": "0.4.15", "required": "0.4.15"},
        ],
    }
}


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["main.py", "--use-sage-attention"], "sage"),
        (["main.py", "--use-flash-attention"], "flash"),
        (["main.py", "--use-ck-attention"], "ck"),
        (["main.py", "--use-pytorch-cross-attention"], "sdpa"),
        (["main.py", "--use-split-cross-attention"], "split"),
        (["main.py", "--listen", "127.0.0.1"], "sdpa"),
    ],
)
def test_attention_is_read_from_the_running_argv(argv, expected):
    assert op.attention_from_argv(argv) == expected


def test_fast_flags_bare_means_every_feature():
    """`--fast` with no values enables all of them; the record must say which, not repeat the flag."""
    assert set(op.fast_from_argv(["main.py", "--fast"])) == set(op.ALL_FAST_FEATURES)


def test_fast_flags_named_are_recorded_as_named():
    assert op.fast_from_argv(["main.py", "--fast", "fp16_accumulation"]) == ["fp16_accumulation"]


def test_no_fast_flag_is_an_empty_list_not_none():
    assert op.fast_from_argv(["main.py", "--use-sage-attention"]) == []


def test_dynamic_vram_is_on_unless_disabled():
    assert op.dynamic_vram_from_argv(["main.py"]) is True
    assert op.dynamic_vram_from_argv(["main.py", "--disable-dynamic-vram"]) is False


def test_reserve_vram_is_recorded_when_given():
    assert op.reserve_vram_from_argv(["main.py", "--reserve-vram", "16"]) == 16.0
    assert op.reserve_vram_from_argv(["main.py"]) is None


def test_probe_reads_the_live_stats(monkeypatch):
    # Isolate this test from whatever's actually installed in whatever interpreter
    # _venv_package_availability would otherwise resolve to -- that mechanism has its own
    # dedicated tests below.
    monkeypatch.setattr(op, "_venv_package_availability", lambda exe: (True, False))
    block = op.probe("http://127.0.0.1:8188", opener=FakeOpener(LIVE))
    assert block["attention_backend"] == "sage"
    assert block["comfy_version"] == "0.34.0"
    assert block["torch"] == "2.10.0+cu128"
    assert block["cuda"] == "12.8"
    assert block["dynamic_vram"] is True
    assert block["packages"]["comfy_aimdo"] == "0.4.15"
    assert block["packages"]["comfy_kitchen"] == "0.2.31"
    assert "--use-sage-attention" in block["comfy_argv"]


def test_probe_parses_the_list_shape_not_a_dict_shape():
    """The defect: comfy_package_versions is a list of dicts, not a dict keyed by name. A parser
    written against the wrong shape returns None for everything and no test catches it unless the
    fixture matches what the server actually sends.
    """
    assert op._package_versions_from_system_stats(LIVE["system"]["comfy_package_versions"]) == {
        "comfyui-frontend-package": "1.49.6",
        "comfy-kitchen": "0.2.31",
        "comfy-aimdo": "0.4.15",
    }
    # The old (wrong) fixture shape must not silently "work" -- a dict input is not a list.
    assert op._package_versions_from_system_stats({"comfy-aimdo": "0.4.15"}) == {}


def test_venv_package_availability_distinguishes_not_probed_from_absent(monkeypatch):
    """None ("not probed") must never collapse into False ("probed, not found") -- that collapse is
    what made two knowable packages read as unknowable.
    """
    import comfy_launch_policy

    monkeypatch.setattr(comfy_launch_policy, "sageattention_available", lambda exe: True)
    monkeypatch.setattr(comfy_launch_policy, "triton_available", lambda exe: False)
    assert op._venv_package_availability("some/python") == (True, False)

    def _explode(exe):
        raise RuntimeError("could not resolve comfy's interpreter")

    monkeypatch.setattr(comfy_launch_policy, "sageattention_available", _explode)
    assert op._venv_package_availability("some/python") == (None, None)


def test_probe_failure_is_a_block_that_says_it_does_not_know():
    """A render still has to be recordable when the probe fails -- but it must not claim SDPA."""

    class Broken:
        def open(self, request, timeout=None):
            raise OSError("comfy down")

    block = op.probe("http://127.0.0.1:8188", opener=Broken())
    assert block["attention_backend"] == "unknown"
    assert block["comfy_version"] is None
    assert block.get("probe_error")


def test_the_block_never_claims_a_default_it_did_not_read(monkeypatch):
    monkeypatch.setattr(op, "_venv_package_availability", lambda exe: (None, None))
    block = op.probe("http://127.0.0.1:8188", opener=FakeOpener({"system": {}}))
    assert block["attention_backend"] == "unknown"
    assert block["comfy_argv"] == []


def test_build_metadata_payload_carries_the_arm():
    """Integration: the actual sidecar-writing function this task wires must carry the block.

    Every other test here exercises the module in isolation; this is the one that would have
    caught the defect if worker_metadata.build_metadata_payload had never been wired to it at all.
    """
    from worker_metadata import build_metadata_payload

    data = build_metadata_payload(
        req={"prompt": "x", "enable_vae_tiling": True},
        image_path="out.png",
        metadata_output="out.json",
        backend_name="diffusers",
        device="cuda",
        dtype="float16",
        detected_pipeline="sdxl",
        lora_used=False,
        elapsed=1.0,
        steps_per_sec=1.0,
    )
    assert "optimizations" in data
    optimizations = data["optimizations"]
    assert {"attention_backend", "comfy_argv", "fast_flags", "dynamic_vram", "vae_tiling",
            "fp16_cast", "wrapper_attention_mode"} <= set(optimizations)
    assert optimizations["vae_tiling"] is True
