# Slice 2 methodology — kill 9px instructions

Read `64_slice1_methodology.md` first. Do not reopen material.

## What slice 2 is

Doc 64 §4 and §10.2. On the generation cockpit, no `font-size:9px` and no `Type::Micro` on a string that tells the user what to do. The empty well is one sentence, `Type::Body`, `TextMid`. Metric chips leave that well. No new token. No other page.

## Where the 9px actually was

Three sites, all in the cockpit, and a fourth that would have put them back:

- `ImageGenerationPage_ui.cpp` dropzone hint, `font-size:9px`, three lines inside an 84px chip.
- Same file, verb caption `Edit (I2I)`, 9px, 14px tall, hardcoded `#f4f0ff`.
- Same file, `NEG` eyebrow, 9px mono.
- `ImageGenerationPage_catalog.cpp` `applyThemeStyling()` rewrote the hint and the verb back to 9px on every theme change. A buildUi-only fix does not survive a preset switch.

Chain, History, and the studios also have 9px. They are not this surface. Leave them.

## Why the chip grew

`Type::Label` is 11/500. Three lines of that do not fit an 84px chip, and the spec forbids shrinking the type to fit. The named fallback is 96px. The click catcher, the thumb, the hint, the clear button, and the verb strip all moved with it. The thumb crop in `ImageGenerationPage_preview.cpp` was still 82. A hint at 96 with a thumb at 82 leaves a ring. Both are 94 inside the 96 frame.

The verb strip is 18px, not 14. A 14px max-height clips 11px type. The wash is `Surface0` at 0.72, the ink is `TextHi`. Not `#f4f0ff`. `@token@` replace, not a new `%N`.

`NEG` is an eyebrow, one word, caps. That is `Type::Caption` (10/500), not Label and not Micro. It is not a member, so `applyThemeStyling` finds it by `NegativeEyebrow`. Without that, a theme switch leaves the boot color.

## The empty well

§5, which slice 2 cites, is one mark and one sentence. Not a title plus a lecture.

- The radial violet glow behind the sigil is gone. The sigil strokes are `TextLo`. The pupil is the same ink. Violet and cyan in that SVG were a second light source.
- `QString::arg` on a string with five `%1` replaces one of them. Use `replace("%1", ink)` so every stroke gets the color.
- Sentences, one line, named by the verb: T2I `Write the picture.` T2V `Write the shot.` I2I `Lock needs a plate.` I2V `A keyframe starts the shot.` A readiness reason, when there is one, is that sentence. Do not prefix `Almost ready.`
- `canvasEmptySub_` stays in the tree and stays hidden. Deleting the member would touch the header for no behavior. `updateCanvasEmptyState` no longer splits on `\n\n`.
- A wrapping `QLabel` with `AlignHCenter` and no minimum width sizes itself to the longest word, then clips the next line. `Write the picture.` rendered as `Write the`. The sentence label has a 280px minimum width and a 32px minimum height.
- The four metric chips are not created. Width, steps, cfg, and seed already live on the Sampling and Output tabs. Putting a second copy on the action row is a later slice. The responsive-matrix comment about `CanvasMetricChip` at 24×20 is a race note, not a requirement that the chips exist.

## What was left

- Verb strings are still `Edit (I2I)` / `Keyframe` / `Unused (T2V)` / `Source`. Slice 2 changes their type, not their names. The sibling plan owns the verb shelf.
- The long `showText` lectures on the non-empty preview path (busy, missing file after a result) were not the empty well. Left alone.
- Contrast was not measured. Slice 7.

## How to know it worked

Grep `font-size:9px` under `ImageGenerationPage*.cpp` returns nothing. T2I with no image: the dropzone hint is readable at arm's length, the well says `Write the picture.`, there is no `1080 × 1920` chip in the well, and the mark is not glowing violet. A theme switch does not restore 9px, because `applyThemeStyling` is the second writer and it was updated too.

## Files

- `qt_ui/ImageGenerationPage_ui.cpp` — chip 96, Label hint, Label verb, Caption NEG, TextLo sigil, one sentence, chips removed.
- `qt_ui/ImageGenerationPage_catalog.cpp` — the theme-switch writer.
- `qt_ui/ImageGenerationPage_preview.cpp` — sentences, no title/sub split, thumb 94.

## Next slice

Slice 3. One preflight sentence. Do not reopen material or 9px.
