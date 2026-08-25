"""Video component-stack resolution must not block model selection."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
PAGE_H = (ROOT / "qt_ui" / "ImageGenerationPage.h").read_text(encoding="utf-8")
VIDEO = (ROOT / "qt_ui" / "ImageGenerationPage_video.cpp").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_mainwindow_component_resolver_is_async() -> None:
    body = _between(
        MAIN,
        "MainWindow::resolveComponentStackViaWorker",
        "QJsonObject MainWindow::operatingPointsForFamily",
    )
    assert "sendWorkerRequestAsync(" in body
    assert "sendWorkerRequest(" not in body
    assert "completion(" in body


def test_page_rejects_stale_component_resolution() -> None:
    body = _between(
        VIDEO,
        "void ImageGenerationPage::maybeAutoPopulateVideoComponents",
        "void ImageGenerationPage::applyVideoAutoPopulateToCombos",
    )
    assert "componentResolveGeneration_" in PAGE_H
    assert "++componentResolveGeneration_" in body
    assert "generation != pageGuard->componentResolveGeneration_" in body
    assert "QPointer<ImageGenerationPage>" in body
    assert "componentStackResolver_(" in body
    assert "applyResolvedVideoComponents" in body
