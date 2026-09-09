"""Fan-out of queue progress onto long-lived subscriber sockets.

The submitting TCP connection is already closed when a queued job runs, so
progress used to have nowhere to go except the poll. A `subscribe` command
registers the request's EventEmitter; QueueEmitter.emit() forwards to every
live subscriber. A dead one is dropped on the first write failure --
EventEmitter already tracks client_disconnected.

When the session secret rotates (a new worker launch), old subscribers fail
auth on reconnect and must present the new secret. While they are gone the
poll is still delivering, so the bar slows rather than stopping.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_emitters: list[Any] = []


def register(emitter: Any) -> None:
    with _lock:
        if emitter not in _emitters:
            _emitters.append(emitter)


def drop_dead() -> None:
    with _lock:
        _emitters[:] = [e for e in _emitters if not getattr(e, "client_disconnected", False)]


def fanout(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    drop_dead()
    with _lock:
        live = list(_emitters)
    for emitter in live:
        try:
            emitter.emit(payload)
        except Exception:
            if hasattr(emitter, "client_disconnected"):
                emitter.client_disconnected = True


def reset_for_tests() -> None:
    with _lock:
        _emitters.clear()
