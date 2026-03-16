# Sprint 10 Architecture: ComfyUI Workflow Importer and Scanner

## Goal

SpellVision should accept third-party ComfyUI workflows, analyze them, resolve what they need, and expose them through the SpellVision interface without turning the app into a raw node-editor clone.

This first implementation milestone focuses on three concrete capabilities:

1. import a workflow from JSON or image-embedded metadata
2. scan it for nodes, models, task type, and user-facing controls
3. generate a SpellVision workflow profile that maps the graph to canonical UI slots

This keeps the UI task-first and queue-first while still letting you benefit from the ComfyUI ecosystem.

---

## Design principles

### 1. SpellVision owns the UX
Imported workflows are backend implementations, not the UI itself.  
A workflow becomes a **profile** with slot bindings rather than a new screen full of raw nodes.

### 2. Nodes and models are separate dependency systems
A workflow can fail because:
- a custom node package is missing
- a model asset is missing
- a model asset exists but is wired to the wrong field
- a workflow is structurally valid but does not expose the controls SpellVision expects

The scanner must report these separately.

### 3. Canonical slots are the contract
SpellVision needs a stable UI contract that is independent of any single workflow graph.

Canonical slots include:
- prompt
- negative_prompt
- seed
- steps
- cfg
- sampler
- scheduler
- width
- height
- fps
- num_frames
- input_image
- input_video
- checkpoint
- vae
- loras
- output_prefix

Future slots can include:
- audio
- motion_strength
- control_image
- reference_image
- depth_map
- mask_image
- rig_input
- mesh_input

### 4. Profiles are generated artifacts
An imported workflow should create two persistent artifacts:
- the stored workflow JSON
- a SpellVision profile JSON with slot bindings and scan metadata

This lets the user run a workflow from the normal SpellVision UI without manually editing the graph again.

---

## Component layout

### `workflow_scanner.py`
Responsible for:
- loading workflows from `.json`, `.png`, `.webp`, or raw JSON text
- normalizing ComfyUI graph shapes where practical
- extracting node ids and class names
- detecting task type
- detecting model references
- detecting custom node requirements
- detecting slot candidates
- producing a structured scan report

### `comfy_slot_mapper.py`
Responsible for:
- mapping graph inputs to canonical SpellVision slots
- scoring candidate bindings
- creating a profile object with `slot_bindings`

### `workflow_importer.py`
Responsible for:
- orchestrating load + scan + slot map
- copying the source workflow into a managed SpellVision workflow library
- generating a profile JSON
- returning a summary result the Qt UI can show to the user

### `workflow_profile_registry.py`
Responsible for:
- saving and loading profile manifests
- listing profiles
- resolving profile paths

---

## Data flow

```text
Import Source
  -> workflow_scanner.load_workflow_source()
  -> workflow_scanner.scan_workflow()
  -> comfy_slot_mapper.build_profile_from_scan()
  -> workflow_importer.import_workflow()
  -> Stored workflow JSON + Stored profile JSON
  -> SpellVision queue/runtime
```

---

## Supported workflow sources in this milestone

### JSON
- Comfy API prompt format keyed by node id
- raw JSON text pasted by the user
- local `.json` files

### PNG / WebP metadata
This implementation checks common embedded metadata locations used by Comfy-style exports, including:
- `workflow`
- `prompt`
- selected image metadata text blocks

If a file does not contain readable embedded workflow JSON, import should fail cleanly with a clear message.

---

## Scanner responsibilities

The scanner produces a `WorkflowScanReport` with:

- source metadata
- detected graph format
- node list
- node counts
- required node packages (heuristic)
- model references
- inferred task command
- inferred media type
- inferred model family hints
- slot candidates
- warnings
- errors

### Task inference
The scanner should infer:
- `t2i`
- `i2i`
- `t2v`
- `i2v`
- `v2v`
- `upscale`
- `unknown`

Inference is heuristic and based on:
- node class names
- presence of image/video input slots
- output nodes
- frame/fps-related controls
- model-family naming hints such as wan, ltx, hunyuan, cogvideo, mochi

### Model reference detection
The scanner should detect references such as:
- checkpoint names
- unet names
- vae names
- lora names
- controlnet names
- clip names
- repo ids
- filename prefixes

These references are only detections in this phase. Actual installation or download is handled later by dedicated dependency resolvers.

---

## Slot binding rules

The slot mapper takes the scan report and produces a `WorkflowProfile`.

Each binding stores:
- canonical slot name
- node id
- input name
- binding path
- confidence score
- optional note

Example:

```json
{
  "slot": "prompt",
  "node_id": "12",
  "input_name": "text",
  "path": "12.inputs.text",
  "confidence": 0.98
}
```

### Binding strategy
1. prefer exact canonical aliases
2. prefer prompt-bearing text nodes for prompt slots
3. prefer loader nodes for checkpoint / lora / vae slots
4. prefer numeric sampler/video nodes for fps / frames / steps / cfg
5. record ambiguous candidates as warnings rather than silently choosing bad bindings

---

## Import result

The importer returns:
- copied workflow path
- generated profile path
- scan report path
- inferred task type
- detected missing custom nodes
- detected missing models
- warnings and errors

This is the right payload for a future Qt `WorkflowImportDialog`.

---

## Storage layout

Recommended layout under the repo/runtime root:

```text
runtime/
  comfy/
    workflows/
      imported/
        <slug>/
          workflow.json
          scan_report.json
          profile.json
```

For early local development, any writable root can be used.

---

## Integration plan

### Phase 1: importer/scanner/profile generation
Delivered in this bundle.

### Phase 2: dependency resolution
Add:
- `comfy_manager_bridge.py`
- `node_dependency_resolver.py`
- `model_dependency_resolver.py`

These will install missing custom nodes and fetch missing model assets.

### Phase 3: Qt integration
Add:
- workflow import dialog
- import summary view
- profile browser
- "Run with SpellVision UI" action

### Phase 4: runtime integration
- allow profile-based execution through the normal queue
- feed profile bindings into the Comfy runtime adapter
- let the adapter apply SpellVision field values to the workflow before submission

---

## Why this matches the app plan

This architecture keeps SpellVision aligned with the broader roadmap:
- image generation
- video generation
- later 3D/world generation
- voice
- rigging

A stable importer/scanner/profile layer means outside workflows can be absorbed into the platform without giving up the clean UI or the queue/history-driven workflow you want.

---

## Current limitations in this milestone

- UI-exported LiteGraph workflows are scanned heuristically and not fully reconstructed into API-prompt format
- custom node package names are inferred heuristically from class names
- actual node installation is not included yet
- actual model installation is not included yet
- ambiguous slot bindings are reported, not auto-resolved through a GUI
- no Qt dialog layer is included yet

These are acceptable limits for a first architecture-driven implementation.
