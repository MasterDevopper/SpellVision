"""Studio project/manifests must publish atomically."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "qt_ui" / "DurableJson.h"
FILES = {
    name: (ROOT / "qt_ui" / "studios" / name).read_text(encoding="utf-8")
    for name in ("CharacterStudioPage.cpp", "ComicStudioPage.cpp", "ConceptReferencePage.cpp")
}


def test_shared_json_writer_checks_full_write_and_commit() -> None:
    source = HEADER.read_text(encoding="utf-8")
    assert "QSaveFile" in source
    assert "file.write(data) != data.size()" in source
    assert "return file.commit();" in source


def test_user_authored_studio_json_uses_atomic_writer() -> None:
    assert FILES["CharacterStudioPage.cpp"].count("writeJsonAtomically(") >= 5
    assert FILES["ComicStudioPage.cpp"].count("writeJsonAtomically(") >= 2
    assert FILES["ConceptReferencePage.cpp"].count("writeJsonAtomically(") >= 1
    for source in FILES.values():
        assert "QIODevice::WriteOnly | QIODevice::Truncate" not in source
