SpellVision

SpellVision is a next-generation local multimodal AI creation studio designed to rival tools such as ComfyUI, A1111, and cloud generators while remaining fully local, high-performance, and extensible.

The goal of SpellVision is to become a flagship desktop creative platform capable of generating and manipulating:

Images

Videos

3D assets

Animations

Game-ready assets

All locally.

SpellVision is built as a true desktop application using:

Rust — high performance engine

Qt 6 — professional desktop UI

Python sidecars — model ecosystem access

GPU acceleration — optimized for high-end systems (5090-class GPUs)

Vision

SpellVision aims to become the ultimate local generative media studio, combining:

the flexibility of node-based tools

the polish of professional desktop software

the power of local AI models

the scalability of a modular architecture

Unlike existing tools, SpellVision focuses on:

professional UX

multi-modal generation

workflow orchestration

asset management

long-form generation pipelines

Core Capabilities

SpellVision will support:

Image Generation

Text-to-Image (T2I)

Image-to-Image (I2I)

Inpainting

Outpainting

Upscaling

Video Generation

Text-to-Video (T2V)

Image-to-Video (I2V)

Clip extension

Long-form video generation

3D Generation

Image-to-3D (TRELLIS-style models)

Mesh refinement

Asset export pipelines

Creative Workflows

visual node graphs

reusable pipelines

automation

batch generation

Architecture

SpellVision uses a hybrid architecture combining Rust performance with the AI ecosystem.

SpellVision
│
├─ Rust Engine
│   ├─ Job Queue
│   ├─ Workflow Engine
│   ├─ Model Registry
│   ├─ Artifact Manager
│   └─ Project System
│
├─ Qt 6 Desktop UI
│   ├─ Main Window
│   ├─ Dockable Panels
│   ├─ Parameter Inspector
│   ├─ Asset Browser
│   ├─ Queue Monitor
│   └─ Workflow Editor
│
├─ Python AI Workers
│   ├─ Diffusion pipelines
│   ├─ Video generation models
│   ├─ Image-to-3D pipelines
│   └─ Post-processing tools
│
└─ Local Data Layer
    ├─ SQLite metadata database
    ├─ Artifact storage
    ├─ Model registry
    └─ Cache system
Technology Stack
Core

Rust

Qt 6

CXX-Qt bridge

AI Ecosystem

Python

PyTorch

Diffusers

video diffusion models

TRELLIS-style 3D generation

Data

SQLite

JSON workflow definitions

Project Goals

SpellVision will become:

a multimodal AI generation suite

a workflow automation platform

a creative asset production studio

a local alternative to cloud AI services

Sprint Roadmap

Each sprint delivers at least one working generator while expanding the platform.

Sprint 0 — Foundation

Goal: Build the desktop application core.

Deliverables

Rust workspace

Qt application shell

QMainWindow layout

Dockable panels

Menu bar and toolbar

Status bar

Logging panel

SQLite database initialization

Job schema

Artifact schema

Model registry schema

Result

A functional desktop application framework ready for AI features.

Sprint 1 — Text-to-Image (T2I)

First working generator.

Features

prompt input

negative prompt

model selector

width / height

steps

CFG

seed

generate button

job queue

progress monitoring

image preview

artifact storage

history gallery

Platform Upgrades

job manager v1

artifact store v1

model registry scanner

Result

SpellVision becomes a fully functional image generator.

Sprint 2 — Image-to-Image (I2I)

Adds iterative image workflows.

Features

image upload

drag-and-drop source images

strength control

reuse prompt parameters

artifact lineage tracking

send image → I2I workflow

Platform Upgrades

asset input system

preprocessing pipeline

artifact lineage graph

Result

SpellVision supports iterative creative workflows.

Sprint 3 — Inpainting / Outpainting

Transforms the app into a creative editing tool.

Features

mask brush

mask erase

canvas editor

inpainting pipeline

artifact versioning

comparison view

Platform Upgrades

image editing canvas

layered image state

artifact version tracking

Result

SpellVision becomes a practical AI image editor.

Sprint 4 — Text-to-Video (T2V)

First video generator.

Features

video prompt

duration control

fps control

resolution selection

clip preview

video artifact storage

playback panel

Platform Upgrades

video artifact type

video preview component

long-running job monitoring

Result

SpellVision becomes a multimodal generator.

Sprint 5 — Image-to-Video (I2V)

Animate still images.

Features

source image animation

motion presets

prompt conditioning

video generation

artifact lineage (image → video)

Platform Upgrades

cross-media asset linking

multimodal input system

Result

Images can now become animated sequences.

Sprint 6 — Long-Video Generation

Enable extended video creation.

Features

clip segmentation

timeline view

generate next segment

segment stitching

rerender individual segments

export assembled video

Platform Upgrades

timeline data model

clip orchestration system

Result

SpellVision supports long-form local video generation.

Sprint 7 — Image-to-3D

Introduce 3D generation.

Features

image input

3D generation pipeline

mesh artifact storage

3D viewer

GLB / OBJ export

preview renders

Platform Upgrades

mesh artifact type

3D preview panel

mesh metadata schema

Result

SpellVision generates 3D assets from images.

Sprint 8 — 3D Refinement

Improve asset quality.

Features

mesh refinement pipeline

version comparison

decimation options

export profiles

Platform Upgrades

mesh lineage system

3D post-processing pipeline

Result

SpellVision produces game-ready assets.

Sprint 9 — Workflow Mode

Advanced node-based pipelines.

Features

visual graph editor

node palette

workflow templates

workflow execution

workflow import/export

Platform Upgrades

workflow engine

graph serialization

Result

SpellVision becomes a workflow automation platform.

Sprint 10 — Multimodal Workflows

Combine image, video, and 3D pipelines.

Features

T2V workflows

I2V workflows

I2-3D workflows

reusable multimodal pipelines

Result

SpellVision becomes a fully modular generation platform.

Sprint 11 — Polish

Focus on usability and performance.

Improvements

benchmarking tools

generation statistics

keyboard shortcuts

improved gallery

model validation

UI polish

Result

SpellVision becomes a professional creative application.

Development Setup
Requirements

Rust

Qt 6

Python 3.10+

CUDA capable GPU

Clone the repository
git clone https://github.com/MasterDevopper/SpellVision
cd SpellVision
Build (planned)
cargo build
Long-Term Goals

Future versions may include:

collaborative workflows

plugin system

distributed generation

model marketplace

automated asset pipelines

game engine integrations

Contributing

Contributions are welcome.

If you want to help:

open issues

propose features

submit pull requests

improve documentation

License

License to be determined.

Author

MasterDevopper

Creator of SpellVision.
