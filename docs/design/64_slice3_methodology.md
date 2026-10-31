# Slice 3 methodology — one preflight sentence

Read slice 1 and slice 2 first. Do not reopen material or 9px.

## What slice 3 is

Doc 64 §10.3. One preflight sentence. No second "Ready to generate". Generate's enabled state matches that sentence. Verb names stay with the sibling plan.

## Where the sentence was written three times

All three updated from `updatePrimaryActionAvailability`:

- Asset Intelligence `aiReadinessText_` — "Ready to generate" or the block reason. This strip lives on the Model tab only.
- Inspector footer `InspectorReadinessText` — "Ready to generate." or "Readiness — %reason", and, while ready, a different sentence ("This will Edit (I2I)…" / "T2V ignores the still…").
- Action-row `readinessHintLabel_` — the block reason again, beside Generate.

The footer is the one that stays. It sits under the tab stack, so it is on screen on Model, Sampling, and Output. The other two are the duplicates.

## What changed

- The footer text is `Ready to generate.` when `readinessBlockReason()` is empty, otherwise that reason, with no "Readiness —" prefix and no Edit/T2V aside.
- `aiReadinessText_` is cleared. The strip keeps its dot and the family sub. Those are not the sentence.
- The action-row pill no longer repeats the reason. An error banner still owns that pill until it is cleared.
- `applyActionReadinessStyle` used to leave Generate clickable when blocked, so a click could show the reason. The footer is the reason now. `setEnabled(enabled)` — and `enabled` is already false when busy, because busy is a block reason. Queue uses the same function.
- The empty well does not also show the block reason. That was slice 2 borrowing the reason before this sentence had a home. The well keeps its verb line.

## Type and color

The footer rule was `@label@`. The preflight sentence is `Type::Body`. One rule change, `#InspectorReadinessText`, to `@body@`. Blocked sets the dynamic property `blocked` and a second rule colors it `@warnDot@`. That token was only replaced in the image-generation sheet. The footer rule lives in the shell sheet, and a missing `.replace()` aborts Debug at startup (`assertNoUnresolvedTokens`). The shell sheet now replaces `@warnDot@` too. Not a new token. Not cyan.

`QString::arg` was not extended. No `%N` was deleted from a multi-arg sheet.

## What was left

- "Readiness first. Details on demand." above the strip. That is inspector chrome, slice 5.
- The verb asides. Putting "Edit" back as the one sentence is the sibling plan. Do not add it as a second label.
- Worker-down is not a block reason. Generate can still look ready while the worker is down. That is the honesty pass, not this slice.
- Contrast was not measured.

## How to know it worked

Grep `Ready to generate` under `qt_ui/` returns nothing. On T2I with a checkpoint and a prompt, the inspector footer is gone, the status bar does not say Text to Image, and Generate is enabled with no sentence beside it. Clear the prompt: the reason sits in the gap left of Generate, and Generate is disabled. The empty well is a small mark and `Write the picture.`

## Files

- `qt_ui/ImageGenerationPage_catalog.cpp` — the sentence, the enable, the cleared duplicates.
- `qt_ui/ImageGenerationPage_ui.cpp` — construction no longer plants the second string.
- `qt_ui/ImageGenerationPage_preview.cpp` — the well is not a second copy of the reason.
- `qt_ui/ThemeManager.cpp` — Body, and Warning when blocked.

## Composition correction

The footer was the wrong home. A ready Generate is the sentence. A blocked one says why in the gap immediately left of the button (`ReadinessHint`), as text, not a second chip. The inspector strip stays hidden. Do not write `Ready to generate.` back onto it.

The page name is the title bar only. `BottomPageLabel` stays in the tree and stays hidden. `pageLabelText` is unchanged so the title bar and the presenter test still share one spelling. The three `BottomPageLabel` pairs in `kKnownStripOverflows` were struck because a hidden chip cannot overflow.

The empty mark is 40px at 0.35 opacity. A 190px mark in Ember's gold `TextLo` was the hero of the plate.

Slice 4. Generate isolate. Do not reopen material, 9px, or this sentence.
