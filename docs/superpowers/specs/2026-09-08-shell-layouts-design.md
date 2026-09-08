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

Every number below was TAKEN, on this tree, by a command whose output is reproducible from the
repository. Nothing here is inferred from the code reading correct. Wave 1 shipped a spec marked
"shipped" whose numbers lived only in git-ignored directories, and its final review called that the
central failure; this section exists so a reader who never runs anything can still see what was
measured, what passed, and what did not.

**How the pixel numbers were taken, and why not with the capture rig.** `scripts/dev/uia/Capture-SvThemes.ps1`
grabs a fixed 1600x1000 SCREEN region rather than the window, so it photographs whatever is in front
of the app; a run earlier in this wave came back holding a real account sign-in dialog on the owner's
live desktop and that pass was deliberately stopped. The measurements below instead render the shell
OFFSCREEN (`QWidget::grab()` on a `MainWindow` carrying `WA_DontShowOnScreen`, sized 1600x1000) and
compare those pixels with `scripts/dev/uia/compare_captures.py`'s own comparison — per-channel
absolute difference, ITU-R 601-2 luminance of that difference, a > 8/255 threshold, the fraction of
pixels over it — reproduced in process in `tests/cpp/test_shell_layout.cpp`. That is better evidence
than a photograph as well as a safer one: no taskbar clock, so a number means what it says.

**The in-process comparison was cross-checked against the script itself**, not assumed to agree. The
same case, run with `SPELLVISION_LAYOUT_CAPTURE_DIR` set, writes its nine grabs as PNGs;
`compare_captures.py` on those files returns 0.1214 / 0.1294 / 0.1678 (T2I), 0.2595 / 0.5724 / 0.5663
(Home), 0.1784 / 0.4593 / 0.4521 (Models) against the case's own 0.1200 / 0.1279 / 0.1663, 0.2561 /
0.5702 / 0.5640, 0.1774 / 0.4587 / 0.4516 — every pair within 0.0035, the gap being PIL's rounding in
`convert("L")` against integer arithmetic plus a PNG round trip.

### 7.1 The six criteria

| # | Criterion | Measured | Verdict |
|---|---|---|---|
| 1 | The three layouts are selectable at first run and in Settings, and the choice survives a restart | First run: `first_run_asks_for_a_layout_before_it_asks_about_the_machine` (picker on stack page 0, checklist on page 1, neither on the other), `accepting_first_run_commits_the_layout_it_showed` (a click on the Workspaces card + Next + Continue leaves `ui/shellLayout` = 2 in the real store), `dismissing_first_run_keeps_the_layout_nobody_confirmed`. Settings: `picking_a_card_in_settings_writes_the_real_layout` (3 cards clicked, 3 real writes). Restart: `the_choice_survives_a_round_trip` + `a_stored_value_this_build_does_not_know_reads_as_instrument`. | **PASS** |
| 2 | Switching layouts while a page holds unsaved input preserves that input, and switching while a job runs does not interrupt it | Input: `a_layout_switch_keeps_the_page_and_what_is_typed_in_it` — the prompt's text and the page POINTER survive Instrument → Workspaces. Job: `a_layout_switch_does_not_interrupt_a_page_that_is_mid_job` — the cockpit is put into its busy state through `ImageGenerationPage::setBusy`, the same entry point the worker's telemetry uses, and the locked controls, the disabled Generate and the typed prompt all survive a full trip round Canvas → Workspaces → Instrument. | **PASS on the input half; PARTIAL on the job half** — no REAL job was run. This suite starts no runtime on purpose (`SPELLVISION_NO_RUNTIME_LAUNCH`), so what is proved is that a switch does not reset the page's in-flight state, not that a rendering GPU job survives one. |
| 3 | Each layout differs from the other two by at least 1 % of pixels on T2I, Home and Models | Nine pairs, table 7.2. Smallest 0.1200 (12.0 %), largest 0.5702 (57.0 %); the gate is 0.0100. | **PASS**, by a factor of 12 at the narrowest pair |
| 4 | Every rail mode is reachable in every layout at the minimum window size (1180x760), with no control clipped | `every_rail_mode_is_reachable_at_the_minimum_window_size_in_every_layout`. Reachability: **16 of 16 modes** present, visible and navigating on a click, in all three layouts. Clipping: **5–6 controls** squeezed below their own `minimumSizeHint`, in all three layouts identically — table 7.3. | **Reachability PASS. Clipping MISS.** The clipped set is byte-identical across the three layouts, which is what says this wave did not cause it: it is the shell's pre-existing debt at the size the shell itself declares. |
| 5 | The two new ratchets are at zero, and each has a recorded planted-violation proof | `shell-geometry-through-the-layout` **0**, `layout-switch-is-not-a-rebuild` **0**, both with an empty baseline in `tests/sweeps/exemptions.py`. Proofs re-run 2026-09-08 and quoted in 7.4. | **PASS** |
| 6 | `ctest` and `pytest` green; the wave-1 ratchets stay at their totals | `ctest --test-dir build -C Debug` **24/24 passed**, `test_shell_layout` at **53 cases** (47 at the start of this task, +6). `pytest tests -q` **2024 passed, 14 skipped, 6 deselected**. Sweeps **TOTAL 183 known across 29 rules, 24 of them at zero** — identical to the pre-wave baseline in every number, with no rule risen and none fallen. | **PASS** |

### 7.2 Criterion 3 — the nine pairwise distances

Fraction of pixels moving by more than 8/255 of luminance, `MainWindow` grabbed offscreen at
1600x1000, gate 0.0100.

| Page | Instrument vs Canvas | Instrument vs Workspaces | Canvas vs Workspaces |
|---|---|---|---|
| T2I | 0.1200 | 0.1279 | 0.1663 |
| Home | 0.2561 | 0.5702 | 0.5640 |
| Models | 0.1774 | 0.4587 | 0.4516 |

Every cell is at least twelve times the gate. Two facts a later reader should have:

* **T2I's three numbers depend on what ran before them.** Taken from the case alone they are the
  0.1200 / 0.1279 / 0.1663 above; taken inside the full `test_shell_layout` sequence, where earlier
  Canvas cases have already opened and closed the inspector and folded the prompt, the same case
  reports 0.2364 / 0.1448 / 0.2785. Both pass; the cockpit simply carries more state at the second
  measurement. Home and Models move by less than 0.0002 between the two runs.
* **Instrument vs Canvas is the narrowest pair on every page, and that is by design** — Canvas keeps
  the shell it does not change (section 2.1); the rail stands in both, and what moves is its density
  and the cockpit's own chrome. Workspaces moves the rail itself, which is why its pairs are two to
  four times larger.

### 7.3 Criterion 4 — what is clipped at 1180x760

Reachability is asked of the SCREEN and of a CLICK, never of `modeIds().size()`: a density that HIDES
a tile leaves that vector untouched, and a planted one already walked past a count-based assertion
once in this wave. All 16 rail modes pass in all three layouts.

The clipping scan is the responsive matrix's predicate with its recorded blind spot closed:
`test_responsive_matrix.cpp`'s `layoutManaged()` asks `parent->layout()->indexOf(w)`, and
`QLayout::indexOf` sees only a layout's OWN direct items, so a widget inside a nested `QHBoxLayout`
that was `addLayout()`ed into its parent's column answers "not layout managed" and is skipped
silently. `test_shell_layout.cpp`'s `layoutManagedDeep()` walks the parent's whole layout tree
instead. It is therefore a strictly harder question than the matrix asks, and it found things the
matrix could not.

| Group | What | Measured, at 1180x760 | Why it is not this wave's |
|---|---|---|---|
| `centralShell` | `MainWindow::centralWidget()` | 1180x663 against a minimum of ~1000x1209 | the page stack's minimum, propagated up one level |
| `MainPageStack` | the page stack | 1116x663 against 963x1209 (Instrument) | a `QStackedWidget`'s minimum is the MAXIMUM over every page ever added, and this binary visits all 16 modes. `InspirationPage` wants 953x1209 and `DatasetGenerationPage` wants 360x977 — both taller than the 760 the shell declares. Real in the app too, once the user has visited either page. |
| `BottomTelemetryContainer` | 3–4 of the telemetry labels | e.g. `BottomReadyLabel` 48x24 against a 50x24 minimum, `BottomVramLabel` 108x24 against 118x24 | the strip's fixed widths sum past a 1180 px window. Invisible to the responsive matrix, whose "Title bar + telemetry" surface constructs an `ImageGenerationPage` rather than the real bar. |

The ratchet on this is **grouped rather than keyed to the five object names, and that is a measurement
result rather than a convenience**: which telemetry label loses the argument depends on the TEXT it
currently holds, and the VRAM readout's text changes when the NVML poll lands — a first run of the
case named three labels, the next named four. A ratchet keyed to an exact five would have been a coin
flip. It is two-way in the usual sense: an offender outside these three groups fails the case in
whichever layout it appears, and a group that stops offending must be deleted rather than left
standing as an excuse.

**None of the three is a layout defect and none is fixed here.** They are recorded so criterion 4 is a
stated MISS with three named causes rather than a pass with an asterisk, and so the next reader knows
that "1180x760" is a number the shell declares and does not currently honour.

### 7.4 Criterion 5 — the two ratchets, with their proofs

Both at **0** on the live tree, both with `{}` as their baseline in `tests/sweeps/exemptions.py`. The
proofs below were re-run on 2026-09-08 against the rules as they ship; they are carried by
`tests/test_sweeps.py` (`test_the_shell_geometry_rule_fires_on_the_defect_it_was_written_from`,
`test_the_shell_geometry_rule_lets_the_shell_measure_its_own_rail`,
`test_the_layout_switch_rule_fires_on_the_rebuild_it_forbids`,
`test_the_layout_switch_rule_is_not_confused_by_a_brace_in_a_string`), so they re-run on every suite.

`shell-geometry-through-the-layout`, planted into a synthetic `qt_ui/MainWindow.cpp`:

```
  line 1  key=MainWindow::positionQueueOverlay:sideRail_->width()
    measures the rail outside the shell: sideRail_->width() -- ask sideRail_->contentOrigin() where page content begins instead
  line 2  key=MainWindow::b:sideRail_->height()
    measures the rail outside the shell: sideRail_->height() -- ...
  line 3  key=MainWindow::c:sideRail_->geometry()
    measures the rail outside the shell: sideRail_->geometry() -- ...
  line 4  key=MainWindow::e:chrome(ThemeManager::Chrome::ModeRailWidth)
    reads the rail's chrome token outside the shell: chrome(ThemeManager::Chrome::ModeRailWidth) -- ...
  -- same text under qt_ui/shell/ (the owning package): no violations
```

The counterweight matters as much as the four hits: line 5 of the probe is the fix's own comment
naming `sideRail_->width()` and line 6 is `sideRail_->contentOrigin()`, and neither is reported — a
rule that could not tell those apart would report its own citation forever and could only reach zero
by pardoning the file it watches.

`layout-switch-is-not-a-rebuild`, planted inside a synthetic `applyShellLayout` body:

```
  line 3  key=applyShellLayout:removeWidget(
    applyShellLayout takes a widget out of the stack: removeWidget( -- a layout switch re-lays the widgets it already has; rebuilding one costs the user what they typed into it
  line 4  key=applyShellLayout:deleteLater(
    applyShellLayout destroys a widget: deleteLater( -- ...
  line 5  key=applyShellLayout:new ImageGenerationPage
    applyShellLayout constructs a page: new ImageGenerationPage -- ...
```

The same three spellings inside the neighbouring `ensureGenerationPageBuilt`, where they are exactly
what that function is FOR, are silent — which is what makes the rule's one-function scope a property
rather than a claim.

### 7.5 The task-9 code, proved by planting

Six defects were planted one at a time, each by rewriting the source in place (never a restore from a
`.bak`: that restores an old mtime, MSBuild skips the file, and the plant survives into the binary
while the source reads clean), rebuilt, run, and reverted with a control.

| Planted | Caught by | Exact failure |
|---|---|---|
| the dialog's picker set to `CommitMode::Immediate` | 3 cases | `first_run_asks_for_a_layout_before_it_asks_about_the_machine` — `Actual (picker->commitMode()): 0`, `Expected (…::Deferred): 1`; `dismissing_first_run_keeps_the_layout_nobody_confirmed` — `Actual (ShellLayout::instance().layout()): Canvas`, `Expected (Layout::Instrument): Instrument`; `accepting_first_run_commits_the_layout_it_showed` — `'ShellLayout::instance().layout() == Layout::Instrument' returned FALSE. (the pick reached the real setting before the user accepted anything …)` |
| `commitLayoutChoice()` removed from both accept handlers | `accepting_first_run_commits_the_layout_it_showed` | `Actual (ShellLayout::instance().layout()): Instrument`, `Expected (Layout::Workspaces): Workspaces` |
| the checklist inserted at index 0, ahead of the picker | `first_run_asks_for_a_layout_before_it_asks_about_the_machine` | `'first->findChild<LayoutPickerWidget *>()' returned FALSE. (page 0 carries no layout picker)` |
| `applyShellLayout` maps Canvas to Instrument | 7 cases, including the pixel one | `every_layout_differs_from_the_other_two_on_every_page` — `'failures.isEmpty()' returned FALSE. (under the 1 % gate: T2I Instrument vs Canvas = 0.0000; Home Instrument vs Canvas = 0.0000; Models Instrument vs Canvas = 0.0000)` |
| the rail hides the `settings` tile in a vertical Full rail | 3 cases | `every_rail_mode_is_reachable_at_the_minimum_window_size_in_every_layout` — `'failures.isEmpty()' returned FALSE. (Instrument: settings is not on the rail \| Canvas: … \| Workspaces: …)` |
| `applyShellLayout` calls `setBusy(false)` on every cockpit | `a_layout_switch_does_not_interrupt_a_page_that_is_mid_job` | `'secondaryStates() == busySecondary' returned FALSE. (Canvas released the controls a running job had locked)` |

One of these was a plant that did not fire on its first attempt, and it is worth recording: the rail
plant keyed on `entry.id == "prefs"` and the suite stayed at 53 passed. `prefs` is the tile's LABEL;
its mode id is `settings`. The plant was wrong, not the guard — but a plant that silently does
nothing looks exactly like a guard that works, which is the failure mode this whole procedure exists
to avoid.

### 7.6 What is NOT proved

* **A real job across a layout switch** (criterion 2, second half). See the table. Proving it needs a
  live worker, a live ComfyUI and a GPU render, none of which this suite starts.
* **Anything about how the two surfaces LOOK to a person.** No screenshot was taken and none should
  have been — the capture rig photographs the owner's live desktop. The pixel numbers prove the three
  layouts differ; they do not prove any of them is good.
* **The first-run dialog at 1180 px.** Criterion 4 covers the shell, not the modal. The dialog's
  picker page inherits `LayoutPickerWidget`'s own geometry, whose narrow-width behaviour was likewise
  reasoned rather than photographed in task 8.
* **Whether the three clipped groups in 7.3 are the whole story at 1180x760.** The scan skips
  everything inside a scroll area, on purpose — a scroll area's job is to be smaller than its
  contents — so a control clipped INSIDE one is invisible to it, exactly as it is to the responsive
  matrix.
