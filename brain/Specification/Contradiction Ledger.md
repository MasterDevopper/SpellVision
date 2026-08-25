---
title: Contradiction Ledger
type: spec
status: living
updated: 2026-08-24
---

# Contradiction Ledger

Repository-resolvable mismatches. Prefer code/live config.

| ID | Topic | Stale claim | Canonical | Action |
|----|-------|-------------|-----------|--------|
| C1 | T2V/I2V maturity | FEATURE_MATRIX / old roadmap “Planned” | Cockpits + native families work | Rebuild matrix before planning |
| C2 | LTX status | README “LTX experimental”; CLAUDE §6 single-stage as default | Native production; default = `two_stage_distilled` | Update README + CLAUDE §6 |
| C3 | Chain Studio | Missing from FEATURE_MATRIX *or* FEATURE_MATRIX lists it while CLAUDE says omitted | Engine proven; rail hidden unless `SPELLVISION_SHOW_ALL_MODES=1` | Treat both docs as stale on this cell |
| C4 | Rust prereq | DEV_GUIDE / SPELLVISION_ARCHITECTURE | Rust archived, unwired | Purge prereq lists |
| C5 | Comfy root | `runtime_paths.default_comfy_root` / old D: path | `C:\\sv_comfynext\\ComfyUI` live | Treat default_comfy_root as drift |
| C6 | Asset root | `.env` `${SPELLVISION_ROOT}/models`, `external_assets/` | `D:/AI_ASSETS/models` | Reconcile env helpers |
| C7 | Character/Comic ship scope | Roadmap (2026-07) said v2.0 | **2026-08-17 lock: in v1, A+B** | Treat old roadmap lines as stale; follow Owner Decision Log |
| C8 | Hunyuan i2v | Doc 26 “render-verified kijai” | Contract readiness_notes cite CLIPVision 768-vs-1024 block / gated Comfy update | **Re-verify live** post cutover; update loser |
| C9 | Models page name | Some docs `ModelsPage` | `ModelManagerPage` | Use real type name |
| C10 | Doc 13 identity | Some cites Doc 13 = release readiness | Doc 13 = Simple/Advanced; readiness = Doc 28 | Fix citations |
| C11 | Worker size | ARCHITECTURE / old brain “~6700 god file” | Facade ~2104; work in named modules ([[Worker Facade Split]]) | Treat old line counts as stale |
| C12 | Theme default | Some notes “runtime default may be Neon Forge” | ArcaneGlass default via one-time migration | Treat Neon-default claim as stale |
| C13 | Inspire | CLAUDE §6 + FEATURE_MATRIX = `ModePage` stub | `InspirationPage` moodboard on rail | Rebuild those two sentences |
| C14 | Manager / Dataset | CLAUDE §6 + FEATURE_MATRIX = built-unreachable | Rail modes `runtime` + `dataset` | Same |
| C15 | Test count | Doc 37 “155 passed”; README “ping + queue” | 2026-08-24: 423 passed / 2 skipped / 5 smoke deselected (`PYTHONPATH=""`) | Cite latest run, not Doc 37 |
| C16 | Full Roadmap 0.1→2.0 | Video MVP at v0.5, 3D at v0.7 | T2V/I2V + Gen3D page already exist | Aspirational sequence, not current truth |

## Related

[[Authority and Precedence]] · [[Current State Ledger]] · [[Open Questions Register]]
