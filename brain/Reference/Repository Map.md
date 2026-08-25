---
title: Repository Map
type: reference
updated: 2026-07-25
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
