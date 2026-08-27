"""What a graph OUTPUTS decides what it is; a word in a prompt decides nothing.

Reproduced before the fix: a plain SDXL text-to-image graph -- CheckpointLoaderSimple, CLIPTextEncode,
EmptyLatentImage, KSampler, VAEDecode, SaveImage -- classified as **t2v / video at 0.99 confidence**
purely because its prompt read "a swan gliding on a still lake". Also "a wandering knight", "a night
market in Taiwan", and "a plate of mochi dessert".

Three separate defects produced that:

  * `_node_text` concatenates class name, title, input names AND input VALUES, so substring markers
    were matched against the user's prompt;
  * the markers were bare substrings -- "wan" inside swan/wandering/Taiwan, "mochi" the dessert;
  * a video-family node alone set media_type="video", overriding a SaveImage that was sitting right
    there in the same evidence list. And because confidence summed every piece of evidence,
    contradictory evidence RAISED it: the most ambiguous graphs reported the most certainty.

`primary_task` drives the launch type and the output file extension, so this submitted a t2i graph
as a video job.

Library effect: 53 image / 28 video -> 56 image / 25 video. The three that moved (basict2i-v23,
detailer-v23, t2i-v23) are t2i workflows that use the "Image Saver" custom node instead of core
SaveImage, so nothing recognised their output at all.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from workflow_scanner import (  # noqa: E402
    WorkflowNodeInfo,
    _class_words,
    _node_is_image_output,
    _node_is_video_core,
    scan_workflow,
)


def _t2i(prompt: str, saver: str = "SaveImage") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "juggernautXL_v9.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
        "4": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 30, "cfg": 7.0}},
        "5": {"class_type": "VAEDecode", "inputs": {}},
        "6": {"class_type": saver, "inputs": {"filename_prefix": "out"}},
    }


def _cap(graph):
    return scan_workflow(graph).capability_report


# --- the prompt must not decide the task ---------------------------------------------------------

def test_a_prompt_word_never_makes_a_t2i_graph_a_video_graph():
    for prompt in ("a swan gliding on a still lake at dawn",
                   "a wandering knight in a wheat field",
                   "a night market in Taiwan, neon",
                   "a plate of mochi dessert, macro",
                   "render like an mp4 still, gif vibes, 24 fps look"):
        cap = _cap(_t2i(prompt))
        assert cap.primary_task == "t2i", f"{prompt!r} -> {cap.primary_task}"
        assert cap.media_type == "image"


def test_the_baseline_prompt_is_unaffected():
    cap = _cap(_t2i("a portrait of a woman, studio lighting"))
    assert (cap.primary_task, cap.media_type) == ("t2i", "image")
    assert cap.confidence >= 0.8


# --- real video graphs must still classify -------------------------------------------------------

def test_a_wan_video_graph_is_still_video():
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.1_t2v.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a dog running"}},
        "3": {"class_type": "WanImageToVideo", "inputs": {"num_frames": 81}},
        "4": {"class_type": "KSampler", "inputs": {}},
        "5": {"class_type": "SaveVideo", "inputs": {}},
    }
    cap = _cap(graph)
    assert cap.media_type == "video"
    assert cap.confidence >= 0.8


def test_a_video_core_with_no_output_node_is_still_video():
    """Nothing contradicts it, so the core is allowed to decide."""
    graph = {
        "1": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"length": 49}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
        "3": {"class_type": "VAEDecode", "inputs": {}},
    }
    assert _cap(graph).media_type == "video"


# --- contradiction lowers confidence -------------------------------------------------------------

def test_a_video_core_with_an_image_output_reads_as_image_and_says_why():
    graph = _t2i("a portrait")
    graph["7"] = {"class_type": "WanVideoSampler", "inputs": {}}
    cap = _cap(graph)
    assert cap.media_type == "image"
    assert any("video-family nodes but its only output is an image" in w for w in cap.warnings)


def test_contradictory_evidence_lowers_confidence_instead_of_raising_it():
    """Summing evidence meant the most ambiguous graph reported the most certainty."""
    clean = _cap(_t2i("a portrait"))
    conflicted_graph = _t2i("a portrait")
    conflicted_graph["7"] = {"class_type": "WanVideoSampler", "inputs": {}}
    conflicted = _cap(conflicted_graph)
    assert conflicted.confidence < clean.confidence


# --- word matching --------------------------------------------------------------------------------

def test_class_words_split_camel_case_and_separators():
    assert _class_words("WanImageToVideo") == {"wan", "image", "to", "video"}
    assert _class_words("VHS_VideoCombine") == {"vhs", "video", "combine"}
    assert _class_words("Sampler Selector (Image Saver)") == {"sampler", "selector", "image", "saver"}


def test_video_core_matches_a_class_word_not_a_substring():
    assert _node_is_video_core(WorkflowNodeInfo(node_id="1", class_type="WanImageToVideo"))
    assert not _node_is_video_core(WorkflowNodeInfo(node_id="1", class_type="SwanTransform"))


def test_video_core_matches_a_schema_input_name():
    """An input literally named num_frames is schema; the word "frames" in a prompt is not."""
    assert _node_is_video_core(WorkflowNodeInfo(node_id="1", class_type="Thing", input_names=["num_frames"]))
    assert not _node_is_video_core(WorkflowNodeInfo(node_id="1", class_type="Thing", input_names=["text"]))


# --- output detection ------------------------------------------------------------------------------

def test_a_custom_pack_saver_counts_as_an_image_output():
    """Three t2i workflows here use alexopus/ComfyUI-Image-Saver's "Image Saver"."""
    cap = _cap(_t2i("a portrait", saver="Image Saver"))
    assert (cap.primary_task, cap.media_type) == ("t2i", "image")


def test_loaders_and_selectors_are_not_outputs():
    for cls in ("LoadImage", "LoadImageBatch", "ImageResizeKJv2", "Sampler Selector (Image Saver)"):
        assert not _node_is_image_output(WorkflowNodeInfo(node_id="1", class_type=cls)), cls


def test_core_savers_are_outputs():
    for cls in ("SaveImage", "PreviewImage", "Image Saver"):
        assert _node_is_image_output(WorkflowNodeInfo(node_id="1", class_type=cls)), cls


def test_an_animated_webp_saver_is_not_an_image_output():
    """SaveAnimatedWEBP produces video; counting it as an image output would flip the verdict."""
    assert not _node_is_image_output(WorkflowNodeInfo(node_id="1", class_type="SaveAnimatedWEBP"))
