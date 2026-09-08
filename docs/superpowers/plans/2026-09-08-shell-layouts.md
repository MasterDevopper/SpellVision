# Shell Layouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick one of three whole-app layouts at first run and switch between them live in Settings, without losing page state.

**Architecture:** A new owner, `qt_ui/shell/ShellLayout`, holds the choice and persists it. `MainWindow::applyShellLayout` is the only function that arranges shell furniture; it re-parents rather than rebuilds. The rail becomes a widget class that knows its own orientation and reports where page content begins, which is what finally lets the activity drawer stop computing its position from the rail's width.

**Tech Stack:** C++17, Qt 6.10.2, CMake + MSVC, QSettings (`DarkDuck`/`SpellVision`), pytest sweeps, QtTest.

**Spec:** `docs/superpowers/specs/2026-09-08-shell-layouts-design.md`

## Global Constraints

- `Stop-Process -Name SpellVision -ErrorAction SilentlyContinue` before EVERY build, or the link fails with LNK1168.
- Build: `cmake --build build --config Debug` from the repo root. Do not re-run the CMake configure unless `CMakeLists.txt` changed, then `cmake -S . -B build -G "Visual Studio 17 2022" -A x64`.
- Tests: `ctest --test-dir build -C Debug --output-on-failure` and `$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q`. Baselines at the start of this wave: ctest 23/23, pytest 2018 passed / 14 skipped / 6 deselected, sweeps TOTAL 183 with 22 of 27 rules at zero.
- A C++ test that touches `ThemeManager` or `ShellLayout` writes the REAL settings store — both construct `QSettings("DarkDuck","SpellVision")` explicitly, so redirection is a no-op. Back up in `initTestCase`, restore in `cleanupTestCase`, and keep any guard case LAST in its class (Qt runs slots in declaration order). The owner's live values are `appearance/themePreset=3`, `appearance/surfaceStyle=2`; `reg query "HKCU\Software\DarkDuck\SpellVision\appearance"` must still read those when you finish.
- Sweep baselines in `tests/sweeps/exemptions.py` are ONE-WAY: a count that rises fails the build, a count that falls must be lowered in the same commit. The pre-commit hook enforces this.
- A new sweep rule must be PROVED to fail on a planted violation before it is trusted, and its real coverage recorded. Wave 1's final review found four of six rules narrower than their names.
- Locate every edit site by NAME, never by the line numbers in this plan — they are from `112ee8d` and will shift. Read the file immediately before editing it.
- No object name may be renamed: tests, remaining stylesheet selectors and the UI-Automation capture scripts all key off them.
- Roles and surfaces are declared at a widget's creation site through `spellvision::kit::setRole` / `setSurface` (wave 1). A button with no role paints transparent fill AND transparent edge, so a new button without one is invisible.
- Do not stop the worker on port 8765 and do not touch anything under `runtime/`.
- No `Co-Authored-By` trailer on commits in this repo.

---

### Task 1: The layout owner

**Files:**
- Create: `qt_ui/shell/ShellLayout.h`, `qt_ui/shell/ShellLayout.cpp`
- Create: `tests/cpp/test_shell_layout.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Produces: `spellvision::shell::ShellLayout` singleton — `Layout` enum {`Instrument`=0, `Canvas`, `Workspaces`}, `instance()`, `layout()`, `setLayout(Layout)`, `setLayoutByIndex(int)`, `layoutNames()` (`QStringList`, user-facing), `layoutDescription(Layout)` (one sentence, user-facing), `load()`, `save()`, signal `layoutChanged(Layout)`.
- Consumed by Tasks 5, 8 and 9.

- [ ] **Step 1: Write the failing test**

Create `tests/cpp/test_shell_layout.cpp`. Mirror the fixture discipline of `tests/cpp/test_sv_style.cpp` — read it first for the settings backup/restore pattern and copy it exactly.

```cpp
#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "shell/ShellLayout.h"

using spellvision::shell::ShellLayout;
using Layout = spellvision::shell::ShellLayout::Layout;

class TestShellLayout : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        savedHadKey_ = s.contains(QStringLiteral("ui/shellLayout"));
        savedLayout_ = s.value(QStringLiteral("ui/shellLayout"), 0).toInt();
    }

    void the_default_is_instrument()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        s.remove(QStringLiteral("ui/shellLayout"));
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
    }

    void the_choice_survives_a_round_trip()
    {
        ShellLayout::instance().setLayout(Layout::Workspaces);
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Workspaces);
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QCOMPARE(s.value(QStringLiteral("ui/shellLayout")).toInt(), 2);
    }

    void a_no_op_set_does_not_announce_a_change()
    {
        ShellLayout::instance().setLayout(Layout::Canvas);
        QSignalSpy spy(&ShellLayout::instance(), &ShellLayout::layoutChanged);
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCOMPARE(spy.count(), 0);
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCOMPARE(spy.count(), 1);
    }

    void an_out_of_range_index_is_ignored_rather_than_crashing()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);
        ShellLayout::instance().setLayoutByIndex(7);
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
        ShellLayout::instance().setLayoutByIndex(-1);
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
    }

    void every_layout_has_a_name_and_a_sentence()
    {
        QCOMPARE(ShellLayout::instance().layoutNames().size(), 3);
        for (const QString &name : ShellLayout::instance().layoutNames())
            QVERIFY(!name.isEmpty());
        for (int i = 0; i < 3; ++i)
            QVERIFY(!ShellLayout::instance().layoutDescription(static_cast<Layout>(i)).isEmpty());
    }

    void cleanupTestCase()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        if (savedHadKey_)
            s.setValue(QStringLiteral("ui/shellLayout"), savedLayout_);
        else
            s.remove(QStringLiteral("ui/shellLayout"));
        s.sync();
    }

private:
    bool savedHadKey_ = false;
    int savedLayout_ = 0;
};

QTEST_MAIN(TestShellLayout)
#include "test_shell_layout.moc"
```

- [ ] **Step 2: Run it and watch it fail to compile**

Run: `cmake --build build --config Debug --target test_shell_layout`
Expected: FAIL, `shell/ShellLayout.h` not found.

- [ ] **Step 3: Write the owner**

`qt_ui/shell/ShellLayout.h` — a `QObject` singleton. Read `qt_ui/ThemeManager.h` first and mirror its shape (private constructor, `instance()`, `load`/`save`, a change signal), because the Settings page and `MainWindow` should meet one pattern rather than two. Do NOT put layout state into `ThemeManager`: a theme decides colour and material, a layout decides structure, and `themeChanged` already fans out to every widget that repaints.

The names and sentences are user-facing copy and are fixed by the spec:

```cpp
QStringList ShellLayout::layoutNames() const
{
    return {QStringLiteral("Instrument"), QStringLiteral("Canvas"), QStringLiteral("Workspaces")};
}

QString ShellLayout::layoutDescription(Layout layout) const
{
    switch (layout)
    {
    case Layout::Instrument:
        return QStringLiteral("A dense left rail with the inspector beside your work. The default.");
    case Layout::Canvas:
        return QStringLiteral("The image takes the room. Prompt and controls fold away until you need them.");
    case Layout::Workspaces:
        return QStringLiteral("Modes across the top, so wide pages like Models and History get the full width.");
    }
    return {};
}
```

`setLayout` writes, saves and emits ONLY on a real change. `load()` reads `ui/shellLayout`, clamping an out-of-range or absent value to `Instrument`.

- [ ] **Step 4: Register the test and the sources**

In `CMakeLists.txt`, add `qt_ui/shell/ShellLayout.cpp` to the core target's sources beside the other `qt_ui/shell/*.cpp` entries, and add a `test_shell_layout` target beside `test_sv_style` — copy that target's definition exactly, including the `QT_ASSUME_STDERR_HAS_CONSOLE=1` test property, without which a Qt test prints zero bytes on failure.

- [ ] **Step 5: Build and run**

Run: `cmake -S . -B build -G "Visual Studio 17 2022" -A x64; cmake --build build --config Debug --target test_shell_layout; ctest --test-dir build -C Debug -R shell_layout --output-on-failure`
Expected: PASS, 5 cases. Then the full `ctest` (24/24 now) and the registry check.

- [ ] **Step 6: Commit**

```powershell
git add qt_ui/shell/ShellLayout.h qt_ui/shell/ShellLayout.cpp tests/cpp/test_shell_layout.cpp CMakeLists.txt
git commit -m "feat(shell): the layout is a choice the app can hold

An owner for it, shaped like ThemeManager so Settings meets one pattern rather
than two, and deliberately not part of ThemeManager: a theme decides colour, a
layout decides structure, and a preset should be wearable in any of the three.
Nothing reads it yet."
```

---

### Task 2: The rail becomes a widget

**Files:**
- Create: `qt_ui/shell/SideRail.h`, `qt_ui/shell/SideRail.cpp`
- Modify: `qt_ui/MainWindow.cpp` (`createSideRail`, `buildShell`, and every `sideRail_` reader), `qt_ui/MainWindow.h`
- Modify: `CMakeLists.txt`
- Test: `tests/cpp/test_shell_layout.cpp`

**Interfaces:**
- Consumes: `spellvision::kit::setRole` (rail buttons take `Role::Rail`).
- Produces: `spellvision::shell::SideRail` — `addMode(id, label, iconName)`, `addGroupHeader(text)`, `setCurrentMode(id)`, `setOrientation(Qt::Orientation)`, `orientation()`, `contentOrigin()` (a `QPoint` in `centralShell_` coordinates where page content begins), `buttonFor(id)`, signal `modeActivated(QString)`.

This task is a pure extraction: the rail must look and behave EXACTLY as it does now when vertical. Orientation support arrives in Task 3.

- [ ] **Step 1: Read what you are extracting**

`MainWindow::createSideRail` (`MainWindow.cpp:1656-1724` at `112ee8d`) and `MainWindow::createRailButton` (`:576-600`). Note before you move anything: the rail is a `QWidget` with a `QVBoxLayout`, wrapping a `QScrollArea` around a `column` widget whose `QVBoxLayout` holds one `QToolButton` per mode added with `Qt::AlignHCenter`; buttons are `ToolButtonTextUnderIcon` at a fixed 56x48; the rail itself takes `setFixedWidth(Chrome::ModeRailWidth)`. Also find every other place that touches `sideRail_` — at minimum `positionQueueOverlay`, `togglePrimarySidebar`, `updateModeButtonState`, and the theme-change lambda in `buildShell` that regenerates every button icon.

- [ ] **Step 2: Write the failing test**

Add to `tests/cpp/test_shell_layout.cpp`, before any guard case:

```cpp
    void the_rail_reports_where_content_begins()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.resize(rail.sizeHint());
        const QPoint origin = rail.contentOrigin();
        QCOMPARE(origin.y(), 0);
        QVERIFY2(origin.x() >= 48, qPrintable(QString::number(origin.x())));
    }
```

Run: `cmake --build build --config Debug --target test_shell_layout` — Expected: FAIL, `shell/SideRail.h` not found.

- [ ] **Step 3: Extract**

Move the two functions into `SideRail`, unchanged in behaviour. `contentOrigin()` returns `QPoint(width(), 0)` for a vertical rail. `MainWindow::createSideRail` becomes a thin builder that constructs a `SideRail`, feeds it the mode list it already builds, and connects `modeActivated` to `switchToMode`.

Every reader of `sideRail_` keeps working: `sideRail_` changes type from `QWidget*` to `SideRail*` in `MainWindow.h`, and any code that reached into the rail's children by `findChild` or by index must instead call `buttonFor(id)`. If you find a reader this interface cannot serve, add the accessor rather than exposing the layout.

- [ ] **Step 4: Prove it is a no-op, visually**

Run: `Stop-Process -Name SpellVision -ErrorAction SilentlyContinue; cmake --build build --config Debug; ctest --test-dir build -C Debug --output-on-failure; $env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q`
Then: `.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix rail-extract -Presets 3 -Materials 2` and compare each shot against its `kit-final` equivalent with `scripts\dev\uia\compare_captures.py`.
Expected: every pair under 0.0010. An extraction that moves pixels is not an extraction. If a pair exceeds it, find out why before proceeding — the capture rig also saves the WRONG PAGE under the right filename when a drive step fails, so confirm the page is what you think it is first.

- [ ] **Step 5: Commit**

```powershell
git add qt_ui/shell/SideRail.h qt_ui/shell/SideRail.cpp qt_ui/MainWindow.cpp qt_ui/MainWindow.h tests/cpp/test_shell_layout.cpp CMakeLists.txt
git commit -m "refactor(shell): the rail is a widget that knows its own shape

Extracted from two MainWindow methods with no behaviour change — the captures
move by less than a thousandth of a pixel fraction. It gains one thing it never
had: an answer to where page content begins, which is the question the activity
drawer has been guessing at."
```

---

### Task 3: Orientation, and the chrome tokens that were missing

**Files:**
- Modify: `qt_ui/shell/SideRail.{h,cpp}`
- Modify: `qt_ui/ThemeManager.h` (`Chrome` enum), `qt_ui/ThemeManager.cpp` (`chrome()`)
- Modify: `qt_ui/MainWindow.cpp` (the status bar's three hardcoded heights)
- Test: `tests/cpp/test_shell_layout.cpp`

**Interfaces:**
- Consumes: `SideRail::setOrientation` from Task 2.
- Produces: `Chrome::RailBarHeight` (44), `Chrome::StatusBarHeight` (40). `Chrome::MenuBarHeight` is DELETED — it has no reader anywhere in the tree.

- [ ] **Step 1: Write the failing test**

```cpp
    void the_rail_changes_shape_with_its_orientation()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.addMode(QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("home"));

        rail.setOrientation(Qt::Vertical);
        rail.resize(rail.sizeHint());
        const QPoint vertical = rail.contentOrigin();
        const QSize verticalButton = rail.buttonFor(QStringLiteral("t2i"))->size();

        rail.setOrientation(Qt::Horizontal);
        rail.resize(rail.sizeHint());
        const QPoint horizontal = rail.contentOrigin();
        const QSize horizontalButton = rail.buttonFor(QStringLiteral("t2i"))->size();

        QCOMPARE(vertical.y(), 0);
        QVERIFY(vertical.x() > 0);
        QCOMPARE(horizontal.x(), 0);
        QVERIFY(horizontal.y() > 0);
        QVERIFY2(horizontalButton.width() > verticalButton.width(),
                 "a horizontal rail sets its label beside the icon, so its buttons are wider");
        QVERIFY2(horizontalButton.height() < verticalButton.height(),
                 "and shorter");
    }
```

Run the target — Expected: FAIL (no `setOrientation`).

- [ ] **Step 2: Implement orientation**

`setOrientation` rebuilds the rail's internals: swap both `QVBoxLayout`s for `QHBoxLayout`s (and back), switch buttons between `ToolButtonTextUnderIcon` at 56x48 and `ToolButtonTextBesideIcon` at a height of `chrome(Chrome::RailBarHeight)`, and swap `setFixedWidth(ModeRailWidth)` for `setFixedHeight(RailBarHeight)`, clearing the other constraint with `QWIDGETSIZE_MAX`. The scroll area's scrollbar policies swap with it. `contentOrigin()` returns `QPoint(width(), 0)` vertical, `QPoint(0, height())` horizontal.

Group headers (Create / Manage / System) render as separators vertically and as labelled boundaries horizontally; the mode list and its groups already exist in `MainWindow` — pass them through `addGroupHeader` rather than teaching `SideRail` the app's modes.

- [ ] **Step 3: The tokens**

Add `RailBarHeight` (44) and `StatusBarHeight` (40) to `Chrome` and to `ThemeManager::chrome()`. Delete `MenuBarHeight` and confirm with a grep that nothing referenced it. Replace the status bar's three literals (`MainWindow.cpp:2318-2320`) with `chrome(Chrome::StatusBarHeight)` — that number was always this token.

- [ ] **Step 4: Build, test, commit**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
git add qt_ui/shell/SideRail.h qt_ui/shell/SideRail.cpp qt_ui/ThemeManager.h qt_ui/ThemeManager.cpp qt_ui/MainWindow.cpp tests/cpp/test_shell_layout.cpp
git commit -m "feat(shell): the rail can lie down

Orientation swaps both layouts, the button style and which dimension is fixed.
Two chrome tokens arrive with it: a height for a horizontal rail, and the status
bar's 40, which was hardcoded three times two lines apart. MenuBarHeight is
deleted — it was declared, never read, and named for a menu bar this shell does
not have."
```

---

### Task 4: The drawer stops guessing, and a ratchet says so

**Files:**
- Modify: `qt_ui/MainWindow.cpp` (`positionQueueOverlay`)
- Modify: `tests/sweeps/rules.py`, `tests/sweeps/exemptions.py`
- Test: `tests/test_sweeps.py` (the rule's own probe test, beside the existing ones)

**Interfaces:**
- Consumes: `SideRail::contentOrigin()` from Task 2.

- [ ] **Step 1: Fix the geometry**

`positionQueueOverlay` (`MainWindow.cpp:4276-4292`) reads `sideRail_->width()` and starts the drawer at that X. Replace with `contentOrigin()`, so the drawer's rect is `QRect(origin.x(), shellHeight - h, shellWidth - origin.x(), h)` for a vertical rail and takes the origin's Y for a horizontal one. Keep the visibility check that currently zeroes `railWidth` when the rail is hidden — a hidden rail's origin is the top-left corner.

- [ ] **Step 2: Write the ratchet, and plant a violation first**

Add `shell-geometry-through-the-layout` to `tests/sweeps/rules.py`: outside `qt_ui/shell/`, no file may read `sideRail_->width()`, `sideRail_->height()`, `Chrome::ModeRailWidth` or `Chrome::RailBarHeight` in order to position something. Follow the existing rules' shape, and read `_check_qss_draws_a_control` first for how a rule reports a `Violation` with a path, a line and a key.

Then PROVE it, on in-memory mutated text, exactly as wave 1's rules were proved:

```
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -c "from pathlib import Path; from tests.sweeps import rules; p=Path('qt_ui/MainWindow.cpp'); t=p.read_text(encoding='utf-8',errors='ignore'); t=t.replace('void MainWindow::resizeEvent', 'void MainWindow::probe() { const int w = sideRail_->width(); Q_UNUSED(w); }\n\nvoid MainWindow::resizeEvent', 1); print([ (v.line, v.key) for v in rules._check_shell_geometry_through_the_layout(p, t) ])"
```

Expected: exactly one violation, at the planted line. A rule that has not been seen to fail is not trusted. Record the probe and its output in your report, and record in a comment what the rule does NOT catch.

- [ ] **Step 3: Baseline and commit**

Run the sweeps. The rule should be at zero once step 1 lands; if any other reader exists, fix it rather than baselining it, and say so.

```powershell
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
git add qt_ui/MainWindow.cpp tests/sweeps/rules.py tests/sweeps/exemptions.py tests/test_sweeps.py
git commit -m "fix(shell): the drawer asks where content begins instead of measuring the rail

positionQueueOverlay started the drawer's X at sideRail_->width(), which is
correct for exactly as long as the rail is a left-hand vertical strip. A rule
now forbids positioning anything off the rail's width outside the shell, with a
planted violation on record proving it fails."
```

---

### Task 5: applyShellLayout, and two layouts that work

**Files:**
- Modify: `qt_ui/MainWindow.{h,cpp}` (`buildShell`, a new `applyShellLayout`, the `switchToMode` tail)
- Modify: `tests/sweeps/rules.py`, `tests/sweeps/exemptions.py`
- Test: `tests/cpp/test_shell_layout.cpp`

**Interfaces:**
- Consumes: `ShellLayout` (Task 1), `SideRail::setOrientation` (Task 3).
- Produces: `MainWindow::applyShellLayout(ShellLayout::Layout)`.

This task ships **Instrument** and **Workspaces**. Canvas needs the cockpit refactor and arrives in Task 7.

- [ ] **Step 1: Write the failing test — a switch must not cost the user their prompt**

The heart of the feature. Build a `MainWindow`, type into a page, switch layout, and assert both the page pointer and the text survive.

```cpp
    void a_layout_switch_keeps_the_page_and_what_is_typed_in_it()
    {
        MainWindow window;
        window.resize(1400, 900);
        window.setAttribute(Qt::WA_DontShowOnScreen);
        window.show();
        window.switchToMode(QStringLiteral("t2i"));
        QWidget *before = window.currentPageForTest();
        QVERIFY(before);
        QPlainTextEdit *prompt = before->findChild<QPlainTextEdit *>(QStringLiteral("PromptInput"));
        QVERIFY(prompt);
        prompt->setPlainText(QStringLiteral("a lighthouse in a storm"));

        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();

        QCOMPARE(window.currentPageForTest(), before);
        QCOMPARE(prompt->toPlainText(), QStringLiteral("a lighthouse in a storm"));
    }
```

`currentPageForTest()` is a small accessor you add to `MainWindow` returning `pageStack_->currentWidget()`. Verify `PromptInput` is the live object name before relying on it; if it differs, use the real one.

- [ ] **Step 2: Write applyShellLayout**

One function owns the arrangement. Instrument sets `shellLayout` to `LeftToRight` with the rail first and the rail vertical. Workspaces re-parents the rail into a `QVBoxLayout` above the stack — the simplest implementation replaces `shellLayout`'s direction with `TopToBottom` and sets the rail horizontal, since `QBoxLayout::setDirection` re-lays existing children without re-parenting them.

Four rules bind it: it re-parents and never constructs a page; it is idempotent, so calling it twice with the same layout is a no-op; it runs again whenever a page is built (call it at the tail of `ensureGenerationPageBuilt` and `ensureDeferredPageBuilt`, because a page built after a switch has not seen the current layout); and it ends by repositioning the drawer.

`buildShell` calls it once with `ShellLayout::instance().layout()` after loading, and connects `layoutChanged` to it.

- [ ] **Step 3: The second ratchet**

`layout-switch-is-not-a-rebuild`: within `applyShellLayout` and any function it calls in `MainWindow.cpp`, forbid `new <Page>`, `deleteLater`, `removeWidget` and `pageStack_->clear()`. A static rule cannot follow a call graph, so scope it to the body of `applyShellLayout` itself and say plainly in the rule's comment that it checks one function's body, not its callees — an honest narrow rule beats a broad one that cannot deliver. Prove it with a planted `deleteLater` and record the probe.

- [ ] **Step 4: Measure the two layouts apart**

```powershell
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix layout-a -Presets 3 -Materials 2
```
Drive T2I, Home and Models in each of Instrument and Workspaces, then compare each page's two shots. Expected: at least 0.0100 per page — the spec's criterion 3 and the same gate wave 1 used to catch a Surface Style option that had never differed. Report all three numbers.

- [ ] **Step 5: Commit**

```powershell
git add qt_ui/MainWindow.cpp qt_ui/MainWindow.h tests/cpp/test_shell_layout.cpp tests/sweeps/rules.py tests/sweeps/exemptions.py
git commit -m "feat(shell): two layouts, switched live, without losing the page

applyShellLayout is the only function that arranges shell furniture, it
re-parents rather than rebuilds, and it runs again when a lazily built page
arrives so a page built after a switch is not left in the old shape. A ratchet
forbids it constructing or deleting a page, because that failure would look
like a glitch and cost the user their prompt."
```

---

### Task 6: The cockpit's movable parts become members

**Files:**
- Modify: `qt_ui/ImageGenerationPage.h`, `qt_ui/ImageGenerationPage.cpp` (`buildUi`)

No visual change. This is the prerequisite that makes Canvas possible, and it is worth landing alone so that if Canvas needs redesign, this does not go back with it.

- [ ] **Step 1: Promote three locals**

In `buildUi`: `promptCard` (`ImageGenerationPage.cpp:595`) and `canvasCard` (`:1064`) become members `promptCard_` and `canvasCard_`. The action row (`:1399`) is a bare `QHBoxLayout` — a layout cannot be re-parented, so wrap it in a `QWidget` member `actionRow_` that owns it, and add that widget where the layout is added today (`:1463`).

Keep every object name exactly as it is: `PromptCard` and `CanvasCard` are read by stylesheets, by the wave-1 surface roles and by the capture scripts.

- [ ] **Step 2: Prove it changed nothing**

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix cockpit-members -Presets 3 -Materials 2
```
Compare the T2I shot against its `layout-a` equivalent: expected under 0.0010. Wrapping a layout in a widget adds a level to the tree, so if the number is larger, find the margin that appeared and zero it rather than accepting it.

- [ ] **Step 3: Commit**

```powershell
git add qt_ui/ImageGenerationPage.h qt_ui/ImageGenerationPage.cpp
git commit -m "refactor(cockpit): the prompt, the canvas and the action row are addressable

Three of the cockpit's four structural pieces were locals in buildUi, reachable
afterwards only by findChild on an object name. The action row was not even a
widget. No pixel moves; the next task needs to be able to pick them up."
```

---

### Task 7: The Canvas layout

**Files:**
- Modify: `qt_ui/ImageGenerationPage.{h,cpp}`
- Modify: `qt_ui/MainWindow.cpp` (`applyShellLayout` tells the current page)
- Modify: `qt_ui/generation/CockpitInspector.{h,cpp}`

**Interfaces:**
- Consumes: `promptCard_`, `canvasCard_`, `actionRow_` (Task 6); `ShellLayout::Layout` (Task 1).
- Produces: `ImageGenerationPage::applyShellLayout(ShellLayout::Layout)`, `CockpitInspector::setCollapsed(bool)`.

- [ ] **Step 1: The inspector learns to collapse**

`CockpitInspector` currently fixes its width through `setWidthBudget` (`generation/CockpitInspector.cpp:134-160`, clamping to 280-460 and setting equal min and max). Add `setCollapsed(bool)`: collapsed, it shows only its four tab icons at a fixed 48 px and its content area is hidden; expanded, it restores the budget it had. Collapsing must not lose a control's value — the widgets are hidden, never destroyed.

- [ ] **Step 2: The page arranges itself**

`ImageGenerationPage::applyShellLayout`: Instrument and Workspaces restore today's order (prompt card above the canvas, action row inside the canvas card, inspector expanded). Canvas moves `actionRow_` into the canvas card's footer, collapses `promptCard_` to a single-line height that grows on focus, and calls `setCollapsed(true)`.

Every one of those is reversible, and switching back must restore the previous arrangement exactly — assert it with a capture compare against the Instrument shot, not by eye.

- [ ] **Step 3: Test that the switch is lossless in both directions**

Extend the Task 5 test: type a prompt, switch to Canvas, switch back, assert the text and the page pointer both survive, and assert `cockpitInspector_` is expanded again.

- [ ] **Step 4: Measure and commit**

Capture T2I in all three layouts at one preset; every pair must exceed 0.0100. Report the three numbers.

```powershell
git add qt_ui/ImageGenerationPage.h qt_ui/ImageGenerationPage.cpp qt_ui/MainWindow.cpp qt_ui/generation/CockpitInspector.h qt_ui/generation/CockpitInspector.cpp
git commit -m "feat(cockpit): Canvas gives the room to the image

The prompt folds to a line until focused, the action row moves into the canvas
card's footer, and the inspector becomes a rail of tab icons that expands over
the canvas. Nothing is removed and nothing is destroyed — collapsing hides
widgets, so a control's value survives the round trip, which the test asserts
in both directions."
```

---

### Task 8: Choosing in Settings

**Files:**
- Create: `qt_ui/shell/LayoutPickerWidget.{h,cpp}`
- Modify: `qt_ui/SettingsPage.{h,cpp}`
- Test: `tests/cpp/test_shell_layout.cpp`

**Interfaces:**
- Produces: `spellvision::shell::LayoutPickerWidget` — three selectable cards, each a painted diagram, a name and a sentence; signal `layoutPicked(ShellLayout::Layout)`. Shared with Task 9, which is why it is its own widget.

- [ ] **Step 1: The painted thumbnails**

Each card paints a small diagram of its arrangement from theme tokens — a rail block, a content block, an inspector block — so the thumbnails follow the active preset and cannot go stale the way a screenshot would. Read `qt_ui/style/SvStyle.cpp`'s `paintSurface` for how the wave paints a surface from tokens, and use `ThemeManager::color` for every colour. No literal hex, and no literal radius: `radiusCard()` and `radiusControl()` exist and the `qss-literal-radius` ratchet is at zero.

- [ ] **Step 2: The Settings card**

Add a "Layout" card to the Appearance section of `SettingsPage`, directly above Surface Style. Read `SettingsPage.cpp:246-265` and `:502-509` for the established pattern, and follow the SURFACE STYLE one: the control calls `ShellLayout::instance().setLayoutByIndex(index)` directly and the shell repaints off `layoutChanged`. Do NOT copy the theme-preset pattern that detours through a page signal into `MainWindow` glue — that road exists for historical reasons.

- [ ] **Step 3: Test the round trip through the UI**

Construct a `SettingsPage`, pick each layout through the widget, and assert `ShellLayout::instance().layout()` follows and `ui/shellLayout` is written. Restore the owner's value afterwards.

- [ ] **Step 4: Capture, and commit**

Capture Settings in two presets and confirm the three cards render, the current one is visibly selected (the wave-1 chip fix means selection is an accent tint over the plate plus an accent edge — check it reads on Ivory, which is where a white veil vanished), and nothing clips at 1180 px.

```powershell
git add qt_ui/shell/LayoutPickerWidget.h qt_ui/shell/LayoutPickerWidget.cpp qt_ui/SettingsPage.h qt_ui/SettingsPage.cpp tests/cpp/test_shell_layout.cpp CMakeLists.txt
git commit -m "feat(settings): the layout is a card of three painted choices

It follows the surface-style pattern that mutates directly rather than the
preset's detour through MainWindow glue. The thumbnails are drawn from theme
tokens, so they wear whichever preset is active and cannot go stale the way a
screenshot would."
```

---

### Task 9: Choosing at first run, and the criteria

**Files:**
- Modify: `qt_ui/shell/FirstRunDialog.{h,cpp}`
- Modify: `qt_ui/MainWindow.cpp` (the first-run trigger, if the dialog's contract changes)
- Modify: `docs/superpowers/specs/2026-09-08-shell-layouts-design.md` (a Results section)

- [ ] **Step 1: A second page in the dialog**

`FirstRunDialog` is one flat body today (`shell/FirstRunDialog.cpp:104-274`), fired 2 s after the window appears and gated on `setup/firstRunWizard_v1` (`MainWindow.cpp:1268-1299`). Make it a two-page `QStackedWidget`: the layout picker first, the environment checklist second, with Back and Next. Keep the same gate, the same suppression checkbox, and the same two exit actions.

Reuse `LayoutPickerWidget` from Task 8 — one widget, two surfaces, so the two cannot drift apart. Write `ui/shellLayout` on accept. A user who dismisses the dialog keeps Instrument, which is the default, so dismissal is never a trap.

- [ ] **Step 2: Measure the five criteria**

Run each of the spec's §5 criteria and record the measured value:

```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix wave2-final -Presets 0,3 -Materials 2
```

Criterion 4 needs the minimum window size: launch at exactly 1180x760 in each layout and confirm every rail mode is reachable with nothing clipped. Criterion 3 needs pairwise compares on T2I, Home and Models. Criterion 5 needs both ratchets at zero WITH their planted-violation proofs quoted.

- [ ] **Step 3: Record the outcome where a reader can reach it**

Add a Results section to the spec: the five criteria as a table with measured values and an explicit pass or miss per row, the pairwise layout distances, the ratchet counts with their probes, and the test counts. Wave 1 shipped a spec marked "shipped" whose numbers lived only in git-ignored directories, and the final review called it the task's central failure. Do not repeat it.

- [ ] **Step 4: Commit**

```powershell
git add qt_ui/shell/FirstRunDialog.h qt_ui/shell/FirstRunDialog.cpp qt_ui/MainWindow.cpp docs/superpowers/specs/2026-09-08-shell-layouts-design.md
git commit -m "feat(shell): the layout is the first thing the app asks

A picker page ahead of the environment checklist, sharing the Settings widget so
the two surfaces cannot drift. Dismissing keeps Instrument, which is the default,
so there is no trap in closing it. The wave's five criteria are measured into the
spec rather than into a git-ignored directory."
```

---

## Self-review

**Spec coverage.** §2.1 the three layouts: Tasks 5 (Instrument, Workspaces) and 7 (Canvas). §2.2 the owner: Task 1. §2.3 applying live: Task 5. §2.4 the orientation-aware rail and the chrome tokens: Tasks 2 and 3. §2.5 the drawer: Task 4. §2.6 the cockpit's movable parts: Tasks 6 and 7. §2.7 first run: Task 9. §2.8 Settings: Task 8. §2.9 exclusions: nothing to build. §3 both ratchets: Tasks 4 and 5, each with a planted-violation proof. §4 tests: Task 1 (round trip, no-op, range), 2 and 3 (rail geometry), 5 and 7 (lossless switch), 8 (UI round trip); captures in 2, 5, 6, 7, 8, 9. §5 criteria: Task 9 step 2.

**Placeholders.** None. Every test case is written out; the two extractions (Tasks 2 and 6) give anchors and a no-op gate rather than transcribed code, because the code to move is 70 lines that will have shifted and must be read from the file.

**Type consistency.** `ShellLayout::Layout`, `layoutNames`, `layoutDescription`, `setLayoutByIndex`, `layoutChanged` are used with one spelling throughout. `SideRail::contentOrigin`, `setOrientation`, `buttonFor` likewise. `applyShellLayout` names the same function on `MainWindow` and on `ImageGenerationPage`, taking the same enum in both.

**Ordering.** Task 6 lands before 7 so the Canvas layout can be redesigned without taking the refactor back. Task 4 lands before 5 so the first layout switch does not ship a drawer in the wrong place. Task 8 lands before 9 so the picker widget exists before two surfaces need it.
