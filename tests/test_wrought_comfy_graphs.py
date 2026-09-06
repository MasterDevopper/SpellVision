"""Graph shape tests for the Wrought transport. Hermetic: no ComfyUI is contacted."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
sys.path.insert(0, str(ROOT / "python"))

import wrought_comfy as wc  # noqa: E402


def _by_class(graph: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append(node_id)
    return out


def test_t2i_graph_is_the_locked_recipe():
    g = wc.t2i_graph("pos", "neg", seed=7, prefix="x", width=768, height=1024)
    classes = _by_class(g)
    for needed in ("UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode",
                   "ModelSamplingAuraFlow", "EmptySD3LatentImage", "KSampler", "VAEDecode",
                   "SaveImage"):
        assert needed in classes, needed
    ks = g[classes["KSampler"][0]]["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (52, 3.5, "euler", "simple")
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["shift"] == 1.15
    assert g[classes["CLIPLoader"][0]]["inputs"]["type"] == "krea2"
    assert ks["seed"] == 7
    assert g[classes["EmptySD3LatentImage"][0]]["inputs"] == {"width": 768, "height": 1024, "batch_size": 1}


def test_reference_edit_graph_routes_the_reference_into_the_positive():
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png")
    classes = _by_class(g)
    assert "LoadImage" in classes and "TextEncodeQwenImageEditPlus" in classes
    assert "FluxKontextMultiReferenceLatentMethod" in classes
    load = classes["LoadImage"][0]
    enc = g[classes["TextEncodeQwenImageEditPlus"][0]]["inputs"]
    assert enc["image1"] == [load, 0] and enc["vae"][0] == classes["VAELoader"][0]
    method = classes["FluxKontextMultiReferenceLatentMethod"][0]
    assert g[method]["inputs"]["conditioning"] == [classes["TextEncodeQwenImageEditPlus"][0], 0]
    assert g[method]["inputs"]["reference_latents_method"] == "index_timestep_zero"
    ks = g[classes["KSampler"][0]]["inputs"]
    assert ks["positive"] == [method, 0]
    # the NEGATIVE is the real house negative, not ConditioningZeroOut -- we run CFG 3.5 on RAW
    assert g[ks["negative"][0]]["class_type"] == "CLIPTextEncode"
    assert g[ks["negative"][0]]["inputs"]["text"] == "neg"


def test_no_graph_carries_a_disk_path():
    g = wc.reference_edit_graph("pos", "neg", 1, "x", 8, 8, reference_name="skin_000.png")
    assert g[_by_class(g)["LoadImage"][0]]["inputs"]["image"] == "skin_000.png"
    assert ":\\" not in str(g) and "C:/" not in str(g)


@pytest.mark.needs_comfy
def test_live_core_knows_every_node_class_we_emit():
    """Doc 50 rule 2: the class names come from a live /object_info, not from memory."""
    from comfy_prompt_client import _http_get_json
    info = _http_get_json("http://127.0.0.1:8188", "/object_info", timeout=60)
    g = wc.reference_edit_graph("pos", "neg", 1, "x", 8, 8, reference_name="r.png")
    for node in g.values():
        assert node["class_type"] in info, node["class_type"]
    ref = info["FluxKontextMultiReferenceLatentMethod"]["input"]["required"]
    assert "reference_latents_method" in ref


def test_lane_a_suit_graph_uses_a_different_seed_and_the_uploaded_name():
    g = wc.reference_edit_graph("suit prompt", "neg", seed=9_500_007, prefix="wv2_orc_007_suit",
                                width=1216, height=1728, reference_name="wv2_orc_007_skin_00001_.png")
    ks = g[[k for k, n in g.items() if n["class_type"] == "KSampler"][0]]["inputs"]
    assert ks["seed"] == 9_500_007
    load = g[[k for k, n in g.items() if n["class_type"] == "LoadImage"][0]]["inputs"]["image"]
    assert load.endswith(".png") and "/" not in load


def test_reference_edit_graph_carries_krea_s_own_reference_lora_by_default():
    # Measured 2026-09-06: Utopic cannot consume reference tokens without this LoRA (latent
    # checkerboard) -- see wrought_comfy.reference_edit_graph's docstring and
    # evidence/v2_reference_edit_probes_2026-09-06.jpg. The LoRA sits between the checkpoint and
    # ModelSamplingAuraFlow, so every downstream sampling node rides the patched model.
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png")
    classes = _by_class(g)
    lora_id = classes["LoraLoaderModelOnly"][0]
    lora = g[lora_id]["inputs"]
    assert lora["lora_name"] == "krea2_style_reference.safetensors"
    assert lora["strength_model"] == 1.0
    assert lora["model"] == [classes["UNETLoader"][0], 0]
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["model"] == [lora_id, 0]


def test_reference_edit_graph_omits_the_lora_when_asked():
    g = wc.reference_edit_graph("pos", "neg", seed=1, prefix="x", width=1216, height=1728,
                                reference_name="skin_000.png", lora=None)
    classes = _by_class(g)
    assert "LoraLoaderModelOnly" not in classes
    assert g[classes["ModelSamplingAuraFlow"][0]]["inputs"]["model"] == [classes["UNETLoader"][0], 0]


def test_sheet_prompt_is_a_build_document_not_a_look():
    import wrought_sheet_test as st
    p = st.sheet_prompt("left", "flat")
    assert "the same woman as the reference" in p and "only one eye visible" in p
    assert "even soft frontal" in p and "light grey studio backdrop" in p
    assert "dark studio" not in p and "key light" not in p
    soft = st.sheet_prompt("front", "soft")
    assert "soft directional" in soft


def test_sheet_negative_refuses_the_look_under_flat_light():
    import wrought_sheet_test as st
    assert "dark background" in st.sheet_negative("flat") and "mirrored pair" in st.sheet_negative("flat")
    assert "dark background" not in st.sheet_negative("soft")


def _sheet_report(images_ok: list, cross_ok: list) -> dict:
    return {
        "images": [{"path": f"v{i}.png", "ok": ok, "findings": [{"ok": ok, "rule": "r", "detail": "d"}]}
                   for i, ok in enumerate(images_ok)],
        "cross_view": [{"ok": ok, "rule": "c", "detail": "d"} for ok in cross_ok],
    }


def test_sheet_verdict_true_only_when_the_whole_sheet_passes():
    import wrought_sheet_test as st
    four_views = {v: Path(f"{v}.png") for v in ("front", "back", "left", "right")}

    # (a) all four views rendered, every finding ok, cross_view non-empty and ok -> True
    assert st.sheet_verdict(four_views, _sheet_report([True, True, True, True], [True, True])) is True

    # (b) only three views rendered (one missing) -- False even though everything else is ok
    three_views = {v: Path(f"{v}.png") for v in ("front", "back", "left")}
    assert st.sheet_verdict(three_views, _sheet_report([True, True, True], [True])) is False

    # (c) four views rendered, but one per-image finding is not ok -> False
    assert st.sheet_verdict(four_views, _sheet_report([True, True, False, True], [True])) is False

    # (d) four views rendered, everything ok, but cross_view is empty -> False (vacuous truth trap)
    assert st.sheet_verdict(four_views, _sheet_report([True, True, True, True], [])) is False


# --- Fix round 2 (Critical): a view whose mask shatters in prepare() must not kill the batch ---

def test_run_sheet_survives_a_pad_failure_on_one_view(monkeypatch, tmp_path):
    """`prepare_reference_sheet.prepare` raises on a view it cannot mask (a dark-ground side view
    does that to `subject_mask` for real). Left unguarded, that exception would propagate out of
    `run_sheet` before its JSON was ever written, killing main()'s whole plate loop over one bad
    view. Stub every collaborator so this test exercises only run_sheet's OWN try/except: the
    checker's own reaction to a not-fully-passing sheet is already covered by test (c) above
    (test_sheet_verdict_true_only_when_the_whole_sheet_passes) and is not re-asserted here.
    """
    import wrought_sheet_test as st
    from PIL import Image

    def fake_render(endpoint, graph, target):
        Image.new("RGB", (64, 96)).save(target)
        return True

    def fake_prepare(path, out, margin=None):
        if "left" in path.name:
            raise RuntimeError("shattered")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.open(path).save(out)
        return {"src": str(path), "out": str(out), "from": "64x96", "to": "64x96", "subject": "1x1"}

    def fake_check_set(paths):
        return {"images": [{"path": str(p), "ok": True,
                            "findings": [{"ok": True, "rule": "r", "detail": "d"}]} for p in paths],
                "cross_view": [{"ok": True, "rule": "c", "detail": "d"}]}

    class _FakeEndpoint:
        api = "fake"

        def upload_reference(self, path, max_side=(768, 1088)):
            return "ref.png"

    monkeypatch.setattr(st.wc, "render", fake_render)
    monkeypatch.setattr(st.prepare_reference_sheet, "prepare", fake_prepare)
    monkeypatch.setattr(st, "check_set", fake_check_set)
    monkeypatch.setattr(st.measures, "face_identity", lambda a, b: {})

    out_dir = tmp_path / "out"
    skin_plate = tmp_path / "human_woman" / "000_skin.png"
    result = st.run_sheet(_FakeEndpoint(), skin_plate, out_dir, "flat", 1)

    assert result["pad_errors"] == {"left": "shattered"}
    stem = "human_woman_000_skin_flat"
    assert (out_dir / f"{stem}_sheet.json").exists()
    # the view that could not be padded falls back to its RAW render, not a padded path
    assert result["checked"]["left"] == str(out_dir / f"{stem}_left.png")
    assert result["checked"]["front"] == str(out_dir / "padded" / f"{stem}_front.png")
