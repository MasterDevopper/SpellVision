from __future__ import annotations

import sys
from pathlib import Path


PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from video_family_contracts import (
    infer_video_family_from_text,
    normalize_video_family_id,
    video_family_contract,
    video_family_contracts_snapshot,
)


def test_flux3_is_a_truthfully_labeled_remote_preview_family() -> None:
    contract = video_family_contract("flux-3")

    assert contract.family == "flux3"
    assert contract.display_name == "FLUX.3 (BFL API Preview)"
    assert contract.backend_route == "bfl_api"
    assert contract.stack_kind == "remote_api"
    assert contract.tasks == ("t2v", "i2v")
    assert contract.required_components == ()
    assert contract.production_ready is False


def test_flux3_aliases_and_markers_resolve_without_matching_flux_image() -> None:
    assert normalize_video_family_id("FLUX.3") == "flux3"
    assert normalize_video_family_id("flux_3") == "flux3"
    assert infer_video_family_from_text("FLUX.3 Video") == "flux3"
    assert infer_video_family_from_text("flux image checkpoint") == "unknown"


def test_hunyuan_splits_t2v_production_from_i2v_wrapper() -> None:
    """C12: family-level production must not imply Hunyuan i2v is production.

    T2V is native-production. I2V is wrapper-only (CLIPVision native path blocked).
    """
    contract = video_family_contract("hunyuan_video")

    assert contract.family == "hunyuan_video"
    assert contract.tasks == ("t2v", "i2v")
    assert contract.validation_status == "production"
    assert contract.status_for_task("t2v") == "production"
    assert contract.status_for_task("i2v") == "wrapper"
    assert contract.production_ready is True
    assert contract.production_ready_for("t2v") is True
    assert contract.production_ready_for("i2v") is False

    payload = contract.to_payload()
    assert payload["validation_status"] == "production"
    assert payload["task_validation_status"]["t2v"] == "production"
    assert payload["task_validation_status"]["i2v"] == "wrapper"
    assert payload["production_ready"] is True
    assert payload["production_ready_for"]["t2v"] is True
    assert payload["production_ready_for"]["i2v"] is False


def test_hunyuan_snapshot_does_not_advertise_i2v_as_production() -> None:
    snapshot = video_family_contracts_snapshot()
    hunyuan = snapshot["families"]["hunyuan_video"]
    assert hunyuan["task_validation_status"]["i2v"] == "wrapper"
    assert hunyuan["production_ready_for"]["i2v"] is False
    assert hunyuan["production_ready_for"]["t2v"] is True
    assert "hunyuan_video" in snapshot["production_families"]


def test_other_production_families_keep_both_tasks_production() -> None:
    wan = video_family_contract("wan")
    assert wan.status_for_task("t2v") == "production"
    assert wan.status_for_task("i2v") == "production"
    assert wan.production_ready_for("i2v") is True

    ltx = video_family_contract("ltx")
    assert ltx.status_for_task("i2v") == "production"
    assert ltx.production_ready_for("i2v") is True


def test_hunyuan_builder_has_no_dead_native_concat_after_i2v_return() -> None:
    """Dead CLIPVision concat after the i2v return must be gone."""
    import inspect

    from native_video_graphs import _build_native_hunyuan_video_prompt

    source = inspect.getsource(_build_native_hunyuan_video_prompt)
    assert '"class_type": "CLIPVisionEncode"' not in source
    assert "TextEncodeHunyuanVideo_ImageToVideo" not in source
    assert 'guidance_type": "v1 (concat)"' not in source
