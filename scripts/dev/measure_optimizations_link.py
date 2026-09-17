"""The worker socket the harness measures through.

Ruling W3-P2: run through the worker, not around it. ``scripts/dev/wrought_comfy.py`` and
``runtime/night_run.py`` both talk to ComfyUI directly, and that is precisely why their numbers
never reached a sidecar -- a timing taken outside the product is a timing about ComfyUI, not about
SpellVision. Every render here goes over ``127.0.0.1:8765`` as a normal job, so each row is also a
real job with a sidecar and an ``optimizations`` block of its own.

Deliberately thin: one request/response helper, one restart, one render. The harness owns the
sequencing; this owns the wire.
"""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
PORT = 8765

# The worker publishes a per-launch session secret (security pass v1). A client that did not spawn
# the worker finds it here; without it every request is refused.
SESSION_FILE_ENV = "SPELLVISION_WORKER_SESSION_FILE"


def session_secret(path: str | Path | None) -> str:
    if not path:
        return ""
    try:
        return str(json.loads(Path(path).read_text(encoding="utf-8")).get("secret") or "").strip()
    except (OSError, ValueError):
        return ""


def request(
    payload: dict[str, Any],
    *,
    host: str = HOST,
    port: int = PORT,
    timeout: float = 1800.0,
    secret: str = "",
) -> list[dict[str, Any]]:
    """Send one request; return every JSON message the worker emits before it closes.

    The timeout is generous by default because a single cell of this matrix is a full render, and a
    harness that gives up at 30 s would report a timeout as a measurement.
    """
    if secret and "session_secret" not in payload:
        payload = {**payload, "session_secret": secret}
    messages: list[dict[str, Any]] = []
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(timeout)
        buffer = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, _sep, buffer = buffer.partition(b"\n")
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line.decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
    return messages


def restart_into_arm(arm: dict[str, Any] | None, **kwargs) -> dict[str, Any]:
    """Restart ComfyUI into ``arm`` and return the ack -- whose ``argv`` is what actually launched.

    The reply is returned WHOLE, argv included, rather than reduced to ok/not-ok: the caller's job
    is to check that the arm took, and it cannot do that from a boolean.
    """
    payload: dict[str, Any] = {"command": "restart_comfy_runtime", "startup_timeout_sec": 180}
    payload.update(arm or {})
    for message in request(payload, **kwargs):
        if message.get("type") == "comfy_runtime_ack":
            return message
    return {"ok": False, "error": "no comfy_runtime_ack in the restart reply"}


def render(job_request: dict[str, Any], **kwargs) -> tuple[float, dict[str, Any]]:
    """Run one render and return ``(wall_seconds, the terminal message)``.

    Wall time is measured HERE, around the whole request, and the worker's own
    ``generation_time_sec`` comes back in the terminal message. The two are both recorded; where
    they disagree, the gap is queue and model-load time, which is exactly what "cold" means.
    """
    started = time.perf_counter()
    messages = request(job_request, **kwargs)
    elapsed = time.perf_counter() - started
    terminal: dict[str, Any] = {}
    for message in messages:
        if message.get("state") in {"completed", "failed", "cancelled"} or message.get("type") in {"result", "error"}:
            terminal = message
    return elapsed, terminal
