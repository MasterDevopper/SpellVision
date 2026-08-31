#!/usr/bin/env python3
"""Generate the SpellVision Obsidian brain vault under repo brain/."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "brain"
DATE = "2026-07-25"


def w(rel: str, content: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    text = content.strip() + "\n"
    p.write_text(text, encoding="utf-8")
    print(f"wrote {rel} ({len(text)} bytes)")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)

    w(
        ".obsidian/app.json",
        '{\n  "alwaysUpdateLinks": true\n}',
    )
    w(
        ".obsidian/appearance.json",
        '{\n  "accentColor": "#8b5cf6"\n}',
    )
    w(
        ".obsidian/core-plugins.json",
        """{
  "file-explorer": true,
  "global-search": true,
  "switcher": true,
  "graph": true,
  "backlink": true,
  "outgoing-link": true,
  "tag-pane": true,
  "page-preview": true,
  "daily-notes": false,
  "templates": true,
  "note-composer": true,
  "command-palette": true,
  "editor-status": true,
  "bookmarks": true,
  "outline": true,
  "word-count": true,
  "file-recovery": true,
  "canvas": true,
  "properties": true
}""",
    )

    w(
        "00 Home.md",
        f"""---
title: SpellVision Brain — Home
type: dashboard
status: living
updated: {DATE}
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

## Current truth (compressed — {DATE})

| Axis | Truth |
|------|-------|
| Product | Premium desktop AI studio: Comfy/A1111 power **without node graphs** |
| Stack | Qt6/C++ UI ↔ Python worker (TCP/JSON `:8765`) ↔ ComfyUI (`:8188`) |
| Exec engine | **ComfyUI stays** — SpellVision owns graph construction (`native_comfy_template`) |
| Image | Multi-family production (SDXL/Pony, Flux, PixArt, Lumina, Z-Image, Anima) |
| Video | LTX / Wan / Hunyuan / Mochi on native template; CogVideoX detected only |
| LTX | Native production default (AV); Prompt-API = explicit fallback only |
| UI shell | VSCode-like rail + ArcaneGlass north star; Simple/Advanced in-place |
| v1.0 gate | **Shipping arc** (installer + first-run + dep resolution) — not more families |
| v2.0 banked | 3D Phase D, deeper audio, LLM orchestration |
| Comfy live | `C:\\\\sv_comfynext\\\\ComfyUI` + isolated venv; models `D:/AI_ASSETS/models` |
| Rust | **Gone** — `attic/rust_original_intent/` only |

## Start here

1. [[Product MOC]] — promise, audience, UX non-negotiables
2. [[Architecture MOC]] — three layers + native template pattern
3. [[Systems MOC]] — subsystems you will touch
4. [[Current State Ledger]] — what is green / partial / cut
5. [[v1.0 Roadmap Synthesis]] — arcs and critical path
6. [[Contradiction Ledger]] — never re-learn stale docs
7. [[Open Questions Register]] — owner intent still open
8. [[Dev Environment]] — build/run/test commands

## Domain MOCs

- [[Product MOC]] · [[Architecture MOC]] · [[Systems MOC]] · [[Planning MOC]]
- [[Decision Map]] · [[Specification MOC]] · [[Reference MOC]]

## Visuals

- [[System Map]] — Mermaid three-layer + job flow
- [[Architecture Overview]] — canvas explorable map

## How to maintain

- After any accepted owner decision: checkpoint register → ADR/spec → maps → validate.
- After code truth shifts: update [[Current State Ledger]] + [[Acceptance Evidence Ledger]] first.
- Run vault validator before claiming brain complete (skill `knowledge-base-engineering`).
""",
    )

    # Product
    w(
        "Product/Product MOC.md",
        f"""---
title: Product MOC
type: moc
updated: {DATE}
---

# Product MOC

- [[Product Vision]]
- [[UX Principles]]
- [[Audience and Shipping Bar]]

## Related

- [[v1.0 Roadmap Synthesis]]
- [[Current State Ledger]]
- [[Theme System ArcaneGlass]]
""",
    )

    w(
        "Product/Product Vision.md",
        f"""---
title: Product Vision
type: product
status: accepted
sources:
  - CLAUDE.md §1
  - README.md
updated: {DATE}
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
""",
    )

    w(
        "Product/UX Principles.md",
        f"""---
title: UX Principles
type: product
status: accepted
sources:
  - CLAUDE.md §2
  - docs/design/13_simple_advanced_disclosure_phase7.md
  - docs/design/ArcaneGlass_token_spec.md
updated: {DATE}
---

# UX Principles (non-negotiable)

## Progressive disclosure — global Simple / Advanced

- One app-wide concept — not per-feature reinventions.
- **Simple** = intent (Portrait/Landscape, quality presets); hide pixel math, schedulers, CFG, nodes.
- **Advanced** = raw knobs.
- Toggle per-surface; default in Settings.
- **Rule: Advanced reveals in place. Never relocates controls to another screen.** Muscle memory survives upgrade.

## Scrolling discipline

| Surface | Rule |
|---------|------|
| Generation cockpit | Fits viewport — **no scroll**. Tabbed inspector (Prompt pinned + Model/Sampling/Output/Advanced stack). |
| Content surfaces | **Exactly one** scroll region (library, gallery, history, datasets). Never nested. |
| Studio side rails | Body in `QScrollArea`; Advanced must remain reachable at half-screen. |

## Design language

- Skeleton: **VSCode** — custom title bar, left activity rail, high density that breathes.
- Skin: **ArcaneGlass** via `ThemeManager`. Brand: metallic-framed violet arcane-eye.
- One hero accent (violet eye-glow); platinum/steel hairlines; cyan = **semantic ready/online only**.
- Owner visual QA is harsh: token polish alone is a C. Instrument quality > half-themed chrome.

## Responsive parity

Fullscreen-only polish is not showcase. Half-screen + default restore must keep **same functionality** (scroll OK; clip/hide not OK). See skill `spellvision-qt-studio-surfaces` + [[Theme System ArcaneGlass]].

## Related

[[Audience and Shipping Bar]] · [[Generation Cockpit]] · [[Theme System ArcaneGlass]]
""",
    )

    w(
        "Product/Audience and Shipping Bar.md",
        f"""---
title: Audience and Shipping Bar
type: product
status: accepted
sources:
  - CLAUDE.md §1
  - docs/design/SpellVision_v1.0_Roadmap.md
  - docs/design/28_release_readiness_checklist.md
updated: {DATE}
---

# Audience and Shipping Bar

## Audience

Eventually shipped openly to everyone. Build showpiece **and** functional tool — not a personal script.

## v1.0 bar (synthesis)

v1.0 is not “more model families.” Three arcs:

1. **Families** — nearly closed; license surfacing + optional Wan 2.2 dual-noise i2v
2. **UI polish** — mode-aware history is load-bearing
3. **Shipping** — **true gate**: installer bundle + first-run wizard + guided dependency resolution

Gates: functional + licensing/compliance + security (Doc 28). Green functional + red license = **not shippable**.

## Explicit cut list (v2.0+)

3D Phase D, audio pipeline depth, LLM node-orchestration, Comfy auto-update, god-file decomposition (health), family-aware duration layer wiring (design-proven), Rust/cxx-qt SpellBound arc.

## Related

[[v1.0 Roadmap Synthesis]] · [[Acceptance Evidence Ledger]] · [[Open Questions Register]]
""",
    )

    # Architecture
    w(
        "Architecture/Architecture MOC.md",
        f"""---
title: Architecture MOC
type: moc
updated: {DATE}
---

# Architecture MOC

- [[Three-Layer Architecture]]
- [[Native Comfy Template Pattern]]
- [[Dependency Map]]
- [[Job Lifecycle Contract]]
- [[Worker Protocol]]
- [[System Map]]
""",
    )

    w(
        "Architecture/Three-Layer Architecture.md",
        f"""---
title: Three-Layer Architecture
type: architecture
status: accepted
sources:
  - CLAUDE.md §3
  - ARCHITECTURE.md
  - README.md
updated: {DATE}
---

# Three-Layer Architecture

```mermaid
flowchart LR
  UI[Qt6 C++ UI qt_ui] -->|TCP NDJSON :8765| W[Python worker worker_service.py]
  W -->|HTTP /prompt /upload :8188| C[ComfyUI engine]
  W --> State[worker_service_state.py]
  UI --> QSettings[(QSettings DarkDuck/SpellVision)]
```

## Ownership split

| Layer | Owns | Does not own |
|-------|------|--------------|
| **C++/Qt6 UI** | Shell, pages, request build, queue UX, theme, preview, rail | Comfy graph details, model load |
| **Python worker** | Job lifecycle, routing, adapters, graph builders, Comfy lifecycle | Pixel paint / chrome |
| **ComfyUI** | Node execution, custom nodes, VRAM during sample | Product UX |

## Settled decisions

1. **ComfyUI stays the execution engine** — not replaced by native diffusers. Solo velocity cannot match Comfy model support.
2. **SpellVision owns all graph construction** — thin hybrid fast-path for common ops.
3. **Native ≠ pure diffusers** — means `backend_route="native_comfy_template"`: dynamic graph from internal template/code.
4. **Rust core is gone** — archive only; ignore stale Rust prereqs in old guides.

## Key paths

| Concern | Location |
|---------|----------|
| UI entry | `qt_ui/main.cpp`, `MainWindow.*` |
| Worker entry | `python/worker_service.py` |
| Job SM | `python/worker_service_state.py` |
| Comfy bootstrap | `python/comfy_bootstrap.py`, `comfy_runtime_manager.py` |
| Paths | `python/runtime_paths.py` |
| Video adapters | `python/video_adapters/` |
| Templates | `python/video_templates/` |
| Studios | `qt_ui/studios/` |

## Related

[[Native Comfy Template Pattern]] · [[Worker Service]] · [[ComfyUI Runtime]] · [[Job Lifecycle Contract]]
""",
    )

    w(
        "Architecture/Native Comfy Template Pattern.md",
        f"""---
title: Native Comfy Template Pattern
type: architecture
status: accepted
sources:
  - CLAUDE.md §3 §6
  - python/video_family_contracts.py
  - python/video_adapters/
updated: {DATE}
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

- Prefix bugs (`ltx\\\\` in ckpt names) caught only by live object_info.
- Full 22B fp path can peak ~31 GB @ 768×512×97 — Simple defaults must cap res×frames.
- Width/height ÷32; frames `(N×8)+1`. Snap with warning, don’t 400.
- `/object_info` body ~2MB: Connection close + retries; `OSError` can slip past URLError handlers.

## Related

[[Video Families]] · [[ComfyUI Runtime]] · [[Phase D 3D Plan]]
""",
    )

    w(
        "Architecture/Dependency Map.md",
        f"""---
title: Dependency Map
type: architecture
updated: {DATE}
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
""",
    )

    w(
        "Architecture/Job Lifecycle Contract.md",
        f"""---
title: Job Lifecycle Contract
type: contract
status: accepted
sources:
  - docs/JOB_LIFECYCLE_CONTRACT.md
  - python/worker_service_state.py
updated: {DATE}
---

# Job Lifecycle Contract

## States

`queued` → `starting` → `running` → `completed` | `failed` | `cancelled`

Also: `queued` → `cancelled`; `starting` → `failed`.

## Valid transitions

```text
queued -> starting | cancelled
starting -> running | failed
running -> completed | failed | cancelled
```

Invalid transitions ignored/logged — **do not assume completion** unless full path ran.

## Known bug

**Ping / fast-path:** `QUEUED → COMPLETED` silently fails. Terminal message can show `ok: true` while `state: queued`. Strict xfail in tests. Fix: route through STARTING→RUNNING→COMPLETED or relax SM for ping only.

## Related

[[Worker Protocol]] · [[Worker Service]] · [[Known Bugs and Footguns]]
""",
    )

    w(
        "Architecture/Worker Protocol.md",
        f"""---
title: Worker Protocol
type: contract
status: accepted
sources:
  - docs/SPELLVISION_WORKER_PROTOCOL.md
  - ARCHITECTURE.md
updated: {DATE}
---

# Worker Protocol

## Transport

- Local TCP loopback `127.0.0.1:8765`
- UTF-8 JSON, **one logical event per line** (NDJSON)
- UI → `worker_client.py` → `worker_service.py` → Comfy/pipeline → events back

## Roles

| Actor | Responsibility |
|-------|----------------|
| Qt UI | Build requests, consume stream, progress/result UI |
| worker_client | Connect, forward, relay stdout lines |
| worker_service | Validate, route, execute, emit progress/result/error |

Frontend **never** talks to ComfyUI directly.

## Related

[[Job Lifecycle Contract]] · [[Worker Service]] · [[Generation Cockpit]]
""",
    )

    # Systems
    w(
        "Systems/Systems MOC.md",
        f"""---
title: Systems MOC
type: moc
updated: {DATE}
---

# Systems MOC

## Runtime spine

- [[Qt UI Shell]]
- [[Generation Cockpit]]
- [[Worker Service]]
- [[ComfyUI Runtime]]
- [[Job Lifecycle Contract]]

## Product surfaces

- [[Model Library]]
- [[Workflow Library Flows]]
- [[Chain Studio]]
- [[Character and Comic Studios]]
- [[Theme System ArcaneGlass]]
- [[Video Families]]
- [[Image Families and Memory]]

## Future

- [[Phase D 3D Plan]]
""",
    )

    w(
        "Systems/Qt UI Shell.md",
        f"""---
title: Qt UI Shell
type: system
status: implemented
sources:
  - qt_ui/MainWindow.*
  - qt_ui/shell/
  - CLAUDE.md §2 §6
updated: {DATE}
---

# Qt UI Shell

## Shape

VSCode-style desktop shell:

- Custom title bar (`CustomTitleBar`)
- Left activity rail (`ShellNavigationController`)
- Central page stack (`MainWindow::buildPages` / `switchToMode`)
- Bottom telemetry (`BottomTelemetryPresenter` / themed status strip)
- Command palette (`CommandPaletteDialog`)

## Rail

Flat entries (order evolves): Home, Chain, T2I, I2I, T2V, I2V, Flows, History, Inspire, Models, Prefs (+ Create studios when wired). Some modes nav-gated via `kV1HiddenModes` / `SPELLVISION_SHOW_ALL_MODES=1` (Chain/Inspire pattern).

## Page inventory (high level)

| Page | Status notes |
|------|----------------|
| Home / HomeDashboard | Outputs gallery; empty gallery ≠ no files if sidecars missing |
| ImageGenerationPage | T2I/I2I cockpit |
| VideoGenerationPage | T2V/I2V cockpit |
| ModelManagerPage | Stage-1 inventory browser (wired) |
| WorkflowLibraryPage | Import + readiness |
| SettingsPage | Theme, defaults, disclosure |
| CharacterStudioPage / ComicStudioPage | In tree under `qt_ui/studios/` |
| Chain studio (`qt_ui/chain/`) | Engine proven; may be nav-gated |
| ManagerPage / DatasetGenerationPage | Exist; historically under-wired |
| Inspire | Often ModePage stub |

## Theming

All chrome via `ThemeManager` tokens. Content pages own dedicated QSS — **never** apply `shellStyleSheet()` to nested pages.

## Related

[[Generation Cockpit]] · [[Theme System ArcaneGlass]] · [[Character and Comic Studios]]
""",
    )

    w(
        "Systems/Generation Cockpit.md",
        f"""---
title: Generation Cockpit
type: system
status: implemented
sources:
  - qt_ui/ImageGenerationPage.*
  - qt_ui/VideoGenerationPage.*
  - qt_ui/generation/
  - CLAUDE.md §2
updated: {DATE}
---

# Generation Cockpit

## Layout contract

- Fits viewport — **no page scroll**
- Pinned Prompt card + inspector tabs (Model / Sampling / Output / Advanced) as stacked widget
- Simple/Advanced reveals in place
- Primary Generate is the **only** loud colored control

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

[[Worker Protocol]] · [[Video Families]] · [[UX Principles]]
""",
    )

    w(
        "Systems/Worker Service.md",
        f"""---
title: Worker Service
type: system
status: implemented
sources:
  - python/worker_service.py
  - python/worker_service_state.py
  - docs/design/20_worker_runtime_ground_truth_map.md
  - docs/design/21_worker_refactor_plan.md
updated: {DATE}
---

# Worker Service

## Role

Backend process: TCP handler, queue, command dispatch, family runners, Comfy orchestration.

## Major modules

| Module | Concern |
|--------|---------|
| `worker_service.py` | Entry, dispatch, runners (`run_t2i`, `run_i2i`, `run_comfy_workflow`, `run_native_video`, …) — still large (“god file”) |
| `worker_service_state.py` | Job SM + records (stdlib-only) |
| `worker_client.py` | CLI bridge for UI |
| `runtime_adapters/` | Diffusers / Comfy workflow / native video bases |
| `video_adapters/` | Wan, LTX, generic + registry |
| `video_family_contracts.py` | Family capability contracts |
| `model_*` / `node_*` | Inventory + dependency resolution |
| `workflow_*` | Import / scan / profiles |
| `memory_optimization.py` | Shared-weight + fp16 cast path for image pipes |
| `ltx_*.py` | Prompt-API fallback + history/requeue helpers |

## Logging gotcha

Root logger defaults to **WARNING** — `logging.info` is invisible. Promote diagnostics to WARNING+.

## Health / tests

- Pytest session fixture spawns worker on free port (`tests/conftest.py`)
- Contract tests: ping, queue/`noop_slow`, LoRA adapters, workflow import, family builders
- Smoke tier deselected by default (`-m "not smoke"`)

## Related

[[Job Lifecycle Contract]] · [[Native Comfy Template Pattern]] · [[Image Families and Memory]]
""",
    )

    w(
        "Systems/ComfyUI Runtime.md",
        f"""---
title: ComfyUI Runtime
type: system
status: implemented
sources:
  - CLAUDE.md §4 §9
  - docs/design/25_gated_comfyui_update_plan.md
  - python/comfy_bootstrap.py
updated: {DATE}
---

# ComfyUI Runtime

## Live vs rollback (resolved 2026-07-17)

| Role | Path |
|------|------|
| **LIVE** | `C:\\\\sv_comfynext\\\\ComfyUI` (core ~2026-07-10), isolated venv `C:\\\\sv_comfynext\\\\.venv` |
| **ROLLBACK** | `D:\\\\AI_ASSETS\\\\comfy_runtime\\\\ComfyUI` (May core) + backup under `F:\\\\comfy_backup\\\\…` |
| Models/assets | **`D:/AI_ASSETS/models`** (shared via `extra_model_paths.yaml`) |
| Imported workflows | `<projectRoot>/runtime/imported_workflows` (project-relative, by design) |

## Process

- Port `:8188`; health `GET /system_stats`; ~90s startup timeout
- Launchers: `scripts/dev/start_comfy.ps1`, `run_ui.ps1`
- **PYTHONUTF8=1 required** on Jul-core or RES4LYF can crash stderr logging
- Kornia **pinned 0.8.2** in Comfy venv; sageattention/triton-windows present
- Worker stays on **project** `.venv` — venvs decoupled; HTTP-bridged

## Drift

`runtime_paths.py:default_comfy_root()` (`runtime/comfy/ComfyUI`) is unused drift — do not treat as live.

## Related

[[Dev Environment]] · [[Native Comfy Template Pattern]] · [[ADR-004 Asset and Comfy roots]]
""",
    )

    w(
        "Systems/Model Library.md",
        f"""---
title: Model Library
type: system
status: partial
sources:
  - qt_ui/ModelManagerPage.*
  - docs/SPELLVISION_MODEL_MANAGER_SPEC.md
  - docs/design/22_model_library_arc.md
  - CLAUDE.md §6
updated: {DATE}
---

# Model Library

## Stage-1 (implemented)

`ModelManagerPage` — recursive scan of models root (`D:/AI_ASSETS/models`), tree (Name/Type/Family/Size/Status), details panel, disk cache `model_inventory_cache.json`.

Verified live historically at scale (700+ assets). Visual polish lags cockpit (pre token sweeps).

## Not yet full spec

Full `SPELLVISION_MODEL_MANAGER_SPEC.md` includes downloads, dependency health, compatibility cues — Stage 1 only. Cache root “not configured” for downloads historically.

## License surfacing

Family specs carry `commercial_use` / `license_note` — UI badge + commercial-use warning still scoped for v1.0 ([[v1.0 Roadmap Synthesis]]).

## Related

[[Image Families and Memory]] · [[Video Families]] · [[Open Questions Register]]
""",
    )

    w(
        "Systems/Workflow Library Flows.md",
        f"""---
title: Workflow Library Flows
type: system
status: implemented
sources:
  - qt_ui/WorkflowLibraryPage.*
  - python/workflow_importer.py
  - python/workflow_scanner.py
  - CLAUDE.md §6
updated: {DATE}
---

# Workflow Library (Flows)

## Role

Import Comfy workflows → dependency/readiness → launch/materialize. On-ramp for native-family templatization.

## Storage

`runtime/imported_workflows` under project root (not asset-root). Empty count was historical empty-dir state, not a root bug.

## Related

[[Native Comfy Template Pattern]] · [[ComfyUI Runtime]]
""",
    )

    w(
        "Systems/Chain Studio.md",
        f"""---
title: Chain Studio
type: system
status: implemented
sources:
  - qt_ui/chain/
  - docs/design/CHAIN_STUDIO_*.md
  - CLAUDE.md §6
updated: {DATE}
---

# Chain Studio

## Role

Multi-stage composition backbone (image chain proven; 3D stages defined but execution-disabled until workers exist).

## Status

- Track A engine + Track B surface historically most-finished generation path
- Often **nav-gated** for v1.0 polish (`SPELLVISION_SHOW_ALL_MODES=1` to show)
- Under-documented in stale `FEATURE_MATRIX` (omission, not absence)

## Related

[[Character and Comic Studios]] · [[Phase D 3D Plan]] · [[Current State Ledger]]
""",
    )

    w(
        "Systems/Character and Comic Studios.md",
        f"""---
title: Character and Comic Studios
type: system
status: partial
sources:
  - qt_ui/studios/CharacterStudioPage.*
  - qt_ui/studios/ComicStudioPage.*
  - docs/design/29_character_comic_studios.md
  - docs/design/11d_character_creation_end_to_end_runbook.md
  - docs/design/SpellVision_v1.0_Roadmap.md
updated: {DATE}
---

# Character and Comic Studios

## In tree

Create-mode pages under `qt_ui/studios/` with glass panels, Simple/Advanced, generate handoff into T2I/I2I cockpit path, runtime project JSON under `runtime/characters/` and `runtime/comics/`.

## Roadmap label tension

v1.0 roadmap banks specialized Chain child pages to **v2.0**. Code + studio skill treat them as active surfaces. Treat roadmap as **ship-scope** statement; treat code as **implementation existence**. See [[Contradiction Ledger]].

## Character

Stages per 11d runbook; mesh stages may probe external SpellBound/Pixal3D spike — never fake success if tools missing.

## Comic

Layout presets, panel prompts, generate-all = first incomplete panel, page composite export. Side columns must scroll.

## Related

[[Qt UI Shell]] · [[Generation Cockpit]] · [[UX Principles]]
""",
    )

    w(
        "Systems/Theme System ArcaneGlass.md",
        f"""---
title: Theme System ArcaneGlass
type: system
status: implemented
sources:
  - qt_ui/ThemeManager.*
  - qt_ui/DashboardGlassPanel.*
  - docs/design/16_theme_token_reference.md
  - docs/design/ArcaneGlass_token_spec.md
updated: {DATE}
---

# Theme System (ArcaneGlass)

## Tokens

`ThemeManager` exposes Color / Spacing / Type / Chrome enums. Spacing: snap off-scale literals to tokens; **literal zero stays zero**.

## Glass

`DashboardGlassPanel::paintEvent` stack (shadow → GlassFill mix → specular → accent glow → vignette → dual rim). Painted glass, not DWM acrylic.

## Presets

Arcane Glass, Obsidian Studio, Neon Forge, Ivory Holograph (+ others). **ArcaneGlass is north-star skin**; default may still be another preset until showcase migration.

## QSS pitfall

Never `QString::arg` past `%9` for multi-token sheets — use `@token@` + `replace`. Shell QSS only on MainWindow.

## Related

[[UX Principles]] · [[Qt UI Shell]] · [[Known Bugs and Footguns]]
""",
    )

    w(
        "Systems/Video Families.md",
        f"""---
title: Video Families
type: system
status: implemented
sources:
  - python/video_family_contracts.py
  - python/video_adapters/
  - docs/design/26_families_done_milestone.md
  - CLAUDE.md §6
updated: {DATE}
---

# Video Families

## Contract table (code)

| Family | validation_status | backend_route | Tasks |
|--------|-------------------|---------------|-------|
| wan | production | native_comfy_template | t2v, i2v |
| ltx | production | native_comfy_template | t2v, i2v |
| hunyuan_video | production | native_comfy_template | t2v, i2v |
| mochi | production | native_comfy_template | t2v |
| cogvideox | detected | future_comfy_profile | — |
| workflow | configured | comfy_workflow_profile | imported graphs |

## Practical matrix (product)

| Family | T2V | I2V | License notes |
|--------|-----|-----|---------------|
| LTX-2.3 | proven native AV | proven native | permissive |
| Wan 2.x | dual-noise production | 2.1 single-model green; 2.2 dual-noise i2v tracked | permissive |
| Hunyuan | production native | **reconcile docs** — Doc 26 claims kijai-proven; contract notes CLIPVision encode block pre/post Comfy cutover | non-commercial (Tencent) |
| Mochi-1 | production | n/a (t2v-only) | Apache-2.0 |

## LTX operating points

- Default: distilled two-stage (VRAM-safer); single-stage-full opt-in
- Full model wants higher steps (25–40); CFG ~3–5
- Caps: ÷32 spatial; frames `(N×8)+1`
- LoRA opt-in (no default chel)

## Related

[[Native Comfy Template Pattern]] · [[Acceptance Evidence Ledger]] · [[Contradiction Ledger]]
""",
    )

    w(
        "Systems/Image Families and Memory.md",
        f"""---
title: Image Families and Memory
type: system
status: implemented
sources:
  - CLAUDE.md §6–7
  - python/memory_optimization.py
  - tests/test_worker_lora_adapters.py
  - docs/design/26_families_done_milestone.md
updated: {DATE}
---

# Image Families and Memory

## Families (v1.0 matrix closed)

SDXL/Pony/Illustrious, Flux (t2i+i2i), PixArt-Σ, Lumina 2.0, Z-Image Turbo, Anima — render-verified on product surface per Doc 26.

## VRAM / shared weights

- `build_paired_pipelines` from `memory_optimization.py` wired into `build_pipelines`
- fp32 checkpoints: CPU cast to fp16 before device move (`cast_fp32_to_fp16`)
- Shared UNet for t2i+i2i; LoRAs as **non-destructive named adapters** (`load_lora_weights` + `set_adapters`, never `fuse_lora`)
- Guarded by `tests/test_worker_lora_adapters.py` (A→B→A + no-LoRA-after-LoRA)

## Related

[[Worker Service]] · [[Model Library]] · [[Known Bugs and Footguns]]
""",
    )

    w(
        "Systems/Phase D 3D Plan.md",
        f"""---
title: Phase D 3D Plan
type: system
status: specified_not_built
sources:
  - CLAUDE.md §6 Phase D
  - docs/design/11b_3d_pipeline_phase_d_execution_plan.md
  - docs/design/11c_3d_pipeline_consolidated_master_plan.md
updated: {DATE}
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
""",
    )

    # Planning
    w(
        "Planning/Planning MOC.md",
        f"""---
title: Planning MOC
type: moc
updated: {DATE}
---

# Planning MOC

- [[Current State Ledger]]
- [[v1.0 Roadmap Synthesis]]
- [[Acceptance Evidence Ledger]]
- [[Build and Verify Commands]]
""",
    )

    w(
        "Planning/Current State Ledger.md",
        f"""---
title: Current State Ledger
type: planning
status: living
updated: {DATE}
authority: CLAUDE.md + code over FEATURE_MATRIX
---

# Current State Ledger

Synthesized {DATE}. Re-verify consequential claims in code before acting.

## Green — implemented + product-proven (per authoritative docs)

| Area | Notes |
|------|-------|
| Shell + theme tokens | Rail, title bar, ThemeManager, glass panels |
| T2I / I2I cockpits | Functional; multi-family image matrix closed |
| T2V / I2V cockpits | Functional (matrix docs stale if they say Planned) |
| LTX native AV | Production default route |
| Wan t2v dual-noise | Production |
| Wan i2v 2.1 + VAE guard | Cell green; 2.2 dual-noise i2v still build task |
| Chain Studio engine | Proven; may be nav-gated |
| Flows import/readiness | Working with real imports |
| ModelManager Stage-1 | Wired inventory browser |
| Worker SM extraction | `worker_service_state.py` |
| Shared-weight fp16 image path | Wired + LoRA adapter tests |
| Comfy cutover | Live on C: sv_comfynext |

## Partial

| Area | Gap |
|------|-----|
| License badges | Data in specs; UI surfacing open |
| Wan 2.2 dual-noise i2v | Tracked Arc-1 build |
| Hunyuan i2v | Doc 26 vs contract notes conflict |
| Character/Comic studios | Code present; v1.0 ship scope deferred / polish varies |
| Model Manager | Not full download/compat spec |
| History | Mode-aware spine still polish item |
| Shipping | Installer + first-run + guided deps ~15% |

## Specified / not built (v2.0+)

Phase D 3D execution, audio depth, LLM orchestration, Comfy auto-update, installer bundling spike.

## Stale surfaces (do not trust alone)

- `docs/SPELLVISION_FEATURE_MATRIX.md` — video Planned; omits Chain
- README LTX “experimental” — superseded by native production
- Guides listing Rust as prereq
- `runtime_paths.default_comfy_root` path

## Related

[[Contradiction Ledger]] · [[Acceptance Evidence Ledger]] · [[v1.0 Roadmap Synthesis]]
""",
    )

    w(
        "Planning/v1.0 Roadmap Synthesis.md",
        f"""---
title: v1.0 Roadmap Synthesis
type: planning
status: accepted_scope
sources:
  - docs/design/SpellVision_v1.0_Roadmap.md
  - docs/design/26_families_done_milestone.md
  - docs/design/27_v1.0_task_backlog.md
  - docs/design/28_release_readiness_checklist.md
updated: {DATE}
---

# v1.0 Roadmap Synthesis

## Settled scope forks

| Fork | Decision |
|------|----------|
| 3D pipeline Phase D | **v2.0** |
| Comic + Character as ship features | Roadmap **v2.0** (code may already exist) |
| UI polish | **v1.0 all-in** |

## Arc 1 — Families (~85%)

Matrix nearly complete. Remaining: license badge wiring; Wan 2.2 dual-noise i2v (quality upgrade); confirm no additive family gates ship.

## Arc 2 — UI polish (~60%)

Load-bearing: **#12 mode-aware history**. Also palettes, glass states, layout-to-mockup, Simple copy, upscale tier UI, cosmetic tail.

## Arc 3 — Shipping (~15%) — true gate

1. Guided dependency resolution (format-aware, placement-correct, license-flagged; HF token gap)
2. Installer bundling spike (Qt + Python + CUDA + Comfy isolated venv + PYTHONUTF8)
3. First-run wizard assembly
4. Run Doc 28 gates last

## Critical path order

Arc-1 loose ends → mode-aware history early → dep resolution before installer → installer spike → first-run → Doc 28 gate run.

## Related

[[Audience and Shipping Bar]] · [[Acceptance Evidence Ledger]] · [[Open Questions Register]]
""",
    )

    w(
        "Planning/Acceptance Evidence Ledger.md",
        f"""---
title: Acceptance Evidence Ledger
type: planning
status: living
updated: {DATE}
---

# Acceptance Evidence Ledger

Track acceptance as a **vector**, not a single “done” label.

| Item | Impl exists | Regression guard | Product/render proof | Durable artifact | Decision accepted | Downstream integration | Repo status closed |
|------|-------------|------------------|----------------------|------------------|-------------------|------------------------|--------------------|
| Image family matrix | Y | partial (pytest + smokes) | Y (Doc 26) | docs + commits | Y | cockpit + models | Y for matrix |
| LTX native t2v/i2v | Y | partial | Y (CLAUDE §6) | template JSON + commits | Y | Video cockpit | Y native prod |
| Wan t2v dual-noise | Y | builder tests | Y | commits | Y | Video cockpit | Y |
| Wan i2v 2.1 + VAE guard | Y | dry-run noted | Y | commit 33f631d | Y (Option A) | Video cockpit | A closed; B open |
| Wan 2.2 dual-noise i2v | N | N | N | Doc 27 | scheduled | — | N |
| Hunyuan t2v | Y | — | Y | commits | Y | cockpit | Y |
| Hunyuan i2v | ? | — | conflicting | Doc 26 vs contract | **reconcile** | — | N |
| Mochi t2v | Y | — | Y | commit 0fabe6a | Y | cockpit | Y |
| License UI badges | N | N | N | Doc 26 §4 | scoped | Model cards | N |
| Chain Studio spine | Y | — | Y historical | design docs | Y engine | nav gate | partial ship |
| Mode-aware history | N/partial | N | N | roadmap #12 | Y needed | History | N |
| Installer bundle | N | N | N | Doc 25/28 | Y needed | ship | N |
| Guided dep resolution | partial map | N | N | Doc 19 | Y needed | first-run | N |
| Phase D 3D | N | N | N | 11b/11c | deferred v2 | — | parked |
| Job SM ping path | Y | strict xfail | N (bug) | ARCHITECTURE.md | known bug | queue UX | N |

## How to update

When a family or subsystem lands: tick dimensions with **paths/commits/test names**, never vibes.

## Related

[[Current State Ledger]] · [[Contradiction Ledger]] · [[Job Lifecycle Contract]]
""",
    )

    w(
        "Planning/Build and Verify Commands.md",
        f"""---
title: Build and Verify Commands
type: planning
updated: {DATE}
---

# Build and Verify Commands

Canonical ops live in [[Dev Environment]]. Short list:

```powershell
Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue
.\\scripts\\dev\\run_ui.ps1          # build + backend + Comfy + UI
.\\scripts\\dev\\rebuild_ui.ps1
.\\scripts\\dev\\start_comfy.ps1
.\\scripts\\dev\\start_backend.ps1
```

```bash
# pytest — force project venv on Windows/Hermes
export PATH="$(pwd)/.venv/Scripts:$PATH"
export VIRTUAL_ENV="$(pwd)/.venv"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
```

## Related

[[Dev Environment]] · [[Known Bugs and Footguns]]
""",
    )

    # Decisions
    w(
        "Decisions/Decision Map.md",
        f"""---
title: Decision Map
type: moc
updated: {DATE}
---

# Decision Map

| ID | Title | Status |
|----|-------|--------|
| ADR-001 | [[ADR-001 ComfyUI stays execution engine]] | accepted |
| ADR-002 | [[ADR-002 Native Comfy template path]] | accepted |
| ADR-003 | [[ADR-003 Simple Advanced disclosure]] | accepted |
| ADR-004 | [[ADR-004 Asset and Comfy roots]] | accepted |
| ADR-005 | [[ADR-005 v1.0 scope forks]] | accepted |

Owner log: [[Owner Decision Log]]
""",
    )

    w(
        "Decisions/ADR-001 ComfyUI stays execution engine.md",
        f"""---
title: ADR-001 ComfyUI stays execution engine
status: accepted
updated: {DATE}
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
""",
    )

    w(
        "Decisions/ADR-002 Native Comfy template path.md",
        f"""---
title: ADR-002 Native Comfy template path
status: accepted
updated: {DATE}
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
""",
    )

    w(
        "Decisions/ADR-003 Simple Advanced disclosure.md",
        f"""---
title: ADR-003 Simple Advanced disclosure
status: accepted
updated: {DATE}
---

# ADR-003 — Global Simple / Advanced disclosure

## Decision

One app-wide Simple/Advanced model. Advanced **reveals in place**; never relocates controls.

## Related

[[UX Principles]] · docs/design/13_simple_advanced_disclosure_phase7.md
""",
    )

    w(
        "Decisions/ADR-004 Asset and Comfy roots.md",
        f"""---
title: ADR-004 Asset and Comfy roots
status: accepted
updated: {DATE}
---

# ADR-004 — Asset and Comfy roots

## Decision

| Resource | Canonical |
|----------|-----------|
| Models/assets | `D:/AI_ASSETS/` (`models` under it) |
| LIVE Comfy | `C:\\\\sv_comfynext\\\\ComfyUI` + isolated venv |
| Worker Python | Project `.venv` |
| Imported workflows | `<repo>/runtime/imported_workflows` |

`.env` / `runtime_paths.py` values that disagree are **drift to reconcile**, not alternate truths — except deliberate project-relative workflow library.

## Related

[[ComfyUI Runtime]] · [[Dev Environment]] · [[Contradiction Ledger]]
""",
    )

    w(
        "Decisions/ADR-005 v1.0 scope forks.md",
        f"""---
title: ADR-005 v1.0 scope forks
status: accepted
updated: {DATE}
---

# ADR-005 — v1.0 scope forks

## Decision

- Phase D 3D → **v2.0**
- Character/Comic as *shipped* specialized surfaces → roadmap **v2.0** (does not erase in-tree code)
- UI polish → **v1.0**
- True gate → **shipping arc** (installer, first-run, guided deps)

## Related

[[v1.0 Roadmap Synthesis]] · [[Audience and Shipping Bar]]
""",
    )

    w(
        "Decisions/Owner Decision Log.md",
        f"""---
title: Owner Decision Log
type: log
updated: {DATE}
---

# Owner Decision Log

Minimal durable checkpoints for interactive decisions. Newest first.

## 2026-07-25 — Brain bootstrap

- Created Obsidian brain under `brain/` synthesizing CLAUDE.md, design docs 25–29, architecture, contracts, and live tree layout.
- No new product-scope decisions elicited in this pass; open items remain in [[Open Questions Register]].

## Prior (from docs, not re-elicited)

- Wan i2v: Option A done + Option B scheduled (Doc 26)
- Comfy cutover live on C: sv_comfynext (Doc 25)
- v1.0 forks: 3D/studios ship-label v2.0; polish + shipping v1.0 (Roadmap)
""",
    )

    # Specification
    w(
        "Specification/Specification MOC.md",
        f"""---
title: Specification MOC
type: moc
updated: {DATE}
---

# Specification MOC

- [[Authority and Precedence]]
- [[Contradiction Ledger]]
- [[Open Questions Register]]
- [[Spec Coverage Matrix]]
- [[Source Crosswalk]]
""",
    )

    w(
        "Specification/Authority and Precedence.md",
        f"""---
title: Authority and Precedence
type: spec
status: accepted
updated: {DATE}
---

# Authority and Precedence

When sources disagree, resolve in this order:

1. **Live config** — `.env`, `scripts/dev/*.ps1`, running ports/paths
2. **Live code + contracts** — `video_family_contracts.py`, adapters, UI wiring
3. **CLAUDE.md** — operating constitution (audit-corrected sections)
4. **Binding design docs** — Docs 25–28, v1.0 roadmap, job lifecycle, worker protocol
5. **ARCHITECTURE.md / README.md** — maps; may lag
6. **Historical sprint docs / attic** — evidence of intent, not current instruction
7. **FEATURE_MATRIX / old product roadmap** — **stale risk** — never plan solely from these

## Status language

Use [[00 Home]] legend. Never collapse “phase closed,” “code exists,” and “product proven” into one word.

## Related

[[Contradiction Ledger]] · [[Source Crosswalk]]
""",
    )

    w(
        "Specification/Contradiction Ledger.md",
        f"""---
title: Contradiction Ledger
type: spec
status: living
updated: {DATE}
---

# Contradiction Ledger

Repository-resolvable mismatches. Prefer code/live config.

| ID | Topic | Stale claim | Canonical | Action |
|----|-------|-------------|-----------|--------|
| C1 | T2V/I2V maturity | FEATURE_MATRIX / old roadmap “Planned” | Cockpits + native families work | Rebuild matrix before planning |
| C2 | LTX status | README “LTX experimental” | Native production default | Update README when touching |
| C3 | Chain Studio | Missing from FEATURE_MATRIX | Engine proven; may be nav-gated | Document in matrix |
| C4 | Rust prereq | DEV_GUIDE / SPELLVISION_ARCHITECTURE | Rust archived, unwired | Purge prereq lists |
| C5 | Comfy root | `runtime_paths.default_comfy_root` / old D: path | `C:\\\\sv_comfynext\\\\ComfyUI` live | Treat default_comfy_root as drift |
| C6 | Asset root | `.env` `${{SPELLVISION_ROOT}}/models`, `external_assets/` | `D:/AI_ASSETS/models` | Reconcile env helpers |
| C7 | Character/Comic ship scope | Roadmap v2.0 | Pages exist in `qt_ui/studios/` | Distinguish ship-scope vs code-exists |
| C8 | Hunyuan i2v | Doc 26 “render-verified kijai” | Contract readiness_notes cite CLIPVision 768-vs-1024 block / gated Comfy update | **Re-verify live** post cutover; update loser |
| C9 | Models page name | Some docs `ModelsPage` | `ModelManagerPage` | Use real type name |
| C10 | Doc 13 identity | Some cites Doc 13 = release readiness | Doc 13 = Simple/Advanced; readiness = Doc 28 | Fix citations |
| C11 | Worker line counts | ARCHITECTURE ~6700 lines | Churns; don’t hardcode | Say “large god file” |
| C12 | Theme default | North star ArcaneGlass | Runtime default may be Neon Forge | Showcase migration pending |

## Related

[[Authority and Precedence]] · [[Current State Ledger]] · [[Open Questions Register]]
""",
    )

    w(
        "Specification/Open Questions Register.md",
        f"""---
title: Open Questions Register
type: spec
status: living
updated: {DATE}
---

# Open Questions Register

Numbered, contiguous. Empty response ≠ approval.

## P0 — blocks architecture or next ship wave

### Q1 — Installer bundle strategy
**Why:** Arc-3 critical path unknown difficulty (multi-GB CUDA+Comfy isolated venv).
**Options:** (A) Full offline bundle (B) Thin client + first-run downloads (C) Hybrid pinned runtime cache (D) Dev-only zip defer public installer.
**Recommend:** C hybrid — ship managed runtime layout matching Doc 25, download models on demand.
**Status:** open

### Q2 — Hunyuan i2v truth post cutover
**Why:** Doc 26 vs `video_family_contracts` disagree; license-sensitive family.
**Options:** (A) Contract correct — still blocked (B) Doc 26 correct — unstick contract notes (C) Partial: one wrapper path only.
**Recommend:** Live render probe on current Comfy; update both surfaces same day.
**Status:** open

## P1 — blocks complete subsystem/release spec

### Q3 — Wan 2.2 dual-noise i2v in v1.0?
**Why:** Quality upgrade vs schedule; cell already green via 2.1.
**Options:** (A) Defer to post-v1.0 (B) Build before ship (C) Ship behind Advanced experimental flag.
**Recommend:** A unless marketing needs flagship i2v — Doc 26 already green via A.
**Status:** open (scheduled as build task; ship inclusion undecided)

### Q4 — License gate strength
**Why:** Hunyuan non-commercial must be honest.
**Options:** (A) Badge only (B) Soft warn on generate when commercial toggle on (C) Hard block commercial toggle.
**Recommend:** B per Doc 26.
**Status:** open (scoped, not built)

### Q5 — Character/Comic in v1.0 nav?
**Why:** Code exists; roadmap says v2.0 ship.
**Options:** (A) Hide nav (Chain pattern) (B) Ship as preview (C) Fully polish into v1.0.
**Recommend:** A for clean cut list unless demo needs them.
**Status:** open

## P2 — phase-local

### Q6 — Quantized LTX / offload for higher native res
**Why:** Softness vs 32GB ceiling.
**Status:** parked optimization thread

### Q7 — God-file decomposition timing
**Why:** Health vs feature velocity.
**Status:** explicitly out of families-done bar

### Q8 — Mode-aware history schema details
**Why:** Arc-2 #12 load-bearing; needs core + per-mode payload design ratification in implementation.
**Status:** open at design-detail level

## Related

[[Owner Decision Log]] · [[v1.0 Roadmap Synthesis]] · [[Contradiction Ledger]]
""",
    )

    w(
        "Specification/Spec Coverage Matrix.md",
        f"""---
title: Spec Coverage Matrix
type: spec
updated: {DATE}
---

# Spec Coverage Matrix

| Domain | Product intent | ADR/decision | Detailed contract | Impl | Proof | Gaps |
|--------|----------------|--------------|-------------------|------|-------|------|
| Abstraction promise | Y | ADR-001/002 | partial | Y | Y | guided deps incomplete |
| Simple/Advanced | Y | ADR-003 | Doc 13 | Y | Y | copy polish |
| Job lifecycle | Y | — | JOB_LIFECYCLE | Y | partial | ping SM bug |
| Worker protocol | Y | — | WORKER_PROTOCOL | Y | pytest | expand coverage |
| Image families | Y | Doc 26 | classifiers | Y | Y | license UI |
| Video families | Y | Doc 26 | contracts | Y | mostly | Hunyuan i2v C8; Wan 2.2 i2v |
| Model library | Y | Doc 22 / MM spec | Stage-1 only | partial | inventory | downloads/compat |
| Flows | Y | sprint10 docs | importer | Y | Y | — |
| Chain | Y | design docs | Y | Y | historical | nav/ship |
| Studios | Doc 29 | ADR-005 tension | 11d/29 | partial | varies | ship scope Q5 |
| 3D | Y | deferred | 11b/11c | N | N | whole Phase D |
| Shipping | Y | ADR-005 | Doc 28 stub | N | N | installer/deps |
| Theme | Y | — | Doc 16 / ArcaneGlass | Y | visual QA | default preset C12 |

## Related

[[Acceptance Evidence Ledger]] · [[Open Questions Register]]
""",
    )

    # Reference
    w(
        "Reference/Reference MOC.md",
        f"""---
title: Reference MOC
type: moc
updated: {DATE}
---

# Reference MOC

- [[Repository Map]]
- [[Glossary]]
- [[Source Crosswalk]]
- [[Dev Environment]]
- [[Known Bugs and Footguns]]
""",
    )

    w(
        "Reference/Repository Map.md",
        f"""---
title: Repository Map
type: reference
updated: {DATE}
---

# Repository Map

```text
SpellVision/
  qt_ui/           C++/Qt6 UI (shell, generation, studios, chain, workers, …)
  python/          worker, adapters, resolvers, templates
  tests/           pytest worker contracts
  scripts/dev/     run_ui, rebuild_ui, start/stop backend/comfy
  docs/            design + product + historical sprints
  brain/           THIS Obsidian vault (synthesized truth)
  runtime/         imported_workflows, local runtime data
  attic/           archives including rust_original_intent
  build/           CMake output (gitignored)
  .venv/           project Python (worker)
```

## Key entry files

- `CLAUDE.md` — agent/operating constitution
- `CMakeLists.txt` — UI target registration
- `python/worker_service.py` — backend entry
- `qt_ui/MainWindow.cpp` — UI composition

## Related

[[Dependency Map]] · [[Source Crosswalk]]
""",
    )

    w(
        "Reference/Glossary.md",
        f"""---
title: Glossary
type: reference
updated: {DATE}
---

# Glossary

| Term | Meaning |
|------|---------|
| **Native / native_comfy_template** | Repo-built Comfy graph path — not pure diffusers |
| **Simple / Advanced** | Global progressive disclosure |
| **Cockpit** | Generation page that must fit viewport without scroll |
| **Family** | Model lineage with contract (wan, ltx, flux, …) |
| **Flows** | Workflow Library surface |
| **Chain Studio** | Multi-stage composition spine |
| **ArcaneGlass** | North-star theme skin |
| **Worker** | Python TCP service on :8765 |
| **Cutover** | 2026-07-17 move to C: sv_comfynext Comfy |
| **God file** | Oversized `worker_service.py` pending split |
| **Prompt-API (LTX)** | Legacy/fallback route, not default |
| **Stage-1 Model Manager** | Inventory browser without full download epic |
""",
    )

    w(
        "Reference/Source Crosswalk.md",
        f"""---
title: Source Crosswalk
type: reference
updated: {DATE}
---

# Source Crosswalk

| Brain note | Primary repo sources |
|------------|----------------------|
| Product Vision | `CLAUDE.md` §1, `README.md` |
| UX Principles | `CLAUDE.md` §2, `docs/design/13_*`, ArcaneGlass spec |
| Three-Layer Architecture | `CLAUDE.md` §3, `ARCHITECTURE.md` |
| Native template | `CLAUDE.md` §6, `python/video_*`, adapters |
| Comfy runtime | Doc 25, `comfy_bootstrap.py`, launchers |
| Job lifecycle | `docs/JOB_LIFECYCLE_CONTRACT.md`, `worker_service_state.py` |
| Worker protocol | `docs/SPELLVISION_WORKER_PROTOCOL.md` |
| v1.0 roadmap | `docs/design/SpellVision_v1.0_Roadmap.md`, Docs 26–28 |
| Phase D | `CLAUDE.md` Phase D, Docs 11b/11c |
| Studios | Doc 29, `qt_ui/studios/`, skill surfaces |
| Dev env | `CLAUDE.md` §4, `scripts/dev/*` |

## Related

[[Authority and Precedence]] · [[Repository Map]]
""",
    )

    w(
        "Reference/Dev Environment.md",
        f"""---
title: Dev Environment
type: reference
status: accepted
sources:
  - CLAUDE.md §4
  - scripts/dev/*.ps1
updated: {DATE}
---

# Dev Environment

## Host

- Windows, PowerShell for launchers
- CMake ≥3.21, Visual Studio 17 2022 generator
- Qt 6.10.2 primary (`C:\\\\Qt\\\\6.10.2\\\\msvc2022_64\\\\`), fallbacks 6.8.2 → 6.7.3
- Python 3.12+ project `.venv`; Torch 2.10+cu128; CUDA 12.8; GPU class RTX 5090 32GB

## Ports

| Service | Default |
|---------|---------|
| Worker | `127.0.0.1:8765` |
| ComfyUI | `127.0.0.1:8188` |

## Commands

```powershell
Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue  # before rebuild (LNK1168)
.\\scripts\\dev\\run_ui.ps1
# switches: -NoComfy -NoBackend -FastDeploy -QtRoot
.\\scripts\\dev\\rebuild_ui.ps1
.\\scripts\\dev\\start_backend.ps1 / stop_backend.ps1
.\\scripts\\dev\\start_comfy.ps1 / stop_comfy.ps1
```

## Logs

- `build/worker_service.{{stdout,stderr}}.log`
- `build/comfy_runtime.{{stdout,stderr}}.log`
- Session JSON under `build/.*.session.json`

## Settings

QSettings org=`DarkDuck`, app=`SpellVision`.

## Env vars (observed)

`SPELLVISION_COMFY_PYTHON`, `SPELLVISION_WORKER_HOST`, `SPELLVISION_WORKER_PORT`, `SPELLVISION_COMFY_PORT`, `SPELLVISION_ROOT`, `SPELLVISION_SHOW_ALL_MODES`, `PYTHONUTF8` (Comfy).

## Related

[[ComfyUI Runtime]] · [[Build and Verify Commands]] · [[Known Bugs and Footguns]]
""",
    )

    w(
        "Reference/Known Bugs and Footguns.md",
        f"""---
title: Known Bugs and Footguns
type: reference
status: living
updated: {DATE}
---

# Known Bugs and Footguns

| Item | Detail |
|------|--------|
| QUEUED→COMPLETED | Silent fail; need STARTING→RUNNING→COMPLETED |
| logging.info | Invisible (root WARNING) |
| LNK1168 | Kill SpellVision before rebuild |
| QString::arg %10+ | Breaks QSS; use @token@ replace |
| shellStyleSheet on content pages | Parse spam + flat chrome |
| Inspector readiness | Must manually sync label |
| Stale I2I/I2V paths | Clear with setInputImagePath empty |
| IMG stub on T2I/T2V | Forbidden |
| Wan VAE mismatch | 2.1 needs wan_2.1_vae not 2.2 48-ch |
| fp32 checkpoints | Cast before device; shared weights |
| Hermes pytest | Force project venv or Pillow breaks |
| Half-screen | Functional parity required |
| object_info resets | Retry + Connection close |

## Related

[[Job Lifecycle Contract]] · [[Theme System ArcaneGlass]] · [[Dev Environment]]
""",
    )

    # Visuals
    w(
        "Visuals/System Map.md",
        f"""---
title: System Map
type: visual
updated: {DATE}
---

# System Map

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Qt UI
  participant W as Worker :8765
  participant C as Comfy :8188
  U->>UI: Intent (prompt, family, simple knobs)
  UI->>W: NDJSON request
  W->>W: Resolve family + deps + build graph
  W->>C: /prompt (+ /upload if i2v)
  C-->>W: progress / images / video
  W-->>UI: job_update stream
  UI-->>U: canvas + history
```

See also canvas: [[Architecture Overview]]
""",
    )

    # Canvas JSON
    canvas = {
        "nodes": [
            {
                "id": "home",
                "type": "file",
                "file": "00 Home.md",
                "x": 0,
                "y": 0,
                "width": 320,
                "height": 200,
            },
            {
                "id": "product",
                "type": "file",
                "file": "Product/Product Vision.md",
                "x": -400,
                "y": 280,
                "width": 280,
                "height": 160,
            },
            {
                "id": "arch",
                "type": "file",
                "file": "Architecture/Three-Layer Architecture.md",
                "x": 0,
                "y": 280,
                "width": 300,
                "height": 160,
            },
            {
                "id": "worker",
                "type": "file",
                "file": "Systems/Worker Service.md",
                "x": 360,
                "y": 280,
                "width": 280,
                "height": 160,
            },
            {
                "id": "comfy",
                "type": "file",
                "file": "Systems/ComfyUI Runtime.md",
                "x": 700,
                "y": 280,
                "width": 280,
                "height": 160,
            },
            {
                "id": "video",
                "type": "file",
                "file": "Systems/Video Families.md",
                "x": 360,
                "y": 520,
                "width": 280,
                "height": 160,
            },
            {
                "id": "plan",
                "type": "file",
                "file": "Planning/Current State Ledger.md",
                "x": -400,
                "y": 520,
                "width": 280,
                "height": 160,
            },
            {
                "id": "contra",
                "type": "file",
                "file": "Specification/Contradiction Ledger.md",
                "x": 0,
                "y": 520,
                "width": 280,
                "height": 160,
            },
            {
                "id": "questions",
                "type": "file",
                "file": "Specification/Open Questions Register.md",
                "x": 700,
                "y": 520,
                "width": 300,
                "height": 160,
            },
        ],
        "edges": [
            {"id": "e1", "fromNode": "home", "fromSide": "bottom", "toNode": "product", "toSide": "top"},
            {"id": "e2", "fromNode": "home", "fromSide": "bottom", "toNode": "arch", "toSide": "top"},
            {"id": "e3", "fromNode": "home", "fromSide": "bottom", "toNode": "worker", "toSide": "top"},
            {"id": "e4", "fromNode": "arch", "fromSide": "right", "toNode": "worker", "toSide": "left"},
            {"id": "e5", "fromNode": "worker", "fromSide": "right", "toNode": "comfy", "toSide": "left"},
            {"id": "e6", "fromNode": "worker", "fromSide": "bottom", "toNode": "video", "toSide": "top"},
            {"id": "e7", "fromNode": "home", "fromSide": "bottom", "toNode": "plan", "toSide": "top"},
            {"id": "e8", "fromNode": "plan", "fromSide": "right", "toNode": "contra", "toSide": "left"},
            {"id": "e9", "fromNode": "contra", "fromSide": "right", "toNode": "questions", "toSide": "left"},
        ],
    }
    import json

    w("Visuals/Architecture Overview.canvas", json.dumps(canvas, indent=2))

    # README for vault
    w(
        "README.md",
        f"""---
title: Brain README
updated: {DATE}
---

# SpellVision Obsidian Brain

Open **this folder** (`brain/`) as an Obsidian vault.

- Start at [[00 Home]]
- Authority: [[Authority and Precedence]]
- Agent skill: Hermes skill `spellvision` (project umbrella) + `spellvision-qt-studio-surfaces` (UI)

Generated/maintained for agent + human navigation. Prefer updating ledgers when code truth moves.
""",
    )

    print(f"\\nVault root: {ROOT}")
    md_count = len(list(ROOT.rglob("*.md")))
    print(f"Markdown notes: {md_count}")


if __name__ == "__main__":
    main()
