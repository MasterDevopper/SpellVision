# Sprint 15C Pass 4 — Gated LTX T2V Smoke-Test Route

Adds a gated LTX smoke-test worker route that builds a tiny LTX T2V test request from the Pass 3 workflow contract.

## What this pass does

- Adds `python/ltx_smoke_test_route.py`.
- Adds worker command aliases:
  - `ltx_t2v_smoke_test`
  - `ltx_smoke_test_route`
  - `video_family_smoke_test_route`
- Requires the LTX workflow contract to report `ready_to_test == true` before the route is considered passable.
- Builds a tiny, low-risk T2V smoke request with:
  - 512x320
  - 33 frames
  - 8 fps
  - 8 steps
  - CFG 1
  - Euler / linear_quadratic
- Keeps LTX experimental and does not modify the Wan production route.

## Intentional non-goal

This pass does not submit the workflow to ComfyUI yet. It returns the exact smoke payload, metadata contract, diagnostics, and output expectations so the next pass can wire prompt mutation/submission safely.

## Smoke test

```powershell
'{"command":"ltx_t2v_smoke_test"}' | & .\.venv\Scripts\python.exe .\python\worker_client.py
```

Expected:

- `type: ltx_t2v_smoke_test`
- `gate_passed: true`
- `ready_to_test: true`
- `generation_enabled: true`
- `submitted: false`
- `submission_status: ready_for_next_pass`
