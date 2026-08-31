"""Visible queue polling must never run worker RPC through nested event loop."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.cpp").read_text(encoding="utf-8")
MAIN_H = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def test_queue_controller_uses_async_request_contract() -> None:
    assert "sendRequestAsync" in HEADER
    assert "std::function<QJsonObject(const QJsonObject &request" not in HEADER
    body = SOURCE.split("bool WorkerQueueController::pollOnce()", 1)[1].split(
        "void WorkerQueueController::startPolling", 1
    )[0]
    assert "sendRequestAsync" in body
    assert "QEventLoop" not in body
    assert "pollInFlight_ = false;" in body


def test_main_window_queue_binding_uses_async_process_path() -> None:
    assert "void sendWorkerRequestAsync(" in MAIN_H
    constructor = MAIN.split("workerQueueController_ =", 1)[1].split(
        "workerQueueController_->bind", 1
    )[0]
    assert "queueBindings.sendRequestAsync" in constructor
    assert "sendWorkerRequestAsync(request" in constructor
    async_body = MAIN.split("void MainWindow::sendWorkerRequestAsync", 1)[1].split(
        "QJsonObject MainWindow::sendWorkerRequest", 1
    )[0]
    assert "QEventLoop" not in async_body
    assert "QProcess::started" in async_body
    assert "QProcess::finished" in async_body
    assert "QTimer::timeout" in async_body
