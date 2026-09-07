# Foundation kit: one style, one component vocabulary

**Status:** approved design, 2026-09-07. Wave 1 of the S+ programme.
**Owner decisions banked:** three shell layouts (Instrument, Canvas, Workspaces) in wave 2; all five
presets and three materials stay and get fixed; Arcane Glass returns as the shipped default; the kit
is built as a `QProxyStyle`.

## 1. Why

The 2026-09-07 audit graded the visual layer C+ and found the cause in form, not hue: 315 object
names, 27 button styles, the primary button defined seven times at radii 8 and 10 and weights 600, 700
and 800, 133 literal corner radii across 13 values, one system font with five stylesheets requesting a
font that is not shipped, and a Surface Style setting whose three materials produce cockpit captures
that cannot be told apart. Every later wave (three shells, image-first cards, notification layer)
would multiply that debt by three. The kit is the prerequisite for all of them.

Evidence, as of `88a4ae1`:

- Primary button definitions: `ThemeManager.cpp:1505`, `DatasetGenerationPage.cpp:236`,
  `Gen3DPage.cpp:309`, `InspirationPage.cpp:273`, `studios/CharacterStudioPage.cpp:2353`,
  `studios/ComicStudioPage.cpp:1490`, `studios/ConceptReferencePage.cpp:949`.
- Radius systems: `ThemeManager.cpp:406-433` (10/6 by material), `DashboardSurfaceTokens.h:39-43`
  (26/20/16/13), thirteen `setCornerRadius` literals (24, 20, 18, 16, 14).
- Material reach: `@rcard@`/`@rctl@` substituted only in `shellStyleSheet` (`ThemeManager.cpp:1397`);
  the cockpit sheet carries 18 literals (`ThemeManager.cpp:1431-1616`); the cockpit builds no
  `DashboardGlassPanel`, so Hybrid equals Matte there.
- Fonts: `main.cpp:291-296` sets Segoe UI 12 px; no `QFontDatabase::addApplicationFont` anywhere;
  `'JetBrains Mono'` requested at `ImageGenerationPage.cpp:581, 726`,
  `ImageGenerationPage_catalog.cpp:822, 876`; `'Cascadia Mono'` at `ImageGenerationPage.cpp:1184`.
- Application style: none set; the platform default is the base. Palette and the popup overlay sheet
  are pushed at `ThemeManager.cpp:1096-1097` (`applyApplicationChrome`).

## 2. What is built

### 2.1 `qt_ui/style/SvStyle.{h,cpp}` — the one place controls are drawn

`spellvision::style::SvStyle : QProxyStyle`, constructed over `QStyleFactory::create("Fusion")` and
installed once in `main.cpp` with `QApplication::setStyle` before the window is built. It reads
`ThemeManager` tokens at draw time; it caches nothing, so a preset or material switch is a repaint.

Roles are widget properties the style reads through `widget->property(...)`:

| property | values | applies to |
|---|---|---|
| `svRole` | `primary`, `secondary`, `tertiary`, `danger`, `chip`, `tab` | `QPushButton`, `QToolButton` |
| `svSurface` | `plate`, `panel`, `inset`, `glass` | `QFrame` |

During migration the style also maps today's object names to roles so unmigrated pages render
correctly before their code changes: `PrimaryActionButton`, `PrimaryButton`, `*PrimaryBtn`,
`DetailsPrimaryActionButton` → primary; `SecondaryActionButton`, `SecondaryButton`, `*SecondaryBtn`,
`HistoryActionButton`, `ModelsActionButton` → secondary; `TertiaryActionButton` → tertiary;
`ModelsDangerButton` → danger; `InspectorTab`, `ModelsViewToggle`, `TitleBarModeButton` → tab or chip;
object names ending in `Card` → panel. The map is a single table in `SvStyle.cpp` and is deleted at the
end of the wave when every site sets the property itself.

What the style draws, and from which token:

| element | fill | edge | radius | notes |
|---|---|---|---|---|
| primary button | `AccentHover`→`Accent` vertical gradient | inset 1 px `AccentTertiary` at 35 % | `radiusCard()` | white text, 600 weight, min height 34, padding 0 18; the only control on the card radius, which is what marks it as the hero |
| secondary button | `Surface2` | `Border` hairline | `radiusControl()` | hover `BorderStrong` + 6 % white |
| tertiary button | transparent | hairline on hover only | `radiusControl()` | text `TextMid`, hover `TextHi` |
| danger button | `Error` at 16 % | `Error` hairline | `radiusControl()` | text `Error` |
| chip | `Surface1` | `Border` | `radiusControl()` | checked: `BorderStrong` + 5 % white |
| tab | none | none | 0 | checked: 2 px `Accent` underline with `AccentGlow` |
| line/text edit | `Surface0` | `Border`, focus `AccentHover` | `radiusControl()` | placeholder `TextLo` |
| combo | as line edit | | | chevron drawn as a 1.8 px stroke, `TextLo` |
| spin box | as line edit | | | up/down as strokes, no bevel |
| check / radio indicator | `Surface0` | `BorderStrong` | 4 px / round | checked fill `Accent`, mark white |
| slider | groove `Surface0` + `BorderSubtle`; fill `Accent` at 55 % opacity | handle `Surface2` + `BorderStrong` | round | |
| scrollbar | track transparent; handle `Border` at hover `BorderStrong` | none | round | extent 8 px, no arrows |
| progress bar | track `Surface0`; chunk `Accent` | `BorderSubtle` | 3 px | `GlowProgressBar` keeps its own paint |
| tab bar (`QTabBar`) | as tab role | | | |
| item view row | selected `AccentSubtle`, hover 4 % white | none | 4 px | |
| header section | `Surface1` | bottom hairline | 0 | |
| frame `plate` | `Surface1` | `Border` + 1 px `GlassHighlight` top line | `radiusCard()` | the canvas card, the prompt card |
| frame `panel` | `Surface1` | `Border` | `radiusCard()` | every other card |
| frame `inset` | `Surface0` | `BorderSubtle` | `radiusControl()` | recessed groups |
| frame `glass` | delegated to `DashboardGlassPanel` | | | the existing painted class stays |
| focus ring | none | 2 px `AccentHover` | element radius + 2 | `PE_FrameFocusRect` |

Metrics the style owns: `PM_ScrollBarExtent` 8, `PM_ButtonShiftHorizontal/Vertical` 0,
`PM_DefaultFrameWidth` 1, `PM_FocusFrameHMargin` 2, `PM_TabBarTabVSpace` 8. `sizeFromContents` gives
role-based minimum heights: primary 34, secondary 30, tertiary 28, chip 24, tab 34, edits 28.

Hairline weight multiplies by the material: Refined Glass ×1.0, Matte Instrument ×1.45, Hybrid ×1.25
(Doc 47's values). Radii come from `radiusControl()` and `radiusCard()`, which already vary by material
(10/6, 6/4, 8/5). This is what makes the Surface Style setting reach the cockpit.

### 2.2 `qt_ui/style/SvKit.{h,cpp}` — factories that set the role

Free functions in `spellvision::kit`, each returning the created widget with the property set and the
object name preserved:

```
QPushButton *button(Role role, const QString &text, const QString &objectName, QWidget *parent);
QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent);   // checkable
QFrame      *card(Surface surface, const QString &objectName, QWidget *parent);       // StyledPanel
QWidget     *row(const QString &label, QWidget *control, QWidget *parent);            // label left, control right, hairline below
void         setRole(QWidget *w, Role role);      // for widgets that already exist
void         setSurface(QFrame *f, Surface s);
```

`setRole` and `setSurface` call `style()->unpolish(w); style()->polish(w); w->update();` so a role
change at runtime repaints. Nothing else lives here; no layouts, no copy, no page knowledge.

### 2.3 `qt_ui/style/SvFonts.{h,cpp}` and `qt_ui/fonts/`

Bundled under the SIL Open Font License 1.1, with `OFL.txt` beside them: IBM Plex Sans Regular, Medium,
SemiBold; IBM Plex Mono Regular, Medium. `registerBundledFonts()` adds each through
`QFontDatabase::addApplicationFont`, returns the families that registered, and `main.cpp` sets the
application font to IBM Plex Sans 12 px when registration succeeded, Segoe UI 12 px otherwise. The
existing `ThemeManager::Type` ramp keeps its sizes (28/20/16/14/12/12/11/11/10/9) and moves to weights
600/600/600/500/400/500/400/500/500/500, which are the weights Plex ships. `fontCss()` keeps its
signature. A new `ThemeManager::numericFont()` returns the UI font with the `tnum` feature set; the
status bar labels, the cockpit chips and the queue table use it.

The five stylesheets naming JetBrains Mono or Cascadia Mono change to `IBM Plex Mono`.

### 2.4 Stylesheet retreat

The rule for every stylesheet in `qt_ui` after this wave: **a stylesheet may set spacing, padding,
margins and minimum sizes; it may not draw a control.** Any `background`, `border`, `border-radius`,
`color` rule on a type the style owns (`QPushButton`, `QToolButton`, `QLineEdit`, `QTextEdit`,
`QPlainTextEdit`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QCheckBox`, `QRadioButton`, `QSlider`,
`QScrollBar`, `QProgressBar`, `QTabBar`, `QHeaderView`, `QAbstractItemView`, and `QFrame` object names
carrying a surface) is deleted, and the widget receives the property instead.

Sheets affected, with today's object-name rule counts: `ThemeManager.cpp` 132 (shell 309 lines, cockpit
186, settings 68, home 19, overlay 30), `ComicStudioPage.cpp` 26, `CharacterStudioPage.cpp` 21,
`ModelManagerPage.cpp` 21, `ConceptReferencePage.cpp` 18, `HomeDashboardPage.cpp` 18,
`T2VHistoryPage.cpp` 16, `WorkflowLibraryPage.cpp` 7, `InspirationPage.cpp` 7,
`DatasetGenerationPage.cpp` 7, `TrainPage.cpp` 6, `Gen3DPage.cpp` 6, `ImageGenerationPage.cpp` 4.

Kept: the qApp overlay sheet (`applicationOverlayStyleSheet`) for tooltips, menus, popups and message
boxes, because they escape the window cascade; its values already come from tokens and its radii move
to `radiusControl()`.

`shellStyleSheet` converts from positional `.arg()` to the `@token@` replace idiom as its drawing rules
leave, which retires the `%N` shift trap recorded in Doc 32. `assertNoUnresolvedTokens` runs on every
generator, not only the shell.

`DashboardSurfaceTokens::radiusHero/radiusPanel/radiusInset/radiusChip` are deleted; the painted
dashboard classes read `radiusCard()` (hero, panel) and `radiusControl()` (inset, chip). The thirteen
`setCornerRadius` literals become role calls.

Migration order, one Debug build, one `ctest`, one pytest run between steps:

1. Install `SvStyle`, fonts, factories, ratchets at their starting baselines. Nothing else changes.
   The app must look the same or better; the matrix must pass.
2. Shell: `shellStyleSheet` drawing rules out; title bar, rail, status bar, drawer.
3. Cockpit: `imageGenerationStyleSheet` and the four per-widget sheets in `ImageGenerationPage`.
   The canvas card gets `svSurface=glass`.
4. Models, Flows, History.
5. Character, Comic, Concept studios.
6. Home, Settings, Dataset, Train, Gen3D, Inspiration, Runtime, dialogs.
7. Delete the object-name→role map from `SvStyle.cpp`. Every site now sets its own property.

### 2.5 Live switching

`ThemeManager::applyApplicationChrome` gains a third step after palette and overlay:
`SvStyle::refreshAll()`, which walks `QApplication::allWidgets()` and calls `unpolish`, `polish`,
`update` on each. It is connected to `themeChanged` exactly where the palette already is. Preset swaps
colours; material swaps radii, hairline weight and plate paint; both reach every control because the
style draws them.

Default preset for a fresh install becomes `Preset::ArcaneGlass`. Existing installs keep their persisted
`appearance/themePreset`; there is no migration and no silent restyle.

### 2.6 Ratchets

New rules in `tests/sweeps/rules.py`, selecting `cpp_sources()`, baselines in `exemptions.py`,
one-way down, each citing the audit item:

| rule | counts | start | end of wave |
|---|---|---|---|
| `qss-literal-radius` | `border-radius:\s*\d+px` in `qt_ui` | 133 | 0 outside the overlay sheet |
| `qss-draws-a-control` | a stylesheet rule on an owned type that sets background, border, border-radius or color | measured at step 1 | 0 outside the overlay sheet |
| `primary-button-defined-once` | `#PrimaryActionButton\s*\{` outside `ThemeManager.cpp` | 3 | 0 |
| `type-weight-on-ramp` | `font-weight:\s*(700\|800\|900)` in stylesheets, plus `setWeight` off the 400/500/600 ramp | measured at step 1 (36 declarations today) | 0 |
| `font-family-is-shipped` | any `font-family` naming a family not in `SvFonts::bundledFamilies()` or the platform fallback | 5 | 0 |
| `spacing-literal` | `setSpacing(n)` / `setContentsMargins(...)` with a non-zero literal that is not a `Spacing::` token | ~141 | baseline, direction down |

`test_rule_matches_its_baseline` already enforces one-way movement and prints the debt.

### 2.7 Tests

- `tests/cpp/test_sv_style.cpp` (offscreen platform): for each button role, render a 120×34 button to a
  `QImage` and assert the centre pixel equals the role's token within ±2 per channel; switch
  `ThemeManager` to Matte Instrument and assert `pixelMetric`-derived corner radius changes and the
  hairline alpha changes; assert `numericFont()` reports the `tnum` feature; assert
  `bundledFamilies()` contains "IBM Plex Sans" when the fonts directory is present.
- The existing responsive matrix (36 cells) runs after every migration step; its QSS-parse-warning
  clause catches a malformed sheet.
- `tests/test_ui_release_polish.py` keeps passing unchanged; no object name it asserts on is renamed.
- UIA re-capture (`scripts/dev/uia`) of T2I, Home, Models, Flows, History in Arcane Glass under all
  three materials and in Ivory Holograph. A script computes the fraction of differing pixels between
  the Refined Glass and Matte Instrument cockpit captures; the wave is not done below 1 %.
- Startup trace (`SPELLVISION_STARTUP_TRACE`) before and after: font registration must cost under
  100 ms; if it does not, fonts load after first paint.

### 2.8 Success criteria

1. Every control on every page is drawn by `SvStyle`; `qss-draws-a-control` is 0 outside the overlay.
2. `primary-button-defined-once` 0; `qss-literal-radius` 0 outside the overlay; `font-family-is-shipped` 0;
   `type-weight-on-ramp` 0.
3. Refined Glass and Matte Instrument cockpit captures differ by more than 1 % of pixels.
4. Debug build green; `ctest` green including the new test; full pytest green; sweeps baseline lowered.
5. Owner eyes on the five captures in Arcane Glass and Ivory Holograph (Doc 30's gate).

## 3. Risks and how they are held

- **Mixed rendering mid-migration.** Any remaining stylesheet rule on a widget makes Qt use
  `QStyleSheetStyle` for that widget and fall through to `SvStyle` for the rest. Expected; contained by
  the per-page order and a matrix run per step.
- **Fusion base changes unmigrated pages at once** (scrollbars, combos). Intended; the palette keeps
  colour coherent, and step 1 is judged by eye before step 2 starts.
- **Object names are load-bearing.** UIA (`PrimaryActionButton` is how Generate is found), the matrix
  and eleven pytest ratchets read them. No object name is renamed in this wave.
- **`%N` argument shift.** Deleting a rule from a positional sheet shifts every later argument. The
  conversion to `@token@` happens per sheet before its rules are deleted, never after.
- **`ImageGenerationPage.cpp` is 26 lines under its 3000-line ceiling.** Kit adoption there is
  deletion-heavy (sheets go away); any addition lands in `ImageGenerationPage_catalog.cpp` or the new
  style TUs.
- **Font licensing.** IBM Plex is OFL 1.1; the licence file ships beside the fonts and the About page
  names it.

## 4. Not in this wave

No page layout changes, no copy changes, no new controls beyond the factories, no shell layouts, no
notification layer, no polling changes, no theme art direction. Those are waves 2 to 5 and each gets
its own spec.

## 5. Programme map (for orientation only)

1. Foundation kit — this document.
2. Shell layouts: Instrument, Canvas, Workspaces; first-run picker; live switch in Settings.
   Grounding already gathered: the shell is `[rail | pageStack]` (`MainWindow.cpp:1615-1616`),
   Workspaces is achievable by re-parenting, Canvas needs the prompt card and action row promoted to
   members, the parking loop (`MainWindow.cpp:2200-2207`), the drawer's rail coupling
   (`MainWindow.cpp:4290`) and `setWidthBudget`'s fixed max (`CockpitInspector.cpp:138-139`) are the
   invariants to respect.
3. Feedback loop: optimistic Generate, adaptive then pushed progress, notification layer, no GUI-thread
   waits.
4. Surfaces: copy and paths, image-first cards, rail overflow, Simple as summary, History grid, Flows
   readiness cards, motion tokens.
5. Beyond S: live-preview lane, keyboard everywhere, undo, per-preset art direction, re-audit.
