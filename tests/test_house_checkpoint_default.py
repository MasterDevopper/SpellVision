"""First install does not pick a model. Recents only after the user chose one."""
from pathlib import Path

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
    igp = (Path(__file__).resolve().parents[1] / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")
    assert 'setSpecialValueText(QStringLiteral("—"))' in igp
    assert "setValue(isVideoMode() ? 832 : 1024)" not in igp
    assert "Choose a canvas size to generate." in text
    assert "Choose an output folder to generate." in text
    assert "Not set — Browse…" in igp
    assert "chooseComfyOutputPath()" not in igp.split("outputFolderLabel_ = new QLabel", 1)[-1][:200]
