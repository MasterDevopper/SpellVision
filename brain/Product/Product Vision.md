---
title: Product Vision
type: product
status: accepted
sources:
  - CLAUDE.md §1
  - README.md
updated: 2026-07-25
---

# Product Vision

## Defining promise

> Give people the full power of ComfyUI / A1111-class generation **without making them learn node graphs.**
> The user states intent; SpellVision figures out which nodes are needed, wires them correctly, resolves model/node dependencies, and runs them.

**That abstraction layer is the product.** Every feature decision is judged against: does it let a non-expert get a great result while letting a power user reach the raw knobs?

## What it is today

Premium **desktop** AI generation studio:

- Image: T2I / I2I across multiple families
- Video: T2V / I2V via native Comfy templates
- Composition: Chain Studio spine (nav may gate for v1.0)
- Specialized studios: Character / Comic pages exist in tree (roadmap labels vs tree — see [[Contradiction Ledger]])
- Planned: 3D game assets (Phase D), dataset generation integration

## What it is not

- Not a node editor clone
- Not a pure-diffusers replacement for ComfyUI
- Not a personal one-machine script — build for open shipping

## Abstraction layer modules (in tree)

`model_dependency_resolver.py`, `node_dependency_resolver.py`, `workflow_profile_registry.py`, `comfy_slot_mapper.py`, `workflow_importer.py`, `workflow_scanner.py`

## Related

[[UX Principles]] · [[Three-Layer Architecture]] · [[Native Comfy Template Pattern]]
