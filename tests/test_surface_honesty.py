"""Gen3D/Train stay visible but honest. No first-install Sohya path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = (ROOT / "qt_ui" / "Gen3DPage.cpp").read_text(encoding="utf-8")
TRAIN = (ROOT / "qt_ui" / "TrainPage.cpp").read_text(encoding="utf-8")
HISTORY = (ROOT / "qt_ui" / "HistoryPage.cpp").read_text(encoding="utf-8")
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


def test_ltx_payload_does_not_invent_house_companion_filenames() -> None:
    """Empty LTX draft used to stamp house checkpoints/VAEs/encoders into every
    native LTX request. Resolver fills companions from object_info; do not invent."""
    assert 'QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors")' not in REQUEST_BUILDER
    assert "comfy_gemma_3_12B_it" not in REQUEST_BUILDER
    assert "ltx-2.3_text_projection_bf16" not in REQUEST_BUILDER
    assert "LTX23_audio_vae" not in REQUEST_BUILDER
    assert "LTX23_video_vae" not in REQUEST_BUILDER
    assert 'QStringLiteral("clip_vision_g")' not in REQUEST_BUILDER


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


def test_history_empty_copy_is_not_video_only() -> None:
    """History lists stills too. Empty details still said Select a video / T2V / Wan."""
    assert 'QStringLiteral("Select a video")' not in HISTORY
    assert 'QStringLiteral("Select a result")' in HISTORY
    assert "Choose a completed T2V result" not in HISTORY
    assert "No T2V history entries" not in HISTORY
    assert "No video history loaded yet" not in HISTORY


def test_history_kn_shortcuts_do_not_fire_while_searching() -> None:
    """Bare K/N parented to the page with window context grade the row while
    typing in HistorySearch (knight loses letters and mutates KEEP/NO)."""
    ctor = HISTORY.split("HistoryPage::HistoryPage", 1)[1]
    ctor = ctor.split("void HistoryPage::setProjectRoot", 1)[0]
    assert "new QShortcut(QKeySequence(Qt::Key_K), this)" not in ctor
    assert "new QShortcut(QKeySequence(Qt::Key_N), this)" not in ctor
    assert "new QShortcut(QKeySequence(Qt::Key_K), table_)" in ctor
    assert "WidgetWithChildrenShortcut" in ctor


def test_mode_switch_and_window_resize_reflow_generation_pages() -> None:
    """Page-switch then fullscreen then T2I left the cockpit on the size
    it was hidden at. showEvent can run before contentsRect settles;
    MainWindow resize/changeEvent never told the page at all."""
    mw = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
    header = (ROOT / "qt_ui" / "ImageGenerationPage.h").read_text(encoding="utf-8")
    page = (ROOT / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")
    assert "void reflowForCurrentGeometry();" in header
    assert "void ImageGenerationPage::reflowForCurrentGeometry()" in page
    assert "reflowCurrentGenerationPage" in mw
    switch = mw.split("void MainWindow::switchToMode", 1)[1].split(
        "void MainWindow::sendModelToGeneration", 1
    )[0]
    assert "reflowCurrentGenerationPage" in switch
    resize = mw.split("void MainWindow::resizeEvent", 1)[1].split(
        "ImageGenerationPage *MainWindow::generationPageForMode", 1
    )[0]
    assert "reflowCurrentGenerationPage" in resize
    change = mw.split("void MainWindow::changeEvent", 1)[1].split(
        "bool MainWindow::nativeEvent", 1
    )[0]
    assert "reflowCurrentGenerationPage" in change
    assert "WindowStateChange" in change


def test_history_page_is_named_history_not_t2v() -> None:
    """History lists stills and video. The old T2V-prefixed class/file name is a lie."""
    old = "T2V" + "HistoryPage"
    header = ROOT / "qt_ui" / "HistoryPage.h"
    source = ROOT / "qt_ui" / "HistoryPage.cpp"
    assert header.is_file(), "HistoryPage.h is the product name"
    assert source.is_file(), "HistoryPage.cpp is the product name"
    assert not (ROOT / "qt_ui" / f"{old}.h").exists()
    assert not (ROOT / "qt_ui" / f"{old}.cpp").exists()
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "qt_ui/HistoryPage.cpp" in cmake
    assert f"qt_ui/{old}.cpp" not in cmake
    text = header.read_text(encoding="utf-8")
    assert "class HistoryPage" in text
    assert f"class {old}" not in text
    cpp = source.read_text(encoding="utf-8")
    assert 'setObjectName(QStringLiteral("HistoryPage"))' in cpp
    main = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
    assert '#include "HistoryPage.h"' in main
    assert "new HistoryPage(" in main
