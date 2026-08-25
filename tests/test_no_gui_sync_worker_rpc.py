"""No GUI request path may use synchronous or nested-event-loop worker RPC."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_dataset_and_gen3d_submissions_are_async() -> None:
    dataset = _between(MAIN, "generateDatasetRequested", "useWorkflowRequested")
    gen3d = _between(MAIN, "comfyGenerateRequested", "Seed workflow list")
    assert "sendWorkerRequestAsync(" in dataset
    assert "sendWorkerRequest(" not in dataset
    assert "QPointer<DatasetGenerationPage>" in dataset
    assert "sendWorkerRequestAsync(" in gen3d
    assert "sendWorkerRequest(" not in gen3d
    assert "QPointer<Gen3DPage>" in gen3d


def test_nested_worker_event_loop_is_removed() -> None:
    helper = _between(MAIN, "QJsonObject sendWorkerRequestForRuntime", "QHash<QString, QString> classifyModelsViaWorkerRuntime")
    assert "QEventLoop" not in helper
    assert "loop.exec()" not in helper
    assert "QProcess process" in helper
    assert "waitForFinished" in helper
    assert "#include <QEventLoop>" not in MAIN


def test_sync_mainwindow_worker_api_is_removed() -> None:
    assert "QJsonObject sendWorkerRequest(" not in HEADER
    assert "QJsonObject MainWindow::sendWorkerRequest(" not in MAIN
