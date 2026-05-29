# Sprint MOCKUP — ImageGenerationPage redesign to target mockup

This sprint reworked the T2I / I2I / T2V / I2V page to match
`spellvision_target_mockup.html`. The work landed as a sequence of
surgical `apply_*.py` patches (the project's established
str_replace-based refactor convention), each verified by a clean
rebuild before the next.

Touched source files (only these three):

| File                          | Role                                              |
| ----------------------------- | ------------------------------------------------- |
| `qt_ui/ImageGenerationPage.h` | new member pointers + forward decls               |
| `qt_ui/ImageGenerationPage.cpp` | structure, layout, collapse logic               |
| `qt_ui/ThemeManager.cpp`      | QSS selectors + the `imageGenerationStyleSheet()` color-slot chain |

Apply scripts live in `scripts/refactors/` per repo convention.

---

## Pass 1 — Asset Intelligence redesign

`scripts/refactors/apply_sprint_mockup_pass1_asset_intelligence.py`

Replaced the dense single-`QLabel` HTML `<table>` (9–20 key:value
rows) with a structured surface:

- Readiness pill (`AiReadinessStrip` / `AiReadinessDot` /
  `AiReadinessText` / `AiReadinessSub`) — colored dot + headline +
  right-aligned sub.
- STACK chip group + (video only) COMPONENTS chip group.
- (video only) timing block — Length / Rate / Duration metric pairs.
- "Show all fields" disclosure that toggles the *preserved* legacy
  HTML dump (renamed `AssetIntelligenceBody` → `AiDetailsBody`,
  hidden by default). No information surface was lost.

`imageGenerationStyleSheet()` gained 18 QSS selectors and 12 new
`.arg()` color slots (positions 34–45), all derived from existing
preset colors (`successColor()` / `warningColor()` / `errorColor()` /
`accentColor()`) so every theme stays tonally correct.

### Pass 1 fixups (1 → 4) — the `.arg`-chain bug

The redesign initially shipped with persistent
`Could not parse stylesheet` warnings and a mis-styled
`AiDetailsToggle`. Four fixups chased it:

- **fixup**  — removed `text-align: left` (unsupported on
  `QToolButton`). Not the cause.
- **fixup2** — renamed dynamic property `is` → `chipState` (CSS L4
  `:is()` keyword collision concern); dropped `letter-spacing`. Not
  the cause.
- **fixup3** — moved chip variants from attribute selectors to
  distinct object names (`AiChipSet` / `AiChipAuto`); cleaned up
  incomplete `border:` shorthands. Defensive, not the cause.
- **fixup4** — **the actual root cause.** The Pass 1 patch *replaced*
  the last `.arg()` in the chain instead of *inserting after* it, so
  the chain fed 44 args into 45 placeholders. `QString::arg()`
  substitutes the lowest-numbered placeholder per call, so everything
  from `%33` shifted by one and `%45` was left as a literal `%45` in
  the QSS. `color: %45` in the `AiDetailsToggle` rule is an invalid
  token → Qt rejected that rule → the parse warning. Restoring the
  one missing `.arg()` line fixed all symptoms at once.

Fixups 1–3 are harmless defensive cleanups and were left in place.

---

## Pass 2 — Quick Controls stacked-label cells

`scripts/refactors/apply_sprint_mockup_pass2_quick_controls_stacked.py`

Added a `makeStackedField` lambda (label *above* field) beside the
existing `makeSettingsRow` (label *left of* field) and swapped the 12
Quick Controls call sites to it. Card title
"Generation Quick Controls" → "Generation Controls". Removed the
dead `QLabel#AiChip` base rule left over from fixup 3; added
`QLabel#StackedFieldLabel`.

---

## Pass 3 — Disclosure promotion + grid pairing

`scripts/refactors/apply_sprint_mockup_pass3_disclosure_promotion.py`

1. **Sampler & Scheduler** extracted from Quick Controls into its own
   collapsed-by-default `SamplerSchedulerCard` (header + toggle
   pattern mirroring the existing OutputQueue/Advanced cards).
2. **LTX Launch Options** wrapped in a disclosure header and moved
   out of the Quick Controls flow into its own card (LTX video only).
3. **Grid pairing retune** — `configureAdaptivePair()` only went
   2-column when `wideLeftRail && !constrainedLeftHeight`, which in
   practice never held (rail ~370px, height usually < 900), so
   Width|Height and Steps|CFG always stacked. Added a width-only
   `pairableLeftRail` (≥ 360px) gate so the size/steps pairs form the
   mockup's 2-col mini-grid regardless of height.

ThemeManager card-chrome selector lists extended with
`SamplerSchedulerCard` and `LtxLaunchOptionsPanel`.

---

## Pass 4 / 4b / 4c — collapse correctness

### Pass 4 — collapsed-card body leak
`scripts/refactors/apply_sprint_mockup_pass4_collapse_fix.py`

Collapsing only clamped the card to 58px via `setMaximumHeight`,
which clips visually but does not stop Qt laying out / painting the
body widgets. Tall bodies (the new Sampler/Scheduler rows) bled out
under the header and overlapped the title. Fix: explicitly
`setVisible(false)` on body widgets when collapsed (walking
`samplerSchedulerLayout_` items; walking LTX/Advanced direct children
except their headers).

Also fixed a **pre-existing bug not introduced by this sprint**: the
Advanced card is created as `createCard("AdvancedCard")` but the
collapse logic looked up `findChild("AdvancedControlsCard")` — which
never matched, so the Advanced card had never actually collapsed.
Corrected the lookup to `"AdvancedCard"`.

(Verified there were no `chipState` remnants to clean — fixup 3 had
already swapped cleanly to object names.)

### Pass 4b — Advanced toggle + Batch/Prefix leak
`scripts/refactors/apply_sprint_mockup_pass4b_toggle_and_batch_fix.py`

- Advanced toggle button was gated on
  `advancedCard->isVisible()` (unreliable mid-layout) instead of the
  sibling cards' plain `setVisible(true)`. Switched to
  `setVisible(true)`.
- `OutputQueueCard` had the same body-leak as Pass 4's cards but was
  out of Pass 4 scope; its Batch / Prefix / Output-Folder rows bled
  out as a cramped sliver. Gated by hiding `OutputQueueBody*`-named
  children when collapsed.

### Pass 4c — Advanced "Open" button clip
`scripts/refactors/apply_sprint_mockup_pass4c_advanced_button_clip_fix.py`

The four other cards hide their body hint when collapsed, so their
collapsed content (header only) fits the shared 58px clamp. Pass 4's
Advanced keep-list kept `AdvancedBodyHint` visible when collapsed, so
Advanced had to fit header + 24px hint + spacing into 58px; the clamp
sliced the vertically-centered toggle to ~¼ height. Fix: drop
`AdvancedBodyHint` from the keep-list so Advanced collapses
header-only, identical to its four siblings.

---

## Net result

All five disclosure cards (Sampler & Scheduler, LTX Launch Options,
Output / Queue, Advanced) collapse/expand uniformly to clean header
strips. Quick Controls uses stacked-label cells with a 2-col
size/steps mini-grid. Asset Intelligence matches the mockup's
readiness-first surface with the full legacy data preserved behind a
disclosure. Splitter sizing, the Video Family card, and the Model
Stack panel were intentionally left untouched.

## Rollback

Each pass wrote `*.pre_sprint_mockup_*.bak` backups next to the
touched files at apply time. These are local-only safety nets and are
intentionally not committed (covered by the repo's backup ignore
pattern). To revert a pass, restore the relevant file from its
backup; the idempotent apply scripts can then be re-run cleanly.
