"""Operating-point contract fetch must not block cockpit updates.

Sliced by NAME PAIR until 2026-09-17, and that is how it broke: each body was
``text.split(this function).split(the function that happened to follow it)``, so the assertions
about ``operatingPointsForFamily`` were really assertions about everything between it and
``sendWorkerRequestAsync``. W2 landed ``fetchModelDefaultsAsync`` in that gap -- a function which
legitimately calls the worker -- and the rule reported that the cache-only lookup had grown a fetch.
It had not; the slice had grown a neighbour.

``cpp_source.definition_body`` brace-matches instead, so the end of a function is its closing brace
rather than whichever definition is written next. That is the whole reason that helper exists
(tests/cpp_source.py), and this file is the fourth test to have been caught by not using it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "qt_ui" / "MainWindow.h").read_text(encoding="utf-8")
PAGE_H = (ROOT / "qt_ui" / "ImageGenerationPage.h").read_text(encoding="utf-8")


def test_operating_point_lookup_is_cache_only() -> None:
    """The lookup is called from paint/layout paths, where a worker round-trip is a freeze. It
    answers from the table it already holds, or it answers empty -- it never fetches."""
    body = definition_body("operatingPointsForFamily", qualifier="MainWindow")
    assert "sendWorkerRequest(" not in body
    assert "sendWorkerRequestAsync(" not in body
    assert "operatingPointsByFamily_.value" in body


def test_operating_point_fetch_is_async_singleflight() -> None:
    assert "operatingPointsFetchInFlight_" in HEADER
    assert "operatingPointsFetchWaiters_" in HEADER
    body = definition_body("fetchOperatingPointsAsync", qualifier="MainWindow")
    assert "sendWorkerRequestAsync(" in body
    assert "if (operatingPointsFetchInFlight_)" in body
    assert "operatingPointsFetchWaiters_" in body


def test_cockpit_refreshes_after_contract_arrives() -> None:
    assert "refreshOperatingPointSelector" in PAGE_H
    build = definition_body("ensureGenerationPageBuilt", qualifier="MainWindow")
    assert "fetchOperatingPointsAsync(" in build
    assert "QPointer<ImageGenerationPage>" in build
    assert "pageGuard->refreshOperatingPointSelector()" in build
