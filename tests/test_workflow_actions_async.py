"""Workflow import and launch must use nonblocking worker transport."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
COORDINATOR = ROOT / "qt_ui" / "workflows" / "WorkflowDropCoordinator.cpp"


def _drop_path_source() -> str:
    """The workflow-drop import, wherever it lives.

    This check used to slice MainWindow.cpp between the ``workflowFileDropped`` connect and the next
    connect under it -- that is, it sliced a LAMBDA by its neighbours, and it went empty the moment
    the lambda became a function, with the property it describes completely intact. A grep anchored
    on what sits NEXT TO the code is measuring the neighbourhood, so this looks the implementation up
    by name, in both of its homes: MainWindow while the shell half lives there, and
    WorkflowDropCoordinator for the sequence itself.
    """
    parts = []
    if COORDINATOR.is_file():
        parts.append(COORDINATOR.read_text(encoding="utf-8"))
    if "MainWindow::importDroppedWorkflow" in SOURCE:
        parts.append(SOURCE.split("MainWindow::importDroppedWorkflow", 1)[1].split("\nvoid MainWindow::", 1)[0])
    assert parts, "no workflow-drop implementation found"
    return "\n".join(parts)


def test_workflow_drop_import_is_async_and_lifetime_safe() -> None:
    """Every hop of the drop sequence is nonblocking, and no completion can touch a dead object.

    The lifetime guard used to be a ``QPointer<ImageGenerationPage>`` because the whole import was a
    lambda that captured the cockpit it was going to write into. The sequence is four worker
    round-trips now, and the thing that can die under them is the COORDINATOR, so that is what the
    guard is on -- a stronger property than the old one, since the page is reached through a binding
    the coordinator owns rather than a raw pointer the completion holds.
    """
    body = _drop_path_source()
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(request" not in body

    coordinator = COORDINATOR.read_text(encoding="utf-8")
    # Every command the drop sends, and the two the old path never sent at all.
    for command in ("import_workflow", "compile_workflow_prompt", "check_workflow_launch_readiness"):
        assert f'QStringLiteral("{command}")' in coordinator, command
    # One guard per async hop: the import, the re-import after consent, the compile, the readiness.
    assert coordinator.count("QPointer<WorkflowDropCoordinator> guard(this)") >= 4
    assert "if (!guard)" in coordinator
    # Busy state is released on the way out of the sequence, not left spinning.
    assert "setBusy(false, QString())" in coordinator


def test_workflow_launch_is_async() -> None:
    body = SOURCE.split("void MainWindow::launchWorkflowProfileWithModel", 1)[1].split(
        "void MainWindow::applyWorkerQueueResponse", 1
    )[0]
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(request" not in body
    assert "applyWorkerQueueResponse(response);" in body
    assert "pollWorkerQueueStatus();" in body
