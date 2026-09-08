# Shell Layouts — design

**Status:** built and measured on `wave/s-plus-ui`; the measurements are section 7. Wave 2 of the S+ UI programme.
**Predecessor:** `2026-09-07-foundation-kit-design.md` (wave 1, shipped on `wave/s-plus-ui`).
**Grounded against:** the tree at `112ee8d`, by a structural survey with file:line evidence for every claim in §1.

---

## 1. What the shell is today

`MainWindow` builds itself in four calls (`MainWindow.cpp:1235-1241`): `buildShell`, `buildPages`, `buildPersistentDocks`, `buildBottomTelemetryBar`. The body of the window is exactly one line of structure:

```
centralShell_ [QHBoxLayout] = [ sideRail_ (stretch 0), pageStack_ (stretch 1) ]
```

created at `MainWindow.cpp:1613-1625`. Four other things live outside that layout: the title bar sits in the window's own menu slot via `setMenuWidget` (`:1597-1606`), the telemetry strip is a `QStatusBar` (`:2306-2422`), and the activity drawer is a free child of `centralShell_` positioned imperatively (`:4049-4150`, `:4276-4292`).

Five facts constrain every layout this wave can offer, and each is a specific edit rather than a general risk:

1. **The rail is vertical by construction.** `createSideRail` builds a `QVBoxLayout` for the rail and another for its button column, adds each button with `Qt::AlignHCenter`, and styles them `ToolButtonTextUnderIcon` at a fixed 56x48 (`MainWindow.cpp:1656-1724`, `:585-587`). Nothing branches on orientation.
2. **The drawer's geometry assumes the rail is a left-hand strip.** `positionQueueOverlay` reads `sideRail_->width()` and starts the drawer's X at that offset (`MainWindow.cpp:4283-4291`). Move the rail anywhere else and the drawer is wrong, silently, because it is positioned rather than laid out.
3. **The title bar's toggle icons are baked to an edge.** `CustomTitleBar.cpp:408-412` names its glyphs `sidebar-left` and `sidebar-right`.
4. **The chrome token is a width with no height twin.** `Chrome::ModeRailWidth` is 64 (`ThemeManager.cpp:353`); a horizontal rail needs a height. `Chrome::MenuBarHeight` (40) exists and has no reader, while the status bar hardcodes its own 40 three times (`MainWindow.cpp:2318-2320`).
5. **The cockpit's three most movable parts are not addressable.** `promptCard`, `canvasCard` and the action row are LOCAL variables inside `buildUi` (`ImageGenerationPage.cpp:595`, `:1064`, `:1399`). Their children are all members; the containers are not. No layout that relocates the prompt or the action row can be written until they are members.

Two further facts make the feature cheap rather than expensive. Pages are already lazy and re-homed on demand: `switchToMode` adds a page to the stack the first time it is shown (`MainWindow.cpp:6125-6168`), so a layout that rebuilds the stack's surroundings does not have to rebuild the pages. And the app already has a working precedent for "pick one of N, apply live, persist": the Surface Style combo mutates `ThemeManager` directly and every subscriber repaints off `themeChanged` (`SettingsPage.cpp:504-509`), while the theme preset takes the longer road of a page signal into `MainWindow` glue (`SettingsPage.cpp:480-483` into `MainWindow.cpp:2106-2111`).

**Absent, confirmed by exhaustive search:** no QSettings key for a shell layout, a rail position or a shell-wide density. `showLayoutMenu` (`MainWindow.cpp:4813-4836`) is named "layout" but only toggles panel visibility and persists nothing. The first-run dialog is an environment checklist with two folder pickers (`shell/FirstRunDialog.cpp:104-274`); it has no appearance or layout choice of any kind.

---

## 2. Design

### 2.1 The three layouts

Each is a shell arrangement, not a skin. All three keep every feature reachable; none hides a control the others expose. The names are what the user sees.

| Layout | Rail | Page area | Inspector | Drawer |
|---|---|---|---|---|
| **Instrument** (default) | left, vertical, 64 px, icon over text | fills the rest | right column, adaptive 280-460 | bottom, spanning from the rail's inner edge |
| **Canvas** | left, vertical, collapsed to 48 px, icon only | fills the rest; the canvas takes the height the prompt gives back | right column, **collapsed to a rail of tab icons**; a click on a glyph PUSHES it open beside the canvas and a second click shuts it | bottom, full width |
| **Workspaces** | **top, horizontal**, 44 px, icon beside text, grouped Create / Manage / System | fills the rest | right column, as Instrument | bottom, full width |

**Instrument** is today's shape with wave 1's paint. It exists so the layout switch always has a known-good home, and so a user who likes what they have can opt out of the other two.

**Canvas** answers the cockpit's real complaint: the prompt card and the inspector eat space the image wants. The prompt collapses to a single line that grows on focus, the action row stays in the canvas card's own footer where it already sits (see section 2.6), and the inspector becomes an icon rail that PUSHES open beside the canvas when a glyph is clicked. Nothing is removed; the page's chrome yields to its subject.

**Corrected during task 7, second correction to this document from that task.** This row and this paragraph used to say the inspector "expands over the canvas" and "overlays when opened". It pushes: the column widens in the layout it already occupies and the canvas narrows beside it. Two reasons, and neither is a preference. An overlay has to be positioned imperatively, which is the one mechanism in this shell that has already produced a silent geometry bug -- the activity drawer computing its own X from the rail's width (sections 1, 2.5 and 6 all name it) -- and section 6 already predicts Canvas is the layout most likely to be wrong first. And an overlay tall enough to hold the Model tab would cover the action row, which lives at the canvas card's bottom. The push cannot: the two are in different columns. Left visible rather than quietly rewritten, because the next task paints its picker thumbnails from this table and a thumbnail showing an overlay would advertise a layout that does not exist.

**Workspaces** answers navigation rather than generation. The rail's three groups become a horizontal bar, so the page gets the full width, which is what the wide content surfaces (models, flows, history, dataset) actually want. It is also the layout that survives a narrow window best, because a horizontal rail scrolls sideways where a vertical one runs out of height.

### 2.2 Where layout lives

A new owner, `qt_ui/shell/ShellLayout.{h,cpp}`, namespace `spellvision::shell`:

- `enum class Layout { Instrument = 0, Canvas, Workspaces }`.
- A singleton, mirroring `ThemeManager`'s shape so the Settings page has one pattern to follow rather than two: `layout()`, `setLayout(Layout)`, `setLayoutByIndex(int)`, `layoutNames()`, `load()`, `save()`, and a `layoutChanged(Layout)` signal.
- Persists `ui/shellLayout` under org `DarkDuck`, app `SpellVision`. Default **Instrument** (index 0) on a fresh install, for the same reason wave 1 defaults to Arcane Glass: the shipped default is the shape the app was designed in.

**It is deliberately NOT part of `ThemeManager`.** A theme decides colour and material; a layout decides structure. Merging them would mean a preset could not be worn in two layouts, and `themeChanged` already fans out to every widget that repaints — a layout change needs a rarer, heavier signal that only the shell listens to.

### 2.3 Applying a layout, live

`MainWindow::applyShellLayout(Layout)` owns the whole arrangement and is the only function that positions shell-level furniture. `buildShell` calls it once at construction; the `layoutChanged` connection calls it again on every switch. It performs exactly four steps:

1. Set `shellLayout`'s direction and the order of its two children, re-parenting `sideRail_` and `pageStack_` rather than rebuilding either.
2. Call `sideRail_->setOrientation(...)` (see §2.4) so the rail rebuilds its own internals.
3. Ask the layout for the drawer's content origin and hand it to `positionQueueOverlay` (see §2.5).
4. Broadcast to pages that care, through a new `QEvent` or a direct call on the current page, so the cockpit can move its prompt and action row (see §2.6).

A switch must not destroy a built page, lose a form's contents, or interrupt a running job. That is testable and is a success criterion.

### 2.4 The rail becomes orientation-aware

`createSideRail` is replaced by a small widget class, `qt_ui/shell/SideRail.{h,cpp}`, that owns its buttons and can rebuild them for an orientation:

- `setOrientation(Qt::Orientation)` swaps the outer and column layouts between `QVBoxLayout` and `QHBoxLayout`, switches the buttons between `ToolButtonTextUnderIcon` (56x48) and `ToolButtonTextBesideIcon` (a height of `Chrome::RailBarHeight`, new token, 44), and swaps the fixed width for a fixed height.
- Group headers (Create / Manage / System) render as separators in the vertical rail and as labelled group boundaries in the horizontal one.
- `contentOrigin()` returns the point where page content begins, which is what the drawer needs.

`Chrome::ModeRailWidth` keeps its 64. `Chrome::RailBarHeight` is added at 44. `Chrome::MenuBarHeight` is deleted: it has no reader, and the status bar's three hardcoded 40s become `Chrome::StatusBarHeight`, which is what that number always was.

### 2.5 The drawer stops assuming

`positionQueueOverlay` currently computes `railWidth` itself. It will instead ask: `const QPoint origin = sideRail_->contentOrigin();` and lay the drawer from there, so a top rail yields an origin with a Y offset and a zero X. This is the one change that converts a silent geometry bug into a structural fact.

### 2.6 The cockpit's movable parts

Three locals become members of `ImageGenerationPage`: `promptCard_`, `canvasCard_`, and `actionRow_` (promoted from a bare `QHBoxLayout` to a `QWidget` that owns it, because a layout cannot be re-parented on its own). This is a prerequisite refactor with no visual change, and it is worth doing even if the Canvas layout were cut: three of the cockpit's four structural pieces are currently unreachable after construction except by `findChild` on an object name.

`ImageGenerationPage::applyShellLayout(Layout)` then arranges them: Instrument and Workspaces keep today's order, Canvas collapses the prompt to one line until focused and collapses the inspector to a strip of tab glyphs.

**Corrected during task 7, and the correction is worth keeping rather than quietly fixing.** This paragraph used to say Canvas *moves* `actionRow_` into the canvas card's footer. It is already there and it already was at `112ee8d`, the commit this spec was grounded on: the last line of the canvas card's construction reads `canvasLayout->addLayout(actionRow, 0)` there and `canvasLayout->addWidget(actionRow_, 0)` at HEAD -- the same seat, promoted to a widget by the refactor above. The survey read `:1399` as a loose local and did not notice which layout it was added to. A move that never runs is worse than no move, because the next reader takes the sentence for a description of the code and goes looking for the mechanism. What Canvas actually needs is that the seat be **asserted**, in all three layouts, so a future arrangement cannot lift the row out of the footer unnoticed -- which is what `the_action_row_is_the_canvas_card_footer_in_every_layout` does.

### 2.7 Choosing at first run

`FirstRunDialog` gains a second page, shown **before** the environment checklist, with the three layouts as large picker cards: a name, one sentence, and a rendered thumbnail of the arrangement. It writes `ui/shellLayout` on accept.

The dialog is currently a single flat body (`shell/FirstRunDialog.cpp:104-274`) fired 2 s after the window appears and gated on `setup/firstRunWizard_v1`. It becomes a two-page `QStackedWidget` with the same gate and the same suppression checkbox. A user who dismisses it keeps Instrument, which is the default anyway, so dismissal is never a trap.

The thumbnails are drawn, not photographed: three small painted diagrams from theme tokens, so they follow the active preset and cannot go stale the way a screenshot would.

**As built (task 9).** Two pages in a `QStackedWidget` named `FirstRunPages`, the picker at index 0
and the checklist at index 1, with Back and Next in the same action row that already held Open
Runtime Setup and Continue; the suppression checkbox belongs to the checklist page, because it
suppresses the CHECK and offering it beside the layout cards would read as "do not ask me about
layouts again". The picker is the Settings widget in `CommitMode::Deferred`, and `commitSelection()`
runs on BOTH exit actions -- Open Runtime Setup is a destination, not a cancellation, and a layout
chosen on the way to the runtime page would otherwise be silently dropped. Only closing the dialog
leaves the layout where it was, which is the promise above, and section 7.5 records the planted
defect that proves it.

### 2.8 Changing later, in Settings

A "Layout" card in the Appearance section of `SettingsPage`, directly above Surface Style, using the **Surface Style pattern** rather than the theme-preset one: the combo calls `ShellLayout::instance().setLayoutByIndex(index)` directly, and the shell repaints off `layoutChanged`. The longer road through `MainWindow` glue exists for the preset for historical reasons and should not be copied.

The card carries the same three painted thumbnails as the first-run picker, sharing one widget, so the two surfaces cannot drift apart.

### 2.9 What this wave does not do

Density (comfortable/compact), per-page layout overrides, a user-defined layout, and moving the inspector to the left are all out. They are the obvious next asks, and the design leaves room for each — a `Layout` enum with a persisted key is the seam they would extend — but none is in this wave.

---

## 3. Ratchets

Two new sweep rules, in the wave-1 style: one-way per-file baselines, and each must be proved to FAIL on a planted violation before it is trusted. Wave 1's final review found four of six rules narrower than their names, so a rule ships with a documented statement of what it does and does not catch.

- **`shell-geometry-through-the-layout`** — no file outside `qt_ui/shell/` may read `sideRail_->width()`, `sideRail_->height()`, or `Chrome::ModeRailWidth` / `Chrome::RailBarHeight` to position something. Positioning asks the rail for its `contentOrigin()`. This rule exists because the drawer bug was invisible for as long as the rail never moved.
- **`layout-switch-is-not-a-rebuild`** — `applyShellLayout` and everything it calls may not construct a page, call `deleteLater` on one, or clear `pageStack_`. A layout switch that quietly rebuilds a page loses the user's prompt, and the failure would look like a glitch rather than a bug.

---

## 4. Tests

- **C++, `tests/cpp/test_shell_layout.cpp`:** the enum round-trips through QSettings; `setLayoutByIndex` emits once per real change and not on a no-op; the rail reports a different `contentOrigin()` per layout; the rail's button metrics change with orientation; a switch preserves a page's identity (the same pointer is in the stack afterwards) and its state (text typed into a prompt survives).
- **Matrix:** the responsive matrix gains a layout dimension for the two pages that have cells today, so half-width behaviour is checked in all three layouts rather than only in Instrument.
- **Captures:** three layouts x two presets on T2I, Home and Models, compared pairwise. Two layouts that differ by less than 1 % of pixels are not two layouts — the same gate wave 1 used to catch a Surface Style option that had never actually differed.

---

## 5. Success criteria

1. The three layouts are selectable at first run and in Settings, and the choice survives a restart.
2. Switching layouts while a page holds unsaved input preserves that input, and switching while a job runs does not interrupt it.
3. Each layout differs from the other two by at least 1 % of pixels on T2I, Home and Models.
4. Every rail mode is reachable in every layout at the minimum window size (1180x760), with no control clipped.
5. The two new ratchets are at zero, and each has a recorded planted-violation proof.
6. `ctest` and `pytest` green; the wave-1 ratchets stay at their totals.

---

## 6. Risks

**The drawer is positioned, not laid out.** Every layout bug this wave can ship will surface there first. The mitigation is §2.5 plus the first ratchet, and the drawer gets a capture in every layout.

**Canvas is the layout most likely to be wrong on the first try**, because it changes the cockpit rather than the shell. Its prerequisite refactor (§2.6) is separable and lands first, so if Canvas needs redesign after the owner sees it, the refactor and the other two layouts still ship.

**A layout switch touches a lazily built page that may not exist yet.** `applyShellLayout` must therefore be idempotent per page and must run again when a page is built, not only when the layout changes.

---

## 7. Results — measured 2026-09-08, at the end of task 9

Every number below was TAKEN, on this tree, by a command reproducible from the repository. Nothing
here is inferred from the code reading correct. Wave 1 shipped a spec marked "shipped" whose numbers
lived only in git-ignored directories, and its final review called that the central failure; this
section exists so a reader who never runs anything can still see what was measured, what passed, and
what did not.

**This section was wrong twice before it was right, and the corrections are left visible.** Both
mistakes were about the bottom telemetry strip, both were confident, and both were produced by an
instrument nobody had checked:

1. The first version said the strip's "fixed widths sum past a 1180 px window" and listed six
   squeezed labels.
2. The review corrected the cause and reattributed the shortfall to wave 1's IBM Plex switch
   (`9621592`), naming four rungs.
3. The third reading found **one** clipped label, 2 px, font-independent — and then a fourth reading
   found that even that measurement had been taken in the wrong typeface. §7.3 has the mechanism.

Criterion 4's "identical across the three layouts, therefore not this wave's" was also a
non-sequitur: a regression introduced before the layouts existed is identical across all of them
precisely because it predates them. That inference is gone; what is left is dated evidence.

**CORRECTED AFTER THE FINAL REVIEW (2026-09-08). A THIRD harness gap was found, and this time by
enumerating the family rather than by tripping over it.** `main.cpp` does three things before any
widget exists: it installs `SvStyle`, it registers the bundled IBM Plex faces, and it pushes the
themed palette and overlay sheet onto `qApp` with `applyApplicationChrome()`. The suite did the first
two (found, one at a time, as task 8's R3 and task 9's N2) and **not the third**, so every colour and
every layout below was taken under the PLATFORM application palette. Rendering `FirstRunDialog` from
the harness gave a near-black ground under light-theme content while the cards inside painted light —
two programs in one image. All three now live in `tests/cpp/AppEnvironment.h` and six binaries call
it. **What that moved is recorded in 7.2; the verdicts are unchanged, and the T2I row of criterion 3
is 22–23 % lower than this document used to claim.**

**All measurements below were taken with the bundled IBM Plex Sans registered in the test harness.**
Until fix round 2 they were not: `registerBundledFonts()` is called in `main.cpp` and nowhere else,
so `tests/cpp/test_shell_layout.cpp` measured **Segoe UI** — the same shape as the `SvStyle` defect
task 8 found one layer up, where the harness did not do what `main.cpp` does and every pixel
assertion was quietly about a different program. It was load-bearing: under Segoe the strip's page
chip reads 84 / 95 / 135 px where Plex reads 85 / 96 / 132, and `IMPORTING` reads 59 against 63.
`initTestCase` now registers the faces and sets the same 12 px `IBM Plex Sans` `main.cpp` does, and
`the_suite_measures_the_typeface_the_app_ships` fails if it stops.

**How the pixel numbers were taken, and why not with the capture rig.** `scripts/dev/uia/Capture-SvThemes.ps1`
grabs a fixed 1600x1000 SCREEN region rather than the window, so it photographs whatever is in front
of the app; a run earlier in this wave came back holding a real account sign-in dialog on the owner's
live desktop and that pass was deliberately stopped. The measurements below instead render the shell
OFFSCREEN (`QWidget::grab()` on a `MainWindow` carrying `WA_DontShowOnScreen`, sized 1600x1000) and
compare those pixels with `scripts/dev/uia/compare_captures.py`'s own comparison — per-channel
absolute difference, ITU-R 601-2 luminance of that difference, a > 8/255 threshold, the fraction of
pixels over it — reproduced in process in `tests/cpp/test_shell_layout.cpp`.

**The in-process comparison was cross-checked against the script itself**, not assumed to agree. The
same case, run with `SPELLVISION_LAYOUT_CAPTURE_DIR` set, writes its nine grabs as PNGs;
`compare_captures.py` on those files returns 0.0947 / 0.1047 / 0.1312 (T2I), 0.2596 / 0.5743 / 0.5682
(Home), 0.1832 / 0.4660 / 0.4588 (Models) against the case's own 0.0935 / 0.1029 / 0.1281, 0.2562 /
0.5720 / 0.5660, 0.1822 / 0.4653 / 0.4582 — every pair within 0.0031, the gap being PIL's rounding in
`convert("L")` against integer arithmetic plus a PNG round trip. (Re-run under the corrected
application chrome. The first version of this paragraph agreed just as closely on the OLD numbers,
which is the point worth keeping: an in-process comparison agreeing with the script proves the
arithmetic, never the pixels it was fed.)

### 7.1 The six criteria

| # | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | The three layouts are selectable at first run and in Settings, and the choice survives a restart | First run: `first_run_asks_for_a_layout_before_it_asks_about_the_machine` (picker on stack page 0, checklist on page 1, neither on the other), `accepting_first_run_commits_the_layout_it_showed` (Workspaces card + Next + Continue leaves `ui/shellLayout` = 2 in the real store), `dismissing_first_run_keeps_the_layout_nobody_confirmed`, `the_first_run_dialog_keeps_its_height_across_its_pages` (620x753 on both pages), `the_first_run_cards_are_as_dense_as_the_settings_cards` (added by the final review: the height being STABLE was asserted and the height being USED was not, and page 0 was handing the picker 345 px of surplus that became blank bands inside the cards), and `a_thumbnail_shows_the_same_pick_its_card_does_in_deferred_mode` — the last of which exists because the picker's diagram and its frame disagreed about the selection in Deferred mode, the mode first run uses (§7.5). Settings: `picking_a_card_in_settings_writes_the_real_layout` (3 cards clicked, 3 real writes). Restart: `the_choice_survives_a_round_trip` + `a_stored_value_this_build_does_not_know_reads_as_instrument`. | **PASS** |
| 2 | Switching layouts while a page holds unsaved input preserves that input, and switching while a job runs does not interrupt it | Input: `a_layout_switch_keeps_the_page_and_what_is_typed_in_it` — the prompt's text and the page POINTER survive Instrument → Workspaces. Job: `a_layout_switch_does_not_interrupt_a_page_that_is_mid_job` — the cockpit is put into its busy state through `ImageGenerationPage::setBusy`, the same entry point the worker's telemetry uses, and the locked controls, the disabled Generate and the typed prompt all survive a full trip round Canvas → Workspaces → Instrument. | **PASS on the input half; PARTIAL on the job half** — no REAL job was run. This suite starts no runtime on purpose (`SPELLVISION_NO_RUNTIME_LAUNCH`), so what is proved is that a switch does not reset the page's in-flight state, not that a rendering GPU job survives one. |
| 3 | Each layout differs from the other two by at least 1 % of pixels on T2I, Home and Models | Nine pairs, table 7.2. Smallest 0.0935 (9.4 %), largest 0.5720 (57.2 %); the gate is 0.0100. | **PASS**, by a factor of 9 at the narrowest pair |
| 4 | Every rail mode is reachable in every layout at the minimum window size (1180x760), with no control clipped | `every_rail_mode_is_reachable_at_the_minimum_window_size_in_every_layout` + `the_telemetry_strip_fits_the_text_it_actually_shows`. Reachability: **16 of 16 modes** present, visible and navigating on a click, in all three layouts. Clipping: the ~1200 px page-stack minimum (§7.3, table A — re-measured, and the branch made the binding page 16 px SHORTER than the base rather than taller) **and five hard-clipped telemetry strings** (§7.3, table B) — the page chip cuts `Character Studio` (85 px in 82), `Concept Reference` (96 in 82) and `Runtime / Comfy Manager` (132 in 82, still 132 in 104 at 1600) without eliding, and the workflow-import path writes `IMPORTING` (63 in 34) and `Workflow import running` (125 in 56). One further clip, `Ready` at 32 px in a 30 px box, WAS fixed here. | **Reachability PASS. Clipping MISS**, and a wider miss than the first two versions of this row admitted. Everything left is dated to before this branch and is recorded two-way rather than fixed: widening the strip is surface work and wave 4 owns it. |
| 5 | The two new ratchets are at zero, and each has a recorded planted-violation proof | `shell-geometry-through-the-layout` **0**, `layout-switch-is-not-a-rebuild` **0**, both with an empty baseline in `tests/sweeps/exemptions.py`. Proofs in 7.4, produced by running the rules over the probe text the COMMITTED tests use. | **PASS** |
| 6 | `ctest` and `pytest` green; the wave-1 ratchets stay at their totals | `ctest --test-dir build -C Debug` **24/24 passed**, `test_shell_layout` at **58 cases** (47 at the start of task 9, +10, +1 for the final review's R1 density guard). `pytest tests -q` **2026 passed, 14 skipped, 6 deselected** (+2 committed rule probes). Sweeps **TOTAL 201 known across 29 rules, 23 of them at zero**. The total ROSE, and the reason is recorded rather than smoothed over: `qss-draws-a-control` was reporting zero while `_OWNED_TYPES` omitted `QFrame`, which `SvStyle` draws — adding it surfaced 18 pre-existing sites in 7 files, baselined per file. No file gained a violation; one rule started counting what it should always have counted. | **PASS** |

### 7.2 Criterion 3 — the nine pairwise distances

Fraction of pixels moving by more than 8/255 of luminance, `MainWindow` grabbed offscreen at
1600x1000 under IBM Plex Sans, gate 0.0100.

| Page | Instrument vs Canvas | Instrument vs Workspaces | Canvas vs Workspaces |
|---|---|---|---|
| T2I | 0.0935 | 0.1029 | 0.1281 |
| Home | 0.2562 | 0.5720 | 0.5660 |
| Models | 0.1822 | 0.4653 | 0.4582 |

Every cell is at least nine times the gate. Three facts a later reader should have:

* **These are not the numbers this table carried at the end of task 9, and the difference is the
  harness, not the app.** Under the platform application palette the same case read T2I
  0.1206 / 0.1282 / 0.1666 and Home/Models within 0.0007 of the values above. Supplying
  `applyApplicationChrome()` — what `main.cpp` does at line 310 — drops the T2I row by 22–23 % and
  leaves Home and Models where they were. T2I is the page whose two narrow layouts share the most
  chrome, so it is the row most sensitive to what colour that chrome actually is; Home and Workspaces
  move the rail itself, and a moved rail is a moved rail under any palette. **The gate is unmoved and
  the verdict is unchanged**, but the margin is a factor of 9, not 12, and the earlier figure was
  measured in a program that is not the one that ships.
* **T2I's three numbers depend on what ran before them.** Taken from the case alone they are the
  0.0935 / 0.1029 / 0.1281 above; taken inside the full `test_shell_layout` sequence, where earlier
  Canvas cases have already opened and closed the inspector and folded the prompt, the same case
  reports 0.0852 / 0.1001 / 0.1214. Both pass; the cockpit simply carries more state at the second
  measurement. Home and Models are identical between the two runs.
* **Instrument vs Canvas is the narrowest pair on every page, and that is by design** — Canvas keeps
  the shell it does not change (section 2.1); the rail stands in both, and what moves is its density
  and the cockpit's own chrome. Workspaces moves the rail itself, which is why its pairs are two to
  four times larger.

### 7.3 Criterion 4 — what is clipped at 1180x760, and the instrument that was wrong twice

Reachability is asked of the SCREEN and of a CLICK, never of `modeIds().size()`: a density that HIDES
a tile leaves that vector untouched, and a planted one already walked past a count-based assertion
once in this wave. All 16 rail modes pass in all three layouts.

**The instrument, stated correctly at last.** `QLabel::minimumSizeHint()` is a perfectly good clip
predicate — its closing `.expandedTo(minimumSize())` clamps UPWARD only, so it cannot hide a clip,
and a bare label needing 32 px reports 32/32/32/42/72 at fixed widths 24/30/32/42/72. What is wrong
is not the hint but its **staleness**: `QWidget` caches it behind `valid_hints`, which `setText`,
`setFont` and `setAlignment` clear and **`setFixedWidth` does not**. A scan that resizes the window
and then reads the hint is reading the PREVIOUS rung's answer, and against this ladder the hint lags
by exactly one rung in both directions. That is the whole defect, and it manufactured five false
positives: at 1180 the "shortfalls" were `pick()`'s MID rungs to the pixel — (110+88)/2 = 99,
(96+84)/2 = 90, (78+68)/2 = 73, (128+108)/2 = 118, (72+64)/2 = 68. The font A/B run that seemed to
confirm the Plex attribution was measuring only that `setFont` clears the cache.

An earlier draft of this section blamed `sizeForWidth`'s opening
`if (q->minimumWidth() > 0) w = qMax(w, q->minimumWidth())`. That line is **inert** here: without
word wrap the `w` it produces only reaches `fm.boundingRect`, which ignores it. Recorded because
"the hint is unusable" was itself a wrong conclusion, drawn from the right observation.

The question that needs no cache is `QFontMetrics::horizontalAdvance(text)` against
`contentsRect().width()`, and it is what both guards now ask.

**Table A — the shell geometry. RE-MEASURED 2026-09-08 under the corrected harness, and the
"unchanged at `88a4ae1`" line under it was WRONG:**

| Group | Measured, at 1180x760 | What it is |
|---|---|---|
| `centralShell` | 1180x663 against a minimum of 1042x1203 (Instrument), 1003x1203 (Canvas), 998x1247 (Workspaces) | `MainWindow::centralWidget()`, matched by IDENTITY rather than by the loose key `QWidget(-)`. Its height minimum is the stack's, propagated up one level; only the WIDTH figure differs per layout, because the rail's own width is or is not inside it. |
| `MainPageStack` | 1116x663 against 978x1203 (Instrument), 1132x663 against 955x1203 (Canvas), 1180x619 against 998x1203 (Workspaces) | a `QStackedWidget`'s minimum is the MAXIMUM over every page ever added, and this binary visits all 16 modes. `InspirationPage` wants 955x1203 and `DatasetGenerationPage` 366x970 — both taller than the 760 the shell declares. Real in the app too, once the user has visited either page. |

These are one finding wearing two faces: the same 1203 px height in both rows.

**The numbers this table used to carry (1209, 953x1209, 360x977) were taken in a different program**
— before `applyApplicationChrome()` was supplied to the harness, and the width figures before the
bundled typeface was. They are left named here rather than quietly replaced, because a table that
silently updates its own numbers teaches a reader that measurements are stable when they are not.
The figure also depends on what has run before it inside the binary and on what the page finds on
disk: 1201 and 1203 were both observed on 2026-09-08 from the same commit. **Quote it as "about
1200 px against a declared 760", never as a constant.**

**"Both pages' minimums are unchanged at `88a4ae1`" was UNVERIFIED, and it is now MEASURED AND
FALSE.** The final review declined to assert it either way and asked for the base commit to be
built; it was. Two measurements, and they answer two different questions:

1. **The whole branch.** `88a4ae1` was checked out into a worktree, configured and built, and a
   probe target linking `SpellVisionCore` constructed each page standalone (standalone rather than
   inside a `MainWindow`, and that is forced: at `88a4ae1` `MainWindow` has no
   `SPELLVISION_NO_RUNTIME_LAUNCH` guard — the branch added it — so building one there would have
   probed and LAUNCHED the worker and ComfyUI on the machine). Each tree measured under its own
   `main.cpp` environment, which is the honest comparison: what each version of the app lays out.

   | Page | `88a4ae1` (platform style, Segoe UI) | HEAD (SvStyle, IBM Plex Sans, app chrome) | Δ |
   |---|---|---|---|
   | `InspirationPage` | 977x1189 | 955x1173 | −22 wide, **−16 tall** |
   | `DatasetGenerationPage` | 376x931 | 370x990 | −6 wide, **+59 tall** |

   So the branch moved both. But it did not cause the MISS, and it moved the number that matters the
   RIGHT way: the stack's minimum is the maximum over its pages, `InspirationPage` is what binds, and
   `InspirationPage` is **16 px shorter** than it was at the base. `DatasetGenerationPage` grew 59 px
   and is still 183 px clear of binding anything.

2. **The specific edit that was suspected.** The branch added `min-height: 30px` to
   `InspirationPage`'s button stylesheet (`:285`) where the base had none, which is exactly the shape
   of edit that moves a page minimum. Isolated as a single variable — HEAD's tree with only
   `qt_ui/InspirationPage.cpp` replaced by its `88a4ae1` version, rebuilt, the same criterion-4 case
   run — it contributes **zero**: `955x1203` with the base file and `955x1203` with HEAD's,
   back to back. The `min-height` is inert because `SvStyle::sizeFromContents` already floors the
   button above it, which is what "very likely inert" guessed and is now what was measured.

**Criterion 4's attribution is therefore unchanged in substance and corrected in wording**: the
~1200 px page-stack minimum against a 760 px declared window is real, is a MISS, and predates this
branch — the branch made the binding page slightly smaller. What is no longer claimed is that the
pages' minimums are *identical* to the base's. They are not, in either direction, and the reason is
that this branch replaced the style that lays every control out.

**Table B — the telemetry strings that do not fit, found only once the guard drove every mode.** The
first version of that guard measured ONE text per label, whichever the bar happened to hold, so it
could not see the widest string the strip actually shows. It now navigates all 16 rail modes at every
reachable rung. Only the chips written with `elide=false` are asked, because those are hard-clipped
rather than shortened; `VRAM`, `Model` and `LoRA` pass `elide=true` and are fitted by
`widgets::elideForWidget`.

| chip | string | box at 1180 | text | over |
|---|---|---|---|---|
| `BottomPageLabel` | `Character Studio` | 82 px | 85 px | 3 |
| `BottomPageLabel` | `Concept Reference` | 82 px | 96 px | 14 |
| `BottomPageLabel` | `Runtime / Comfy Manager` | 82 px | 132 px | **50** (still 28 over at 1600) |
| `BottomReadyLabel` | `IMPORTING` | 34 px | 63 px | 29 |
| `BottomStateLabel` | `Workflow import running` | 56 px | 125 px | **69** |

None of these is elided, so the text is cut mid-word rather than ellipsised. **None is fixed here**:
the ladder and the strings both predate this branch, widening a rung is surface work, and wave 4 owns
the strip. They are recorded two-way and keyed by **(chip, string)** rather than by chip — keyed by
chip alone, which is how this shipped for one run, a NEW overflow on a listed chip is invisible, and
the P9 plant proved exactly that: putting Ready's rung back made `Ready` spill by 2 px and the strip
guard stayed silent because `IMPORTING` had already bought that label a pardon.

**One clip WAS fixed**: Ready's `narrow` rung left a 30 px box for a 32 px word at 1180, the window's
declared minimum. It now carries its `wide` rung's 52, giving 34 px. `"Ready"` advances 32 px under
both Plex and Segoe, so this was never the font's doing. The ladder's `tight` rung (< 1100 px) is not
covered: `MainWindow::setMinimumSize` is 1180x760 and no window reaches it.

**The clipping scan used to be stronger than the responsive matrix's, and that gap is now closed.**
`test_responsive_matrix.cpp` carried its own `clippedControls` under the SAME NAME, gated by a
`layoutManaged()` that asks `parent->layout()->indexOf(w)` — and `QLayout::indexOf` sees only a
layout's OWN direct items, so a widget inside a nested `QHBoxLayout` that was `addLayout()`ed into
its parent's column answered "not layout managed" and was skipped in silence, on the surface Doc 28
lists as a release gate. Both now call one function in `tests/cpp/ClipScan.h`, which walks the
parent's whole layout tree and asks a label's own font metrics.

Pointing the gate at the deeper scanner found **exactly one** clip the shallow one could not see, it
was real, and **it is fixed**: at half-screen width the I2V cockpit showed the readiness hint
`Choose an output folder to generate.` in a 66 px box that needs 183 px, hard cut.

`ErrorPillLabel` exists to stop exactly that, and it overrides `minimumSizeHint()` to report its
enforced 60 px floor so that an in-contract squeeze is not called a clip — which is precisely why a
hint-based scan could never flag this and why that override is not a dodge. But `refit()` returned
early on an empty `oneLine_`, and **nine** call sites wrote the pill with a raw `QLabel::setText()`,
so the pill elided only what arrived through `setMessage()`. Every readiness hint — the most-shown
string it carries — bypassed elision.

Routing those callers at `setMessage()` would have been the wrong fix: it prepends the warning glyph,
installs a "Click for the full message." tooltip, sets a pointing-hand cursor and arms the failure
dialog, which is error dress on a sentence that is not an error. `ErrorPillLabel::setHint()` carries
the elision and none of that; `hasMessage()` still answers "is an ERROR showing". `knownClips()` is
back to empty in the same commit — the baselines are one-way, and the guard asked for it in its own
words ("no longer clips — strike it from `knownClips()`").

Guarded by `a_hint_is_elided_like_a_message_and_dressed_like_neither`
(`tests/cpp/test_action_row_pill.cpp`). Planting the early return back makes the matrix fail naming
the cell and the string, and makes that case fail "not elided" — while **both error-path cases stay
green**, which is exactly why this survived to a merge gate.

### 7.4 Criterion 5 — the two ratchets, with their proofs

Both at **0** on the live tree, both with `{}` as their baseline in `tests/sweeps/exemptions.py`.

The output below is produced by running each rule over **the probe text the committed tests use**,
and the producing script asserts that the keys it prints are exactly the lists those tests assert, so
this record cannot drift from what `pytest tests/test_sweeps.py` actually checks. The four tests are
`test_the_shell_geometry_rule_fires_on_the_defect_it_was_written_from`,
`test_the_shell_geometry_rule_lets_the_shell_measure_its_own_rail`,
`test_the_layout_switch_rule_fires_on_the_rebuild_it_forbids` and
`test_the_layout_switch_rule_is_not_confused_by_a_brace_in_a_string`.

`shell-geometry-through-the-layout` — **six** hits on a twelve-line probe:

```
  line  1  key=MainWindow::a:sideRail_->width()
          measures the rail outside the shell: sideRail_->width() -- ask sideRail_->contentOrigin() where page content begins instead
  line  2  key=MainWindow::b:sideRail_->height()
  line  3  key=MainWindow::c:sideRail_->geometry()
  line  4  key=MainWindow::d:sideRail_->size()
  line  5  key=MainWindow::e:chrome(ThemeManager::Chrome::ModeRailWidth)
          reads the rail's chrome token outside the shell: chrome(ThemeManager::Chrome::ModeRailWidth) -- ...
  line  6  key=MainWindow::f:chrome(Chrome::RailBarHeight)
  same text under qt_ui/shell/: 0 violations
```

Extent AND position, because they are one assumption wearing two faces. The counterweight is the half
that decides whether the zero means anything: the probe's remaining six lines — the fix's own comment
naming `sideRail_->width()`, a block comment naming the token, the token's `case` and its enum
declaration, `setVisible`/`isVisible`, and `contentOrigin()` itself — are all silent. A rule that
could not tell those apart would report its own citation forever and could reach zero only by
pardoning the file it watches.

`layout-switch-is-not-a-rebuild` — **five** hits inside one function's braces:

```
  line  3  key=applyShellLayout:removeWidget(
          applyShellLayout takes a widget out of the stack: removeWidget( -- a layout switch re-lays the widgets it already has; rebuilding one costs the user what they typed into it
  line  4  key=applyShellLayout:deleteLater(
  line  5  key=applyShellLayout:delete i
  line  6  key=applyShellLayout:pageStack_->clear(
  line  7  key=applyShellLayout:new ImageGenerationPage
```

Silent on a comment that names `deleteLater`, on a string literal containing `}` (which would
otherwise close the body early and take the rule quiet from there on), and on the same three
spellings inside the neighbouring `ensureGenerationPageBuilt`, where they are exactly what that
function is FOR — which is what makes the rule's one-function scope a property rather than a claim.

### 7.5 The task-9 code, proved by planting

Thirteen defects were planted one at a time, each by rewriting the source in place (never a restore
from a `.bak`: that restores an old mtime, MSBuild skips the file, and the plant survives into the
binary while the source reads clean), rebuilt, run, and reverted with a control.

| Planted | Caught by | Exact failure |
|---|---|---|
| the dialog's picker set to `CommitMode::Immediate` | 3 cases | `first_run_asks_for_a_layout_before_it_asks_about_the_machine` — `Actual (picker->commitMode()): 0`, `Expected (…::Deferred): 1`; `dismissing_first_run_keeps_the_layout_nobody_confirmed` — `Actual: Canvas`, `Expected: Instrument`; `accepting_first_run_commits_the_layout_it_showed` — `'…layout() == Layout::Instrument' returned FALSE. (the pick reached the real setting before the user accepted anything …)` |
| `commitLayoutChoice()` removed from both accept handlers | `accepting_first_run_commits_the_layout_it_showed` | `Actual (ShellLayout::instance().layout()): Instrument`, `Expected (Layout::Workspaces): Workspaces` |
| the checklist inserted at index 0, ahead of the picker | `first_run_asks_for_a_layout_before_it_asks_about_the_machine` | `'first->findChild<LayoutPickerWidget *>()' returned FALSE. (page 0 carries no layout picker)` |
| `applyShellLayout` maps Canvas to Instrument | 7 cases | `every_layout_differs_from_the_other_two_on_every_page` — `'failures.isEmpty()' returned FALSE. (under the 1 % gate: T2I Instrument vs Canvas = 0.0000; Home … = 0.0000; Models … = 0.0000)` |
| the rail hides the `settings` tile in a vertical Full rail | 3 cases | `every_rail_mode_is_reachable_…` — `(Instrument: settings is not on the rail \| Canvas: … \| Workspaces: …)` |
| `applyShellLayout` calls `setBusy(false)` on every cockpit | `a_layout_switch_does_not_interrupt_a_page_that_is_mid_job` | `'secondaryStates() == busySecondary' returned FALSE. (Canvas released the controls a running job had locked)` |
| the thumbnail reads `ShellLayout::instance()` instead of the picker | `a_thumbnail_shows_the_same_pick_its_card_does_in_deferred_mode` | `'deferredThumb >= immediateThumb * 0.5' returned FALSE. (the picked card's DIAGRAM moved 0.0000 in Deferred mode against 0.7043 in Immediate …)`; log: `deferred card 0.7854 thumb 0.0000 other-thumb 0.0000` |
| `setRetainSizeWhenHidden(false)` on the suppression checkbox | `the_first_run_dialog_keeps_its_height_across_its_pages` | `(the dialog jumped from 721 px tall to 753 px when Next was pressed)`; log: `layout page 620x721, checklist page 620x753` |
| Ready's narrow rung put back to 48 | 2 cases | `the_telemetry_strip_fits_the_text_it_actually_shows` — `NEW overflow: BottomReadyLabel at 1180px on home: 2 px past a 30 px box (Ready)` …; `every_rail_mode_is_reachable_…` — `NEW clip QLabel(BottomReadyLabel) text needs 2 px more than its 30 px contents box` in all three layouts |
| `ShellLayout::save()` returns before writing | 5 cases | `dismissing_first_run_keeps_the_layout_nobody_confirmed` fails on the STORE comparison — the line that could not fail before fix round 1 |
| `pageContextForMode` returns the bare mode id | `the_telemetry_strip_fits_the_text_it_actually_shows` | `'overflowing.contains(…)' returned FALSE. (BottomPageLabel no longer overflows -- strike it from kKnownStripOverflows)` — the two-way arm |
| the queue chip's mid rung cut to 30 | 2 cases | `the_telemetry_strip_fits_the_text_it_actually_shows` — `NEW overflow: BottomQueueLabel at 1180px on home: 23 px past a 22 px box (Queue: 0)` …; and the criterion-4 scan, same finding |
| the harness's `QApplication::setFont(ui)` removed | `the_suite_measures_the_typeface_the_app_ships` | `Compared values are not the same` at the family comparison; log: `application font is Segoe UI (bundled: IBM Plex Mono, IBM Plex Sans)`, and every strip number shifts with it |

**Three plants failed to plant, and every one of them looked exactly like a guard that works.** The
first keyed on `entry.id == "prefs"` — `prefs` is the tile's LABEL, its mode id is `settings` — and
the suite came back 53 passed, 0 failed. The second was a plant script whose Python raised before
writing anything; the run that followed was a control wearing a plant's name, and it too came back
green. The third was subtler and is the reason the pair key in §7.3 exists: the plant DID take, the
guard DID have a case for it, and the guard still passed, because the allowance pardoned the whole
label. A plant that does nothing, a defect the code does not have, and an allowance that is too wide
all print the same thing. Every plant from fix round 1 onward therefore asserts the mutant TOOK
before any result is read: the planted line is grepped back off disk (case-sensitively), the build
output is checked for that translation unit being recompiled, and the run aborts if either is missing.

### 7.6 What is NOT proved

* **A real job across a layout switch** (criterion 2, second half). Proving it needs a live worker, a
  live ComfyUI and a GPU render, none of which this suite starts.
* **Anything about how the surfaces LOOK to a person.** No screenshot was taken during the wave and
  none should have been with the capture rig, which photographs the owner's live desktop. The pixel
  numbers prove the three layouts differ; they do not prove any of them is good. TWO defects on the
  first-run dialog are what that cost, both invisible to fifty-odd passing cases: the Deferred-mode
  thumbnail in §7.5, and the cards standing 534 px tall around 187 px of content — 72 % empty, on the
  app's very first screen — which the final review found by rendering the dialog OFFSCREEN with
  `QWidget::grab()` on a `WA_DontShowOnScreen` widget. That method costs nothing and touches no
  desktop; not using it was the gap, not the rig.
* **The ladder's `tight` rung** (< 1100 px). Unreachable at the shell's declared 1180 minimum.
* **The elided chips.** `VRAM`, `Model` and `LoRA` are fitted by `widgets::elideForWidget` and are out
  of the guard's scope. Observed in passing and not pursued: the model chip reads 1 px past its
  contents box on a long checkpoint name, because the helper fits to `width - 6` while the contents
  box is narrower still.
* **That the guard's copies stay in step with production.** Two things are duplicated into the test:
  the `IMPORTING` / `Workflow import running` strings (their real path needs a file dialog and a
  `QProcess`), and the list of chips written with `elide=false`. Rename or reflag either in
  `MainWindow.cpp` and the guard goes quiet about it without saying so.
* **Whether the two clipped groups in table A are the whole story.** The scan skips everything inside
  a scroll area, on purpose — a scroll area's job is to be smaller than its contents — so a control
  clipped INSIDE one is invisible to it, exactly as it is to the responsive matrix. (The matrix asks
  one question the shared scanner does not: whether a resizable area with the horizontal bar off has
  content wider than its viewport, which is clipping rather than scrolling.)
* **That a self-eliding label is measured correctly.** `ClipScan.h` compares a label's `text()` to its
  box, which is right for a plain `QLabel` and wrong for one that elides at paint time while keeping
  the full string in `text()`. Both self-eliding widgets in the tree write the elided string back
  with `setText`, so neither is misread today — `ErrorPillLabel` included, now that its hint path
  elides as well. The counterweight is still not written.
