# Sprint 15C Pass 23 — Promote LTX Requeue Flow to Queue/Preview Contract

Promotes successful LTX requeue submissions into a normalized Qt-side queue/preview contract.

The T2V History page now:

- Builds `spellvision_ltx_requeue_queue_preview_contract` from the Pass 18/20 response.
- Persists the latest contract to `D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui/latest_ltx_requeue_queue_preview_contract.json`.
- Emits `ltxRequeuePreviewContractReady(contract)` for future queue/preview consumers.
- Keeps the existing `ltxRequeueSubmitted(promptId, primaryOutputPath)` signal for lightweight consumers.

This pass does not start another generation. It only normalizes and publishes the result that already came back from the guarded requeue submit path.
