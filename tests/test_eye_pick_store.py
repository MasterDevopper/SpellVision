"""Inspiration KEEP/NO store is registered and wired. No house auto-pin."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMAKE = ROOT / "CMakeLists.txt"
INSP = ROOT / "qt_ui" / "InspirationPage.cpp"
STORE = ROOT / "qt_ui" / "EyePickStore.cpp"


def test_eye_pick_store_is_in_cmake_and_page() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    assert "qt_ui/EyePickStore.cpp" in cmake
    assert STORE.is_file()
    text = INSP.read_text(encoding="utf-8")
    assert 'applyPick(QStringLiteral("keep"))' in text
    assert "runtime/eye_picks.json" in text
    assert "KEEP (K)" in text
    assert "Add hunt folder" in text
    assert "inspiration/extra_roots" in text
    assert "Pin teacher" in text
    assert "inspiration/teacher_still" in text
    assert "wrought_house_v1/images/002.png" not in text
    catalog = (ROOT / "qt_ui" / "OutputCardModel.cpp").read_text(encoding="utf-8")
    assert "setExtraRoots" in catalog
    assert "QDirIterator" in catalog
    assert "setNameNeedle" in catalog
    assert "huntPlateFilters" in catalog
    assert "plate.png" in catalog
    assert "return 800;" in catalog
    assert "userGenerationDestFolder" in catalog
    assert "fi.dir().dirName()" in catalog
    assert 'base.compare(QLatin1String("plate")' in catalog
    assert "InspLightbox" in text
    assert "setMinimumHeight(420)" in text
    assert "Qt::KeepAspectRatio" in text
    igp = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")
    assert "void ImageGenerationPage::chooseOutputFolder" in igp
    assert "image_generation/output_folder" in igp
    assert "void ImageGenerationPage::queueHuntList" in igp
    assert "stem | seed | prompt" in igp
    assert "skipped" in igp and "plate.png" in igp
    store = STORE.read_text(encoding="utf-8")
    hist = (ROOT / "qt_ui" / "T2VHistoryPage.cpp").read_text(encoding="utf-8")
    assert "pickStore_.load()" in text
    assert "pickStore_.load()" in hist
    assert "KEEP (K)" in hist
    assert "void T2VHistoryPage::applyPick" in hist
    assert "pickStore_.setMark" in hist
    assert '"picks"' in store or "picks" in store
    assert "keep" in store and "no" in store
    assert "Queue list…" in (ROOT / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")
    video = (ROOT / "qt_ui" / "ImageGenerationPage_video.cpp").read_text(encoding="utf-8")
    assert "applyKrea2002CanvasIfDefault" not in video
