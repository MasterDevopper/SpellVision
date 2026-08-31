"""Confirmed worker loss terminalizes stale local work and releases busy UI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_H = (ROOT / "qt_ui" / "QueueManager.h").read_text(encoding="utf-8")
WORKER_H = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.h").read_text(encoding="utf-8")
WORKER_CPP = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.cpp").read_text(encoding="utf-8")
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def test_worker_controller_debounces_and_emits_confirmed_loss() -> None:
    assert "consecutivePollFailures_" in WORKER_H
    assert "hasSuccessfulPoll_" in WORKER_H
    assert "queueConnectivityLost" in WORKER_H
    assert "kConfirmedLossFailureCount" in WORKER_CPP
    assert "failNonterminalItems" in WORKER_CPP


def test_queue_manager_has_batch_terminalization_for_worker_loss() -> None:
    assert "failNonterminalItems" in QUEUE_H


def test_main_window_resets_explicit_telemetry_on_confirmed_loss() -> None:
    assert "queueConnectivityLost" in MAIN
    connection = MAIN.split("queueConnectivityLost", 1)[1][:900]
    assert "resetSubmissionTelemetry" in connection
    assert "Worker disappeared" in MAIN
