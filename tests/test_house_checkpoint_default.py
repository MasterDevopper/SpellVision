"""First install does not pick a model. Recents only after the user chose one."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body  # noqa: E402

CATALOG = Path(__file__).resolve().parents[1] / "qt_ui" / "ImageGenerationPage_catalog.cpp"


def test_t2i_empty_selection_has_no_house_unet_rank() -> None:
    text = CATALOG.read_text(encoding="utf-8")
    assert "houseImageCheckpointRank" not in text
    assert "preferredDefaultImageCheckpoint" not in text
    assert "loxsuptopicworldkrea2_v10bf16" not in text.lower()
    assert "lastUserImageCheckpoint" in text
    assert "lastUserRecentSelection" in text
    assert "image_generation/recent_checkpoints" in text
    assert "image_generation/recent_video_model_stacks" in text
    assert "return CatalogEntry{};" in text
    assert "entries.first()" not in text
    assert "modelEntries.first()" not in text
    assert "modelDisplayByValue_.firstKey()" not in text
    apply_preset = text[text.find("void ImageGenerationPage::applyPreset") : text.find("void ImageGenerationPage::updatePrimaryActionAvailability")]
    if "void ImageGenerationPage::updatePrimaryActionAvailability" not in text:
        apply_preset = text[text.find("void ImageGenerationPage::applyPreset") :]
    assert "trySetSelectedModelByCandidate" not in apply_preset
    assert "No checkpoint selected" in text
    assert "F:/AI_ASSETS" not in text
    # These four are about what CONSTRUCTION writes into the canvas and output controls, which is
    # why they must not widen to the whole family: resetToDefaults() legitimately writes a canvas
    # pair, and it is a user action, not a house default shipped in the built page.
    igp = definition_body("buildUi", qualifier="ImageGenerationPage")
    assert 'setSpecialValueText(QStringLiteral("—"))' in igp
    assert "setValue(isVideoMode() ? 832 : 1024)" not in igp
    assert "Choose a canvas size to generate." in text
    assert "Choose an output folder to generate." in text
    assert "Not set — Browse…" in igp
    assert "chooseComfyOutputPath()" not in igp.split("outputFolderLabel_ = new QLabel", 1)[-1][:200]
