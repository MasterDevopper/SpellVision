"""One request key, two node vocabularies, no translation.

Two node families answer "where does the text encoder run" with different words for the same place:

    core ComfyUI CLIPLoader / DualCLIPLoader    device: ["default", "cpu"]
    core LTXAVTextEncoderLoader                 device: ["default", "cpu"]
    kijai WanVideoTextEncode                    device: ["gpu", "cpu"]

Nine sites set that input and every one of them read the SAME request key, ``text_encoder_device``,
forwarding the user's word to whichever node was in front of them. So a stated ``"gpu"`` reached a
core loader whose combo does not contain it, and a stated ``"default"`` reached the wrapper's, and
ComfyUI answered both with a 400 naming a node the user never chose.

The vocabularies are genuinely different and are NOT merged -- that would be applying a rule at the
wrong level, which rule 5 warns is the same bug in disguise. What is shared is the INTENT: run the
text encoder on the GPU, or off it. The resolver translates that intent into each node's own
spelling, read from ``/object_info`` rather than from a remembered pair, because the LTX prefix bug
was a value recalled instead of read.

Two further defects the same reading found:

* **LTX read a different key.** ``ltx_text_encoder_device`` is a name nothing else in the tree
  writes, so the cockpit's setting did nothing on that route -- a control that works everywhere else
  and is inert in one place, which is the Phase 2d defect class exactly.
* **Eight of the nine never consulted the memory profile.** ``comfy_text_encoder_device`` decides
  CPU placement when VRAM is tight and only krea2 called it, so a low-VRAM profile moved krea2's
  text encoder off the GPU and left every other family's on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from comfy_graph_helpers import (  # noqa: E402
    text_encoder_device,
    text_encoder_device_input,
)

CORE = {"CLIPLoader": {"input": {"optional": {"device": [["default", "cpu"], {}]}}}}
WRAPPER = {"WanVideoTextEncode": {"input": {"required": {"device": [["gpu", "cpu"], {}]}}}}
NO_DEVICE = {"CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}]}}}}


# --- one intent, each node's own word -----------------------------------------------------------

@pytest.mark.parametrize("stated", ["gpu", "GPU", " cuda ", "default"])
def test_on_gpu_is_spelled_for_the_node_that_receives_it(stated: str) -> None:
    """The defect. `gpu` and `default` name the same place; each node accepts only one of them."""
    assert text_encoder_device({"text_encoder_device": stated}, CORE, "CLIPLoader") == "default"
    assert text_encoder_device(
        {"text_encoder_device": stated}, WRAPPER, "WanVideoTextEncode") == "gpu"


def test_off_gpu_happens_to_share_a_word_and_is_still_resolved_not_forwarded() -> None:
    """Both vocabularies spell it "cpu", which is why forwarding LOOKED correct for so long: the
    only case anyone tested by hand was the one where the two vocabularies agree."""
    assert text_encoder_device({"text_encoder_device": "cpu"}, CORE, "CLIPLoader") == "cpu"
    assert text_encoder_device({"text_encoder_device": "cpu"}, WRAPPER, "WanVideoTextEncode") == "cpu"


def test_the_vocabulary_comes_from_object_info_not_from_a_remembered_pair() -> None:
    """A node that renames its values is followed, not second-guessed. Hardcoding the two known
    lists would need editing the day the wrapper renames one -- and the LTX prefix bug was exactly
    a value remembered instead of read."""
    renamed = {"SomeFutureEncoder": {"input": {"required": {"device": [["accelerator", "cpu"], {}]}}}}
    assert text_encoder_device({"text_encoder_device": "gpu"}, renamed, "SomeFutureEncoder") == ""


def test_a_word_naming_no_placement_is_reported_and_dropped(caplog) -> None:
    """Forwarding it would produce a 400 from ComfyUI naming a node the user never chose. Saying so
    here names the value the user actually typed."""
    import logging

    with caplog.at_level(logging.WARNING):
        assert text_encoder_device({"text_encoder_device": "wizard"}, CORE, "CLIPLoader") == "default"
    assert any("wizard" in r.getMessage() for r in caplog.records)


def test_a_node_without_the_input_gets_nothing() -> None:
    """Adding a key a node does not declare is a 400. Returning "" lets `_set_if_allowed` and the
    dict-splat form both contribute nothing."""
    assert text_encoder_device({"text_encoder_device": "cpu"}, NO_DEVICE, "CLIPTextEncode") == ""
    assert text_encoder_device_input({}, NO_DEVICE, "CLIPTextEncode") == {}
    assert text_encoder_device({}, {}, "Missing") == ""


def test_the_input_form_splats_cleanly() -> None:
    assert text_encoder_device_input({"text_encoder_device": "cpu"}, CORE, "CLIPLoader") == {"device": "cpu"}
    node = {"class_type": "CLIPLoader",
            "inputs": {"clip_name": "x", **text_encoder_device_input({}, CORE, "CLIPLoader")}}
    assert node["inputs"]["device"] in {"default", "cpu"}


# --- precedence ---------------------------------------------------------------------------------

def test_the_request_outranks_the_resolved_stack() -> None:
    assert text_encoder_device(
        {"text_encoder_device": "cpu"}, CORE, "CLIPLoader",
        stack={"text_encoder_device": "default"}) == "cpu"


def test_the_stack_is_used_when_the_request_is_silent() -> None:
    assert text_encoder_device({}, CORE, "CLIPLoader", stack={"text_encoder_device": "cpu"}) == "cpu"


def test_an_empty_value_is_silence_not_a_choice() -> None:
    """`""` is what the UI sends for "unset"; treating it as a stated value would pin every render
    to whatever the first branch happened to produce."""
    for empty in ("", "   ", None):
        assert text_encoder_device({"text_encoder_device": empty}, CORE, "CLIPLoader") in {"default", "cpu"}


def test_the_ltx_key_is_honoured_and_so_is_the_shared_one() -> None:
    """LTX read `ltx_text_encoder_device` and nothing else wrote it, so the cockpit's setting was
    dropped on that route. Both are read now, the specific one first so an existing caller keeps
    its override."""
    ltx = {"LTXAVTextEncoderLoader": {"input": {"required": {"device": [["default", "cpu"], {}]}}}}
    keys = ("ltx_text_encoder_device", "text_encoder_device")
    assert text_encoder_device({"text_encoder_device": "cpu"}, ltx, "LTXAVTextEncoderLoader",
                               keys=keys) == "cpu"
    assert text_encoder_device({"ltx_text_encoder_device": "cpu", "text_encoder_device": "gpu"},
                               ltx, "LTXAVTextEncoderLoader", keys=keys) == "cpu"


# --- the memory profile decides when nobody states anything -------------------------------------

def test_an_unstated_placement_follows_the_memory_profile(monkeypatch) -> None:
    """Eight of the nine sites hardcoded their default instead, so a low-VRAM profile offloaded
    krea2's text encoder and nobody else's -- the same product, the same setting, different
    behaviour by family."""
    import comfy_graph_helpers
    import memory_optimization

    monkeypatch.setattr(memory_optimization, "comfy_text_encoder_device", lambda **_k: "cpu")
    assert text_encoder_device({}, CORE, "CLIPLoader") == "cpu"
    assert text_encoder_device({}, WRAPPER, "WanVideoTextEncode") == "cpu"

    monkeypatch.setattr(memory_optimization, "comfy_text_encoder_device", lambda **_k: "default")
    assert text_encoder_device({}, CORE, "CLIPLoader") == "default"
    # ...and the SAME profile answer reaches the wrapper in the wrapper's word.
    assert text_encoder_device({}, WRAPPER, "WanVideoTextEncode") == "gpu"
    assert comfy_graph_helpers  # imported for the monkeypatch to bind through


def test_a_stated_value_beats_the_profile(monkeypatch) -> None:
    """The profile is a default, not an override. A user who asks for the GPU on a tight profile is
    making a choice they are allowed to make."""
    import memory_optimization

    monkeypatch.setattr(memory_optimization, "comfy_text_encoder_device", lambda **_k: "cpu")
    assert text_encoder_device({"text_encoder_device": "gpu"}, CORE, "CLIPLoader") == "default"


# --- every builder actually routes through it ---------------------------------------------------

@pytest.mark.parametrize("module,loader", [
    ("native_image_graphs", "text_encoder_device_input"),
    ("native_video_graphs", "text_encoder_device"),
])
def test_the_builders_import_the_resolver(module: str, loader: str) -> None:
    source = (ROOT / "python" / f"{module}.py").read_text(encoding="utf-8")
    assert loader in source, f"{module} does not use {loader}"


def test_no_builder_still_spells_a_device_by_hand() -> None:
    """The sweep owns this tree-wide; asserted here too so the rule's own subject stays visible in
    the file that explains it."""
    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import rules

    violations = [r for r in rules.ALL_RULES
                  if r.name == "text-encoder-placement-through-one-resolver"][0].run()
    assert not violations, [str(v) for v in violations]
