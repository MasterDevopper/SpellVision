"""Submission rejection paths must release the explicit telemetry busy latch."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPP = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    return CPP.split(start, 1)[1].split(end, 1)[0]


def test_submission_telemetry_has_one_reset_operation() -> None:
    assert "void resetSubmissionTelemetry();" in HEADER
    reset = _between(
        "void MainWindow::resetSubmissionTelemetry()",
        "void MainWindow::submitChainGenerationRequestAsync",
    )
    for property_name in (
        "svTelemetryBusy",
        "svTelemetryBusyMode",
        "svTelemetryBusyState",
        "svTelemetryPhaseRank",
        "svTelemetryProgressTarget",
        "svTelemetryJobActive",
        "svTelemetryCompletionPulse",
        "svTelemetryCompletedRowsAtSubmit",
        "svTelemetrySawActive",
    ):
        assert property_name in reset
    assert "syncBottomTelemetry();" in reset


def test_chain_rejections_after_latch_reset_telemetry() -> None:
    body = _between(
        "void MainWindow::submitChainGenerationRequestAsync",
        "void MainWindow::submitGenerationRequest",
    )
    assert body.count("resetSubmissionTelemetry();") >= 3


def test_page_rejections_after_latch_reset_telemetry() -> None:
    body = _between(
        "void MainWindow::submitGenerationRequest",
        "void MainWindow::onWorkerQueueReachable",
    )
    assert body.count("resetSubmissionTelemetry();") >= 3
    assert "if (!ok)" in body
    assert "if (!ok && !errorText.isEmpty())" not in body
