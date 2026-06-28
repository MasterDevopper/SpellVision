# SPELLVISION_ARCHITECTURE.md

## System Architecture

SpellVision is designed as a **modular AI generation platform**.

### Architecture Overview

Qt UI\
↓\
Python Worker (`worker_service.py`)\
↓\
ComfyUI execution engine\
↓\
AI Models

------------------------------------------------------------------------

## Components

### Qt UI

Responsible for:

-   prompt entry
-   generation controls
-   previews
-   job history
-   progress display

The UI should never run AI models directly.

------------------------------------------------------------------------

### Python Worker

`worker_service.py` (with `worker_service_state.py`) is responsible for:

-   job state and the job queue (the state machine)
-   loading AI pipelines / building ComfyUI graphs
-   executing generation tasks via the ComfyUI execution engine
-   streaming progress
-   saving results
-   managing models

> The original Rust core (`spellvision_core`) was an early job-queue stub. It was
> archived to `attic/rust_original_intent/` and unwired from the build; job state
> and orchestration now live in the Python worker. There is no Rust in the live
> architecture.

------------------------------------------------------------------------

### Model Layer

Models may include:

-   Stable Diffusion
-   video diffusion models
-   3D generation models
-   voice synthesis models

------------------------------------------------------------------------

## Worker Protocol

Requests are sent as JSON messages.

Example:

    {"command":"ping"}

Generation jobs return:

-   progress updates
-   result message
-   error message if failure occurs

------------------------------------------------------------------------

## Data Flow

User Prompt → UI → Worker → Model → Output → UI Preview
