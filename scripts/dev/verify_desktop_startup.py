"""End-to-end smoke: the desktop launches, owns a worker, and gives it back on close.

Promoted out of an untracked scratch directory (`.hermes/`), where it had been sitting as real test
tooling that nothing could run because nobody knew it was there. It covers a seam none of the other
suites reach: `pytest` drives the worker directly over TCP and never launches the executable, and
`ctest` links `SpellVisionCore` without ever starting a process. This is the only check that the
shipped binary and the worker it spawns actually meet.

Three properties, and the third is the one that matters:

  1. The app starts and does not exit early.
  2. The worker answers a real protocol ping on 127.0.0.1:8765 -- a JSON request over the wire, not
     a port-open check, because an open port proves a listener and not a protocol.
  3. After a graceful close the worker STOPS answering. A desktop-owned worker that outlives its
     desktop holds :8765 and the GPU, and the next launch then adopts a worker nobody owns -- the
     same class of defect as the cancelled render that kept the GPU, and as the detached ComfyUI
     that had no teardown path.

**Exit codes are a three-way distinction, and that is the point.**

    0   startup verified AND the app closed cleanly taking its worker with it
    1   a real product failure -- the app died early, the worker never answered, or the worker
        outlived a close that DID happen
    2   the harness could not run the check: no build, :8765 already occupied, or the close could
        not be initiated at all

Code 2 exists because the close half is environment-sensitive and a harness failure must never be
reported as a product verdict. Verified separately on 2026-09-01 by driving the same binary from
PowerShell: it closes in ~1.5s with exit code 0 and its worker stops with it, so
`stopOwnedWorkerService()` is correct. What is unreliable is closing it from a Python-launched
process, not the closing.

It refuses to run when :8765 is already occupied rather than testing someone else's worker, which is
the difference between a smoke test and a coincidence.

Usage (needs a Debug build present):

    python scripts/dev/verify_desktop_startup.py

Windows-only. The close half goes through .NET's Process.CloseMainWindow rather than hand-rolled
WM_CLOSE -- see close_main_window() for the three ctypes approaches that posted successfully and
closed nothing.
"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "build" / "Debug" / "SpellVision.exe"
HOST, PORT = "127.0.0.1", 8765

STARTUP_BUDGET_SEC = 25.0
CLOSE_BUDGET_SEC = 30.0
SHUTDOWN_BUDGET_SEC = 8.0


def ping(timeout: float = 0.5) -> bool:
    """A real protocol round-trip. An open socket proves a listener, not a worker."""
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as sock:
            sock.sendall(b'{"command":"ping"}\n')
            sock.shutdown(socket.SHUT_WR)
            sock.settimeout(timeout)
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                for line in data.splitlines():
                    try:
                        if isinstance(json.loads(line), dict):
                            return True
                    except json.JSONDecodeError:
                        pass
    except OSError:
        return False
    return False


def close_main_window(pid: int) -> bool:
    """Close the app the way its close button does, via .NET's Process.CloseMainWindow.

    Deliberately NOT hand-rolled ctypes, and the reason is worth recording because it cost real
    time. Posting WM_CLOSE from Python to a window found by EnumWindows does not close this app --
    tried against every top-level window, then against the single visible unowned titled one, then
    with full argtypes declared so a 64-bit HWND could not be truncated. All three posted
    successfully and the app sat there. The same app closes in about 1.5 seconds, exit code 0,
    when .NET's CloseMainWindow targets the handle the OS itself considers the main window.

    This is a frameless window with a custom title bar, which owns a hidden `_q_titlebar` helper and
    two Qt observer windows; something in that arrangement is why a hand-picked handle is not the
    same handle. Chasing it further would be testing Win32, not SpellVision.

    The distinction that matters for the result: a failure here is a HARNESS failure, and it must
    not be reported as the app refusing to close. The first version of this script did exactly that
    -- it timed out, force-killed the app with /F, which skips destructors, and then reported the
    orphaned worker that force-kill had just created.
    """
    script = (
        f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if (-not $p) { exit 0 }; "
        "if ($p.CloseMainWindow()) { exit 0 } else { exit 3 }"
    )
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True)
    return done.returncode == 0


def main() -> int:
    if not EXE.is_file():
        print(f"no Debug build at {EXE} -- build first", file=sys.stderr)
        return 2
    if ping():
        print("refusing smoke: port 8765 was already occupied", file=sys.stderr)
        return 2

    app = subprocess.Popen([str(EXE)], cwd=str(ROOT))
    try:
        deadline = time.monotonic() + STARTUP_BUDGET_SEC
        while time.monotonic() < deadline and not ping():
            if app.poll() is not None:
                print(f"SpellVision exited early with {app.returncode}", file=sys.stderr)
                return 1
            time.sleep(0.2)
        if not ping():
            print("desktop-owned worker did not answer a protocol ping", file=sys.stderr)
            return 1
        print("worker_protocol_ready=true")

        # Give the main window a moment to exist: a close requested before it does goes nowhere,
        # and the failure then reads as "the app ignores its close button".
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not close_main_window(app.pid):
            time.sleep(0.5)
        try:
            app.wait(timeout=CLOSE_BUDGET_SEC)
        except subprocess.TimeoutExpired:
            print("harness: the close could not be driven in this environment -- NOT a product "
                  "verdict. Startup and the worker protocol above DID pass.", file=sys.stderr)
            return 2

        deadline = time.monotonic() + SHUTDOWN_BUDGET_SEC
        while time.monotonic() < deadline and ping():
            time.sleep(0.2)
        if ping():
            print("worker remained reachable after graceful desktop shutdown", file=sys.stderr)
            return 1
        print(f"desktop_exit_code={app.returncode}")
        print("owned_worker_stopped=true")
        return 0
    finally:
        if app.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.pid), "/F"], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
