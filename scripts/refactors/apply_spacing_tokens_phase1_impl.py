"""
Spacing Tokens Phase 1 (implementation): define the token accessors.

Companion to the header patch. Implements the five accessors declared
in Phase 1's header change:

    int   spacing(Spacing)   -> the 4/8/12/16/24/32 scale
    int   chrome(Chrome)     -> fixed structural chrome dimensions
    int   radiusCard()       -> 14px
    int   radiusControl()    -> 9px
    int   radiusPill()       -> 999px

These return constants. Spacing is theme-invariant -- there is no
preset_ switch here, unlike the QColor methods. The values are chosen
to match what the cleanest existing pages (T2I, Settings) already use
de facto, so Phase 2 migration is a rename rather than a reflow.

The chrome values come straight from the magic literals currently in
the shell: 32px title bar, 40px menu bar, 24px status strip, 30px
telemetry bar, 76px mode rail. Centralizing them changes nothing yet
-- Phase 2 points the shell at these instead of the literals.

Inserted right after effectsWeight()'s definition to keep the simple
value accessors grouped, mirroring the header ordering.
"""
from pathlib import Path
path = Path("qt_ui/ThemeManager.cpp")
text = path.read_text(encoding="utf-8")

# effectsWeight() is a tiny accessor: `return effectsWeight_;` at line ~111.
# Anchor on the full function so the insertion lands right after it.
needle = '''int ThemeManager::effectsWeight() const
{
    return effectsWeight_;
}'''

replacement = '''int ThemeManager::effectsWeight() const
{
    return effectsWeight_;
}

// --- Spacing Tokens Phase 1: token accessor definitions ---
//
// Constants, not preset-switched: the spacing rhythm and structural
// chrome dimensions are the same across all four themes. Only color
// varies per preset. Values mirror what T2I / Settings already use, so
// Phase 2 migration is a rename, not a reflow.

int ThemeManager::spacing(Spacing token) const
{
    switch (token)
    {
    case Spacing::Hairline: return 4;
    case Spacing::Tight:    return 8;
    case Spacing::Snug:     return 12;
    case Spacing::Card:     return 16;
    case Spacing::Section:  return 24;
    case Spacing::Gutter:   return 32;
    }
    return 16; // Spacing::Card -- safe default if a new token is unhandled.
}

int ThemeManager::chrome(Chrome token) const
{
    switch (token)
    {
    case Chrome::TitleBarHeight:    return 32;
    case Chrome::MenuBarHeight:     return 40;
    case Chrome::StatusStripHeight: return 24;
    case Chrome::TelemetryBarHeight:return 30;
    case Chrome::ModeRailWidth:     return 76;
    }
    return 32; // safe default.
}

int ThemeManager::radiusCard() const
{
    return 14;
}

int ThemeManager::radiusControl() const
{
    return 9;
}

int ThemeManager::radiusPill() const
{
    return 999;
}'''

if needle not in text:
    raise SystemExit("Could not find effectsWeight() definition in ThemeManager.cpp")
text = text.replace(needle, replacement, 1)

path.write_text(text, encoding="utf-8")
print("Applied Spacing Tokens Phase 1 (implementation): token accessors defined.")
