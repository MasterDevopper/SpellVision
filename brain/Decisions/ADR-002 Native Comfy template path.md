---
title: ADR-002 Native Comfy template path
status: accepted
updated: 2026-07-25
---

# ADR-002 — Native Comfy template path

## Decision

Production video (and future native families) use `backend_route="native_comfy_template"`: repo-owned builders/templates submitted to ComfyUI — **not** pure diffusers, **not** ad-hoc Prompt-API as default.

## Pattern authority

LTX migration is the gold-standard procedure (object_info grounding, template prune, adapter snaps, contract flip, UI labels).

## Fallback

LTX Prompt-API engines retained as **explicit opt-in** fallback only.

## Related

[[Native Comfy Template Pattern]] · [[Video Families]]
