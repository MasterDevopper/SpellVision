"""Custom dest uses hunt layout <prefix>/plate.png, not prefix_t2i_stamp."""
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "qt_ui" / "generation" / "OutputPathHelpers.cpp"
MAIN = Path(__file__).resolve().parents[1] / "qt_ui" / "MainWindow.cpp"


def test_hunt_layout_writes_plate_png() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "void resolveGenerationOutputPaths" in helper
    assert 'QStringLiteral("plate")' in helper
    hunt = helper.find("huntLayout")
    stamp = helper.find("yyyyMMdd_HHmmss_zzz")
    assert hunt > 0 and stamp > hunt


def test_mainwindow_uses_resolver_and_writes_prompt_txt() -> None:
    text = MAIN.read_text(encoding="utf-8")
    assert "resolveGenerationOutputPaths" in text
    assert "prompt.txt" in text


def test_salvage_copies_comfy_stem_underscore_png() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "bool salvageHuntPlate" in helper
    assert "_*.png" in helper
    catalog = Path(__file__).resolve().parents[1] / "qt_ui" / "ImageGenerationPage_catalog.cpp"
    text = catalog.read_text(encoding="utf-8")
    assert "salvageHuntPlate" in text
    assert "salvaged" in text
