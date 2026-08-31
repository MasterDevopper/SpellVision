"""Custom dest uses hunt layout <prefix>/plate.png, not prefix_t2i_stamp."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

HELPER = Path(__file__).resolve().parents[1] / "qt_ui" / "generation" / "OutputPathHelpers.cpp"
MAIN = Path(__file__).resolve().parents[1] / "qt_ui" / "MainWindow.cpp"


def test_hunt_layout_writes_plate_png() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "void resolveGenerationOutputPaths" in helper
    assert 'QStringLiteral("plate")' in helper
    hunt = helper.find("huntLayout")
    stamp = helper.find("yyyyMMdd_HHmmss_zzz")
    assert hunt > 0 and stamp > hunt


def test_the_generation_request_uses_the_resolver_and_writes_prompt_txt() -> None:
    # Asserted against the BUILDER, found by name, rather than against whichever file currently
    # holds it. This test named MainWindow.cpp and broke when the 200-line builder moved into its
    # own translation unit -- a refactor that changed no behaviour.
    builder = definition_body("buildWorkerGenerationRequest")
    assert "resolveGenerationOutputPaths" in builder
    assert "prompt.txt" in builder


def test_salvage_copies_comfy_stem_underscore_png() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "bool salvageHuntPlate" in helper
    assert "_*.png" in helper
    catalog = Path(__file__).resolve().parents[1] / "qt_ui" / "ImageGenerationPage_catalog.cpp"
    text = catalog.read_text(encoding="utf-8")
    assert "salvageHuntPlate" in text
    assert "salvaged" in text
