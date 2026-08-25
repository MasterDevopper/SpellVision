# SpellVision

A Qt6 desktop studio for AI image and video generation. The product promise: ComfyUI / A1111-class power **without node graphs**.

## What it is today

SpellVision is a **Qt6/C++ desktop shell** that drives a **Python worker** over local TCP/JSON. The worker owns graph construction and runs [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

Supported now:

- **T2I / I2I** — SDXL, Flux, Krea2, and the rest of the image matrix (diffusers fast-path + native Comfy templates)
- **T2V / I2V** — LTX (production; default **distilled two-stage**), Wan (t2v + 2.1 i2v; 2.2 dual-noise i2v is a remaining ship gate), Hunyuan, Mochi, hosted FLUX.3
- **Studios** — Character, Comic (stills), Concept Reference
- **Shell** — Home, Flows, History, Inspiration, Models (Stage-1), Runtime, Dataset, Train, Settings

Not started as a native family: **Text-to-3D / Image-to-3D**. `Gen3DPage` is a hidden Comfy-workflow passthrough.

## Architecture in one paragraph

The Qt6/C++ frontend (`qt_ui/`) talks to the worker (`python/worker_service.py`) on `127.0.0.1:8765` with newline-delimited JSON. The worker talks to ComfyUI on `:8188`. **Native** means SpellVision builds a Comfy template/graph (`backend_route="native_comfy_template"`), not a pure-diffusers bypass. Operating constitution: `CLAUDE.md`. Living status: `brain/Planning/Current State Ledger.md`.

## Repo layout

```
python/             worker, adapters, resolvers, native graph builders
qt_ui/              Qt6/C++ frontend (shell, cockpits, studios, theme)
cmake/              CMake for the Qt build
tests/              pytest harness (project `.venv`; unset PYTHONPATH)
scripts/dev/        rebuild_ui.ps1, start_*.ps1, run_ui.ps1
docs/               design docs + FEATURE_MATRIX
brain/              Obsidian vault — start at brain/00 Home.md
attic/              archived sprints + original Rust scaffolding
```

There is no `Trellis/` or `UltraShape/` directory in this repo.

## Daily launch

Open `build/Debug/SpellVision.exe`. The app starts or adopts the worker (`:8765`) and ComfyUI (`:8188`). Configure roots in **Runtime**. First install must not invent a house UNET, dest, or teacher still.

## Development workflow

```powershell
Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue
scripts\dev\rebuild_ui.ps1
```

Then open `build\Debug\SpellVision.exe`. `run_ui.ps1` is optional if the exe bootstrap is healthy.

### Third-party build dependency: libwebp

The build pulls **libwebp** (BSD-3-Clause) via CMake `FetchContent`, pinned to `v1.5.0`, and links the
decoder-only `webpdecoder` target. Qt 6.10.2 ships no WebP plugin. ~94% of Civitai
model previews are WebP. Cached under `build/_deps/` after first configure.

## Tests

Use the **project** venv. Hermes `PYTHONPATH` will break numpy/torch.

```bash
export PATH="$(pwd)/.venv/Scripts:$PATH"
export VIRTUAL_ENV="$(pwd)/.venv"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
```

Smoke renders (`-m smoke`) need live Comfy on `:8188` and real checkpoints; they are deselected by default.

## History

Originally conceived as Rust + CXX-Qt. That scaffolding lives in `attic/rust_original_intent/` and is **not** a build prerequisite.

## License

See `LICENSE`.
