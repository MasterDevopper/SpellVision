---
title: Native Comfy Template Pattern
type: architecture
status: accepted
sources:
  - CLAUDE.md §3 §6
  - python/video_family_contracts.py
  - python/video_adapters/
updated: 2026-07-25
---

# Native Comfy Template Pattern

## Definition

`backend_route = "native_comfy_template"`:

- Worker builds or patches a **repo-owned** graph (code builder and/or JSON template).
- Submits to ComfyUI `/prompt`.
- Family readiness gated by contracts + dependency resolvers.
- **Not** “bypass Comfy.”

## Proven families (contract `validation_status=production`)

| Family | Builder style | Notes |
|--------|---------------|-------|
| **Wan** | Code-built graph | Dual-noise t2v production; i2v via 2.1 single-model + VAE guard; 2.2 dual-noise i2v tracked |
| **LTX** | Patch `video_templates/ltx_av_native.json` | Default distilled two-stage; AV out; LoRA opt-in |
| **Hunyuan** | Native template | T2V production; i2v has doc vs contract tension — [[Contradiction Ledger]] |
| **Mochi** | Native template | T2V-only, Apache-2.0 |

## Pattern for any new native family (mirror LTX discipline)

1. Import proven Comfy workflow (Flows) → discover deps.
2. Dump live `/object_info` — **never invent node class names or input keys**.
3. Templatize reachable graph; prune unused passes.
4. Adapter (`*VideoAdapter`) + `prepare_request` snaps/constraints.
5. Contract row: `validation_status`, `backend_route`, components.
6. Route by `resolved_native_video_family`, not substring hacks.
7. Render-verify product surface; record evidence.

## Hard lessons (LTX)

- Prefix bugs (`ltx\\` in ckpt names) caught only by live object_info.
- Full 22B fp path can peak ~31 GB @ 768×512×97 — Simple defaults must cap res×frames.
- Width/height ÷32; frames `(N×8)+1`. Snap with warning, don’t 400.
- `/object_info` body ~2MB: Connection close + retries; `OSError` can slip past URLError handlers.

## Related

[[Video Families]] · [[ComfyUI Runtime]] · [[Phase D 3D Plan]]
