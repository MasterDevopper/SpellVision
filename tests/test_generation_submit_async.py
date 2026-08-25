"""Visible generation submission must not block GUI on worker RPC."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def _function_body(start: str, end: str) -> str:
    return SOURCE.split(start, 1)[1].split(end, 1)[0]


def test_generation_submit_uses_async_worker_transport() -> None:
    body = _function_body(
        "void MainWindow::submitGenerationRequest",
        "void MainWindow::onWorkerQueueReachable",
    )
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(request" not in body
    assert "QPointer<ImageGenerationPage>" in body
    assert "pageGuard->setBusy(false" in body


def test_studio_correlation_is_registered_from_async_completion() -> None:
    assert "std::function<void(const QString &queueId" in HEADER
    body = _function_body(
        "void MainWindow::submitStudioGenerationRequest",
        "void MainWindow::syncStudioPreviewsFromQueue",
    )
    assert "QString queueId;" not in body
    assert "QString jobId;" not in body
    assert "[this, studio, comicPanelIndex, prefix]" in body
    assert "pendingStudioPreviews_.insert" in body
