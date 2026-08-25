"""Ctrl+K lists visible rail pages. Chain and Gen3D stay gated."""
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "qt_ui" / "MainWindow.cpp"
NAV = Path(__file__).resolve().parents[1] / "qt_ui" / "shell" / "ShellNavigationController.cpp"


def test_palette_includes_rail_pages_missing_from_old_nav_block() -> None:
    text = MAIN.read_text(encoding="utf-8")
    start = text.find("void MainWindow::populatePaletteTopLevel")
    assert start > 0
    block = text[start : start + 8000]
    for needle in (
        "nav.dataset",
        "nav.inspiration",
        "nav.runtime",
        "nav.train",
    ):
        assert needle in block, f"palette missing {needle}"
    assert "nav.chain" in block
    assert 'isModeHidden(QStringLiteral("chain"))' in block
    assert "nav.gen3d" in block
    assert 'isModeHidden(QStringLiteral("gen3d"))' in block
    nav = NAV.read_text(encoding="utf-8")
    hidden = nav[nav.find("kV1HiddenModes") : nav.find("return kV1HiddenModes")]
    assert 'QStringLiteral("chain")' in hidden
    assert 'QStringLiteral("gen3d")' in hidden
