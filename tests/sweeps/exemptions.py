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
    # Zero, and it stays zero. All 80 sites route through `bounded_option`, which resolves the
    # field's aliases and its valid range from one table instead of from 80 hand-written `or`
    # chains. Two of those chains INVERTED a video denoise: 0.0 means "return the input unchanged",
    # and `or 1.0` turned it into "ignore the input entirely".
    #
    # The bounds table is what makes this more than a rename. It answers "is zero sayable here" once
    # per FIELD -- yes for cfg, denoise, limit, timeout, shift and lora_scale; no for steps, fps and
    # width -- and a stated value outside the range is clamped AND REPORTED. The old form silently
    # substituted a default, which is how a stated steps=0 came back as a normal-looking render with
    # nothing anywhere saying the number had been ignored.
    "no-machine-paths": {
        "python/comfy_root.py::C:/sv_comfynext/ComfyUI": (
            "THE resolver. These two literals are the live and rollback installs the 2026-07-17 "
            "cutover created, and a resolver has to name the things it resolves between -- the same "
            "way comfy_endpoint names 127.0.0.1:8188. The rule's point is that this is the ONLY "
            "place they appear; before this they were spread across five modules, three of them "
            "naming only the rollback tree."
        ),
        "python/comfy_root.py::D:/AI_ASSETS/comfy_runtime/ComfyUI": (
            "Same: the rollback install, named here so every other module can stop naming it."
        ),
        "qt_ui/shell/RuntimeProfile.cpp::C:/sv_comfynext/ComfyUI": (
            "The Qt half of the same resolver. resolvePreferredComfyRoot already existed and was "
            "already called from two of the four Qt sites -- it was a one-line "
            "`return normalized(configured)`, a resolver in name only. Filling it in beat adding a "
            "ninth, and these two literals moved here out of ImageGenerationPage and "
            "ModelThumbnailCache."
        ),
        "qt_ui/shell/RuntimeProfile.cpp::D:/AI_ASSETS/comfy_runtime/ComfyUI": (
            "Same: the rollback install, named once on the Qt side."
        ),
    },

    "zero-is-sayable": {
        "python/runtime_adapters/comfy_workflow_adapter.py::_poll_history:comfy_timeout_sec": (
            "UNREACHABLE, the same package as the cancellable-comfy-submission exemption below: a "
            "parallel implementation of submit-and-poll that nothing imports. Rewriting a call in "
            "code with no consumer would add risk and prove nothing. Phase 4a deletes the package "
            "and this exemption goes with it."
        ),
    },

    "request-keys-have-readers": {},

    # Zero, and it stays zero: the whole point is that there is one resolver per side.
    "one-comfy-root-resolver": {},

    "samplers-through-one-resolver": {
        "python/native_video_graphs.py::_build_native_hunyuan_wrapper_i2v_prompt::scheduler": (
            "Not a sampler choice. The kijai HunyuanVideoWrapper's `scheduler` input names a "
            "diffusers scheduler CLASS (FlowMatchDiscreteScheduler), which is the wrapper's "
            "sampling algorithm rather than a value from the KSampler scheduler combo. Routing it "
            "through sampling_for would offer the user ComfyUI scheduler names for an input that "
            "does not take them."
        ),
    },

    "cancellable-comfy-submission": {
        "python/runtime_adapters/comfy_workflow_adapter.py::_submit_prompt": (
            "UNREACHABLE. This package is a second, parallel implementation of submit-and-poll from "
            "the Doc 21 worker refactor that never landed: `git grep runtime_adapters` outside the "
            "package itself returns docs and the brain generator, no importer. Wiring a cancel into "
            "code nothing calls would add risk and prove nothing. It is a textbook instance of the "
            "meta-finding -- the same bug, surviving in a copy -- and belongs to Phase 4a (delete "
            "what has no consumer), not here. Remove the package and this exemption goes with it."
        ),
    },

    "wire-types-registered": {
        "python/worker_client.py::client_warning": (
            "Produced BY this client for a message it did not recognise, not by the worker. "
            "Registering it would be circular."
        ),
        "python/worker_client.py::client_error": (
            "Same: this client's own transport-failure envelope, never sent by the worker."
        ),
        "python/ltx_prompt_api_submission.py::spellvision_result_registration": (
            "A nested sub-record carried inside a larger payload's `result_registration` field, "
            "not a top-level wire message -- it never reaches normalize_worker_message."
        ),
        "python/ltx_queue_history_registry.py::spellvision_result_registration": (
            "The same nested sub-record, built in a second place. Exempting it site by site rather "
            "than by type name is deliberate: if this record ever DOES become a top-level message "
            "somewhere new, that third site must be looked at rather than inheriting a blanket pass."
        ),
    },
}


# --- real violations, counted, awaiting their phase -------------------------------------------------

BASELINE: dict[str, dict[str, int]] = {
    # Doc 50 rule 8. Every one of these makes a value the UI offers unsayable. The fix is
    # `numeric_option` / `bounded_option`, which already exist and are used at three call sites --
    # that under-use is the whole finding. Phase 2 of the overhaul plan drives this to zero.
    #
    # native_video_graphs alone holds 45 of the 80, which is why the shared builder spine (Phase 4)
    # and this rule are the same piece of work approached from two directions.
    # Zero, and it stays zero. All 80 sites route through `bounded_option`, which resolves the
    # field's aliases and its valid range from one table instead of from 80 hand-written `or`
    # chains. Two of those chains INVERTED a video denoise: 0.0 means "return the input unchanged",
    # and `or 1.0` turned it into "ignore the input entirely".
    #
    # The bounds table is what makes this more than a rename. It answers "is zero sayable here" once
    # per FIELD -- yes for cfg, denoise, limit, timeout, shift and lora_scale; no for steps, fps and
    # width -- and a stated value outside the range is clamped AND REPORTED. The old form silently
    # substituted a default, which is how a stated steps=0 came back as a normal-looking render with
    # nothing anywhere saying the number had been ignored.
    "zero-is-sayable": {},

    # A hardcoded path is how a resolver stops being one. Three of these
    # (ltx_requeue_draft_submission, video_family_readiness, ltx_prompt_api_*) point at
    # D:/AI_ASSETS/comfy_runtime/ComfyUI -- the ROLLBACK build CLAUDE.md 9.2 forbids probing as
    # live -- and they take it because RuntimeProfile never exports the env name they read, so they
    # cannot see the configured root at all. Phase 3a.
    #
    # look_completion.py:319 reaches into C:/Users/xXste/Code_Projects/Master-Sculptor, a different
    # repository on the author's disk. That one is a dependency, not a default.
    # 26 -> 13. Every ComfyUI-install literal is gone: eight resolvers across four env names became
    # one, and the three modules that hardcoded the ROLLBACK tree (ltx_requeue_draft_submission,
    # ltx_prompt_api_*, and runtime_paths' own copy of the live/rollback pair) now derive from it.
    #
    # What is left is two different things. garment_shrinkwrap and look_completion reach into
    # C:/Users/xXste/Code_Projects/Master-Sculptor, a SEPARATE repository on the author's disk --
    # that is a dependency to be configured, not a default to be resolved. The qt_ui entries are
    # display and cache paths on the Qt side, which no Python resolver can help with; they need the
    # C++ equivalent of comfy_root and that does not exist yet.
    # 26 -> 11. Every ComfyUI-install literal outside the two resolvers is gone: eight resolvers
    # across four env names became one on each side of the wire. The Qt half mattered as much as the
    # Python half -- ImageGenerationPage carried the C++ twin of the LTX workflow literal, and
    # ModelThumbnailCache probed for ffmpeg inside the rollback tree.
    #
    # What is left is two different things. garment_shrinkwrap and look_completion reach into
    # C:/Users/xXste/Code_Projects/Master-Sculptor, a SEPARATE repository on the author's disk --
    # a dependency to be configured, not a default to be resolved. The rest are display, cache and
    # third-party tool paths (C:/ffmpeg) that no ComfyUI resolver can help with.
    "no-machine-paths": {
        "python/garment_shrinkwrap.py": 3,
        "qt_ui/T2VHistoryPage.cpp": 3,
        "python/look_completion.py": 2,
        "python/runtime_paths.py": 1,
        "qt_ui/assets/ModelThumbnailCache.cpp": 1,
        "qt_ui/workers/WorkerQueueController.cpp": 1,
    },

    # Zero, and it stays zero. This rule shipped with a ratchet naming three files; sweeping all 92
    # modules found three more violations -- clothes_only (seed 0 -> 7), look_completion
    # (0 -> 4419) and ltx_smoke_test_route (0 -> a prompt hash, because _safe_int returns its
    # fallback for anything <= 0). All three are fixed.
    "seed-one-rule": {},

    # Zero, and it stays zero. Four terminalisers discarded transition_job's return; all four
    # happened to work, but silently -- which is exactly how fail_job hid the stranding bug for as
    # long as it did. Scoped to TERMINAL targets on purpose: 30 sites discard a STARTING/RUNNING
    # hop, which is a milder question, and flagging all of them would have buried these four.
    "terminalisers-check-their-hop": {},
    "wire-types-registered": {},

    # Zero, and it stays zero: every route that owns a job now hands its prompt id to the handle.
    # The only site left is exempted above as unreachable, so a NEW violation here means a new
    # route can start a render nobody can stop.
    "cancellable-comfy-submission": {},

    # 54 keys the UI sends that the worker never names. They are NOT one thing, and the split is
    # the useful part of the finding:
    #
    #   Provenance. Most of GenerationRequestBuilder's block -- video_dimensions_valid,
    #   video_readiness_warnings, client_video_mode, submit_origin, workflow_draft_source -- is
    #   diagnostic state the UI includes so it lands in the metadata sidecar, which
    #   clone_request_snapshot deep-copies whole. Nothing reads them individually and nothing
    #   should. They are not defects, but they are also not distinguishable from defects by
    #   inspection, which is why they sit at baseline rather than in EXEMPT: the honest label is
    #   "unclassified", and classifying 54 keys one at a time is its own pass.
    #
    #   Real, and named here so they are not lost: `batch_count` (the cockpit has a batch control
    #   and the worker has no batching at all -- asking for four images renders one) and
    #   `positive_embeddings` / `negative_embeddings` (an embeddings picker whose values reach a
    #   worker with no textual-inversion loading). Both are FEATURE gaps rather than hardening, so
    #   this pass records them instead of half-building them.
    #
    # What the rule already earned: wan_split, high_steps, low_steps, split_step, noise_split_step
    # and wan_noise_split_step were all in this list, and all six are now read.
    "request-keys-have-readers": {
        "qt_ui/generation/GenerationRequestBuilder.cpp": 32,
        "qt_ui/MainWindow.cpp": 8,
        "qt_ui/Gen3DPage.cpp": 5,
        "qt_ui/workers/WorkerCommandRunner.cpp": 5,
        "qt_ui/DatasetGenerationPage.cpp": 1,
        "qt_ui/ManagerPage.cpp": 1,
        "qt_ui/WorkflowLibraryPage.cpp": 1,
        "qt_ui/studios/CharacterStudioPage.cpp": 1,
    },

    # The four Character-Studio graphs, each a hand-copy of the krea2 graph with its own literal
    # euler/simple. They are REAL violations, not exceptions: the same defect as Hunyuan's, in the
    # copies. Threading the resolver into each separately would entrench the duplication, so they
    # are held here until Phase 5 collapses the four into one builder -- at which point this drops
    # to zero in one edit rather than four.
    "samplers-through-one-resolver": {
        "python/clothes_only.py": 2,
        "python/krea2_regional_inpaint.py": 2,
        "python/look_completion.py": 2,
        "python/qwen_image_edit_graph.py": 2,
    },
}


def baseline_for(rule: str) -> dict[str, int]:
    return BASELINE.get(rule, {})


def is_exempt(rule: str, site: str) -> bool:
    return site in EXEMPT.get(rule, {})


def total_baseline() -> int:
    return sum(sum(files.values()) for files in BASELINE.values())
