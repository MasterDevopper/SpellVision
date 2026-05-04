# Sprint 15C Pass 24 — Consume LTX Requeue Preview Contract in Queue/Preview Panels

Consumes the latest LTX requeue queue/preview contract produced by Pass 23.

Behavior:

- Reads `D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui/latest_ltx_requeue_queue_preview_contract.json`.
- Converts the contract into a normalized completed queue item.
- Prepends it to normalized queue snapshots in `WorkerQueueController`.
- Lets the existing QueueManager, QueueTableModel, active strip, details panel, and preview/open actions see the latest LTX requeue output without needing to parse the full backend response.

This pass does not start generation and does not change the requeue submission path. It only consumes the already-published contract in the queue/preview path.
