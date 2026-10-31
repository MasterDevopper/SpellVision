# Qwen 3.8 27B — cockpit showpiece build prompt

Paste the block below into a **fresh** Qwen session. One slice per session. When it finishes, start `/new` and paste the same block with the slice number changed. Do not paste chat history.

---

You are implementing one slice of the SpellVision generation-cockpit visual uplift. You are not designing. The design is already written. If the spec and your taste disagree, the spec wins.

## Repo

- Root: `C:/Users/xXste/Code_Projects/SpellVision`
- Branch: `feat/ui-s-grade`. Do not commit unless asked.
- Shell is git-bash. Use POSIX (`ls`, `rg`). Do not use PowerShell builtins (`Get-ChildItem`, `Select-String`, `$env:`).
- Pass `C:/...` paths to native tools (git, python, cmake). Do not use `/c/Users/...` with git or python.
- Qt 6.10.2, CMake generator `Visual Studio 17 2022`, Debug exe `build/Debug/SpellVision.exe`.

## Source of truth — read before any edit

Read these in full, in this order, before you change a file:

1. `docs/design/64_cockpit_showpiece_uplift.md` — the plan. Sections 0–12. This is the law.
2. `docs/design/64_slice1_methodology.md` — how slice 1 was done. Do not reopen material.
3. `docs/design/64_slice2_methodology.md` — how slice 2 was done. Do not restore 9px, and do not fix type only in `buildUi`.
4. `docs/design/64_slice3_methodology.md` — how slice 3 was done. One Ready sentence, on the inspector footer. Do not put it back on Asset Intelligence or the action row.
5. `qt_ui/ThemeManager.h` — `Color`, `Style`, `Spacing`, `Chrome`, `Type`. Use these tokens. Do not invent token names.
6. The files the slice names below. Read the live file immediately before you patch it. Line numbers in the spec drift.

Also read, do not edit unless the slice requires a token fix:

- `docs/design/ArcaneGlass_token_spec.md`
- `docs/design/32_showcase_shell_redesign.md` (the `%N` deletion incident)

Sibling, not this task: `.hermes/audit-2026-10-27/grade-2026-10-27.md` (verbs, installer, heal). Do not implement that file in this session.

## This session's slice

SLICE: 1

Allowed slices are 1 through 7, matching section 10 of the spec. Do only the number above. Stop when its done-when is true. Do not start the next slice.

| Slice | Work | Done when |
|---|---|---|
| 1 | Material. Cockpit work surfaces use `Style::MatteInstrument`. Canvas well is the only glass (`GlassFill` + one `GlassHighlight` hairline). No copy changes. | A T2I with no image has exactly one glass region: the canvas well. Prompt, action row, inspector, asset intelligence, LoRA rows are opaque. |
| 2 | Kill 9px instructions. Dropzone hint and the "Edit (I2I)" caption move to `Type::Label` (11/500). Empty-state sentence rewritten per spec §5. Metric chips leave the empty well. | No `font-size:9px` on a string that tells the user what to do. Empty well has one mark and one sentence. No `1080×1920` / steps / cfg chips in the empty well. |
| 3 | One preflight sentence. Remove the duplicate "Ready to generate" (`ImageGenerationPage_ui.cpp` asset-intelligence label and `ImageGenerationPage_catalog.cpp` setter). Generate enabled state matches that sentence. | One readiness string in the cockpit. Generate is disabled when that sentence says the backend or the keyframe is missing, if that fact is already known in this class. Do not invent a new worker probe. |
| 4 | Generate isolate. Generate is the only filled `Accent` control in the action row, last, height ≥44px, same geometry in T2I/I2I/T2V/I2V. Other action-row buttons: no fill, `TextMid`, hairline only on hover. | Squint: Generate is the only saturated fill in the action row. |
| 5 | Inspector quiet. Text tabs, active = `TextHi` + 2px `Accent` underline, no filled pill. Label-to-field `Spacing::Hairline`, field-to-field `Spacing::Snug`, between cards `Spacing::Section`. LoRA rows are hairlines, not glass cards. Scrollbar 6px, no horizontal bar. | No new controls. No horizontal scrollbar. A model path does not widen the inspector. |
| 6 | Plate rim. When the result path changes, well hairline goes `Accent` at ~40% for ≤1.6s, then returns to `Border`. 200ms ease-out. `QPropertyAnimation`. Reduced-motion: cut, no loop. | No particle, no zoom, no inspector dim. Busy state keeps the last plate; does not replace it with a centered spinner paragraph. |
| 7 | Half-screen + contrast. At 960px width and at restored full size: Generate visible and ≥44px, verb/dropzone text not truncated below `Type::Label`, no inspector horizontal scroll. Measure sRGB contrast for the pairs in spec §3. Record ratios in the patch note. If you added a widget that can clip, extend `tests/cpp/test_responsive_matrix.cpp`. | Spec §11 checklist items that this slice can prove are checked. Do not claim the ones you did not measure. |

## Hard rules

- Surface is `ImageGenerationPage` (T2I, I2I, T2V, I2V) and `CockpitInspector` only. Do not restyle Home, Models, studios, Settings, the rail, or the title bar.
- Do not add a theme, a token name, a page, a font file, particles, a GL overlay, or a palette extracted from the generated image.
- Do not move a control to another screen. Advanced reveals in place.
- Do not add a page-root `QScrollArea`. Inspector tab bodies may scroll.
- `QString::arg` is safe only for `%1`–`%9`. Multi-token stylesheets use `@token@` and `.replace()`. Never delete a `%N` from a multi-arg sheet. That bug turned the rail into a lavender void (Doc 32).
- Do not apply `shellStyleSheet()` to the page.
- Literal spacing 0 stays 0. Off-scale literals (6, 7, 10, 14) snap to the nearest `ThemeManager::Spacing` token.
- Cyan / `Color::Success` is the ready dot only, and only when the backend is actually ready. No decorative cyan or blue.
- Generate is the only saturated fill. Do not add a second violet button.
- Ember must keep working. Do not force-migrate `appearance/themePreset`. Material (`Style`) is orthogonal to preset.
- Do not start ComfyUI (`:8188`) or the worker (`:8765`). Do not run generation. GPU is not yours.
- Do not commit, push, or edit `.env`.
- If a spec line and the live file disagree, trust the live file for anchors and the spec for intent. Say so in the report.

## How to edit

1. Read every file you will patch, in full or in chunks, before the first write.
2. One slice, one patch series. Match existing style. No drive-by refactor.
3. Before rebuild: `Stop-Process -Name SpellVision -Force -ErrorAction SilentlyContinue` is PowerShell. From git-bash use `taskkill //F //IM SpellVision.exe` if the exe is running, or skip the kill if it is not.
4. Build only if the slice changed C++ and you can: `cmake --build build --config Debug --target SpellVision`. If the build fails, fix the error you introduced. Do not claim success from a compile you did not run.
5. Do not launch the app if a build was not done. A stale exe misgrades the slice.

## Report, then stop

When the slice is done, reply with only:

- Slice number
- Files changed
- What a screenshot should show
- Contrast ratios, if this was slice 7; otherwise "not measured"
- Anything in the spec you could not do, and the file:line reason
- The exact next slice number, or "stop" if this was 7

Do not start the next slice. Do not summarize the whole plan. Do not propose extra polish.
