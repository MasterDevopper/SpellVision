"""Shared pytest fixtures for SpellVision worker tests.

The worker_service is treated as a black-box subprocess. That is exactly how
the C++ shell talks to it, so the test surface matches the production surface.

Two fixtures are exposed:

  worker_service
      Session-scoped. Spawns python/worker_service.py on a free port and
      tears it down at session end. Yields {"host", "port", "process"}.

  worker_client
      Session-scoped. A callable that sends one JSON request to the worker
      and returns the full list of JSON messages it emits back. Mirrors the
      protocol used by python/worker_client.py.

Tests should depend on worker_client for almost everything; depend on the
raw worker_service fixture only if you need direct access to the subprocess
(for example, to inspect its stdout/stderr in a debugging test).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest


# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = PROJECT_ROOT / "python"
WORKER_SERVICE = PYTHON_DIR / "worker_service.py"


# ---------------------------------------------------------------------------
# Networking helpers (private; tests use the worker_client fixture)
# ---------------------------------------------------------------------------

def _pick_free_port() -> int:
    """Ask the OS for an unused TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_listener(host: str, port: int, timeout: float = 60.0) -> None:
    """Block until something is accepting connections at host:port.

    The worker loads torch / diffusers / comfy at import time, which can take
    several seconds on a cold start. We give it a generous default budget.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
    raise TimeoutError(
        f"worker service did not bind to {host}:{port} within {timeout:.1f}s "
        f"(last error: {last_error!r})"
    )


def _read_session_secret_file(path: str | None) -> str:
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("secret") or "").strip()
    except (OSError, ValueError):
        return ""


def _send_request(
    host: str,
    port: int,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
    session_file: str | None = None,
) -> list[dict[str, Any]]:
    """Send one request and return every JSON message the worker emits.

    Mirrors python/worker_client.py:
      * single-line JSON request, terminated with \\n
      * write side is shut down to signal end-of-request
      * server emits newline-delimited JSON until it closes the stream
    """
    messages: list[dict[str, Any]] = []
    # Present this worker's session secret unless the test deliberately sends its own (or none).
    secret = _read_session_secret_file(session_file)
    if secret and "session_secret" not in payload:
        payload = {**payload, "session_secret": secret}
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(timeout)

        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError(
                    f"worker did not produce a complete response within {timeout:.1f}s; "
                    f"messages so far: {messages}"
                ) from exc
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, _sep, buf = buf.partition(b"\n")
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError as exc:
                    raise AssertionError(
                        f"worker emitted non-JSON line: {line!r} ({exc})"
                    ) from exc
        if buf.strip():
            raise AssertionError(
                f"worker stream ended without a trailing newline; tail: {buf!r}"
            )
    return messages


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def worker_service() -> Iterator[dict[str, Any]]:
    """Spawn worker_service.py on a free port for the test session.

    Yields a dict with the host/port the worker is listening on, plus the
    underlying Popen handle so individual tests can read stdout/stderr if
    they need to debug a failure.
    """
    if not WORKER_SERVICE.exists():
        pytest.skip(
            f"worker_service.py not found at {WORKER_SERVICE}; "
            "adjust PYTHON_DIR in tests/conftest.py to match your layout."
        )

    port = _pick_free_port()
    host = "127.0.0.1"

    env = os.environ.copy()
    env["SPELLVISION_WORKER_HOST"] = host
    env["SPELLVISION_WORKER_PORT"] = str(port)
    # Isolate worker mutable state (queue manifest, job archive, history) from
    # the developer machine's real state root and from the repository checkout.
    env["SPELLVISION_STATE_ROOT"] = tempfile.mkdtemp(prefix="sv_test_state_")
    # The worker publishes a per-launch session secret; put this worker's in the same isolated
    # temp tree so it can never collide with the developer's real worker on 8765, and so the
    # client fixture below knows where to read it.
    session_file = os.path.join(tempfile.mkdtemp(prefix="sv_test_session_"), "worker_session.json")
    env["SPELLVISION_WORKER_SESSION_FILE"] = session_file
    # Force unbuffered output so we can read service stdout promptly on failure.
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, str(WORKER_SERVICE)],
        cwd=str(PYTHON_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Drain both pipes continuously instead of only at teardown.
    #
    # A PIPE nobody reads holds roughly 64 KB, and a process that fills it BLOCKS ON WRITE -- so a
    # worker that logs enough simply stops replying, mid-request, with no error anywhere. That is
    # not hypothetical: adding one WARNING to a path the runtime-status poll touches turned a 2.4s
    # test into a 30s timeout whose only symptom was "messages so far: []". The bug looked like the
    # worker and was the harness, which is the worst place for one to live.
    #
    # Draining also makes the captured output complete rather than truncated at the buffer, which is
    # what a failing test wants to read.
    captured: dict[str, list[bytes]] = {"stdout": [], "stderr": []}

    def _drain(stream, key: str) -> None:
        try:
            for chunk in iter(lambda: stream.read(4096), b""):
                captured[key].append(chunk)
        except (ValueError, OSError):
            pass  # the pipe is closed at teardown; nothing left to read

    drains = [
        threading.Thread(target=_drain, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for thread in drains:
        thread.start()

    def _captured(key: str) -> str:
        return b"".join(captured[key]).decode("utf-8", errors="replace")

    try:
        try:
            _wait_for_listener(host, port, timeout=60.0)
        except TimeoutError:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            for thread in drains:
                thread.join(timeout=2)
            raise AssertionError("\n".join([
                "worker_service failed to start.",
                "--- stdout ---", _captured("stdout"),
                "--- stderr ---", _captured("stderr"),
            ]))

        yield {"host": host, "port": port,
        "session_file": session_file, "process": proc, "output": _captured}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


@pytest.fixture(scope="session")
def worker_client(worker_service) -> Callable[..., list[dict[str, Any]]]:
    """A callable that sends one JSON request and returns all worker messages.

    Usage:
        def test_thing(worker_client):
            messages = worker_client({"command": "ping"})
            ...

    Optional kwargs: timeout (seconds, default 30).
    """
    host = worker_service["host"]
    port = worker_service["port"]
    session_file = worker_service.get("session_file")

    def _client(payload: dict[str, Any], *, timeout: float = 30.0) -> list[dict[str, Any]]:
        return _send_request(host, port, payload, timeout=timeout, session_file=session_file)

    return _client


# ---------------------------------------------------------------------------
# Ambient dependencies: declared by the fixture you use, enforced by a guard
# ---------------------------------------------------------------------------
#
# A test that reaches the live worker, ComfyUI or the internet depends on something this repo does
# not control. Those tests are legitimate and stay -- but they must SAY SO, or "the suite passes"
# stops meaning anything. Measured before this landed: 26% of test files had such a dependency,
# none of it declared, and a full run failed two tests purely because ComfyUI happened to be down.
#
# Two halves, and the second is the one that matters:
#
#   1. The marker is DERIVED from the fixtures a test requests. Asking authors to remember a
#      decorator would be a second resolver (Doc 50 rule 5) and it would drift from reality the
#      first time someone forgot.
#
#   2. For any test declaring no ambient marker, outbound connections raise. Forgetting is
#      therefore a FAILURE rather than a test that passes whenever the service is up -- which is
#      Doc 50 rule 4 applied to the test suite itself. Without this the marker set would rot
#      exactly the way the thing it is measuring did.

AMBIENT_MARKERS = ("needs_worker", "needs_comfy", "needs_network", "needs_gpu", "smoke")

# Fixtures that inherently mean "this test needs a live worker".
_WORKER_FIXTURES = frozenset({"worker_service", "worker_client"})


class AmbientDependencyError(RuntimeError):
    """A test reached the network without declaring that it would."""


def pytest_collection_modifyitems(config, items):
    """Derive needs_worker from the fixtures a test actually requests.

    The fixture IS the marker. Nothing to remember, and nothing to keep in step.
    """
    for item in items:
        if _WORKER_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.needs_worker)


def _port_of(address) -> int | None:
    """The port from a socket address, or None for address families that have none."""
    if isinstance(address, tuple) and len(address) >= 2 and isinstance(address[1], int):
        return address[1]
    return None


@pytest.fixture(autouse=True)
def _forbid_undeclared_ambient_dependencies(request):
    """Block outbound connections for tests that declare no ambient dependency.

    Guards ``connect``, not ``bind``: binding is how a test creates something, connecting is how it
    reaches for something it did not create.

    **A connection to a port this process bound is allowed.** Several tests stand up a loopback HTTP
    double and talk to it -- `test_comfy_object_info_transport` serves a real gzipped body to prove
    the transport handles it, which is exactly the kind of test worth having. That is hermetic by
    construction: the server is in this process and dies with it. Tracking bound ports distinguishes
    "I made this" from "I hope it is running" without asking anyone to annotate the difference, and
    it fails safe -- a port this process never bound is treated as ambient.

    The error names the address, because the useful question when this fires is which service the
    test was reaching for. The answer is either "add the marker" or "it did not mean to do that",
    and the second is the more interesting outcome.
    """
    if any(request.node.get_closest_marker(name) for name in AMBIENT_MARKERS):
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_bind = socket.socket.bind
    locally_bound: set[int] = set()

    def _bind(self, address, *args, **kwargs):
        result = real_bind(self, address, *args, **kwargs)
        try:
            # Read the port back from the socket rather than from the argument: binding to port 0
            # asks the OS to choose, and the chosen port is the one a client will connect to.
            locally_bound.add(self.getsockname()[1])
        except Exception:
            port = _port_of(address)
            if port:
                locally_bound.add(port)
        return result

    def _guarded(real):
        def _call(self, address, *args, **kwargs):
            if _port_of(address) in locally_bound:
                return real(self, address, *args, **kwargs)
            raise AmbientDependencyError(
                f"{request.node.nodeid} connected to {address!r} without declaring an ambient "
                "dependency. Mark it with @pytest.mark.needs_comfy / needs_network / needs_gpu "
                "(needs_worker is applied automatically from the worker fixtures), or remove the "
                "connection -- an undeclared dependency makes the suite pass or fail on what "
                "happens to be running."
            )
        return _call

    socket.socket.bind = _bind
    socket.socket.connect = _guarded(real_connect)
    socket.socket.connect_ex = _guarded(real_connect_ex)
    try:
        yield
    finally:
        socket.socket.bind = real_bind
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex


# --- a declared ambient dependency that is ABSENT should skip, not fail slowly -------------------

def _comfy_is_reachable(timeout: float = 1.0) -> bool:
    """Cheap TCP probe of the configured ComfyUI endpoint. Cached for the session."""
    global _COMFY_REACHABLE
    if _COMFY_REACHABLE is None:
        host, port = "127.0.0.1", 8188
        raw = os.environ.get("SPELLVISION_COMFY_PORT", "").strip()
        if raw.isdigit():
            port = int(raw)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                _COMFY_REACHABLE = True
        except OSError:
            _COMFY_REACHABLE = False
    return _COMFY_REACHABLE


_COMFY_REACHABLE: bool | None = None


@pytest.fixture(autouse=True)
def _skip_when_the_declared_service_is_absent(request):
    """A test that DECLARES it needs ComfyUI should skip when ComfyUI is not there.

    The guard above makes an UNDECLARED dependency loud. This is the other half, and it was missing:
    a declared one still ran, failed on a connection error, and said nothing about the service. With
    ComfyUI stopped the suite went from 41s to 294s and produced two failures that read as code
    breakage -- the actual cause, a service being down, appeared nowhere in the output.

    Deliberately a skip and not an xfail: the test is fine, the machine simply cannot run it. The
    reason names the endpoint, because the useful question when this appears is "should that be
    running?".

    Note the structural limit this exists to paper over. Both of the tests that exposed it reach
    ComfyUI *through the worker subprocess*, and an in-process socket guard cannot see a child
    process's connections -- so `needs_comfy` on a worker-mediated test can only ever be declared by
    hand. Worse, those two already carried `needs_worker` (derived automatically from the fixture),
    and the guard exempts a test that declares ANY ambient marker. Declaring the cheap dependency
    silently bought the expensive one.
    """
    if request.node.get_closest_marker("needs_comfy") and not _comfy_is_reachable():
        pytest.skip("ComfyUI is not reachable on 127.0.0.1:8188 -- start it to run this test")
    yield
