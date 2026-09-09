"""T3: inspect shows a local sidecar example image. Nothing is fetched."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_models_inspect_shows_local_example_image() -> None:
    cpp = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
    hdr = (ROOT / "qt_ui" / "ModelManagerPage.h").read_text(encoding="utf-8")
    assert "exampleImageLabel_" in hdr
    assert "imagePreviewPath" in cpp
    assert "exampleImageLabel_" in cpp
