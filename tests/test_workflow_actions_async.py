"""Workflow import and launch must use nonblocking worker transport."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")


def test_workflow_drop_import_is_async_and_lifetime_safe() -> None:
    body = SOURCE.split("workflowFileDropped", 1)[1].split("prepForI2IRequested", 1)[0]
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(request" not in body
    assert "QPointer<ImageGenerationPage>" in body
    assert "pageGuard->setBusy(false" in body


def test_workflow_launch_is_async() -> None:
    body = SOURCE.split("void MainWindow::launchWorkflowProfileWithModel", 1)[1].split(
        "void MainWindow::applyWorkerQueueResponse", 1
    )[0]
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(request" not in body
    assert "applyWorkerQueueResponse(response);" in body
    assert "pollWorkerQueueStatus();" in body
