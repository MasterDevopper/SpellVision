"""App shutdown must never disrupt adopted or active Comfy work."""
import re
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


# --- what the three above do not cover ----------------------------------------------------------
#
# Those three say the teardown asks the server and that a non-Idle answer detaches. They do not say
# WHEN it asks, what it may spend asking, or that the one remaining kill is fenced behind both
# signals. Each case below is a way the guard could be wired that satisfies all three and still
# ends a render. The probe's own behaviour -- that nothing which fails resolves to Idle -- is held
# over a real socket in tests/cpp/test_comfy_exit_guard.cpp, because no source check can see it.


def test_our_own_busy_queue_detaches_without_spending_a_probe() -> None:
    """The local queue is trustworthy in one direction: when it says busy, we are busy, and no
    answer from the server can overturn that. So it stays as a short-circuit -- asking anyway would
    put a network round trip in front of a decision already made, on aboutToQuit of all places, and
    a probe that then timed out would resolve to Unknown and detach exactly as the local signal
    already said. Only its NEGATIVE was ever untrustworthy, and that is what the probe is for."""
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    assert body.count("probeComfyQueueState") == 1, "one probe, one ask"
    match = re.search(
        r"localQueueBusy\s*\?\s*spellvision::shell::ComfyQueueState::Busy", body)
    assert match, (
        "the local queue's Busy must short-circuit the probe: it belongs on the true arm, with "
        "the probe on the false one"
    )
    assert body.index("probeComfyQueueState") > match.start(), (
        "the probe is reached only when our own queue has nothing to say"
    )


def test_the_exit_probe_is_bounded_by_an_explicit_short_budget() -> None:
    """Exit is a deadline, not a lifetime. This runs on aboutToQuit, so the ask carries its own
    timeout rather than inheriting a default someone later widens for a generation path, and that
    timeout is short enough that a wedged ComfyUI cannot hold a quit open. A probe with no budget
    is not a safer guard -- it is a hang, and the user's answer to a hung quit is the task manager,
    which kills the render anyway."""
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    call = re.search(r"probeComfyQueueState\((?P<args>[^;]*?)\);", body, re.S)
    assert call, "the probe call should be readable"
    timeout_arg = call.group("args").split(",")[-1].strip()
    assert timeout_arg, "the probe must be given an explicit timeout, not the header's default"

    source = (ROOT / "qt_ui" / "MainWindow.cpp").read_text(encoding="utf-8")
    declared = re.search(
        r"constexpr int %s\s*=\s*(\d+);" % re.escape(timeout_arg), source)
    assert declared, f"{timeout_arg} should be a named constant in MainWindow.cpp"
    budget = int(declared.group(1))
    assert 0 < budget <= 2000, (
        f"the exit probe budget is {budget} ms; a quit may not wait that long on a backend that "
        "is not answering"
    )


def test_termination_is_fenced_behind_both_signals() -> None:
    """The one surviving kill. It must sit AFTER the non-Idle branch has returned, so the only way
    to reach it is an idle local queue and a server that said Idle itself. A terminate that ran
    before the branch, or a branch that fell through to it, would pass every assertion above and
    still be the original defect."""
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    assert body.count("->terminate()") == 1, "exactly one kill in the whole teardown"
    assert "->kill()" not in body, "exit never hard-kills an app-owned ComfyUI"
    gate = body.index("queueState != spellvision::shell::ComfyQueueState::Idle")
    kill = body.index("->terminate()")
    assert kill > gate, "the kill must come after the gate, not before it"
    assert "return;" in body[gate:kill], (
        "the non-Idle branch must RETURN; falling through to terminate() would make the gate "
        "decorative"
    )


def test_a_comfy_this_app_did_not_start_is_never_touched() -> None:
    """Ownership outranks every queue. An adopted ComfyUI -- one that was already running when the
    app came up, which is how the owner's own session runs -- is somebody else's process, so the
    function returns before it probes anything and long before anything is terminated. A guard
    that probed first would be harmless but wrong-shaped; one that terminated first is the bug
    this file exists for."""
    body = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    ownership_gate = body.index("if (!ownedProcess)")
    assert body.index("probeComfyQueueState") > ownership_gate
    assert body.index("->terminate()") > ownership_gate
    assert "return;" in body[ownership_gate:ownership_gate + 40], (
        "the ownership check must return, not merely branch"
    )
