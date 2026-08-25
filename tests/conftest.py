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


def _send_request(
    host: str,
    port: int,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Send one request and return every JSON message the worker emits.

    Mirrors python/worker_client.py:
      * single-line JSON request, terminated with \\n
      * write side is shut down to signal end-of-request
      * server emits newline-delimited JSON until it closes the stream
    """
    messages: list[dict[str, Any]] = []
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
    # Force unbuffered output so we can read service stdout promptly on failure.
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, str(WORKER_SERVICE)],
        cwd=str(PYTHON_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        try:
            _wait_for_listener(host, port, timeout=60.0)
        except TimeoutError:
            proc.terminate()
            try:
                out, err = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
            raise AssertionError(
                "worker_service failed to start.\n"
                f"--- stdout ---\n{out.decode('utf-8', errors='replace')}\n"
                f"--- stderr ---\n{err.decode('utf-8', errors='replace')}"
            )

        yield {"host": host, "port": port, "process": proc}
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

    def _client(payload: dict[str, Any], *, timeout: float = 30.0) -> list[dict[str, Any]]:
        return _send_request(host, port, payload, timeout=timeout)

    return _client
