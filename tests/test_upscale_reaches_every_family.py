"""An upscale a family cannot receive is a control that lies, and it lies quietly.

This module holds the upscale route to a property of the TREE rather than of the families somebody
remembered: **every graph a native builder produces must have an image sink the graft can reach.**

The history is the argument. `graft_pixel_upscale` searched for the literal string `"SaveImage"`.
Every native VIDEO family ends `...VAEDecode -> CreateVideo(images) -> SaveVideo`, so the search
found nothing, and the graft returned the graph untouched -- no upscale, and no complaint. That is
the same failure as the one recorded in `upscale_engine`'s own docstring, at a different site, which
is Doc 50 rule 10 exactly: a rule applied where the defect was found and nowhere else.

Two checks, deliberately of different kinds:

* **Hermetic** -- every terminal node class the video builders can select is either in `IMAGE_SINKS`
  or is a class that does not consume an IMAGE at all (`SaveVideo` takes VIDEO; the picture reaches
  it through `CreateVideo`). Ground truth is the pinned node contract, so this runs with ComfyUI
  down and in CI.
* **Live** (`needs_comfy`) -- each native video family's graph is built through the shipping entry
  point with an upscale requested, and the upscale must actually be IN the returned graph, feeding
  the sink. A structural test can be satisfied by a table; only this one can be satisfied by the
  feature working.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from upscale_engine import IMAGE_SINKS  # noqa: E402

BUILDER_MODULES = ("native_video_graphs.py", "native_image_graphs.py")
CONTRACT = ROOT / "docs" / "pipeline" / "comfy_baselines" / "node_contract_206b9245.json"

# A class a builder terminates on that does NOT take an IMAGE. The picture reaches these through a
# node that does, so they are correctly absent from IMAGE_SINKS -- and the reason is recorded here
# rather than left to be re-derived by whoever next reads the sink table and wonders.
NOT_AN_IMAGE_CONSUMER = {
    "SaveVideo": "takes VIDEO. CreateVideo is the node that consumes the frames.",
    "SaveAudio": "takes AUDIO.",
}


def _sink_candidates() -> set[str]:
    """Class names the builders select as an output node, read out of the source.

    Both spellings are collected: the `_first_available_class(object_info, (...), label='...saving')`
    fallback tuples, and plain `"class_type": "X"` literals. A name that appears only in a comment
    is not collected, because this reads the AST rather than the text.
    """
    found: set[str] = set()
    for module in BUILDER_MODULES:
        tree = ast.parse((ROOT / "python" / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # ("SaveWEBM", "SaveAnimatedWEBP", ...) passed to _first_available_class with a label
            # that says what the class is FOR. The label is what makes this precise rather than a
            # sweep of every tuple of strings in the file.
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_first_available_class":
                label = ""
                for keyword in node.keywords:
                    if keyword.arg == "label" and isinstance(keyword.value, ast.Constant):
                        label = str(keyword.value.value).lower()
                # "video latent creation" selects EmptyLTXVLatentVideo and friends, which are where
                # a graph STARTS. Matching "creation" alone collected all five of them and the
                # ratchet failed on its first run demanding they be classified as sinks -- a rule
                # whose first report is five false positives is not a rule yet (Doc 53 5).
                is_output = any(word in label for word in ("saving", "assembly")) or (
                    "creation" in label and "latent" not in label
                )
                if not is_output:
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Tuple):
                        found.update(
                            str(e.value) for e in arg.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        )
            # {"class_type": "CreateVideo", ...}
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "class_type"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value.startswith(("Save", "Create", "VHS_"))
                    ):
                        found.add(value.value)
    return found


def test_every_output_class_a_builder_selects_is_classified() -> None:
    """A terminal class is graftable or is documented as taking something other than an IMAGE.

    The third state -- present in neither -- is the one that hides a defect: `CreateVideo` sat there
    for the whole life of this feature, in neither the sink table nor any exception list, and the
    absence read as nothing at all.
    """
    known = {class_name for class_name, _input in IMAGE_SINKS}
    unclassified = sorted(_sink_candidates() - known - set(NOT_AN_IMAGE_CONSUMER))
    assert not unclassified, (
        "these output classes are selected by a builder but are in neither upscale_engine."
        f"IMAGE_SINKS nor NOT_AN_IMAGE_CONSUMER: {unclassified}. A graph that terminates on one of "
        "them takes no upscale, and says nothing about it."
    )


def test_the_sink_table_matches_what_the_schema_says_those_classes_take() -> None:
    """Every entry in IMAGE_SINKS names an input the class really has, and that input is an IMAGE.

    Ground truth is the pinned contract rather than a live `/object_info`, so this holds with
    ComfyUI stopped. A class the contract does not cover is skipped rather than guessed at -- the
    contract pins the classes this repo depends on, not the whole core.
    """
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["contract"]
    checked = 0
    for class_name, input_name in IMAGE_SINKS:
        entry = contract.get(class_name)
        if not entry or not entry.get("__present__"):
            continue
        inputs = entry.get("inputs") or {}
        assert input_name in inputs, (
            f"IMAGE_SINKS says {class_name} carries its image on {input_name!r}, and the pinned "
            f"contract says its inputs are {sorted(inputs)}."
        )
        assert inputs[input_name].get("type") == "IMAGE", (
            f"{class_name}.{input_name} is {inputs[input_name].get('type')}, not IMAGE. Grafting "
            "into it would rewire something that is not the picture."
        )
        checked += 1
    assert checked >= 2, "the contract covered too few sinks for this to have checked anything"


def test_the_graft_has_exactly_one_home_on_the_video_path() -> None:
    """Nothing may build a video graph around the applier.

    `_build_native_split_video_prompt` builds and then upscales; `_build_native_split_video_graph`
    only builds. A caller that reaches for the inner one gets a correct graph with no upscale in it
    -- which is precisely how this feature was broken for images, one layer down.
    """
    offenders = []
    for path in sorted((ROOT / "python").rglob("*.py")):
        if path.name == "native_video_graphs.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "_build_native_split_video_graph" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "these modules call the un-upscaled inner builder directly: "
        f"{offenders}. Call _build_native_split_video_prompt instead."
    )


# --- the frame is not the request ---------------------------------------------------------------


def test_the_target_is_the_frame_size_not_the_requested_size() -> None:
    """A spatial latent upsampler makes `req["width"]` the size of the LATENT, not of the picture.

    On the DEFAULT LTX route `LTXVLatentUpsampler` runs between the two samplers, so a request for
    768x512 renders a 1536x1024 file -- verified against a live render 2026-09-03. The first version
    of the video graft computed its `ImageScale` target as `req["width"] * scale` = 1536, which the
    frame already was: it ran a 4x model upscale and then resized straight back to the size it
    started at. Bigger file, same dimensions. That is a request honoured into a no-op, which is the
    exact defect this whole feature was fixed for, reintroduced one layer up.
    """
    from native_video_graphs import _video_frame_dimensions

    plain = {"1": {"class_type": "EmptyLTXVLatentVideo", "inputs": {}}}
    assert _video_frame_dimensions(plain, 768, 512) == (768, 512)

    upsampled = dict(plain, **{"2": {"class_type": "LTXVLatentUpsampler", "inputs": {}}})
    assert _video_frame_dimensions(upsampled, 768, 512) == (1536, 1024), (
        "the two-stage route doubles the frame; a target computed from the request would resize "
        "the upscaled frames back to the size they already were"
    )


def test_a_video_family_resolves_to_the_comfy_graft_not_the_pil_post_pass() -> None:
    """The video families reach the route that can actually reach their picture.

    They resolved to `pixel_pil` before -- the diffusers runner's post-pass, which never sees a
    picture ComfyUI produced. Nobody performed it, so an upscale requested on a video was neither
    done nor refused. The family list is read from the plugin registry rather than restated, for the
    same reason the image one is: the second copy is what left krea2 silently un-upscalable.
    """
    from upscale_engine import ROUTE_PIXEL_COMFY, ROUTE_RESIZE_COMFY, resolve_upscale_route
    from native_video_graphs import NATIVE_VIDEO_FAMILY_PLUGINS

    for plugin in NATIVE_VIDEO_FAMILY_PLUGINS:
        for family in {plugin.family, plugin.match_prefix} - {""}:
            assert resolve_upscale_route(family, "model", enabled=True) == ROUTE_PIXEL_COMFY, family
            assert resolve_upscale_route(family, "lanczos", enabled=True) == ROUTE_RESIZE_COMFY, family


# --- the live gate ------------------------------------------------------------------------------


@pytest.mark.needs_comfy
@pytest.mark.needs_gpu
def test_every_native_video_family_graph_takes_the_graft() -> None:
    """Built through the shipping entry point, with an upscale asked for, the upscale is in there.

    Structural tests above can be satisfied by a table. This one can only be satisfied by the graft
    finding a sink in a graph the real builder really produced, for each family in the registry.

    Requires the live core because the builders select node classes from `/object_info`; skipped
    rather than failed when a family's models are not on this box, since that is a property of the
    machine and not of the code.
    """
    from comfy_prompt_client import _http_get_json
    import native_video_graphs as nvg

    try:
        object_info = _http_get_json("http://127.0.0.1:8188", "/object_info", timeout=180)
    except Exception as exc:  # pragma: no cover - the marker already scopes this
        pytest.skip(f"ComfyUI not reachable: {exc}")

    models = {
        "ltx": "D:/AI_ASSETS/models/checkpoints/ltx/ltx-2.3-22b-dev.safetensors",
        "mochi": "D:/AI_ASSETS/models/diffusion_models/mochi",
        "hunyuan": "D:/AI_ASSETS/models/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors",
    }
    reached = 0
    missing: list[str] = []
    for family, model in models.items():
        if not Path(model).exists():
            continue
        req = {
            "command": "t2v", "model": model, "video_family": family,
            "prompt": "a calm ocean wave", "width": 768, "height": 512,
            "frames": 49, "num_frames": 49, "fps": 16, "steps": 12, "cfg": 3.0, "seed": 1,
            "output": str(ROOT / "build" / f"sinkcheck_{family}.mp4"),
            "upscale_enabled": True, "upscale_method": "model", "upscale_scale": 2.0,
        }
        try:
            graph = nvg._build_native_split_video_prompt(
                req, object_info, command="t2v", family=family, job_id=f"sink-{family}")
        except RuntimeError as exc:
            # One family's models being absent is a fact about this box. Skipping the TEST on it
            # would cancel the families that ARE installed -- the first run of this did exactly
            # that, reporting a skip while ltx had already passed, so the check looked unexercised
            # when it had in fact just succeeded.
            missing.append(f"{family} ({exc})")
            continue
        classes = {n.get("class_type") for n in graph.values() if isinstance(n, dict)}
        assert "ImageUpscaleWithModel" in classes, f"{family}: the graft found no sink"
        sinks = [n for n in graph.values()
                 if isinstance(n, dict) and n.get("class_type") in {c for c, _ in IMAGE_SINKS}]
        assert sinks, f"{family}: no image sink at all"
        for sink in sinks:
            ref = sink["inputs"].get("images")
            assert isinstance(ref, list), f"{family}: sink takes no image reference"
            fed_by = graph[str(ref[0])]["class_type"]
            assert fed_by in ("ImageScale", "ImageUpscaleWithModel"), (
                f"{family}: the sink is fed by {fed_by}, so the upscale is in the graph but not "
                "on the path to the output -- a dangling branch reads as a working feature"
            )
        reached += 1
    if not reached:
        pytest.skip("no native video family resolvable on this box: " + "; ".join(missing))
