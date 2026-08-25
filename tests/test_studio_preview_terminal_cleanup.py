"""Terminal studio queue items must not leave Character/Comic/Concept busy forever."""
from pathlib import Path

CPP = (Path(__file__).resolve().parent.parent / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def test_terminal_studio_preview_without_output_has_bounded_settle_grace() -> None:
    body = CPP.split("void MainWindow::syncStudioPreviewsFromQueue()", 1)[1].split(
        "void MainWindow::appendLogLine", 1
    )[0]
    assert "kStudioOutputSettleMs" in CPP
    assert "Generation completed, but no output file was produced" in body
    assert "currentMSecsSinceEpoch" in body
    assert "QTimer::singleShot" in body
    assert "settleRetryScheduled" in body
    assert "correlationKeys" in body
    assert "clearStudioBusy(preview.studioMode" in body
    assert body.count("dropItemKeys(item, key);") >= 3
