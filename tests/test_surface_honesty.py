"""Gen3D/Train stay visible but honest. No first-install Sohya path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = (ROOT / "qt_ui" / "Gen3DPage.cpp").read_text(encoding="utf-8")
TRAIN = (ROOT / "qt_ui" / "TrainPage.cpp").read_text(encoding="utf-8")
HISTORY = (ROOT / "qt_ui" / "T2VHistoryPage.cpp").read_text(encoding="utf-8")
REQUEST_BUILDER = (ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.cpp").read_text(encoding="utf-8")


def test_gen3d_admits_no_in_page_mesh() -> None:
    assert "no in-page mesh viewer" in GEN.lower()
    assert "No mesh viewer in this page" in GEN
    assert "setResultMesh" in GEN


def test_train_is_launcher_without_machine_path() -> None:
    assert "External trainer launcher" in TRAIN
    assert "Sohya_kk/main.py" not in TRAIN
    assert "Code_Projects/Sohya_kk" not in TRAIN
    assert 'pathEdit_->setText(saved)' in TRAIN


def test_legacy_prompt_api_requeue_is_not_a_visible_product_action() -> None:
    assert "requeueButton_->setHidden(true)" in HISTORY
    assert "validateRequeueButton_->setHidden(true)" in HISTORY
    assert "submitRequeueButton_->setHidden(true)" in HISTORY
    assert "copyActions->addWidget(requeueButton_" not in HISTORY
    assert "prompt_api_export_path" not in REQUEST_BUILDER
    assert "D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json" not in REQUEST_BUILDER
