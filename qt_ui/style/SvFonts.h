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
// <exe dir>/../../qt_ui/fonts (the Debug build tree), <cwd>/qt_ui/fonts (the dev launcher starts
// the app from the repo root). The first that exists wins; otherwise the first candidate is
// returned so a log line can say where the app looked.
QString fontsDirectory();

} // namespace spellvision::style
