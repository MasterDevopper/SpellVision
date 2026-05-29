# SpellVision

A desktop application for AI image and video generation, with planned support for AI 3D model generation.

## What it is today

SpellVision is a **Qt6/C++ desktop shell** that drives a **Python worker service** over a local TCP/JSON protocol. The Python worker orchestrates [ComfyUI](https://github.com/comfyanonymous/ComfyUI) as the generation runtime and handles per-family routing for different model families.

Currently supported workflows:

- **Text-to-image** (T2I) — Stable Diffusion 1.5, SDXL, SD3, Flux
- **Image-to-image** (I2I)
- **Text-to-video** (T2V) — Wan in production, LTX experimental
- **Image-to-video** (I2V) — Wan in production, LTX experimental

Planned, staged under `Trellis/` and `UltraShape/`:

- **Text-to-3D** and **image-to-3D** generation

## Architecture in one paragraph

The Qt6/C++ frontend (`qt_ui/`) connects to the worker (`python/worker_service.py`) on `127.0.0.1:8765` and sends newline-delimited JSON requests. The worker streams back newline-delimited JSON messages (`job_update`, `progress`, `status`, `result`, `error`) and manages a separate ComfyUI process for actual generation. For a deeper map of which file owns which concern, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Repo layout

```
python/             worker service, ComfyUI bootstrap, model registry, per-family adapters
qt_ui/              Qt6/C++ frontend (shell, pages, controllers, presenters, theming)
cmake/              CMake configuration for the Qt build
tests/              pytest harness for the Python worker
scripts/dev/        operational helpers: start_*.ps1, stop_*.ps1, run_ui.ps1, etc.
scripts/refactors/  archived refactor scripts (kept for history)
docs/               design documents
Trellis/            staged: future text-to-3D and image-to-3D
UltraShape/         staged: future 3D-related work
attic/              archived sprint-pass docs, historical refactor scripts, and the
                    original Rust scaffolding (kept in git history; not part of the build)
```

## Development workflow

The dev helpers live in `scripts/dev/`. The intended order:

```powershell
# Build the Qt UI
scripts\dev\rebuild_ui.ps1

# In separate terminals (or via your preferred process manager):
scripts\dev\start_comfy.ps1       # starts ComfyUI
scripts\dev\start_backend.ps1     # starts the Python worker service
scripts\dev\run_ui.ps1            # launches the Qt shell
```

Stop scripts mirror the start scripts.

## Tests

```powershell
pip install -r requirements_dev.txt
pytest tests/
```

The test suite spins up `python/worker_service.py` as a subprocess and exercises the C++ <-> Python TCP/JSON contract directly. See `tests/conftest.py` for the test infrastructure. The current suite covers the ping contract and basic queue semantics; expanding it is straightforward — each test just calls the `worker_client` fixture with a JSON request and asserts on the response stream.

## History

SpellVision was originally conceived as a Rust application with CXX-Qt bindings. The Rust scaffolding remains in `attic/rust_original_intent/` for reference, but the implementation pivoted to Qt6/C++ + Python during development.

## License

See `LICENSE`.
