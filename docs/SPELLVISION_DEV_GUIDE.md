# SPELLVISION_DEV_GUIDE.md

## Development Guide

This document explains how to build and run SpellVision.

------------------------------------------------------------------------

## Prerequisites

Install:

-   Qt 6
-   Python 3.12+
-   Rust
-   CMake
-   Visual Studio Build Tools

Optional:

-   Ollama
-   Blender

------------------------------------------------------------------------

## Setup Python Environment

Create virtual environment:

    python -m venv .venv

Activate:

    .\.venv\Scripts\Activate.ps1

------------------------------------------------------------------------

## Install Dependencies

Example:

    pip install torch torchvision
    pip install diffusers transformers accelerate
    pip install safetensors pillow

Optional:

    pip install xformers

------------------------------------------------------------------------

## Configure Build

    cmake -S . -B build -DQt6_DIR="C:/Qt/6.x/msvc/lib/cmake/Qt6"

------------------------------------------------------------------------

## Build

    cmake --build build --config Debug

------------------------------------------------------------------------

## Run

    build/Debug/SpellVision.exe

------------------------------------------------------------------------

## Worker Protocol

Workers communicate via JSON.

Example request:

    {"command":"ping"}

Example result:

    {"ok":true}

------------------------------------------------------------------------

## Coding Rules

-   UI code stays in Qt
-   Model code stays in Python
-   Rust handles job state
-   All generations must store metadata
