"""Comfy teardown stops only the QProcess launched by this MainWindow session."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPP = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def _body(start: str, end: str) -> str:
    return CPP.split(start, 1)[1].split(end, 1)[0]


def test_comfy_state_and_logs_use_per_user_writable_storage() -> None:
    write_body = _body(
        "bool MainWindow::writeComfySessionFile",
        "void MainWindow::ensureComfyRuntimeAvailable",
    )
    ensure_body = _body(
        "void MainWindow::ensureComfyRuntimeAvailable",
        "void MainWindow::buildShell",
    )
    assert "QStandardPaths::AppLocalDataLocation" in CPP
    assert "QSaveFile" in CPP
    assert 'filePath(QStringLiteral("build"))' not in write_body
    assert "comfyRuntimeStateRoot" in ensure_body


def test_comfy_teardown_uses_only_owned_qprocess() -> None:
    body = _body("void MainWindow::tearDownComfyOnExit", "QString MainWindow::workerTaskCommandForMode")
    assert "ownedComfyProcess_" in body
    assert "taskkill" not in body
    assert "stop_comfy_runtime" not in body
    assert "adopted_existing" not in body
    assert "processIsAlive" not in body
