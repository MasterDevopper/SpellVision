"""App shutdown must never disrupt adopted or active Comfy work."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
RUNTIME_H = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.h").read_text(encoding="utf-8")
RUNTIME_CPP = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_teardown_checks_ownership_before_touching_comfy() -> None:
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    ownership = body.index("QProcess *ownedProcess = ownedComfyProcess_")
    assert "sendWorkerRequest" not in body
    assert body.index("if (!ownedProcess)") > ownership
    assert "probeComfyQueueState" in body
    assert "ComfyQueueState::Idle" in body


def test_busy_or_unknown_owned_comfy_is_detached() -> None:
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    assert "queueState != spellvision::shell::ComfyQueueState::Idle" in body
    assert "ownedProcess->setParent(nullptr)" in body
    assert "ownedComfyProcess_ = nullptr" in body


def test_comfy_queue_probe_is_tristate_and_bounded() -> None:
    assert "enum class ComfyQueueState" in RUNTIME_H
    assert "Unknown" in RUNTIME_H and "Idle" in RUNTIME_H and "Busy" in RUNTIME_H
    body = _between(RUNTIME_CPP, "ComfyQueueState probeComfyQueueState", "QString resolvePreferredComfyRoot")
    assert 'GET /queue HTTP/1.1' in body
    assert 'queue_running' in body
    assert 'queue_pending' in body
    assert "1024 * 1024" in body
    assert "ComfyQueueState::Unknown" in body
