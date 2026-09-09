"""ComfyUI WebSocket progress (Producer C).

Grounded in a live capture on 2026-09-09 against ComfyUI v0.34.0.
A 4-step KSampler emitted:

    {\"type\": \"progress\", \"data\": {\"value\": N, \"max\": 4, \"prompt_id\": ..., \"node\": \"8\"}}

`value`/`max` is the sampler step. `progress_state` exists too (per-node
value/max/state) but loaders are 0/1 and must not be treated as sampling
progress. `crystools.monitor` is GPU telemetry and is ignored.

The history poll at /history has no step data. This module is what stops
us emitting total=0 for a ComfyUI render that is already counting.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import uuid
from typing import Any
from urllib.parse import urlparse


def progress_from_message(msg: dict[str, Any], prompt_id: str) -> tuple[int, int] | None:
    if not isinstance(msg, dict) or msg.get("type") != "progress":
        return None
    data = msg.get("data")
    if not isinstance(data, dict):
        return None
    if str(data.get("prompt_id") or "") != str(prompt_id or ""):
        return None
    value = data.get("value")
    maxv = data.get("max")
    if not isinstance(value, (int, float)) or not isinstance(maxv, (int, float)):
        return None
    if maxv <= 0:
        return None
    return int(value), int(maxv)


def steps_from_frames(
    timed_frames: list[tuple[float, dict[str, Any]]],
    prompt_id: str,
    now: float | None = None,
) -> tuple[int, int] | None:
    """Last sampler step in the capture. `now` is accepted so an interpolator
    that used wall time would compile — and the test asserts we do not invent a step from it.
    """
    last: tuple[int, int] | None = None
    for t, frame in timed_frames:
        if now is not None and t > now:
            continue
        got = progress_from_message(frame, prompt_id)
        if got is not None:
            last = got
    return last


class ComfyProgressSocket:
    """Background reader. latest() is (step, total) or None until a progress frame."""

    def __init__(self, api_url: str, prompt_id: str) -> None:
        self.api_url = str(api_url or "").rstrip("/")
        self.prompt_id = str(prompt_id)
        self._lock = threading.Lock()
        self._latest: tuple[int, int] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def latest(self) -> tuple[int, int] | None:
        with self._lock:
            return self._latest

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="comfy-progress-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _note(self, msg: dict[str, Any]) -> None:
        got = progress_from_message(msg, self.prompt_id)
        if got is None:
            return
        with self._lock:
            self._latest = got

    def _run(self) -> None:
        try:
            parsed = urlparse(self.api_url if "://" in self.api_url else f"http://{self.api_url}")
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 8188)
            sock = _connect_ws(host, port)
            sock.settimeout(1.0)
            try:
                while not self._stop.is_set():
                    try:
                        opcode, payload = _read_ws_frame(sock)
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    if opcode == 0x8:
                        break
                    if opcode != 0x1:
                        continue
                    try:
                        msg = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(msg, dict):
                        self._note(msg)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
        except Exception:
            return


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def _read_ws_frame(sock: socket.socket) -> tuple[int, bytes]:
    hdr = _recv_exact(sock, 2)
    opcode = hdr[0] & 0x0F
    masked = hdr[1] & 0x80
    length = hdr[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    if masked:
        mask = _recv_exact(sock, 4)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(_recv_exact(sock, length)))
    else:
        payload = _recv_exact(sock, length)
    return opcode, payload


def _connect_ws(host: str, port: int) -> socket.socket:
    client_id = str(uuid.uuid4())
    path = f"/ws?clientId={client_id}"
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock = socket.create_connection((host, port), 15)
    sock.sendall(req.encode("ascii"))
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("no websocket handshake")
        header += chunk
    status = header.split(b"\r\n", 1)[0].decode("ascii", "replace")
    if "101" not in status:
        raise RuntimeError(f"websocket handshake failed: {status}")
    return sock
