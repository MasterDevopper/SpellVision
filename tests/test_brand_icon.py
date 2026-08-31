"""Brand icon ships with the exe and is preferred over the old jpg."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_brand_icon_is_wired() -> None:
    icons = ROOT / "qt_ui" / "icons"
    assert (icons / "SpellVision.ico").is_file()
    assert (icons / "SpellVision.png").is_file()
    assert (icons / "SpellVision_Dark.ico").is_file()
    assert (icons / "SpellVision_Dark.png").is_file()
    assert (icons / "SpellVision_Light.ico").is_file()
    assert (icons / "SpellVision_Light.png").is_file()
    assert (icons / "SpellVision.rc").is_file()
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "qt_ui/icons/SpellVision.rc" in cmake
    assert "SpellVision_Dark.png" in cmake
    assert "SpellVision_Light.png" in cmake
    main = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
    title = (ROOT / "qt_ui" / "CustomTitleBar.cpp").read_text(encoding="utf-8")
    assert "SpellVision_Dark" in main and "SpellVision_Light" in main
    assert "SpellVision_Dark" in title and "SpellVision_Light" in title
    assert "IvoryHolograph" in main and "IvoryHolograph" in title
