"""A workflow names its own node packs; resolution must use that instead of guessing from class names.

ComfyUI stamps every saved node with `properties.cnr_id` / `aux_id` / `ver`. Measured on this
library: 431 non-core nodes carry all three, 257 carry cnr_id + ver, 14 carry aux_id + ver. Of the
40 classes that genuinely block a launch, 26 name their pack. So the class->pack problem the
6-entry starter catalog fuzzy-matches at (and got wrong 33 times on one workflow) is already
answered inside the file.

The load-bearing behaviours here:
  * an UNKNOWN licence must NOT block resolution -- kjnodes/VHS/rgthree/easy-use all publish
    `license: {"file": "LICENSE"}`, and those are the packs that unblock most workflows;
  * one install action per PACK, not per class;
  * a network failure is never cached as "pack does not exist";
  * nothing is guessed: a class with no declared identity is reported undeclared.
"""
from __future__ import annotations

import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
from node_dependency_resolver import build_node_install_plan  # noqa: E402
from workflow_pack_resolver import (  # noqa: E402
    ClassPackIndex,
    PackCache,
    PackDirectory,
    declared_packs,
    install_actions_for,
    package_name_for,
    resolve_declared_packs,
)
from workflow_scanner import WorkflowNodeInfo, WorkflowScanReport, WorkflowSource  # noqa: E402


def _node(class_type: str, *, cnr_id: str | None = None, aux_id: str | None = None,
          ver: str | None = None, node_id: str = "1") -> WorkflowNodeInfo:
    props: dict[str, str] = {}
    if cnr_id:
        props["cnr_id"] = cnr_id
    if aux_id:
        props["aux_id"] = aux_id
    if ver:
        props["ver"] = ver
    return WorkflowNodeInfo(node_id=node_id, class_type=class_type,
                            raw={"properties": props} if props else {})


KJ_DETAIL = {
    "id": "comfyui-kjnodes",
    "repository": "https://github.com/kijai/ComfyUI-KJNodes",
    "license": '{"file": "LICENSE"}',  # normalises to UNKNOWN -- the common real-world case
    "latest_version": {"version": "1.5.0", "dependencies": ["numba"]},
    "downloads": 4264624,
    "github_stars": 3178,
}


def _getter(details: dict[str, dict], calls: list[str] | None = None):
    def get(path: str, params=None, *, timeout: float = 20.0):
        if calls is not None:
            calls.append(path)
        pack_id = path.rsplit("/", 1)[-1]
        if pack_id in details:
            return details[pack_id]
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
    return get


# --- what the workflow declares -------------------------------------------------------------

def test_aux_id_resolves_with_no_network_at_all():
    """A github owner/repo needs no Registry call, and `ver` is a commit -- an exact pin."""
    nodes = [_node("ImageResizeKJv2", aux_id="kijai/ComfyUI-KJNodes",
                   ver="717092a3ceb51c474b5b3f77fc188979f0db9d67")]
    plan = resolve_declared_packs(nodes, ["ImageResizeKJv2"], offline=True)
    assert len(plan.resolutions) == 1
    res = plan.resolutions[0]
    assert res.status == "RESOLVED"
    assert res.repo_url == "https://github.com/kijai/ComfyUI-KJNodes"
    assert res.install_ref == "717092a3ceb51c474b5b3f77fc188979f0db9d67"
    assert res.ref_kind == "commit"
    assert plan.registry_consulted is False


def test_cnr_id_only_offline_is_unresolved_not_guessed():
    """Without the Registry there is no repo for a bare pack id. Say so; do not invent one."""
    nodes = [_node("SomeNode", cnr_id="comfyui-impact-pack", ver="8.25.1")]
    plan = resolve_declared_packs(nodes, ["SomeNode"], offline=True)
    assert plan.resolutions[0].status == "UNRESOLVED"
    assert plan.resolutions[0].repo_url is None
    assert plan.unresolved_classes == ["SomeNode"]


def test_cnr_id_resolves_through_the_registry():
    nodes = [_node("ImageResizeKJv2", cnr_id="comfyui-kjnodes", ver="1.4.0")]
    plan = resolve_declared_packs(nodes, ["ImageResizeKJv2"],
                                  getter=_getter({"comfyui-kjnodes": KJ_DETAIL}), cache=None)
    res = plan.resolutions[0]
    assert res.status == "RESOLVED"
    assert res.repo_url == "https://github.com/kijai/ComfyUI-KJNodes"
    assert res.downloads == 4264624
    assert res.py_deps == ["numba"]
    assert plan.registry_reachable is True


def test_unknown_licence_is_disclosed_not_a_blocker():
    """kjnodes/VHS/rgthree/easy-use all report UNKNOWN. Gating on it would make the feature useless."""
    nodes = [_node("ImageResizeKJv2", cnr_id="comfyui-kjnodes")]
    plan = resolve_declared_packs(nodes, ["ImageResizeKJv2"],
                                  getter=_getter({"comfyui-kjnodes": KJ_DETAIL}), cache=None)
    res = plan.resolutions[0]
    assert res.status == "RESOLVED", "an unknown licence must not stop resolution"
    assert res.license == "UNKNOWN"
    assert res.auto_installable is False, "carried for a future unattended toggle only"
    action = install_actions_for(plan)[0]
    assert action["license"] == "UNKNOWN"
    assert action["requires_confirmation"] is True


def test_declared_version_wins_over_the_registry_latest():
    """The pin is the revision that produced this graph, not whatever shipped since."""
    nodes = [_node("ImageResizeKJv2", cnr_id="comfyui-kjnodes", ver="1.4.0")]
    plan = resolve_declared_packs(nodes, ["ImageResizeKJv2"],
                                  getter=_getter({"comfyui-kjnodes": KJ_DETAIL}), cache=None)
    assert plan.resolutions[0].install_ref == "1.4.0"


def test_registry_latest_is_used_when_the_workflow_pins_nothing():
    nodes = [_node("ImageResizeKJv2", cnr_id="comfyui-kjnodes")]
    plan = resolve_declared_packs(nodes, ["ImageResizeKJv2"],
                                  getter=_getter({"comfyui-kjnodes": KJ_DETAIL}), cache=None)
    assert plan.resolutions[0].install_ref == "1.5.0"


def test_core_nodes_are_never_offered_as_a_pack():
    """A missing comfy-core class is a version problem; installing a pack cannot fix it."""
    nodes = [_node("ModelSamplingAuraFlow", cnr_id="comfy-core", ver="0.34.0")]
    plan = resolve_declared_packs(nodes, ["ModelSamplingAuraFlow"], offline=True)
    assert plan.resolutions == []
    assert plan.undeclared_classes == ["ModelSamplingAuraFlow"]


def test_classes_from_one_pack_produce_one_action():
    """The Retry-Dependencies failure mode was N installs of the same pack. One pack, one action."""
    nodes = [
        _node("A", aux_id="kijai/ComfyUI-KJNodes", ver="abc1234", node_id="1"),
        _node("B", aux_id="kijai/ComfyUI-KJNodes", ver="abc1234", node_id="2"),
        _node("C", aux_id="kijai/ComfyUI-KJNodes", ver="abc1234", node_id="3"),
    ]
    plan = resolve_declared_packs(nodes, ["A", "B", "C"], offline=True)
    assert len(plan.resolutions) == 1
    assert plan.resolutions[0].class_names == ["A", "B", "C"]
    assert len(install_actions_for(plan)) == 1


def test_undeclared_classes_are_reported_never_guessed():
    nodes = [_node("MysteryNode"), _node("ImageResizeKJv2", aux_id="kijai/ComfyUI-KJNodes")]
    plan = resolve_declared_packs(nodes, ["MysteryNode", "ImageResizeKJv2"], offline=True)
    assert plan.undeclared_classes == ["MysteryNode"]
    assert [r.class_names for r in plan.resolutions] == [["ImageResizeKJv2"]]


def test_aux_id_and_cnr_id_group_as_one_pack():
    """The same pack seen under both identities must not install twice."""
    nodes = [
        _node("A", cnr_id="comfyui-kjnodes", aux_id="kijai/ComfyUI-KJNodes", node_id="1"),
        _node("B", cnr_id="comfyui-kjnodes", aux_id="kijai/ComfyUI-KJNodes", node_id="2"),
    ]
    plan = resolve_declared_packs(nodes, ["A", "B"], offline=True)
    assert len(plan.resolutions) == 1


def test_one_pack_named_two_ways_merges_into_one_install():
    """Measured on Comfyroll: some nodes declared only cnr_id, others only aux_id, and the two are
    the same repo. Grouping happens before the Registry answers, so they only converge once both
    have a URL -- unmerged that is two clones into one directory."""
    detail = {"id": "ComfyUI_Comfyroll_CustomNodes",
              "repository": "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git",
              "license": "MIT", "latest_version": {"version": "1.76"},
              "downloads": 10, "github_stars": 1300}
    nodes = [
        _node("CR Text", cnr_id="ComfyUI_Comfyroll_CustomNodes", node_id="1"),
        _node("CR Image", aux_id="Suzie1/ComfyUI_Comfyroll_CustomNodes", ver="deadbee", node_id="2"),
    ]
    plan = resolve_declared_packs(
        nodes, ["CR Text", "CR Image"],
        getter=_getter({"ComfyUI_Comfyroll_CustomNodes": detail}), cache=None)
    assert len(plan.resolutions) == 1, "same repo, one install"
    res = plan.resolutions[0]
    assert res.class_names == ["CR Image", "CR Text"]
    assert res.license == "MIT", "the confirmed licence survives the merge"
    assert res.ref_kind == "commit" and res.install_ref == "deadbee", "the precise pin wins"


def test_package_name_comes_from_the_repo_not_the_registry_id():
    """The install lands in custom_nodes/<repo name>; matching the Registry id would miss it."""
    nodes = [_node("A", cnr_id="comfyui-kjnodes", aux_id="kijai/ComfyUI-KJNodes")]
    plan = resolve_declared_packs(nodes, ["A"], offline=True)
    assert package_name_for(plan.resolutions[0]) == "ComfyUI-KJNodes"


# --- cache ------------------------------------------------------------------------------------

def test_registry_answers_are_cached_to_disk(tmp_path):
    calls: list[str] = []
    getter = _getter({"comfyui-kjnodes": KJ_DETAIL}, calls)
    cache_file = tmp_path / "packs.json"
    nodes = [_node("A", cnr_id="comfyui-kjnodes")]

    resolve_declared_packs(nodes, ["A"], getter=getter, cache_path=cache_file)
    assert len(calls) == 1
    assert cache_file.is_file()

    resolve_declared_packs(nodes, ["A"], getter=getter, cache_path=cache_file)
    assert len(calls) == 1, "second resolve must be served from disk"


def test_a_404_is_cached_but_a_network_failure_is_not(tmp_path):
    """"No such pack" is an answer worth remembering. "Could not reach the Registry" is not --
    caching it would make one offline moment look like a missing pack for a day."""
    cache_file = tmp_path / "packs.json"

    calls: list[str] = []
    resolve_declared_packs([_node("A", cnr_id="ghost-pack")], ["A"],
                           getter=_getter({}, calls), cache_path=cache_file)
    resolve_declared_packs([_node("A", cnr_id="ghost-pack")], ["A"],
                           getter=_getter({}, calls), cache_path=cache_file)
    assert len(calls) == 1, "a 404 is cached"

    def exploding(path, params=None, *, timeout=20.0):
        raise urllib.error.URLError("connection refused")

    plan = resolve_declared_packs([_node("B", cnr_id="offline-pack")], ["B"],
                                  getter=exploding, cache_path=cache_file)
    assert plan.registry_reachable is False
    cache = PackCache(cache_file)
    assert cache.get("offline-pack") is None, "an unreachable Registry must not be cached as a miss"
    assert cache.get("ghost-pack") is not None


def test_a_corrupt_cache_file_is_ignored_not_fatal(tmp_path):
    cache_file = tmp_path / "packs.json"
    cache_file.write_text("{not json", encoding="utf-8")
    plan = resolve_declared_packs([_node("A", cnr_id="comfyui-kjnodes")], ["A"],
                                  getter=_getter({"comfyui-kjnodes": KJ_DETAIL}), cache_path=cache_file)
    assert plan.resolutions[0].status == "RESOLVED"


# --- grouping helper --------------------------------------------------------------------------

def test_declared_packs_ignores_classes_the_caller_did_not_ask_about():
    nodes = [_node("Wanted", aux_id="a/b"), _node("Ignored", aux_id="c/d")]
    packs, undeclared = declared_packs(nodes, ["Wanted"])
    assert [p.key for p in packs] == ["a/b"]
    assert undeclared == []


# --- tier 3: the reverse index ------------------------------------------------------------------

DIRECTORY_PAGE = {
    "totalPages": 1,
    "total": 2,
    "nodes": [
        {"id": "comfyui-kjnodes", "name": "KJNodes", "repository": "https://github.com/kijai/ComfyUI-KJNodes",
         "license": "GPL-3.0", "downloads": 4264624, "github_stars": 3178,
         "latest_version": {"version": "1.5.0", "dependencies": []}},
        {"id": "tiny-pack", "name": "Tiny", "repository": "https://github.com/x/tiny",
         "license": "MIT", "downloads": 3, "github_stars": 0,
         "latest_version": {"version": "0.1.0", "dependencies": []}},
    ],
}

PACK_CLASSES = {
    "comfyui-kjnodes": ["SetNode", "GetNode", "ImageResizeKJv2"],
    "tiny-pack": ["SetNode"],
}


def _directory_getter(calls: list[str] | None = None):
    """Serves the pack list and each pack's class list, the way the Registry does."""
    def get(path: str, params=None, *, timeout: float = 20.0):
        if calls is not None:
            calls.append(path)
        if path == "/nodes":
            return DIRECTORY_PAGE
        if path.endswith("/comfy-nodes"):
            pack_id = path.split("/")[2]
            return {"comfy_nodes": [{"comfy_node_name": c} for c in PACK_CLASSES.get(pack_id, [])]}
        raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
    return get


def _built_index(tmp_path):
    directory = PackDirectory(tmp_path / "dir.json")
    assert directory.ensure(getter=_directory_getter())
    index = ClassPackIndex(tmp_path / "index.json")
    index.build(directory, getter=_directory_getter(), workers=2)
    return index


def test_the_index_answers_a_class_no_workflow_declared(tmp_path):
    """SetNode/GetNode/LoadImageBatch/CR Upscale Image share no tokens with the packs that publish
    them -- a name heuristic resolved 0 of 16 here. Only the reverse index gets them."""
    index = _built_index(tmp_path)
    plan = resolve_declared_packs([_node("SetNode")], ["SetNode"],
                                  getter=_directory_getter(), search_undeclared=True,
                                  index=index, cache=None)
    assert plan.undeclared_classes == []
    res = plan.resolutions[0]
    assert res.source == "registry_class_search"
    assert res.pack_id == "comfyui-kjnodes", "the more-used pack wins when several publish the class"
    assert res.license == "GPL-3.0", "copyleft is disclosed, not hidden"


def test_no_index_means_undeclared_not_silently_nothing(tmp_path):
    """The dangerous shape is an empty plan that reads as 'nothing to install'."""
    plan = resolve_declared_packs([_node("SetNode")], ["SetNode"],
                                  search_undeclared=True, index_path=tmp_path / "missing.json",
                                  cache=None, offline=True)
    assert plan.undeclared_classes == ["SetNode"]
    assert plan.index_available is False
    assert plan.to_dict()["index_available"] is False


def test_index_build_is_resumable(tmp_path):
    directory = PackDirectory(tmp_path / "dir.json")
    directory.ensure(getter=_directory_getter())
    index = ClassPackIndex(tmp_path / "index.json")
    index.build(directory, getter=_directory_getter(), workers=1)
    assert index.complete is True

    calls: list[str] = []
    reopened = ClassPackIndex(tmp_path / "index.json")
    assert reopened.classes, "the index survives a restart"
    reopened.build(directory, getter=_directory_getter(calls), workers=1)
    assert [c for c in calls if c.endswith("/comfy-nodes")] == [], "already-indexed packs are not refetched"


def test_index_lookup_needs_no_network(tmp_path):
    index = _built_index(tmp_path)

    def exploding(path, params=None, *, timeout=20.0):
        raise AssertionError("tier 3 must be a pure lookup")

    plan = resolve_declared_packs([_node("GetNode")], ["GetNode"], getter=exploding,
                                  search_undeclared=True, index=index, cache=None, offline=True)
    assert plan.resolutions[0].pack_id == "comfyui-kjnodes"


# --- the install plan -------------------------------------------------------------------------

def _report(nodes, missing):
    return WorkflowScanReport(
        report_id="test",
        source=WorkflowSource(source_kind="test", display_name="test"),
        graph_format="comfy_ui_graph",
        node_count=len(nodes),
        nodes=list(nodes),
        missing_custom_nodes=list(missing),
        inferred_model_family_hints=["flux"],
    )


GREEDY_ENTRY = {
    "package_name": "ComfyUI-TeaCache",
    "install_method": "manager",
    "repo_url": "https://example.invalid/teacache.git",
    "class_name_patterns": ["teacache"],
    "aliases": ["teacache"],
    "model_families": ["wan", "ltx", "hunyuan_video", "cogvideox", "flux"],
}


def test_plan_prefers_the_declaration_over_a_catalog_guess(tmp_path):
    nodes = [
        _node("ImageResizeKJv2", aux_id="kijai/ComfyUI-KJNodes", ver="abc1234", node_id="1"),
        _node("GetImageSizeKJ", aux_id="kijai/ComfyUI-KJNodes", ver="abc1234", node_id="2"),
    ]
    plan = build_node_install_plan(
        _report(nodes, ["ImageResizeKJv2", "GetImageSizeKJ"]),
        comfy_root=tmp_path,
        node_catalog={"packages": [GREEDY_ENTRY]},
        registry_offline=True,
    )
    assert {d.resolved_package for d in plan.dependencies} == {"ComfyUI-KJNodes"}
    assert all(d.source == "workflow_aux_id" for d in plan.dependencies)
    assert all(d.confidence == 1.0 for d in plan.dependencies)
    assert len(plan.install_actions) == 1, "two classes, one pack, one install"
    assert plan.install_actions[0]["install_ref"] == "abc1234"
    assert plan.unresolved_classes == []


def test_plan_falls_back_to_the_catalog_for_undeclared_classes(tmp_path):
    nodes = [_node("TeaCacheForImgGen")]
    plan = build_node_install_plan(
        _report(nodes, ["TeaCacheForImgGen"]),
        comfy_root=tmp_path,
        node_catalog={"packages": [GREEDY_ENTRY]},
        registry_offline=True,
    )
    assert plan.dependencies[0].resolved_package == "ComfyUI-TeaCache"
    assert plan.dependencies[0].source == "starter_catalog"


def test_plan_still_refuses_to_guess_an_undeclared_unrelated_class(tmp_path):
    """The TeaCache regression, now through the whole plan: no declaration, no name match, no install."""
    nodes = [_node("UltralyticsDetectorProvider")]
    plan = build_node_install_plan(
        _report(nodes, ["UltralyticsDetectorProvider"]),
        comfy_root=tmp_path,
        node_catalog={"packages": [GREEDY_ENTRY]},
        registry_offline=True,
    )
    assert plan.install_actions == []
    assert plan.unresolved_classes == ["UltralyticsDetectorProvider"]


def test_plan_carries_the_pack_report_for_the_ui(tmp_path):
    nodes = [_node("A", aux_id="kijai/ComfyUI-KJNodes"), _node("Mystery", node_id="2")]
    plan = build_node_install_plan(
        _report(nodes, ["A", "Mystery"]),
        comfy_root=tmp_path,
        node_catalog={"packages": []},
        registry_offline=True,
    )
    assert plan.pack_plan is not None
    assert plan.pack_plan["undeclared_classes"] == ["Mystery"]
    assert plan.pack_plan["counts"]["classes_covered"] == 1


# --- tier 3 must also rescue a FAILED declaration, not only an undeclared class ---------------


def test_the_index_rescues_a_class_whose_declaration_failed_to_resolve():
    """Measured gap: the index contained VHS_VideoCombine, SAMLoader, "easy boolean" and
    "Pick From Batch (mtb)" while the plan reported all of them unknown -- because each was
    DECLARED and its declaration had failed, and tier 3 only ever looked at undeclared classes.
    Withholding the strongest evidence from the classes that most need it."""
    import time

    from workflow_pack_resolver import ClassPackIndex, resolve_declared_packs
    from workflow_scanner import WorkflowNodeInfo

    # A node that declares a cnr_id we cannot resolve offline.
    node = WorkflowNodeInfo(
        node_id="1", class_type="VHS_VideoCombine",
        raw={"type": "VHS_VideoCombine", "properties": {"cnr_id": "comfyui-videohelpersuite"}},
    )

    index = ClassPackIndex.__new__(ClassPackIndex)
    index.classes = {"VHS_VideoCombine": {
        "pack_id": "comfyui-videohelpersuite",
        "repo_url": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
        "version": "1.0.0", "license": "GPL-3.0", "downloads": 100,
    }}
    index.packs_done = {"x"}
    index.complete = True
    index.path = "<memory>"
    index.fetched_at = time.time()
    index.ttl = 10_000

    plan = resolve_declared_packs([node], ["VHS_VideoCombine"], offline=True,
                                  search_undeclared=True, index=index)

    assert "VHS_VideoCombine" not in plan.unresolved_classes, (
        "a class the index answered must not be reported unresolved because another tier missed"
    )
    assert any("videohelpersuite" in (r.pack_id or "").lower() for r in plan.resolved())


def test_a_class_no_tier_can_answer_is_still_reported_unresolved():
    import time

    from workflow_pack_resolver import ClassPackIndex, resolve_declared_packs
    from workflow_scanner import WorkflowNodeInfo

    node = WorkflowNodeInfo(node_id="1", class_type="TotallyUnknownNode",
                            raw={"type": "TotallyUnknownNode", "properties": {"cnr_id": "nope"}})
    index = ClassPackIndex.__new__(ClassPackIndex)
    index.classes = {}
    index.packs_done = {"x"}
    index.complete = True
    index.path = "<memory>"
    index.fetched_at = time.time()
    index.ttl = 10_000

    plan = resolve_declared_packs([node], ["TotallyUnknownNode"], offline=True,
                                  search_undeclared=True, index=index)
    assert "TotallyUnknownNode" in plan.unresolved_classes
