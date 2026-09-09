"""Producer C: ComfyUI /ws progress is ComfyUI's numbers, not a timer."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fixtures"))

from comfy_ws_progress_frames import (
    CRYSTOOLS,
    LOADER_STATE,
    OTHER_PROMPT,
    SAMPLER_PROGRESS_FRAMES,
)
from comfy_progress_socket import progress_from_message, steps_from_frames


def test_sampler_progress_frames_are_value_over_max():
    seen = [progress_from_message(f, "831d9f43-58f3-4398-89cc-9dd7d2289bb5") for f in SAMPLER_PROGRESS_FRAMES]
    assert seen == [(1, 4), (3, 4), (4, 4)]


def test_a_frame_for_another_prompt_is_ignored():
    assert progress_from_message(OTHER_PROMPT, "831d9f43-58f3-4398-89cc-9dd7d2289bb5") is None


def test_loader_state_and_crystools_are_not_sampler_steps():
    pid = "831d9f43-58f3-4398-89cc-9dd7d2289bb5"
    assert progress_from_message(LOADER_STATE, pid) is None
    assert progress_from_message(CRYSTOOLS, pid) is None


def test_steps_match_the_capture_and_not_elapsed_time():
    """A client that interpolates from elapsed time is the defect this wave exists to avoid."""
    frames = list(SAMPLER_PROGRESS_FRAMES)
    # Fake wall times 0, 10, 20 seconds — if the parser used time, 10s of 20s would be 2/4.
    timed = []
    t0 = 1_000_000.0
    for i, frame in enumerate(frames):
        timed.append((t0 + i * 10.0, frame))
    last = steps_from_frames(timed, "831d9f43-58f3-4398-89cc-9dd7d2289bb5", now=t0 + 10.0)
    assert last == (3, 4)
    # Explicit plant target: elapsed interpolation would report 2/4 at the midpoint.
    elapsed_guess = int((10.0 / 20.0) * 4)
    assert last[0] != elapsed_guess
