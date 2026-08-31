"""Malformed TCP frames fail closed with a typed response and keep the worker alive."""
from __future__ import annotations

import json
import socket
from typing import Any


def _send_raw(worker_service: dict[str, Any], payload: bytes) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    with socket.create_connection(
        (worker_service["host"], worker_service["port"]), timeout=10.0
    ) as sock:
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(10.0)
        buffer = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk

    for line in buffer.splitlines():
        if line.strip():
            messages.append(json.loads(line.decode("utf-8")))
    return messages


def _assert_invalid_request(messages: list[dict[str, Any]]) -> None:
    assert messages, "worker closed the connection without an error envelope"
    error = messages[-1]
    assert error.get("type") == "error"
    assert error.get("ok") is False
    assert error.get("error_code") == "invalid_request"
    assert error.get("state") == "failed"


def test_tcp_rejects_non_object_json_and_remains_healthy(worker_service, worker_client) -> None:
    _assert_invalid_request(_send_raw(worker_service, b"[]\n"))
    assert any(message.get("pong") is True for message in worker_client({"command": "ping"}))


def test_tcp_rejects_invalid_utf8_and_remains_healthy(worker_service, worker_client) -> None:
    _assert_invalid_request(_send_raw(worker_service, b"{\"command\":\"ping\",\"x\":\xff}\n"))
    assert any(message.get("pong") is True for message in worker_client({"command": "ping"}))
