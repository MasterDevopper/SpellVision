"""Cockpit catalog traversal and classification stay off the GUI thread."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "qt_ui" / "ImageGenerationPage.h").read_text(encoding="utf-8")
CATALOG = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")
PAGE = (ROOT / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")


def test_full_catalog_refresh_runs_on_immutable_background_inputs() -> None:
    assert "QFutureWatcher<CatalogRefreshResult>" in HEADER
    assert "static CatalogRefreshResult scanCatalogs" in HEADER
    refresh = CATALOG.split("void ImageGenerationPage::refreshModelCatalog()", 1)[1].split(
        "QString ImageGenerationPage::catalogSignature", 1
    )[0]
    assert "QtConcurrent::run" in refresh
    assert "[modelsRoot, videoMode]" in refresh
    assert "[this]" not in refresh
    assert "rescanModelCatalog();" not in refresh


def test_catalog_results_are_applied_on_watcher_completion() -> None:
    assert "applyCatalogRefreshResult" in HEADER
    assert "onCatalogRefreshFinished" in HEADER
    assert "&QFutureWatcher<CatalogRefreshResult>::finished" in PAGE
    apply_body = CATALOG.split("void ImageGenerationPage::applyCatalogRefreshResult", 1)[1]
    assert "scanImageModelCatalog" not in apply_body.split("void ImageGenerationPage::", 1)[0]
    assert "scanVideoModelStackCatalog" not in apply_body.split("void ImageGenerationPage::", 1)[0]


def test_navigation_signature_probe_is_backgrounded() -> None:
    assert "QFutureWatcher<QString> *catalogSignatureWatcher_" in HEADER
    show = PAGE.split("void ImageGenerationPage::showEvent", 1)[1].split(
        "void ImageGenerationPage::resizeEvent", 1
    )[0]
    assert "catalogSignature(chooseModelsRootPath())" not in show
    assert "checkCatalogSignatureAsync();" in show
