# Shell Layouts — design

**Status:** draft, awaiting owner review. Wave 2 of the S+ UI programme.
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
| **Canvas** | left, vertical, collapsed to 48 px, icon only | fills the rest; the canvas takes the height the prompt gives back | right column, **collapsed to a rail of tab icons** that expands over the canvas on demand | bottom, full width |
| **Workspaces** | **top, horizontal**, 44 px, icon beside text, grouped Create / Manage / System | fills the rest | right column, as Instrument | bottom, full width |

**Instrument** is today's shape with wave 1's paint. It exists so the layout switch always has a known-good home, and so a user who likes what they have can opt out of the other two.

**Canvas** answers the cockpit's real complaint: the prompt card and the action row eat vertical space the image wants. The prompt collapses to a single line that grows on focus, the action row moves into the canvas card's own footer, and the inspector becomes an icon rail that overlays when opened. Nothing is removed; the page's chrome yields to its subject.

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
