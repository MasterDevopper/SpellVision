---
title: Acceptance Evidence Ledger
type: planning
status: living
updated: 2026-08-17
---

# Acceptance Evidence Ledger

Track acceptance as a **vector**, not a single “done” label.

| Item | Impl exists | Regression guard | Product/render proof | Durable artifact | Decision accepted | Downstream integration | Repo status closed |
|------|-------------|------------------|----------------------|------------------|-------------------|------------------------|--------------------|
| Image family matrix | Y | partial (pytest + smokes) | Y (Doc 26) | docs + commits | Y | cockpit + models | Y for matrix |
| LTX native t2v/i2v | Y | partial | Y (CLAUDE §6) | template JSON + commits | Y | Video cockpit | Y native prod |
| Wan t2v dual-noise | Y | builder tests | Y | commits | Y | Video cockpit | Y |
| Wan i2v 2.1 + VAE guard | Y | dry-run noted | Y | commit 33f631d | Y (Option A) | Video cockpit | A closed; B open |
| Wan 2.2 dual-noise i2v | Y graph | dual-noise tests | N render | Doc 27 + 2026-08-17 lock | **ship gate** | `_wan_video_build` i2v | graph only |
| Hunyuan t2v | Y | — | Y | commits | Y | cockpit | Y |
| Hunyuan i2v | ? | — | conflicting | Doc 26 vs contract | **reconcile** | — | N |
| Mochi t2v | Y | — | Y | commit 0fabe6a | Y | cockpit | Y |
| Krea2 raw default | Y | `test_krea2_family` | N owner render | family_operating_points | Y raw default | cockpit path | Y contract |
| License UI badges | Y badge+warn | family license tests | N owner eyes | Doc 26 §4 + 2026-08-17 lock | badge + soft warn | Model cards + generate | partial |
| Chain Studio spine | Y | — | Y historical | design docs | Y engine | nav gate | partial ship |
| Mode-aware history | N/partial | N | N | roadmap #12 | Y needed | History | N |
| Runtime profile + app-owned worker | partial | N | N | Doc 28 §5 | **this increment** | exe launch | N |
| Hybrid installer bundle | N | N | N | Doc 25/28 | engines-in-box | ship | N |
| Guided dep resolution | partial map | N | N | Doc 19 | Y needed | first-run | N |
| Character mesh / garments / hair | N | N | N | 2026-08-17 A+B lock | **v1 gate** | Character Studio | N |
| Phase D 3D (non-character) | N | N | N | 11b/11c | still later unless Character B consumes it | — | parked |
| God-file facade | Y | `test_godfile_split` | N (structure) | plan 2026-08-17 | Y extract-now | facade re-exports | Y first-cut |
| SamplingController | Y | `test_sampling_controller_split` | N | worker allow-lists | Y | cockpit Sampling tab | Y |
| Shutdown unload | Y | `test_runtime_unload_on_exit` | N owner VRAM | MainWindow + worker_runtime | Y fail-closed | aboutToQuit | partial |
| Job SM ping path | Y | strict xfail | N (bug) | ARCHITECTURE.md | known bug | queue UX | N |

## How to update

When a family or subsystem lands: tick dimensions with **paths/commits/test names**, never vibes.

## Related

[[Current State Ledger]] · [[Contradiction Ledger]] · [[Job Lifecycle Contract]] · [[Planned Additions]]
