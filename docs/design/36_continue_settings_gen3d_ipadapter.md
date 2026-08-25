# 36 — Continue wave: Settings + Gen3D workflows + IPAdapter

**Date:** 2026-07-25  
**Verify:** Debug green · pytest 138 passed

## Settings (P0 B1 — were inert)
| Signal | Now |
|--------|-----|
| `usePresetAccentChanged` | → `ThemeManager::setUsePresetAccent` |
| `chooseAccentColorRequested` | → `QColorDialog` → `setAccentOverride` |
| `effectsWeightChanged` | → `setEffectsWeight` |
| `restoreDefaultsRequested` | → `resetToDefaults` + reseed Settings UI |
| `homeDashboardConfigChanged` | → `HomePage::setDashboardConfig` |
| `homeDashboardCustomizeRequested` | → switch Home + apply config |
| Seed on open | preset / accent / effects / dashboard from live ThemeManager + Home |

## Gen3D
| Item | Change |
|------|--------|
| Workflow picker | Combo lists imported Flows profiles; **✦** marks 3D-ish names |
| Generate gate | Requires workflow + Comfy online (no QProcess) |
| Bind | `task_command=comfy_workflow` + `workflow_path` + multi-view slots |
| Refresh | Re-scans library when navigating to Gen3D |

## IPAdapter / reference freedom (worker)
| Item | Change |
|------|--------|
| `run_i2i` strength | Reads `strength` / `denoise_strength`; clamps |
| `pose_flexible` | Strength floor **0.55** so photo can't lock pose |
| `maybe_apply_ipadapter` | Best-effort load from `models/ipadapter` (+ explicit path); never fails job |
| Call kwargs | Attaches `ip_adapter_image` / scale when pipeline supports it |

## Smoke
1. Settings → change theme / accent / effects / Restore defaults (live)  
2. Gen3D → workflow combo populated from Flows; Generate blocked without pick  
3. Character ref image → I2I with higher denoise; check worker log for strength / ip-adapter note  
