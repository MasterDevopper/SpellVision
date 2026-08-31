---
title: Workflow Library Flows
type: system
status: implemented
sources:
  - qt_ui/WorkflowLibraryPage.*
  - python/workflow_importer.py
  - python/workflow_scanner.py
  - CLAUDE.md §6
updated: 2026-07-25
---

# Workflow Library (Flows)

## Role

Import Comfy workflows → dependency/readiness → launch/materialize. On-ramp for native-family templatization.

## Storage

`runtime/imported_workflows` under project root (not asset-root). Empty count was historical empty-dir state, not a root bug.

## Related

[[Native Comfy Template Pattern]] · [[ComfyUI Runtime]]
