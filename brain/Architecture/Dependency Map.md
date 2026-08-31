---
title: Dependency Map
type: architecture
updated: 2026-07-25
---

# Dependency Map

```mermaid
flowchart TB
  subgraph ui [qt_ui]
    MW[MainWindow]
    Shell[ShellNavigationController]
    Gen[Image/VideoGenerationPage]
    Studios[Character/Comic Studio]
    Models[ModelManagerPage]
    Flows[WorkflowLibraryPage]
    Theme[ThemeManager]
    WQ[workers]
  end
  subgraph py [python]
    WS[worker_service]
    ST[worker_service_state]
    VA[video_adapters]
    RA[runtime_adapters]
    MR[model resolvers]
    WI[workflow_importer]
    CB[comfy_bootstrap]
  end
  subgraph ext [external]
    Comfy[ComfyUI :8188]
    Assets[D:/AI_ASSETS/models]
  end
  MW --> Shell
  MW --> Gen
  MW --> Studios
  Gen --> WQ
  Studios --> Gen
  WQ -->|worker_client NDJSON| WS
  WS --> ST
  WS --> VA
  WS --> RA
  WS --> MR
  WS --> WI
  WS --> CB
  CB --> Comfy
  VA --> Comfy
  MR --> Assets
  Theme --> MW
```

## Build-time

- CMake ≥3.21, VS 2022 gen, Qt 6.10.2 (+fallbacks), libwebp FetchContent for WebP thumbs.
- Python 3.12 project `.venv` (worker); Comfy **isolated** venv post cutover.

## Related

[[Three-Layer Architecture]] · [[Repository Map]] · [[Dev Environment]]
