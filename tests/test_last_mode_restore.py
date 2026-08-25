"""Last visited mode is restored. First install has no lastModeId → Home."""
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "qt_ui" / "MainWindow.cpp"


def test_last_mode_is_persisted_and_restored() -> None:
    text = MAIN.read_text(encoding="utf-8")
    assert 'ui/lastModeId' in text
    assert "startMode = lastMode" in text
    persist = text.find('setValue(QStringLiteral("ui/lastModeId")')
    restore = text.find('value(QStringLiteral("ui/lastModeId")')
    assert restore > 0 and persist > restore
    assert 'if (!lastMode.isEmpty())' in text
