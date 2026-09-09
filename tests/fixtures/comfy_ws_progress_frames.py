"""ComfyUI /ws progress, sourced from a live capture 2026-09-09.

Real prompt 831d9f43 on 127.0.0.1:8188, KSampler 4 steps, node 8.
The frames below are the `progress` messages that carried a step count.
`progress_state` also exists (per-node value/max/state) but loaders are 0/1;
the sampler's step count is this `progress` envelope.
"""
from __future__ import annotations

# Captured verbatim (data payload only) from build/comfy_ws_capture.jsonl.
SAMPLER_PROGRESS_FRAMES = [
    {"type": "progress", "data": {"value": 1, "max": 4, "prompt_id": "831d9f43-58f3-4398-89cc-9dd7d2289bb5", "node": "8"}},
    {"type": "progress", "data": {"value": 3, "max": 4, "prompt_id": "831d9f43-58f3-4398-89cc-9dd7d2289bb5", "node": "8"}},
    {"type": "progress", "data": {"value": 4, "max": 4, "prompt_id": "831d9f43-58f3-4398-89cc-9dd7d2289bb5", "node": "8"}},
]

OTHER_PROMPT = {
    "type": "progress",
    "data": {"value": 2, "max": 20, "prompt_id": "other-prompt", "node": "8"},
}

LOADER_STATE = {
    "type": "progress_state",
    "data": {
        "prompt_id": "831d9f43-58f3-4398-89cc-9dd7d2289bb5",
        "nodes": {
            "3": {
                "value": 1.0,
                "max": 1.0,
                "state": "finished",
                "node_id": "3",
                "prompt_id": "831d9f43-58f3-4398-89cc-9dd7d2289bb5",
            }
        },
    },
}

CRYSTOOLS = {"type": "crystools.monitor", "data": {"cpu": 0}}
