# Sprint 15C Pass 27 — Comfy Startup Ownership and Accurate Runtime Health

Adds ComfyUI runtime ownership to the dev launcher and blocks LTX requeue submit before confirmation when ComfyUI is offline.

Changes:

- Adds `scripts/dev/start_comfy.ps1`.
- Adds `scripts/dev/stop_comfy.ps1`.
- Updates `scripts/dev/run_ui.ps1` with `-NoComfy`, `-ComfyRoot`, and `-ComfyPort`.
- `run_ui.ps1` now starts/adopts ComfyUI on `127.0.0.1:8188` by default.
- Comfy startup waits for `/system_stats`, not just a listening port.
- Comfy session metadata is written to `build/.comfy_runtime.session.json`.
- Adopted external Comfy sessions are not stopped on exit.
- Comfy sessions started by `run_ui.ps1` are stopped on exit.
- `Submit Requeue` now checks Comfy reachability before showing the confirmation dialog.

This separates `SpellVision worker ready` from `ComfyUI healthy`, making runtime health more accurate.
