# Sprint 10 Workflow Dependency Layer

## Goal

Turn the workflow importer/scanner into an executable dependency planner that can:

1. import ComfyUI workflows from JSON or embedded metadata,
2. detect likely missing custom nodes and model assets,
3. bootstrap a ComfyUI runtime with ComfyUI-Manager available out of the box,
4. generate a concrete install plan for nodes and models,
5. optionally execute that install plan,
6. keep SpellVision's opinionated UI by converting imported workflows into profiles.

## Architecture

The dependency layer sits after the workflow scanner and before queue execution.

```text
workflow source
    ↓
workflow_scanner.py
    ↓
node_dependency_resolver.py ──→ comfy_manager_bridge.py
    ↓
model_dependency_resolver.py ──→ model_sources.py
    ↓
workflow_importer.py
    ↓
artifacts/
  workflow.json
  scan_report.json
  profile.json
  dependency_plan.json
  dependency_apply_result.json (optional)
```

## Design principles

### 1. Manager is infrastructure, not the UI

SpellVision stays the primary front-end. ComfyUI-Manager is used as a package/install backend for custom nodes.

### 2. Node dependencies and model dependencies are separate

A workflow can fail because:
- node packages are missing, or
- model files are missing.

SpellVision should report those independently.

### 3. Curated node catalogs beat fragile guessing

The scanner can detect unknown custom-node classes, but class-to-package mapping is inherently fuzzy.
The resolver therefore supports:
- a starter catalog bundled with SpellVision,
- project-local catalogs,
- user overrides,
- manual git fallback for repos outside the registry.

### 4. Import first, apply later

The importer always produces a dependency plan even if auto-install is disabled.
That keeps the import deterministic and reviewable.

## Main modules

### comfy_manager_bridge.py

Responsibilities:
- detect the ComfyUI root structure,
- ensure ComfyUI-Manager exists,
- install manager requirements,
- run `cm-cli.py`,
- list installed custom nodes,
- install registry-backed custom nodes,
- clone git-based custom nodes when needed,
- optionally enable CLI-only mode.

### node_dependency_resolver.py

Responsibilities:
- inspect `WorkflowScanReport.missing_custom_nodes`,
- match custom class names against a node catalog,
- mark likely installed packages,
- produce install actions:
  - `manager_install`
  - `git_clone`
  - `already_installed`
  - `manual_review`

### model_dependency_resolver.py

Responsibilities:
- inspect model references from the scan report,
- map asset kinds into ComfyUI model folders,
- use `model_sources.py` to materialize local, URL, Hugging Face, and Civitai assets,
- produce install/copy actions,
- optionally copy or move files into ComfyUI model directories.

## Suggested runtime layout

```text
runtime/
  comfy/
    ComfyUI/
      main.py
      custom_nodes/
        ComfyUI-Manager/
      models/
        checkpoints/
        loras/
        vae/
        controlnet/
        clip/
        diffusion_models/
        unet/
```

## Import flow

1. User imports workflow.
2. Scanner builds scan report.
3. Node resolver builds a node install plan.
4. Model resolver builds a model install plan.
5. Importer writes the plan to `dependency_plan.json`.
6. If auto-apply is enabled:
   - bootstrap manager,
   - install nodes,
   - copy/download models,
   - write `dependency_apply_result.json`.
7. Workflow profile is now associated with a known dependency state.

## Extension points

- replace the starter node catalog with a richer catalog or registry sync,
- add profile-specific dependency hints,
- add workflow-pack manifests,
- surface the plan in Qt for approval before install,
- lock node versions when registry metadata is available.
