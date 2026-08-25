"""App-owned runtimes must not remain indefinitely unready after process start."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_worker_has_nonblocking_readiness_deadline() -> None:
    body = _between(MAIN, "void MainWindow::ensureWorkerServiceAvailable", "void MainWindow::stopOwnedWorkerService")
    assert "kWorkerReadinessDeadlineMs" in body
    assert "QTimer::singleShot(kWorkerReadinessDeadlineMs, process" in body
    assert "workerReachable_" in body
    assert "process->terminate()" in body
    assert "waitForFinished" not in body


def test_comfy_has_nonblocking_readiness_deadline() -> None:
    body = _between(MAIN, "void MainWindow::ensureComfyRuntimeAvailable", "void MainWindow::buildShell")
    assert "kComfyReadinessDeadlineMs" in body
    assert "QTimer::singleShot(kComfyReadinessDeadlineMs, process" in body
    assert "comfyReachable_" in body
    assert "process->terminate()" in body
    assert "waitForFinished" not in body


def test_readiness_timeout_escalates_without_blocking_gui() -> None:
    assert "kRuntimeTerminateGraceMs" in MAIN
    assert "QTimer::singleShot(kRuntimeTerminateGraceMs, process" in MAIN
    assert "process->kill()" in MAIN
    assert "failed to become ready" in MAIN
