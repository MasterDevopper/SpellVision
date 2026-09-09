"""T3: LoRA Manager teacher — rebuild thumbnail cache, not a vendored UI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_models_page_rebuilds_thumbnail_cache() -> None:
    cpp = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
    hdr = (ROOT / "qt_ui" / "ModelManagerPage.h").read_text(encoding="utf-8")
    cache = (ROOT / "qt_ui" / "assets" / "ModelThumbnailCache.h").read_text(encoding="utf-8")
    assert "Rebuild cache" in cpp
    assert "rebuildThumbnailCache" in hdr
    assert "void clear();" in cache or "void clear()" in cache
