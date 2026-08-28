"""The resolve_missing_models command: catalog sources, graph sources, and the stale-artifact guard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_resolution_commands import (  # noqa: E402
    _load_graph,
    _loaders_have_inputs,
    installed_from_disk,
    installed_from_disk_all,
    installed_from_object_info,
)


def api_graph(*nodes):
    return {str(i): n for i, n in enumerate(nodes)}


def node(class_type, **inputs):
    return {"class_type": class_type, "inputs": inputs}


# --- catalog sources ------------------------------------------------------------------------


def test_object_info_catalog_reads_every_model_loader():
    object_info = {
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["sdxl/a.safetensors",
                                                                        "sd15/b.safetensors"]]}}},
        "UNETLoader": {"input": {"required": {"unet_name": [["wan/c.safetensors"]]}}},
    }
    assert installed_from_object_info(object_info) == [
        "sd15/b.safetensors", "sdxl/a.safetensors", "wan/c.safetensors"
    ]


def test_object_info_catalog_tolerates_a_missing_or_odd_loader():
    assert installed_from_object_info({}) == []
    assert installed_from_object_info({"CheckpointLoaderSimple": {"input": {"required": {}}}}) == []


def test_disk_catalog_returns_paths_relative_to_the_category_root(tmp_path):
    """Relative, not basename: the architecture lives in the leading folder, and a basename
    throws it away -- which is what left the classifier with nothing to go on."""
    root = tmp_path / "models" / "checkpoints"
    (root / "sdxl").mkdir(parents=True)
    (root / "sdxl" / "a.safetensors").write_bytes(b"x")
    (root / "loose.ckpt").write_bytes(b"x")
    (root / "sdxl" / "notes.txt").write_text("ignored")

    names = installed_from_disk(tmp_path, use_cache=False)
    assert names == ["loose.ckpt", "sdxl/a.safetensors"], "non-weight files must not appear"


def test_disk_catalog_of_a_missing_root_is_empty_not_an_error(tmp_path):
    assert installed_from_disk(tmp_path / "nope", use_cache=False) == []


def test_the_catalog_spans_every_loader_category_not_just_checkpoints(tmp_path):
    """Wan and Hunyuan ship as diffusion models. A checkpoints-only scan reported 'nothing on
    disk to offer' for every video workflow while 30 compatible files sat one folder over --
    and it showed up as an empty result, never as an error."""
    models = tmp_path / "models"
    (models / "checkpoints" / "sdxl").mkdir(parents=True)
    (models / "checkpoints" / "sdxl" / "a.safetensors").write_bytes(b"x")
    (models / "diffusion_models" / "wan").mkdir(parents=True)
    (models / "diffusion_models" / "wan" / "b.safetensors").write_bytes(b"x")
    (models / "unet").mkdir(parents=True)
    (models / "unet" / "c.safetensors").write_bytes(b"x")

    assert installed_from_disk(tmp_path, "checkpoints", use_cache=False) == ["sdxl/a.safetensors"]
    assert installed_from_disk_all(tmp_path) == [
        "c.safetensors", "sdxl/a.safetensors", "wan/b.safetensors"
    ]


# --- the stale-artifact guard ---------------------------------------------------------------


def test_a_loader_with_no_inputs_marks_the_graph_unreadable():
    """The dangerous case: a graph whose loaders lost their widget values binds no model names,
    so 'what is missing?' answers *none* and the user is told everything is fine."""
    assert _loaders_have_inputs(api_graph(node("CheckpointLoaderSimple", ckpt_name="a.safetensors")))
    stripped = api_graph({"class_type": "UNETLoader", "inputs": {}})
    assert not _loaders_have_inputs(stripped)


def test_a_graph_with_no_model_loaders_is_not_treated_as_stale():
    assert _loaders_have_inputs(api_graph(node("SaveImage")))


def test_the_cached_compile_is_used_when_comfy_is_unreachable(tmp_path):
    ui_graph = {"nodes": [{"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["a.safetensors"]}],
                "links": []}
    (tmp_path / "workflow.json").write_text(json.dumps(ui_graph), encoding="utf-8")
    (tmp_path / "prompt_api.json").write_text(
        json.dumps(api_graph(node("CheckpointLoaderSimple", ckpt_name="sdxl/a.safetensors"))),
        encoding="utf-8",
    )

    graph, source = _load_graph(tmp_path, object_info=None)
    assert graph is not None
    assert "prompt_api.json" in source
    assert "ComfyUI was unreachable" in source


def test_a_stale_cached_compile_reports_unreadable_rather_than_empty(tmp_path):
    ui_graph = {"nodes": [{"id": 1, "type": "UNETLoader", "widgets_values": ["a.safetensors"]}], "links": []}
    (tmp_path / "workflow.json").write_text(json.dumps(ui_graph), encoding="utf-8")
    (tmp_path / "prompt_api.json").write_text(
        json.dumps({"1": {"class_type": "UNETLoader", "inputs": {}}}), encoding="utf-8"
    )

    graph, source = _load_graph(tmp_path, object_info=None)
    assert graph is None, "an unreadable artifact must not answer 'nothing is missing'"
    assert "stale" in source


def test_an_api_shaped_workflow_needs_no_object_info(tmp_path):
    (tmp_path / "workflow.json").write_text(
        json.dumps(api_graph(node("CheckpointLoaderSimple", ckpt_name="sdxl/a.safetensors"))),
        encoding="utf-8",
    )
    graph, source = _load_graph(tmp_path, object_info=None)
    assert graph is not None
    assert source == "workflow.json"


def test_nothing_readable_says_so(tmp_path):
    graph, source = _load_graph(tmp_path, object_info=None)
    assert graph is None
    assert source == "no readable graph"
