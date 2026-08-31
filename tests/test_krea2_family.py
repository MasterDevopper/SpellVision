from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from family_install_plan import build_family_install_plan
from family_operating_points import (
    default_operating_point,
    family_operating_points_payload,
    operating_point_params,
    resolve_family_defaults,
)
from model_dependency_manifest import COMPONENT_MANIFEST
from model_import import dest_subdir
from model_registry import family_license_info, infer_model_family


def _krea_slots(present: list[str] | None = None) -> dict[str, dict]:
    plan = build_family_install_plan("krea2", task="t2i", present_basenames=present or [])
    return {row["component"]: row for row in plan["slots"]}


def test_krea2_is_detectable_and_installable() -> None:
    assert infer_model_family("krea2_turbo_fp8_scaled.safetensors") == "krea2"
    assert infer_model_family("Comfy-Org/Krea-2") == "krea2"
    assert dest_subdir("Checkpoint", "krea2_turbo_fp8_scaled.safetensors") == "diffusion_models"
    assert dest_subdir("Checkpoint", "qwen3vl_4b_fp8_scaled.safetensors") == "text_encoders"


def test_krea2_default_is_raw_turbo_is_speed_lane() -> None:
    assert default_operating_point("krea2") == "raw"
    assert default_operating_point("krea2_image") == "raw"
    raw = operating_point_params("krea2_image", "raw")
    turbo = operating_point_params("krea2_image", "turbo")
    assert raw["steps"] == 52 and raw["cfg"] == 3.5
    assert turbo["steps"] == 8 and turbo["cfg"] == 1.0
    blank = resolve_family_defaults("krea2", None, {})
    assert blank["steps"] == 52 and blank["cfg"] == 3.5
    payload = family_operating_points_payload("krea2")
    assert payload["default_operating_point"] == "raw"
    names = [op["name"] for op in payload["operating_points"]]
    assert names == ["turbo", "raw"] or set(names) == {"turbo", "raw"}
    from video_family_contracts import video_family_contracts_snapshot
    snap = video_family_contracts_snapshot()
    assert snap["families"]["krea2"]["default_operating_point"] == "raw"


def test_krea2_loras_are_enabled_never_required() -> None:
    slots = COMPONENT_MANIFEST["krea2"]["slots"]
    assert "lora" not in slots
    plan = _krea_slots()
    assert "lora" not in plan
    for name in ("raw", "turbo"):
        params = operating_point_params("krea2_image", name)
        lora = params.get("lora") or {}
        assert lora.get("accel") is not True
        assert not lora.get("high") and not lora.get("low")


def test_krea2_install_offers_official_bases_only() -> None:
    empty = build_family_install_plan("krea2", task="t2i", present_basenames=[])
    by_name = {row["component"]: row for row in empty["slots"]}
    assert by_name["unet_raw"]["required"] is True
    assert by_name["unet_raw"]["install_action"] == "fetch"
    assert by_name["unet_raw"]["fetch_ref"].endswith("krea2_raw_fp8_scaled.safetensors")
    assert by_name["unet_turbo"]["required"] is False
    assert by_name["unet_turbo"]["install_action"] == "fetch"
    assert by_name["unet_turbo"]["fetch_ref"].endswith("krea2_turbo_fp8_scaled.safetensors")
    assert by_name["text_encoder"]["required"] is True
    assert by_name["vae"]["required"] is True
    assert set(empty["missing_required"]) == {"unet_raw", "text_encoder", "vae"}
    refs = " ".join(empty["fetchable"])
    assert "loras/" not in refs
    assert "krea2_darkbrush" not in refs
    assert "krea2_turbo_lora" not in refs

    raw_ready = build_family_install_plan(
        "krea2",
        task="t2i",
        present_basenames=[
            "krea2_raw_fp8_scaled.safetensors",
            "qwen3vl_4b_fp8_scaled.safetensors",
            "qwen_image_vae.safetensors",
        ],
    )
    assert raw_ready["missing_required"] == []
    present_by = {row["component"]: row["install_action"] for row in raw_ready["slots"]}
    assert present_by["unet_raw"] == "already_present"
    assert present_by["unet_turbo"] == "fetch"

    turbo_only = build_family_install_plan(
        "krea2",
        task="t2i",
        present_basenames=[
            "krea2_turbo_fp8_scaled.safetensors",
            "qwen3vl_4b_fp8_scaled.safetensors",
            "qwen_image_vae.safetensors",
        ],
    )
    assert turbo_only["missing_required"] == ["unet_raw"]


def test_krea2_native_graph_uses_grounded_nodes() -> None:
    import worker_service as ws

    class Resolved:
        def value(self, name: str) -> str:
            return {
                "text_encoder": "qwen3vl_4b_fp8_scaled.safetensors",
                "vae": "qwen_image_vae.safetensors",
            }.get(name, "")

    object_info = {
        "UNETLoader": {
            "input": {"required": {"unet_name": [["krea2_raw_fp8_scaled.safetensors", "krea2_turbo_fp8_scaled.safetensors"]]}},
        },
        "LoraLoaderModelOnly": {
            "input": {"required": {"lora_name": [["krea2_softwatercolor.safetensors"]], "model": ["MODEL"], "strength_model": ["FLOAT"]}},
        },
    }
    graph = ws._build_krea2_image_prompt(
        {
            "model": r"F:/AI_ASSETS/models/diffusion_models/krea2_raw_fp8_scaled.safetensors",
            "prompt": "a fox in the snow",
            "command": "t2i",
            "width": 1024,
            "height": 1024,
        },
        object_info,
        "job-krea2",
        Resolved(),
    )
    assert graph["2"]["inputs"]["type"] == "krea2"
    assert graph["5"]["class_type"] == "ModelSamplingAuraFlow"
    assert graph["5"]["inputs"]["shift"] == 1.15
    assert graph["7"]["class_type"] == "EmptySD3LatentImage"
    assert graph["8"]["inputs"]["steps"] == 52
    assert graph["8"]["inputs"]["cfg"] == 3.5
    assert graph["8"]["inputs"]["model"] == ["5", 0]
    assert not any(node.get("class_type") == "LoraLoaderModelOnly" for node in graph.values())
    assert "krea2" in ws.NATIVE_IMAGE_FAMILIES
    assert ws.NATIVE_IMAGE_FAMILY_PLUGINS["krea2"].family == "krea2"
    assert ws._should_route_native_image({
        "command": "t2i",
        "model": r"F:/AI_ASSETS/models/diffusion_models/krea2_raw_fp8_scaled.safetensors",
        "model_family": "image",
    })
    import image_runners as ir
    assert ir._should_route_native_image is ws._should_route_native_image
    import comfy_prompt_client as cpc
    assert callable(cpc._comfy_required_inputs)
    assert hasattr(cpc, "uuid")
    import worker_metadata as wm
    assert ".mp4" in wm.VIDEO_OUTPUT_EXTENSIONS
    license_info = family_license_info("krea2")
    assert license_info["key"] == "krea2"
    assert "Community License" in str(license_info["license_note"])


def test_krea2_turbo_filename_still_snaps_speed_lane() -> None:
    import worker_service as ws

    class Resolved:
        def value(self, name: str) -> str:
            return {
                "text_encoder": "qwen3vl_4b_fp8_scaled.safetensors",
                "vae": "qwen_image_vae.safetensors",
            }.get(name, "")

    object_info = {
        "UNETLoader": {
            "input": {"required": {"unet_name": [["krea2_turbo_fp8_scaled.safetensors"]]}},
        },
    }
    graph = ws._build_krea2_image_prompt(
        {
            "model": r"F:/AI_ASSETS/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors",
            "prompt": "a fox in the snow",
            "command": "t2i",
            "width": 1024,
            "height": 1024,
        },
        object_info,
        "job-krea2-turbo",
        Resolved(),
    )
    assert graph["8"]["inputs"]["steps"] == 8
    assert graph["8"]["inputs"]["cfg"] == 1.0
    zeroed = ws._build_krea2_image_prompt(
        {
            "model": r"F:/AI_ASSETS/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors",
            "prompt": "a fox in the snow",
            "command": "t2i",
            "width": 1024,
            "height": 1024,
            "cfg": 0.0,
        },
        object_info,
        "job-krea2-turbo-zero",
        Resolved(),
    )
    assert zeroed["8"]["inputs"]["cfg"] == 1.0


def test_krea2_enabled_lora_is_optional_and_applied() -> None:
    import worker_service as ws

    class Resolved:
        def value(self, name: str) -> str:
            return {
                "text_encoder": "qwen3vl_4b_fp8_scaled.safetensors",
                "vae": "qwen_image_vae.safetensors",
            }.get(name, "")

    object_info = {
        "UNETLoader": {
            "input": {"required": {"unet_name": [["krea2_raw_fp8_scaled.safetensors"]]}},
        },
        "LoraLoaderModelOnly": {
            "input": {
                "required": {
                    "model": ["MODEL"],
                    "lora_name": [["krea2_softwatercolor.safetensors"]],
                    "strength_model": ["FLOAT"],
                }
            }
        },
    }
    graph = ws._build_krea2_image_prompt(
        {
            "model": r"F:/AI_ASSETS/models/diffusion_models/krea2_raw_fp8_scaled.safetensors",
            "prompt": "a fox in the snow",
            "command": "t2i",
            "loras": [
                {"name": "krea2_softwatercolor.safetensors", "strength": 0.8, "enabled": True},
                {"name": "krea2_darkbrush.safetensors", "strength": 1.0, "enabled": False},
            ],
        },
        object_info,
        "job-krea2-lora",
        Resolved(),
    )
    lora_nodes = [node for node in graph.values() if node.get("class_type") == "LoraLoaderModelOnly"]
    assert len(lora_nodes) == 1
    assert lora_nodes[0]["inputs"]["lora_name"] == "krea2_softwatercolor.safetensors"
    assert lora_nodes[0]["inputs"]["strength_model"] == 0.8
    assert graph["5"]["inputs"]["model"] != ["1", 0]


# --- text encoder placement: policy, not the reference workflow's machine ---------------------


# The slice of /object_info these tests depend on, stated rather than assumed.
#
# It used to be `{}`. The builder hardcoded the {"default", "cpu"} pair and the test asserted the
# same pair back, so the two agreed with each other and neither was checking ComfyUI. Now the
# builder READS the vocabulary -- the core loaders spell on-GPU "default" and the kijai wrapper
# spells it "gpu", and forwarding one node's word to the other is a 400 -- so the fixture has to
# supply the fact it was previously asserting.
KREA2_OBJECT_INFO = {
    "CLIPLoader": {"input": {"optional": {"device": [["default", "cpu"], {"advanced": True}]}}},
}


def _krea2_graph(monkeypatch, req_extra=None, profile=None, object_info=None):
    """Build the Krea 2 graph with the model/encoder lookups stubbed."""
    import native_image_graphs as nig

    monkeypatch.setattr(nig, "_comfy_unet_name_for_model", lambda info, path: "krea2.safetensors")
    if profile is not None:
        import memory_optimization

        monkeypatch.setattr(memory_optimization, "auto_select_memory_profile", lambda *a, **k: profile)

    class _Resolved:
        def value(self, key):
            return None

    req = {"model": "diffusion_models/krea2.safetensors", "prompt": "a cat", "width": 1024, "height": 1024}
    req.update(req_extra or {})
    info = KREA2_OBJECT_INFO if object_info is None else object_info
    return nig._build_krea2_image_prompt(req, info, "job_test", _Resolved())


def test_an_unreadable_object_info_omits_the_device_rather_than_guessing(monkeypatch):
    """If the vocabulary cannot be read, no value is invented.

    Omitting the key leaves ComfyUI on its own default, which is correct for the node. Writing a
    remembered "default" would be a guess that happens to be right for core loaders and wrong for
    the wrapper -- and guessing a value instead of reading it is the LTX prefix bug."""
    graph = _krea2_graph(monkeypatch, object_info={})
    assert "device" not in graph["2"]["inputs"]


def test_the_encoder_device_is_a_valid_clip_loader_choice(monkeypatch):
    """Live /object_info: CLIPLoader.device is optional with exactly {"default", "cpu"}.

    Anything else is a 400 from ComfyUI, so the value is pinned to that set rather than trusted
    from a request.
    """
    graph = _krea2_graph(monkeypatch)
    assert graph["2"]["class_type"] == "CLIPLoader"
    assert graph["2"]["inputs"]["device"] in {"default", "cpu"}


def test_a_card_with_headroom_keeps_the_encoder_resident(monkeypatch):
    """The reference workflow hardcodes cpu. Copying it would cost encode latency on every
    generation for users who have the VRAM to spare."""
    from memory_optimization import MemoryProfile

    graph = _krea2_graph(monkeypatch, profile=MemoryProfile.PERFORMANCE)
    assert graph["2"]["inputs"]["device"] == "default"


def test_a_constrained_card_pushes_the_4b_encoder_to_system_ram(monkeypatch):
    from memory_optimization import MemoryProfile

    for profile in (MemoryProfile.BALANCED, MemoryProfile.LOW_VRAM):
        graph = _krea2_graph(monkeypatch, profile=profile)
        assert graph["2"]["inputs"]["device"] == "cpu", profile


def test_an_explicit_request_beats_the_profile(monkeypatch):
    from memory_optimization import MemoryProfile

    graph = _krea2_graph(monkeypatch, {"text_encoder_device": "cpu"}, profile=MemoryProfile.PERFORMANCE)
    assert graph["2"]["inputs"]["device"] == "cpu"


def test_an_unsupported_device_falls_back_instead_of_reaching_comfy(monkeypatch):
    """A typo must not become a failed generation."""
    from memory_optimization import MemoryProfile

    graph = _krea2_graph(monkeypatch, {"text_encoder_device": "mps"}, profile=MemoryProfile.PERFORMANCE)
    assert graph["2"]["inputs"]["device"] == "default"


def test_er_sde_is_the_settled_krea2_default():
    """Settled 2026-08-28 by render comparison, not by copying the reference workflow.

    Three pairs -- two prompts at raw (52 steps / cfg 3.5) and one at turbo (8 / 1.0) -- with the
    sampler as the only variable. er_sde resolved fine high-frequency structure markedly better in
    every pair, at no time cost on the one clean timing comparison (56.5s vs 56.2s).

    Measuring it is what exposed the larger bug: no native image builder read the requested sampler
    at all, so the first er_sde submission silently rendered euler. See
    tests/test_native_image_sampler_choice.py.
    """
    from family_operating_points import FAMILY_SAMPLER_ALLOWLISTS, operating_point_params

    allowed = FAMILY_SAMPLER_ALLOWLISTS["krea2_image"]["samplers"]
    assert "er_sde" in allowed and "euler" in allowed, "both stay selectable"

    for variant in ("raw", "turbo"):
        assert operating_point_params("krea2_image", variant)["sampler"] == "er_sde", variant
