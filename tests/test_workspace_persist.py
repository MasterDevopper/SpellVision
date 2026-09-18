"""Last session persists on Generate — user's last settings, not a house default."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from cpp_source import definition_body  # noqa: E402
CATALOG = ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp"


def test_generate_persists_workspace_settings() -> None:
    # The Generate connection is made in the construction pass; find it by name, not by file.
    page = definition_body("buildUi", qualifier="ImageGenerationPage")
    assert "persistWorkspaceSettings();" in page
    gen = page.find("SubmitKind::Generate")
    persist = page.rfind("persistWorkspaceSettings();", 0, gen)
    assert persist > 0
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "void ImageGenerationPage::persistWorkspaceSettings()" in catalog
    assert "void ImageGenerationPage::saveSnapshot()" in catalog
    assert catalog.find("persistWorkspaceSettings()") < catalog.find("void ImageGenerationPage::saveSnapshot()")
