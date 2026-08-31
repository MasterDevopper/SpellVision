"""End-to-end smoke: the desktop launches, owns a worker, and gives it back on close.

Promoted out of an untracked scratch directory (`.hermes/`), where it had been sitting as real test
tooling that nothing could run because nobody knew it was there. It covers a seam none of the other
suites reach: `pytest` drives the worker directly over TCP and never launches the executable, and
`ctest` links `SpellVisionCore` without ever starting a process. This is the only check that the
shipped binary and the worker it spawns actually meet.

Three properties, and the third is the one that matters:

  1. The app starts and does not exit early.
  2. Within 15s the worker answers a real protocol ping on 127.0.0.1:8765 -- a JSON request over the
     wire, not a port-open check, because an open port proves a listener and not a protocol.
  3. After a graceful WM_CLOSE the worker STOPS answering. A desktop-owned worker that outlives its
     desktop holds :8765 and the GPU, and the next launch then adopts a worker nobody owns -- which
     is the same class of defect as the cancelled render that kept the GPU, and as the detached
     ComfyUI that had no teardown path.

It refuses to run when :8765 is already occupied rather than testing someone else's worker, which is
the difference between a smoke test and a coincidence.

Usage (needs a Debug build present):

    python scripts/dev/verify_desktop_startup.py

Exits non-zero with a named reason on any failure. Windows-only: the graceful-close half uses
WM_CLOSE via user32, because that is the path a user actually takes and the one with the teardown
bug in it.
"""
import ctypes
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "build" / "Debug" / "SpellVision.exe"
HOST, PORT = "127.0.0.1", 8765

STARTUP_BUDGET_SEC = 15.0
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


def close_windows(pid: int) -> None:
    """WM_CLOSE every top-level window owned by pid -- the path a user takes."""
    user32 = ctypes.windll.user32
    wm_close = 0x0010

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        window_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            user32.PostMessageW(hwnd, wm_close, 0, 0)
        return True

    user32.EnumWindows(callback, 0)


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

        # Twice: the first close can land while the window is still coming up.
        close_windows(app.pid)
        time.sleep(0.5)
        close_windows(app.pid)
        app.wait(timeout=10)

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
