# 64 — Cockpit showpiece uplift

**Status:** PLAN. Do not start until you have read this file and the files it names.  
**Surface:** the generation cockpit only (`ImageGenerationPage` serving T2I / I2I / T2V / I2V, plus `CockpitInspector`). Do not restyle Home, Models, studios, or Settings in this pass.  
**Mode:** Operate. Dense pro tool. One rank-1 per view.  
**North star:** a team that copies Comfy, Swarm, or Invoke still loses, because the generated plate is the only colored light in the room and the chrome has nothing left to steal.

This is a visual plan. The verb shelf (Lock / Edit / Keyframe) is specified in `.hermes/audit-2026-10-27/grade-2026-10-27.md` and is a sibling, not a substitute. Do both. Do not ship the skin without the verb, and do not ship the verb in 9px type.

---

## 0. What you are building

A look-dev bench. The prompt is the instrument. The plate is the result and the light. Generate is the only chromatic control. Everything else is platinum hairline and stepped matte.

A competitor beats this only by inventing a new relationship between the plate and the chrome. Adding a gradient, a sixth theme, or glow on every card is how they lose.

### Laws this plan obeys (do not re-derive them)

| Law | Source | What it forces here |
|---|---|---|
| Isolation / von Restorff | von Restorff 1933; Laws of UX | One object may differ. That object is Generate, and after a result, the plate. A second violet button, a cyan decoration, or a glowing card kills the memory of the first. |
| Contrast creates hierarchy, not hue | Nielsen Norman Group, visual hierarchy | Advance/recede by tone and saturation against the void. Violet does not win because it is violet. It wins because nothing else is saturated. |
| Three sizes, three contrast steps | NN/g scale + contrast practice | Cockpit type is Caption / Body / Heading only for meaning. Micro (9px) carries no meaning. |
| Group by proximity before boxes | Gestalt proximity; NN/g common region | Double the gap between groups before you add a border. A card border is a last resort. |
| Hick | more visible choices, slower decision | Simple shows intent, prompt, plate, Generate. Advanced reveals in place. Never a new page. |
| Fitts | time to target grows with distance and shrinks with size | Generate stays in the action row, right side, ≥44px tall, and never moves between modes. |
| 60 / 30 / 10 | palette split | ~60% void (`Surface0`), ~30% matte work surfaces, ~10% accent, and the 10% is Generate plus the active verb only. |
| WCAG 2.2 SC 1.4.3 | 4.5:1 body text, 3:1 large text (≥24px or ≥19px bold) | Measure sRGB pairs. Do not round 4.49 up. Do not use hue to pass. |
| WCAG 2.2 SC 1.4.11 | 3:1 non-text for control boundaries | Hairlines that define a control must clear 3:1 against the surface they sit on, or the control has a second encoding (weight, icon). |
| Dark elevation is tone, not glow | Material 3 HCT: tone is luminance; chroma is colorfulness | Lift `Surface0 → Surface1 → Surface2` by tone. Do not lift by adding a radial glow per card. |
| Neutrals take 2–5% of the accent hue | dirty-gray failure next to a saturated accent | Void and platinum are violet-tinted steel, not pure `#808080`. |
| Motion 150–300ms, ease-out in, ease-in out | UI transition band | Over 400ms reads as lag. Under 100ms reads as a glitch. Honor reduced-motion: no glow pulse. |
| One rank-1 | squint test | Blur the cockpit. The plate (or the empty-state eye, before a plate exists) and Generate are the only things that survive. If a LoRA row survives the blur, it is too loud. |

### What is already true (do not redo)

- Tokens exist. `ThemeManager::Color` is the ramp (`qt_ui/ThemeManager.h:75-103`). `Style::{RefinedGlass, MatteInstrument, Hybrid}` is the material (`:61-66`). Hybrid is defined as matte where the user works and glass on the hero only. **The cockpit is not on Hybrid.** That is the uplift.
- ArcaneGlass hex roles are specified in `docs/design/ArcaneGlass_token_spec.md`. Hero `#7C5CFF`, deep `#5B4BD6`, highlight `#C6B6FF`, void `#0A0B12`, cyan `#34D6E6` is Success only. If a branch still uses blue `#6f8cff` or cyan `#6fd3ff` as `AccentSecondary` / `AccentTertiary`, fix the role. Do not add a color.
- Spacing is tokenized: Hairline 4, Tight 8, Snug 12, Card 16, Section 24, Gutter 32 (`ThemeManager.h:111-118`). Literal 6, 7, 10, 14 are off-scale. Snap or use the token. Literal 0 stays 0.
- Type roles exist (`:145-156`). Body is 12px. That is the dense-tool floor already chosen. Do not jump the cockpit to a 16px consumer body. Do ban 9px for any string the user must read to act.
- Cockpit scroll law: no page scroll. Inspector tab bodies may scroll (`CockpitInspector.cpp`, `InspectorTabScroll`). Do not add a page `QScrollArea`.
- Advanced reveals in place. Do not move Denoise, sampler, or seed to another screen to "clean up."
- `QString::arg` is only safe for `%1`–`%9`. Multi-token sheets use `@token@` + `.replace()`. Dropping a `%N` from a multi-arg sheet shifts every later color (Doc 32, the F-grade incident). Never do that.
- Do not apply `shellStyleSheet()` to the page. Shell stays on `MainWindow`.
- Bundled Space Grotesk / Inter are out of scope (Doc 30). Do not block this pass on webfonts. Segoe UI stays. If JetBrains Mono is already registered, use it for seed, dimensions, VRAM, and frame counts only. If it is not registered, do not add a font file in this pass.

---

## 1. The picture (what the eye does)

Left to right, top to bottom, after this pass:

1. Title bar names the mode in one weight. Search is quiet. Simple/Advanced is a switch, not a second brand.
2. Prompt card is a matte plate. The verb control (None / Lock / Edit / Keyframe) is the left slot, 84px, label in `Type::Label` (11/500), not 9px. The prompt is `Type::Body`. Negative is a reveal, not a competing button color.
3. The canvas is the only glass. Empty: the eye mark, one sentence, no metric chips shouting 1080×1920. Landed: the plate inset by `Spacing::Snug`, a 1px `Border` frame, and a violet rim only while the result is the new thing (first 1.6s, then the rim dies to the hairline). The image is the color. The chrome does not compete with it.
4. Action row is matte. Secondary actions are hairline text buttons. Generate is the only filled accent control, right-aligned, height ≥44px, radius from the control token, label `Type::Label` weight 600. It does not move when the mode changes.
5. Inspector is matte, one tone above the void, hairline left edge, no per-card sun. Tabs are text, not pills with fills. The active tab is a 2px accent underline, not a violet wash across the tab.
6. Telemetry is numbers in mono, labels in `TextLo`. Cyan appears only on the ready dot, and only when the backend is actually ready.

Squint test (mandatory before you call a slice done): blur a screenshot by ~8px. If you can name more than two survivors, remove emphasis until two remain.

---

## 2. Material — Hybrid, canvas is the glass

**Why.** `ThemeManager.h:51-60` already states the failure: ten glass panels read as ten suns. RefinedGlass was designed to kill per-card radials. Hybrid was designed so glass means "this is the hero." The cockpit still paints prompt, canvas, inspector cards, and asset intelligence as the same glass. That is why it looks like a themed settings panel instead of an instrument.

**Do.**

1. On `ImageGenerationPage` only, set the working surfaces to `Style::MatteInstrument`: prompt card, action row, inspector shell, asset-intelligence block, LoRA rows.
2. Set the canvas card (`CanvasCard` / preview well) to the hero glass path: one fill from `GlassFill` over `Surface0`, one 1px top highlight from `GlassHighlight`, no vignette, no second radial, no rim streak.
3. Do not change the global preset. Ember may stay the user's persisted preset. The material change is orthogonal to preset (`ThemeManager.h:44-46`). ArcaneGlass remains the demo preset; do not force-migrate the user again.
4. If a card still calls a radial glow in its `paintEvent`, delete that call for cockpit cards. Do not lower its alpha and call it fixed.

**Files to open before editing:** `qt_ui/ThemeManager.h`, `qt_ui/ThemeManager.cpp` (Style branches), `qt_ui/ImageGenerationPage_ui.cpp` (card construction), `qt_ui/generation/CockpitInspector.cpp`.

**Done when:** a screenshot of T2I with no image has exactly one glass region (the canvas well). Prompt and inspector are opaque stepped surfaces.

---

## 3. Color — one light, measured

**Why.** Hue does not make hierarchy (NN/g). Saturation against a tinted void does. Two saturated hues at once (violet Generate + cyan decoration + amber warning + a blue accent secondary) collapse the isolation effect. WCAG contrast is luminance, not taste.

**Roles. Do not invent new ones.**

| Role | Token | Use on the cockpit | Forbidden |
|---|---|---|---|
| Void | `Surface0` | page ground | pure `#000` (halation; no shadow can exist) |
| Work | `Surface1` | prompt, inspector, action row | glass fill |
| Raised | `Surface2` | hovered row, open combo popup | a third elevation on the same card |
| Text | `TextHi` / `TextMid` / `TextLo` | 1 / 2 / 3 rank | a fourth gray |
| Light | `Accent` `#7C5CFF` | Generate fill, active verb, active tab underline, focus ring | LoRA weights, section titles, links, icons that are not the action |
| Deep | `AccentSecondary` | Generate pressed state only | any blue |
| Highlight | `AccentTertiary` | Generate label if contrast on `#7C5CFF` fails 4.5:1; otherwise `TextHi` on the button | body text |
| Structure | `Border` / `BorderStrong` | hairlines | colored borders |
| Online | `Success` | the ready dot, and only when the worker answered | "Ready to generate" text, progress bars, links |
| Attention | `Warning` / `Error` | the preflight sentence when blocked | decorative amber |

**Measure before you ship a pair.** Compute contrast in sRGB. Required pairs:

- `TextHi` on `Surface1` ≥ 7:1 (aim above AA; this is the bench).
- `TextMid` on `Surface1` ≥ 4.5:1. If the token fails, lighten `TextMid`. Do not shrink the text to hide the failure.
- `TextLo` on `Surface0` ≥ 4.5:1 or the string is demoted to a tooltip. `TextLo` that fails is not "muted," it is illegible.
- Generate label on `Accent` ≥ 4.5:1. If white-violet fails, use `Surface0` as the label color. Do not outline the word.
- `Border` against `Surface1` ≥ 3:1 where the border is the only sign a control exists (inputs). Decorative hairlines between sections may be quieter; they are not the control boundary.
- Focus ring uses `Accent` at 2px outside the control, not a glow blob.

**Neutrals.** If a surface reads as dead gray next to Generate, tint it 2–5% toward the accent hue. Do this in the ArcaneGlass (and Ember) token branch, not with a one-off `setStyleSheet` on the page.

**Plate light.** When a result is showing, do not recolor the UI from the image (no Material dynamic-color extraction). The image is already the chroma. A second generated palette would fight the plate. The only reaction is the 1.6s rim, then stillness.

---

## 4. Type — three steps, numbers are data

**Why.** The cockpit's 9px strings ("Drop image or browse", "Edit (I2I)") fail both hierarchy and the contrast exception: they are not large text, and they are the instruction. NN/g: three sizes. This tree already has more than three roles; the cockpit may use only these:

| Rank | Token | Cockpit use |
|---|---|---|
| 1 | `Type::Heading` 16/600 | the mode name in the canvas empty state, nothing else |
| 2 | `Type::Body` 12/400 | prompt text, preflight sentence |
| 3 | `Type::Label` 11/500 | buttons, verb chip, inspector field labels |
| meta | `Type::Caption` 10/500 | eyebrows ("MODEL", "STACK") — letter-spacing +5–8%, max two words, all caps only here |
| data | mono, 12/400 | seed, `W×H`, steps, cfg, fps, frames, VRAM. Same color as `TextMid`. Not a second accent. |

**Ban on this surface:** `font-size:9px` and `Type::Micro` for any string that tells the user what to do. The dropzone hint moves to `Type::Label`. If it does not fit the 84px chip, the chip grows to 96px or the hint moves under the chip inside the prompt card. Do not shrink the type to fit.

**Weights.** 400 and 600 only on this surface. 500 is allowed on Label/Caption because the token says so. Do not add 700 on a label and a larger size and a color at once (that burns every channel on one level).

**Measure.** Prompt field stays within a readable measure. It is already a single card; do not let it become a full-bleed 200-character line with no wrap. Wrap is on. Min height stays one line plus the drop slot.

---

## 5. The plate — the peak

**Why.** Peak-end: people remember the peak and the end. The peak is the moment the image or the first frame appears. Today the empty state is a logo plus a paragraph, and the landed state is a pixmap in a well that looks like the empty well. The chrome does not acknowledge the event.

**Empty (no result yet).**

- One mark (the existing eye). It is `TextLo`, not a glowing illustration.
- One sentence, `Type::Body`, `TextMid`, max two lines. It names the verb, not the subsystem. Examples: "Write the picture." / "Lock needs a plate." / "A keyframe starts the shot." Do not say "Drop a plate only if you mean Edit (I2I), not a style reference." That sentence is a spec leaking into the bench.
- No metric chips (1080×1920, 28 steps, cfg 7.0) in the empty well. Those numbers are data and live in the action row or the inspector, in mono, quiet. They are not the hero of an empty room. This also removes the Simple-mode leak of pixel math into the focal area.

**Landed.**

- Image or video inset `Spacing::Snug` from the well, `Border` 1px, radius from the card token.
- For 1600ms after the result path changes, the well's outer hairline is `Accent` at ~40% alpha. Then it returns to `Border`. One shot. Not a loop. `QPropertyAnimation` on opacity of a pen, 200ms ease-out. If the user has reduced-motion (Windows setting or a future app toggle), skip the rim and cut straight to the hairline.
- Do not zoom, do not confetti, do not dim the inspector. The plate arriving is the event.
- Video: first frame is the plate. Transport controls are a hairline overlay on the bottom of the plate, hidden until hover or focus. They are not a second action row.

**Busy.**

- The well does not swap to a spinner that hides the last plate. Keep the last plate at 40% opacity and draw a 2px accent arc on the well's hairline, 1.2s linear loop, parked when reduced-motion (static 2px accent gap instead). The prompt stays editable or clearly locked — pick locked, and say so in the preflight sentence ("Working."). Do not say "Generation in progress…" in the middle of the plate if the preflight sentence already says it.

---

## 6. Generate — the isolate

**Why.** Fitts: large, stable, near the end of the scan. von Restorff: it must be the only filled accent control in the action row. Today Queue, Snapshot, Reset, Unload, Prep, Use Last, and Generate share one row and Generate wins only by being orange-on-Ember. On ArcaneGlass it must win by being the only saturated fill, on every preset.

**Do.**

- Generate: filled `Accent`, label in the color that clears 4.5:1, height 44px minimum, horizontal padding `Spacing::Card`, radius = control radius (Doc 32: 8px is the landed value; use the token, do not hardcode a new one). Position: last in the action row. Same geometry in T2I, I2I, T2V, I2V.
- Every other action in that row: no fill. `TextMid` label, transparent background, 1px `Border` only on hover. Same height so the row does not jump. They are rank 3.
- Disabled Generate is `AccentDisabled` fill and `TextDisabled` label, never a gray button that looks like the others. Disabled means "the preflight sentence says why."
- Pressed: `AccentSecondary`, 80ms. No drop shadow. A shadow on the only saturated button plus a glow is two emphases.
- Do not add an icon that is a second color. A single glyph in the label color is allowed. Prefer the word.

**Focus.** Keyboard focus on Generate is a 2px `Accent` ring, 2px offset, not a thicker border that changes the button's box.

---

## 7. Inspector — quiet instrument

**Why.** Banner blindness: a right rail that looks like a stack of ads gets ignored (NN/g). The inspector is where power lives. It must look like a spec sheet, not a second app.

**Do.**

- Tab bar: equal text tabs, `Type::Label`, `TextMid`. Active: `TextHi` + 2px `Accent` underline. No filled pill. No icon-only mode in this pass (the collapse-to-glyph path in `CockpitInspector.cpp:34-37` may stay for the narrow budget; when expanded, words, not glyphs).
- Field labels above fields, `Type::Label`, `TextLo` if that pair clears 4.5:1, else `TextMid`. Gap label-to-field = `Spacing::Hairline` (4). Gap field-to-field = `Spacing::Snug` (12). Gap between cards = `Spacing::Section` (24). If a card is only there to draw a box around two fields, delete the card and keep the gap.
- Combo boxes: `setMinimumContentsLength` already required. Elide. A model path must not widen the inspector. That is a Fitts and a half-screen bug, not a taste issue.
- LoRA rows: one hairline between rows, not a glass card per LoRA. Weight is mono. Enabled is a check, not a colored bar.
- Asset Intelligence: one line, the preflight sentence, `Type::Body`. Delete the second "Ready to generate" label (`ImageGenerationPage_ui.cpp:1868`, `ImageGenerationPage_catalog.cpp:1417`). Family badge is `Type::Caption`, `TextLo`, not a colored chip.
- Scroll: the tab body may scroll. The scrollbar is `Border`, 6px, no buttons. Do not show a horizontal bar. If content is wider than the viewport, the layout is wrong (Doc 30). Fix the layout.

---

## 8. Motion — almost none

| Event | Motion | Reduced-motion |
|---|---|---|
| Result arrives | 200ms rim fade-in, hold, 200ms fade to hairline. Total accent time ≤ 1.6s. | cut |
| Mode switch | none. Content swaps. Do not slide the page. | cut |
| Advanced toggle | rows show/hide. 120ms opacity if cheap; otherwise instant. No relayout animation that moves Generate. | instant |
| Busy | 1.2s arc on the well hairline | static gap |
| Hover | color of hairline to `BorderStrong`, 120ms | instant |

Do not add particles, Ember field, or a GL overlay on the cockpit. Doc 58 parks that until VRAM yield exists. This pass is still.

---

## 9. Half-screen — the same picture, smaller

**Why.** A showpiece that clips at half width is a mock. Doc 30 is the gate. The owner rule is same functionality, scroll allowed, clip forbidden.

**Do, after the visual slices, at 960×540 and at the restored full size:**

- Generate still fully visible, still the isolate, still ≥44px.
- Verb chip still readable (`Type::Label`, not truncated to "Ed…").
- Inspector tabs still words, or the existing collapse-to-glyph if `setWidthBudget` says so. Glyphs get tooltips. The name does not vanish from the accessible name.
- No control below its minimum. The responsive matrix in `tests/cpp/test_responsive_matrix.cpp` must stay green. If you add a widget, add it to that matrix or you will ship a clip the test cannot see (the Comic lesson in Doc 30).
- Prompt text does not force the canvas to zero height. Canvas keeps a minimum that still shows the plate mark.

---

## 10. Execution order (one slice, then look)

An agent does these in order. Each slice ends with a screenshot at full width and at half width, a squint check, and a contrast check of the pairs in §3. Do not batch them into one patch.

1. **Material.** Hybrid on cockpit work surfaces, glass only on the canvas well. No copy changes.
2. **Kill 9px instructions.** Dropzone and verb caption move to `Type::Label`. Empty-state sentence rewritten per §5. Metric chips leave the empty well.
3. **One preflight sentence.** Remove the duplicate Ready label. Generate's enabled state matches that sentence. (Wiring the verb names is the sibling plan; this slice only makes the existing sentence the only one.)
4. **Generate isolate.** Secondary actions lose their fills. Generate geometry locked across the four modes.
5. **Inspector quiet.** Tabs, gaps, LoRA rows, scrollbar. No new controls.
6. **Plate rim.** The 1.6s accent hairline on result. Reduced-motion path.
7. **Half-screen + contrast.** Fix whatever the screenshots show. Update the C++ matrix if a new widget can clip.

Stop. Do not continue into fonts, a new preset, motion beyond §8, or other pages.

---

## 11. Acceptance (all must be true)

- [ ] Squint: two survivors, plate and Generate.
- [ ] Count of saturated fills in the cockpit = 1 (Generate), plus the ready dot only when online.
- [ ] No `font-size:9px` on a string that instructs.
- [ ] No second "Ready to generate" string.
- [ ] Measured contrast pairs in §3 pass. Record the ratios in the patch note.
- [ ] `QString::arg` not extended past `%9`. No `%N` deleted from a multi-arg sheet.
- [ ] Page root does not scroll. Inspector tab may.
- [ ] Half width: Generate visible, verb readable, no horizontal scrollbar in the inspector.
- [ ] Reduced-motion: no looping arc, no rim animation.
- [ ] Ember and ArcaneGlass both pass the squint test. The material change is not preset-specific.
- [ ] No new theme, no new token name, no new page.

## 12. What not to do

- Do not restyle the rail, title bar, or Home in this pass. The cockpit is the fight.
- Do not extract a palette from the generated image.
- Do not add glow, particles, or a glass treatment to the inspector to "match the canvas."
- Do not introduce a sixth preset. Ember stays valid. ArcaneGlass stays the demo.
- Do not bundle fonts.
- Do not move controls to a new screen to make the cockpit look empty.
- Do not call this S because the screenshot is pretty. S includes the verb, the keyframe refusal, and the single sentence. This document is the visual half. The other half is the grade file. Both, or it is a skin.
