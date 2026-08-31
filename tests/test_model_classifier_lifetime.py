"""Background catalog classification must not retain or race QWidget state."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
SCANNER = (ROOT / "qt_ui" / "assets" / "AssetCatalogScanner.cpp").read_text(encoding="utf-8")


def test_installed_classifier_captures_only_runtime_values() -> None:
    install = MAIN.split("spellvision::assets::setModelFamilyClassifier(", 1)[1].split("buildShell();", 1)[0]
    assert "[this]" not in install
    assert "classifierProjectRoot" in install
    assert "classifierPythonExecutable" in install
    assert "classifyModelsViaWorkerRuntime" in install


def test_global_classifier_access_is_synchronized_and_copied() -> None:
    assert "QMutex g_modelFamilyClassifierMutex" in SCANNER
    setter = SCANNER.split("void setModelFamilyClassifier", 1)[1].split("QString normalizedExpertText", 1)[0]
    assert "QMutexLocker" in setter
    scan = SCANNER.split("QVector<CatalogEntry> scanImageModelCatalog", 1)[1]
    assert "ModelFamilyClassifier classifier" in scan
    assert "QMutexLocker" in scan
    assert "classifier(paths)" in scan
    assert "g_modelFamilyClassifier(paths)" not in scan
