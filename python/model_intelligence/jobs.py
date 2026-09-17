"""The refresh jobs that are running right now, so one can be cancelled from somewhere else.

`RefreshJob` has taken a `cancel` callable since the day it was written -- the 79-minute
measurement is in its docstring as the reason. Nothing ever passed one. The command ran the job
inline in the TCP handler, so the only way to stop a refresh was to kill the worker.

A cancel arrives on a DIFFERENT connection from the one that started the job (in background mode
there is no connection left at all), so the flag cannot live on either. It lives here, keyed by
job id, and both ends address it by that id.
"""
from __future__ import annotations

import threading
import uuid
from typing import Callable

_lock = threading.Lock()
_flags: dict[str, threading.Event] = {}


def start(job_id: str | None = None) -> str:
    """Register a running job and return its id."""
    identifier = str(job_id or f"mi_{uuid.uuid4().hex[:12]}")
    with _lock:
        _flags[identifier] = threading.Event()
    return identifier


def finish(job_id: str) -> None:
    with _lock:
        _flags.pop(str(job_id), None)


def running() -> list[str]:
    with _lock:
        return sorted(_flags)


def cancel(job_id: str = "") -> list[str]:
    """Ask a job to stop, or every job when `job_id` is empty. Returns the ids actually asked.

    Setting a flag for a job that has already finished is not an error worth reporting as one,
    but an id nobody is running is: a caller that cancels the wrong job and is told `ok` will
    watch the refresh keep going and conclude cancel is broken.
    """
    wanted = str(job_id or "").strip()
    with _lock:
        targets = list(_flags) if not wanted else [k for k in _flags if k == wanted]
        for key in targets:
            _flags[key].set()
    return targets


def is_cancelled(job_id: str) -> bool:
    with _lock:
        flag = _flags.get(str(job_id))
    return bool(flag and flag.is_set())


def cancel_check(job_id: str) -> Callable[[], bool]:
    """The callable `RefreshJob(cancel=...)` wants."""
    return lambda: is_cancelled(job_id)


def reset_for_tests() -> None:
    with _lock:
        _flags.clear()
