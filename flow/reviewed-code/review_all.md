# Code Review: ship delta (installer + resolver)

## Review Information
| Field | Value |
|-------|-------|
| Date | 2026-10-30 |
| Files Reviewed | installer scripts, SpellVision.wxs, comfy_root.py, RuntimeProfile retarget, worker bind spot-check |
| Scope | uncommitted ship work, not the whole Comfy tree |
| NEXUS API | not called. It POSTs source to a paid host. |
| open-code-review CLI | not run. L1 checks done by reading the new files. No new third-party import. |
| pytest | not re-run. `tests/test_comfy_root.py` was already green this session. |

## Changed Files
| File | Status | Notes |
|------|--------|-------|
| installer/extract_engines.ps1 | new, patched | path jail added during this review |
| installer/remove_unpacked.ps1 | new | deletes the three unpacked trees on uninstall |
| installer/SpellVision.wxs | new, patched | shortcut keypath moved HKCU → HKLM |
| python/comfy_root.py | modified | engines/ComfyUI only after live and rollback are absent |
| qt_ui/shell/RuntimeProfile.cpp | modified | same fallback; retargets pyvenv.cfg only if python-runtime/python.exe exists |
| UI chrome files | modified | not a security surface |

## Findings

### Finding 1: unsigned cabinet plus tar extract
| Field | Value |
|-------|-------|
| File | installer/extract_engines.ps1 |
| Severity | Critical |
| Status | Fixed in the script. The built MSI still has the old script until the next `wix build`. |

**Description**: The extract ran `tar.exe -xf` as SYSTEM into the install directory. A swapped cabinet could carry a `../` entry and write outside Program Files. The MSI is not signed, so a swapped cabinet is the realistic threat.

**Suggested Fix**: Applied. Entries with `..`, a drive letter, or a destination that does not stay under the script directory are refused. The first zip part (25,829 entries) has no such names.

### Finding 2: per-machine shortcut keyed on HKCU
| Field | Value |
|-------|-------|
| File | installer/SpellVision.wxs |
| Severity | Major |
| Status | Fixed in the wxs. Needs a rebuild to be in the MSI. |

**Description**: The start-menu component used an HKCU keypath on a per-machine package. That shortcut belongs to the installing user, not every user, and uninstall of that component follows the wrong hive.

**Suggested Fix**: Applied. Keypath is now HKLM `Software\DarkDuck\SpellVision\Installed`.

### Finding 3: MSI is unsigned
| Field | Value |
|-------|-------|
| File | build/installer/SpellVision.msi |
| Severity | Major |
| Status | Open. Not a code defect. |

**Description**: Windows will warn, and nothing stops a replaced cabinet except the path jail above. A ship needs a signature. That is an owner step (certificate), not a patch.

### Finding 4: two full interpreters
| Field | Value |
|-------|-------|
| File | payload `.venv` and `engines/.venv` |
| Severity | Suggestion |
| Status | Leave it. |

**Description**: Both venvs carry torch. Merging them would break the kornia pin and the isolated Comfy interpreter. The disk cost is the product decision, not waste to delete.

### Finding 5: existing ship gates still hold
| Field | Value |
|-------|-------|
| File | python/worker_service.py, python/workflow_url_import.py |
| Severity | — |
| Status | Confirmed, not re-tested this pass |

**Description**: Worker bind still calls `assert_bind_is_safe` before listen. No `torch.load` in `python/`. Workflow links still require https and re-check redirects against the allowlist. Those are prior gates, not new work.

## What was not reviewed
The UI slice diffs (cockpit, theme, film) were not a security pass. `runtime/` untracked files are not in the MSI. Do not commit them with the installer.

## Commit Readiness
| Status | Needs a signature. The three review failures are fixed in the rebuilt MSI. |
