---
title: ADR-001 ComfyUI stays execution engine
status: accepted
updated: 2026-07-25
---

# ADR-001 — ComfyUI stays the execution engine

## Decision

Do **not** replace ComfyUI with a pure native-diffusers runtime as the product execution engine.

## Why

Solo developer cannot match ComfyUI’s model/custom-node velocity. SpellVision’s value is the **abstraction layer** (intent → correct graph + deps), not reimplementing every sampler node.

## Consequences

- Graph construction owned by SpellVision (templates/builders)
- Hybrid fast-path OK for common image ops
- Packaging must include Comfy + node packs + isolated venv story

## Related

[[Three-Layer Architecture]] · [[ADR-002 Native Comfy template path]]
