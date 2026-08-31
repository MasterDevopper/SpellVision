"""Application startup must not spin or block before the shell is built."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def _body(start: str, end: str) -> str:
    return SOURCE.split(start, 1)[1].split(end, 1)[0]


def test_worker_startup_is_signal_driven() -> None:
    body = _body(
        "void MainWindow::ensureWorkerServiceAvailable()",
        "void MainWindow::stopOwnedWorkerService()",
    )
    assert "waitForStarted" not in body
    assert "QCoreApplication::processEvents" not in body
    assert "QThread::msleep" not in body
    assert "while (startup.elapsed()" not in body
    assert "QProcess::errorOccurred" in body
    assert "QProcess::FailedToStart" in body


def test_comfy_startup_is_signal_driven() -> None:
    body = _body(
        "void MainWindow::ensureComfyRuntimeAvailable()",
        "void MainWindow::buildShell()",
    )
    assert "waitForStarted" not in body
    assert "QProcess::errorOccurred" in body
    assert "QProcess::FailedToStart" in body
    assert "&QProcess::started" in body
