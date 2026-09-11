# Doc 56 — Release versions

**Status:** process lock, 2026-09-11. **Owner:** feature adds must be **named versions**, the way shipped apps do it.

## Rule

| Kind | Bump | Example |
|------|------|---------|
| Bugfix, no new surface | **PATCH** `1.0.x` | dest-unlink, Batch N actually enqueueing |
| User-visible feature | **MINOR** `1.x.0` | prompt blocks, workflow houses |
| Breaking / incompatible | **MAJOR** `x.0.0` | protocol change the old client cannot speak |

1. A new idea is written under a **heading in `CHANGELOG.md`** (`## [1.1.0]`) **before** code.
2. `CMakeLists.txt` `project(VERSION …)` stays on the **shipping** version until that version ships. Do not set it to 1.1.0 while 1.0.0 is still the hunt.
3. Settings → About already shows `SpellVision %1` from `appVersion()`. That string is CMake’s VERSION. GitHub Releases (`AppVersion.cpp`) compare that number.
4. Do **not** grow 1.0 after it ships by quietly stuffing extras into “nice to haves.” Those extras are 1.1.0 or later.
5. Do **not** use a single “v1.1+” bucket as the product plan. 1.1.0 is one focused minor. The rest wait for 1.2.0, 1.3.0, …

## Current line

| Version | State |
|---------|--------|
| **1.0.0** | Unreleased ship target. Doc 54 §1. T7 not green. |
| **1.1.0** | Planned. Prompt blocks + Character Forge / Pro Grade houses. |
| **1.2.0+** | Unscheduled. Doc 54 §3.2. |

## Related

`CHANGELOG.md` · `CMakeLists.txt` `project(VERSION)` · `qt_ui/shell/AppVersion.*` · Doc 54
