"""The converter refuses what it cannot resolve, and can never emit a dangling link.

The defect these guard (2026-09-17): a node whose class had no schema was OMITTED while every link
into it stayed, and the conversion reported no error. The prompt that came out was rejected by the
live server with

    HTTP 400  error.type = "prompt_outputs_failed_validation"
    node_errors: {"type": "exception_during_validation",
                  "extra_info": {"exception_type": "KeyError"}}   # execution.py:1184

-- a KeyError naming a node id the user has never seen, with nothing anywhere saying a node pack was
missing. Fourteen of the imported library's UI graphs converted to such a prompt.

Two separate guarantees are tested here, because they fail for different reasons and need different
fixes: the REFUSAL (a missing pack, the user's problem) and the POST-CONDITION (a dangling link with
nothing missing, our bug). The post-condition is the one that outlives this particular cause.

Hermetic: the schema fragments are copied from a live ``/object_info`` dump of core v0.34.0 and the
copy is recorded in the test that uses it. Nothing here reaches the network or the server.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from comfy_graph_converter import convert_ui_graph, convert_ui_graph_to_api_prompt  # noqa: E402
from comfy_graph_links import (  # noqa: E402
    assert_no_dangling_links,
    find_dangling_links,
    is_link,
    prompt_verdict,
)
from comfy_missing_packs import missing_class_message, missing_pack_entries  # noqa: E402


# --------------------------------------------------------------------------------------------
# Schemas, copied verbatim from a live /object_info (ComfyUI core v0.34.0, 3607 classes).
# The input ORDER is the whole point of the widget tests below, so it is never retyped from memory.
# --------------------------------------------------------------------------------------------

SCHEMA = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["a.safetensors"], {}]}}},
    "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {"multiline": True}],
                                              "clip": ["CLIP", {}]}}},
    "PreviewImage": {"input": {"required": {"images": ["IMAGE", {}]}}},
    "EmptyHunyuanLatentVideo": {"input": {"required": {
        "width": ["INT", {"default": 848, "min": 16, "max": 16384, "step": 16}],
        "height": ["INT", {"default": 480, "min": 16, "max": 16384, "step": 16}],
        "length": ["INT", {"default": 25, "min": 1, "max": 16384, "step": 4}],
        "batch_size": ["INT", {"default": 1, "min": 1, "max": 4096}],
    }}},
    "WanImageToVideo": {"input": {
        "required": {
            "positive": ["CONDITIONING", {}],
            "negative": ["CONDITIONING", {}],
            "vae": ["VAE", {}],
            "width": ["INT", {"default": 832, "min": 16, "max": 16384, "step": 16}],
            "height": ["INT", {"default": 480, "min": 16, "max": 16384, "step": 16}],
            "length": ["INT", {"default": 81, "min": 1, "max": 16384, "step": 4}],
            "batch_size": ["INT", {"default": 1, "min": 1, "max": 4096}],
        },
        "optional": {
            "clip_vision_output": ["CLIP_VISION_OUTPUT", {}],
            "start_image": ["IMAGE", {}],
        },
    }},
}


def _graph(nodes, links=()):
    return {"nodes": list(nodes), "links": [list(link) for link in links]}


# --------------------------------------------------------------------------------------------
# Task 1 -- refuse, and name what is missing
# --------------------------------------------------------------------------------------------

def _graph_with_missing_class(properties=None):
    """A checkpoint feeding a node whose class this ComfyUI does not have, feeding a preview.

    The link INTO the missing node is what made the old behaviour lethal: dropping node 2 left
    node 3 pointing at "2".
    """
    missing = {"id": 2, "type": "CR Text Concatenate", "inputs": [], "widgets_values": [],
               "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [1]}]}
    if properties:
        missing["properties"] = properties
    return _graph(
        [
            {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [],
             "widgets_values": ["a.safetensors"]},
            missing,
            {"id": 3, "type": "PreviewImage",
             "inputs": [{"name": "images", "type": "IMAGE", "link": 1}], "widgets_values": []},
        ],
        [[1, 2, 0, 3, 0, "IMAGE"]],
    )


def test_unresolvable_class_refuses_and_names_the_class():
    result = convert_ui_graph(_graph_with_missing_class(), SCHEMA)
    assert result.errors, "a conversion that could not resolve a class must say so"
    assert "CR Text Concatenate" in result.errors[0]
    assert result.missing_classes == ["CR Text Concatenate"]
    assert result.prompt == {}, "no partial graph escapes"


def test_the_refusal_records_the_dangling_link_it_would_have_emitted():
    """The evidence, not just the verdict: which input pointed where."""
    result = convert_ui_graph(_graph_with_missing_class(), SCHEMA)
    assert result.dangling_links == ["3.images -> 2"]


def test_message_names_the_pack_where_the_workflow_declares_one():
    """ComfyUI writes properties.cnr_id / aux_id / ver onto every node it saves.

    "install ComfyUI_Comfyroll_CustomNodes" ends the problem; "CR Text Concatenate is missing"
    starts a search. Measured over the imported library: 14 of the 20 refusing workflows name at
    least one pack this way, offline, with no Registry call.
    """
    graph = _graph_with_missing_class({
        "cnr_id": "ComfyUI_Comfyroll_CustomNodes",
        "aux_id": "Suzie1/ComfyUI_Comfyroll_CustomNodes",
        "ver": "d78b780ae43fcf8c6b7c6505e6ffb4584281ceca",
    })
    result = convert_ui_graph(graph, SCHEMA)
    assert result.errors
    message = result.errors[0]
    assert "ComfyUI_Comfyroll_CustomNodes" in message
    assert "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes" in message
    assert result.missing_packs == [{
        "pack": "ComfyUI_Comfyroll_CustomNodes",
        "repo_url": "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes",
        "version": "d78b780ae43fcf8c6b7c6505e6ffb4584281ceca",
        "classes": ["CR Text Concatenate"],
    }]


def test_undeclared_classes_are_named_bare_rather_than_guessed_at():
    """No pack declared -> say so. Ranking packs by name similarity resolved 0 of 16 when measured."""
    message = missing_class_message(_graph_with_missing_class(), ["CR Text Concatenate"])
    assert "CR Text Concatenate" in message
    assert "name no pack in the workflow file" in message
    assert missing_pack_entries(_graph_with_missing_class(), ["CR Text Concatenate"]) == []


def test_the_message_keeps_the_signature_flows_health_parses():
    """`docs/pipeline/comfy_baselines/flows_health.py` regexes this exact sentence.

    Changing it silently would break a reader rather than fix one, so the pack guidance is appended
    after it, never instead of it.
    """
    import re

    message = missing_class_message(_graph_with_missing_class(), ["CR Seed", "CR Text"])
    found = re.search(r"no schema for node class\(es\): (.+?)(?:\.\s|$)", message)
    assert found and found.group(1) == "CR Seed, CR Text"


def test_strict_mode_raises_the_same_refusal_for_the_submit_path():
    with pytest.raises(ValueError, match="CR Text Concatenate"):
        convert_ui_graph_to_api_prompt(_graph_with_missing_class(), SCHEMA)


# --------------------------------------------------------------------------------------------
# Task 1 -- the regression guard that matters most: a resolvable graph is untouched
# --------------------------------------------------------------------------------------------

def test_a_resolvable_graph_converts_exactly_as_before():
    """70 of the library's 90 UI graphs convert correctly today; none of them may move.

    Asserted as the whole prompt rather than a spot check, because a widget cursor that slips by one
    still passes every "is the key present" test.
    """
    graph = _graph(
        [
            {"id": 1, "type": "CheckpointLoaderSimple", "inputs": [],
             "widgets_values": ["a.safetensors"]},
            {"id": 2, "type": "CLIPTextEncode",
             "inputs": [{"name": "clip", "type": "CLIP", "link": 7}],
             "widgets_values": ["a cat"]},
        ],
        [[7, 1, 1, 2, 0, "CLIP"]],
    )
    result = convert_ui_graph(graph, SCHEMA)
    assert result.errors == []
    assert result.prompt == {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "a.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["1", 1]}},
    }
    assert result.node_count == 2


# --------------------------------------------------------------------------------------------
# Task 2 -- the structural post-condition
# --------------------------------------------------------------------------------------------

def test_is_link_matches_the_cores_own_definition():
    """Mirrors comfy_execution/graph_utils.py::is_link. If we disagree with the server about what a
    link is, the post-condition guards a different property than the one that matters."""
    assert is_link(["4", 0])
    assert is_link(["4", 0.0])
    assert not is_link([4, 0]), "the core requires a str source id"
    assert not is_link(["4", 0, 1])
    assert not is_link("4")
    assert not is_link(["4", True]), "a bool is not a slot index"


def test_post_condition_finds_a_dangling_link_in_a_synthetic_prompt():
    prompt = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "a.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "latent_image": ["99", 0]}},
    }
    dangling = find_dangling_links(prompt)
    assert [link.describe() for link in dangling] == ["2.latent_image -> 99"]


def test_post_condition_is_quiet_on_a_well_formed_prompt():
    prompt = {"1": {"class_type": "A", "inputs": {}},
              "2": {"class_type": "B", "inputs": {"x": ["1", 0], "text": "hello", "n": 4}}}
    assert find_dangling_links(prompt) == []
    assert_no_dangling_links(prompt)  # must not raise


def test_assert_no_dangling_links_names_the_referring_input():
    """"node 99 is missing" sends the reader nowhere; "2.latent_image -> 99" says which input broke."""
    prompt = {"2": {"class_type": "KSampler", "inputs": {"latent_image": ["99", 0]}}}
    with pytest.raises(ValueError) as caught:
        assert_no_dangling_links(prompt)
    assert "2.latent_image -> 99" in str(caught.value)


def test_a_dangling_link_with_nothing_missing_reads_as_our_bug():
    """The post-condition's real job: the NEXT cause, whatever it turns out to be.

    With no unresolvable class to blame, the refusal must not say "install a pack" -- it is a
    converter bug and has to read as one.
    """
    prompt = {"2": {"class_type": "KSampler", "inputs": {"latent_image": ["99", 0]}}}
    verdict = prompt_verdict(prompt, {"nodes": []}, [], {})
    assert len(verdict.errors) == 1
    assert "Internal error" in verdict.errors[0]
    assert "2.latent_image -> 99" in verdict.errors[0]
    assert "install" not in verdict.errors[0].lower()


# --------------------------------------------------------------------------------------------
# Task 3 -- widgets land in the inputs the schema names
#
# Both node fixtures are lifted verbatim from library graphs whose STORED prompt_api.json carries
# the wrong values: wan-2-2-smooth-workflow-img2vid-json node 50 (`batch_size: 480, length: 832`)
# and i2v-json node 305 (`batch_size: 480`). Those files were compiled by an older converter that
# did not advance the widget cursor past an input "converted to input"; the cursor then read one
# slot early for every later widget. The live converter is correct -- these tests are what keeps it
# correct, and what tells the next reader the bad numbers are stale artifacts, not a live bug.
# --------------------------------------------------------------------------------------------

def test_wan_image_to_video_widgets_land_in_the_right_inputs():
    node = {
        "id": 50, "type": "WanImageToVideo",
        "inputs": [
            {"name": "positive", "type": "CONDITIONING", "link": 166},
            {"name": "negative", "type": "CONDITIONING", "link": 98},
            {"name": "vae", "type": "VAE", "link": 99},
            {"name": "clip_vision_output", "type": "CLIP_VISION_OUTPUT", "link": None},
            {"name": "start_image", "type": "IMAGE", "link": 131},
            {"name": "width", "type": "INT", "widget": {"name": "width"}, "link": 132},
            {"name": "height", "type": "INT", "widget": {"name": "height"}, "link": 133},
            {"name": "length", "type": "INT", "widget": {"name": "length"}, "link": None},
            {"name": "batch_size", "type": "INT", "widget": {"name": "batch_size"}, "link": None},
        ],
        "widgets_values": [832, 480, 81, 1],
    }
    upstream = {"id": 64, "type": "PreviewImage",
                "inputs": [{"name": "images", "type": "IMAGE", "link": None}], "widgets_values": []}
    links = [[166, 64, 0, 50, 0, "CONDITIONING"], [98, 64, 0, 50, 1, "CONDITIONING"],
             [99, 64, 0, 50, 2, "VAE"], [131, 64, 0, 50, 4, "IMAGE"],
             [132, 64, 1, 50, 5, "INT"], [133, 64, 2, 50, 6, "INT"]]
    result = convert_ui_graph(_graph([upstream, node], links), SCHEMA)
    inputs = result.prompt["50"]["inputs"]
    assert inputs["width"] == ["64", 1]
    assert inputs["height"] == ["64", 2]
    assert inputs["length"] == 81, "a width must never land in `length`"
    assert inputs["batch_size"] == 1, "a height must never land in `batch_size`"


def test_empty_hunyuan_latent_video_widgets_land_in_the_right_inputs():
    node = {
        "id": 305, "type": "EmptyHunyuanLatentVideo",
        "inputs": [
            {"name": "width", "type": "INT", "widget": {"name": "width"}, "link": 1076},
            {"name": "height", "type": "INT", "widget": {"name": "height"}, "link": 1074},
            {"name": "length", "type": "INT", "widget": {"name": "length"}, "link": 1075},
            {"name": "batch_size", "type": "INT", "widget": {"name": "batch_size"}, "link": None},
        ],
        "widgets_values": [480, 832, 49, 1],
    }
    upstream = {"id": 528, "type": "PreviewImage",
                "inputs": [{"name": "images", "type": "IMAGE", "link": None}], "widgets_values": []}
    links = [[1076, 528, 0, 305, 0, "INT"], [1074, 528, 1, 305, 1, "INT"],
             [1075, 528, 2, 305, 2, "INT"]]
    result = convert_ui_graph(_graph([upstream, node], links), SCHEMA)
    inputs = result.prompt["305"]["inputs"]
    assert inputs["width"] == ["528", 0]
    assert inputs["height"] == ["528", 1]
    assert inputs["length"] == ["528", 2]
    assert inputs["batch_size"] == 1, "a width must never land in `batch_size`"
