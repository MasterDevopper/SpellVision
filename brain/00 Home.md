---
title: SpellVision Brain — Home
type: dashboard
status: living
updated: 2026-08-24
---

# SpellVision Brain

Navigable model of **product intent · decisions · architecture · implementation · proof · contradictions · open owner intent**.

> Not a docs dump. Prefer **live config + code** over stale prose. Authority order: [[Authority and Precedence]].

## Status legend

| Label | Meaning |
|-------|---------|
| **implemented + proven** | Code exists; render/product proof exists |
| **implemented, proof pending** | Code exists; no retained product proof yet |
| **partial** | Subset works; gaps explicit |
| **specified, not built** | Spec/plan only |
| **proposed decision** | Design option, not ratified |
| **accepted decision** | Binding for implementation |
| **superseded / stale** | Do not follow; kept for traceability |
| **owner decision required** | Cannot safely infer |

## Current truth (compressed — 2026-08-24)

| Axis | Truth |
|------|-------|
| Product | Premium desktop AI studio: Comfy/A1111 power **without node graphs** |
| Stack | Qt6/C++ UI ↔ Python worker (TCP/JSON `:8765`) ↔ ComfyUI (`:8188`) |
| Exec engine | **ComfyUI stays** — SpellVision owns graph construction (`native_comfy_template`) |
| Worker | **Facade** `worker_service.py` (~2100) re-exports queue / TCP / graphs / runners / runtime / metadata |
| Image | SDXL/Pony, Flux, PixArt, Lumina, Z-Image, Anima, **Krea2** (raw default 52/CFG 3.5; turbo 8/CFG 0; official bases only) |
| Video | LTX / Wan / Hunyuan / Mochi native + FLUX.3 hosted API; CogVideoX detected only |
| LTX | Default = `two_stage_distilled`; single-stage-full is opt-in |
| Tests | 423 passed / 2 skipped / 5 smoke deselected (`PYTHONPATH=""`) |
| UI shell | VSCode-like rail + **ArcaneGlass default**; Simple/Advanced in-place; half-screen parity required |
| Sampling | `SamplingController` from **worker family allow-lists** — Random checkbox landed |
| Rail extra | Character/Comic/Concept/Inspire/Runtime/Dataset/Train **on rail**; Chain + Gen3D hidden |
| v1.0 gate | Hybrid engines + on-demand models; Character A+B in bar; **shipping** still the public-ship gate (~20%) |
| v2.0 banked | Non-character native 3D, comic upload→video, audio depth, LLM orchestration |
| Comfy live | `C:\sv_comfynext\ComfyUI` + isolated venv; models `D:/AI_ASSETS/models` |
| Rust | **Gone** — `attic/rust_original_intent/` only |

## Start here

1. [[Product MOC]] — promise, audience, UX non-negotiables
2. [[Architecture MOC]] — three layers + native template pattern
3. [[Worker Facade Split]] — module homes after the god-file cut
4. [[Systems MOC]] — subsystems you will touch
5. [[Current State Ledger]] — what is green / partial / cut
6. [[Planned Additions]] — v1 gates vs parked v2
7. [[v1.0 Roadmap Synthesis]] — arcs and critical path
8. [[Contradiction Ledger]] — never re-learn stale docs
9. [[Open Questions Register]] — owner intent still open
10. [[Dev Environment]] — build/run/test commands

## Domain MOCs

- [[Product MOC]] · [[Architecture MOC]] · [[Systems MOC]] · [[Planning MOC]]
- [[Decision Map]] · [[Specification MOC]] · [[Reference MOC]]

## Visuals

- [[System Map]] — Mermaid three-layer + job flow
- [[Architecture Overview]] — canvas explorable map
- HTML plate: `docs/design/godfile-split-structure.html` (ArcaneGlass split diagram)
- Graphify studio: `.graphify/studio/studio.html` (23 520 nodes, includes untracked extract modules)
- Graphify Obsidian: `.graphify/obsidian/` (community notes + `graph.canvas`) — separate from this product brain

## How to maintain

- After any accepted owner decision: checkpoint register → ADR/spec → maps → validate.
- After code truth shifts: update [[Current State Ledger]] + [[Acceptance Evidence Ledger]] first.
- Run vault validator before claiming brain complete (skill `knowledge-base-engineering`).
