---
title: Generation Cockpit
type: system
status: implemented
sources:
  - qt_ui/ImageGenerationPage.cpp
  - qt_ui/ImageGenerationPage_preview.cpp
  - qt_ui/ImageGenerationPage_video.cpp
  - qt_ui/ImageGenerationPage_catalog.cpp
  - qt_ui/generation/SamplingController.cpp
  - qt_ui/generation/CockpitWidgetKit.cpp
  - CLAUDE.md §2
updated: 2026-08-17
---

# Generation Cockpit

## Layout contract

- Fits viewport — **no page scroll**
- Pinned Prompt card + inspector tabs (Model / Sampling / Output / Advanced) as stacked widget
- Simple/Advanced reveals in place
- Primary Generate is the **only** loud colored control

## Ownership (2026-08-17)

One `ImageGenerationPage` type, four translation units + controllers. Main file ~2886 / 3000. Type-level split is **specified, not built**.

- `SamplingController` — sampler / scheduler / steps / CFG / seed from **worker family allow-lists** (no static 49-item menus)
- `CockpitWidgetKit` — combo / spin / catalog helpers
- `_preview` / `_video` / `_catalog` TUs — preview, family presentation, catalog

## Request path

```text
Page buildRequestPayload
  → workers/WorkerCommandRunner (+ WorkerSubmissionPolicy)
  → worker_client → worker_service command
  → job_update stream → QueueManager / preview controllers
```

Studios must **not** reimplement transport — hand off via `submitGenerationRequest` / studio submit helper that merges cockpit model/sampler defaults.

## Input modes

- I2I / I2V: live dropzone; clear stale paths with `setInputImagePath(QString())`
- T2I / T2V: **no inert IMG stub** (`promptSourceSlot == nullptr`)

## Readiness

`CockpitInspector` readiness strip is **not** auto-synced — `updatePrimaryActionAvailability()` must write it from `readinessBlockReason()`.

## Related

[[Worker Protocol]] · [[Video Families]] · [[UX Principles]] · [[Worker Facade Split]]
