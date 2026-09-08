#pragma once
//
// THE ENVIRONMENT main.cpp ESTABLISHES BEFORE ANY WIDGET EXISTS -- in one place, for every C++ test.
//
// This header exists because the same defect was found three times, each time by tripping over it
// rather than by looking for it:
//
//   1. task 8, R3  -- the harness never installed SvStyle, so kit::setSurface's svSurface property
//                     was set and never READ: the plate came back #2d2d2d under test against
//                     #f7faff in the app, and a selection separation measured 2.22 levels where the
//                     app shows 12.58.
//   2. task 9, N2  -- the harness never called registerBundledFonts(), so it measured SEGOE UI while
//                     the app ships IBM Plex Sans. Load-bearing, not cosmetic: `READY` advances
//                     34 px under Segoe and 36 under Plex, in a 34 px box.
//   3. final review, I1 -- the harness never called applyApplicationChrome(), so every colour it
//                     measured was taken under the PLATFORM palette. Rendering FirstRunDialog from
//                     the harness produced a near-black ground under light-theme content while the
//                     cards inside painted light: two different programs in one image.
//
// The shape is always "main.cpp does something before any widget exists, and the test binary does
// not", and every measurement taken without it is a measurement of a different program. Enumerating
// the family in one function is the only way a fourth member gets fixed everywhere at once instead
// of wherever somebody happened to be standing.
//
// Call it FIRST in initTestCase, before any widget is constructed and before a message handler is
// installed -- the same order main.cpp uses (style, then fonts, then chrome, then anything else).
// It returns the bundled family list so a caller can assert on it (see
// `the_suite_measures_the_typeface_the_app_ships`).
//
#include "ThemeManager.h"
#include "style/SvFonts.h"
#include "style/SvStyle.h"

#include <QApplication>
#include <QFont>
#include <QString>
#include <QStringList>

namespace spellvision::testenv
{
inline QStringList applyShippedAppEnvironment()
{
    // One style draws every control (main.cpp:291). Installed before any widget exists so nothing is
    // ever polished by the platform default.
    QApplication::setStyle(new spellvision::style::SvStyle);

    // The bundled IBM Plex faces, and the same 12 px main.cpp sets (main.cpp:297-305). A different
    // pixel size here would be a third program again, so it is copied deliberately rather than
    // chosen.
    const QStringList bundled = spellvision::style::registerBundledFonts();
    QFont ui(bundled.contains(QStringLiteral("IBM Plex Sans")) ? QStringLiteral("IBM Plex Sans")
                                                              : QStringLiteral("Segoe UI"));
    ui.setStyleHint(QFont::SansSerif);
    ui.setHintingPreference(QFont::PreferFullHinting);
    ui.setPixelSize(12);
    QApplication::setFont(ui);

    // The themed palette and the overlay sheet, pushed onto qApp (main.cpp:310). Without it a test
    // measures widget colours against the platform's application palette, which is not the app's.
    ThemeManager::instance().applyApplicationChrome();

    return bundled;
}
} // namespace spellvision::testenv
