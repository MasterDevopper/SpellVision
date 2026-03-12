# SPELLVISION_MODEL_MANAGER_SPEC.md

## Purpose

This document defines the SpellVision model management system for:

-   checkpoints
-   LoRAs
-   video models
-   3D models
-   voice models
-   local LLM helper models

The Model Manager must make it easy to install, organize, inspect,
cache, and use models without mixing UI logic with backend execution
logic.

------------------------------------------------------------------------

## Goals

The Model Manager should:

-   detect installed models
-   organize models by type
-   track metadata
-   support local files and named repo references
-   expose compatibility info
-   support future downloads and updates
-   avoid committing model weights to Git
-   provide a stable interface to the UI and worker backend

------------------------------------------------------------------------

## Non-Goals

The Model Manager should not:

-   directly run inference
-   directly own generation job execution
-   embed model-specific pipeline logic in the UI
-   require cloud access for basic local operation

------------------------------------------------------------------------

## Model Categories

SpellVision should support the following categories.

### Image

-   SD 1.5
-   SDXL
-   Flux
-   image upscalers
-   control / adapter models later

### LoRA

-   SD 1.5 LoRAs
-   SDXL LoRAs
-   Flux adapters later

### Video

-   text-to-video models
-   image-to-video models
-   interpolation models

### 3D

-   image-to-3D models
-   text-to-3D models
-   texture models

### Voice

-   TTS models
-   voice cloning models
-   vocoders

### LLM / Assistant

-   Ollama-managed local models
-   prompt optimization models
-   workflow assistant models

------------------------------------------------------------------------

## Recommended Directory Layout

``` text
models/
├─ checkpoints/
│  ├─ sd/
│  ├─ sdxl/
│  ├─ flux/
│  └─ misc/
├─ loras/
│  ├─ sd/
│  ├─ sdxl/
│  ├─ flux/
│  └─ recipes/
├─ video/
├─ 3d/
├─ voice/
├─ llm/
└─ metadata/
```

### Notes

-   `metadata/` stores sidecar metadata files when model files do not
    already provide enough metadata.
-   `recipes/` can store LoRA combinations or preset bundles later.
-   actual model weights must remain ignored by Git.

------------------------------------------------------------------------

## Core Model Record

Every model should be represented internally as a normalized record.

Example conceptual fields:

``` json
{
  "id": "sdxl_nova_exanime_xl_v50",
  "display_name": "Nova Exanime XL v5.0",
  "category": "checkpoint",
  "family": "sdxl",
  "path": "C:/.../models/checkpoints/novaExanimeXL_ilV50.safetensors",
  "format": "safetensors",
  "source": "local",
  "base_model": "sdxl",
  "compatible_lora_families": ["sdxl"],
  "preview_image": "",
  "description": "",
  "tags": ["anime", "stylized"],
  "version": "",
  "sha256": "",
  "file_size_bytes": 0,
  "last_modified_utc": "",
  "status": "ready"
}
```

------------------------------------------------------------------------

## Required Fields

These fields should exist for all model records:

-   `id`
-   `display_name`
-   `category`
-   `family`
-   `path` or `repo_id`
-   `source`
-   `status`

------------------------------------------------------------------------

## Recommended Additional Fields

These fields are strongly recommended:

-   `format`
-   `base_model`
-   `compatible_lora_families`
-   `preview_image`
-   `description`
-   `tags`
-   `version`
-   `sha256`
-   `file_size_bytes`
-   `last_modified_utc`

------------------------------------------------------------------------

## Category-Specific Metadata

### Checkpoints

Should include:

-   base family
-   suggested resolution
-   recommended dtype
-   preferred pipeline
-   VAE notes if needed

### LoRAs

Should include:

-   compatible base family
-   trigger words if known
-   recommended weight range
-   preview images
-   recipe / style notes

### Video models

Should include:

-   input mode (T2V / I2V)
-   supported resolutions
-   estimated VRAM
-   frame constraints

### 3D models

Should include:

-   input type
-   output format
-   mesh or NeRF style
-   texture support

### Voice models

Should include:

-   language
-   gender/style notes if applicable
-   sample rate
-   voice cloning support

### LLM models

Should include:

-   provider (`ollama`)
-   context size if known
-   intended role (`prompt_optimizer`, `assistant`, etc.)

------------------------------------------------------------------------

## Model Sources

SpellVision should support two source types.

### Local file source

Examples:

-   `.safetensors`
-   `.ckpt`
-   `.bin`
-   model folders

### Named source

Examples:

-   Hugging Face repo IDs
-   Ollama model names

Examples:

``` text
stabilityai/stable-diffusion-xl-base-1.0
mistral-small
```

------------------------------------------------------------------------

## Discovery Rules

The Model Manager should scan known directories and build records from
discovered files.

### Checkpoint discovery

Look for:

-   `*.safetensors`
-   `*.ckpt`
-   `*.pt`
-   `*.bin`

### LoRA discovery

Look for:

-   `*.safetensors`
-   `*.bin`

### Sidecar discovery

If a sidecar file exists next to a model file, load it.

Examples:

``` text
model.safetensors
model.metadata.json
model.preview.png
```

------------------------------------------------------------------------

## Sidecar Metadata Format

SpellVision should support sidecar metadata JSON files.

Example:

``` json
{
  "display_name": "Shexyo Style Trigger",
  "base_model": "sdxl",
  "trigger_words": ["shexyo"],
  "recommended_weight_min": 0.6,
  "recommended_weight_max": 1.1,
  "tags": ["style", "anime"],
  "description": "Stylized anime LoRA with clean linework.",
  "preview_image": "shexyo_style_trigger.preview.png"
}
```

------------------------------------------------------------------------

## UI Responsibilities

The Qt UI should use the Model Manager to:

-   populate model lists
-   populate LoRA lists
-   filter by family or type
-   show metadata
-   show preview images
-   show compatibility warnings

The UI should not do low-level model scanning itself once the Model
Manager is fully implemented.

------------------------------------------------------------------------

## Backend Responsibilities

The Python backend should use Model Manager outputs to:

-   resolve selected models
-   validate compatibility
-   prepare pipeline load requests
-   store generation metadata using normalized identifiers

------------------------------------------------------------------------

## Compatibility Rules

### Checkpoint ↔ LoRA

The manager should reject or warn on incompatible family pairs.

Examples:

-   SDXL checkpoint + SDXL LoRA → allowed
-   SD 1.5 checkpoint + SDXL LoRA → reject
-   Flux checkpoint + SDXL LoRA → reject unless explicit adapter support
    exists

### Video / 3D / Voice

These should not appear in standard image-generation selection widgets.

------------------------------------------------------------------------

## Status Values

Suggested status values:

-   `ready`
-   `missing`
-   `invalid`
-   `incompatible`
-   `downloading`
-   `installing`
-   `corrupt`

------------------------------------------------------------------------

## Caching Integration

The Model Manager should work with the pipeline cache.

### Cache Key Inputs

Cache keys should include:

-   model id
-   model path or repo id
-   pipeline family
-   dtype
-   LoRA set
-   scheduler if relevant later

### Goals

-   avoid unnecessary reloads
-   correctly invalidate cache on model change
-   support future multi-pipeline residency

------------------------------------------------------------------------

## Hashing

When practical, compute and store a hash for local models.

Recommended:

-   SHA-256

Purpose:

-   detect duplicates
-   verify integrity
-   detect changed files
-   support future export/import workflows

------------------------------------------------------------------------

## Search and Filtering

The manager should support these filters:

-   category
-   family
-   tags
-   source
-   status
-   text search by display name

------------------------------------------------------------------------

## Sorting

Useful sort modes:

-   name
-   last modified
-   size
-   family
-   category

------------------------------------------------------------------------

## Future Download Support

Later, the Model Manager may support downloading models.

### Future Requirements

-   resumable downloads
-   metadata-first install entries
-   checksum verification
-   safe placement into correct category directories
-   progress reporting to Qt UI

------------------------------------------------------------------------

## LoRA Recipe Support

Future support should include recipe records such as:

``` json
{
  "recipe_name": "Stylized Goblin Rogue",
  "loras": [
    {"id": "shexyo_style_trigger", "weight": 0.9},
    {"id": "armor_detail_pack", "weight": 0.6}
  ],
  "recommended_model_family": "sdxl"
}
```

This is where inspiration from ComfyUI-Lora-Manager becomes useful.

------------------------------------------------------------------------

## Suggested Rust/Qt/Python Ownership

### Rust

-   lightweight registry summaries if needed
-   fast stable identifiers later

### Qt

-   browsing, filtering, selection
-   display of metadata

### Python

-   authoritative scan/load logic in early implementation
-   compatibility validation
-   pipeline preparation

------------------------------------------------------------------------

## Recommended Implementation Stages

### Stage 1

-   filesystem scan
-   populate records
-   basic family detection
-   sidecar metadata load

### Stage 2

-   compatibility warnings
-   preview images
-   tags and search

### Stage 3

-   install/remove/update workflows
-   hashes
-   import/export metadata

### Stage 4

-   recipes
-   download manager
-   remote registries

------------------------------------------------------------------------

## Acceptance Criteria

The Model Manager is considered usable when:

-   checkpoints are discovered automatically
-   LoRAs are discovered automatically
-   compatible selections are obvious
-   sidecar metadata appears in UI
-   invalid or missing files are surfaced clearly
-   generation uses normalized model selections instead of raw ad hoc
    strings

------------------------------------------------------------------------

## Final Design Principle

SpellVision should treat models as managed assets, not loose files.

That is the difference between a simple generator frontend and a real
local AI studio.
