"""The third state: sites that are known, with a reason.

The old ratchets had two states -- compliant, or outside the file list they happened to name. A
violation in the second group was not compliant, not violating and not a documented exception; it
was merely *out of scope*, which is how a defect hides in plain sight. ``clothes_only.py`` rendered
seed 0 as 7 for months with a green seed ratchet three files away.

Two kinds live here, and the difference matters:

``EXEMPT``   a site that is legitimately different. The reason is the deliverable -- a boolean here
             would be indistinguishable from the out-of-scope state this module exists to abolish.

``BASELINE`` sites that are REAL violations, counted per file, awaiting the phase that fixes them.
             Two-way, like ``KNOWN_GAPS`` in test_family_capability: a count that goes UP fails
             because it is a regression, and a count that goes DOWN fails because the baseline must
             be lowered rather than left as a permanent allowance.

Per file rather than per line: line numbers shift under every edit above them, and a key that
invalidates itself would quietly re-report the thing it was meant to record.
"""
from __future__ import annotations

# --- legitimately different -------------------------------------------------------------------------

EXEMPT: dict[str, dict[str, str]] = {
    "zero-is-sayable": {},
    "no-machine-paths": {},
    "seed-one-rule": {},
}


# --- real violations, counted, awaiting their phase -------------------------------------------------

BASELINE: dict[str, dict[str, int]] = {
    # Doc 50 rule 8. Every one of these makes a value the UI offers unsayable. The fix is
    # `numeric_option` / `bounded_option`, which already exist and are used at three call sites --
    # that under-use is the whole finding. Phase 2 of the overhaul plan drives this to zero.
    #
    # native_video_graphs alone holds 45 of the 80, which is why the shared builder spine (Phase 4)
    # and this rule are the same piece of work approached from two directions.
    "zero-is-sayable": {
        "python/native_video_graphs.py": 45,
        "python/native_image_graphs.py": 12,
        "python/worker_service.py": 9,
        "python/native_runners.py": 5,
        "python/worker_tcp.py": 3,
        "python/workflow_library_commands.py": 2,
        "python/clothes_only.py": 1,
        "python/download_commands.py": 1,
        "python/image_runners.py": 1,
        # In a SUBDIRECTORY -- invisible to every sweep in this repo before sources.py used rglob.
        "python/runtime_adapters/comfy_workflow_adapter.py": 1,
    },

    # A hardcoded path is how a resolver stops being one. Three of these
    # (ltx_requeue_draft_submission, video_family_readiness, ltx_prompt_api_*) point at
    # D:/AI_ASSETS/comfy_runtime/ComfyUI -- the ROLLBACK build CLAUDE.md 9.2 forbids probing as
    # live -- and they take it because RuntimeProfile never exports the env name they read, so they
    # cannot see the configured root at all. Phase 3a.
    #
    # look_completion.py:319 reaches into C:/Users/xXste/Code_Projects/Master-Sculptor, a different
    # repository on the author's disk. That one is a dependency, not a default.
    "no-machine-paths": {
        "python/garment_shrinkwrap.py": 3,
        "python/look_completion.py": 3,
        "python/ltx_requeue_draft_submission.py": 3,
        "python/runtime_paths.py": 3,
        "qt_ui/T2VHistoryPage.cpp": 3,
        "python/ltx_prompt_api_submission.py": 2,
        "python/runtime_identity.py": 2,
        "qt_ui/assets/ModelThumbnailCache.cpp": 2,
        "python/ltx_prompt_api_jobs.py": 1,
        "python/ltx_queue_history_registry.py": 1,
        "python/video_family_readiness.py": 1,
        "qt_ui/ImageGenerationPage.cpp": 1,
        "qt_ui/workers/WorkerQueueController.cpp": 1,
    },

    # Zero, and it stays zero. This rule shipped with a ratchet naming three files; sweeping all 92
    # modules found three more violations -- clothes_only (seed 0 -> 7), look_completion
    # (0 -> 4419) and ltx_smoke_test_route (0 -> a prompt hash, because _safe_int returns its
    # fallback for anything <= 0). All three are fixed.
    "seed-one-rule": {},
}


def baseline_for(rule: str) -> dict[str, int]:
    return BASELINE.get(rule, {})


def is_exempt(rule: str, site: str) -> bool:
    return site in EXEMPT.get(rule, {})


def total_baseline() -> int:
    return sum(sum(files.values()) for files in BASELINE.values())
