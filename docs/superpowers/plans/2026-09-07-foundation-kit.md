# Foundation Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every control in SpellVision is drawn by one `QProxyStyle` from ThemeManager tokens, roles travel as widget properties, the stylesheets keep only spacing, IBM Plex ships bundled, and six sweeps ratchets hold the line.

**Architecture:** `qt_ui/style/SvStyle` (a `QProxyStyle` over Fusion) reads `ThemeManager` colours, radii and material at draw time and paints buttons, edits, combos, spins, scrollbars, sliders, indicators, progress, tabs, item rows, headers, frames and the focus ring. `qt_ui/style/SvKit` sets the `svRole` / `svSurface` properties without renaming any object name. `qt_ui/style/SvFonts` registers the bundled Plex faces. The stylesheets retreat page by page, each step gated by a build, `ctest`, pytest and a UI-Automation capture.

**Tech Stack:** C++17, Qt 6.10.2 (Widgets, Test), CMake 3.21+ with the `Visual Studio 17 2022` generator, MSVC, Python 3.12 in `.venv` for pytest and the fetch/compare scripts, PowerShell for the UI-Automation captures.

**Spec:** `docs/superpowers/specs/2026-09-07-foundation-kit-design.md`

## Global Constraints

- Build: `Stop-Process -Name SpellVision -ErrorAction SilentlyContinue` before every build; then `cmake --build build --config Debug` from the repo root. The configure step already exists in `build/`; do not re-run CMake configure unless `CMakeLists.txt` changed (then `cmake -S . -B build -G "Visual Studio 17 2022" -A x64`).
- Tests: `ctest --test-dir build -C Debug --output-on-failure` (Qt tests get `PATH`, `QT_ASSUME_STDERR_HAS_CONSOLE=1` from CMake); `$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q` for the full Python suite. The pre-commit hook runs the ratchet subset on every commit and blocks the commit if it fails.
- No object name is renamed in this wave. UI Automation finds Generate by `PrimaryActionButton`; eleven pytest ratchets read object names from source.
- No page layout changes, no copy changes, no new controls beyond the factories (spec §4).
- `qt_ui/ImageGenerationPage.cpp` must stay at or under 3000 lines (`tests/test_godfile_split.py`, `IGP_MAX = 3000`; it is 2974 today). Additions for the cockpit go in `ImageGenerationPage_catalog.cpp` or the new style TUs.
- Sweeps ratchets are one-way: a count going up fails, a count going down must be lowered in `tests/sweeps/exemptions.py` (`test_rule_matches_its_baseline`).
- Commits: normal prose, one per task, no `Co-Authored-By` trailer (repo memory: this repo does not carry it). Branch is `wave/s-plus-ui`.
- Fonts: IBM Plex Sans (400/500/600) and IBM Plex Mono (400/500), SIL OFL 1.1, licence file shipped beside them.
- Stylesheet rule after this wave (spec §2.4): a stylesheet may set spacing, padding, margins and minimum sizes; it may not draw a control.
- Type ramp weights become 600/600/600/500/400/500/400/500/500/500 for Display/Title/Heading/Subtitle/Body/BodyStrong/Detail/Label/Caption/Micro (spec §2.3).

---

## File map

| file | responsibility | task |
|---|---|---|
| `scripts/dev/fetch_plex_fonts.py` | downloads the five Plex TTFs and the OFL text into `qt_ui/fonts/`; verifies magic bytes and licence text | 1 |
| `qt_ui/fonts/*.ttf`, `qt_ui/fonts/OFL.txt`, `qt_ui/fonts/README.md` | the bundled faces and their licence | 1 |
| `qt_ui/style/SvFonts.{h,cpp}` | `registerBundledFonts()`, `bundledFamilies()`, `fontsDirectory()` | 1 |
| `qt_ui/ThemeManager.{h,cpp}` | weight table, `numericFont()`, `applyApplicationChrome` calls `SvStyle::refreshAll()` | 1, 2 |
| `qt_ui/main.cpp` | registers fonts, sets the app font, installs `SvStyle` | 1, 2 |
| `qt_ui/style/SvStyle.{h,cpp}` | the proxy style: roles, surfaces, all drawing, metrics, `refreshAll()` | 2 |
| `qt_ui/style/SvKit.{h,cpp}` | `button`, `chip`, `card`, `row`, `setRole`, `setSurface` | 3 |
| `tests/cpp/test_sv_style.cpp` | pixel and metric assertions on the style, `tnum` on `numericFont()`, bundled families | 2 |
| `tests/sweeps/rules.py`, `tests/sweeps/exemptions.py` | six new rules and their baselines | 1, 3 |
| `scripts/dev/uia/Capture-SvThemes.ps1` | captures T2I and Home per preset and material, restores the owner's preset | 4 |
| `scripts/dev/uia/compare_captures.py` | fraction of differing pixels between two captures | 4 |
| `CMakeLists.txt` | new TUs in the core list, fonts copied beside the exe, `test_sv_style` registered | 1, 2 |
| `qt_ui/CustomTitleBar.cpp`, `qt_ui/MainWindow.cpp`, `qt_ui/ThemeManager.cpp` (shell sheet) | shell retreat | 4 |
| `qt_ui/ImageGenerationPage*.cpp`, `qt_ui/generation/CockpitInspector.cpp`, `qt_ui/DashboardSurfaceTokens.{h,cpp}`, `qt_ui/DashboardGlassPanel.cpp`, `qt_ui/assets/ModelCardDelegate.cpp`, `qt_ui/DashboardMetricChip.cpp`, `qt_ui/DashboardPreviewPlate.cpp` | cockpit retreat and the radius constants | 5 |
| `qt_ui/ModelManagerPage.cpp`, `qt_ui/WorkflowLibraryPage.cpp`, `qt_ui/T2VHistoryPage.cpp` | library retreat | 6 |
| `qt_ui/studios/*.cpp` | studio retreat | 7 |
| `qt_ui/HomeDashboardPage.cpp`, `qt_ui/HomeModuleFrame.cpp`, `qt_ui/SettingsPage.cpp`, `qt_ui/DatasetGenerationPage.cpp`, `qt_ui/TrainPage.cpp`, `qt_ui/Gen3DPage.cpp`, `qt_ui/InspirationPage.cpp`, `qt_ui/ManagerPage.cpp`, `qt_ui/ModePage.cpp`, `qt_ui/workflows/*Dialog.cpp` | remaining retreat | 8 |
| `qt_ui/style/SvStyle.cpp` (object-name map deleted), `.superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md` | closing the wave | 9 |

---

### Task 1: Bundled fonts, `SvFonts`, the type ramp, `numericFont()`, and the `font-family-is-shipped` ratchet

**Files:**
- Create: `scripts/dev/fetch_plex_fonts.py`
- Create: `qt_ui/fonts/IBMPlexSans-Regular.ttf`, `IBMPlexSans-Medium.ttf`, `IBMPlexSans-SemiBold.ttf`, `IBMPlexMono-Regular.ttf`, `IBMPlexMono-Medium.ttf`, `OFL.txt`, `README.md` (produced by the script)
- Create: `qt_ui/style/SvFonts.h`, `qt_ui/style/SvFonts.cpp`
- Create: `tests/cpp/test_sv_fonts.cpp`
- Modify: `qt_ui/main.cpp:288-297` (the Segoe block)
- Modify: `qt_ui/ThemeManager.h:139-152` (Type comments), `qt_ui/ThemeManager.h` near line 212 (declare `numericFont`)
- Modify: `qt_ui/ThemeManager.cpp:374-391` (weights), after `font(Type)` (define `numericFont`)
- Modify: `qt_ui/ImageGenerationPage.cpp:581, 726, 1184`, `qt_ui/ImageGenerationPage_catalog.cpp:822, 876` (mono family names)
- Modify: `CMakeLists.txt` (core source list next to `qt_ui/shell/ShellNavigationController.cpp`, lines 223-224; test registration after line 407; `WIN32_EXECUTABLE FALSE` list around line 545)
- Modify: `tests/sweeps/rules.py` (new rule + `ALL_RULES`), `tests/sweeps/exemptions.py` (baseline entry)

**Interfaces:**
- Produces: `namespace spellvision::style { QStringList registerBundledFonts(); QStringList bundledFamilies(); QString fontsDirectory(); }` in `qt_ui/style/SvFonts.h`.
- Produces: `QFont ThemeManager::numericFont() const;` (UI font with the OpenType `tnum` feature on).
- Produces: `qt_ui/fonts/` copied to `$<TARGET_FILE_DIR:SpellVision>/fonts` after every build.

- [ ] **Step 1: Record the startup baseline before anything changes**

Run (PowerShell, repo root):
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
$env:SPELLVISION_STARTUP_TRACE = "1"
$p = Start-Process -FilePath .\build\Debug\SpellVision.exe -WorkingDirectory (Get-Location) -PassThru
Start-Sleep -Seconds 12
Stop-Process -Id $p.Id -Force
Get-Content .\build\ui_startup_trace.log -Tail 12
```
Expected: lines ending with `main: after show visible=true …`. Copy the tail into `.superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md` under a heading `Startup baseline before fonts` (create the file and directory if absent; the session-orientation hook reads the newest `progress.md`).

- [ ] **Step 2: Write the fetch script**

Create `scripts/dev/fetch_plex_fonts.py`:
```python
"""Fetch the five IBM Plex faces SpellVision bundles, plus the OFL text.

Google Fonts serves TTF instances to a legacy user agent; this box's curl cannot reach the
network but urllib can (repo memory: HF single-file pulls work the same way). Files land in
qt_ui/fonts with the names ThemeManager and SvFonts expect. Re-runnable; overwrites.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "qt_ui" / "fonts"
UA = "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)"
CSS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600"
       "&family=IBM+Plex+Mono:wght@400;500")
OFL_URLS = (
    "https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt",
    "https://openfontlicense.org/documents/OFL.txt",
)
NAMES = {
    ("IBM Plex Sans", 400): "IBMPlexSans-Regular.ttf",
    ("IBM Plex Sans", 500): "IBMPlexSans-Medium.ttf",
    ("IBM Plex Sans", 600): "IBMPlexSans-SemiBold.ttf",
    ("IBM Plex Mono", 400): "IBMPlexMono-Regular.ttf",
    ("IBM Plex Mono", 500): "IBMPlexMono-Medium.ttf",
}
BLOCK = re.compile(
    r"font-family:\s*'([^']+)';\s*font-style:\s*normal;\s*font-weight:\s*(\d+);.*?src:\s*url\(([^)]+)\)",
    re.S,
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    css = fetch(CSS).decode("utf-8")
    found: dict[tuple[str, int], str] = {}
    for family, weight, url in BLOCK.findall(css):
        found[(family, int(weight))] = url
    missing = [k for k in NAMES if k not in found]
    if missing:
        print("CSS did not list:", missing)
        return 2
    for key, name in NAMES.items():
        data = fetch(found[key])
        if data[:4] not in (b"\x00\x01\x00\x00", b"true") or len(data) < 50_000:
            print("not a TTF or too small:", name, data[:4], len(data))
            return 3
        (OUT / name).write_bytes(data)
        print(f"{name}  {len(data) // 1024} KB")
    licence = b""
    for url in OFL_URLS:
        try:
            licence = fetch(url)
            break
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            print("licence fetch failed:", url, exc)
    if b"SIL OPEN FONT LICENSE" not in licence.upper():
        print("OFL text not obtained; supply qt_ui/fonts/OFL.txt by hand before committing")
        return 4
    (OUT / "OFL.txt").write_bytes(licence)
    (OUT / "README.md").write_text(
        "# Bundled fonts\n\n"
        "IBM Plex Sans (Regular, Medium, SemiBold) and IBM Plex Mono (Regular, Medium), "
        "licensed under the SIL Open Font License 1.1 (see OFL.txt). Fetched by "
        "`scripts/dev/fetch_plex_fonts.py`; registered at startup by `qt_ui/style/SvFonts.cpp`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it**

Run: `.\.venv\Scripts\python.exe scripts\dev\fetch_plex_fonts.py`
Expected: five lines like `IBMPlexSans-Regular.ttf  NNN KB`, exit 0, and `qt_ui/fonts/` holds five `.ttf`, `OFL.txt`, `README.md`. If it exits 4, fetch `OFL.txt` from a browser and place it there; the licence text must contain "SIL OPEN FONT LICENSE".

- [ ] **Step 4: Write the failing test for `SvFonts`**

Create `tests/cpp/test_sv_fonts.cpp`:
```cpp
// The five stylesheets that asked for 'JetBrains Mono' fell back to a generic monospace on every
// machine because nothing registered a font. This proves the bundled faces register and that the
// app can find them from the build tree.
#include <QtTest>
#include <QApplication>
#include <QFontDatabase>

#include "style/SvFonts.h"

class SvFontsTest : public QObject
{
    Q_OBJECT
private slots:
    void bundled_families_register()
    {
        const QStringList families = spellvision::style::registerBundledFonts();
        QVERIFY2(families.contains(QStringLiteral("IBM Plex Sans")),
                 qPrintable(QStringLiteral("registered: ") + families.join(", ")
                            + QStringLiteral(" from ") + spellvision::style::fontsDirectory()));
        QVERIFY(families.contains(QStringLiteral("IBM Plex Mono")));
        QVERIFY(QFontDatabase::families().contains(QStringLiteral("IBM Plex Sans")));
    }

    void bundled_families_are_the_registered_ones()
    {
        spellvision::style::registerBundledFonts();
        const QStringList bundled = spellvision::style::bundledFamilies();
        QCOMPARE(bundled.size(), 2);
        QVERIFY(bundled.contains(QStringLiteral("IBM Plex Sans")));
        QVERIFY(bundled.contains(QStringLiteral("IBM Plex Mono")));
    }
};

QTEST_MAIN(SvFontsTest)
#include "test_sv_fonts.moc"
```

- [ ] **Step 5: Write `SvFonts`**

Create `qt_ui/style/SvFonts.h`:
```cpp
#pragma once

#include <QString>
#include <QStringList>

namespace spellvision::style
{

// Registers every .ttf under fontsDirectory() with QFontDatabase. Idempotent: a second call returns
// the same families without registering twice. Returns the family names that registered.
QStringList registerBundledFonts();

// The families registerBundledFonts() has registered so far (empty before the first call).
QStringList bundledFamilies();

// The directory the fonts were (or would be) loaded from. Search order: <exe dir>/fonts,
// <exe dir>/../../qt_ui/fonts (the Debug build tree), <cwd>/qt_ui/fonts (run_ui.ps1 launches from
// the repo root). The first that exists wins; otherwise the first candidate is returned so a log
// line can say where the app looked.
QString fontsDirectory();

} // namespace spellvision::style
```

Create `qt_ui/style/SvFonts.cpp`:
```cpp
#include "style/SvFonts.h"

#include <QCoreApplication>
#include <QDir>
#include <QFontDatabase>
#include <QFileInfo>

namespace spellvision::style
{
namespace
{
QStringList &registeredFamilies()
{
    static QStringList families;
    return families;
}

bool &registrationDone()
{
    static bool done = false;
    return done;
}
} // namespace

QString fontsDirectory()
{
    const QString exeDir = QCoreApplication::applicationDirPath();
    const QStringList candidates = {
        exeDir + QStringLiteral("/fonts"),
        exeDir + QStringLiteral("/../../qt_ui/fonts"),
        QDir::currentPath() + QStringLiteral("/qt_ui/fonts"),
    };
    for (const QString &candidate : candidates)
    {
        if (QFileInfo(candidate).isDir())
            return QDir(candidate).canonicalPath();
    }
    return candidates.first();
}

QStringList registerBundledFonts()
{
    if (registrationDone())
        return registeredFamilies();
    registrationDone() = true;

    QDir dir(fontsDirectory());
    const QStringList files = dir.entryList({QStringLiteral("*.ttf"), QStringLiteral("*.otf")},
                                            QDir::Files, QDir::Name);
    for (const QString &file : files)
    {
        const int id = QFontDatabase::addApplicationFont(dir.filePath(file));
        if (id < 0)
            continue;
        for (const QString &family : QFontDatabase::applicationFontFamilies(id))
        {
            if (!registeredFamilies().contains(family))
                registeredFamilies().append(family);
        }
    }
    return registeredFamilies();
}

QStringList bundledFamilies()
{
    return registeredFamilies();
}

} // namespace spellvision::style
```

- [ ] **Step 6: Register the TU and the test in CMake; copy the fonts beside the exe**

In `CMakeLists.txt`, in the core source list, directly after the line `qt_ui/shell/ShellNavigationController.h` (line 224), add:
```cmake
    qt_ui/style/SvFonts.cpp
    qt_ui/style/SvFonts.h
```
After the `test_worker_response_parser` block (after line 407), add:
```cmake
# Five stylesheets asked for a font that was never registered and silently fell back. The bundled
# faces must register from the build tree, or every mono column in the cockpit is a lie.
qt_add_executable(test_sv_fonts tests/cpp/test_sv_fonts.cpp)
target_link_libraries(test_sv_fonts PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME sv_fonts COMMAND test_sv_fonts)
```
Add `test_sv_fonts` to the `set_target_properties(... PROPERTIES WIN32_EXECUTABLE FALSE)` list that begins around line 543 (the list that contains `test_canvas_aspect`).
Directly after the `qt_add_executable(SpellVision` block's `target_sources(SpellVision PRIVATE qt_ui/icons/SpellVision.rc)` line (line 353), add:
```cmake
# The bundled faces ride beside the exe so a deployed install finds them; the build tree finds
# them through SvFonts' second search candidate.
add_custom_command(TARGET SpellVision POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${CMAKE_SOURCE_DIR}/qt_ui/fonts" "$<TARGET_FILE_DIR:SpellVision>/fonts")
```

- [ ] **Step 7: Configure, build, run the test to see it fail, then pass**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Debug --target test_sv_fonts
ctest --test-dir build -C Debug -R sv_fonts --output-on-failure
```
Expected: `sv_fonts ... Passed`. If it fails with the `registered:` message listing an empty set, the directory it names is wrong: check `qt_ui/fonts` exists and holds the five `.ttf`.

- [ ] **Step 8: Apply the fonts in `main.cpp` and the ramp in ThemeManager**

In `qt_ui/main.cpp`, add `#include "style/SvFonts.h"` with the other includes, and replace the Segoe block (lines 288-297, the one starting `// Showcase typography: Segoe UI is always present`) with:
```cpp
    // Typography: the bundled IBM Plex faces (qt_ui/fonts, OFL 1.1) when they register, Segoe UI
    // when they do not. Registering before the window is built means every widget inherits it.
    {
        const QStringList bundled = spellvision::style::registerBundledFonts();
        QFont ui(bundled.contains(QStringLiteral("IBM Plex Sans")) ? QStringLiteral("IBM Plex Sans")
                                                                     : QStringLiteral("Segoe UI"));
        ui.setStyleHint(QFont::SansSerif);
        ui.setHintingPreference(QFont::PreferFullHinting);
        ui.setPixelSize(12);
        QApplication::setFont(ui);
    }
```
In `qt_ui/ThemeManager.cpp`, replace the body of `fontWeight` (lines 374-391) with:
```cpp
int ThemeManager::fontWeight(Type token) const
{
    // Three weights, the three Plex ships: 400 read, 500 label, 600 announce. 700 and 800 left
    // with the Segoe era; a heavier weight was the only way Segoe could look intentional.
    switch (token)
    {
    case Type::Display:    return 600;
    case Type::Title:      return 600;
    case Type::Heading:    return 600;
    case Type::Subtitle:   return 500;
    case Type::Body:       return 400;
    case Type::BodyStrong: return 500;
    case Type::Detail:     return 400;
    case Type::Label:      return 500;
    case Type::Caption:    return 500;
    case Type::Micro:      return 500;
    }
    return 400; // Type::Body -- safe default.
}
```
Directly after `QFont ThemeManager::font(Type token) const { ... }` add:
```cpp
QFont ThemeManager::numericFont() const
{
    // Tabular figures: every digit the same width, so a status-bar value or a chip does not
    // wobble as it counts. Plex carries the tnum feature; the fallback face may ignore it.
    QFont f = font(Type::Body);
    f.setFeature(QFont::Tag("tnum"), 1);
    return f;
}
```
In `qt_ui/ThemeManager.h`, next to `QFont font(Type token) const;` (line 212) add:
```cpp
    QFont numericFont() const;         // font(Type::Body) with OpenType tabular figures (tnum) on
```
and replace the Type enum comments (lines 141-150) so each line reads the new weight: `Display = 0, // 28 / 600`, `Title, // 20 / 600`, `Heading, // 16 / 600`, `Subtitle, // 14 / 500`, `Body, // 12 / 400`, `BodyStrong, // 12 / 500`, `Detail, // 11 / 400`, `Label, // 11 / 500`, `Caption, // 10 / 500`, `Micro, // 9 / 500`.

- [ ] **Step 9: Point the five mono sheets at Plex Mono and apply `numericFont()` to the status bar**

In `qt_ui/ImageGenerationPage.cpp:581` and `:726` and `qt_ui/ImageGenerationPage_catalog.cpp:822` and `:876` change `'JetBrains Mono',monospace` to `'IBM Plex Mono',monospace`. In `qt_ui/ImageGenerationPage.cpp:1184` change `'Cascadia Mono','Consolas',monospace` to `'IBM Plex Mono',monospace`.

In `qt_ui/MainWindow.cpp`, find `makeTelemetryLabel` (the lambda or function used at line 2360 `bottomReadyLabel_ = makeTelemetryLabel(...)`); inside it, after the label is constructed, add `label->setFont(ThemeManager::instance().numericFont());` (use the local variable name the helper uses for the created `QLabel`). Verify by grepping: `grep -n "numericFont" qt_ui/MainWindow.cpp` prints exactly one line inside that helper.

- [ ] **Step 10: Add the `font-family-is-shipped` rule**

In `tests/sweeps/rules.py`, before `ALL_RULES`, add:
```python
# --- R22: a font-family in a stylesheet must be one the app ships or the platform fallback -----------

_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;\"]+)")
_SHIPPED_FAMILIES = {"IBM Plex Sans", "IBM Plex Mono", "Segoe UI", "monospace", "sans-serif", "system-ui"}


def _check_font_family_is_shipped(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("//", "*", "#")):
            continue
        for match in _FONT_FAMILY.finditer(line):
            families = [f.strip().strip("'\"") for f in match.group(1).split(",")]
            bad = [f for f in families if f and f not in _SHIPPED_FAMILIES]
            if bad:
                out.append(Violation(path=path, line=number, key=bad[0],
                                     detail=f"font-family names an unshipped face: {bad[0]}"))
    return out


R_FONT_FAMILY_SHIPPED = Rule(
    name="font-family-is-shipped",
    citation=(
        "Five cockpit stylesheets asked for 'JetBrains Mono' and one for 'Cascadia Mono'; nothing "
        "registered either, so every machine fell back to a generic monospace and the mono columns "
        "were never what the author saw. A face the app names has to be one it ships."
    ),
    select=sources.cpp_sources,
    check=_check_font_family_is_shipped,
)
```
Append `R_FONT_FAMILY_SHIPPED,` to `ALL_RULES`.

- [ ] **Step 11: Run the sweeps; confirm the new rule is at zero**

Run: `$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests\test_sweeps.py -q`
Expected: pass, and the printed baseline does not list `font-family-is-shipped` (it carries no debt). If it lists violations, the family in the message was not renamed in step 9; fix that site, do not add a baseline.

- [ ] **Step 12: Full build, all tests, startup trace after**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
$env:SPELLVISION_STARTUP_TRACE = "1"
$p = Start-Process -FilePath .\build\Debug\SpellVision.exe -WorkingDirectory (Get-Location) -PassThru
Start-Sleep -Seconds 12; Stop-Process -Id $p.Id -Force
Get-Content .\build\ui_startup_trace.log -Tail 12
```
Expected: all ctest green (including `sv_fonts`), pytest green, and the `after show` timestamp within 100 ms of the step-1 baseline. Record both numbers in `progress.md`. If the delta exceeds 100 ms, move `registerBundledFonts()` to a `QTimer::singleShot(0, ...)` after `window.show()` in `main.cpp` and re-measure; the spec allows this.

- [ ] **Step 13: Commit**

```powershell
git add scripts/dev/fetch_plex_fonts.py qt_ui/fonts qt_ui/style/SvFonts.h qt_ui/style/SvFonts.cpp tests/cpp/test_sv_fonts.cpp qt_ui/main.cpp qt_ui/ThemeManager.h qt_ui/ThemeManager.cpp qt_ui/ImageGenerationPage.cpp qt_ui/ImageGenerationPage_catalog.cpp qt_ui/MainWindow.cpp CMakeLists.txt tests/sweeps/rules.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "feat(style): ship IBM Plex, register it at startup, and put the type ramp on three weights

The app ran on Segoe UI 12 px while five stylesheets asked for a mono face nothing
registered. Plex Sans and Plex Mono now ride under qt_ui/fonts (OFL 1.1), register
through SvFonts before the window is built, and the ramp uses the three weights Plex
ships. numericFont() gives the status bar tabular figures. A sweeps rule holds that
any font-family named in a stylesheet is one the app ships."
```

---

### Task 2: `SvStyle` — the proxy style, installed, refreshing on theme change, proven by pixels

**Files:**
- Create: `qt_ui/style/SvStyle.h`, `qt_ui/style/SvStyle.cpp`
- Create: `tests/cpp/test_sv_style.cpp`
- Modify: `qt_ui/main.cpp` (install the style right after `QApplication app(argc, argv);`, line 285)
- Modify: `qt_ui/ThemeManager.cpp:1090-1098` (`applyApplicationChrome`)
- Modify: `CMakeLists.txt` (core list, test registration, `WIN32_EXECUTABLE FALSE` list)

**Interfaces:**
- Consumes: `ThemeManager::instance().color(Color)`, `.radiusCard()`, `.radiusControl()`, `.style()`, `.styleUsesGlass(bool)`, `.font(Type)`.
- Produces: `namespace spellvision::style { enum class Role { None, Primary, Secondary, Tertiary, Danger, Chip, Tab, Rail }; enum class Surface { None, Plate, Panel, Inset, Glass }; class SvStyle : public QProxyStyle { static Role roleOf(const QWidget*); static Surface surfaceOf(const QWidget*); static QString roleName(Role); static QString surfaceName(Surface); static void refreshAll(); ... }; }`

- [ ] **Step 1: Write the failing test**

Create `tests/cpp/test_sv_style.cpp`:
```cpp
// One style draws every control. Before this, the primary button was defined seven times at two
// radii and three weights, and switching the Surface Style setting changed nothing on the cockpit.
// These assertions read pixels back from real widgets, because "the token is set" is not "the
// control is drawn".
#include <QtTest>
#include <QApplication>
#include <QImage>
#include <QPushButton>
#include <QToolButton>
#include <QFrame>

#include "ThemeManager.h"
#include "style/SvStyle.h"

using spellvision::style::Role;
using spellvision::style::Surface;
using spellvision::style::SvStyle;

namespace
{
QImage grab(QWidget &w, int width = 120, int height = 34)
{
    w.resize(width, height);
    w.setAttribute(Qt::WA_DontShowOnScreen);
    w.show();
    return w.grab().toImage().convertToFormat(QImage::Format_ARGB32);
}

bool near(const QColor &a, const QColor &b, int tolerance)
{
    return qAbs(a.red() - b.red()) <= tolerance && qAbs(a.green() - b.green()) <= tolerance
        && qAbs(a.blue() - b.blue()) <= tolerance;
}

QColor mix(const QColor &a, const QColor &b, qreal t)
{
    return QColor::fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                            a.greenF() + (b.greenF() - a.greenF()) * t,
                            a.blueF() + (b.blueF() - a.blueF()) * t);
}
} // namespace

class SvStyleTest : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase()
    {
        QApplication::setStyle(new SvStyle);
        ThemeManager::instance().setPreset(ThemeManager::Preset::ArcaneGlass);
        ThemeManager::instance().setStyle(ThemeManager::Style::RefinedGlass);
    }

    void the_installed_style_is_ours()
    {
        QVERIFY(qobject_cast<SvStyle *>(QApplication::style()) != nullptr);
    }

    void role_reads_the_property_first_then_the_object_name()
    {
        QPushButton a;
        a.setProperty("svRole", QStringLiteral("danger"));
        a.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&a), Role::Danger);
        QPushButton b;
        b.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&b), Role::Primary);
        QPushButton c;
        c.setObjectName(QStringLiteral("SecondaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&c), Role::Secondary);
        QFrame f;
        f.setObjectName(QStringLiteral("PromptCard"));
        QCOMPARE(SvStyle::surfaceOf(&f), Surface::Panel);
    }

    void primary_is_painted_from_the_accent()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton b; // no text: the centre column is fill, not glyph
        b.setProperty("svRole", QStringLiteral("primary"));
        const QImage img = grab(b);
        const QColor at80 = img.pixelColor(img.width() / 2, int(img.height() * 0.8));
        const QColor expected = mix(tm.color(ThemeManager::Color::AccentHover),
                                    tm.color(ThemeManager::Color::Accent), 0.8);
        QVERIFY2(near(at80, expected, 14),
                 qPrintable(at80.name() + QStringLiteral(" vs ") + expected.name()));
    }

    void secondary_is_the_raised_surface()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton b;
        b.setProperty("svRole", QStringLiteral("secondary"));
        const QImage img = grab(b);
        const QColor centre = img.pixelColor(img.width() / 2, img.height() / 2);
        QVERIFY2(near(centre, tm.color(ThemeManager::Color::Surface2), 3),
                 qPrintable(centre.name()));
    }

    void the_material_reaches_the_control()
    {
        auto &tm = ThemeManager::instance();
        QPushButton b;
        b.setProperty("svRole", QStringLiteral("secondary"));
        tm.setStyle(ThemeManager::Style::RefinedGlass);
        SvStyle::refreshAll();
        const QImage refined = grab(b);
        tm.setStyle(ThemeManager::Style::MatteInstrument);
        SvStyle::refreshAll();
        const QImage matte = grab(b);
        QVERIFY(refined != matte);
        QVERIFY(tm.radiusControl() == 4);
        tm.setStyle(ThemeManager::Style::RefinedGlass);
    }

    void numeric_font_has_tabular_figures()
    {
        const QFont f = ThemeManager::instance().numericFont();
        QVERIFY(f.featureTags().contains(QFont::Tag("tnum")));
    }
};

QTEST_MAIN(SvStyleTest)
#include "test_sv_style.moc"
```

- [ ] **Step 2: Register the test; build it; watch it fail to compile**

In `CMakeLists.txt` add after the `sv_fonts` block:
```cmake
# The proxy style is the one place controls are drawn. Pixel assertions, because the token being
# set is not the same as the control being painted from it.
qt_add_executable(test_sv_style tests/cpp/test_sv_style.cpp)
target_link_libraries(test_sv_style PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME sv_style COMMAND test_sv_style)
```
Add `test_sv_style` to the `WIN32_EXECUTABLE FALSE` list. Add to the core source list after `qt_ui/style/SvFonts.h`:
```cmake
    qt_ui/style/SvStyle.cpp
    qt_ui/style/SvStyle.h
```
Run: `cmake -S . -B build -G "Visual Studio 17 2022" -A x64; cmake --build build --config Debug --target test_sv_style`
Expected: compile error, `style/SvStyle.h` not found.

- [ ] **Step 3: Write `SvStyle.h`**

Create `qt_ui/style/SvStyle.h`:
```cpp
#pragma once

#include <QProxyStyle>
#include <QString>

class QPainter;
class QWidget;

namespace spellvision::style
{

// What a control IS, independent of what it is named. Read from the widget property "svRole"
// (a string: primary, secondary, tertiary, danger, chip, tab, rail); during the migration also
// inferred from today's object names so unmigrated pages draw correctly before their code changes.
enum class Role { None, Primary, Secondary, Tertiary, Danger, Chip, Tab, Rail };

// What a frame IS. Property "svSurface": plate, panel, inset, glass.
enum class Surface { None, Plate, Panel, Inset, Glass };

// The one place SpellVision draws a control. A QProxyStyle over Fusion that reads ThemeManager at
// draw time -- it caches nothing, so a preset or material switch is refreshAll() and a repaint.
class SvStyle final : public QProxyStyle
{
    Q_OBJECT
public:
    SvStyle();

    static Role roleOf(const QWidget *widget);
    static Surface surfaceOf(const QWidget *widget);
    static QString roleName(Role role);
    static QString surfaceName(Surface surface);

    // unpolish + polish + update over every widget. Connected to ThemeManager::themeChanged
    // through applyApplicationChrome().
    static void refreshAll();

    void polish(QWidget *widget) override;
    void drawPrimitive(PrimitiveElement element, const QStyleOption *option, QPainter *painter,
                       const QWidget *widget) const override;
    void drawControl(ControlElement element, const QStyleOption *option, QPainter *painter,
                     const QWidget *widget) const override;
    void drawComplexControl(ComplexControl control, const QStyleOptionComplex *option,
                            QPainter *painter, const QWidget *widget) const override;
    int pixelMetric(PixelMetric metric, const QStyleOption *option,
                    const QWidget *widget) const override;
    QSize sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contents,
                           const QWidget *widget) const override;
};

} // namespace spellvision::style
```

- [ ] **Step 4: Write `SvStyle.cpp`**

Create `qt_ui/style/SvStyle.cpp`:
```cpp
#include "style/SvStyle.h"

#include "ThemeManager.h"

#include <QAbstractButton>
#include <QAbstractScrollArea>
#include <QApplication>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QRadialGradient>
#include <QStyleFactory>
#include <QStyleOption>
#include <QStyleOptionButton>
#include <QStyleOptionComboBox>
#include <QStyleOptionFrame>
#include <QStyleOptionHeader>
#include <QStyleOptionProgressBar>
#include <QStyleOptionSlider>
#include <QStyleOptionSpinBox>
#include <QStyleOptionTab>
#include <QStyleOptionToolButton>
#include <QStyleOptionViewItem>
#include <QToolButton>
#include <QWidget>

namespace spellvision::style
{
namespace
{
using Color = ThemeManager::Color;

const ThemeManager &theme() { return ThemeManager::instance(); }
QColor tok(Color c) { return theme().color(c); }

QColor withAlpha(QColor c, qreal alpha)
{
    c.setAlphaF(alpha);
    return c;
}

QPainterPath rounded(const QRectF &rect, qreal radius)
{
    QPainterPath path;
    path.addRoundedRect(rect, radius, radius);
    return path;
}

// Inset by half a pixel so a 1 px stroke lands on whole pixels instead of smearing over two.
QRectF strokeRect(const QRect &rect) { return QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5); }

// The object-name map. Deleted at the end of the wave (Task 9) once every site sets its property.
Role roleFromObjectName(const QString &name)
{
    if (name == QLatin1String("PrimaryActionButton") || name == QLatin1String("PrimaryButton")
        || name == QLatin1String("DetailsPrimaryActionButton") || name.endsWith(QLatin1String("PrimaryBtn")))
        return Role::Primary;
    if (name == QLatin1String("SecondaryActionButton") || name == QLatin1String("SecondaryButton")
        || name == QLatin1String("HistoryActionButton") || name == QLatin1String("ModelsActionButton")
        || name == QLatin1String("DetailsSecondaryActionButton") || name == QLatin1String("DetailsActionButton")
        || name == QLatin1String("HomeModuleFrameButton") || name == QLatin1String("ModelCardInspectButton")
        || name.endsWith(QLatin1String("SecondaryBtn")))
        return Role::Secondary;
    if (name == QLatin1String("TertiaryActionButton"))
        return Role::Tertiary;
    if (name == QLatin1String("ModelsDangerButton"))
        return Role::Danger;
    if (name == QLatin1String("InspectorTab") || name == QLatin1String("TitleBarModeButton"))
        return Role::Tab;
    if (name == QLatin1String("ModelsViewToggle") || name == QLatin1String("NegativeToggleButton")
        || name == QLatin1String("AiDetailsToggle") || name == QLatin1String("OperatingPointButton"))
        return Role::Chip;
    if (name == QLatin1String("SideRailButton"))
        return Role::Rail;
    return Role::None;
}

Surface surfaceFromObjectName(const QString &name)
{
    if (name == QLatin1String("CanvasCard") || name == QLatin1String("PromptCard"))
        return Surface::Plate;
    if (name.endsWith(QLatin1String("Card")) || name.endsWith(QLatin1String("Surface")))
        return Surface::Panel;
    return Surface::None;
}

struct ButtonPaint
{
    QColor fill;
    QColor edge;
    QColor text;
    qreal radius = 6;
    bool gradient = false;
};

ButtonPaint buttonPaint(Role role, const QStyleOption *opt)
{
    const bool hover = opt->state & QStyle::State_MouseOver;
    const bool down = opt->state & QStyle::State_Sunken;
    const bool checked = opt->state & QStyle::State_On;
    const bool enabled = opt->state & QStyle::State_Enabled;
    ButtonPaint p;
    p.radius = theme().radiusControl();
    p.text = tok(enabled ? Color::TextHi : Color::TextDisabled);
    switch (role)
    {
    case Role::Primary:
        p.gradient = true;
        p.fill = tok(Color::Accent);
        p.edge = withAlpha(tok(Color::AccentTertiary), 0.35);
        p.text = enabled ? QColor(Qt::white) : withAlpha(QColor(Qt::white), 0.6);
        p.radius = theme().radiusCard();
        if (down) p.fill = tok(Color::AccentActive);
        break;
    case Role::Secondary:
        p.fill = tok(Color::Surface2);
        p.edge = tok(hover ? Color::BorderStrong : Color::Border);
        if (hover) p.fill = p.fill.lighter(106);
        if (down) p.fill = withAlpha(tok(Color::Accent), 0.22);
        break;
    case Role::Tertiary:
        p.fill = hover ? withAlpha(QColor(Qt::white), 0.04) : QColor(0, 0, 0, 0);
        p.edge = hover ? tok(Color::Border) : QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    case Role::Danger:
        p.fill = withAlpha(tok(Color::Error), hover ? 0.24 : 0.16);
        p.edge = withAlpha(tok(Color::Error), 0.6);
        p.text = tok(Color::Error);
        break;
    case Role::Chip:
        p.fill = checked ? withAlpha(QColor(Qt::white), 0.05) : tok(Color::Surface1);
        p.edge = tok(checked || hover ? Color::BorderStrong : Color::Border);
        p.text = tok(enabled ? (checked ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    case Role::Rail:
        p.fill = checked ? withAlpha(QColor(Qt::white), 0.05)
                         : (hover ? withAlpha(QColor(Qt::white), 0.04) : QColor(0, 0, 0, 0));
        p.edge = QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (checked || hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        p.radius = 8;
        break;
    case Role::Tab:
    case Role::None:
        p.fill = QColor(0, 0, 0, 0);
        p.edge = QColor(0, 0, 0, 0);
        p.text = tok(enabled ? (checked || hover ? Color::TextHi : Color::TextMid) : Color::TextDisabled);
        break;
    }
    return p;
}

void paintButtonPanel(Role role, const QStyleOption *opt, QPainter *painter)
{
    const ButtonPaint p = buttonPaint(role, opt);
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    const QRectF r = strokeRect(opt->rect);
    if (role == Role::Tab)
    {
        if (opt->state & QStyle::State_On)
        {
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            painter->drawRoundedRect(QRectF(r.left() + 6, r.bottom() - 2, r.width() - 12, 2), 1, 1);
        }
        painter->restore();
        return;
    }
    if (p.gradient)
    {
        QLinearGradient g(r.topLeft(), r.bottomLeft());
        g.setColorAt(0.0, tok(Color::AccentHover));
        g.setColorAt(1.0, p.fill);
        painter->setBrush(g);
    }
    else
    {
        painter->setBrush(p.fill);
    }
    painter->setPen(p.edge.alpha() > 0 ? QPen(p.edge, 1.0) : QPen(Qt::NoPen));
    painter->drawPath(rounded(r, p.radius));
    if (role == Role::Rail && (opt->state & QStyle::State_On))
    {
        painter->setPen(Qt::NoPen);
        painter->setBrush(tok(Color::Accent));
        painter->drawRoundedRect(QRectF(r.left(), r.top() + 10, 2, r.height() - 20), 1, 1);
    }
    painter->restore();
}

void paintSurface(Surface surface, const QStyleOption *opt, QPainter *painter)
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    const QRectF r = strokeRect(opt->rect);
    const qreal radius = surface == Surface::Inset ? theme().radiusControl() : theme().radiusCard();
    const QPainterPath path = rounded(r, radius);
    if (surface == Surface::Glass && theme().styleUsesGlass(true))
    {
        painter->setPen(Qt::NoPen);
        painter->setBrush(tok(Color::GlassFill));
        painter->drawPath(path);
        QRadialGradient glow(r.topLeft() + QPointF(r.width() * 0.2, 0), r.width() * 0.6);
        glow.setColorAt(0.0, tok(Color::GlassGlow));
        glow.setColorAt(1.0, QColor(0, 0, 0, 0));
        painter->setBrush(glow);
        painter->drawPath(path);
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->setBrush(Qt::NoBrush);
        painter->drawPath(path);
        painter->setPen(QPen(tok(Color::GlassHighlight), 1.0));
        painter->drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1));
        painter->restore();
        return;
    }
    const bool plate = surface == Surface::Plate || surface == Surface::Glass;
    painter->setBrush(tok(surface == Surface::Inset ? Color::Surface0 : Color::Surface1));
    painter->setPen(QPen(tok(surface == Surface::Inset ? Color::BorderSubtle : Color::Border), 1.0));
    painter->drawPath(path);
    if (plate)
    {
        painter->setPen(QPen(tok(Color::GlassHighlight), 1.0));
        painter->drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1));
    }
    painter->restore();
}

void paintFieldPanel(const QStyleOption *opt, QPainter *painter)
{
    const bool focus = opt->state & QStyle::State_HasFocus;
    const bool enabled = opt->state & QStyle::State_Enabled;
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setBrush(tok(Color::Surface0));
    painter->setPen(QPen(tok(focus ? Color::AccentHover : (enabled ? Color::Border : Color::BorderSubtle)), 1.0));
    painter->drawPath(rounded(strokeRect(opt->rect), theme().radiusControl()));
    painter->restore();
}

void paintChevron(QPainter *painter, const QRectF &box, bool up, const QColor &color)
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);
    painter->setPen(QPen(color, 1.8, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    const QPointF c = box.center();
    const qreal w = 3.5, h = up ? -2.0 : 2.0;
    painter->drawPolyline(QPolygonF({QPointF(c.x() - w, c.y() - h), QPointF(c.x(), c.y() + h), QPointF(c.x() + w, c.y() - h)}));
    painter->restore();
}

int roleMinHeight(Role role)
{
    switch (role)
    {
    case Role::Primary:   return 34;
    case Role::Secondary: return 30;
    case Role::Tertiary:  return 28;
    case Role::Danger:    return 30;
    case Role::Chip:      return 24;
    case Role::Tab:       return 34;
    case Role::Rail:      return 0;
    case Role::None:      return 28;
    }
    return 28;
}

int roleHPad(Role role)
{
    switch (role)
    {
    case Role::Primary:   return 18;
    case Role::Secondary: return 12;
    case Role::Tertiary:  return 10;
    case Role::Danger:    return 12;
    case Role::Chip:      return 8;
    case Role::Tab:       return 10;
    case Role::Rail:      return 0;
    case Role::None:      return 12;
    }
    return 12;
}
} // namespace

SvStyle::SvStyle() : QProxyStyle(QStyleFactory::create(QStringLiteral("Fusion"))) {}

Role SvStyle::roleOf(const QWidget *widget)
{
    if (!widget)
        return Role::None;
    const QString prop = widget->property("svRole").toString();
    if (prop == QLatin1String("primary")) return Role::Primary;
    if (prop == QLatin1String("secondary")) return Role::Secondary;
    if (prop == QLatin1String("tertiary")) return Role::Tertiary;
    if (prop == QLatin1String("danger")) return Role::Danger;
    if (prop == QLatin1String("chip")) return Role::Chip;
    if (prop == QLatin1String("tab")) return Role::Tab;
    if (prop == QLatin1String("rail")) return Role::Rail;
    return roleFromObjectName(widget->objectName());
}

Surface SvStyle::surfaceOf(const QWidget *widget)
{
    if (!widget)
        return Surface::None;
    const QString prop = widget->property("svSurface").toString();
    if (prop == QLatin1String("plate")) return Surface::Plate;
    if (prop == QLatin1String("panel")) return Surface::Panel;
    if (prop == QLatin1String("inset")) return Surface::Inset;
    if (prop == QLatin1String("glass")) return Surface::Glass;
    return surfaceFromObjectName(widget->objectName());
}

QString SvStyle::roleName(Role role)
{
    switch (role)
    {
    case Role::Primary:   return QStringLiteral("primary");
    case Role::Secondary: return QStringLiteral("secondary");
    case Role::Tertiary:  return QStringLiteral("tertiary");
    case Role::Danger:    return QStringLiteral("danger");
    case Role::Chip:      return QStringLiteral("chip");
    case Role::Tab:       return QStringLiteral("tab");
    case Role::Rail:      return QStringLiteral("rail");
    case Role::None:      break;
    }
    return QString();
}

QString SvStyle::surfaceName(Surface surface)
{
    switch (surface)
    {
    case Surface::Plate: return QStringLiteral("plate");
    case Surface::Panel: return QStringLiteral("panel");
    case Surface::Inset: return QStringLiteral("inset");
    case Surface::Glass: return QStringLiteral("glass");
    case Surface::None:  break;
    }
    return QString();
}

void SvStyle::refreshAll()
{
    if (!qApp)
        return;
    QStyle *st = QApplication::style();
    const QWidgetList widgets = QApplication::allWidgets();
    for (QWidget *w : widgets)
    {
        st->unpolish(w);
        st->polish(w);
        w->update();
    }
}

void SvStyle::polish(QWidget *widget)
{
    QProxyStyle::polish(widget);
    if (qobject_cast<QAbstractButton *>(widget) || surfaceOf(widget) != Surface::None)
        widget->setAttribute(Qt::WA_Hover, true);
}

void SvStyle::drawPrimitive(PrimitiveElement element, const QStyleOption *option, QPainter *painter,
                            const QWidget *widget) const
{
    switch (element)
    {
    case PE_PanelButtonCommand:
    case PE_PanelButtonTool:
    case PE_PanelButtonBevel:
        paintButtonPanel(roleOf(widget), option, painter);
        return;
    case PE_FrameFocusRect:
        return; // the ring is drawn by the control that has focus (buttons via State_HasFocus below)
    case PE_PanelLineEdit:
        paintFieldPanel(option, painter);
        return;
    case PE_FrameLineEdit:
        return;
    case PE_Frame:
    {
        const Surface surface = surfaceOf(widget);
        if (surface != Surface::None)
        {
            paintSurface(surface, option, painter);
            return;
        }
        if (qobject_cast<const QAbstractScrollArea *>(widget))
        {
            paintFieldPanel(option, painter);
            return;
        }
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->setBrush(Qt::NoBrush);
        painter->drawPath(rounded(strokeRect(option->rect), theme().radiusControl()));
        painter->restore();
        return;
    }
    case PE_IndicatorCheckBox:
    case PE_IndicatorRadioButton:
    {
        const bool on = option->state & State_On;
        const bool radio = element == PE_IndicatorRadioButton;
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        const QRectF r = strokeRect(option->rect);
        painter->setBrush(on ? tok(Color::Accent) : tok(Color::Surface0));
        painter->setPen(QPen(tok(on ? Color::Accent : Color::BorderStrong), 1.0));
        if (radio)
            painter->drawEllipse(r);
        else
            painter->drawPath(rounded(r, 4));
        if (on)
        {
            painter->setPen(QPen(Qt::white, 1.8, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
            painter->setBrush(Qt::NoBrush);
            if (radio)
            {
                painter->setBrush(Qt::white);
                painter->setPen(Qt::NoPen);
                painter->drawEllipse(r.center(), 3, 3);
            }
            else
            {
                const QPointF c = r.center();
                painter->drawPolyline(QPolygonF({QPointF(c.x() - 4, c.y()), QPointF(c.x() - 1, c.y() + 3), QPointF(c.x() + 4, c.y() - 3)}));
            }
        }
        painter->restore();
        return;
    }
    case PE_PanelItemViewItem:
    case PE_PanelItemViewRow:
    {
        const bool selected = option->state & State_Selected;
        const bool hover = option->state & State_MouseOver;
        if (!selected && !hover)
            return;
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setPen(Qt::NoPen);
        painter->setBrush(selected ? tok(Color::AccentSubtle) : withAlpha(QColor(Qt::white), 0.04));
        painter->drawPath(rounded(QRectF(option->rect), 4));
        painter->restore();
        return;
    }
    default:
        break;
    }
    QProxyStyle::drawPrimitive(element, option, painter, widget);
}

void SvStyle::drawControl(ControlElement element, const QStyleOption *option, QPainter *painter,
                          const QWidget *widget) const
{
    switch (element)
    {
    case CE_PushButtonBevel:
        paintButtonPanel(roleOf(widget), option, painter);
        if (option->state & State_HasFocus)
        {
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(QPen(tok(Color::AccentHover), 2.0));
            painter->setBrush(Qt::NoBrush);
            painter->drawPath(rounded(QRectF(option->rect).adjusted(1, 1, -1, -1), buttonPaint(roleOf(widget), option).radius));
            painter->restore();
        }
        return;
    case CE_PushButtonLabel:
    {
        if (const auto *btn = qstyleoption_cast<const QStyleOptionButton *>(option))
        {
            QStyleOptionButton copy = *btn;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(roleOf(widget), option).text);
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_ToolButtonLabel:
    {
        if (const auto *tb = qstyleoption_cast<const QStyleOptionToolButton *>(option))
        {
            QStyleOptionToolButton copy = *tb;
            copy.palette.setColor(QPalette::ButtonText, buttonPaint(roleOf(widget), option).text);
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_TabBarTabShape:
    {
        if (option->state & State_Selected)
        {
            painter->save();
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            const QRect r = option->rect;
            painter->drawRoundedRect(QRectF(r.left() + 6, r.bottom() - 2, r.width() - 12, 2), 1, 1);
            painter->restore();
        }
        return;
    }
    case CE_TabBarTabLabel:
    {
        if (const auto *tab = qstyleoption_cast<const QStyleOptionTab *>(option))
        {
            QStyleOptionTab copy = *tab;
            const bool on = option->state & State_Selected;
            copy.palette.setColor(QPalette::WindowText, tok(on ? Color::TextHi : Color::TextMid));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    case CE_ProgressBarGroove:
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing, true);
        painter->setBrush(tok(Color::Surface0));
        painter->setPen(QPen(tok(Color::BorderSubtle), 1.0));
        painter->drawPath(rounded(strokeRect(option->rect), 3));
        painter->restore();
        return;
    case CE_ProgressBarContents:
    {
        if (const auto *pb = qstyleoption_cast<const QStyleOptionProgressBar *>(option))
        {
            const int span = pb->maximum - pb->minimum;
            if (span <= 0)
                return; // indeterminate: GlowProgressBar paints its own phase loop
            const qreal frac = qreal(pb->progress - pb->minimum) / span;
            QRectF r = QRectF(option->rect).adjusted(1, 1, -1, -1);
            r.setWidth(r.width() * frac);
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(Color::Accent));
            painter->drawPath(rounded(r, 2));
            painter->restore();
            return;
        }
        break;
    }
    case CE_ProgressBarLabel:
        return;
    case CE_HeaderSection:
        painter->save();
        painter->fillRect(option->rect, tok(Color::Surface1));
        painter->setPen(QPen(tok(Color::Border), 1.0));
        painter->drawLine(option->rect.bottomLeft(), option->rect.bottomRight());
        painter->restore();
        return;
    case CE_HeaderLabel:
    {
        if (const auto *hd = qstyleoption_cast<const QStyleOptionHeader *>(option))
        {
            QStyleOptionHeader copy = *hd;
            copy.palette.setColor(QPalette::ButtonText, tok(Color::TextMid));
            QProxyStyle::drawControl(element, &copy, painter, widget);
            return;
        }
        break;
    }
    default:
        break;
    }
    QProxyStyle::drawControl(element, option, painter, widget);
}

void SvStyle::drawComplexControl(ComplexControl control, const QStyleOptionComplex *option,
                                 QPainter *painter, const QWidget *widget) const
{
    switch (control)
    {
    case CC_ComboBox:
    {
        if (const auto *cb = qstyleoption_cast<const QStyleOptionComboBox *>(option))
        {
            paintFieldPanel(option, painter);
            const QRect arrow = subControlRect(CC_ComboBox, cb, SC_ComboBoxArrow, widget);
            paintChevron(painter, QRectF(arrow), false, tok(Color::TextLo));
            if (!cb->editable)
            {
                // Label is drawn by CE_ComboBoxLabel through the base; only the panel and chevron are ours.
                QStyleOptionComboBox copy = *cb;
                copy.palette.setColor(QPalette::Text, tok(Color::TextHi));
                copy.palette.setColor(QPalette::ButtonText, tok(Color::TextHi));
                QProxyStyle::drawControl(CE_ComboBoxLabel, &copy, painter, widget);
            }
            return;
        }
        break;
    }
    case CC_SpinBox:
    {
        if (const auto *sb = qstyleoption_cast<const QStyleOptionSpinBox *>(option))
        {
            paintFieldPanel(option, painter);
            const QRect up = subControlRect(CC_SpinBox, sb, SC_SpinBoxUp, widget);
            const QRect down = subControlRect(CC_SpinBox, sb, SC_SpinBoxDown, widget);
            const bool upOn = sb->activeSubControls & SC_SpinBoxUp && (sb->state & State_Sunken);
            const bool downOn = sb->activeSubControls & SC_SpinBoxDown && (sb->state & State_Sunken);
            paintChevron(painter, QRectF(up), true, tok(upOn ? Color::TextHi : Color::TextLo));
            paintChevron(painter, QRectF(down), false, tok(downOn ? Color::TextHi : Color::TextLo));
            return;
        }
        break;
    }
    case CC_ScrollBar:
    {
        if (const auto *sb = qstyleoption_cast<const QStyleOptionSlider *>(option))
        {
            const QRect slider = subControlRect(CC_ScrollBar, sb, SC_ScrollBarSlider, widget);
            const bool hover = sb->state & State_MouseOver;
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            painter->setPen(Qt::NoPen);
            painter->setBrush(tok(hover ? Color::BorderStrong : Color::Border));
            const QRectF r = QRectF(slider).adjusted(2, 2, -2, -2);
            painter->drawRoundedRect(r, 3, 3);
            painter->restore();
            return;
        }
        break;
    }
    case CC_Slider:
    {
        if (const auto *sl = qstyleoption_cast<const QStyleOptionSlider *>(option))
        {
            const QRect groove = subControlRect(CC_Slider, sl, SC_SliderGroove, widget);
            const QRect handle = subControlRect(CC_Slider, sl, SC_SliderHandle, widget);
            painter->save();
            painter->setRenderHint(QPainter::Antialiasing, true);
            const bool horizontal = sl->orientation == Qt::Horizontal;
            QRectF track = horizontal ? QRectF(groove.left(), groove.center().y() - 2, groove.width(), 4)
                                      : QRectF(groove.center().x() - 2, groove.top(), 4, groove.height());
            painter->setPen(QPen(tok(Color::BorderSubtle), 1.0));
            painter->setBrush(tok(Color::Surface0));
            painter->drawRoundedRect(track, 2, 2);
            QRectF filled = track;
            if (horizontal)
                filled.setRight(handle.center().x());
            else
                filled.setTop(handle.center().y());
            painter->setPen(Qt::NoPen);
            painter->setBrush(withAlpha(tok(Color::Accent), 0.55));
            painter->drawRoundedRect(filled, 2, 2);
            painter->setBrush(tok(Color::Surface2));
            painter->setPen(QPen(tok(Color::BorderStrong), 1.0));
            painter->drawEllipse(QRectF(handle).adjusted(1, 1, -1, -1));
            painter->restore();
            return;
        }
        break;
    }
    case CC_ToolButton:
    {
        if (const auto *tb = qstyleoption_cast<const QStyleOptionToolButton *>(option))
        {
            paintButtonPanel(roleOf(widget), option, painter);
            QStyleOptionToolButton label = *tb;
            label.rect = subControlRect(CC_ToolButton, tb, SC_ToolButton, widget);
            drawControl(CE_ToolButtonLabel, &label, painter, widget);
            return;
        }
        break;
    }
    default:
        break;
    }
    QProxyStyle::drawComplexControl(control, option, painter, widget);
}

int SvStyle::pixelMetric(PixelMetric metric, const QStyleOption *option, const QWidget *widget) const
{
    switch (metric)
    {
    case PM_ScrollBarExtent:         return 8;
    case PM_ScrollBarSliderMin:      return 24;
    case PM_ButtonShiftHorizontal:   return 0;
    case PM_ButtonShiftVertical:     return 0;
    case PM_DefaultFrameWidth:       return 1;
    case PM_ButtonMargin:            return 12;
    case PM_IndicatorWidth:          return 16;
    case PM_IndicatorHeight:         return 16;
    case PM_ExclusiveIndicatorWidth: return 16;
    case PM_ExclusiveIndicatorHeight:return 16;
    case PM_TabBarTabVSpace:         return 8;
    case PM_SliderThickness:         return 16;
    case PM_SliderLength:            return 14;
    case PM_FocusFrameHMargin:       return 2;
    case PM_ButtonIconSize:          return 16;
    default:                         break;
    }
    return QProxyStyle::pixelMetric(metric, option, widget);
}

QSize SvStyle::sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contents,
                                const QWidget *widget) const
{
    QSize size = QProxyStyle::sizeFromContents(type, option, contents, widget);
    switch (type)
    {
    case CT_PushButton:
    {
        const Role role = roleOf(widget);
        size.setHeight(qMax(size.height(), roleMinHeight(role)));
        size.setWidth(contents.width() + 2 * roleHPad(role));
        return size;
    }
    case CT_ToolButton:
    {
        const Role role = roleOf(widget);
        if (role == Role::Rail)
            return size; // the rail tile is fixed 56x48 by MainWindow; do not fight it
        size.setHeight(qMax(size.height(), roleMinHeight(role)));
        size.setWidth(contents.width() + 2 * roleHPad(role));
        return size;
    }
    case CT_LineEdit:
    case CT_ComboBox:
    case CT_SpinBox:
        size.setHeight(qMax(size.height(), 28));
        return size;
    default:
        break;
    }
    return size;
}

} // namespace spellvision::style
```

- [ ] **Step 5: Install the style and wire the refresh**

In `qt_ui/main.cpp`, add `#include "style/SvStyle.h"` and directly after `QApplication app(argc, argv);` (line 285) add:
```cpp
    // One style draws every control. Installed before any widget exists so nothing is ever
    // polished by the platform default; ThemeManager::applyApplicationChrome() refreshes it.
    QApplication::setStyle(new spellvision::style::SvStyle);
```
In `qt_ui/ThemeManager.cpp`, add `#include "style/SvStyle.h"` and change `applyApplicationChrome` (line 1090) to:
```cpp
void ThemeManager::applyApplicationChrome() const
{
    // Push the themed palette + overlay sheet onto qApp, then re-polish every widget so the proxy
    // style repaints from the new tokens. Called once at startup (from main) and auto-reapplied on
    // themeChanged (wired in the ctor).
    if (!qApp)
        return;
    qApp->setPalette(buildPalette());
    qApp->setStyleSheet(applicationOverlayStyleSheet());
    spellvision::style::SvStyle::refreshAll();
}
```

- [ ] **Step 6: Build and run the style test**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug --target test_sv_style
ctest --test-dir build -C Debug -R sv_style --output-on-failure
```
Expected: `sv_style ... Passed`, six cases. If `primary_is_painted_from_the_accent` fails with two hex values, the gradient stops are wrong way round in `paintButtonPanel` (top must be `AccentHover`). If `the_material_reaches_the_control` fails, `refreshAll()` did not repolish; confirm `QApplication::style()` is the `SvStyle` instance.

- [ ] **Step 7: Build the app, run everything, look**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
. .\scripts\dev\uia\svdrive.ps1
$p = Start-Process .\build\Debug\SpellVision.exe -WorkingDirectory (Get-Location) -PassThru; Start-Sleep 10
Set-SvState -State Restore -W 1600 -H 1000 | Out-Null; Select-SvRail T2I | Out-Null; Start-Sleep 2
Save-SvShot -Name "kit-step1-t2i" | Out-Null; Select-SvRail Home | Out-Null; Start-Sleep 2; Save-SvShot -Name "kit-step1-home" | Out-Null
Stop-Process -Id $p.Id -Force
```
Expected: ctest and pytest green; the matrix reports no QSS parse warnings. Open `scripts/dev/uia/shots/kit-step1-t2i.png`: the page still shows its stylesheet look (rules still exist), scrollbars are now 8 px thin, combos have a stroked chevron. Nothing must be unreadable; if any text is invisible, the palette role that text reads is wrong for that control — fix in `buttonPaint`, not with a stylesheet.

- [ ] **Step 8: Commit**

```powershell
git add qt_ui/style/SvStyle.h qt_ui/style/SvStyle.cpp tests/cpp/test_sv_style.cpp qt_ui/main.cpp qt_ui/ThemeManager.cpp CMakeLists.txt
git commit -m "feat(style): SvStyle, one proxy style that draws every control from the tokens

A QProxyStyle over Fusion reads ThemeManager at draw time: buttons by role,
frames by surface, edits, combos, spins, scrollbars, sliders, indicators,
progress, tabs, item rows and headers. Roles travel as widget properties, with a
temporary object-name map so unmigrated pages draw correctly. Theme and material
changes re-polish every widget through applyApplicationChrome. Pixel tests prove
the accent reaches the primary button and the material reaches a control."
```

---

### Task 3: `SvKit` factories and the five structural ratchets at their baselines

**Files:**
- Create: `qt_ui/style/SvKit.h`, `qt_ui/style/SvKit.cpp`
- Modify: `CMakeLists.txt` (core list after `SvStyle.h`)
- Modify: `tests/sweeps/rules.py` (five rules + `ALL_RULES`), `tests/sweeps/exemptions.py` (`BASELINE` entries and two `EXEMPT` entries)
- Modify: `tests/cpp/test_sv_style.cpp` (one more case, using the factory)

**Interfaces:**
- Consumes: `Role`, `Surface`, `SvStyle::roleName`, `SvStyle::surfaceName` from Task 2.
- Produces: `namespace spellvision::kit { QPushButton *button(style::Role, const QString &text, const QString &objectName, QWidget *parent = nullptr); QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent = nullptr); QFrame *card(style::Surface, const QString &objectName, QWidget *parent = nullptr); QWidget *row(const QString &label, QWidget *control, QWidget *parent = nullptr); void setRole(QWidget *, style::Role); void setSurface(QFrame *, style::Surface); }`

- [ ] **Step 1: Add the failing factory test**

Append to `tests/cpp/test_sv_style.cpp` (inside the class, before `QTEST_MAIN`), and add `#include "style/SvKit.h"` at the top:
```cpp
    void the_factory_sets_the_role_and_keeps_the_name()
    {
        QPushButton *b = spellvision::kit::button(Role::Primary, QStringLiteral("Generate"),
                                                  QStringLiteral("PrimaryActionButton"));
        QCOMPARE(b->objectName(), QStringLiteral("PrimaryActionButton"));
        QCOMPARE(b->property("svRole").toString(), QStringLiteral("primary"));
        QCOMPARE(SvStyle::roleOf(b), Role::Primary);
        spellvision::kit::setRole(b, Role::Secondary);
        QCOMPARE(SvStyle::roleOf(b), Role::Secondary);
        QFrame *f = spellvision::kit::card(Surface::Glass, QStringLiteral("CanvasCard"));
        QCOMPARE(f->frameShape(), QFrame::StyledPanel);
        QCOMPARE(SvStyle::surfaceOf(f), Surface::Glass);
        delete b;
        delete f;
    }
```
Run: `cmake --build build --config Debug --target test_sv_style` — Expected: compile error, `style/SvKit.h` not found.

- [ ] **Step 2: Write `SvKit`**

Create `qt_ui/style/SvKit.h`:
```cpp
#pragma once

#include "style/SvStyle.h"

#include <QString>

class QFrame;
class QPushButton;
class QToolButton;
class QWidget;

namespace spellvision::kit
{

// Factories that say what a widget IS. Each sets the role or surface property SvStyle reads and
// keeps the object name the caller asks for, because object names are load-bearing (UI Automation,
// the responsive matrix, eleven pytest ratchets). No layouts, no copy, no page knowledge here.
QPushButton *button(style::Role role, const QString &text, const QString &objectName, QWidget *parent = nullptr);
QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent = nullptr); // checkable
QFrame *card(style::Surface surface, const QString &objectName, QWidget *parent = nullptr);   // StyledPanel
QWidget *row(const QString &label, QWidget *control, QWidget *parent = nullptr);              // label left, control right, hairline below

// For widgets that already exist. Re-polishes so the change paints immediately.
void setRole(QWidget *widget, style::Role role);
void setSurface(QFrame *frame, style::Surface surface);

} // namespace spellvision::kit
```

Create `qt_ui/style/SvKit.cpp`:
```cpp
#include "style/SvKit.h"

#include "ThemeManager.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QStyle>
#include <QToolButton>
#include <QVBoxLayout>

namespace spellvision::kit
{
namespace
{
void repolish(QWidget *widget)
{
    if (!widget)
        return;
    widget->style()->unpolish(widget);
    widget->style()->polish(widget);
    widget->update();
}
} // namespace

QPushButton *button(style::Role role, const QString &text, const QString &objectName, QWidget *parent)
{
    auto *b = new QPushButton(text, parent);
    b->setObjectName(objectName);
    b->setProperty("svRole", style::SvStyle::roleName(role));
    b->setCursor(Qt::PointingHandCursor);
    return b;
}

QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent)
{
    auto *c = new QToolButton(parent);
    c->setText(text);
    c->setObjectName(objectName);
    c->setCheckable(true);
    c->setAutoRaise(false);
    c->setProperty("svRole", style::SvStyle::roleName(style::Role::Chip));
    c->setCursor(Qt::PointingHandCursor);
    return c;
}

QFrame *card(style::Surface surface, const QString &objectName, QWidget *parent)
{
    auto *f = new QFrame(parent);
    f->setObjectName(objectName);
    f->setFrameShape(QFrame::StyledPanel);
    f->setFrameShadow(QFrame::Plain);
    f->setProperty("svSurface", style::SvStyle::surfaceName(surface));
    return f;
}

QWidget *row(const QString &label, QWidget *control, QWidget *parent)
{
    const auto &theme = ThemeManager::instance();
    auto *host = new QWidget(parent);
    auto *column = new QVBoxLayout(host);
    column->setContentsMargins(0, 0, 0, 0);
    column->setSpacing(0);
    auto *line = new QHBoxLayout();
    line->setContentsMargins(0, theme.spacing(ThemeManager::Spacing::Tight), 0, theme.spacing(ThemeManager::Spacing::Tight));
    line->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));
    auto *caption = new QLabel(label, host);
    caption->setObjectName(QStringLiteral("KitRowLabel"));
    line->addWidget(caption, 0);
    line->addStretch(1);
    if (control)
    {
        control->setParent(host);
        line->addWidget(control, 0);
    }
    column->addLayout(line);
    auto *rule = new QFrame(host);
    rule->setObjectName(QStringLiteral("KitRowRule"));
    rule->setFrameShape(QFrame::HLine);
    rule->setFixedHeight(1);
    column->addWidget(rule);
    return host;
}

void setRole(QWidget *widget, style::Role role)
{
    if (!widget)
        return;
    widget->setProperty("svRole", style::SvStyle::roleName(role));
    repolish(widget);
}

void setSurface(QFrame *frame, style::Surface surface)
{
    if (!frame)
        return;
    frame->setFrameShape(QFrame::StyledPanel);
    frame->setFrameShadow(QFrame::Plain);
    frame->setProperty("svSurface", style::SvStyle::surfaceName(surface));
    repolish(frame);
}

} // namespace spellvision::kit
```
Add to the CMake core list after `qt_ui/style/SvStyle.h`:
```cmake
    qt_ui/style/SvKit.cpp
    qt_ui/style/SvKit.h
```
Note: `ThemeManager::spacing(Spacing)` exists (`ThemeManager.h:110-118` declares the enum; the accessor is used 281 times in the tree as `theme.spacing(ThemeManager::Spacing::Tight)`). If the accessor name differs, grep `qt_ui/ThemeManager.h` for `Spacing token` and use that name.

- [ ] **Step 3: Build and run the style test**

Run: `cmake -S . -B build -G "Visual Studio 17 2022" -A x64; cmake --build build --config Debug --target test_sv_style; ctest --test-dir build -C Debug -R sv_style --output-on-failure`
Expected: seven cases pass.

- [ ] **Step 4: Add the five structural rules**

In `tests/sweeps/rules.py`, before `ALL_RULES`, add:
```python
# --- R23-R27: the stylesheet retreat (spec docs/superpowers/specs/2026-09-07-foundation-kit-design.md §2.4) ---

_OWNED_TYPES = (
    "QPushButton|QToolButton|QLineEdit|QTextEdit|QPlainTextEdit|QComboBox|QSpinBox|QDoubleSpinBox|"
    "QCheckBox|QRadioButton|QSlider|QScrollBar|QProgressBar|QTabBar|QHeaderView|QAbstractItemView|"
    "QTreeView|QListView|QTableView|QListWidget|QTreeWidget|QTableWidget"
)
_QSS_RULE = re.compile(
    r"((?:" + _OWNED_TYPES + r")|#\w*(?:Button|Btn|Card|Toggle|Tab|Surface)\b)([^{};]*)\{([^}]*)\}",
    re.S,
)
_DRAWS = re.compile(r"\b(background|background-color|border|border-color|border-radius|color)\s*:")
_LITERAL_RADIUS = re.compile(r"border-radius\s*:\s*\d+px")
_PRIMARY_RULE = re.compile(r"#PrimaryActionButton\s*\{")
_OFF_RAMP_WEIGHT = re.compile(r"font-weight\s*:\s*(700|800|900)\b|QFont::(Bold|ExtraBold|Black)\b|setBold\(\s*true\s*\)")
_LITERAL_SPACING = re.compile(r"setSpacing\(\s*([1-9]\d*)\s*\)")
_LITERAL_MARGINS = re.compile(r"setContentsMargins\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _check_qss_draws_a_control(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for match in _QSS_RULE.finditer(text):
        if not _DRAWS.search(match.group(3)):
            continue
        selector = (match.group(1) + match.group(2)).replace('"', "").replace("\n", " ").strip()
        selector = " ".join(selector.split())[:60]
        out.append(Violation(path=path, line=_line_of(text, match.start()), key=selector,
                             detail=f"stylesheet draws a control the style owns: {selector}"))
    return out


R_QSS_DRAWS_A_CONTROL = Rule(
    name="qss-draws-a-control",
    citation=(
        "The primary button was defined seven times at two radii and three weights, and the Surface "
        "Style setting changed nothing on the cockpit because 133 literal radii never read the "
        "material. SvStyle draws every control; a stylesheet may set spacing, never paint."
    ),
    select=sources.cpp_sources,
    check=_check_qss_draws_a_control,
)


def _check_qss_literal_radius(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("//", "*", "#")):
            continue
        for match in _LITERAL_RADIUS.finditer(line):
            out.append(Violation(path=path, line=number, key=match.group(0).replace(" ", ""),
                                 detail=f"literal radius: {match.group(0)}"))
    return out


R_QSS_LITERAL_RADIUS = Rule(
    name="qss-literal-radius",
    citation=(
        "Three radius systems disagreed (10/6, 26/20/16/13, and thirteen per-call literals). A "
        "radius is part of the material and comes from radiusCard()/radiusControl(), never a number."
    ),
    select=sources.cpp_sources,
    check=_check_qss_literal_radius,
)


def _check_primary_defined_once(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if _PRIMARY_RULE.search(line):
            out.append(Violation(path=path, line=number, key="PrimaryActionButton",
                                 detail="a second definition of the primary button"))
    return out


R_PRIMARY_DEFINED_ONCE = Rule(
    name="primary-button-defined-once",
    citation=(
        "Dataset, Gen3D and Inspiration each redefined #PrimaryActionButton as a flat borderless "
        "variant under the same object name ThemeManager styles. One hero, one definition."
    ),
    select=sources.cpp_sources,
    check=_check_primary_defined_once,
)


def _check_weight_on_ramp(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("//", "*", "#")):
            continue
        for match in _OFF_RAMP_WEIGHT.finditer(line):
            out.append(Violation(path=path, line=number, key=match.group(0).replace(" ", ""),
                                 detail=f"weight off the 400/500/600 ramp: {match.group(0)}"))
    return out


R_WEIGHT_ON_RAMP = Rule(
    name="type-weight-on-ramp",
    citation=(
        "Weights 700, 800 and 900 leaked past the ramp (a 900 on a rule no widget carries). Plex "
        "ships 400, 500 and 600; the ramp is those three and fontCss() is how a sheet asks for one."
    ),
    select=sources.cpp_sources,
    check=_check_weight_on_ramp,
)


def _check_literal_spacing(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("//", "*", "#")):
            continue
        for match in _LITERAL_SPACING.finditer(line):
            out.append(Violation(path=path, line=number, key=f"setSpacing({match.group(1)})",
                                 detail=f"literal spacing: {match.group(0)}"))
        for match in _LITERAL_MARGINS.finditer(line):
            if any(int(g) for g in match.groups()):
                out.append(Violation(path=path, line=number, key=f"setContentsMargins({','.join(match.groups())})",
                                     detail=f"literal margins: {match.group(0)}"))
    return out


R_LITERAL_SPACING = Rule(
    name="spacing-literal",
    citation=(
        "281 Spacing:: token reads coexist with ~88 literal setSpacing and ~53 non-zero literal "
        "margins, six of the literal values matching no token. Literal zero stays literal; every "
        "other spacing decision reads the scale."
    ),
    select=sources.cpp_sources,
    check=_check_literal_spacing,
)
```
Append to `ALL_RULES`: `R_QSS_DRAWS_A_CONTROL, R_QSS_LITERAL_RADIUS, R_PRIMARY_DEFINED_ONCE, R_WEIGHT_ON_RAMP, R_LITERAL_SPACING,`.

- [ ] **Step 5: Measure, then write the baselines and the two exemptions**

Run this to print per-file counts for the new rules:
```powershell
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -c "import collections; from tests.sweeps import rules, sources
for name in ['qss-draws-a-control','qss-literal-radius','primary-button-defined-once','type-weight-on-ramp','spacing-literal']:
    rule = next(r for r in rules.ALL_RULES if r.name == name)
    counts = collections.Counter(sources.relative(v.path) for v in rule.run())
    print(name); [print(f'        \"{f}\": {n},') for f, n in sorted(counts.items())]"
```
In `tests/sweeps/exemptions.py`, add to `EXEMPT`:
```python
    "qss-draws-a-control": {
        "qt_ui/ThemeManager.cpp::QComboBox QAbstractItemView": (
            "The combo popup is a top-level window that escapes the MainWindow cascade and the "
            "proxy style's item-view paint does not reach a popup's selection colour on every "
            "platform; the qApp overlay sheet is the one place it can be themed."
        ),
        "qt_ui/ThemeManager.cpp::QMessageBox QPushButton, QInputDialog QPushButton": (
            "Message-box buttons are created by Qt inside a dialog that escapes the cascade; the "
            "overlay sheet is the only hook that reaches them before they show."
        ),
    },
    "primary-button-defined-once": {
        "qt_ui/ThemeManager.cpp::PrimaryActionButton": (
            "The one definition, kept for spacing only after Task 4; the paint lives in SvStyle."
        ),
    },
```
and to `BASELINE`, one block per rule, pasting exactly the printed `"file": n,` lines under each name:
```python
    "qss-draws-a-control": {
        # pasted from the measure command
    },
    "qss-literal-radius": {
        # pasted
    },
    "type-weight-on-ramp": {
        # pasted
    },
    "spacing-literal": {
        # pasted
    },
```
(`primary-button-defined-once` needs no baseline once the three page-local definitions are counted: paste those three files with `1` each; they go to zero in Tasks 6 and 8.)

- [ ] **Step 6: Run the sweeps and the full ratchet subset**

Run: `$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests\test_sweeps.py -q`
Expected: pass; the printed baseline now lists the five new rules with their totals. `test_every_rule_states_why_it_exists` and `test_every_exemption_states_a_reason` pass because each has a citation and each exemption a reason.

- [ ] **Step 7: Commit**

```powershell
git add qt_ui/style/SvKit.h qt_ui/style/SvKit.cpp tests/cpp/test_sv_style.cpp CMakeLists.txt tests/sweeps/rules.py tests/sweeps/exemptions.py
git commit -m "feat(style): SvKit factories and five ratchets that make the stylesheet retreat one-way

button/chip/card/row set the role or surface property SvStyle reads and keep the
object name the caller asks for. Five sweeps rules count what the retreat removes:
stylesheet rules that draw an owned control, literal radii, second definitions of
the primary button, weights off the 400/500/600 ramp, and literal spacing. Each
starts at today's measured baseline and may only fall."
```

---

### Task 4: Shell retreat — title bar, rail, status bar, drawer, and the `@token@` conversion

**Files:**
- Create: `scripts/dev/uia/Capture-SvThemes.ps1`, `scripts/dev/uia/compare_captures.py`
- Modify: `qt_ui/ThemeManager.cpp:1100-1408` (`shellStyleSheet`), `:1259` (`#SideRailBadge`), `:1505-1513`
- Modify: `qt_ui/MainWindow.cpp:569-603` (`createRailButton`), `:1676` (rail scroll sheet), `:4073-4086` (queue overlay surface sheet), `:4488-4490` (queue label failure style)
- Modify: `qt_ui/CustomTitleBar.cpp:250-256, 274-298` (buttons get roles)
- Modify: `tests/sweeps/exemptions.py` (lower baselines)

**Interfaces:**
- Consumes: `spellvision::kit::setRole`, `setSurface` (Task 3); `Role::Rail`, `Role::Tab`, `Role::Tertiary`.
- Produces: `Capture-SvThemes.ps1 -Prefix <p>` writes `scripts/dev/uia/shots/<p>-<preset>-<material>-{t2i,home}.png` for the presets and materials it is given and restores the persisted preset; `compare_captures.py a.png b.png` prints the fraction of pixels that differ by more than 8/255 in any channel.

- [ ] **Step 1: Write the capture and compare tools**

Create `scripts/dev/uia/compare_captures.py`:
```python
"""Fraction of differing pixels between two captures. Used to prove a material change is visible."""
import sys
from PIL import Image, ImageChops

a = Image.open(sys.argv[1]).convert("RGB")
b = Image.open(sys.argv[2]).convert("RGB")
if a.size != b.size:
    print(f"size mismatch {a.size} vs {b.size}")
    sys.exit(2)
diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 8 else 0)
changed = sum(1 for v in diff.getdata() if v)
print(f"{changed / (diff.width * diff.height):.4f}")
```
Create `scripts/dev/uia/Capture-SvThemes.ps1`:
```powershell
# Captures T2I and Home for each (preset, material) pair, one app launch per pair, and restores the
# persisted preset afterwards. Preset indices: 0 Arcane Glass, 1 Obsidian Studio, 2 Neon Forge,
# 3 Ivory Holograph, 4 Ember. Material: 0 Refined Glass, 1 Matte Instrument, 2 Hybrid.
param(
    [string]$Prefix = "themes",
    [int[]]$Presets = @(0, 3),
    [int[]]$Materials = @(0, 1, 2)
)
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot "svdrive.ps1")
$key = "HKCU:\Software\DarkDuck\SpellVision\appearance"
$orig = Get-ItemProperty $key
try {
    foreach ($p in $Presets) {
        foreach ($m in $Materials) {
            Set-ItemProperty $key -Name themePreset -Value ([int]$p)
            Set-ItemProperty $key -Name surfaceStyle -Value ([int]$m)
            $proc = Start-Process -FilePath (Join-Path $root "build\Debug\SpellVision.exe") -WorkingDirectory $root -PassThru
            $deadline = (Get-Date).AddSeconds(45); $hwnd = 0
            while ((Get-Date) -lt $deadline) { try { $hwnd = Get-SvHwnd } catch { $hwnd = 0 }; if ($hwnd) { break }; Start-Sleep -Milliseconds 500 }
            if (-not $hwnd) { Write-Warning "no window for preset $p material $m"; Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; continue }
            Start-Sleep -Seconds 4
            Set-SvState -State Restore -W 1600 -H 1000 | Out-Null; Start-Sleep -Milliseconds 1500
            Select-SvRail T2I | Out-Null; Start-Sleep -Milliseconds 1500; Save-SvShot -Name "$Prefix-p$p-m$m-t2i" | Out-Null
            Select-SvRail Home | Out-Null; Start-Sleep -Milliseconds 2200; Save-SvShot -Name "$Prefix-p$p-m$m-home" | Out-Null
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 1500
        }
    }
} finally {
    Set-ItemProperty $key -Name themePreset -Value ([int]$orig.themePreset)
    Set-ItemProperty $key -Name surfaceStyle -Value ([int]$orig.surfaceStyle)
    "restored themePreset=$($orig.themePreset) surfaceStyle=$($orig.surfaceStyle)"
}
```

- [ ] **Step 2: List the shell's drawing rules**

Run:
```powershell
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -c "from tests.sweeps import rules
r = next(x for x in rules.ALL_RULES if x.name=='qss-draws-a-control')
[print(v) for v in r.run() if 'ThemeManager.cpp' in str(v.path)]"
```
Expected: one line per selector in `shellStyleSheet`, `settingsStyleSheet`, `homePageStyleSheet`, `imageGenerationStyleSheet` with a line number. This list is the worklist for this task (shell) and Task 5 (cockpit); the settings and home sheets are Task 8.

- [ ] **Step 3: Convert `shellStyleSheet` to `@token@` before deleting anything**

In `qt_ui/ThemeManager.cpp` inside `shellStyleSheet()` (1100-1408): for each `%N` placeholder in the sheet body, introduce a named token. The mechanical recipe: read the comment beside each `.arg(...)` value (e.g. `// %60 inspector checked border`), replace every `%60` in the sheet text with `@inspCheckedBorder@`, and move that value from the positional `.arg(...)` list to a `.replace(QLatin1String("@inspCheckedBorder@"), <same expression>)` line in the existing `.replace` chain. Do all 62, then delete the `.arg(` call entirely. Build after this step alone:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue; cmake --build build --config Debug; ctest --test-dir build -C Debug -R responsive_matrix --output-on-failure
```
Expected: matrix passes (its QSS-parse clause would fail on a stray `%N` or an unresolved `@token@`, and `assertNoUnresolvedTokens` aborts the Debug build if a token is left). Commit this conversion on its own:
```powershell
git add qt_ui/ThemeManager.cpp
git commit -m "refactor(theme): shellStyleSheet reads named tokens, not positional arguments

A 62-argument QString::arg resolves by lowest placeholder number, so deleting a
rule renumbered every later colour (the 2026-07-25 lavender void). Every value is
now a named @token@; a rule can be deleted without moving another."
```

- [ ] **Step 4: Delete the shell's drawing rules and set roles**

For each worklist line from step 2 that is inside `shellStyleSheet` (lines 1100-1408): if the rule's body sets only `padding`, `margin`, `min-height`, `min-width`, `spacing`, `font-size`, `font-weight` via `@label@`-style tokens — keep it. Otherwise remove the `background`, `border`, `border-radius`, `color` declarations from that rule (delete the whole rule when nothing remains). Delete the `QLabel#SideRailBadge` rule at line 1259 outright (no widget carries that name). Do the same for the per-widget sheets at `MainWindow.cpp:1676` (rail scroll area: keep only `QScrollArea{border:0;background:transparent}` if the style would otherwise draw a field panel behind the rail — it will, because `QScrollArea` is a `QAbstractScrollArea`; keep exactly that one rule) and `MainWindow.cpp:4073-4086` (queue overlay surface: replace the sheet with `spellvision::kit::setSurface(overlaySurface, spellvision::style::Surface::Panel);` and delete the `themeChanged` re-style lambda at 4086 if it only re-set that sheet). Leave `MainWindow.cpp:4488-4490` (the queue label failure style) as is: it colours a label, not a control the style owns.

Set roles at the creation sites:
- `qt_ui/MainWindow.cpp:569-603` `createRailButton`: after `button->setObjectName(QStringLiteral("SideRailButton"))` add `button->setProperty("svRole", QStringLiteral("rail"));` (include `"style/SvKit.h"` at the top of `MainWindow.cpp`).
- `qt_ui/CustomTitleBar.cpp:274-298`: after `simpleButton_` and `advancedButton_` are created add `spellvision::kit::setRole(simpleButton_, spellvision::style::Role::Tab); spellvision::kit::setRole(advancedButton_, spellvision::style::Role::Tab);`.
- `qt_ui/CustomTitleBar.cpp:250-256`: for `layoutButton_`, `primarySidebarButton_`, `bottomPanelButton_`, `secondarySidebarButton_`, `minButton_`, `maxButton_` add `spellvision::kit::setRole(<name>, spellvision::style::Role::Tertiary);`; for `closeButton_` add `spellvision::kit::setRole(closeButton_, spellvision::style::Role::Danger);` and keep the `#TitleBarCloseButton:hover` rule at `ThemeManager.cpp:1188` only if `Role::Danger`'s hover reads too weak by eye; otherwise delete it (it is a literal hex the ratchet counts).
- Status bar: `bottomQueueLabel_` and friends are labels; nothing to set. The `GlowProgressBar` keeps its own paint.

- [ ] **Step 5: Build, matrix, sweeps, capture**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix kit-step2 -Presets 0,3 -Materials 0,1
.\.venv\Scripts\python.exe scripts\dev\uia\compare_captures.py scripts\dev\uia\shots\kit-step2-p0-m0-t2i.png scripts\dev\uia\shots\kit-step2-p0-m1-t2i.png
```
Expected: pytest fails only in `test_rule_matches_its_baseline` with "violations DROPPED" for `ThemeManager.cpp` under `qss-draws-a-control` and `qss-literal-radius`; lower those numbers in `exemptions.py` to the reported values and re-run until green. The compare prints a fraction; record it in `progress.md` (it will still be small because the cockpit sheet is untouched; the shell chrome alone changes). Open `kit-step2-p0-m0-t2i.png` and `kit-step2-p3-m0-t2i.png`: the title bar buttons, the rail's active tile (5 % wash plus the 2 px accent bar) and the drawer must read correctly in both Arcane Glass and Ivory Holograph. If the rail label text is invisible on Ivory, `Role::Rail` in `buttonPaint` must read `TextMid` for the unchecked state (it does) and the palette's `ButtonText` must not be overridden by a leftover `#SideRailButton { color: ... }` rule; delete that rule.

- [ ] **Step 6: Commit**

```powershell
git add qt_ui/ThemeManager.cpp qt_ui/MainWindow.cpp qt_ui/CustomTitleBar.cpp scripts/dev/uia/Capture-SvThemes.ps1 scripts/dev/uia/compare_captures.py tests/sweeps/exemptions.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "refactor(shell): the shell sheet stops drawing controls; the rail and title bar carry roles

Title-bar toggles are tabs, its icon buttons tertiary, close is danger, and the
rail tile is the new rail role with its wash and accent bar painted by SvStyle.
The dead SideRailBadge rule is gone. Capture-SvThemes.ps1 and compare_captures.py
are the tools that will prove the material axis reaches the cockpit."
```

---

### Task 5: Cockpit retreat — the cockpit sheet, the four per-widget sheets, the glass plate, and the dashboard radius constants

**Files:**
- Modify: `qt_ui/ThemeManager.cpp:1431-1616` (`imageGenerationStyleSheet`)
- Modify: `qt_ui/ImageGenerationPage.cpp` (per-widget sheets at 581, 726, 1184 and the negative-toggle / dropzone / segmented dynamic stylers found by `grep -n "setStyleSheet" qt_ui/ImageGenerationPage.cpp`), `:1067` (`CanvasCard`), `:600` (`PromptCard`)
- Modify: `qt_ui/ImageGenerationPage_catalog.cpp:822, 876` and any `setStyleSheet` it holds
- Modify: `qt_ui/generation/CockpitInspector.cpp:52` (`InspectorTab` buttons), `:93` (readiness strip)
- Modify: `qt_ui/DashboardSurfaceTokens.h:39-43`, `qt_ui/DashboardSurfaceTokens.cpp:123-127`, `qt_ui/assets/ModelCardDelegate.cpp:71,105,140,158`, `qt_ui/DashboardMetricChip.cpp:90`, `qt_ui/DashboardPreviewPlate.cpp:108`, `qt_ui/DashboardGlassPanel.h:51`
- Modify: `tests/sweeps/exemptions.py`

**Interfaces:**
- Consumes: `kit::setRole`, `kit::setSurface`, `Surface::Glass`, `Surface::Plate`, `Surface::Panel`, `Role::Tab`, `Role::Chip`, `Role::Secondary`, `Role::Primary`.
- Produces: `DashboardSurfaceTokens` no longer declares `radiusHero`, `radiusPanel`, `radiusInset`, `radiusChip`; readers call `ThemeManager::instance().radiusCard()` (hero, panel) or `radiusControl()` (inset, chip).

- [ ] **Step 1: Worklist**

Run the step-2 command from Task 4 filtered to `ImageGenerationPage`, `CockpitInspector` and the `imageGenerationStyleSheet` line range (1431-1616 of `ThemeManager.cpp`), plus `grep -n "setStyleSheet" qt_ui/ImageGenerationPage*.cpp qt_ui/generation/CockpitInspector.cpp`. Expected: the 18 literal radii in the cockpit sheet, the four per-widget sheets in the page, and the inspector's tab/readiness sheets.

- [ ] **Step 2: Convert `imageGenerationStyleSheet` to `@token@` and delete its drawing rules**

Apply the Task 4 step-3 recipe to `imageGenerationStyleSheet` (its `.arg` list resolves at 1608-1614; it has ~46 arguments): name every placeholder, move to the `.replace` chain, delete the `.arg` call, build, then delete every declaration the worklist names (background, border, border-radius, color) from rules on owned types and on `#...Card`/`#...Button` selectors, keeping padding/margin/min-height. Add `assertNoUnresolvedTokens(sheet, QStringLiteral("imageGenerationStyleSheet"));` before its `return`.

- [ ] **Step 3: Give the cockpit its surfaces and roles**

In `qt_ui/ImageGenerationPage.cpp`:
- After `auto *canvasCard = createCard(QStringLiteral("CanvasCard"));` (line 1067) add `spellvision::kit::setSurface(canvasCard, spellvision::style::Surface::Glass);`
- After `auto *promptCard = createCard(QStringLiteral("PromptCard"));` (line 600) add `spellvision::kit::setSurface(promptCard, spellvision::style::Surface::Plate);`
- For every other `createCard(QStringLiteral("<Name>"))` in the file, add `spellvision::kit::setSurface(<var>, spellvision::style::Surface::Panel);` on the next line.
- Replace each per-widget `setStyleSheet(...)` that draws (the negative toggle open/closed styler, the dropzone loaded/unloaded styler, the segmented control) with a role: negative toggle → `kit::setRole(negativeToggle_, Role::Chip)` and use `setChecked(open)` for the open state instead of restyling; dropzone → `kit::setSurface(dropzone, Surface::Inset)`; segmented buttons → `Role::Chip` with `setCheckable(true)`. Keep any sheet that sets only font-family for the mono readouts (those are the five sites renamed in Task 1).
- Add `#include "style/SvKit.h"` at the top. Because the page file is 26 lines under its ceiling, count lines after the edit: `(Get-Content qt_ui\ImageGenerationPage.cpp).Count` must print ≤ 3000. Sheets deleted should leave it lower than before; if not, move the negative-toggle and dropzone role calls into a new helper `applyCockpitRoles(ImageGenerationPage &)` in `qt_ui/ImageGenerationPage_catalog.cpp` and call it once from `buildUi`.

In `qt_ui/generation/CockpitInspector.cpp:52` after `btn->setObjectName(QStringLiteral("InspectorTab"));` add `btn->setProperty("svRole", QStringLiteral("tab"));`. At `:93` after the readiness frame's object name add `spellvision::kit::setSurface(readiness, spellvision::style::Surface::Inset);`. Delete any `setStyleSheet` in the file that draws.

- [ ] **Step 4: Delete the dashboard radius constants**

In `qt_ui/DashboardSurfaceTokens.h:39-43` delete `radiusHero`, `radiusPanel`, `radiusInset`, `radiusChip` (keep `strokeWidth`). In `DashboardSurfaceTokens.cpp:123-127` delete their assignments. At each reader replace: `tokens.radiusHero` and `tokens.radiusPanel` → `ThemeManager::instance().radiusCard()`; `tokens.radiusInset` and `tokens.radiusChip` → `ThemeManager::instance().radiusControl()` (`ModelCardDelegate.cpp:71,105,140,158`, `DashboardMetricChip.cpp:90`, `DashboardPreviewPlate.cpp:108`). In `DashboardGlassPanel.h:51` change `cornerRadius_ = 12` to read `ThemeManager::instance().radiusCard()` at construction (initialise in the ctor). Build: `cmake --build build --config Debug` — expected: no reference to a deleted member remains (the compiler lists any you missed).

- [ ] **Step 5: Build, matrix, sweeps, capture, and the pixel-diff gate**

Run the Task 4 step-5 block with `-Prefix kit-step3`. Lower the baselines the sweeps report. Expected: `compare_captures.py` between `kit-step3-p0-m0-t2i.png` and `kit-step3-p0-m1-t2i.png` prints **≥ 0.0100** (spec §2.8 item 3). Open both: the Refined Glass plate shows the glass fill, glow and top highlight; the Matte plate is opaque with a heavier hairline and tighter corners (6 vs 10). If the fraction is below 0.01, `paintSurface` is not being reached for `CanvasCard`: confirm `frameShape()` is `StyledPanel` (`setSurface` sets it) and that no leftover `#CanvasCard { background: ... }` rule remains in the cockpit sheet. Also confirm the T2I page line count is ≤ 3000 and record the compare fraction in `progress.md`.

- [ ] **Step 6: Commit**

```powershell
git add qt_ui/ThemeManager.cpp qt_ui/ImageGenerationPage.cpp qt_ui/ImageGenerationPage_catalog.cpp qt_ui/generation/CockpitInspector.cpp qt_ui/DashboardSurfaceTokens.h qt_ui/DashboardSurfaceTokens.cpp qt_ui/assets/ModelCardDelegate.cpp qt_ui/DashboardMetricChip.cpp qt_ui/DashboardPreviewPlate.cpp qt_ui/DashboardGlassPanel.h qt_ui/DashboardGlassPanel.cpp tests/sweeps/exemptions.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "refactor(cockpit): the cockpit is drawn by the style; the canvas is a glass plate; one radius pair

The cockpit sheet keeps spacing and loses its 18 literal radii; the prompt card is
a plate, every other card a panel, the canvas the glass hero Hybrid never had. The
dashboard's private radius set (26/20/16/13) is deleted and its readers use the
material's two radii. Refined Glass and Matte Instrument cockpit captures now
differ by <fraction> of pixels; they were identical."
```
(Replace `<fraction>` with the measured number.)

---

### Task 6: Library retreat — Models, Flows, History

**Files:**
- Modify: `qt_ui/ModelManagerPage.cpp` (sheet at `:1336`, 21 object-name rules; buttons `ModelsActionButton`, `ModelsDangerButton`, `ModelsViewToggle`, cards `ModelsSummaryCard`, `ModelsDetailsCard`)
- Modify: `qt_ui/WorkflowLibraryPage.cpp` (sheet at `:1939`, 7 rules; `PrimaryActionButton` on Import stays named)
- Modify: `qt_ui/T2VHistoryPage.cpp` (sheet at `:1632`, 16 rules; `HistoryActionButton`, `HistoryHeroCard`, `HistoryDetailsCard`, `HistoryContentCard`)
- Modify: `tests/sweeps/exemptions.py`

**Interfaces:**
- Consumes: `kit::setRole`, `kit::setSurface`, `kit::button`, `kit::chip`.

- [ ] **Step 1: Worklist**

Run the Task 4 step-2 command filtered to the three files. Expected: every selector that draws, with its line.

- [ ] **Step 2: Retreat each sheet and set roles**

For each of the three files: open the page's sheet at the cited line; delete `background`, `border`, `border-radius` and `color` declarations from rules on owned types and on `#…Button`/`#…Card`/`#…Toggle` selectors; keep padding, margin and min sizes. At each button's creation site (grep `setObjectName(QStringLiteral("ModelsActionButton"))` and the others), add the matching role: `ModelsActionButton` → `Role::Secondary`; `ModelsDangerButton` → `Role::Danger`; `ModelsViewToggle` → `Role::Chip` (they are checkable already); `HistoryActionButton` → `Role::Secondary`; Workflows' Import button (`PrimaryActionButton`) → `Role::Primary`. At each card's creation site, `kit::setSurface(card, Surface::Panel)`; the History hero card → `Surface::Plate`. Add `#include "style/SvKit.h"` to each file. Where a page defines its own `#PrimaryActionButton { ... }`, delete that rule (the `primary-button-defined-once` ratchet lists it).

- [ ] **Step 3: Build, matrix, sweeps, capture**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
. .\scripts\dev\uia\svdrive.ps1
$p = Start-Process .\build\Debug\SpellVision.exe -WorkingDirectory (Get-Location) -PassThru; Start-Sleep 10
Set-SvState -State Restore -W 1600 -H 1000 | Out-Null
foreach ($r in @("Models","Flows","History")) { Select-SvRail $r | Out-Null; Start-Sleep 2; Save-SvShot -Name ("kit-step4-" + $r.ToLower()) | Out-Null }
Set-SvState -State HalfW | Out-Null; Start-Sleep 2; Save-SvShot -Name "kit-step4-history-halfw" | Out-Null
Stop-Process -Id $p.Id -Force
```
Expected: matrix green (History details at Half W is one of its cells; the four full-word buttons must still fit, and they will because `sizeFromContents` pads secondary buttons at 12 px, less than the old sheet's 14). Lower the reported baselines. Open the four captures: buttons read as secondary (raised surface, hairline), the danger button reads red-on-tint, cards have one hairline and the material's radius.

- [ ] **Step 4: Commit**

```powershell
git add qt_ui/ModelManagerPage.cpp qt_ui/WorkflowLibraryPage.cpp qt_ui/T2VHistoryPage.cpp tests/sweeps/exemptions.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "refactor(library): Models, Flows and History stop drawing their own controls

Three page sheets keep their spacing and lose their paint; their buttons and cards
carry roles the style draws. The Workflows Import button is the first page-local
primary definition to go."
```

---

### Task 7: Studio retreat — Character, Comic, Concept

**Files:**
- Modify: `qt_ui/studios/CharacterStudioPage.cpp` (sheet 2327-2392, 21 rules; `CharStudioPrimaryBtn`, `CharStudioSecondaryBtn`; `setCornerRadius` at 362, 420, 459, 675, 925)
- Modify: `qt_ui/studios/ComicStudioPage.cpp` (sheet 1490-1533, 26 rules; `ComicPrimaryBtn`, `ComicSecondaryBtn`; `setCornerRadius` at 300, 352, 574, 601, 693)
- Modify: `qt_ui/studios/ConceptReferencePage.cpp` (sheet ~949-981, 18 rules; `ConceptRefPrimaryBtn`, `ConceptRefSecondaryBtn`; the dead `font-weight: 800` at 952; `setCornerRadius` at 211, 252, 458, 476)
- Modify: `tests/sweeps/exemptions.py`

**Interfaces:**
- Consumes: `kit::setRole`, `kit::setSurface`; `ThemeManager::radiusCard()`.

- [ ] **Step 1: Worklist**

Run the Task 4 step-2 command filtered to `qt_ui/studios`. Also `grep -n "setCornerRadius" qt_ui/studios/*.cpp` — expected: the fourteen sites listed above.

- [ ] **Step 2: Retreat, roles, radii**

In each studio: delete drawing declarations from the sheet's rules on owned types and on `#…Btn`/`#…Card` selectors, keep spacing; at each `setObjectName(QStringLiteral("<Studio>PrimaryBtn"))` add `kit::setRole(<var>, Role::Primary)`; at each `…SecondaryBtn` add `Role::Secondary`; for every `DashboardGlassPanel` whose `setCornerRadius(N)` is called, replace `N` with `ThemeManager::instance().radiusCard()` (they are all hero or panel surfaces; none is an inset). Remove the literal `font-weight: 800;` at `ConceptReferencePage.cpp:952` (it was already dead: the `@label@` token that follows it wins). Add the include to each file.

- [ ] **Step 3: Build, matrix, sweeps, capture**

Run the Task 6 step-3 block with the rail names `Char`, `Comic`, `Concept` and prefix `kit-step5`. Expected: matrix green (Comic Advanced ON and Character concept are cells); baselines lowered; `type-weight-on-ramp` drops by one for Concept. Open the three captures: the studio primary buttons now match Generate exactly (same gradient, same radius, same weight), which is the point.

- [ ] **Step 4: Commit**

```powershell
git add qt_ui/studios/CharacterStudioPage.cpp qt_ui/studios/ComicStudioPage.cpp qt_ui/studios/ConceptReferencePage.cpp tests/sweeps/exemptions.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "refactor(studios): the three studios use the one primary and the material's radius

CharStudioPrimaryBtn, ComicPrimaryBtn and ConceptRefPrimaryBtn were three more
definitions of Generate at radius 10 and weight 600; they now carry the primary
role and look like it. Fourteen setCornerRadius literals read radiusCard()."
```

---

### Task 8: Remaining retreat — Home, Settings, Dataset, Train, Gen3D, Inspiration, Runtime, ModePage, dialogs

**Files:**
- Modify: `qt_ui/HomeDashboardPage.cpp` (sheet at `:1493`, 18 rules; `setCornerRadius` at 108), `qt_ui/HomeModuleFrame.cpp:47` (24/20 → `radiusCard()`)
- Modify: `qt_ui/ThemeManager.cpp` (`settingsStyleSheet` 1639-1706, `homePageStyleSheet` 1619-1637, `modePageStyleSheet` 1775-1778, the settings preview helpers 1708-1773; `#PrimaryActionButton`/`#SecondaryActionButton`/`#TertiaryActionButton` at 1505-1513 keep spacing only)
- Modify: `qt_ui/DatasetGenerationPage.cpp:225-238`, `qt_ui/Gen3DPage.cpp:299-311`, `qt_ui/InspirationPage.cpp:262-275` (delete the page-local `#PrimaryActionButton` rules; buttons get `Role::Primary`)
- Modify: `qt_ui/TrainPage.cpp:113`, `qt_ui/ManagerPage.cpp`, `qt_ui/ModePage.cpp:58`, `qt_ui/workflows/ModelResolutionDialog.cpp:269`, `qt_ui/workflows/CivitaiVariantDialog.cpp:212`, `qt_ui/CommandPaletteDialog.cpp:170`, `qt_ui/SettingsPage.cpp`
- Modify: `tests/sweeps/exemptions.py`

**Interfaces:**
- Consumes: `kit::setRole`, `kit::setSurface`, `ThemeManager::radiusCard()`, `fontCss(Type)`.

- [ ] **Step 1: Worklist**

Run the Task 4 step-2 command with no filter; the remaining violations are this task's list. Also `grep -rn "font-size: 15px\|font-size: 13px" qt_ui/workflows qt_ui/CommandPaletteDialog.cpp` (two off-ramp sizes: replace `font-size: 15px; font-weight: 600;` with `@subtitle@` resolved through `fontCss(Type::Subtitle)` and the 13 px with `@body@`).

- [ ] **Step 2: Retreat everything left**

Same recipe as Tasks 6 and 7 in every listed file: delete drawing declarations, keep spacing, set roles at creation sites (`Role::Primary` for the three page-local primaries, `Role::Secondary` for `HomeModuleFrameButton`, `ModelCardInspectButton`, dialog action buttons; `Surface::Panel` for `SettingsCard`, `DatasetCard`, `TrainCard`, `G3Card`, `ModeSectionCard`, `ModelResolutionCard`; `Surface::Plate` for `ModeHeroCard`, `HomeModuleSurface`). `HomeModuleFrame.cpp:47` and `HomeDashboardPage.cpp:108` both read `radiusCard()` now (the two Home surfaces agree). In `ThemeManager.cpp` the `#PrimaryActionButton`, `#SecondaryActionButton`, `#TertiaryActionButton` rules at 1505-1513 lose every declaration except padding and min-height; the `color: #FFFFFF` at 1507 goes (the style paints the label white). Keep `applicationOverlayStyleSheet` (its two owned-type selectors are exempt).

- [ ] **Step 3: Build, matrix, sweeps, capture the lot**

Run:
```powershell
Stop-Process -Name SpellVision -ErrorAction SilentlyContinue
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix kit-step6 -Presets 0,1,2,3,4 -Materials 0,1,2
```
Expected: `qss-draws-a-control` 0 outside the two exemptions, `qss-literal-radius` 0 outside the overlay sheet (add an `EXEMPT` entry per overlay selector with the reason "escapes the window cascade; the only hook is the qApp sheet"), `primary-button-defined-once` 0, `type-weight-on-ramp` 0, `font-family-is-shipped` 0, `spacing-literal` at its Task 3 baseline (this wave does not migrate spacing; the rule only holds the line). Thirty captures land; open the five `-m0-home` captures: five presets, one skeleton, and now the buttons and cards are identical in form across them.

- [ ] **Step 4: Commit**

```powershell
git add qt_ui tests/sweeps/exemptions.py .superpowers/sdd/PLAN_SPLUS_2026-09-07/progress.md
git commit -m "refactor(pages): every remaining sheet keeps spacing only; the style draws the rest

Home, Settings, Dataset, Train, Gen3D, Inspiration, Runtime, ModePage and the
three dialogs. The last three page-local definitions of the primary button are
gone, the two Home surfaces agree on a radius, and the ratchets that count
drawing rules, literal radii, off-ramp weights and unshipped fonts read zero."
```

---

### Task 9: Close the wave — delete the object-name map, gate on the criteria, record the outcome

**Files:**
- Modify: `qt_ui/style/SvStyle.cpp` (delete `roleFromObjectName`, `surfaceFromObjectName`, and their two call sites; `roleOf`/`surfaceOf` return `None` when the property is unset)
- Modify: `tests/cpp/test_sv_style.cpp` (`role_reads_the_property_first_then_the_object_name` becomes `role_reads_the_property_only`: the `PrimaryActionButton`-named button with no property must yield `Role::None`)
- Modify: `docs/superpowers/specs/2026-09-07-foundation-kit-design.md` (status line → "shipped <date>, commits <range>")
- Modify: `.superpowers/sdd/2026-09-07-foundation-kit/progress.md` (the plan wrote `PLAN_SPLUS_2026-09-07` here; the directory that exists, and that the session-orientation hook reads, is the one named after the plan)

- [ ] **Step 1: Update the test first**

Replace the `role_reads_the_property_first_then_the_object_name` case with:
```cpp
    void role_reads_the_property_only()
    {
        QPushButton a;
        a.setProperty("svRole", QStringLiteral("danger"));
        a.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&a), Role::Danger);
        QPushButton b;
        b.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&b), Role::None);
        QFrame f;
        f.setObjectName(QStringLiteral("PromptCard"));
        QCOMPARE(SvStyle::surfaceOf(&f), Surface::None);
    }
```
Run: `cmake --build build --config Debug --target test_sv_style; ctest --test-dir build -C Debug -R sv_style --output-on-failure` — Expected: FAIL on the `Role::None` line (the map still answers).

- [ ] **Step 2: Delete the map**

In `qt_ui/style/SvStyle.cpp` delete `roleFromObjectName` and `surfaceFromObjectName` and change the last line of `roleOf` to `return Role::None;` and of `surfaceOf` to `return Surface::None;`. Build the app and run the whole app once: any button that lost its look is a site that never set its property; add the role at that site (the capture set from Task 8 is the reference). Run: `ctest --test-dir build -C Debug --output-on-failure` — Expected: all green.

- [ ] **Step 2b: the checked chip has to read on a light preset**

Task 7 measured a selected chip against an unselected one on Ivory Holograph and found four
levels of separation: `Role::Chip`'s checked fill is `withAlpha(QColor(Qt::white), 0.05)`, a
white veil, which is a dark-theme idiom that does nothing over a near-white `Surface1`. Only the
`BorderStrong` hairline carried selection, where the retreated sheets had used an accent border
*and* an accent tint. The owner runs Ivory Holograph with the Hybrid material, so this is the
everyday view, and Comic's panel board is where it costs the most: four plates, one selected,
indistinguishable.

Write the failing test first, in `tests/cpp/test_sv_style.cpp`, immediately BEFORE
`the_test_does_not_touch_the_real_settings` (that case must stay the last slot):

```cpp
    void the_checked_chip_reads_on_every_preset()
    {
        auto &tm = ThemeManager::instance();
        const auto centreOf = [](bool checked) {
            QPushButton b; // no text: the centre column is fill, not glyph
            b.setProperty("svRole", QStringLiteral("chip"));
            b.setCheckable(true);
            b.setChecked(checked);
            const QImage img = grab(b);
            return img.pixelColor(img.width() / 2, img.height() / 2);
        };
        for (const auto preset : {ThemeManager::Preset::ArcaneGlass,
                                  ThemeManager::Preset::IvoryHolograph})
        {
            tm.setPreset(preset);
            SvStyle::refreshAll();
            const QColor on = centreOf(true);
            const QColor off = centreOf(false);
            const int distance = qAbs(on.red() - off.red()) + qAbs(on.green() - off.green())
                + qAbs(on.blue() - off.blue());
            QVERIFY2(distance >= 24,
                     qPrintable(QStringLiteral("preset %1: %2 vs %3, distance %4")
                                    .arg(int(preset))
                                    .arg(on.name(), off.name())
                                    .arg(distance)));
        }
        tm.setPreset(ThemeManager::Preset::ArcaneGlass);
        SvStyle::refreshAll();
    }
```

Run: `cmake --build build --config Debug --target test_sv_style; ctest --test-dir build -C Debug -R sv_style --output-on-failure` — Expected: FAIL on the Ivory Holograph pass, with a distance around 4.

Then fix the role in `qt_ui/style/SvStyle.cpp` (`buttonPaint`, the `case Role::Chip:` arm).

> **SUPERSEDED — do not execute the version this step first printed.** It set
> `p.fill = checked ? tok(Color::AccentSubtle) : tok(Color::Surface1);`, and `AccentSubtle` is
> TRANSLUCENT (7–10 % on four presets, 15.7 % on Ember). Painted raw, the backdrop decides how much
> selection is worth: measured 17 on Arcane Glass against this step's own gate of 24, so the code
> below fails the test above it. The shipped version composites the tint over the chip's opaque
> plate first, which is what makes the distance the same on a card, in an inset track and on the
> bare window. `over()` is the helper it needs, and its precondition — an OPAQUE base — is why the
> blend is written out rather than handed to `QPainter`.

```cpp
    case Role::Chip:
        // A checked chip has to read on a light ground as well as a dark one. A white veil is a
        // dark-theme idiom -- over Ivory Holograph's near-white Surface1 it moved the plate by
        // four levels, which is not a signal. AccentSubtle is a HUE shift rather than a luminance
        // one, so it survives both grounds, and selection is then carried by two channels: the
        // tint and an accent edge, instead of one hairline.
        p.fill = checked ? over(tok(Color::Surface1), tok(Color::AccentSubtle)) : tok(Color::Surface1);
        p.edge = checked ? tok(Color::Accent) : tok(hover ? Color::BorderStrong : Color::Border);
        break;
```

The `if (lift && checked) p.text = tok(Color::TextHi);` line goes with it, and that deletion is
the point rather than a tidy-up. It has never reached a live label: `ThemeManager` always installs
the qApp overlay sheet, so `QStyleSheetStyle` draws every button label out of the widget palette,
and `SvStyle::polish` writes only the REST colour from `labelColorFor(role, blocked, enabled)` —
a function with no `checked` parameter. `polish` also runs once, at construction, so it could not
track a toggle even if it wanted to. Making the label follow the check state would mean a new
mechanism (repolishing on `toggled`, or a palette write from an event filter); the tint plus the
accent edge make it unnecessary, and leaving the dead line in place would keep a third channel
that looks like it works. Two channels that reach the screen beat three where one is a fiction.

Run the same two commands — Expected: PASS on both presets. The unit test measures fill, which
is exactly the channel that survives the overlay sheet, so a pass here is a pass in the app — but
confirm it in the app anyway, because that is the claim being made. Then `ctest --test-dir build -C Debug
--output-on-failure` (all green) and re-capture Comic on the owner's preset:
`.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix kit-chip -Presets 3 -Materials 2`, drive to the
`Comic` rail item, and confirm by eye that the selected panel plate is now distinguishable from
the other three. Record the measured distance for both presets in `progress.md`.

Leave `Role::Rail` and `Role::Tab` alone: the rail's checked item carries an accent bar and the
tab an underline, both drawn separately, so neither depends on the veil for its signal.

- [ ] **Step 2c: make the third material exist**

Task 8's captures exposed a product defect that no ratchet could see: on T2I, **Refined Glass and
Hybrid differ by 0.0006 of pixels** (0.0007 and 0.0009 on the other presets, 0.0105 on Ember)
against 0.1192 for Refined vs Matte. One of the three Surface Style options is invisible on the
app's main page, and the owner runs it. Spec §2.8's third criterion — a material change reaches
the control — passed only because it was measured on the pair that does differ.

The material system is not the problem; the call site is. `ThemeManager::styleUsesGlass(bool
heroSurface)` already answers exactly right — Refined true always, Matte false always, **Hybrid
`heroSurface`** — and `applyStyleToColorTokens`'s comment says the choice is "decided per panel by
`styleUsesGlass()`". But `paintSurface` (`qt_ui/style/SvStyle.cpp:275`) takes the glass branch only
when `surface == Surface::Glass`, and then asks `styleUsesGlass(true)`. A hardcoded `true` is the
one argument for which Refined and Hybrid agree, so the question is asked in the only way that
cannot distinguish them, and every other surface takes the flat branch under all three materials.
What is left between Refined and Hybrid is a 2 px radius and `Border` at 1.25 alpha.

Let the surface ask the question honestly. In `paintSurface`, replace the branch condition:

```cpp
    // Which surfaces are "hero" is the material axis's whole hinge: Refined glasses everything,
    // Matte glasses nothing, and Hybrid glasses the hero surfaces only -- which is what the
    // material is FOR. Asking with a hardcoded true was asking the one question whose answer is
    // the same for Refined and Hybrid, which is why the two rendered within 0.0006 of each other.
    // Inset stays out of it: a recessed field is not a lit surface in any material.
    const bool hero = surface == Surface::Glass || surface == Surface::Plate;
    if (surface != Surface::Inset && theme().styleUsesGlass(hero))
```

in place of `if (surface == Surface::Glass && theme().styleUsesGlass(true))`. Nothing else in the
function changes: the glass body already reads `GlassFill`, `GlassGlow`, `GlassHighlight` and
`Border` from tokens, and Matte drives all three glass tokens to transparent, so a Matte surface
that now enters the branch paints a solid fill and a hairline — the same thing the flat branch gave
it. Verify that claim rather than assume it: the Matte capture must not move.

Write the failing test first, in `tests/cpp/test_sv_style.cpp`, before
`the_test_does_not_touch_the_real_settings`:

```cpp
    void every_material_reaches_a_panel()
    {
        auto &tm = ThemeManager::instance();
        const auto panelImage = [](ThemeManager::Style style) {
            ThemeManager::instance().setStyle(style);
            SvStyle::refreshAll();
            QFrame f;
            f.setFrameShape(QFrame::StyledPanel);
            f.setProperty("svSurface", QStringLiteral("panel"));
            return grab(f, 160, 80);
        };
        const QImage refined = panelImage(ThemeManager::Style::RefinedGlass);
        const QImage hybrid = panelImage(ThemeManager::Style::Hybrid);
        const QImage matte = panelImage(ThemeManager::Style::MatteInstrument);
        QVERIFY2(refined != hybrid, "Refined and Hybrid paint a panel identically");
        QVERIFY2(hybrid != matte, "Hybrid and Matte paint a panel identically");
        tm.setStyle(ThemeManager::Style::RefinedGlass);
        SvStyle::refreshAll();
    }
```

Run: `cmake --build build --config Debug --target test_sv_style; ctest --test-dir build -C Debug -R
sv_style --output-on-failure` — Expected: FAIL on the first QVERIFY2 (a panel is flat in both).
Then make the change and re-run — Expected: PASS.

Then measure it where the defect was found, and record all three numbers in `progress.md`:

```powershell
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix kit-mat -Presets 3 -Materials 0,1,2
.\.venv\Scripts\python.exe scripts\dev\uia\compare_captures.py scripts\dev\uia\shots\kit-mat-p3-m0-t2i.png scripts\dev\uia\shots\kit-mat-p3-m2-t2i.png
.\.venv\Scripts\python.exe scripts\dev\uia\compare_captures.py scripts\dev\uia\shots\kit-mat-p3-m0-t2i.png scripts\dev\uia\shots\kit-mat-p3-m1-t2i.png
```

Expected: Refined vs **Hybrid** now at or above **0.0100**, the same gate §2.8 sets for the
material axis, and Refined vs Matte still around 0.119. If Hybrid clears the gate only because
Refined got glassier, say so — that is a real answer, and Refined glassing every panel is what
"Refined Glass" has always claimed to be. Open the three captures: all three materials must remain
legible, and the accent glow must stay the only coloured light source.

- [ ] **Step 3: The success criteria, measured**

Run:
```powershell
$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q
.\scripts\dev\uia\Capture-SvThemes.ps1 -Prefix kit-final -Presets 0,3 -Materials 0,1,2
.\.venv\Scripts\python.exe scripts\dev\uia\compare_captures.py scripts\dev\uia\shots\kit-final-p0-m0-t2i.png scripts\dev\uia\shots\kit-final-p0-m1-t2i.png
$env:SPELLVISION_STARTUP_TRACE = "1"; $p = Start-Process .\build\Debug\SpellVision.exe -WorkingDirectory (Get-Location) -PassThru; Start-Sleep 12; Stop-Process -Id $p.Id -Force; Get-Content .\build\ui_startup_trace.log -Tail 12
```
Expected, written into `progress.md` as a table against spec §2.8: (1) `qss-draws-a-control` 0 outside the overlay; (2) `primary-button-defined-once` 0, `qss-literal-radius` 0 outside the overlay, `font-family-is-shipped` 0, `type-weight-on-ramp` 0; (3) compare fraction ≥ 0.0100 — and measure it for BOTH material pairs, Refined vs Matte and Refined vs Hybrid, since step 2c exists because the criterion was only ever measured on the pair that already differed; (4) ctest and pytest green, baseline totals lower than at Task 3; (5) the six `kit-final` captures attached for the owner's eyes.

Two surfaces need looking at by eye in this pass because steps 2b and 2c change them and no
ratchet covers either: the **session strip's checked thumbnail**, which lost its 2 px accent rim
in Task 8 and should get one back from the chip's accent edge; and a **Hybrid panel**, which
should now read as a different material from Refined rather than a 2 px radius apart.

- [ ] **Step 4: Commit and mark the spec shipped**

Edit the spec's status line to `**Status:** shipped 2026-MM-DD on wave/s-plus-ui; commits <first>..<last>.` Then:
```powershell
git add qt_ui/style/SvStyle.cpp tests/cpp/test_sv_style.cpp docs/superpowers/specs/2026-09-07-foundation-kit-design.md
git commit -m "feat(style): every site names its own role; the object-name map is deleted

The temporary map that let unmigrated pages draw correctly has no callers left.
roleOf and surfaceOf read the property only, and the test says so. A checked chip
carries an accent tint instead of a white veil, so selection reads on the light
presets too. The wave's five criteria are recorded in the ledger with the
measured numbers."
```

---

## Self-review (run by the plan author)

**Spec coverage.** §2.1 style: Task 2 (drawing, metrics, roles, `refreshAll`) and Task 4 (`rail` role in use). §2.2 factories: Task 3. §2.3 fonts, ramp, `numericFont`, mono sheets: Task 1. §2.4 retreat, migration order 1-7: Tasks 2 (install), 4 (shell), 5 (cockpit), 6 (library), 7 (studios), 8 (remaining), 9 (map deleted); `@token@` conversion: Task 4 step 3 and Task 5 step 2; `assertNoUnresolvedTokens` on every generator: Task 5 step 2 adds it to the cockpit sheet, Task 8 step 2 applies the same line to settings/home/mode sheets (add it there when editing them); dashboard radius constants: Task 5 step 4. §2.5 live switching and the Arcane Glass default: `refreshAll` wired in Task 2; **the default preset for fresh installs is not yet a task** — add to Task 8 step 2: in `qt_ui/ThemeManager.cpp:522` (the reset default) and `:531` (the `load()` fallback) the default value is already `Preset::ArcaneGlass` (index 0) per the audit sweep; verify with `grep -n "themePreset" qt_ui/ThemeManager.cpp` that the fallback argument is `0`, and record in `progress.md`; if it is not 0, change it there. §2.6 ratchets: Task 1 (`font-family-is-shipped`), Task 3 (the other five). §2.7 tests: `test_sv_style` Task 2/3/9, `test_sv_fonts` Task 1, matrix every task, captures and compare Tasks 4-9, startup trace Task 1 and 9. §2.8 criteria: Task 9 step 3.

**Placeholders.** None: every code step carries its code; the two "measured" values (baselines, compare fraction) are produced by commands in the same step.

**Type consistency.** `Role`/`Surface` enums, `SvStyle::roleName/surfaceName`, `kit::setRole/setSurface/button/chip/card/row`, `registerBundledFonts/bundledFamilies/fontsDirectory`, `ThemeManager::numericFont` are used with the same names and signatures in Tasks 1-9.
