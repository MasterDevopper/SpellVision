"""Queue polling must not re-enter through nested GUI event processing."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "qt_ui" / "workers" / "WorkerQueueController.cpp").read_text(encoding="utf-8")


def test_queue_poll_is_single_flight_for_all_terminal_paths() -> None:
    assert "bool pollInFlight_ = false;" in HEADER
    body = SOURCE.split("bool WorkerQueueController::pollOnce()", 1)[1].split(
        "void WorkerQueueController::startPolling", 1
    )[0]
    guard_pos = body.index("if (pollInFlight_)")
    request_pos = body.index("bindings_.sendRequestAsync(\n")
    assert guard_pos < request_pos
    assert body.index("pollInFlight_ = true;") < request_pos
    assert "pollInFlight_ = false;" in body
    # One availability check plus primary and secondary async calls.
    assert body.count("bindings_.sendRequestAsync") == 3
