---
title: Phase D 3D Plan
type: system
status: specified_not_built
sources:
  - CLAUDE.md §6 Phase D
  - docs/design/11b_3d_pipeline_phase_d_execution_plan.md
  - docs/design/11c_3d_pipeline_consolidated_master_plan.md
updated: 2026-07-25
---

# Phase D — 3D (plan only)

## Goal

Game assets: buildings, weapons, animals, clothing, characters where **clothing is a separate mesh**.

## Two layers

1. **Single-asset generation** — new `native_comfy_template` family (mirror LTX import→template→adapter→gate). Candidates drift (Hunyuan3D / TRELLIS family) — re-survey live; never hard-code node names from old notes.
2. **Composition** — Chain Studio orchestration of separately generated meshes. Separable garments are **not** a single fused I2-3D shot.

## Hard truths

- Open I2-3D → one fused watertight mesh (clothing glued).
- Hair = geometry blobs; strand/card hair is Blender post.
- Two-stage shape+texture VRAM — measure, don’t assume.

## Build order (when opened)

D1 single-asset I2-3D → D2 mesh viewer/thumbnail surface → D3 T2-3D → D4 composition garments.

**v1.0:** deferred to v2.0 ship scope.

## Related

[[Native Comfy Template Pattern]] · [[Chain Studio]] · [[v1.0 Roadmap Synthesis]]
