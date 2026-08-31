"""KEEP/NO grading store must be writable and crash-durable."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "qt_ui" / "EyePickStore.cpp").read_text(encoding="utf-8")


def test_eye_picks_use_per_user_state_and_legacy_migration() -> None:
    assert "QStandardPaths::AppLocalDataLocation" in SOURCE
    assert 'qEnvironmentVariable("SPELLVISION_STATE_ROOT")' in SOURCE
    assert 'runtime/eye_picks.json' in SOURCE
    assert "legacyStorePath" in SOURCE


def test_eye_pick_save_and_export_are_atomic_and_checked() -> None:
    assert "QSaveFile file(path)" in SOURCE
    assert "file.write(data) != data.size()" in SOURCE
    assert "return file.commit();" in SOURCE
    export_body = SOURCE.split("bool EyePickStore::exportTo", 1)[1]
    assert "QSaveFile" in export_body
    assert "QFile::remove(dest)" not in export_body
