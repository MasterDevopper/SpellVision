"""Applying a chosen substitute to the graph, and refusing to launch when it did not apply."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from comfy_prompt_client import apply_model_substitutions  # noqa: E402


def graph(*nodes):
    return {str(i + 1): n for i, n in enumerate(nodes)}


def node(class_type, **inputs):
    return {"class_type": class_type, "inputs": inputs}


def test_a_chosen_substitute_replaces_the_named_model():
    g = graph(node("CheckpointLoaderSimple", ckpt_name="prefectIllustriousXL_40.safetensors"))
    applied = apply_model_substitutions(
        g, {"prefectIllustriousXL_40.safetensors": "sdxl/hassakuXLIllustrious_v34.safetensors"}
    )
    assert g["1"]["inputs"]["ckpt_name"] == "sdxl/hassakuXLIllustrious_v34.safetensors"
    assert applied == [{
        "node_id": "1", "input": "ckpt_name",
        "wanted": "prefectIllustriousXL_40.safetensors",
        "used": "sdxl/hassakuXLIllustrious_v34.safetensors",
    }]


def test_matching_ignores_separator_and_case():
    """The graph may bake sdxl/foo while the catalog says sdxl\\foo. Matching the raw string means
    the substitution silently fails and the launch quietly uses the model being replaced."""
    g = graph(node("CheckpointLoaderSimple", ckpt_name="SDXL\\Foo.safetensors"))
    applied = apply_model_substitutions(g, {"sdxl/foo.safetensors": "sdxl/bar.safetensors"})
    assert applied
    assert g["1"]["inputs"]["ckpt_name"] == "sdxl/bar.safetensors"


def test_every_occurrence_is_replaced_across_nodes_and_input_names():
    g = graph(
        node("CheckpointLoaderSimple", ckpt_name="a.safetensors"),
        node("UNETLoader", unet_name="a.safetensors"),
        node("CheckpointLoaderSimple", ckpt_name="other.safetensors"),
    )
    applied = apply_model_substitutions(g, {"a.safetensors": "b.safetensors"})
    assert len(applied) == 2
    assert g["1"]["inputs"]["ckpt_name"] == "b.safetensors"
    assert g["2"]["inputs"]["unet_name"] == "b.safetensors"
    assert g["3"]["inputs"]["ckpt_name"] == "other.safetensors", "untouched models stay untouched"


def test_a_substitution_that_matches_nothing_reports_nothing_applied():
    """The caller turns this into a refusal to launch. Silently proceeding would run the graph
    still referencing a model the user just said they do not have."""
    g = graph(node("CheckpointLoaderSimple", ckpt_name="a.safetensors"))
    assert apply_model_substitutions(g, {"absent.safetensors": "b.safetensors"}) == []
    assert g["1"]["inputs"]["ckpt_name"] == "a.safetensors"


def test_non_model_inputs_are_never_touched():
    g = graph(node("CLIPTextEncode", text="a.safetensors"),
              node("EmptyLatentImage", width=1024, height=1024))
    assert apply_model_substitutions(g, {"a.safetensors": "b.safetensors"}) == []
    assert g["1"]["inputs"]["text"] == "a.safetensors"


def test_empty_or_missing_substitutions_are_a_no_op():
    g = graph(node("CheckpointLoaderSimple", ckpt_name="a.safetensors"))
    assert apply_model_substitutions(g, None) == []
    assert apply_model_substitutions(g, {}) == []
    assert apply_model_substitutions(g, {"": "b.safetensors"}) == []
    assert apply_model_substitutions(g, {"a.safetensors": ""}) == []
    assert g["1"]["inputs"]["ckpt_name"] == "a.safetensors"


def test_substituting_a_model_for_itself_is_not_reported_as_a_change():
    g = graph(node("CheckpointLoaderSimple", ckpt_name="a.safetensors"))
    assert apply_model_substitutions(g, {"a.safetensors": "a.safetensors"}) == []


def test_a_malformed_graph_does_not_raise():
    g = {"1": "not a node", "2": {"class_type": "X"}, "3": {"class_type": "Y", "inputs": "nope"}}
    assert apply_model_substitutions(g, {"a.safetensors": "b.safetensors"}) == []
