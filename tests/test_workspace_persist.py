"""Last session persists on Generate — user's last settings, not a house default."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
CATALOG = ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp"


def test_generate_persists_workspace_settings() -> None:
    page = PAGE.read_text(encoding="utf-8")
    assert "persistWorkspaceSettings();" in page
    gen = page.find("SubmitKind::Generate")
    persist = page.rfind("persistWorkspaceSettings();", 0, gen)
    assert persist > 0
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "void ImageGenerationPage::persistWorkspaceSettings()" in catalog
    assert "void ImageGenerationPage::saveSnapshot()" in catalog
    assert catalog.find("persistWorkspaceSettings()") < catalog.find("void ImageGenerationPage::saveSnapshot()")
