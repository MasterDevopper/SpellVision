"""Live 2026-09-10: Character T2I after LTX hung 10 min on UNETLoader at ~4 GB."""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import worker_runtime  # noqa: E402


def test_image_after_video_waits_for_comfy_queue_idle() -> None:
    """ /free returns 200 without aborting a load. Wait until Comfy's queue is empty. """
    src = inspect.getsource(worker_runtime.prepare_runtime_for_request)
    assert "request_comfy_free_memory" in src
    assert "wait_until_comfy_queue_idle" in src
