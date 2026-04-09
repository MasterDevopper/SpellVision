# SpellVision UI QA Checklist
## Regression and Release Validation Checklist

Use this checklist on every major UI build, sprint demo, and release candidate.

---

# 1. Shell QA

## Main window
- [ ] app launches into a stable shell
- [ ] no duplicated top headers inside pages
- [ ] custom title bar supports drag, maximize, minimize, restore
- [ ] dock resizing works
- [ ] dock state restores correctly after restart if enabled
- [ ] no unexpected layout jumps when switching pages
- [ ] bottom telemetry bar remains visible and authoritative

## Navigation rail
- [ ] active page highlight is always correct
- [ ] tooltips show correct labels
- [ ] icons remain readable at normal window sizes
- [ ] future/reserved icons do not break spacing
- [ ] rail does not overlap main content on resize

---

# 2. Home Page QA

- [ ] Home loads without oversized decorative header blocks
- [ ] mode switch changes hero content correctly
- [ ] recent workflow cards render cleanly
- [ ] favorites carousel does not clip or overflow
- [ ] dependency banners appear only when relevant
- [ ] workflow click populates target surface correctly
- [ ] no major empty dead zones in layout

---

# 3. Generation Page QA

## Structure
- [ ] left inspector, center preview, and right dock align correctly
- [ ] inspector sections are in correct order
- [ ] collapsible sections expand/collapse smoothly
- [ ] important controls are visible without deep hunting

## Prompt editors
- [ ] prompt editor accepts large text reliably
- [ ] negative prompt editor behaves the same
- [ ] token chips insert into correct prompt field
- [ ] family defaults are visible when applied
- [ ] prompt content is never silently overwritten

## Model stack
- [ ] checkpoint picker updates current model correctly
- [ ] VAE picker behaves consistently
- [ ] incompatible assets are filtered or marked correctly
- [ ] asset state in UI matches real execution request

## LoRA stack
- [ ] add/remove LoRA rows works
- [ ] reorder works and persists if intended
- [ ] enable/disable works
- [ ] weight slider and numeric field stay in sync
- [ ] trigger words show when available
- [ ] recommended negatives show when available
- [ ] clicking trigger words inserts only selected tokens
- [ ] multiple selected trigger words insert correctly
- [ ] stack state shown in UI matches outgoing request

## Actions
- [ ] Generate is visually primary
- [ ] Queue is clearly available and distinct
- [ ] Save Snapshot and Reset are subordinate
- [ ] destructive/reset actions are not visually confused with Generate
- [ ] disabled states are obvious

## Preview
- [ ] preview updates to the current job output
- [ ] preview never gets stuck showing old output after model/job change
- [ ] loading/empty states look intentional
- [ ] hover actions do not flicker
- [ ] preview aspect handling is correct

---

# 4. History QA

- [ ] outputs appear in history automatically
- [ ] grouping modes work correctly
- [ ] preview panel matches selected item
- [ ] metadata summary shows key fields first
- [ ] advanced metadata expands correctly
- [ ] send-to-T2I / send-to-I2I actions populate pages correctly
- [ ] compare mode loads correct items
- [ ] broken image paths are handled gracefully

---

# 5. Queue QA

- [ ] active job strip updates correctly
- [ ] queue table reflects real queue state
- [ ] reorder works
- [ ] multi-select works if implemented
- [ ] progress states update live
- [ ] failed/cancelled/completed states are visually distinct
- [ ] duplicate/retry/remove actions affect the correct row
- [ ] queue state remains trustworthy after first job completes
- [ ] queue does not visually lose pending items

---

# 6. Settings QA

## Structure
- [ ] settings tree expands/collapses correctly
- [ ] search finds the correct settings area
- [ ] selected category stays highlighted
- [ ] content panel updates without stale content

## Appearance
- [ ] theme changes apply consistently
- [ ] density changes apply globally
- [ ] spacing remains coherent after density changes
- [ ] text remains readable in all supported themes

## Generation defaults
- [ ] family prompt defaults save correctly
- [ ] family prompt defaults apply correctly
- [ ] visible applied defaults match saved defaults
- [ ] bypass/disable behavior works if implemented

---

# 7. Buttons and Interaction QA

## Button hierarchy
- [ ] only one primary action dominates each local action group
- [ ] secondary actions are subordinate but readable
- [ ] ghost buttons still feel clickable
- [ ] destructive actions are clearly dangerous

## States
- [ ] hover states are visible
- [ ] pressed states are visible
- [ ] focus states are visible for keyboard users
- [ ] disabled states are obvious and not misleading

## Hit targets
- [ ] buttons are large enough to click comfortably
- [ ] sliders are usable without precision frustration
- [ ] combo boxes are not too small
- [ ] important actions remain usable at compact density

---

# 8. Spacing and Density QA

- [ ] compact density remains readable
- [ ] standard density feels balanced
- [ ] comfortable density does not waste excessive space
- [ ] resizing the window does not create layout chaos
- [ ] controls adapt to smaller widths cleanly
- [ ] the left rail and central workspace stay balanced

---

# 9. Telemetry QA

- [ ] telemetry data is current
- [ ] queue count is accurate
- [ ] progress bar matches real job state
- [ ] runtime status matches worker/runtime truth
- [ ] VRAM/model/LoRA summary is correct
- [ ] telemetry is not duplicated inconsistently in other areas

---

# 10. Visual Quality QA

- [ ] no unnecessary black text boxes behind labels
- [ ] no giant decorative header blocks wasting space
- [ ] surfaces feel cohesive
- [ ] accent color is used intentionally, not excessively
- [ ] cards and panels have consistent padding
- [ ] typography hierarchy feels stable
- [ ] the UI reads as premium and deliberate

---

# 11. Performance QA

- [ ] page switching feels responsive
- [ ] typing in prompt editors does not stutter
- [ ] dragging the window does not stutter badly
- [ ] queue refreshes do not freeze the UI
- [ ] preview updates do not hang the page
- [ ] repeated polling does not visibly degrade responsiveness

---

# 12. Failure-State QA

- [ ] missing model state is understandable
- [ ] missing dependency state is understandable
- [ ] failed job state surfaces helpful information
- [ ] broken preview/image path does not crash page layout
- [ ] empty states are clean, not broken-looking

---

# 13. Release Gate

A build should not be considered UI-ready unless:
- [ ] shell is stable
- [ ] generation page is trustworthy
- [ ] preview reflects reality
- [ ] queue reflects reality
- [ ] settings are navigable
- [ ] button hierarchy is correct
- [ ] no major spacing regressions exist
- [ ] no obvious visual reverts are present
