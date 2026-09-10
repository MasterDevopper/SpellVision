"""T3: Models page shows metadata model_name. File on disk is unchanged."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_models_page_uses_metadata_display_name() -> None:
    cpp = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
    hdr = (ROOT / "qt_ui" / "ModelManagerPage.h").read_text(encoding="utf-8")
    assert "displayName" in hdr
    assert "meta.modelName" in cpp
    assert "c.strippedName = display" in cpp or "displayName" in cpp
    # Handoff to generation stays the filename.
    assert "c.modelValue = e.name" in cpp
