# SPELLVISION_ARCHITECTURE.md

## System Architecture

SpellVision is designed as a **modular AI generation platform**.

### Architecture Overview

Qt UI\
↓\
Rust Core\
↓\
Python Worker\
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

### Rust Core

Handles:

-   job state
-   job queue
-   fast internal logic
-   Qt bridge

Rust ensures high performance for orchestration tasks.

------------------------------------------------------------------------

### Python Worker

Responsible for:

-   loading AI pipelines
-   executing generation tasks
-   streaming progress
-   saving results
-   managing models

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
