"""Operating-point contract fetch must not block cockpit updates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")
PAGE_H = (ROOT / "qt_ui" / "ImageGenerationPage.h").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_operating_point_lookup_is_cache_only() -> None:
    body = _between(
        MAIN,
        "QJsonObject MainWindow::operatingPointsForFamily",
        "void MainWindow::sendWorkerRequestAsync",
    )
    assert "sendWorkerRequest(" not in body
    assert "sendWorkerRequestAsync(" not in body
    assert "operatingPointsByFamily_.value" in body


def test_operating_point_fetch_is_async_singleflight() -> None:
    assert "operatingPointsFetchInFlight_" in HEADER
    assert "operatingPointsFetchWaiters_" in HEADER
    body = _between(
        MAIN,
        "void MainWindow::fetchOperatingPointsAsync",
        "QJsonObject MainWindow::operatingPointsForFamily",
    )
    assert "sendWorkerRequestAsync(" in body
    assert "if (operatingPointsFetchInFlight_)" in body
    assert "operatingPointsFetchWaiters_" in body


def test_cockpit_refreshes_after_contract_arrives() -> None:
    assert "refreshOperatingPointSelector" in PAGE_H
    build = _between(MAIN, "void MainWindow::ensureGenerationPageBuilt", "void MainWindow::startIdlePagePrewarm")
    assert "fetchOperatingPointsAsync(" in build
    assert "QPointer<ImageGenerationPage>" in build
    assert "pageGuard->refreshOperatingPointSelector()" in build
