"""Who each worker command is FOR: a user, a developer, or the app itself.

Doc 49 measured which worker commands the UI can reach and found the queue append-only. The
uncomfortable part of that finding was not the number — it was that **nothing distinguished a
command that is deliberately CLI-only from one somebody forgot to wire**. From outside, an
unreachable diagnostic and an unreachable feature look identical, so the audit could not be turned
into a standing guarantee. This module is that distinction, declared rather than inferred.

## The three audiences

``USER_FACING``
    A person is supposed to be able to invoke it from the app. **Every one of these must have a
    route in ``qt_ui/``**, and ``tests/test_worker_command_audience.py`` fails if one does not.
    This is the ratchet: wiring a command up is what promotes it here, and promoting it without
    wiring it breaks the suite.

``DIAGNOSTIC``
    For a developer at a terminal — smoke tests, dry runs, graph inspection, contract probes.
    Genuinely CLI-only. No UI route is expected and their absence is not a defect.

``INTERNAL``
    Not addressed by a person at all: aliases the dispatcher accepts for compatibility, commands
    the worker issues to itself, and commands superseded by a native implementation.

## What the classification is grounded on

The command list is extracted from ``worker_tcp``'s dispatch table — 113 commands, where
``worker_client.CONTROL_COMMANDS ∪ STREAMING_COMMANDS`` covers only 51. That registry is a
STREAMING-vs-one-shot classifier, not a command list, and using it as one is what made the first
pass of this audit miss more than half the surface.

``USER_FACING`` was seeded from measured routing, not from names: a command with a literal in
``qt_ui/`` demonstrably has a route. The rest were classified by reading what they do.

**Residual risk, stated honestly:** the ratchet is one-directional. A command wrongly listed as
``USER_FACING`` fails the suite immediately. A genuinely user-facing command wrongly filed under
``DIAGNOSTIC`` passes quietly — the test cannot know a user wanted it. So this file is a claim
about intent that stays only as true as the last person to edit it.
"""
from __future__ import annotations

# Reachable from the app today, each verified by a command literal in qt_ui/.
USER_FACING: frozenset[str] = frozenset({
    # Generation and the queue. The queue commands below were the Doc 49 headline: all ten were
    # implemented and unreachable until the context menu landed.
    "enqueue", "queue_status",
    "cancel_queue_item", "cancel_active_queue_item", "cancel_all_queue_items",
    "remove_queue_item", "clear_pending_queue", "pause_queue", "resume_queue",
    "move_queue_item_up", "move_queue_item_down", "retry_queue_item", "duplicate_queue_item",
    # Runtime control the Runtime page exposes. unload_all_runtimes + clear_cuda_cache are the
    # Free VRAM button; the finer-grained unloads stay diagnostic.
    "comfy_runtime_status", "restart_comfy_runtime", "unload_all_runtimes", "clear_cuda_cache",
    "comfy_manager_status", "install_comfy_manager", "install_custom_node",
    "install_recommended_video_nodes",
    # Models: import, inspect, classify, and the substitution/download lane.
    "import_model_url", "inspect_model_url", "classify_models",
    "start_download", "download_status", "cancel_download",
    "resolve_missing_models", "civitai_variants",
    "family_install_plan", "apply_family_install_plan", "resolve_component_stack",
    # Workflows: import, discover, launch-readiness, dependency retry, delete.
    "import_workflow", "discover_comfy_workflows", "check_workflow_launch_readiness",
    "retry_workflow_dependencies", "delete_workflow_profile", "build_node_class_index",
    # Video family contracts drive the family status surface.
    "video_family_contracts",
    # LTX prompt-API submission, reachable only through history-requeue / explicit opt-in.
    "ltx_prompt_api_gated_submission", "ltx_requeue_draft_gated_submission",
    "ltx_ui_queue_history_contract",
    # Dataset generation has its own rail page.
    "generate_dataset",
    # Liveness, used by the backend health dot.
    "ping",
    # --- generation itself -----------------------------------------------------------------
    # These were INVISIBLE to the first pass of this audit. They are admitted by a
    # `if command not in {...}: reject` guard in worker_tcp rather than an `==` chain, and the
    # extractor only understood the `==` and `in` forms -- so the most important commands in the
    # protocol went unclassified while the completeness test passed. Caught by the integration
    # allowlist in tests/test_worker_auth.py cross-checking against the same extractor.
    "t2i", "i2i", "t2v", "i2v",
    "comfy_workflow",
    # Studio verbs (Character Studio look/clothes pipeline, Krea 2 regional inpaint).
    "look_complete", "clothes_only", "garment_shrinkwrap", "krea2_regional_inpaint",
    # 3D. The Gen3D page is nav-hidden unless SPELLVISION_SHOW_ALL_MODES=1, but hidden-by-default
    # is not the same as unreachable -- both of these have call sites.
    "gen3d", "i23d",
})

# Developer tools. CLI-only ON PURPOSE -- no UI route is expected.
DIAGNOSTIC: frozenset[str] = frozenset({
    # The LTX prompt-API era. LTX is native/production now (CLAUDE.md §6) and this whole family is
    # kept as an explicit fallback and inspection surface, not a user path.
    "ltx_prompt_api_submit", "ltx_prompt_api_submit_wait", "ltx_prompt_api_submit_and_capture",
    "ltx_prompt_api_conversion_adapter", "ltx_prompt_api_conversion_preview",
    "ltx_prompt_api_export_adapter", "ltx_prompt_api_normalization_preview",
    "ltx_submit_prompt_api", "ltx_execute_requeue_draft",
    "ltx_materialize_workflow", "ltx_workflow_materialization_dry_run",
    "ltx_t2v_materialize_dry_run", "ltx_t2v_smoke_test", "ltx_smoke_test_route",
    "ltx_workflow_graph_inspection", "ltx_workflow_contract", "ltx_test_workflow_contract",
    "ltx_readiness_status", "ltx_runtime_readiness",
    "ltx_history_registry", "ltx_queue_registry", "ltx_registry_history", "ltx_registry_queue",
    "ltx_recent_history", "ltx_recent_queue", "ltx_ui_registry_snapshot", "ltx_ui_results_contract",
    # The video-family equivalents of the same probes.
    "video_family_status", "video_family_readiness", "video_family_readiness_status",
    "video_family_workflow_contract", "video_family_test_workflow_contract",
    "video_family_graph_inspection", "video_family_materialization_dry_run",
    "video_family_smoke_test_route", "video_family_ltx_ui_contract",
    "video_family_ltx_history_registry", "video_family_ltx_queue_registry",
    "video_family_ltx_requeue_gated_submission",
    "video_family_prompt_api_conversion_adapter", "video_family_prompt_api_gated_submission",
    "video_family_prompt_api_normalization_preview",
    # Runtime introspection. The lifecycle pair is owned by scripts/dev/*.ps1, not the app;
    # the app exposes Restart and Free VRAM instead.
    "start_comfy_runtime", "stop_comfy_runtime",
    "runtime_diagnostics", "runtime_memory_status",
    "unload_image_runtime", "unload_video_runtime",
    # Guided dependency resolution (Doc 19) exists on the worker; the UI drives the
    # family_install_plan pair instead. Kept for CLI use rather than deleted.
    "guided_install_plan", "apply_guided_install_plan",
    # Graph and history inspection.
    "compile_workflow_prompt", "video_history_status",
    # The pytest harness's slow no-op, used to exercise the full job state path.
    "noop_slow",
    # t23d is dispatched but has NO call site anywhere in qt_ui -- its sibling i23d does. Text-to-3D
    # is Phase D3 and explicitly not started (CLAUDE.md §5), so this is an unfinished feature rather
    # than a wiring oversight. Classified honestly here rather than left to look like either.
    "t23d",
})

# Never addressed by a person.
INTERNAL: frozenset[str] = frozenset({
    # Dispatcher aliases kept for compatibility. Each maps onto a command above.
    "enqueue_job",          # -> enqueue
    "cancel", "cancel_job",  # -> cancel_queue_item
    "retry", "retry_job",    # -> retry_queue_item
    "history_video_status",  # -> video_history_status
    "model_import_inspect", "model_import_apply",  # -> inspect_model_url / import_model_url
    # Credentials are handled NATIVELY in C++ (qt_ui/shell/SecureCredentialStore), which writes the
    # same file with the same DPAPI entropy and key names as python/credential_store.py -- verified:
    # both resolve to %LOCALAPPDATA%/DarkDuck/SpellVision/credentials.json. So these are superseded
    # rather than unwired, and the UI avoids an RPC per keystroke.
    "save_credential", "set_credential", "clear_credential", "credential_status", "secrets_status",
    # Issued by the worker to itself before a generation.
    "ensure_comfy_runtime", "prepare_model_swap",
    # Superseded: the UI reads workflow profile JSON off disk directly.
    "list_workflow_profiles",
})


def audience_of(command: str) -> str | None:
    """``"user_facing"`` / ``"diagnostic"`` / ``"internal"``, or None if unclassified."""
    name = str(command or "").strip()
    if name in USER_FACING:
        return "user_facing"
    if name in DIAGNOSTIC:
        return "diagnostic"
    if name in INTERNAL:
        return "internal"
    return None


def all_classified() -> frozenset[str]:
    return USER_FACING | DIAGNOSTIC | INTERNAL
