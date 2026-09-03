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


def test_the_upscale_row_is_offered_wherever_its_keys_are_sent() -> None:
    """A control a surface does not offer does not contribute to that surface's request.

    The instance that produced this rule: the cockpit hid the whole upscale row in video mode, and
    hidden widgets keep their values, so every T2V/I2V request carried the last image-mode
    `upscale_enabled` -- a checkbox nobody could see, stating an intent nobody had stated for that
    mode. Nothing on the video path read those keys, which is the only reason it was harmless, and
    the note left in the code said it "becomes a bug the day a video upscale is wired."

    It was wired on 2026-09-03, and the fix was to satisfy the rule from the other side: the row is
    now OFFERED in video modes, so sending its keys is honest. That is why this test checks the two
    sides AGREE rather than checking for the mode fence -- a test that pins one of the two valid
    answers turns a correct change into a red build and teaches nothing about the rule.
    """
    disclosure = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")

    offered_everywhere = "upscaleRow_->setVisible(true)" in disclosure

    # Anchored on the INSERT, not on the key name. The first version searched backwards from the
    # first occurrence of "upscale_enabled", which is in the comment that explains the rule -- so
    # the window it examined was prose, and re-introducing the fence did not make it fail. A static
    # test whose anchor also appears in the text it is testing is measuring the text.
    insert = REQUEST_BUILDER.index('payload.insert(QStringLiteral("upscale_enabled")')
    gated_in_builder = "if (!draft.isVideoMode) {" in REQUEST_BUILDER[max(0, insert - 400) : insert]

    assert offered_everywhere == (not gated_in_builder), (
        "the two sides disagree about which modes offer an upscale. "
        f"Row offered in every mode: {offered_everywhere}. "
        f"Request builder fences the keys to image modes: {gated_in_builder}. "
        "Offered-and-fenced means the user sets a tier and nothing happens; hidden-and-sent means a "
        "widget nobody can see is stating an intent for a mode it was never set in."
    )

    # Whichever side is in force, all four keys travel together. A subset would let the method
    # change while `enabled` stayed behind, which is the two-sources-of-truth defect one level down.
    for key in ("upscale_enabled", "upscale_method", "upscale_scale", "upscale_model_name"):
        assert key in REQUEST_BUILDER, f"{key} is no longer sent at all"
