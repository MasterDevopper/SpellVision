"""A workflow can name an exact download URL for a model; that beats every other tier.

ComfyUI writes properties.models = [{name, url, directory}] onto loader nodes saved from a template
or shared through the Manager. Measured here: 7 of 80 workflows, 20 declarations, all three fields
present on every one. Coverage is modest, but where it exists nothing about the answer is inferred,
so it goes ahead of hash lookup, name search and any substitution.

Also pinned here: a bare "foo.safetensors" out of a workflow is a model NAME, not a path.
parse_asset_reference classified it as local_file with an absolute path to a file that does not
exist, so install_action could only ever be "review" -- a permanent dead end for the single most
common way a workflow names a model.

The declaration is untrusted input from a downloaded file, so the URL must be https and the
destination must be one plain path component.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from model_dependency_resolver import build_model_install_plan  # noqa: E402
from model_sources import parse_asset_reference  # noqa: E402
from workflow_model_declarations import declaration_for, declared_models  # noqa: E402
from workflow_scanner import (  # noqa: E402
    ModelReference,
    WorkflowNodeInfo,
    WorkflowScanReport,
    WorkflowSource,
)

WAN_VAE = {"name": "wan_2.1_vae.safetensors",
           "url": "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
           "directory": "vae"}


def _node(class_type: str, models: list[dict] | None = None, node_id: str = "1") -> WorkflowNodeInfo:
    raw: dict = {}
    if models is not None:
        raw["properties"] = {"models": models}
    return WorkflowNodeInfo(node_id=node_id, class_type=class_type, raw=raw)


def _report(nodes, refs):
    return WorkflowScanReport(
        report_id="test",
        source=WorkflowSource(source_kind="test", display_name="test"),
        graph_format="comfy_ui_graph",
        node_count=len(nodes),
        nodes=list(nodes),
        model_references=list(refs),
    )


def _ref(value, kind="vae", node_id="1"):
    return ModelReference(kind=kind, value=value, node_id=node_id, input_name="vae_name")


# --- extraction ----------------------------------------------------------------------------------

def test_a_declaration_is_read_off_the_loader_node():
    decls = declared_models([_node("VAELoader", [WAN_VAE])])
    assert decls["wan_2.1_vae.safetensors"].url == WAN_VAE["url"]
    assert decls["wan_2.1_vae.safetensors"].directory == "vae"


def test_one_file_declared_by_several_nodes_merges():
    decls = declared_models([_node("VAELoader", [WAN_VAE], "1"), _node("VAELoader", [WAN_VAE], "7")])
    assert list(decls) == ["wan_2.1_vae.safetensors"]
    assert decls["wan_2.1_vae.safetensors"].node_ids == ["1", "7"]


def test_a_subfolder_reference_still_finds_its_declaration():
    """Comfy allows 'ltx/foo.safetensors' as a widget value; the declaration keys on the filename."""
    decls = declared_models([_node("VAELoader", [WAN_VAE])])
    assert declaration_for(decls, "wan/wan_2.1_vae.safetensors") is not None
    assert declaration_for(decls, "other.safetensors") is None


def test_a_non_https_url_is_refused():
    """This URL is handed to a downloader, and a workflow is a file off the internet."""
    bad = {**WAN_VAE, "url": "http://example.invalid/model.safetensors"}
    assert declared_models([_node("VAELoader", [bad])]) == {}
    worse = {**WAN_VAE, "url": "file:///C:/Windows/System32/config/SAM"}
    assert declared_models([_node("VAELoader", [worse])]) == {}


def test_a_traversing_directory_is_dropped_but_the_url_is_kept():
    """The directory builds a filesystem path, so it must be one plain component."""
    evil = {**WAN_VAE, "directory": "../../../Windows"}
    decls = declared_models([_node("VAELoader", [evil])])
    assert decls["wan_2.1_vae.safetensors"].directory is None


def test_malformed_entries_are_skipped_not_fatal():
    decls = declared_models([_node("VAELoader", ["not a dict", {}, {"name": "x.safetensors"}, WAN_VAE])])
    assert list(decls) == ["wan_2.1_vae.safetensors"]


# --- the reference parser ---------------------------------------------------------------------

def test_a_bare_filename_is_a_model_name_not_a_missing_local_file():
    ref = parse_asset_reference("juggernautXL_v9.safetensors")
    assert ref.kind == "model_name"
    assert ref.filename == "juggernautXL_v9.safetensors"


def test_a_real_local_file_is_still_a_local_file(tmp_path):
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"x")
    assert parse_asset_reference(str(path)).kind == "local_file"


def test_a_path_with_a_directory_is_still_treated_as_a_path():
    assert parse_asset_reference("C:/models/checkpoints/model.safetensors").kind == "local_file"


# --- the plan ------------------------------------------------------------------------------------

def test_a_declared_model_becomes_a_download_not_a_review(tmp_path):
    plan = build_model_install_plan(
        _report([_node("VAELoader", [WAN_VAE])], [_ref("wan_2.1_vae.safetensors")]),
        comfy_root=tmp_path,
    )
    dep = plan.dependencies[0]
    assert dep.install_action == "download_declared"
    assert dep.resolved_source_kind == "workflow_declared_url"
    assert dep.materialized["url"] == WAN_VAE["url"]
    assert dep.destination_path.endswith(os.path.join("vae", "wan_2.1_vae.safetensors"))


def test_the_declared_directory_beats_the_class_derived_one(tmp_path):
    """A CLIPLoader declaring text_encoders must not land in models/clip."""
    decl = {"name": "umt5_xxl.safetensors", "url": "https://huggingface.co/x/y/resolve/main/umt5_xxl.safetensors",
            "directory": "text_encoders"}
    plan = build_model_install_plan(
        _report([_node("CLIPLoader", [decl])], [_ref("umt5_xxl.safetensors", kind="clip")]),
        comfy_root=tmp_path,
    )
    assert plan.dependencies[0].comfy_subdir == "text_encoders"


def test_a_model_already_on_disk_is_never_re_downloaded(tmp_path):
    present = tmp_path / "models" / "vae"
    present.mkdir(parents=True)
    (present / "wan_2.1_vae.safetensors").write_bytes(b"x")
    plan = build_model_install_plan(
        _report([_node("VAELoader", [WAN_VAE])], [_ref("wan_2.1_vae.safetensors")]),
        comfy_root=tmp_path,
    )
    assert plan.dependencies[0].install_action == "already_present"


def test_an_undeclared_bare_name_is_reported_honestly(tmp_path):
    plan = build_model_install_plan(
        _report([_node("VAELoader")], [_ref("mystery.safetensors")]),
        comfy_root=tmp_path,
    )
    dep = plan.dependencies[0]
    assert dep.install_action == "review"
    assert dep.resolved_source_kind == "model_name"
    assert "no source" in " ".join(dep.notes)
    assert dep.destination_path is None, "no path is claimed for a file with no source"


# --- a declaration that no longer matches what the node binds -------------------------------


def _declaring_node(node_id, class_type, declared, bound_widgets):
    from workflow_scanner import WorkflowNodeInfo

    return WorkflowNodeInfo(
        node_id=node_id, class_type=class_type,
        raw={"properties": {"models": [{"name": declared, "url": "https://huggingface.co/a/b/c.safetensors"}]},
             "widgets_values": bound_widgets},
    )


def test_a_declaration_that_names_a_different_file_is_reported():
    """Authors start from a template and swap models; properties.models is written when a model is
    ADDED and never rewritten when the widget changes. Real case from a Krea 2 workflow: the
    UNETLoader declared z_image_turbo_bf16.safetensors and its HuggingFace URL while binding
    "Lox's Utopic World Krea V1 bf16.safetensors" -- a leftover pointing at a different model."""
    from workflow_model_declarations import stale_declarations

    findings = stale_declarations([
        _declaring_node("761", "UNETLoader", "z_image_turbo_bf16.safetensors",
              ["Lox's Utopic World Krea V1 bf16.safetensors", "default"]),
    ])
    assert len(findings) == 1
    assert findings[0]["declared"] == "z_image_turbo_bf16.safetensors"
    assert "Lox's Utopic World" in findings[0]["bound"]
    assert findings[0]["node_id"] == "761"


def test_a_declaration_matching_the_bound_value_is_not_reported():
    from workflow_model_declarations import stale_declarations

    assert stale_declarations([
        _declaring_node("1", "VAELoader", "ae.safetensors", ["ae.safetensors"]),
    ]) == []


def test_a_subfolder_prefix_on_the_bound_value_still_matches():
    from workflow_model_declarations import stale_declarations

    assert stale_declarations([
        _declaring_node("1", "VAELoader", "ae.safetensors", ["flux/ae.safetensors"]),
    ]) == []


def test_a_node_with_nothing_bound_is_not_accused():
    """Silence beats a false accusation when there is nothing to compare against."""
    from workflow_model_declarations import stale_declarations
    from workflow_scanner import WorkflowNodeInfo

    node = WorkflowNodeInfo(node_id="1", class_type="VAELoader",
                            raw={"properties": {"models": [{"name": "ae.safetensors",
                                                            "url": "https://huggingface.co/a/b"}]}})
    assert stale_declarations([node]) == []


# --- presence must respect a folder the reference names -------------------------------------


def test_a_folder_qualified_reference_is_not_satisfied_by_a_file_elsewhere(tmp_path):
    """_model_present fell back to "this basename exists SOMEWHERE under a model root", ignoring
    kind, subdir and size. Any ae.safetensors then marked a VAE present, and the launch path's own
    basename fallback bound and executed it. Generic names make that likely, not exotic:
    ae.safetensors, clip_l.safetensors and model.safetensors all appear under several
    architectures.

    A reference that names a folder is ASSERTING where the file lives, so a match elsewhere is a
    different file."""
    from model_dependency_resolver import _model_present

    roots = {}
    models_root = tmp_path / "models"
    (models_root / "vae").mkdir(parents=True)
    (models_root / "vae" / "ae.safetensors").write_bytes(b"x")
    all_basenames = {"ae.safetensors"}

    # Bare name: the fallback is still allowed and still useful.
    assert _model_present("ae.safetensors", "vae", roots, models_root, all_basenames)

    # Folder-qualified and NOT present at that path -> missing, even though the basename exists.
    assert not _model_present("flux/ae.safetensors", "vae", roots, models_root, all_basenames)


def test_a_folder_qualified_reference_that_is_where_it_says_it_is_still_resolves(tmp_path):
    from model_dependency_resolver import _model_present

    models_root = tmp_path / "models"
    (models_root / "vae" / "flux").mkdir(parents=True)
    (models_root / "vae" / "flux" / "ae.safetensors").write_bytes(b"x")
    assert _model_present("flux/ae.safetensors", "vae", {}, models_root, {"ae.safetensors"})
