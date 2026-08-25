"""User-facing Qt copy must not send people back to run_ui.ps1."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "qt_ui"


def test_qt_ui_does_not_tell_users_to_run_ui_ps1() -> None:
    hits = []
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in {".cpp", ".h", ".ui"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "run_ui.ps1" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"run_ui.ps1 leftovers in UI: {hits}"
